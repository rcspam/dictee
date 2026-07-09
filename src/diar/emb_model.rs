//! WeSpeaker ResNet34 embedding model (masked 256-d speaker embeddings).
//!
//! Derived from speakrs v0.4.2 `inference/embedding` (Apache-2.0, see
//! src/diar/mod.rs), reduced to the single-session masked path (the only one
//! exercised by the base ONNX bundle) and wired through the crate's
//! `ExecutionConfig` session conventions.

use std::path::Path;

use ndarray::{Array1, Array2, Array3, s};
use ort::session::Session;
use ort::value::TensorRef;

use crate::error::{Error, Result};
use crate::execution::ModelConfig as ExecutionConfig;

const WINDOW_SAMPLES: usize = 160_000;
const MASK_FRAMES: usize = 589;
const DEFAULT_MIN_NUM_SAMPLES: usize = 400;

pub struct EmbeddingModel {
    session: Session,
    waveform_buffer: Array3<f32>,
    weights_buffer: Array2<f32>,
    min_num_samples: usize,
    resilience: crate::diar::resilient::GpuResilience,
}

impl EmbeddingModel {
    pub fn new(model_path: impl AsRef<Path>, exec_config: &ExecutionConfig) -> Result<Self> {
        let model_path = model_path.as_ref();
        let session = Self::build_session(model_path, exec_config)?;

        let metadata_path = model_path.with_extension("min_num_samples.txt");
        let min_num_samples =
            read_min_num_samples(&metadata_path).unwrap_or(DEFAULT_MIN_NUM_SAMPLES);

        Ok(Self {
            session,
            waveform_buffer: Array3::zeros((1, 1, WINDOW_SAMPLES)),
            weights_buffer: Array2::zeros((1, MASK_FRAMES)),
            min_num_samples,
            resilience: crate::diar::resilient::GpuResilience::new(
                "diar embedding",
                model_path.to_path_buf(),
                exec_config.clone(),
            ),
        })
    }

    fn build_session(model_path: &Path, exec_config: &ExecutionConfig) -> Result<Session> {
        let cfg = exec_config
            .clone()
            .with_intra_threads(1)
            .with_inter_threads(1)
            .with_custom_configure(|builder| {
                builder
                    .with_memory_pattern(true)?
                    .with_independent_thread_pool()
                    // strip the rc.12 recoverable builder state from the error
                    .map_err(Into::into)
            });
        let mut builder = cfg.apply_to_session_builder(Session::builder()?)?;
        Ok(builder.commit_from_file(model_path)?)
    }

    pub fn min_num_samples(&self) -> usize {
        self.min_num_samples
    }

    /// Extract a speaker embedding weighted by a segmentation mask, preferring
    /// the overlap-free "clean" mask when it carries enough frames.
    pub fn embed_masked(
        &mut self,
        audio: &[f32],
        mask: &[f32],
        clean_mask: Option<&[f32]>,
    ) -> Result<Array1<f32>> {
        let used_mask = select_mask(mask, clean_mask, audio.len(), self.min_num_samples);
        self.embed_single(audio, used_mask)
    }

    fn embed_single(&mut self, audio: &[f32], weights: &[f32]) -> Result<Array1<f32>> {
        let copy_len = audio.len().min(WINDOW_SAMPLES);
        self.waveform_buffer
            .slice_mut(s![0, 0, ..copy_len])
            .assign(&ndarray::ArrayView1::from(&audio[..copy_len]));
        if copy_len < WINDOW_SAMPLES {
            self.waveform_buffer.slice_mut(s![0, 0, copy_len..]).fill(0.0);
        }
        prepare_weights(weights, &mut self.weights_buffer);

        // Degraded to CPU earlier: periodically try to move back to the GPU.
        if self.resilience.should_probe_gpu() {
            match Self::build_session(&self.resilience.model_path, &self.resilience.exec_config) {
                Ok(session) => {
                    self.session = session;
                    self.resilience.mark_gpu();
                    eprintln!("[dictee] {} resumed on GPU.", self.resilience.label());
                }
                Err(_) => self.resilience.probe_failed(),
            }
        }

        let first = if self.resilience.inject_failure() {
            Err(Error::Diar(
                "injected GPU failure (DICTEE_DIAR_FAIL_WINDOW)".to_string(),
            ))
        } else {
            Self::infer(&mut self.session, &self.waveform_buffer, &self.weights_buffer)
        };
        match first {
            Ok(out) => Ok(out),
            // Mid-run GPU failure (typically VRAM exhausted by another app):
            // rebuild on CPU and retry THIS window, then keep going degraded.
            Err(e) if !self.resilience.on_cpu && self.resilience.gpu_preferred() => {
                eprintln!(
                    "[dictee] {} inference failed on GPU ({}); rebuilding on CPU and retrying.",
                    self.resilience.label(),
                    e
                );
                self.session =
                    Self::build_session(&self.resilience.model_path, &self.resilience.cpu_config())?;
                self.resilience.mark_cpu();
                Self::infer(&mut self.session, &self.waveform_buffer, &self.weights_buffer)
            }
            Err(e) => Err(e),
        }
    }

    fn infer(
        session: &mut Session,
        waveform_buffer: &Array3<f32>,
        weights_buffer: &Array2<f32>,
    ) -> Result<Array1<f32>> {
        let waveform_tensor = TensorRef::from_array_view(waveform_buffer.view())?;
        let weights_tensor = TensorRef::from_array_view(weights_buffer.view())?;
        let outputs = session
            .run(ort::inputs!["waveform" => waveform_tensor, "weights" => weights_tensor])?;
        // Upstream v0.5.0 fix: never index outputs[0] (panics when empty).
        let output = outputs
            .values()
            .next()
            .ok_or_else(|| Error::Diar("embedding model returned no outputs".to_string()))?;
        let (_shape, data) = output.try_extract_tensor::<f32>()?;
        Ok(Array1::from_vec(data.to_vec()))
    }
}

fn prepare_weights(weights: &[f32], weights_buffer: &mut Array2<f32>) {
    let mut row = weights_buffer.row_mut(0);
    if weights.len() == MASK_FRAMES {
        row.assign(&ndarray::ArrayView1::from(weights));
        return;
    }

    let copy_len = weights.len().min(MASK_FRAMES);
    row.fill(0.0);
    row.slice_mut(s![..copy_len])
        .assign(&ndarray::ArrayView1::from(&weights[..copy_len]));
}

fn read_min_num_samples(path: &Path) -> Option<usize> {
    std::fs::read_to_string(path).ok()?.trim().parse().ok()
}

pub(crate) fn select_mask<'a>(
    mask: &'a [f32],
    clean_mask: Option<&'a [f32]>,
    num_samples: usize,
    min_num_samples: usize,
) -> &'a [f32] {
    let Some(clean_mask) = clean_mask else {
        return mask;
    };

    if clean_mask.len() != mask.len() || num_samples == 0 {
        return mask;
    }

    let min_mask_frames = (mask.len() * min_num_samples).div_ceil(num_samples) as f32;
    let clean_weight: f32 = clean_mask.iter().copied().sum();
    if clean_weight > min_mask_frames {
        clean_mask
    } else {
        mask
    }
}

/// Decide whether clean mask has enough weight, working directly on column views
pub(crate) fn should_use_clean_mask(
    clean_col: &ndarray::ArrayView1<f32>,
    mask_len: usize,
    num_samples: usize,
    min_num_samples: usize,
) -> bool {
    if num_samples == 0 {
        return false;
    }
    let min_mask_frames = (mask_len * min_num_samples).div_ceil(num_samples) as f32;
    let clean_weight: f32 = clean_col.iter().copied().sum();
    clean_weight > min_mask_frames
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::array;

    #[test]
    fn select_mask_prefers_clean_mask_when_it_is_long_enough() {
        let mask = [1.0, 1.0, 1.0, 0.0];
        let clean = [1.0, 1.0, 1.0, 0.0];

        let selected = select_mask(&mask, Some(&clean), 16_000, 6_000);

        assert_eq!(selected, clean);
    }

    #[test]
    fn select_mask_falls_back_to_full_mask_when_clean_mask_is_too_short() {
        let mask = [1.0, 1.0, 1.0, 0.0];
        let clean = [1.0, 0.0, 0.0, 0.0];

        let selected = select_mask(&mask, Some(&clean), 16_000, 6_000);

        assert_eq!(selected, mask);
    }

    #[test]
    fn prepare_weights_clears_tail_when_mask_is_shorter_than_buffer() {
        let mut short_buffer = Array2::from_elem((1, MASK_FRAMES), 9.0f32);
        prepare_weights(&[1.0, 2.0], &mut short_buffer);
        assert_eq!(short_buffer[[0, 0]], 1.0);
        assert_eq!(short_buffer[[0, 1]], 2.0);
        assert!(short_buffer.row(0).iter().skip(2).all(|&v| v == 0.0));

        let full = vec![3.0f32; MASK_FRAMES];
        prepare_weights(&full, &mut short_buffer);
        assert!(short_buffer.row(0).iter().all(|&v| v == 3.0));
    }

    #[test]
    fn should_use_clean_mask_matches_select_mask_threshold() {
        let clean = array![1.0f32, 1.0, 1.0, 0.0];
        assert!(should_use_clean_mask(&clean.view(), 4, 16_000, 6_000));
        let sparse = array![1.0f32, 0.0, 0.0, 0.0];
        assert!(!should_use_clean_mask(&sparse.view(), 4, 16_000, 6_000));
    }
}
