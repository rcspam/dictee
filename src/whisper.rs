//! Whisper backend (whisper.cpp via whisper-rs, Vulkan GPU-only).
//! GPU-only by design: no CPU fallback (large-v3 on CPU is unusable; CPU is Parakeet's job).

use crate::decoder::{TimedToken, TranscriptionResult};
use crate::timestamps::TimestampMode;
use crate::transcriber::Transcriber;
use eyre::{eyre, Result as EyreResult};
use std::collections::HashSet;
use std::ffi::CStr;
use whisper_rs::{
    FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters, WhisperState,
};

/// Number of Vulkan devices ggml can see. Used at startup to decide whether
/// the Whisper backend is available at all (0 ⇒ unavailable, never CPU).
pub fn vulkan_device_count() -> i32 {
    whisper_rs::vulkan::list_devices().len() as i32
}

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

pub struct WhisperBackend {
    _ctx: WhisperContext,
    state: WhisperState,
    lang: String,
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
        Ok(Self { _ctx: ctx, state, lang })
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
        let mut params =
            FullParams::new(SamplingStrategy::BeamSearch { beam_size: 5, patience: 1.0 });
        params.set_language(Some(&self.lang));

        // Anti-hallucination (β / Meetily strategy, verified against whisper.cpp defaults).
        // temperature is 0.3 and temperature_inc is left at its 0.2 default so the
        // temperature fallback still recovers hard passages in long meeting audio;
        // clean_repetitive_text() (below) is the safety net against repetition loops.
        params.set_temperature(0.3);
        params.set_suppress_blank(true);
        params.set_suppress_nst(true); // drop non-speech tokens ([music], "thank you"...)
        params.set_no_context(true); // clean prompt per request (no cross-request bleed)
        params.set_entropy_thold(2.4);
        params.set_logprob_thold(-1.0);
        params.set_no_speech_thold(0.55);
        // no_timestamps(true)+token_timestamps(true): avoids whisper.cpp chunk-skip that
        // discards valid text (verified behavior in the Meetily whisper engine).
        params.set_no_timestamps(true);
        params.set_token_timestamps(true);

        // Cap the encoder context to the real clip length on short dictation: the
        // decoder then can't hallucinate over the 30 s silence padding, and it's
        // faster. Long audio keeps the full context.
        let dur_s = audio.len() as f32 / 16000.0;
        if let Some(ctx) = audio_ctx_for(dur_s) {
            params.set_audio_ctx(ctx);
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

/// Map a clip duration (seconds) to a whisper `audio_ctx` cap, or `None` to keep
/// the full 1500-position context. whisper.cpp always pads input to a 30 s window
/// = 1500 encoder positions (1 position = 20 ms, verified whisper.cpp:6279). On a
/// short clip the remainder is silence the decoder can hallucinate over; capping
/// audio_ctx to the real length (+ ~2 s margin) removes that and lowers latency.
/// Applied only for clips clearly under the 30 s window; longer audio keeps full
/// context (whisper segments long audio into full 30 s windows internally).
fn audio_ctx_for(dur_s: f32) -> Option<i32> {
    if dur_s <= 0.0 || dur_s >= 28.0 {
        return None;
    }
    let ctx = (dur_s * 50.0).ceil() as i32 + 100; // +100 positions ≈ 2 s margin
    Some(ctx.min(1500))
}

/// Collapse pathological consecutive word repetition that large-v3 occasionally
/// emits even with beam search + temperature fallback. A run of the SAME word
/// repeated 3+ times in a row is collapsed to a single occurrence; a single
/// doubling (legitimate emphasis like "très très") is left alone. Whitespace is
/// normalized to single spaces. Pure function — no model state.
fn clean_repetitive_text(text: &str) -> String {
    let words: Vec<&str> = text.split_whitespace().collect();
    if words.is_empty() {
        return String::new();
    }
    let mut out: Vec<&str> = Vec::with_capacity(words.len());
    let mut i = 0;
    while i < words.len() {
        // Count how many times the current word repeats consecutively.
        let mut j = i + 1;
        while j < words.len() && words[j] == words[i] {
            j += 1;
        }
        let run = j - i;
        // run >= 3 → keep one; run == 1 or 2 → keep as-is (emphasis allowed).
        if run >= 3 {
            out.push(words[i]);
        } else {
            for w in &words[i..j] {
                out.push(w);
            }
        }
        i = j;
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
    fn empty_stays_empty() {
        assert_eq!(clean_repetitive_text(""), "");
    }

    #[test]
    fn audio_ctx_caps_short_clips() {
        assert_eq!(audio_ctx_for(4.0), Some(300)); // 4*50 + 100 margin
        assert_eq!(audio_ctx_for(1.0), Some(150));
    }

    #[test]
    fn audio_ctx_none_for_long_or_invalid() {
        assert_eq!(audio_ctx_for(30.0), None); // >= 30 s window: keep full
        assert_eq!(audio_ctx_for(28.0), None); // threshold
        assert_eq!(audio_ctx_for(0.0), None);
        assert_eq!(audio_ctx_for(-2.0), None);
    }

    #[test]
    fn audio_ctx_never_exceeds_1500() {
        assert_eq!(audio_ctx_for(27.9), Some(1495)); // 27.9*50=1395 +100=1495
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
    ///   cargo test --features whisper whisper::tests::selects_dedicated_gpu_not_igpu \
    ///     -- --ignored --nocapture
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
