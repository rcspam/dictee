//! Sequential diarization pipeline: sliding-window segmentation -> powerset
//! decode -> masked embeddings -> AHC/PLDA/VBx clustering -> reconstruction.
//!
//! Derived from speakrs v0.4.2 `pipeline/` (Apache-2.0, see src/diar/mod.rs),
//! flattened to the sequential CPU/ONNX decision path (which is exactly what
//! upstream executes with the base two-model bundle: unbatched sessions and
//! the Masked embedding path).

use std::ops::Deref;

use ndarray::{Array2, Array3, ArrayView2, s};

use crate::diar::ahc::cluster as cluster_ahc;
use crate::diar::ahc::AhcConfig;
use crate::diar::binarize::{BinarizeConfig, binarize};
use crate::diar::emb_model::{EmbeddingModel, should_use_clean_mask};
use crate::diar::plda::PldaTransform;
use crate::diar::powerset::PowersetMapping;
use crate::diar::reconstruct::Reconstructor;
use crate::diar::seg_model::SegmentationModel;
use crate::diar::segment::{Segment, merge_segments};
use crate::diar::utils::cosine_similarity;
use crate::diar::vbx::{VbxConfig, cluster_vbx};
use crate::error::Result;

// ── Constants (pyannote community-1 pipeline geometry) ──────────────────────

/// Sliding window length for segmentation model input, in seconds
pub const SEGMENTATION_WINDOW_SECONDS: f64 = 10.0;
/// Default sliding window step for segmentation, in seconds
pub const SEGMENTATION_STEP_SECONDS: f64 = 1.0;
/// Duration of each output frame from the segmentation model, in seconds
pub const FRAME_DURATION_SECONDS: f64 = 0.0619375;
/// Hop between consecutive output frames from the segmentation model, in seconds
pub const FRAME_STEP_SECONDS: f64 = 0.016875;

/// Minimum speaker activity (sum of weights) to run embedding inference.
/// Speakers below this threshold are skipped because their NaN embedding is
/// filtered out later
pub(crate) const MIN_SPEAKER_ACTIVITY: f32 = 10.0;

// ── Configuration ────────────────────────────────────────────────────────────

/// How to map cluster assignments back to per-frame speaker activations
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ReconstructMethod {
    /// Standard top-K selection (pyannote-compatible)
    Standard,
    /// Temporal smoothing. If scores are within epsilon, keep the previous speaker.
    Smoothed {
        /// Score difference below which the previous frame's speaker is preferred
        epsilon: f32,
    },
}

/// Tunable parameters for the diarization pipeline
#[derive(Debug, Clone)]
pub struct PipelineConfig {
    /// Hysteresis binarization and min-duration filtering
    pub binarize: BinarizeConfig,
    /// Agglomerative hierarchical clustering settings
    pub ahc: AhcConfig,
    /// Variational Bayes HMM clustering settings
    pub vbx: VbxConfig,
    /// Maximum gap in seconds between segments to merge into one
    pub merge_gap: f64,
    /// Minimum speaker activity weight to keep a speaker in output
    pub speaker_keep_threshold: f64,
    /// Strategy for mapping clusters back to frame activations
    pub reconstruct_method: ReconstructMethod,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self {
            binarize: BinarizeConfig::default(),
            ahc: AhcConfig::default(),
            vbx: VbxConfig::default(),
            merge_gap: 0.0,
            speaker_keep_threshold: 1e-7,
            reconstruct_method: ReconstructMethod::Smoothed { epsilon: 0.1 },
        }
    }
}

// ── Data types ───────────────────────────────────────────────────────────────

/// Decoded powerset segmentations per chunk, shape (chunks, frames, speakers)
#[derive(Debug, Clone)]
pub struct DecodedSegmentations(pub Array3<f32>);

impl Deref for DecodedSegmentations {
    type Target = Array3<f32>;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

/// Speaker embeddings per chunk, shape (chunks, speakers, embedding_dim)
#[derive(Debug, Clone)]
pub struct ChunkEmbeddings(pub Array3<f32>);

impl Deref for ChunkEmbeddings {
    type Target = Array3<f32>;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

/// Number of active speakers per chunk
#[derive(Debug, Clone)]
pub struct SpeakerCountTrack(pub Vec<usize>);

impl Deref for SpeakerCountTrack {
    type Target = Vec<usize>;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

/// Cluster assignments per chunk-speaker pair, shape (chunks, speakers)
///
/// Values are cluster IDs (negative for unassigned/inactive)
#[derive(Debug, Clone)]
pub struct ChunkSpeakerClusters(pub Array2<i32>);

impl Deref for ChunkSpeakerClusters {
    type Target = Array2<i32>;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

/// Frame-level binary speaker activations, shape (frames, speakers)
#[derive(Debug, Clone)]
pub struct DiscreteDiarization(pub Array2<f32>);

impl Deref for DiscreteDiarization {
    type Target = Array2<f32>;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl DiscreteDiarization {
    /// Zero out all but the highest-scoring speaker in each frame
    pub fn make_exclusive(&mut self) {
        crate::diar::reconstruct::make_exclusive(&mut self.0);
    }

    /// Convert frame activations to time-stamped speaker segments
    pub fn to_segments(
        &self,
        frame_step_seconds: f64,
        frame_duration_seconds: f64,
    ) -> Vec<Segment> {
        crate::diar::segment::to_segments(&self.0, frame_step_seconds, frame_duration_seconds)
    }
}

#[derive(Debug, Clone)]
pub(crate) struct FrameActivations(pub(crate) Array2<f32>);

impl Deref for FrameActivations {
    type Target = Array2<f32>;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

pub(crate) struct RawSegmentationWindows(pub Vec<Array2<f32>>);

impl RawSegmentationWindows {
    pub(crate) fn decode(self, powerset: &PowersetMapping) -> DecodedSegmentations {
        let mut windows = self.0.into_iter();
        let Some(first_window) = windows.next() else {
            return DecodedSegmentations(Array3::zeros((0, 0, 0)));
        };

        let num_windows = windows.len() + 1;
        let first = powerset.hard_decode(&first_window);
        let mut stacked = Array3::<f32>::zeros((num_windows, first.nrows(), first.ncols()));
        stacked.slice_mut(s![0, .., ..]).assign(&first);

        for (window_idx, window) in windows.enumerate() {
            let decoded = powerset.hard_decode(&window);
            stacked
                .slice_mut(s![window_idx + 1, .., ..])
                .assign(&decoded);
        }

        DecodedSegmentations(stacked)
    }
}

/// Intermediate results from segmentation and embedding inference
pub struct InferenceArtifacts {
    pub(crate) layout: ChunkLayout,
    pub(crate) segmentations: DecodedSegmentations,
    pub(crate) embeddings: ChunkEmbeddings,
}

/// Complete output from a diarization run
pub struct DiarizationResult {
    /// Decoded segmentations from the powerset model
    pub segmentations: DecodedSegmentations,
    /// Speaker embeddings extracted from each chunk
    pub embeddings: ChunkEmbeddings,
    /// Number of active speakers per chunk
    pub speaker_count: SpeakerCountTrack,
    /// Cluster assignment for each chunk-speaker pair
    pub hard_clusters: ChunkSpeakerClusters,
    /// Frame-level binary speaker activations after reconstruction
    pub discrete_diarization: DiscreteDiarization,
    /// Merged speaker segments (time-stamped speaker turns)
    pub segments: Vec<Segment>,
}

impl DiarizationResult {
    /// Render RTTM output with the given file identifier
    pub fn rttm(&self, file_id: &str) -> String {
        crate::diar::segment::to_rttm(&self.segments, file_id)
    }
}

// ── Chunk layout (pyannote window/frame geometry) ────────────────────────────

pub(crate) struct ChunkLayout {
    pub step_seconds: f64,
    pub step_samples: usize,
    pub window_samples: usize,
    pub start_frames: Vec<usize>,
    pub output_frames: usize,
}

impl ChunkLayout {
    pub(crate) fn new(
        step_seconds: f64,
        step_samples: usize,
        window_samples: usize,
        num_chunks: usize,
    ) -> Self {
        Self {
            step_seconds,
            step_samples,
            window_samples,
            start_frames: chunk_start_frames(num_chunks, step_seconds),
            output_frames: total_output_frames(num_chunks, step_seconds),
        }
    }

    pub(crate) fn chunk_audio<'a>(&self, audio: &'a [f32], chunk_idx: usize) -> &'a [f32] {
        let start = chunk_idx * self.step_samples;
        let end = (start + self.window_samples).min(audio.len());
        if start < audio.len() {
            &audio[start..end]
        } else {
            &[]
        }
    }
}

pub(crate) fn chunk_start_frames(num_chunks: usize, step_seconds: f64) -> Vec<usize> {
    (0..num_chunks)
        .map(|chunk_idx| {
            closest_frame(chunk_idx as f64 * step_seconds + 0.5 * FRAME_DURATION_SECONDS)
        })
        .collect()
}

pub(crate) fn total_output_frames(num_chunks: usize, step_seconds: f64) -> usize {
    if num_chunks == 0 {
        return 0;
    }

    closest_frame(
        SEGMENTATION_WINDOW_SECONDS
            + (num_chunks - 1) as f64 * step_seconds
            + 0.5 * FRAME_DURATION_SECONDS,
    ) + 1
}

fn closest_frame(timestamp: f64) -> usize {
    ((timestamp - 0.5 * FRAME_DURATION_SECONDS) / FRAME_STEP_SECONDS).round() as usize
}

// ── Inference (sequential path) ──────────────────────────────────────────────

pub(crate) fn run_sequential_inference(
    seg_model: &mut SegmentationModel,
    emb_model: &mut EmbeddingModel,
    powerset: &PowersetMapping,
    audio: &[f32],
) -> Result<InferenceArtifacts> {
    let raw_windows = RawSegmentationWindows(seg_model.run(audio)?);
    let segmentations = raw_windows.decode(powerset);
    let layout = ChunkLayout::new(
        seg_model.step_seconds(),
        seg_model.step_samples(),
        seg_model.window_samples(),
        segmentations.nchunks(),
    );
    let embeddings = segmentations.extract_masked_embeddings(audio, emb_model, &layout)?;

    Ok(InferenceArtifacts {
        layout,
        segmentations,
        embeddings,
    })
}

impl DecodedSegmentations {
    pub(crate) fn nchunks(&self) -> usize {
        self.0.shape()[0]
    }

    pub(crate) fn speaker_count(&self, layout: &ChunkLayout) -> SpeakerCountTrack {
        let reconstructor = Reconstructor::new(self, &layout.start_frames, 0);
        reconstructor.speaker_count(layout.output_frames)
    }

    /// Per-(chunk, speaker) masked embedding extraction. With the base two
    /// ONNX files the upstream batch machinery degenerates to batch size 1,
    /// so this per-item loop is behaviorally identical.
    fn extract_masked_embeddings(
        &self,
        audio: &[f32],
        emb_model: &mut EmbeddingModel,
        layout: &ChunkLayout,
    ) -> Result<ChunkEmbeddings> {
        let num_chunks = self.0.shape()[0];
        let num_speakers = if self.0.ndim() < 3 { 0 } else { self.0.shape()[2] };
        let mut embeddings =
            Array3::<f32>::from_elem((num_chunks, num_speakers, 256), f32::NAN);

        for chunk_idx in 0..num_chunks {
            let chunk_audio = layout.chunk_audio(audio, chunk_idx);
            let chunk_segmentations = self.0.slice(s![chunk_idx, .., ..]);
            let clean = clean_masks(&chunk_segmentations);

            for speaker_idx in 0..num_speakers {
                let mask = chunk_segmentations.column(speaker_idx);
                let activity: f32 = mask.iter().sum();
                if activity < MIN_SPEAKER_ACTIVITY {
                    continue;
                }

                let mask: Vec<f32> = mask.to_vec();
                let clean_mask: Vec<f32> = clean.column(speaker_idx).to_vec();
                let embedding =
                    emb_model.embed_masked(chunk_audio, &mask, Some(&clean_mask))?;
                embeddings
                    .slice_mut(s![chunk_idx, speaker_idx, ..])
                    .assign(&embedding);
            }
        }

        Ok(ChunkEmbeddings(embeddings))
    }
}

// ── Clustering (AHC -> PLDA -> VBx -> centroid re-assignment) ────────────────

pub(crate) struct TrainingEmbeddings(pub Array2<f32>);

impl ChunkEmbeddings {
    pub(crate) fn training_set(&self, segmentations: &DecodedSegmentations) -> TrainingEmbeddings {
        let num_frames = segmentations.0.shape()[1] as f32;
        let mut filtered = Vec::new();
        let mut chunk_indices = Vec::new();

        for chunk_idx in 0..segmentations.0.shape()[0] {
            let single_active: Vec<bool> = segmentations
                .0
                .slice(s![chunk_idx, .., ..])
                .rows()
                .into_iter()
                .map(|row| (row.iter().copied().sum::<f32>() - 1.0).abs() < 1e-6)
                .collect();
            for speaker_idx in 0..segmentations.0.shape()[2] {
                let clean_frames = segmentations
                    .0
                    .slice(s![chunk_idx, .., speaker_idx])
                    .iter()
                    .zip(single_active.iter())
                    .filter_map(|(value, is_single_active)| is_single_active.then_some(*value))
                    .sum::<f32>();
                let embedding = self.0.slice(s![chunk_idx, speaker_idx, ..]);
                let valid_embedding = embedding.iter().all(|value| value.is_finite());
                if valid_embedding && clean_frames >= 0.2 * num_frames {
                    filtered.extend(embedding.iter());
                    chunk_indices.push(chunk_idx);
                }
            }
        }

        let row_count = chunk_indices.len();
        let embedding_dim = self.0.shape()[2];
        let mut filtered_embeddings = Array2::<f32>::zeros((row_count, embedding_dim));
        for (row_idx, values) in filtered.chunks_exact(embedding_dim).enumerate() {
            filtered_embeddings
                .slice_mut(s![row_idx, ..])
                .assign(&ndarray::ArrayView1::from(values));
        }
        TrainingEmbeddings(filtered_embeddings)
    }
}

impl TrainingEmbeddings {
    pub(crate) fn cluster(
        &self,
        segmentations: &DecodedSegmentations,
        embeddings: &ChunkEmbeddings,
        plda: &PldaTransform,
        config: &PipelineConfig,
    ) -> ChunkSpeakerClusters {
        if self.0.nrows() < 2 {
            let mut clusters =
                Array2::<i32>::zeros((segmentations.0.shape()[0], segmentations.0.shape()[2]));
            mark_inactive_speakers(&segmentations.0, &mut clusters);
            return ChunkSpeakerClusters(clusters);
        }

        let ahc_labels = cluster_ahc(&self.0.view(), config.ahc);

        let plda_features = plda.transform(&self.0.view(), 128);
        let phi = plda.phi();
        let (gamma, pi): (Array2<f32>, ndarray::Array1<f32>) = cluster_vbx(
            &ahc_labels,
            &plda_features.view(),
            &phi.slice(s![..128]),
            &config.vbx,
        );

        let mut kept_speakers: Vec<usize> = pi
            .iter()
            .enumerate()
            .filter_map(|(speaker_idx, weight)| {
                (*weight > config.speaker_keep_threshold as f32).then_some(speaker_idx)
            })
            .collect();
        if kept_speakers.is_empty() && !pi.is_empty() {
            let best_speaker = pi
                .iter()
                .enumerate()
                .max_by(|left, right| left.1.total_cmp(right.1))
                .map(|(speaker_idx, _)| speaker_idx)
                .unwrap_or(0);
            kept_speakers.push(best_speaker);
        }

        let centroids = weighted_centroids(&self.0, &gamma, &kept_speakers);

        let mut clusters = assign_chunk_embeddings(segmentations, embeddings, &centroids);
        mark_inactive_speakers(&segmentations.0, &mut clusters);

        ChunkSpeakerClusters(clusters)
    }
}

pub(crate) fn weighted_centroids(
    train_embeddings: &Array2<f32>,
    gamma: &Array2<f32>,
    kept_speakers: &[usize],
) -> Array2<f32> {
    let mut centroids = Array2::<f32>::zeros((kept_speakers.len(), train_embeddings.ncols()));
    for (out_idx, &speaker_idx) in kept_speakers.iter().enumerate() {
        let weights = gamma.column(speaker_idx);
        let weight_sum = weights.sum().max(1e-8);
        for (row_idx, weight) in weights.iter().enumerate() {
            centroids
                .row_mut(out_idx)
                .scaled_add(*weight / weight_sum, &train_embeddings.row(row_idx));
        }
    }
    centroids
}

pub(crate) fn assign_chunk_embeddings(
    segmentations: &DecodedSegmentations,
    embeddings: &ChunkEmbeddings,
    centroids: &Array2<f32>,
) -> Array2<i32> {
    let num_chunks = embeddings.0.shape()[0];
    let num_speakers = embeddings.0.shape()[1];
    let num_clusters = centroids.nrows();
    let mut labels = Array2::<i32>::from_elem((num_chunks, num_speakers), -2);

    for chunk_idx in 0..num_chunks {
        // compute similarity scores for all active speakers against all centroids
        let mut active_local = Vec::new();
        let mut scores = Array2::<f32>::from_elem((num_speakers, num_clusters), f32::NEG_INFINITY);
        for speaker_idx in 0..num_speakers {
            let is_active = segmentations.0.slice(s![chunk_idx, .., speaker_idx]).sum() > 0.0;
            if !is_active {
                continue;
            }

            active_local.push(speaker_idx);
            let embedding = embeddings.0.slice(s![chunk_idx, speaker_idx, ..]);
            if embedding.iter().any(|value| !value.is_finite()) {
                continue;
            }

            for cluster_idx in 0..num_clusters {
                scores[[speaker_idx, cluster_idx]] =
                    1.0 + cosine_similarity(&embedding, &centroids.row(cluster_idx));
            }
        }

        // mask inactive/invalid speakers to min - 1 instead of NEG_INFINITY,
        // matching pyannote's constrained_argmax masking behavior
        let finite_min = scores
            .iter()
            .copied()
            .filter(|v| v.is_finite())
            .fold(f32::INFINITY, f32::min);
        if finite_min.is_finite() {
            let mask_value = finite_min - 1.0;
            scores.mapv_inplace(|v| if v.is_finite() { v } else { mask_value });
        }

        let assignments = best_assignment(&scores, &active_local, num_clusters);
        for (speaker_idx, cluster_idx) in assignments {
            labels[[chunk_idx, speaker_idx]] = cluster_idx as i32;
        }
    }

    labels
}

pub(crate) fn best_assignment(
    scores: &Array2<f32>,
    active_local: &[usize],
    num_clusters: usize,
) -> Vec<(usize, usize)> {
    let target = active_local.len().min(num_clusters);
    let mut search = AssignmentSearch::new(scores, active_local, target, num_clusters);
    search.run(0, 0.0);
    search.best
}

struct AssignmentSearch<'a> {
    scores: &'a Array2<f32>,
    active_local: &'a [usize],
    target: usize,
    used_clusters: Vec<bool>,
    current: Vec<(usize, usize)>,
    best_score: f32,
    best: Vec<(usize, usize)>,
}

impl<'a> AssignmentSearch<'a> {
    fn new(
        scores: &'a Array2<f32>,
        active_local: &'a [usize],
        target: usize,
        num_clusters: usize,
    ) -> Self {
        Self {
            scores,
            active_local,
            target,
            used_clusters: vec![false; num_clusters],
            current: Vec::new(),
            best_score: f32::NEG_INFINITY,
            best: Vec::new(),
        }
    }

    fn run(&mut self, position: usize, current_score: f32) {
        if self.current.len() == self.target {
            if current_score > self.best_score {
                self.best_score = current_score;
                self.best = self.current.clone();
            }
            return;
        }

        if position == self.active_local.len() {
            return;
        }

        let remaining_local = self.active_local.len() - position;
        let remaining_needed = self.target - self.current.len();
        if remaining_local > remaining_needed {
            self.run(position + 1, current_score);
        }

        let speaker_idx = self.active_local[position];
        for cluster_idx in 0..self.used_clusters.len() {
            if self.used_clusters[cluster_idx] {
                continue;
            }

            self.used_clusters[cluster_idx] = true;
            self.current.push((speaker_idx, cluster_idx));
            self.run(
                position + 1,
                current_score + self.scores[[speaker_idx, cluster_idx]],
            );
            self.current.pop();
            self.used_clusters[cluster_idx] = false;
        }
    }
}

pub(crate) fn mark_inactive_speakers(segmentations: &Array3<f32>, hard_clusters: &mut Array2<i32>) {
    for chunk_idx in 0..segmentations.shape()[0] {
        for speaker_idx in 0..segmentations.shape()[2] {
            let active = segmentations.slice(s![chunk_idx, .., speaker_idx]).sum() > 0.0;
            if !active {
                hard_clusters[[chunk_idx, speaker_idx]] = -2;
            }
        }
    }
}

pub(crate) fn clean_masks(segmentations: &ArrayView2<f32>) -> Array2<f32> {
    let single_active: Vec<bool> = segmentations
        .rows()
        .into_iter()
        .map(|row| row.iter().copied().sum::<f32>() < 2.0)
        .collect();
    let mut clean = Array2::<f32>::zeros(segmentations.raw_dim());
    for (frame_idx, is_single_active) in single_active.iter().enumerate() {
        if !*is_single_active {
            continue;
        }

        clean
            .slice_mut(s![frame_idx, ..])
            .assign(&segmentations.slice(s![frame_idx, ..]));
    }
    clean
}

/// Select speaker weights for embedding, returning None if speaker activity is below threshold
pub(crate) fn select_speaker_weights(
    seg_view: &ArrayView2<f32>,
    clean_masks: &Array2<f32>,
    speaker_idx: usize,
    audio_len: usize,
    min_num_samples: usize,
) -> Option<Vec<f32>> {
    let mask_col = seg_view.column(speaker_idx);
    let activity: f32 = mask_col.iter().sum();
    if activity < MIN_SPEAKER_ACTIVITY {
        return None;
    }

    let clean_col = clean_masks.column(speaker_idx);
    let use_clean = should_use_clean_mask(&clean_col, mask_col.len(), audio_len, min_num_samples);
    if use_clean {
        Some(clean_col.iter().copied().collect())
    } else {
        Some(mask_col.iter().copied().collect())
    }
}

// ── Post-inference (clustering + reconstruction) ─────────────────────────────

pub(crate) fn post_inference(
    inference_artifacts: InferenceArtifacts,
    config: &PipelineConfig,
    plda: &PldaTransform,
) -> Result<DiarizationResult> {
    let InferenceArtifacts {
        layout,
        segmentations,
        embeddings,
    } = inference_artifacts;
    let speaker_count = segmentations.speaker_count(&layout);

    if speaker_count
        .iter()
        .all(|speaker_count| *speaker_count == 0)
    {
        return Ok(DiarizationResult {
            segmentations,
            embeddings,
            speaker_count,
            hard_clusters: ChunkSpeakerClusters(Array2::zeros((0, 0))),
            discrete_diarization: DiscreteDiarization(Array2::zeros((0, 0))),
            segments: Vec::new(),
        });
    }

    let training_embeddings = embeddings.training_set(&segmentations);
    let hard_clusters = training_embeddings.cluster(&segmentations, &embeddings, plda, config);

    let reconstructor =
        Reconstructor::with_clusters(&segmentations, &hard_clusters, &layout.start_frames, 0);
    let discrete_diarization = match config.reconstruct_method {
        ReconstructMethod::Smoothed { epsilon } => {
            reconstructor.reconstruct_smoothed(&speaker_count, epsilon)
        }
        ReconstructMethod::Standard => reconstructor.reconstruct(&speaker_count),
    };

    // apply min-duration filtering to remove single-frame speaker flickers
    let has_duration_filter =
        config.binarize.min_duration_on > 0 || config.binarize.min_duration_off > 0;
    let discrete_diarization = if has_duration_filter {
        DiscreteDiarization(binarize(&discrete_diarization, &config.binarize))
    } else {
        discrete_diarization
    };

    let segments = discrete_diarization.to_segments(FRAME_STEP_SECONDS, FRAME_DURATION_SECONDS);
    let segments = merge_segments(&segments, config.merge_gap);

    Ok(DiarizationResult {
        segmentations,
        embeddings,
        speaker_count,
        hard_clusters,
        discrete_diarization,
        segments,
    })
}

#[cfg(test)]
mod tests {
    use std::fs::File;
    use std::path::PathBuf;

    use ndarray::{Array1, Array2, Array3, array};
    use ndarray_npy::ReadNpyExt;

    use super::*;

    fn fixture_path(name: &str) -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests/diar-fixtures")
            .join(name)
    }

    fn load_fixture_array1<T>(name: &str) -> Array1<T>
    where
        Array1<T>: ReadNpyExt,
    {
        Array1::read_npy(File::open(fixture_path(name)).unwrap()).unwrap()
    }

    fn load_fixture_array2<T>(name: &str) -> Array2<T>
    where
        Array2<T>: ReadNpyExt,
    {
        Array2::read_npy(File::open(fixture_path(name)).unwrap()).unwrap()
    }

    fn load_fixture_array3<T>(name: &str) -> Array3<T>
    where
        Array3<T>: ReadNpyExt,
    {
        Array3::read_npy(File::open(fixture_path(name)).unwrap()).unwrap()
    }

    #[test]
    fn chunk_start_frames_match_pyannote_rounding() {
        assert_eq!(
            chunk_start_frames(4, SEGMENTATION_STEP_SECONDS),
            vec![0, 59, 119, 178]
        );
    }

    #[test]
    fn total_output_frames_match_pyannote_aggregate_extent() {
        assert_eq!(total_output_frames(4, SEGMENTATION_STEP_SECONDS), 771);
    }

    #[test]
    fn best_assignment_handles_more_speakers_than_clusters() {
        let scores = array![[0.9, 0.1], [0.8, 0.2], [0.1, 0.95]];
        let assignment = best_assignment(&scores, &[0, 1, 2], 2);
        assert_eq!(assignment.len(), 2);
        assert!(assignment.contains(&(0, 0)) || assignment.contains(&(1, 0)));
        assert!(assignment.contains(&(2, 1)));
    }

    #[test]
    fn filter_embeddings_matches_python_fixture() {
        let segmentations: Array3<f32> = load_fixture_array3("pipeline_segmentation_data.npy");
        let embeddings: Array3<f32> = load_fixture_array3("pipeline_embeddings_data.npy");
        let expected_train_embeddings: Array2<f32> =
            load_fixture_array2("pipeline_train_embeddings.npy");
        let expected_chunk_idx: Array1<i64> = load_fixture_array1("pipeline_train_chunk_idx.npy");

        let train = ChunkEmbeddings(embeddings)
            .training_set(&DecodedSegmentations(segmentations));

        assert_eq!(train.0.nrows(), expected_chunk_idx.len());
        for (lhs, rhs) in train.0.iter().zip(expected_train_embeddings.iter()) {
            approx::assert_abs_diff_eq!(*lhs, *rhs, epsilon = 1e-5);
        }
    }

    #[test]
    fn assign_embeddings_matches_python_fixture() {
        let segmentations: Array3<f32> = load_fixture_array3("pipeline_segmentation_data.npy");
        let embeddings: Array3<f32> = load_fixture_array3("pipeline_embeddings_data.npy");
        let train_embeddings: Array2<f32> = load_fixture_array2("pipeline_train_embeddings.npy");
        let gamma: Array2<f64> = load_fixture_array2("pipeline_vbx_gamma.npy");
        let pi: Array1<f64> = load_fixture_array1("pipeline_vbx_pi.npy");
        let expected: Array2<i8> = load_fixture_array2("pipeline_hard_clusters.npy");

        let kept_speakers: Vec<usize> = pi
            .iter()
            .enumerate()
            .filter_map(|(idx, weight)| (*weight > 1e-7).then_some(idx))
            .collect();
        let centroids = weighted_centroids(
            &train_embeddings,
            &gamma.mapv(|value| value as f32),
            &kept_speakers,
        );
        let segmentations = DecodedSegmentations(segmentations);
        let embeddings = ChunkEmbeddings(embeddings);
        let mut hard_clusters = assign_chunk_embeddings(&segmentations, &embeddings, &centroids);
        mark_inactive_speakers(&segmentations.0, &mut hard_clusters);

        assert_eq!(hard_clusters.dim(), expected.dim());
        for (lhs, rhs) in hard_clusters.iter().zip(expected.iter()) {
            assert_eq!(*lhs as i8, *rhs);
        }
    }
}
