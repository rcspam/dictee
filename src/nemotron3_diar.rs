//! Nemotron 3 Diarization (NVIDIA): streaming Sortformer-family speaker diarization, up to 8
//! speakers ordered by first arrival.
//!
//! Runs the onnx-community export of `nvidia/Nemotron-3-Diarization` in its offline mode. The graph
//! stacks the mel frames, encodes them and classifies the speakers; this module does what
//! transformers' `Nemotron3DiarizationForAudioFrameClassification` does around it: log-mel
//! features, chunking with look-ahead, the arrival-order speaker cache with its FIFO queue, and the
//! speaker segments at 10 ms.
//!
//! Reference: transformers commit 0a896aa41b (`modeling_nemotron3_diarization.py`,
//! `feature_extraction_nemotron_asr_streaming.py`, `processing_nemotron3_diarization.py`) and its
//! numpy port `tests/nemotron3-ref/reference.py`, which `tests/nemotron3_golden.rs` compares
//! against.

use crate::error::{Error, Result};
use crate::execution::ModelConfig;
use crate::sortformer::SpeakerSegment;
use ndarray::{concatenate, s, Array2, ArrayView1, ArrayView2, Axis, Ix3};
use ort::session::{Session, SessionOutputs};
use ort::value::Tensor;
use rustfft::{num_complex::Complex, FftPlanner};
use std::f32::consts::LN_2;
use std::path::Path;

/// Speakers the model tells apart.
pub const NUM_SPEAKERS: usize = 8;

// Feature extractor (preprocessor_config.json of the export).
const SAMPLE_RATE: u32 = 16_000;
const N_FFT: usize = 512;
const WIN_LENGTH: usize = 400;
const HOP_LENGTH: usize = 160;
const N_MELS: usize = 128;
const PREEMPHASIS: f32 = 0.97;
const LOG_GUARD: f32 = 1.0 / 16_777_216.0; // 2^-24

// Model geometry (config.json): 8 mel frames per encoder frame of 80 ms.
const SUBSAMPLING: usize = 8;
const HIDDEN: usize = 512;

// Offline mode (config.json), in encoder frames.
const CHUNK_LEN: usize = 340;
const RIGHT_CONTEXT: usize = 40;
const FIFO_LEN: usize = 40;
const UPDATE_PERIOD: usize = 300;

// Speaker cache policy (streaming_config of config.json). The frame counts are floor(budget x rate)
// for the rates 0.5, 0.75 and 1.5 of the config, in exact integer arithmetic.
const CACHE_LEN: usize = 264;
const SILENCE_SLOTS: usize = 1;
const SCORE_FLOOR: f32 = 0.25;
const LATEST_BOOST: f32 = 0.05;
const BUDGET: usize = CACHE_LEN / NUM_SPEAKERS - SILENCE_SLOTS;
const MIN_POSITIVE: usize = BUDGET / 2;
const STRONG_BOOSTED: usize = BUDGET * 3 / 4;
const WEAK_BOOSTED: usize = BUDGET * 3 / 2;

/// Log-mel features of 16 kHz mono audio, as the model expects them: (frames, 128), one frame
/// every 10 ms, and the number of valid frames. The frames past the valid ones are zero.
pub fn log_mel_features(audio: &[f32]) -> (Array2<f32>, usize) {
    // a centered STFT pads n_fft / 2 on each side: floor(len / hop) valid frames, plus one
    let valid = audio.len() / HOP_LENGTH;
    let mut features = Array2::<f32>::zeros((valid + 1, N_MELS));
    if valid == 0 {
        return (features, 0);
    }

    let pad = N_FFT / 2;
    let mut signal = vec![0.0f32; audio.len() + 2 * pad];
    signal[pad] = audio[0];
    for i in 1..audio.len() {
        signal[pad + i] = audio[i] - PREEMPHASIS * audio[i - 1];
    }

    let mut window = vec![0.0f32; N_FFT];
    let offset = (N_FFT - WIN_LENGTH) / 2;
    window[offset..offset + WIN_LENGTH].copy_from_slice(&symmetric_hann(WIN_LENGTH));

    let filters = MelFilter::bank();
    let fft = FftPlanner::<f32>::new().plan_fft_forward(N_FFT);
    let mut buffer = vec![Complex::new(0.0f32, 0.0); N_FFT];
    let mut scratch = vec![Complex::new(0.0f32, 0.0); fft.get_inplace_scratch_len()];
    let mut power = vec![0.0f32; N_FFT / 2 + 1];

    for (t, mut row) in features.rows_mut().into_iter().take(valid).enumerate() {
        let frame = &signal[t * HOP_LENGTH..t * HOP_LENGTH + N_FFT];
        for ((b, &x), &w) in buffer.iter_mut().zip(frame).zip(&window) {
            *b = Complex::new(x * w, 0.0);
        }
        fft.process_with_scratch(&mut buffer, &mut scratch);
        for (p, c) in power.iter_mut().zip(&buffer) {
            *p = c.norm_sqr();
        }
        for (out, filter) in row.iter_mut().zip(&filters) {
            *out = (filter.apply(&power) + LOG_GUARD).ln();
        }
    }
    (features, valid)
}

/// `torch.hann_window(len, periodic=False)`, i.e. numpy's `hanning`.
fn symmetric_hann(len: usize) -> Vec<f32> {
    let span = (len - 1) as f64;
    (0..len)
        .map(|i| (0.5 - 0.5 * (2.0 * std::f64::consts::PI * i as f64 / span).cos()) as f32)
        .collect()
}

/// One triangle of the Slaney mel filterbank, kept to its nonzero bins.
struct MelFilter {
    first_bin: usize,
    weights: Vec<f32>,
}

impl MelFilter {
    fn bank() -> Vec<MelFilter> {
        let dense = crate::audio::create_mel_filterbank(N_FFT, N_MELS, SAMPLE_RATE as usize);
        dense
            .rows()
            .into_iter()
            .map(|row| {
                let first_bin = row.iter().position(|&w| w != 0.0).unwrap_or(0);
                let end = row
                    .iter()
                    .rposition(|&w| w != 0.0)
                    .map_or(first_bin, |i| i + 1);
                MelFilter {
                    first_bin,
                    weights: row.slice(s![first_bin..end]).to_vec(),
                }
            })
            .collect()
    }

    fn apply(&self, power: &[f32]) -> f32 {
        self.weights
            .iter()
            .zip(&power[self.first_bin..])
            .map(|(w, p)| w * p)
            .sum()
    }
}

fn sigmoid(x: f32) -> f32 {
    1.0 / (1.0 + (-x).exp())
}

/// Speaker probabilities at the encoder frame rate: the sigmoid of the 10 ms logits averaged over
/// each group of 8, zero on the padding frames.
fn pool_probs(logits: ArrayView2<f32>, valid: &[bool]) -> Array2<f32> {
    let mut probs = Array2::<f32>::zeros((valid.len(), NUM_SPEAKERS));
    for (j, (mut row, &is_valid)) in probs.rows_mut().into_iter().zip(valid).enumerate() {
        if !is_valid {
            continue;
        }
        let frames = logits.slice(s![j * SUBSAMPLING..(j + 1) * SUBSAMPLING, ..]);
        for (p, column) in row.iter_mut().zip(frames.columns()) {
            *p = column.iter().map(|&x| sigmoid(x)).sum::<f32>() / SUBSAMPLING as f32;
        }
    }
    probs
}

/// Frames moved from the FIFO queue to the speaker cache: none until the queue overflows, then at
/// least an update period, and whatever else brings the queue back to its capacity.
fn popped_frames(fifo_frames: usize) -> usize {
    if fifo_frames <= FIFO_LEN {
        0
    } else {
        UPDATE_PERIOD.max(fifo_frames - FIFO_LEN).min(fifo_frames)
    }
}

/// Importance of every (frame, speaker) of the cache candidates; -inf for the frames a speaker
/// does not speak in, and for its weak frames once it has enough strong ones.
fn frame_scores(probs: ArrayView2<f32>) -> Array2<f32> {
    let mut scores = Array2::<f32>::from_elem(probs.raw_dim(), f32::NEG_INFINITY);
    for (row, mut out) in probs.rows().into_iter().zip(scores.rows_mut()) {
        let log_complements: [f32; NUM_SPEAKERS] =
            std::array::from_fn(|s| (1.0 - row[s]).max(SCORE_FLOOR).ln());
        let lc = &log_complements;
        // the summation order of numpy's reduction over eight values, to stay bit-exact
        let lc_sum = ((lc[0] + lc[1]) + (lc[2] + lc[3])) + ((lc[4] + lc[5]) + (lc[6] + lc[7]));
        for (s, score) in out.iter_mut().enumerate() {
            if row[s] > 0.5 {
                // + ln 2 is - ln 0.5 in the reference
                *score = row[s].max(SCORE_FLOOR).ln() - lc[s] + lc_sum + LN_2;
            }
        }
    }
    for mut column in scores.columns_mut() {
        if column.iter().filter(|&&v| v > 0.0).count() >= MIN_POSITIVE {
            column.mapv_inplace(|v| if v > 0.0 { v } else { f32::NEG_INFINITY });
        }
    }
    scores
}

/// Adds `boost` to the `k` best frames of every speaker (ties keep the earlier frame).
fn boost_top_k(scores: &mut Array2<f32>, k: usize, boost: f32) {
    let k = k.min(scores.nrows());
    if k == 0 {
        return;
    }
    for mut column in scores.columns_mut() {
        let mut order: Vec<usize> = (0..column.len()).collect();
        order.select_nth_unstable_by(k - 1, |&a, &b| {
            column[b].total_cmp(&column[a]).then(a.cmp(&b))
        });
        for &f in &order[..k] {
            column[f] += boost;
        }
    }
}

/// Frames of `probs` the compressed speaker cache keeps, `probs.nrows()` standing for the silence
/// slot: the `CACHE_LEN` best (frame, speaker) pairs, grouped by speaker and in time order within a
/// speaker, every speaker ending with its silence slot.
fn compress_indices(probs: ArrayView2<f32>) -> Vec<usize> {
    let n = probs.nrows();
    let mut scores = frame_scores(probs);
    // the frames past the cache capacity are the ones just popped from the FIFO queue
    scores
        .slice_mut(s![CACHE_LEN.min(n).., ..])
        .mapv_inplace(|v| v + LATEST_BOOST);
    boost_top_k(&mut scores, STRONG_BOOSTED, 2.0 * LN_2);
    boost_top_k(&mut scores, WEAK_BOOSTED, LN_2);

    // speaker-major ranking of the frames plus the silence slot, which always makes the cut
    let scored = n + SILENCE_SLOTS;
    let scores = &scores;
    let mut ranked: Vec<(f32, usize)> = (0..NUM_SPEAKERS)
        .flat_map(|s| {
            (0..scored).map(move |f| {
                let score = if f < n { scores[[f, s]] } else { f32::INFINITY };
                (score, s * scored + f)
            })
        })
        .collect();
    ranked.select_nth_unstable_by(CACHE_LEN - 1, |a, b| {
        b.0.total_cmp(&a.0).then(a.1.cmp(&b.1))
    });

    // a pair nobody speaks in is replaced by a silence slot, after all the others
    let sentinel = scored * NUM_SPEAKERS;
    let mut kept: Vec<usize> = ranked[..CACHE_LEN]
        .iter()
        .map(|&(score, i)| {
            if score == f32::NEG_INFINITY {
                sentinel
            } else {
                i
            }
        })
        .collect();
    kept.sort_unstable();
    kept.into_iter()
        .map(|i| {
            if i == sentinel {
                n
            } else {
                (i % scored).min(n)
            }
        })
        .collect()
}

/// Rows `keep` of `embeds` and `probs`, the index `embeds.nrows()` giving the silence embedding
/// with zero probabilities.
fn gather(
    embeds: &Array2<f32>,
    probs: &Array2<f32>,
    silence: &[f32],
    keep: &[usize],
) -> (Array2<f32>, Array2<f32>) {
    let n = embeds.nrows();
    let mut kept_embeds = Array2::<f32>::zeros((keep.len(), embeds.ncols()));
    let mut kept_probs = Array2::<f32>::zeros((keep.len(), NUM_SPEAKERS));
    for (row, &f) in keep.iter().enumerate() {
        if f == n {
            kept_embeds.row_mut(row).assign(&ArrayView1::from(silence));
        } else {
            kept_embeds.row_mut(row).assign(&embeds.row(f));
            kept_probs.row_mut(row).assign(&probs.row(f));
        }
    }
    (kept_embeds, kept_probs)
}

/// Arrival-order speaker cache and FIFO queue of the most recent encoder frames, in their offline
/// sizes: every chunk attends to them.
struct SpeakerCache {
    embeds: Array2<f32>,
    /// Probabilities of the cache frames; the only ones left once the cache is out of time order.
    probs: Array2<f32>,
    fifo: Array2<f32>,
    compressed: bool,
}

impl SpeakerCache {
    fn new() -> Self {
        Self {
            embeds: Array2::zeros((0, HIDDEN)),
            probs: Array2::zeros((0, NUM_SPEAKERS)),
            fifo: Array2::zeros((0, HIDDEN)),
            compressed: false,
        }
    }

    /// The cached frames a chunk is prefixed with: the speaker cache, then the FIFO queue.
    fn frames(&self) -> Array2<f32> {
        concatenate![Axis(0), self.embeds, self.fifo]
    }

    /// Pushes a processed chunk to the FIFO queue, moving its oldest frames to the speaker cache
    /// when it overflows. `step_embeds` and `step_probs` cover the step input: the cached frames,
    /// the `chunk_frames` frames of the chunk, then its look-ahead, which stays out.
    fn update(
        &mut self,
        step_embeds: ArrayView2<f32>,
        step_probs: ArrayView2<f32>,
        silence: &[f32],
        chunk_frames: usize,
    ) {
        let n_cache = self.embeds.nrows();
        let start = n_cache + self.fifo.nrows();
        let fifo = concatenate![
            Axis(0),
            self.fifo,
            step_embeds.slice(s![start..start + chunk_frames, ..])
        ];
        let popped = popped_frames(fifo.nrows());
        if popped == 0 {
            self.fifo = fifo;
            return;
        }

        // an uncompressed cache holds plain chunk frames, whose probabilities this step re-estimates
        let stored = if self.compressed {
            self.probs.view()
        } else {
            step_probs.slice(s![..n_cache, ..])
        };
        let embeds = concatenate![Axis(0), self.embeds, fifo.slice(s![..popped, ..])];
        let probs = concatenate![
            Axis(0),
            stored,
            step_probs.slice(s![n_cache..n_cache + popped, ..])
        ];
        (self.embeds, self.probs) = if embeds.nrows() > CACHE_LEN {
            self.compressed = true;
            gather(&embeds, &probs, silence, &compress_indices(probs.view()))
        } else {
            (embeds, probs)
        };
        self.fifo = fifo.slice(s![popped.., ..]).to_owned();
    }
}

/// Segments where a speaker's probability is above `threshold`, from probabilities every 10 ms,
/// sorted by start then speaker. Overlapping speech gives overlapping segments.
fn speaker_segments(probs: ArrayView2<f32>, threshold: f32) -> Vec<SpeakerSegment> {
    let seconds = |frame: usize| (frame as f64 * HOP_LENGTH as f64 / SAMPLE_RATE as f64) as f32;
    let mut segments = Vec::new();
    for (speaker_id, column) in probs.columns().into_iter().enumerate() {
        let mut start = None;
        for (f, &p) in column.iter().chain(std::iter::once(&0.0)).enumerate() {
            match (start, p > threshold) {
                (None, true) => start = Some(f),
                (Some(first), false) => {
                    segments.push(SpeakerSegment {
                        start: seconds(first),
                        end: seconds(f),
                        speaker_id,
                    });
                    start = None;
                }
                _ => {}
            }
        }
    }
    segments.sort_by(|a, b| {
        a.start
            .total_cmp(&b.start)
            .then(a.speaker_id.cmp(&b.speaker_id))
    });
    segments
}

/// (rows, columns) view of a (1, rows, columns) output of the graph.
fn output_2d<'a>(outputs: &'a SessionOutputs<'_>, name: &str) -> Result<ArrayView2<'a, f32>> {
    outputs[name]
        .try_extract_array::<f32>()?
        .into_dimensionality::<Ix3>()
        .map(|batch| batch.index_axis_move(Axis(0), 0))
        .map_err(|e| Error::Model(format!("unexpected shape of {name}: {e}")))
}

/// Nemotron 3 Diarization engine.
pub struct Nemotron3Diarizer {
    session: Session,
    threshold: f32,
}

impl Nemotron3Diarizer {
    /// Loads the ONNX model (`model.onnx`, with its `model.onnx_data` next to it). `threshold` is
    /// the speaker probability above which a 10 ms frame counts as speech of that speaker (0.5 in
    /// the reference).
    pub fn with_config<P: AsRef<Path>>(
        model_path: P,
        execution: Option<ModelConfig>,
        threshold: f32,
    ) -> Result<Self> {
        let session = execution
            .unwrap_or_default()
            .apply_to_session_builder(Session::builder()?)?
            .commit_from_file(model_path.as_ref())?;
        Ok(Self { session, threshold })
    }

    /// Speaker segments of a whole recording (16 kHz; several channels are averaged).
    pub fn diarize(
        &mut self,
        audio: Vec<f32>,
        sample_rate: u32,
        channels: u16,
    ) -> Result<Vec<SpeakerSegment>> {
        if sample_rate != SAMPLE_RATE {
            return Err(Error::Audio(format!(
                "Expected {SAMPLE_RATE} Hz, got {sample_rate} Hz"
            )));
        }
        let audio = if channels > 1 {
            audio
                .chunks(channels as usize)
                .map(|frame| frame.iter().sum::<f32>() / channels as f32)
                .collect()
        } else {
            audio
        };
        let probs = self.speaker_probs(&audio)?;
        Ok(speaker_segments(probs.view(), self.threshold))
    }

    /// Speaker probabilities of 16 kHz mono audio: (frames, `NUM_SPEAKERS`), one frame every
    /// 10 ms, as `log_mel_features` counts them; zero on the frames past the end of the audio.
    pub fn speaker_probs(&mut self, audio: &[f32]) -> Result<Array2<f32>> {
        let (features, valid) = log_mel_features(audio);
        let n_frames = features.nrows();
        let mut probs = Array2::<f32>::zeros((n_frames, NUM_SPEAKERS));
        if valid == 0 {
            return Ok(probs);
        }

        let n_embeds = n_frames.div_ceil(SUBSAMPLING);
        let embed_valid: Vec<bool> = (0..n_embeds).map(|j| j * SUBSAMPLING < valid).collect();
        let mut cache = SpeakerCache::new();
        let mut silence: Option<Vec<f32>> = None;

        for start in (0..n_embeds).step_by(CHUNK_LEN) {
            let end = (start + CHUNK_LEN).min(n_embeds);
            let stop = (end + RIGHT_CONTEXT).min(n_embeds);
            let cached = cache.frames();
            let n_cached = cached.nrows();
            let step_valid: Vec<bool> = std::iter::repeat_n(true, n_cached)
                .chain(embed_valid[start..stop].iter().copied())
                .collect();

            let input = features
                .slice(s![
                    start * SUBSAMPLING..(stop * SUBSAMPLING).min(n_frames),
                    ..
                ])
                .insert_axis(Axis(0))
                .to_owned();
            let mask = Array2::from_shape_vec(
                (1, step_valid.len()),
                step_valid.iter().map(|&v| v as i64).collect(),
            )
            .map_err(|e| Error::Model(e.to_string()))?;
            let outputs = self.session.run(ort::inputs![
                "input_features" => Tensor::from_array(input)?,
                "cached_embeds" => Tensor::from_array(cached.clone().insert_axis(Axis(0)))?,
                "attention_mask" => Tensor::from_array(mask)?,
            ])?;
            let logits = output_2d(&outputs, "logits")?;
            let chunk_embeds = output_2d(&outputs, "chunk_embeds")?;
            if silence.is_none() {
                let learned = outputs["silence_embeds"].try_extract_array::<f32>()?;
                silence = Some(learned.iter().copied().collect());
            }

            let step_probs = pool_probs(logits, &step_valid);
            let step_embeds = concatenate![Axis(0), cached, chunk_embeds];
            cache.update(
                step_embeds.view(),
                step_probs.view(),
                silence.as_deref().unwrap_or_default(),
                end - start,
            );

            // the chunk's own frames; its look-ahead frames are scored with the next chunk
            let first = start * SUBSAMPLING;
            let last = (end * SUBSAMPLING).min(n_frames);
            let offset = n_cached * SUBSAMPLING;
            let rows = logits.slice(s![offset..offset + (last - first), ..]);
            probs
                .slice_mut(s![first..last, ..])
                .zip_mut_with(&rows, |p, &x| *p = sigmoid(x));
        }
        probs.slice_mut(s![valid.., ..]).fill(0.0);
        Ok(probs)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::{array, s, Array2};

    #[test]
    fn hann_window_is_the_symmetric_one() {
        let w = symmetric_hann(400);
        assert_eq!(w.len(), 400);
        assert_eq!(w[0], 0.0);
        assert!(w[399].abs() < 1e-7);
        assert!((w[199] - w[200]).abs() < 1e-7);
        // a symmetric Hann window of N points sums to (N - 1) / 2
        assert!((w.iter().sum::<f32>() - 199.5).abs() < 1e-3);
    }

    #[test]
    fn features_count_one_frame_per_hop_plus_the_centered_one() {
        let (feats, valid) = log_mel_features(&vec![0.1f32; 16_000]);
        assert_eq!(feats.dim(), (101, 128));
        assert_eq!(valid, 100);
        assert!(feats.slice(s![100.., ..]).iter().all(|&v| v == 0.0));
        assert!(feats.slice(s![..100, ..]).iter().all(|&v| v != 0.0));
    }

    #[test]
    fn the_fifo_pops_once_full_then_by_update_periods() {
        assert_eq!(popped_frames(0), 0);
        assert_eq!(popped_frames(40), 0);
        assert_eq!(popped_frames(41), 41);
        assert_eq!(popped_frames(340), 300);
        assert_eq!(popped_frames(380), 340);
    }

    #[test]
    fn probabilities_are_averaged_over_eight_frames_and_masked() {
        let mut logits = Array2::<f32>::zeros((16, NUM_SPEAKERS));
        logits.slice_mut(s![..8, 0]).fill(2.0);
        logits[[0, 1]] = 8.0;
        logits.slice_mut(s![8.., 2]).fill(5.0);
        let probs = pool_probs(logits.view(), &[true, false]);
        assert_eq!(probs.dim(), (2, NUM_SPEAKERS));
        let sig = |x: f32| 1.0 / (1.0 + (-x).exp());
        assert!((probs[[0, 0]] - sig(2.0)).abs() < 1e-6);
        assert!((probs[[0, 1]] - (sig(8.0) + 7.0 * 0.5) / 8.0).abs() < 1e-6);
        assert!((probs[[0, 2]] - 0.5).abs() < 1e-6);
        assert!(probs.row(1).iter().all(|&p| p == 0.0));
    }

    #[derive(serde::Deserialize)]
    struct CompressFixture {
        probs: Vec<Vec<f32>>,
        keep: Vec<usize>,
    }

    #[test]
    fn compression_keeps_the_frames_the_reference_keeps() {
        let path =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/nemotron3-fixtures/compress.json");
        let fixture: CompressFixture =
            serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
        let n = fixture.probs.len();
        let flat: Vec<f32> = fixture.probs.into_iter().flatten().collect();
        let probs = Array2::from_shape_vec((n, NUM_SPEAKERS), flat).unwrap();
        assert_eq!(compress_indices(probs.view()), fixture.keep);
    }

    #[test]
    fn the_cache_fills_then_stays_at_its_capacity() {
        let mut cache = SpeakerCache::new();
        let silence = vec![-1.0f32; 512];
        for step in 0..3 {
            let n_cached = cache.embeds.nrows() + cache.fifo.nrows();
            let n_input = n_cached + 380; // 340 chunk frames + 40 look-ahead frames
                                          // frame f of the chunk carries the value f in its first dimension
            let mut embeds = Array2::<f32>::zeros((n_input, 512));
            for f in 0..380 {
                embeds[[n_cached + f, 0]] = (step * 1000 + f) as f32;
            }
            // speaker (f / 100) % 8 talks on chunk frame f
            let mut probs = Array2::<f32>::from_elem((n_input, NUM_SPEAKERS), 0.01);
            for f in 0..n_input {
                probs[[f, (f / 100) % NUM_SPEAKERS]] = 0.9;
            }
            cache.update(embeds.view(), probs.view(), &silence, 340);
            assert_eq!(cache.embeds.nrows(), 264, "step {step}");
            assert_eq!(cache.probs.nrows(), 264, "step {step}");
            assert_eq!(cache.fifo.nrows(), 40, "step {step}");
            // the FIFO keeps the 40 newest chunk frames, the look-ahead stays out
            assert_eq!(cache.fifo[[0, 0]], (step * 1000 + 300) as f32);
            assert_eq!(cache.fifo[[39, 0]], (step * 1000 + 339) as f32);
        }
        assert!(cache.compressed);
        // every speaker's group ends with a silence slot
        let silences = cache
            .embeds
            .rows()
            .into_iter()
            .filter(|r| r[1] == -1.0)
            .count();
        assert!(silences >= NUM_SPEAKERS);
    }

    #[test]
    fn segments_follow_the_strict_threshold_at_ten_ms() {
        let probs = array![
            [0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.9, 0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.5, 0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.2, 0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.7, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        ];
        let segs: Vec<(f32, f32, usize)> = speaker_segments(probs.view(), 0.5)
            .into_iter()
            .map(|g| (g.start, g.end, g.speaker_id))
            .collect();
        let close = |a: f32, b: f32| (a - b).abs() < 1e-6;
        let expected = [(0.00, 0.02, 0), (0.01, 0.04, 1), (0.04, 0.05, 0)];
        assert_eq!(segs.len(), expected.len(), "{segs:?}");
        for (got, want) in segs.iter().zip(expected) {
            assert!(
                close(got.0, want.0) && close(got.1, want.1) && got.2 == want.2,
                "{segs:?}"
            );
        }
    }
}
