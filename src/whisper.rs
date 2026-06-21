//! Whisper backend (whisper.cpp via whisper-rs, Vulkan GPU-only).
//! GPU-only by design: no CPU fallback (large-v3 on CPU is unusable; CPU is Parakeet's job).

use crate::decoder::{TimedToken, TranscriptionResult};
use crate::timestamps::TimestampMode;
use crate::transcriber::Transcriber;
use eyre::{eyre, Result as EyreResult};
use whisper_rs::{
    FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters, WhisperState,
};

/// Number of Vulkan devices ggml can see. Used at startup to decide whether
/// the Whisper backend is available at all (0 ⇒ unavailable, never CPU).
pub fn vulkan_device_count() -> i32 {
    whisper_rs::vulkan::list_devices().len() as i32
}

/// Pick the best Vulkan device: prefer a dedicated GPU. An integrated GPU (uma)
/// reports system RAM as its VRAM, so we heuristically skip any device whose
/// total VRAM is implausibly large (> 24 GiB ≈ desktop/server dGPU ceiling for
/// laptops; an iGPU on a 32-64 GB machine reports way more). Falls back to the
/// device with the most *plausible* VRAM. Returns None if no device at all.
pub fn select_vulkan_device() -> Option<i32> {
    let devs = whisper_rs::vulkan::list_devices();
    if devs.is_empty() {
        return None;
    }
    const IGPU_VRAM_CEILING: usize = 24 * 1024 * 1024 * 1024; // 24 GiB
    // Prefer plausible-dedicated devices (total <= ceiling), largest total wins.
    let dedicated = devs
        .iter()
        .filter(|d| d.vram.total <= IGPU_VRAM_CEILING)
        .max_by_key(|d| d.vram.total);
    // Fallback: if everything looks like an iGPU, take the largest anyway.
    let chosen = dedicated.or_else(|| devs.iter().max_by_key(|d| d.vram.total))?;
    Some(chosen.id)
}

pub struct WhisperBackend {
    _ctx: WhisperContext,
    state: WhisperState,
}

impl WhisperBackend {
    /// Load a ggml model onto the chosen Vulkan device. GPU-only: errors if the
    /// device index is negative (caller must have a usable Vulkan device).
    pub fn from_ggml(ggml_path: &str, gpu_device: i32) -> EyreResult<Self> {
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
        Ok(Self { _ctx: ctx, state })
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
            FullParams::new(SamplingStrategy::BeamSearch { beam_size: 5, patience: -1.0 });
        params.set_language(Some("auto"));
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
        Ok(TranscriptionResult { text: text.trim().to_string(), tokens })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::transcriber::Transcriber;
    use crate::timestamps::TimestampMode;

    #[test]
    fn device_selection_never_panics_and_is_in_range() {
        let n = vulkan_device_count();
        match select_vulkan_device() {
            Some(idx) => assert!(idx >= 0 && idx < n, "idx {idx} out of 0..{n}"),
            None => assert_eq!(n, 0, "got None but {n} devices exist"),
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

        let mut be = WhisperBackend::from_ggml(ggml, 1).expect("load ggml");
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
