//! Whisper backend (whisper.cpp via whisper-rs, Vulkan GPU-only).
//! GPU-only by design: no CPU fallback (large-v3 on CPU is unusable; CPU is Parakeet's job).

use crate::decoder::{TimedToken, TranscriptionResult};
use crate::timestamps::TimestampMode;
use crate::transcriber::Transcriber;
use eyre::{eyre, Result as EyreResult};
#[cfg(feature = "whisper-vulkan")]
use std::collections::HashSet;
#[cfg(feature = "whisper-vulkan")]
use std::ffi::CStr;
use whisper_rs::{
    FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters, WhisperState,
};

// Vulkan device enumeration helpers — only available when whisper-rs is built
// with the Vulkan backend. The CUDA build omits these symbols and falls back to
// a dummy device id of 0 (whisper.cpp's default GPU in CUDA mode).

#[cfg(feature = "whisper-vulkan")]
/// Number of Vulkan devices ggml can see. Used at startup to decide whether
/// the Whisper backend is available at all (0 ⇒ unavailable, never CPU).
pub fn vulkan_device_count() -> i32 {
    whisper_rs::vulkan::list_devices().len() as i32
}

#[cfg(not(feature = "whisper-vulkan"))]
/// CUDA build: Vulkan enumeration is unavailable; return 1 so the daemon
/// treats the CUDA device as present (device selection is CUDA-managed).
pub fn vulkan_device_count() -> i32 {
    1
}

#[cfg(feature = "whisper-vulkan")]
/// Pick the best Vulkan device by reading the driver-reported device type, not
/// by guessing from VRAM size. The ggml generic backend API exposes each device's
/// real type (`GGML_BACKEND_DEVICE_TYPE_GPU` = 1 for dedicated, `_IGPU` = 2 for
/// integrated). We build a set of names/descriptions of all devices the driver
/// reports as dedicated GPU, then keep only those Vulkan devices whose name is in
/// that set, and among them pick the one with the most free VRAM.
///
/// Returns `None` if there are no Vulkan devices, or if none are dedicated GPUs
/// (an iGPU at RTF ~4.5 is unusable for Whisper large-v3; no fallback is provided).
pub fn select_vulkan_device() -> Option<i32> {
    use whisper_rs::whisper_rs_sys::{
        ggml_backend_dev_count, ggml_backend_dev_get, ggml_backend_dev_get_props,
        ggml_backend_dev_props, ggml_backend_dev_type as ggml_dev_type_fn,
        ggml_backend_dev_type_GGML_BACKEND_DEVICE_TYPE_GPU,
    };

    let devs = whisper_rs::vulkan::list_devices();
    if devs.is_empty() {
        return None;
    }

    // Build a set of all names/descriptions reported as dedicated GPU by the ggml
    // generic backend API (type == GGML_BACKEND_DEVICE_TYPE_GPU == 1).
    let mut dedicated_names: HashSet<String> = HashSet::new();
    // SAFETY: all ggml_backend_dev_* functions are safe to call after library
    // init; they read internal ggml state set up by whisper_rs during load.
    unsafe {
        let count = ggml_backend_dev_count();
        for i in 0..count {
            let dev = ggml_backend_dev_get(i);
            if dev.is_null() {
                continue;
            }
            let dev_type = ggml_dev_type_fn(dev);
            if dev_type != ggml_backend_dev_type_GGML_BACKEND_DEVICE_TYPE_GPU {
                continue;
            }
            // Zero-initialise props; ggml_backend_dev_get_props fills it in.
            let mut props: ggml_backend_dev_props = std::mem::zeroed();
            ggml_backend_dev_get_props(dev, &mut props);
            if !props.name.is_null() {
                dedicated_names
                    .insert(CStr::from_ptr(props.name).to_string_lossy().into_owned());
            }
            if !props.description.is_null() {
                dedicated_names
                    .insert(CStr::from_ptr(props.description).to_string_lossy().into_owned());
            }
        }
    }

    // Among Vulkan devices whose name matches a dedicated GPU, pick highest free VRAM.
    devs.iter()
        .filter(|d| dedicated_names.contains(&d.name))
        .max_by_key(|d| d.vram.free)
        .map(|d| d.id)
}

#[cfg(not(feature = "whisper-vulkan"))]
/// CUDA build: Vulkan enumeration is unavailable; return device 0 (whisper.cpp
/// picks the CUDA device by itself in this mode).
pub fn select_vulkan_device() -> Option<i32> {
    Some(0)
}

#[cfg(feature = "whisper-vulkan")]
/// Free VRAM (bytes) reported by the Vulkan driver for the given device id, or
/// `None` if that id is not among the enumerated devices. Used as a startup
/// guard so the daemon can refuse with a clear message instead of OOM-ing.
pub fn device_free_vram(gpu_device: i32) -> Option<usize> {
    whisper_rs::vulkan::list_devices()
        .into_iter()
        .find(|d| d.id == gpu_device)
        .map(|d| d.vram.free)
}

#[cfg(not(feature = "whisper-vulkan"))]
/// CUDA build: Vulkan VRAM query is unavailable; return `None` so the daemon
/// skips the VRAM fit guard (CUDA OOM handling is left to whisper.cpp).
pub fn device_free_vram(_gpu_device: i32) -> Option<usize> {
    None
}

/// Per-backend decoding knobs, all overridable via `DICTEE_WHISPER_RUST_*`
/// environment variables (read once at backend construction = daemon startup).
/// Defaults reproduce the committed β / Meetily strategy exactly, so an unset
/// environment changes nothing. The `DICTEE_WHISPER_RUST_` prefix keeps these
/// distinct from faster-whisper's `DICTEE_WHISPER_*` (Python) variables.
#[derive(Clone, Copy, Debug, PartialEq)]
struct WhisperTuning {
    temperature: f32,
    /// α/β switch: `-1` disables the temperature fallback (α: deterministic, no
    /// fallback loops); the whisper.cpp default `0.2` keeps it (β: recovers hard
    /// passages in long audio).
    temperature_inc: f32,
    beam_size: i32,
    no_speech_thold: f32,
    entropy_thold: f32,
    logprob_thold: f32,
    /// audio_ctx override: `None`/`Some(0)` = full context (default, no cap);
    /// `Some(n>0)` = fixed cap (advanced — a cap below the clip length truncates
    /// speech). whisper.cpp itself treats audio_ctx 0 as "use full 1500".
    audio_ctx: Option<i32>,
}

impl WhisperTuning {
    fn from_env() -> Self {
        WhisperTuning {
            temperature: env_f32("DICTEE_WHISPER_RUST_TEMPERATURE", 0.3),
            temperature_inc: env_f32("DICTEE_WHISPER_RUST_TEMPERATURE_INC", 0.2),
            beam_size: env_i32("DICTEE_WHISPER_RUST_BEAM_SIZE", 5).max(1),
            no_speech_thold: env_f32("DICTEE_WHISPER_RUST_NO_SPEECH_THOLD", 0.55),
            entropy_thold: env_f32("DICTEE_WHISPER_RUST_ENTROPY_THOLD", 2.4),
            logprob_thold: env_f32("DICTEE_WHISPER_RUST_LOGPROB_THOLD", -1.0),
            audio_ctx: std::env::var("DICTEE_WHISPER_RUST_AUDIO_CTX")
                .ok()
                .and_then(|v| v.trim().parse::<i32>().ok()),
        }
    }
}

/// Parse an env var as f32, falling back to `default` if unset or unparseable.
fn env_f32(key: &str, default: f32) -> f32 {
    std::env::var(key)
        .ok()
        .and_then(|v| v.trim().parse::<f32>().ok())
        .unwrap_or(default)
}

/// Parse an env var as i32, falling back to `default` if unset or unparseable.
fn env_i32(key: &str, default: i32) -> i32 {
    std::env::var(key)
        .ok()
        .and_then(|v| v.trim().parse::<i32>().ok())
        .unwrap_or(default)
}

pub struct WhisperBackend {
    _ctx: WhisperContext,
    state: WhisperState,
    lang: String,
    tuning: WhisperTuning,
}

impl WhisperBackend {
    /// Load a ggml model onto the chosen Vulkan device. GPU-only: errors if the
    /// device index is negative (caller must have a usable Vulkan device).
    pub fn from_ggml(ggml_path: &str, gpu_device: i32, lang: &str) -> EyreResult<Self> {
        if gpu_device < 0 {
            return Err(eyre!("Whisper is GPU-only: no usable Vulkan device"));
        }
        let mut cparams = WhisperContextParameters::default();
        cparams.gpu_device = gpu_device;
        let ctx = WhisperContext::new_with_params(ggml_path, cparams)
            .map_err(|e| eyre!("failed to load ggml {ggml_path}: {e:?}"))?;
        // SAFETY of lifetimes: store ctx alongside state; state borrows from ctx
        // via the crate's own self-referential handling (create_state takes &ctx).
        let state = ctx.create_state().map_err(|e| eyre!("create_state: {e:?}"))?;
        let lang = if lang.is_empty() { "auto".to_string() } else { lang.to_string() };
        Ok(Self { _ctx: ctx, state, lang, tuning: WhisperTuning::from_env() })
    }
}

impl Transcriber for WhisperBackend {
    fn transcribe_samples(
        &mut self,
        audio: Vec<f32>,
        sample_rate: u32,
        channels: u16,
        _mode: Option<TimestampMode>,
    ) -> crate::error::Result<TranscriptionResult> {
        if sample_rate != 16000 || channels != 1 {
            return Err(crate::error::Error::Audio(format!(
                "Whisper expects 16 kHz mono, got {sample_rate} Hz / {channels} ch"
            )));
        }
        let t = self.tuning;
        let mut params =
            FullParams::new(SamplingStrategy::BeamSearch { beam_size: t.beam_size, patience: 1.0 });
        params.set_language(Some(&self.lang));

        // Anti-hallucination (β / Meetily strategy by default, verified against
        // whisper.cpp defaults). All knobs below are overridable per use-case via
        // DICTEE_WHISPER_RUST_* env vars (see WhisperTuning). The default
        // temperature_inc 0.2 keeps the temperature fallback so hard passages in
        // long meeting audio still recover; set it to -1 (α) for deterministic,
        // fallback-free dictation. clean_repetitive_text() (below) is the safety
        // net against repetition loops regardless of these settings.
        params.set_temperature(t.temperature);
        params.set_temperature_inc(t.temperature_inc);
        params.set_suppress_blank(true);
        params.set_suppress_nst(true); // drop non-speech tokens ([music], "thank you"...)
        params.set_no_context(true); // clean prompt per request (no cross-request bleed)
        params.set_entropy_thold(t.entropy_thold);
        params.set_logprob_thold(t.logprob_thold);
        params.set_no_speech_thold(t.no_speech_thold);
        // no_timestamps(true)+token_timestamps(true): avoids whisper.cpp chunk-skip that
        // discards valid text (verified behavior in the Meetily whisper engine).
        params.set_no_timestamps(true);
        params.set_token_timestamps(true);

        // audio_ctx: default = full context (whisper.cpp's 1500-position / 30 s
        // window), matching the whisper.cpp ecosystem on GPU (Handy, Hyprnote,
        // Meetily, vocalinux; dsnote truncates only on CPU). Truncating the encoder
        // context below ~512 makes whisper.cpp repeat/double its output
        // (ggerganov, whisper.cpp#137) and is actually SLOWER on Vulkan (measured
        // 2026-06-23), so we never cap by default. Advanced override via env
        // DICTEE_WHISPER_RUST_AUDIO_CTX: 0 / unset → full; n>0 → fixed cap (a cap
        // below the clip length silently truncates speech — verified — so use care).
        if let Some(n) = t.audio_ctx {
            if n > 0 {
                params.set_audio_ctx(n.min(1500));
            }
        }

        let n_threads = std::thread::available_parallelism()
            .map(|n| n.get() as i32)
            .unwrap_or(4);
        params.set_n_threads(n_threads);

        params.set_print_special(false);
        params.set_print_progress(false);
        params.set_print_realtime(false);
        params.set_print_timestamps(false);

        self.state
            .full(params, &audio)
            .map_err(|e| crate::error::Error::Model(format!("whisper full(): {e:?}")))?;

        let n = self.state.full_n_segments();
        let mut text = String::new();
        let mut tokens = Vec::new();
        for i in 0..n {
            let Some(seg) = self.state.get_segment(i) else {
                continue;
            };
            let s = seg.to_str_lossy().map(|c| c.into_owned()).unwrap_or_default();
            tokens.push(TimedToken {
                text: s.trim().to_string(),
                start: seg.start_timestamp() as f32 / 100.0,
                end: seg.end_timestamp() as f32 / 100.0,
            });
            text.push_str(&s);
        }
        Ok(TranscriptionResult { text: clean_repetitive_text(text.trim()), tokens })
    }
}

/// Absolute ceiling (in words) on the repeating block we try to collapse — a
/// perf bound only. The effective bound at each position is min(this, (n-i)/3),
/// since a block needs ≥3 consecutive repeats to be a loop. Real large-v3(-turbo)
/// loops are short phrases (seen up to ~10 words); 32 leaves a wide margin while
/// keeping the scan near-linear and genuine long verbatim repeats (rare) safe.
const MAX_REPEAT_BLOCK: usize = 32;

/// Collapse pathological consecutive repetition that large-v3(-turbo) emits even
/// with beam search + temperature fallback. Handles both single-word runs
/// ("chat chat chat") AND multi-word phrase loops ("du plasmoïda du plasmoïda …",
/// "et de la et de la …") that the single-word pass misses because the words
/// alternate. A block (1..=MAX_REPEAT_BLOCK words) repeated 3+ times in a row is
/// collapsed to one occurrence; a single doubling (legitimate emphasis like
/// "très très" or a phrase said twice) is left alone. Whitespace is normalized
/// to single spaces. Pure function — no model state.
fn clean_repetitive_text(text: &str) -> String {
    let words: Vec<&str> = text.split_whitespace().collect();
    let n = words.len();
    if n == 0 {
        return String::new();
    }
    let mut out: Vec<&str> = Vec::with_capacity(n);
    let mut i = 0;
    while i < n {
        // At position i, find the block length k whose consecutive repetition
        // covers the most words (reps*k), among blocks repeated 3+ times.
        // Prefer the smallest k on ties so "a a a a" collapses as a single word,
        // not as the 2-word block "a a".
        // A block of length k can repeat ≥3× only if 3k ≤ remaining, so cap at
        // (n-i)/3; never search beyond the perf ceiling.
        let max_k = MAX_REPEAT_BLOCK.min((n - i) / 3);
        let mut best_k = 0;
        let mut best_reps = 0;
        for k in 1..=max_k {
            let mut reps = 1;
            while i + (reps + 1) * k <= n && words[i + reps * k..i + (reps + 1) * k] == words[i..i + k] {
                reps += 1;
            }
            if reps >= 3 && reps * k > best_reps * best_k {
                best_k = k;
                best_reps = reps;
            }
        }
        if best_k > 0 {
            // Keep one copy of the block, skip all its repetitions.
            for w in &words[i..i + best_k] {
                out.push(w);
            }
            i += best_reps * best_k;
        } else {
            out.push(words[i]);
            i += 1;
        }
    }
    out.join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::transcriber::Transcriber;
    use crate::timestamps::TimestampMode;

    #[test]
    fn collapses_consecutive_word_repetition() {
        let out = clean_repetitive_text("le chat chat chat chat dort");
        assert_eq!(out, "le chat dort");
    }

    #[test]
    fn leaves_normal_text_untouched() {
        let s = "Bonjour, ceci est un test de transcription.";
        assert_eq!(clean_repetitive_text(s), s);
    }

    #[test]
    fn allows_legitimate_double_word() {
        // "très très" (one repeat) is legitimate emphasis — keep both.
        let s = "c'est très très bien";
        assert_eq!(clean_repetitive_text(s), s);
    }

    #[test]
    fn collapses_two_word_phrase_loop() {
        // Real large-v3-turbo hallucination captured from a 1.36 s clip:
        // a 2-word phrase looped 25× ("du plasmoïda du plasmoïda ...").
        // Words alternate so the single-word collapse misses it entirely.
        let out = clean_repetitive_text("du plasmoïda du plasmoïda du plasmoïda du plasmoïda");
        assert_eq!(out, "du plasmoïda");
    }

    #[test]
    fn collapses_three_word_phrase_loop() {
        let out = clean_repetitive_text("et de la et de la et de la et de la");
        assert_eq!(out, "et de la");
    }

    #[test]
    fn keeps_phrase_repeated_once() {
        // A phrase said twice is legitimate emphasis (run == 2) — keep it.
        let s = "c'est bien c'est bien";
        assert_eq!(clean_repetitive_text(s), s);
    }

    #[test]
    fn collapses_loop_with_clean_prefix() {
        let out = clean_repetitive_text("bonjour du plasmoïda du plasmoïda du plasmoïda");
        assert_eq!(out, "bonjour du plasmoïda");
    }

    #[test]
    fn collapses_nine_word_phrase_loop() {
        // Real large-v3-turbo loop captured live: a 9-word phrase repeated.
        // The 8-word cap missed this; the block bound is now (n-i)/3.
        let p = "j'aimerais bien savoir ce qui s'est passé quand même.";
        let looped = format!("{p} {p} {p} {p} {p}");
        assert_eq!(clean_repetitive_text(&looped), p);
    }

    #[test]
    fn collapses_long_phrase_loop_with_lowercase_prefix() {
        // Mirrors the captured transcript: "Bon," + a first lowercase copy that
        // differs from the capitalized loop body, then the loop.
        let body = "J'aimerais bien savoir ce qui s'est passé quand même.";
        let looped = format!(
            "Bon, j'aimerais bien savoir ce qui s'est passé quand même. {body} {body} {body} {body}"
        );
        let out = clean_repetitive_text(&looped);
        // Loop collapsed: the capitalized block appears exactly once at the end.
        assert_eq!(out.matches(body).count(), 1);
        assert!(out.starts_with("Bon, j'aimerais"));
    }

    #[test]
    fn empty_stays_empty() {
        assert_eq!(clean_repetitive_text(""), "");
    }

    #[test]
    fn env_helpers_parse_and_fall_back() {
        // Unique keys so parallel tests can't interfere.
        std::env::set_var("DICTEE_TEST_F32", " 0.42 ");
        assert_eq!(env_f32("DICTEE_TEST_F32", 9.9), 0.42);
        assert_eq!(env_f32("DICTEE_TEST_F32_UNSET", 9.9), 9.9);
        std::env::set_var("DICTEE_TEST_F32_BAD", "notanumber");
        assert_eq!(env_f32("DICTEE_TEST_F32_BAD", 9.9), 9.9);
        std::env::set_var("DICTEE_TEST_I32", "7");
        assert_eq!(env_i32("DICTEE_TEST_I32", 3), 7);
        assert_eq!(env_i32("DICTEE_TEST_I32_UNSET", 3), 3);
    }

    #[test]
    fn tuning_defaults_match_committed_beta_strategy() {
        // With no DICTEE_WHISPER_RUST_* set, defaults reproduce the β strategy.
        let t = WhisperTuning::from_env();
        assert_eq!(t.temperature, 0.3);
        assert_eq!(t.temperature_inc, 0.2);
        assert_eq!(t.beam_size, 5);
        assert_eq!(t.no_speech_thold, 0.55);
        assert_eq!(t.entropy_thold, 2.4);
        assert_eq!(t.logprob_thold, -1.0);
        assert_eq!(t.audio_ctx, None);
    }

    #[test]
    fn device_free_vram_is_none_for_bogus_id() {
        // A device id that cannot exist must return None, never panic.
        assert_eq!(device_free_vram(-999), None);
    }

    #[test]
    fn device_selection_never_panics_and_is_in_range() {
        let n = vulkan_device_count();
        match select_vulkan_device() {
            Some(idx) => assert!(idx >= 0 && idx < n, "idx {idx} out of 0..{n}"),
            None => assert_eq!(n, 0, "got None but {n} devices exist"),
        }
    }

    /// Verify that `select_vulkan_device` picks the dedicated NVIDIA GPU and not
    /// the Intel iGPU on this dev box (Intel iGPU = device 0, RTX 4070 = device 1).
    /// Run with:
    ///   cargo test --features whisper-vulkan whisper::tests::selects_dedicated_gpu_not_igpu \
    ///     -- --ignored --nocapture
    #[cfg(feature = "whisper-vulkan")]
    #[test]
    #[ignore]
    fn selects_dedicated_gpu_not_igpu() {
        let devs = whisper_rs::vulkan::list_devices();
        let chosen_id = select_vulkan_device();
        println!("Vulkan devices:");
        for d in &devs {
            println!("  id={} name={:?} vram_free={} MiB", d.id, d.name, d.vram.free / (1024 * 1024));
        }
        if let Some(id) = chosen_id {
            let chosen = devs.iter().find(|d| d.id == id).expect("chosen id not in list");
            println!("Selected: id={} name={:?}", chosen.id, chosen.name);
            assert!(
                !chosen.name.to_lowercase().contains("intel"),
                "selected an Intel iGPU: {:?}",
                chosen.name
            );
            assert!(
                chosen.name.to_lowercase().contains("nvidia")
                    || chosen.name.to_lowercase().contains("rtx")
                    || chosen.name.to_lowercase().contains("geforce"),
                "expected NVIDIA RTX 4070, got: {:?}",
                chosen.name
            );
        } else {
            println!("select_vulkan_device() returned None — no dedicated GPU found (expected on headless CI)");
        }
    }

    // Gated: needs the 3 GB ggml on disk. Run with: cargo test --features whisper -- --ignored
    #[test]
    #[ignore]
    fn transcribes_french_with_punctuation() {
        let ggml = "/home/rapha/.local/share/voxtype/models/ggml-large-v3.bin";
        let mut reader = hound::WavReader::open("tests/poc-kyutai/ref-fr.wav").unwrap();
        let spec = reader.spec();
        let audio: Vec<f32> = reader
            .samples::<i16>()
            .map(|s| s.unwrap() as f32 / 32768.0)
            .collect();

        let mut be = WhisperBackend::from_ggml(ggml, 1, "fr").expect("load ggml");
        let res = be
            .transcribe_samples(audio, spec.sample_rate, spec.channels, Some(TimestampMode::Sentences))
            .unwrap();

        // The whole point of the port: punctuation + capitalization restored.
        println!("transcript: {:?}", res.text);
        assert!(res.text.contains("Bonjour"), "onset/caps lost: {:?}", res.text);
        assert!(
            res.text.contains('.') || res.text.contains(','),
            "no punctuation: {:?}",
            res.text
        );
        assert!(!res.text.trim().is_empty());
    }
}
