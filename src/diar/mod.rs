//! In-house multi-speaker diarization engine (no speaker-count cap).
//!
//! Pipeline: pyannote segmentation-3.0 (ONNX) -> powerset decoding ->
//! WeSpeaker ResNet34 embeddings (ONNX) -> AHC + PLDA + VBx clustering ->
//! frame reconstruction -> speaker turns.
//!
//! Portions derived from speakrs v0.4.2 (https://github.com/avencera/speakrs),
//! Copyright 2026 Praveen Perera, licensed under the Apache License 2.0 —
//! see LICENSE-APACHE and NOTICE at the repository root. Modifications:
//! sequential-path extraction, pure-Rust linear algebra (nalgebra) instead of
//! ndarray-linalg/BLAS, exact-speaker-count AHC cut, dictee session and
//! provider integration.

pub mod ahc;
pub mod binarize;
pub mod emb_model;
pub mod linalg;
pub mod pipeline;
pub mod plda;
pub mod powerset;
pub mod reconstruct;
pub mod seg_model;
pub mod segment;
pub mod utils;
pub mod vbx;

use std::path::Path;

use crate::error::{Error, Result};
use crate::execution::ModelConfig as ExecutionConfig;

pub use pipeline::{DiarizationResult, PipelineConfig, ReconstructMethod};
pub use segment::Segment;

/// Model filenames expected inside the models directory.
pub const SEGMENTATION_ONNX: &str = "segmentation-3.0.onnx";
pub const EMBEDDING_ONNX: &str = "wespeaker-voxceleb-resnet34.onnx";

/// Complete multi-speaker diarization engine (no speaker-count cap).
///
/// ```no_run
/// use parakeet_rs::diar::{Diarizer, PipelineConfig};
///
/// let mut diarizer = Diarizer::from_dir("/usr/share/dictee/diar", None)?;
/// let audio: Vec<f32> = vec![]; // 16 kHz mono samples
/// let result = diarizer.diarize(&audio, &PipelineConfig::default())?;
/// for seg in &result.segments {
///     println!("{:.2} {:.2} {}", seg.start, seg.end, seg.speaker);
/// }
/// # Ok::<(), parakeet_rs::Error>(())
/// ```
pub struct Diarizer {
    seg_model: seg_model::SegmentationModel,
    emb_model: emb_model::EmbeddingModel,
    plda: plda::PldaTransform,
    powerset: powerset::PowersetMapping,
}

impl Diarizer {
    /// Load the segmentation + embedding ONNX models and PLDA parameters from
    /// `models_dir`, building the ONNX sessions through the crate's
    /// [`ExecutionConfig`] conventions (`None` = default CPU config).
    pub fn from_dir(
        models_dir: impl AsRef<Path>,
        exec_config: Option<ExecutionConfig>,
    ) -> Result<Self> {
        let models_dir = models_dir.as_ref();
        let exec_config = exec_config.unwrap_or_default();

        let seg_path = models_dir.join(SEGMENTATION_ONNX);
        if !seg_path.exists() {
            return Err(Error::Diar(format!(
                "segmentation model not found: {}",
                seg_path.display()
            )));
        }
        let seg_model = seg_model::SegmentationModel::new(
            &seg_path,
            pipeline::SEGMENTATION_STEP_SECONDS as f32,
            &exec_config,
        )?;
        let emb_model =
            emb_model::EmbeddingModel::new(models_dir.join(EMBEDDING_ONNX), &exec_config)?;
        let plda = plda::PldaTransform::from_dir(models_dir)?;
        let powerset = powerset::PowersetMapping::new(3, 2);

        Ok(Self {
            seg_model,
            emb_model,
            plda,
            powerset,
        })
    }

    /// Diarize 16 kHz mono audio into time-stamped speaker turns.
    pub fn diarize(
        &mut self,
        audio: &[f32],
        config: &PipelineConfig,
    ) -> Result<DiarizationResult> {
        let artifacts = pipeline::run_sequential_inference(
            &mut self.seg_model,
            &mut self.emb_model,
            &self.powerset,
            audio,
        )?;
        pipeline::post_inference(artifacts, config, &self.plda)
    }
}
