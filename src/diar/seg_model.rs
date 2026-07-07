//! pyannote segmentation-3.0 ONNX model (sliding-window powerset logits).
//!
//! Derived from speakrs v0.4.2 `inference/segmentation` (Apache-2.0, see
//! src/diar/mod.rs), reduced to the single-session sequential path and wired
//! through the crate's `ExecutionConfig` session conventions.

use std::path::Path;

use ndarray::{Array2, Array3};
use ort::session::Session;
use ort::value::TensorRef;

use crate::error::{Error, Result};
use crate::execution::ModelConfig as ExecutionConfig;

const SAMPLE_RATE: usize = 16_000;
const WINDOW_SECONDS: f32 = 10.0;

pub struct SegmentationModel {
    session: Session,
    input_buffer: Array3<f32>,
    window_samples: usize,
    step_samples: usize,
}

impl SegmentationModel {
    /// Load the segmentation model with the given sliding-window step.
    pub fn new(
        model_path: impl AsRef<Path>,
        step_seconds: f32,
        exec_config: &ExecutionConfig,
    ) -> Result<Self> {
        let window_samples = (WINDOW_SECONDS * SAMPLE_RATE as f32) as usize;
        let step_samples = (step_seconds * SAMPLE_RATE as f32) as usize;

        // Same session tuning as upstream: capped intra-op threads, one
        // inter-op thread, memory pattern, independent thread pool.
        let intra = std::thread::available_parallelism()
            .map(|n| n.get().min(6))
            .unwrap_or(1);
        let cfg = exec_config
            .clone()
            .with_intra_threads(intra)
            .with_inter_threads(1)
            .with_custom_configure(|builder| {
                builder
                    .with_memory_pattern(true)?
                    .with_independent_thread_pool()
                    // strip the rc.12 recoverable builder state from the error
                    .map_err(Into::into)
            });
        let mut builder = cfg.apply_to_session_builder(Session::builder()?)?;
        let session = builder.commit_from_file(model_path.as_ref())?;

        Ok(Self {
            session,
            input_buffer: Array3::zeros((1, 1, window_samples)),
            window_samples,
            step_samples,
        })
    }

    pub fn window_samples(&self) -> usize {
        self.window_samples
    }

    pub fn step_samples(&self) -> usize {
        self.step_samples
    }

    pub fn step_seconds(&self) -> f64 {
        self.step_samples as f64 / SAMPLE_RATE as f64
    }

    /// Run segmentation on audio, returning raw logits per sliding window
    /// (each element is [frames, 7] powerset logits). The tail window is
    /// zero-padded, matching pyannote.
    pub fn run(&mut self, audio: &[f32]) -> Result<Vec<Array2<f32>>> {
        let mut offsets = Vec::new();
        let mut offset = 0;
        while offset + self.window_samples <= audio.len() {
            offsets.push(offset);
            offset += self.step_samples;
        }
        let padded_tail = if offset < audio.len() && audio.len() > self.window_samples {
            let mut padded = vec![0.0f32; self.window_samples];
            let remaining = audio.len() - offset;
            padded[..remaining].copy_from_slice(&audio[offset..]);
            Some(padded)
        } else {
            None
        };

        let mut results = Vec::with_capacity(offsets.len() + padded_tail.is_some() as usize);
        for &start in &offsets {
            results.push(self.run_window(&audio[start..start + self.window_samples])?);
        }
        if let Some(tail) = padded_tail {
            results.push(self.run_window(&tail)?);
        }
        Ok(results)
    }

    fn run_window(&mut self, window: &[f32]) -> Result<Array2<f32>> {
        self.input_buffer.fill(0.0);
        self.input_buffer
            .slice_mut(ndarray::s![0, 0, ..window.len()])
            .assign(&ndarray::ArrayView1::from(window));
        let input_tensor = TensorRef::from_array_view(self.input_buffer.view())?;

        let outputs = self.session.run(ort::inputs![input_tensor])?;
        // Upstream v0.5.0 fix: never index outputs[0] (panics when empty).
        let output = outputs
            .values()
            .next()
            .ok_or_else(|| Error::Diar("segmentation model returned no outputs".to_string()))?;
        let (shape, data) = output.try_extract_tensor::<f32>()?;

        let frames = shape[1] as usize;
        let classes = shape[2] as usize;

        Array2::from_shape_vec((frames, classes), data.to_vec())
            .map_err(|error| Error::Diar(format!("segmentation window output shape: {error}")))
    }
}
