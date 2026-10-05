//! Live (streaming) multi-speaker diarization on top of the offline engine.
//!
//! Protocol validated by examples/live_diarize_poc.rs (2026-07-09):
//!   1. Audio is consumed as the standard sliding windows (10 s / 1 s step);
//!      segmentation + masked embeddings are chunk-local in pipeline.rs, so
//!      per-window inference is bit-identical to an offline run.
//!   2. Bootstrap: the first time at least 2 training-quality embeddings
//!      exist, run the full AHC -> PLDA -> VBx clustering -> centroids.
//!   3. Cruise: each new window's embeddings are labeled instantly by
//!      constrained cosine assignment against the centroids (sub-ms).
//!   4. New-voice event: a training-quality embedding farther than
//!      `new_voice_dist` from every centroid triggers a full re-clustering
//!      (rate-limited by `cooldown_secs`). Re-clustering costs milliseconds
//!      early on and a few seconds after ~40 min of speech, which is fine
//!      synchronously between meeting chunks.
//!
//! Speaker ids are STABLE FORWARD: after each re-clustering, new centroids
//! inherit the public id of the closest previous centroid (cosine distance
//! <= `id_match_dist`); genuinely new voices get fresh ids. Past windows are
//! relabeled internally (so future output is consistent) but already-emitted
//! output is not retracted — the end-of-meeting batch pass is the clean one.

use std::path::Path;

use ndarray::{s, Array1, Array2, Array3};

use crate::diar::ahc;
use crate::diar::emb_model::EmbeddingModel;
use crate::diar::pipeline::{
    self, best_assignment, run_sequential_inference, weighted_centroids,
    ChunkSpeakerClusters, DecodedSegmentations, PipelineConfig,
    FRAME_DURATION_SECONDS, FRAME_STEP_SECONDS, SEGMENTATION_STEP_SECONDS,
    SEGMENTATION_WINDOW_SECONDS,
};
use crate::diar::plda::PldaTransform;
use crate::diar::powerset::PowersetMapping;
use crate::diar::reconstruct::Reconstructor;
use crate::diar::seg_model::SegmentationModel;
use crate::diar::segment::merge_segments;
use crate::diar::utils::cosine_similarity;
use crate::diar::vbx::cluster_vbx;
use crate::error::{Error, Result};
use crate::execution::ModelConfig as ExecutionConfig;

const SAMPLE_RATE: usize = 16000;

/// Tunables for the live protocol (engine tunables live in `pipeline`).
#[derive(Debug, Clone)]
pub struct LiveConfig {
    pub pipeline: PipelineConfig,
    /// Cosine distance above which a training-quality embedding counts as an
    /// unknown voice and triggers a re-clustering.
    pub new_voice_dist: f32,
    /// Minimum seconds between two re-clusterings.
    pub cooldown_secs: f64,
    /// Maximum centroid cosine distance to inherit a previous speaker id.
    pub id_match_dist: f32,
}

impl Default for LiveConfig {
    fn default() -> Self {
        Self {
            pipeline: PipelineConfig::default(),
            new_voice_dist: 0.6,
            cooldown_secs: 10.0,
            id_match_dist: 0.5,
        }
    }
}

/// One live speaker turn on the global meeting timeline.
#[derive(Debug, Clone, PartialEq)]
pub struct LiveTurn {
    pub start: f64,
    pub end: f64,
    pub speaker: i32,
}

/// Streaming diarizer: feed audio with [`push_audio`](Self::push_audio),
/// read labeled turns with [`turns_in_range`](Self::turns_in_range).
pub struct LiveDiarizer {
    seg_model: SegmentationModel,
    emb_model: EmbeddingModel,
    powerset: PowersetMapping,
    plda: PldaTransform,
    config: LiveConfig,
    // Rolling audio not yet consumed by a full window (always < window size
    // after processing).
    pending: Vec<f32>,
    // Total samples ever pushed (global timeline).
    total_samples: usize,
    // Per processed window, in window order (window w starts at w * step).
    win_segs: Vec<Array2<f32>>,
    win_embs: Vec<Array2<f32>>,
    labels: Vec<Vec<i32>>,
    // Training-quality (window, local speaker) rows.
    train_rows: Vec<(usize, usize)>,
    centroids: Option<Array2<f32>>,
    // Public stable id of each centroid row.
    centroid_ids: Vec<i32>,
    next_id: i32,
    last_recluster_t: f64,
}

impl LiveDiarizer {
    pub fn from_dir(
        models_dir: impl AsRef<Path>,
        exec_config: Option<ExecutionConfig>,
        config: LiveConfig,
    ) -> Result<Self> {
        let models_dir = models_dir.as_ref();
        let exec_config = exec_config.unwrap_or_default();
        let seg_path = models_dir.join(crate::diar::SEGMENTATION_ONNX);
        if !seg_path.exists() {
            return Err(Error::Diar(format!(
                "segmentation model not found: {}",
                seg_path.display()
            )));
        }
        let seg_model = SegmentationModel::new(
            &seg_path,
            SEGMENTATION_STEP_SECONDS as f32,
            &exec_config,
        )?;
        let emb_model = EmbeddingModel::new(
            models_dir.join(crate::diar::EMBEDDING_ONNX),
            &exec_config,
        )?;
        let plda = PldaTransform::from_dir(models_dir)?;
        Ok(Self {
            seg_model,
            emb_model,
            powerset: PowersetMapping::new(3, 2),
            plda,
            config,
            pending: Vec::new(),
            total_samples: 0,
            win_segs: Vec::new(),
            win_embs: Vec::new(),
            labels: Vec::new(),
            train_rows: Vec::new(),
            centroids: None,
            centroid_ids: Vec::new(),
            next_id: 0,
            last_recluster_t: f64::NEG_INFINITY,
        })
    }

    /// Drop all streaming state (speaker ids restart from 0).
    pub fn reset(&mut self) {
        self.pending.clear();
        self.total_samples = 0;
        self.win_segs.clear();
        self.win_embs.clear();
        self.labels.clear();
        self.train_rows.clear();
        self.centroids = None;
        self.centroid_ids.clear();
        self.next_id = 0;
        self.last_recluster_t = f64::NEG_INFINITY;
    }

    /// Global end of the pushed audio, in seconds.
    pub fn total_seconds(&self) -> f64 {
        self.total_samples as f64 / SAMPLE_RATE as f64
    }

    /// Append NEW (non-overlapping) 16 kHz mono samples and process every
    /// window they complete.
    pub fn push_audio(&mut self, samples: &[f32]) -> Result<()> {
        self.pending.extend_from_slice(samples);
        self.total_samples += samples.len();
        let window = self.seg_model.window_samples();
        let step = self.seg_model.step_samples();
        while self.pending.len() >= window {
            let win_audio: Vec<f32> = self.pending[..window].to_vec();
            self.process_window(&win_audio)?;
            self.pending.drain(..step);
        }
        Ok(())
    }

    fn process_window(&mut self, audio: &[f32]) -> Result<()> {
        let artifacts = run_sequential_inference(
            &mut self.seg_model,
            &mut self.emb_model,
            &self.powerset,
            audio,
        )?;
        let seg = artifacts.segmentations.0.slice(s![0, .., ..]).to_owned();
        let emb = artifacts.embeddings.0.slice(s![0, .., ..]).to_owned();
        let win_idx = self.win_segs.len();
        let num_local = seg.ncols();
        self.train_rows
            .extend(training_rows(&seg, &emb).into_iter().map(|s| (win_idx, s)));
        self.win_segs.push(seg);
        self.win_embs.push(emb);
        self.labels.push(vec![-2; num_local]);

        let now = win_idx as f64 * SEGMENTATION_STEP_SECONDS + SEGMENTATION_WINDOW_SECONDS;

        let Some(centroids) = self.centroids.as_ref() else {
            // Bootstrap as soon as clustering is possible at all.
            if self.train_rows.len() >= 2 {
                self.recluster(now);
            }
            return Ok(());
        };

        // Cruise: instant assignment of this window against the centroids.
        let assigns = assign_window(
            &self.win_segs[win_idx],
            &self.win_embs[win_idx],
            centroids,
        );
        for (spk, row) in assigns {
            self.labels[win_idx][spk] = self.centroid_ids[row];
        }

        // New-voice detection on this window's training-quality rows only.
        let worst = self
            .train_rows
            .iter()
            .filter(|(w, _)| *w == win_idx)
            .map(|(_, spk)| {
                let emb = self.win_embs[win_idx].row(*spk);
                (0..centroids.nrows())
                    .map(|r| 1.0 - cosine_similarity(&emb, &centroids.row(r)))
                    .fold(f32::INFINITY, f32::min)
            })
            .fold(f32::NEG_INFINITY, f32::max);
        if worst > self.config.new_voice_dist
            && now - self.last_recluster_t >= self.config.cooldown_secs
        {
            self.recluster(now);
        }
        Ok(())
    }

    /// Full re-clustering on every training row accumulated so far, stable-id
    /// matching against the previous centroids, and internal relabel of all
    /// processed windows.
    fn recluster(&mut self, now: f64) {
        let dim = self.win_embs[0].ncols();
        let mut train = Array2::<f32>::zeros((self.train_rows.len(), dim));
        for (row, (w, spk)) in self.train_rows.iter().enumerate() {
            train.slice_mut(s![row, ..]).assign(&self.win_embs[*w].row(*spk));
        }

        // Mirror of pipeline.rs TrainingEmbeddings::cluster up to centroids.
        let ahc_labels = ahc::cluster(&train.view(), self.config.pipeline.ahc.clone());
        let feats = self.plda.transform(&train.view(), 128);
        let phi = self.plda.phi();
        let (gamma, pi): (Array2<f32>, Array1<f32>) = cluster_vbx(
            &ahc_labels,
            &feats.view(),
            &phi.slice(s![..128]),
            &self.config.pipeline.vbx,
        );
        let mut kept: Vec<usize> = pi
            .iter()
            .enumerate()
            .filter_map(|(idx, w)| {
                (*w > self.config.pipeline.speaker_keep_threshold as f32).then_some(idx)
            })
            .collect();
        if kept.is_empty() && !pi.is_empty() {
            let best = pi
                .iter()
                .enumerate()
                .max_by(|a, b| a.1.total_cmp(b.1))
                .map(|(idx, _)| idx)
                .unwrap_or(0);
            kept.push(best);
        }
        let new_centroids = weighted_centroids(&train, &gamma, &kept);

        // Stable-id matching: greedy closest-pair inheritance.
        let mut new_ids = vec![-1i32; new_centroids.nrows()];
        if let Some(old) = self.centroids.as_ref() {
            let mut pairs: Vec<(f32, usize, usize)> = Vec::new();
            for n in 0..new_centroids.nrows() {
                for o in 0..old.nrows() {
                    let dist =
                        1.0 - cosine_similarity(&new_centroids.row(n), &old.row(o));
                    if dist <= self.config.id_match_dist {
                        pairs.push((dist, n, o));
                    }
                }
            }
            pairs.sort_by(|a, b| a.0.total_cmp(&b.0));
            let mut used_new = vec![false; new_centroids.nrows()];
            let mut used_old = vec![false; old.nrows()];
            for (_, n, o) in pairs {
                if used_new[n] || used_old[o] {
                    continue;
                }
                used_new[n] = true;
                used_old[o] = true;
                new_ids[n] = self.centroid_ids[o];
            }
        }
        for id in new_ids.iter_mut() {
            if *id < 0 {
                *id = self.next_id;
                self.next_id += 1;
            }
        }

        // Relabel every processed window against the new centroids.
        for w in 0..self.win_segs.len() {
            let assigns = assign_window(&self.win_segs[w], &self.win_embs[w], &new_centroids);
            for l in self.labels[w].iter_mut() {
                *l = -2;
            }
            for (spk, row) in assigns {
                self.labels[w][spk] = new_ids[row];
            }
        }

        // First clustering: renumber public ids by first appearance so the
        // first voice heard is speaker 0 (mirrors the batch binary output).
        if self.centroids.is_none() {
            let mut order: Vec<i32> = Vec::new();
            for lab in self.labels.iter().flatten() {
                if *lab >= 0 && !order.contains(lab) {
                    order.push(*lab);
                }
            }
            let remap = |id: i32| -> i32 {
                order.iter().position(|o| *o == id).map_or(id, |p| p as i32)
            };
            for lab in self.labels.iter_mut().flatten() {
                if *lab >= 0 {
                    *lab = remap(*lab);
                }
            }
            for id in new_ids.iter_mut() {
                *id = remap(*id);
            }
            self.next_id = order.len() as i32;
        }

        self.centroids = Some(new_centroids);
        self.centroid_ids = new_ids;
        self.last_recluster_t = now;
    }

    /// Speaker turns intersecting `[start, end)` on the global timeline,
    /// clipped to that range. Reconstructs only the windows overlapping the
    /// range (bounded cost), plus a transient zero-padded peek window over
    /// the not-yet-windowed audio tail so the range is covered to its end.
    pub fn turns_in_range(&mut self, start: f64, end: f64) -> Result<Vec<LiveTurn>> {
        let step = SEGMENTATION_STEP_SECONDS;
        let win_secs = SEGMENTATION_WINDOW_SECONDS;
        let num_windows = self.win_segs.len();

        // Transient peek over the pending tail (never stored).
        let peek = if !self.pending.is_empty() && self.centroids.is_some() {
            let mut padded = vec![0.0f32; self.seg_model.window_samples()];
            let n = self.pending.len().min(padded.len());
            padded[..n].copy_from_slice(&self.pending[..n]);
            let artifacts = run_sequential_inference(
                &mut self.seg_model,
                &mut self.emb_model,
                &self.powerset,
                &padded,
            )?;
            let seg = artifacts.segmentations.0.slice(s![0, .., ..]).to_owned();
            let emb = artifacts.embeddings.0.slice(s![0, .., ..]).to_owned();
            let mut labels = vec![-2i32; seg.ncols()];
            if let Some(centroids) = self.centroids.as_ref() {
                for (spk, row) in assign_window(&seg, &emb, centroids) {
                    labels[spk] = self.centroid_ids[row];
                }
            }
            let peek_start =
                (self.total_samples - self.pending.len()) as f64 / SAMPLE_RATE as f64;
            Some((seg, labels, peek_start))
        } else {
            None
        };

        // Stored windows overlapping [start, end).
        let first = ((start - win_secs) / step).ceil().max(0.0) as usize;
        let last = ((end / step).floor() as usize + 1).min(num_windows);
        let mut selected: Vec<(usize, f64)> = (first..last)
            .map(|w| (w, w as f64 * step))
            .filter(|(_, t)| *t < end && *t + win_secs > start)
            .collect();
        let peek_entry = peek.as_ref().map(|(_, _, t)| *t);
        if selected.is_empty() && peek_entry.is_none() {
            return Ok(Vec::new());
        }

        let tail_origin = selected
            .first()
            .map(|(_, t)| *t)
            .or(peek_entry)
            .unwrap_or(0.0)
            .min(peek_entry.unwrap_or(f64::INFINITY));
        let frames = self
            .win_segs
            .first()
            .map(|s| s.nrows())
            .or_else(|| peek.as_ref().map(|(s, _, _)| s.nrows()))
            .unwrap_or(0);
        if frames == 0 {
            return Ok(Vec::new());
        }

        let closest_frame = |ts: f64| -> usize {
            ((ts - 0.5 * FRAME_DURATION_SECONDS) / FRAME_STEP_SECONDS).round() as usize
        };

        let total = selected.len() + peek.is_some() as usize;
        let num_local = self.win_segs.first().map_or(
            peek.as_ref().map_or(0, |(s, _, _)| s.ncols()),
            |s| s.ncols(),
        );
        let mut stacked = Array3::<f32>::zeros((total, frames, num_local));
        let mut clusters = Array2::<i32>::from_elem((total, num_local), -2);
        let mut start_frames = Vec::with_capacity(total);
        for (row, (w, t)) in selected.drain(..).enumerate() {
            stacked.slice_mut(s![row, .., ..]).assign(&self.win_segs[w]);
            for (spk, lab) in self.labels[w].iter().enumerate() {
                clusters[[row, spk]] = *lab;
            }
            start_frames.push(closest_frame(t - tail_origin + 0.5 * FRAME_DURATION_SECONDS));
        }
        if let Some((seg, labels, t)) = peek.as_ref() {
            let row = total - 1;
            stacked.slice_mut(s![row, .., ..]).assign(seg);
            for (spk, lab) in labels.iter().enumerate() {
                clusters[[row, spk]] = *lab;
            }
            start_frames.push(closest_frame(t - tail_origin + 0.5 * FRAME_DURATION_SECONDS));
        }

        let output_frames = start_frames.iter().max().copied().unwrap_or(0) + frames;
        let segmentations = DecodedSegmentations(stacked);
        let hard_clusters = ChunkSpeakerClusters(clusters);
        let reconstructor =
            Reconstructor::with_clusters(&segmentations, &hard_clusters, &start_frames, 0);
        let speaker_count = reconstructor.speaker_count(output_frames);
        let discrete = match self.config.pipeline.reconstruct_method {
            pipeline::ReconstructMethod::Smoothed { epsilon } => {
                reconstructor.reconstruct_smoothed(&speaker_count, epsilon)
            }
            pipeline::ReconstructMethod::Standard => reconstructor.reconstruct(&speaker_count),
        };
        let segments = merge_segments(
            &discrete.to_segments(FRAME_STEP_SECONDS, FRAME_DURATION_SECONDS),
            self.config.pipeline.merge_gap,
        );
        // Live segments carry no confidence channel (+INF), so the margin path
        // is inert here; passed through for config parity with file diarization.
        let segments = crate::diar::segment::enforce_min_turn(
            &segments,
            self.config.pipeline.min_turn_duration,
            self.config.pipeline.confidence_absorb_margin,
        );

        let mut turns = Vec::new();
        for seg in segments {
            let s = seg.start + tail_origin;
            let e = seg.end + tail_origin;
            if e <= start || s >= end {
                continue;
            }
            let speaker: i32 = seg
                .speaker
                .strip_prefix("SPEAKER_")
                .and_then(|n| n.parse().ok())
                .unwrap_or(-1);
            turns.push(LiveTurn {
                start: s.max(start),
                end: e.min(end),
                speaker,
            });
        }
        turns.sort_by(|a, b| a.start.total_cmp(&b.start));
        Ok(turns)
    }
}

/// Training-quality local speakers of one window (mirror of pipeline.rs
/// `ChunkEmbeddings::training_set` for a single chunk).
fn training_rows(seg: &Array2<f32>, emb: &Array2<f32>) -> Vec<usize> {
    let num_frames = seg.nrows() as f32;
    let single_active: Vec<bool> = seg
        .rows()
        .into_iter()
        .map(|row| (row.iter().copied().sum::<f32>() - 1.0).abs() < 1e-6)
        .collect();
    let mut rows = Vec::new();
    for spk in 0..seg.ncols() {
        let clean_frames = seg
            .column(spk)
            .iter()
            .zip(single_active.iter())
            .filter_map(|(v, single)| single.then_some(*v))
            .sum::<f32>();
        let valid = emb.row(spk).iter().all(|v| v.is_finite());
        if valid && clean_frames >= 0.2 * num_frames {
            rows.push(spk);
        }
    }
    rows
}

/// Constrained cosine assignment of one window's embeddings against the
/// centroids (mirror of pipeline.rs `assign_chunk_embeddings` for one chunk).
/// Returns (local speaker, centroid row) pairs.
fn assign_window(
    seg: &Array2<f32>,
    emb: &Array2<f32>,
    centroids: &Array2<f32>,
) -> Vec<(usize, usize)> {
    let num_local = emb.nrows();
    let k = centroids.nrows();
    let mut active_local = Vec::new();
    let mut scores = Array2::<f32>::from_elem((num_local, k), f32::NEG_INFINITY);
    for spk in 0..num_local {
        if seg.column(spk).sum() <= 0.0 {
            continue;
        }
        active_local.push(spk);
        let e = emb.row(spk);
        if e.iter().any(|v| !v.is_finite()) {
            continue;
        }
        for c in 0..k {
            scores[[spk, c]] = 1.0 + cosine_similarity(&e, &centroids.row(c));
        }
    }
    let finite_min = scores
        .iter()
        .copied()
        .filter(|v| v.is_finite())
        .fold(f32::INFINITY, f32::min);
    if finite_min.is_finite() {
        let mask = finite_min - 1.0;
        scores.mapv_inplace(|v| if v.is_finite() { v } else { mask });
    }
    best_assignment(&scores, &active_local, k)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn training_rows_filters_nan_and_overlap() {
        // 10 frames, 3 speakers: spk0 clean solo activity, spk1 always in
        // overlap (2 active), spk2 has a NaN embedding.
        let mut seg = Array2::<f32>::zeros((10, 3));
        for f in 0..8 {
            seg[[f, 0]] = 1.0;
        }
        seg[[8, 1]] = 1.0;
        seg[[8, 2]] = 1.0;
        seg[[9, 1]] = 1.0;
        seg[[9, 2]] = 1.0;
        let mut emb = Array2::<f32>::zeros((3, 4));
        emb.row_mut(0).fill(1.0);
        emb.row_mut(1).fill(1.0);
        emb[[2, 0]] = f32::NAN;
        assert_eq!(training_rows(&seg, &emb), vec![0]);
    }

    #[test]
    fn assign_window_prefers_closest_centroid() {
        let mut seg = Array2::<f32>::zeros((4, 2));
        seg[[0, 0]] = 1.0;
        seg[[1, 1]] = 1.0;
        let mut emb = Array2::<f32>::zeros((2, 3));
        emb.row_mut(0).assign(&ndarray::arr1(&[1.0, 0.0, 0.0]));
        emb.row_mut(1).assign(&ndarray::arr1(&[0.0, 1.0, 0.0]));
        let mut centroids = Array2::<f32>::zeros((2, 3));
        centroids.row_mut(0).assign(&ndarray::arr1(&[0.0, 0.9, 0.1]));
        centroids.row_mut(1).assign(&ndarray::arr1(&[0.9, 0.1, 0.0]));
        let mut assigns = assign_window(&seg, &emb, &centroids);
        assigns.sort();
        assert_eq!(assigns, vec![(0, 1), (1, 0)]);
    }
}
