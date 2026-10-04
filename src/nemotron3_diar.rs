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

use crate::diar_pieces::{transcription_pieces, PieceParams};
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

/// How the speaker cache is fed, in encoder frames of 80 ms: NVIDIA's streaming configurations
/// (model card). The input buffer latency is (`chunk_len` + `right_context`) x 80 ms.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Latency {
    /// Encoder frames of a chunk.
    pub chunk_len: usize,
    /// Look-ahead frames the chunk takes from the next ones.
    pub right_context: usize,
    /// Capacity of the FIFO queue of the most recent frames.
    pub fifo_len: usize,
    /// Frames moved from the FIFO queue to the speaker cache when the queue overflows.
    pub update_period: usize,
}

impl Latency {
    /// Offline mode of config.json, 30.4 s: a whole recording.
    pub const OFFLINE: Self = Self {
        chunk_len: 340,
        right_context: 40,
        fifo_len: 40,
        update_period: 300,
    };
    /// Low latency, 1.04 s: a meeting followed live.
    pub const LOW: Self = Self {
        chunk_len: 9,
        right_context: 4,
        fifo_len: 264,
        update_period: 222,
    };
}

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

    let mut spectrum = MelSpectrum::new();
    for (t, row) in features.rows_mut().into_iter().take(valid).enumerate() {
        spectrum.frame(&signal[t * HOP_LENGTH..t * HOP_LENGTH + N_FFT], row);
    }
    (features, valid)
}

/// Window, FFT and mel filterbank of one frame of the pre-emphasised, padded signal.
struct MelSpectrum {
    window: Vec<f32>,
    filters: Vec<MelFilter>,
    fft: std::sync::Arc<dyn rustfft::Fft<f32>>,
    buffer: Vec<Complex<f32>>,
    scratch: Vec<Complex<f32>>,
    power: Vec<f32>,
}

impl MelSpectrum {
    fn new() -> Self {
        let mut window = vec![0.0f32; N_FFT];
        let offset = (N_FFT - WIN_LENGTH) / 2;
        window[offset..offset + WIN_LENGTH].copy_from_slice(&symmetric_hann(WIN_LENGTH));
        let fft = FftPlanner::<f32>::new().plan_fft_forward(N_FFT);
        let scratch = vec![Complex::new(0.0f32, 0.0); fft.get_inplace_scratch_len()];
        Self {
            window,
            filters: MelFilter::bank(),
            fft,
            buffer: vec![Complex::new(0.0f32, 0.0); N_FFT],
            scratch,
            power: vec![0.0f32; N_FFT / 2 + 1],
        }
    }

    /// Log-mel values of `frame` (`N_FFT` samples) into `row`.
    fn frame(&mut self, frame: &[f32], mut row: ndarray::ArrayViewMut1<f32>) {
        for ((b, &x), &w) in self.buffer.iter_mut().zip(frame).zip(&self.window) {
            *b = Complex::new(x * w, 0.0);
        }
        self.fft
            .process_with_scratch(&mut self.buffer, &mut self.scratch);
        for (p, c) in self.power.iter_mut().zip(&self.buffer) {
            *p = c.norm_sqr();
        }
        for (out, filter) in row.iter_mut().zip(&self.filters) {
            *out = (filter.apply(&self.power) + LOG_GUARD).ln();
        }
    }
}

/// The frames of `log_mel_features` for audio that arrives piece by piece: a frame comes out as
/// soon as its window is complete, the last ones at `finish`.
struct MelStream {
    spectrum: MelSpectrum,
    /// The pre-emphasised signal with its leading pad, from padded sample `base` on.
    signal: Vec<f32>,
    base: usize,
    last_sample: Option<f32>,
    samples: usize,
    next_frame: usize,
}

impl MelStream {
    fn new() -> Self {
        Self {
            spectrum: MelSpectrum::new(),
            signal: vec![0.0; N_FFT / 2],
            base: 0,
            last_sample: None,
            samples: 0,
            next_frame: 0,
        }
    }

    /// Frames of the audio so far, `samples / HOP_LENGTH` once finished.
    fn valid(&self) -> usize {
        self.samples / HOP_LENGTH
    }

    /// Appends audio; returns the frames it completes.
    fn push(&mut self, audio: &[f32]) -> Array2<f32> {
        for &x in audio {
            let y = match self.last_sample {
                None => x,
                Some(previous) => x - PREEMPHASIS * previous,
            };
            self.signal.push(y);
            self.last_sample = Some(x);
        }
        self.samples += audio.len();
        // frame t takes the padded samples t * HOP_LENGTH .. t * HOP_LENGTH + N_FFT
        let padded = N_FFT / 2 + self.samples;
        let complete = if padded >= N_FFT {
            (padded - N_FFT) / HOP_LENGTH + 1
        } else {
            0
        };
        self.frames_until(complete)
    }

    /// End of the audio: the trailing pad, and the frames left.
    fn finish(&mut self) -> Array2<f32> {
        self.signal.extend(std::iter::repeat_n(0.0, N_FFT / 2));
        self.frames_until(self.valid())
    }

    fn frames_until(&mut self, count: usize) -> Array2<f32> {
        let n = count.saturating_sub(self.next_frame);
        let mut out = Array2::<f32>::zeros((n, N_MELS));
        for (i, row) in out.rows_mut().into_iter().enumerate() {
            let start = (self.next_frame + i) * HOP_LENGTH - self.base;
            self.spectrum
                .frame(&self.signal[start..start + N_FFT], row);
        }
        self.next_frame += n;
        // no later frame needs the samples before its own start
        let keep_from = self.next_frame * HOP_LENGTH;
        if keep_from > self.base {
            self.signal.drain(..keep_from - self.base);
            self.base = keep_from;
        }
        out
    }
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
fn popped_frames(fifo_frames: usize, latency: &Latency) -> usize {
    if fifo_frames <= latency.fifo_len {
        0
    } else {
        latency
            .update_period
            .max(fifo_frames - latency.fifo_len)
            .min(fifo_frames)
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

/// Arrival-order speaker cache and FIFO queue of the most recent encoder frames, sized by the
/// latency: every chunk attends to them.
struct SpeakerCache {
    latency: Latency,
    embeds: Array2<f32>,
    /// Probabilities of the cache frames; the only ones left once the cache is out of time order.
    probs: Array2<f32>,
    fifo: Array2<f32>,
    compressed: bool,
}

impl SpeakerCache {
    fn new(latency: Latency) -> Self {
        Self {
            latency,
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
        let popped = popped_frames(fifo.nrows(), &self.latency);
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

/// 16 kHz audio with its channels averaged.
fn mono_16k(audio: Vec<f32>, sample_rate: u32, channels: u16) -> Result<Vec<f32>> {
    if sample_rate != SAMPLE_RATE {
        return Err(Error::Audio(format!(
            "Expected {SAMPLE_RATE} Hz, got {sample_rate} Hz"
        )));
    }
    Ok(if channels > 1 {
        audio
            .chunks(channels as usize)
            .map(|frame| frame.iter().sum::<f32>() / channels as f32)
            .collect()
    } else {
        audio
    })
}

/// (rows, columns) view of a (1, rows, columns) output of the graph.
fn output_2d<'a>(outputs: &'a SessionOutputs<'_>, name: &str) -> Result<ArrayView2<'a, f32>> {
    outputs[name]
        .try_extract_array::<f32>()?
        .into_dimensionality::<Ix3>()
        .map(|batch| batch.index_axis_move(Axis(0), 0))
        .map_err(|e| Error::Model(format!("unexpected shape of {name}: {e}")))
}

/// What one forward of the graph gives back: logits every 10 ms over the cached frames, the chunk
/// and its look-ahead; the chunk's encoder frames; the learned silence embedding.
struct StepOutput {
    logits: Array2<f32>,
    chunk_embeds: Array2<f32>,
    silence: Vec<f32>,
}

/// One forward of the graph, behind a trait so that the chunking can be tested without it.
trait StepModel {
    fn step(
        &mut self,
        features: Array2<f32>,
        cached: Array2<f32>,
        mask: &[bool],
    ) -> Result<StepOutput>;
}

impl StepModel for Session {
    fn step(
        &mut self,
        features: Array2<f32>,
        cached: Array2<f32>,
        mask: &[bool],
    ) -> Result<StepOutput> {
        let mask = Array2::from_shape_vec((1, mask.len()), mask.iter().map(|&v| v as i64).collect())
            .map_err(|e| Error::Model(e.to_string()))?;
        let outputs = self.run(ort::inputs![
            "input_features" => Tensor::from_array(features.insert_axis(Axis(0)))?,
            "cached_embeds" => Tensor::from_array(cached.insert_axis(Axis(0)))?,
            "attention_mask" => Tensor::from_array(mask)?,
        ])?;
        Ok(StepOutput {
            logits: output_2d(&outputs, "logits")?.to_owned(),
            chunk_embeds: output_2d(&outputs, "chunk_embeds")?.to_owned(),
            silence: outputs["silence_embeds"]
                .try_extract_array::<f32>()?
                .iter()
                .copied()
                .collect(),
        })
    }
}

/// The model's memory from one chunk to the next: the speaker cache with its FIFO queue, and the
/// learned silence embedding.
struct Tracker {
    cache: SpeakerCache,
    silence: Option<Vec<f32>>,
}

impl Tracker {
    fn new(latency: Latency) -> Self {
        Self {
            cache: SpeakerCache::new(latency),
            silence: None,
        }
    }

    /// Runs the chunk of `chunk_frames` encoder frames: `features` holds the mel frames of the
    /// chunk and its look-ahead, `valid` whether each of their encoder frames is real audio.
    /// Returns the speaker probabilities of the chunk's own first `mel_frames` mel frames.
    fn step<M: StepModel>(
        &mut self,
        model: &mut M,
        features: Array2<f32>,
        valid: &[bool],
        chunk_frames: usize,
        mel_frames: usize,
    ) -> Result<Array2<f32>> {
        let cached = self.cache.frames();
        let n_cached = cached.nrows();
        let step_valid: Vec<bool> = std::iter::repeat_n(true, n_cached)
            .chain(valid.iter().copied())
            .collect();
        let out = model.step(features, cached.clone(), &step_valid)?;
        if self.silence.is_none() {
            self.silence = Some(out.silence);
        }
        let step_probs = pool_probs(out.logits.view(), &step_valid);
        let step_embeds = concatenate![Axis(0), cached, out.chunk_embeds];
        self.cache.update(
            step_embeds.view(),
            step_probs.view(),
            self.silence.as_deref().unwrap_or_default(),
            chunk_frames,
        );
        // the chunk's own frames; its look-ahead frames are scored with the next chunk
        let offset = n_cached * SUBSAMPLING;
        Ok(out
            .logits
            .slice(s![offset..offset + mel_frames, ..])
            .mapv(sigmoid))
    }
}

/// Speaker probabilities of a whole 16 kHz mono recording, chunked by `latency`: (frames,
/// `NUM_SPEAKERS`), one frame every 10 ms as `log_mel_features` counts them; zero past the audio.
fn probs_offline<M: StepModel>(model: &mut M, audio: &[f32], latency: Latency) -> Result<Array2<f32>> {
    let (features, valid) = log_mel_features(audio);
    let n_frames = features.nrows();
    let mut probs = Array2::<f32>::zeros((n_frames, NUM_SPEAKERS));
    if valid == 0 {
        return Ok(probs);
    }
    let n_embeds = n_frames.div_ceil(SUBSAMPLING);
    let embed_valid: Vec<bool> = (0..n_embeds).map(|j| j * SUBSAMPLING < valid).collect();
    let mut tracker = Tracker::new(latency);
    for start in (0..n_embeds).step_by(latency.chunk_len) {
        let end = (start + latency.chunk_len).min(n_embeds);
        let stop = (end + latency.right_context).min(n_embeds);
        let input = features
            .slice(s![start * SUBSAMPLING..(stop * SUBSAMPLING).min(n_frames), ..])
            .to_owned();
        let first = start * SUBSAMPLING;
        let last = (end * SUBSAMPLING).min(n_frames);
        let rows = tracker.step(model, input, &embed_valid[start..stop], end - start, last - first)?;
        probs.slice_mut(s![first..last, ..]).assign(&rows);
    }
    probs.slice_mut(s![valid.., ..]).fill(0.0);
    Ok(probs)
}

/// The speaker probabilities of `probs_offline` for audio that arrives piece by piece: a chunk is
/// run as soon as its look-ahead is there, the last ones at `finish`.
struct ProbStream {
    latency: Latency,
    mel: MelStream,
    tracker: Tracker,
    /// Mel frames not yet consumed by a chunk, from mel frame `features_base` on.
    features: Array2<f32>,
    features_base: usize,
    next_embed: usize,
}

impl ProbStream {
    fn new(latency: Latency) -> Self {
        Self {
            latency,
            mel: MelStream::new(),
            tracker: Tracker::new(latency),
            features: Array2::zeros((0, N_MELS)),
            features_base: 0,
            next_embed: 0,
        }
    }

    /// Appends audio; returns the probabilities of the 10 ms frames it settles.
    fn push<M: StepModel>(&mut self, model: &mut M, audio: &[f32]) -> Result<Array2<f32>> {
        let fresh = self.mel.push(audio);
        self.features = concatenate![Axis(0), self.features, fresh];
        let mut parts = Vec::new();
        let (chunk, look_ahead) = (self.latency.chunk_len, self.latency.right_context);
        // a chunk runs once the mel frames of its look-ahead are all there (all real audio)
        while (self.next_embed + chunk + look_ahead) * SUBSAMPLING
            <= self.features_base + self.features.nrows()
        {
            let start = self.next_embed;
            let (end, stop) = (start + chunk, start + chunk + look_ahead);
            parts.push(self.run_chunk(model, start, end, stop, &vec![true; stop - start], chunk * SUBSAMPLING)?);
        }
        Ok(stack_rows(parts))
    }

    /// End of the audio: the probabilities of every frame left, `probs_offline`'s last rows.
    fn finish<M: StepModel>(&mut self, model: &mut M) -> Result<Array2<f32>> {
        let fresh = self.mel.finish();
        let valid = self.mel.valid();
        // log_mel_features counts one frame past the valid ones, zero
        self.features = concatenate![Axis(0), self.features, fresh, Array2::<f32>::zeros((1, N_MELS))];
        let n_frames = valid + 1;
        let n_embeds = n_frames.div_ceil(SUBSAMPLING);
        // the mel frame the rows below start at (the last chunk stops at n_frames, not at its end)
        let first_row = self.next_embed * SUBSAMPLING;
        let mut parts = Vec::new();
        while valid > 0 && self.next_embed < n_embeds {
            let start = self.next_embed;
            let end = (start + self.latency.chunk_len).min(n_embeds);
            let stop = (end + self.latency.right_context).min(n_embeds);
            let embed_valid: Vec<bool> = (start..stop).map(|j| j * SUBSAMPLING < valid).collect();
            let mel_frames = (end * SUBSAMPLING).min(n_frames) - start * SUBSAMPLING;
            parts.push(self.run_chunk(model, start, end, stop, &embed_valid, mel_frames)?);
        }
        let mut rows = stack_rows(parts);
        // the frames past the audio are zero, as in probs_offline; a silent stream has one zero row
        if valid == 0 {
            rows = Array2::zeros((n_frames.saturating_sub(first_row), NUM_SPEAKERS));
        } else {
            let zero_from = valid.saturating_sub(first_row).min(rows.nrows());
            rows.slice_mut(s![zero_from.., ..]).fill(0.0);
            rows = rows.slice(s![..n_frames - first_row, ..]).to_owned();
        }
        Ok(rows)
    }

    fn run_chunk<M: StepModel>(
        &mut self,
        model: &mut M,
        start: usize,
        end: usize,
        stop: usize,
        valid: &[bool],
        mel_frames: usize,
    ) -> Result<Array2<f32>> {
        let available = self.features_base + self.features.nrows();
        let from = start * SUBSAMPLING - self.features_base;
        let to = (stop * SUBSAMPLING).min(available) - self.features_base;
        let input = self.features.slice(s![from..to, ..]).to_owned();
        let rows = self.tracker.step(model, input, valid, end - start, mel_frames)?;
        self.next_embed = end;
        // later chunks start at `end`: drop the frames before it
        let drop = (end * SUBSAMPLING).min(available) - self.features_base;
        self.features = self.features.slice(s![drop.., ..]).to_owned();
        self.features_base += drop;
        Ok(rows)
    }
}

/// `parts` one under the other.
fn stack_rows(parts: Vec<Array2<f32>>) -> Array2<f32> {
    let views: Vec<_> = parts.iter().map(|p| p.view()).collect();
    if views.is_empty() {
        return Array2::zeros((0, NUM_SPEAKERS));
    }
    ndarray::concatenate(Axis(0), &views).expect("rows of the same width")
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
        let audio = mono_16k(audio, sample_rate, channels)?;
        let probs = self.speaker_probs(&audio)?;
        Ok(speaker_segments(probs.view(), self.threshold))
    }

    /// Transcription pieces of a whole recording (16 kHz; several channels are averaged), see
    /// `diar_pieces`.
    pub fn pieces(
        &mut self,
        audio: Vec<f32>,
        sample_rate: u32,
        channels: u16,
        params: &PieceParams,
    ) -> Result<Vec<SpeakerSegment>> {
        let audio = mono_16k(audio, sample_rate, channels)?;
        let probs = self.speaker_probs(&audio)?;
        Ok(transcription_pieces(
            probs.view(),
            &audio,
            self.threshold,
            params,
        ))
    }

    /// Speaker probabilities of 16 kHz mono audio: (frames, `NUM_SPEAKERS`), one frame every
    /// 10 ms, as `log_mel_features` counts them; zero on the frames past the end of the audio.
    pub fn speaker_probs(&mut self, audio: &[f32]) -> Result<Array2<f32>> {
        probs_offline(&mut self.session, audio, Latency::OFFLINE)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::{array, concatenate, s, Array2, Axis};

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
        let offline = Latency::OFFLINE;
        assert_eq!(popped_frames(0, &offline), 0);
        assert_eq!(popped_frames(40, &offline), 0);
        assert_eq!(popped_frames(41, &offline), 41);
        assert_eq!(popped_frames(340, &offline), 300);
        assert_eq!(popped_frames(380, &offline), 340);
        let low = Latency::LOW;
        assert_eq!(popped_frames(264, &low), 0);
        assert_eq!(popped_frames(273, &low), 222);
    }

    #[test]
    fn latencies_are_nvidias_input_buffers() {
        let buffer = |l: Latency| (l.chunk_len + l.right_context) * SUBSAMPLING * 10;
        assert_eq!(buffer(Latency::OFFLINE), 30_400); // ms
        assert_eq!(buffer(Latency::LOW), 1_040);
    }

    /// A stand-in for the ONNX graph, with its shapes: the logits depend on the cached frames and
    /// on the chunk's features, so any chunking or state difference between two runs shows.
    struct FakeModel;

    impl StepModel for FakeModel {
        fn step(
            &mut self,
            features: Array2<f32>,
            cached: Array2<f32>,
            mask: &[bool],
        ) -> Result<StepOutput> {
            let chunk = features.nrows().div_ceil(SUBSAMPLING);
            let n_cached = cached.nrows();
            assert_eq!(mask.len(), n_cached + chunk);
            let logits = Array2::from_shape_fn(
                ((n_cached + chunk) * SUBSAMPLING, NUM_SPEAKERS),
                |(r, s)| {
                    let v = if r < n_cached * SUBSAMPLING {
                        cached.row(r / SUBSAMPLING).sum()
                    } else {
                        let f = (r - n_cached * SUBSAMPLING).min(features.nrows() - 1);
                        features.row(f).sum()
                    };
                    (v * 0.013 + s as f32 * 0.7).sin() * 4.0
                },
            );
            let chunk_embeds = Array2::from_shape_fn((chunk, HIDDEN), |(f, h)| {
                let row = (f * SUBSAMPLING).min(features.nrows() - 1);
                features[[row, h % N_MELS]] * 0.01 + h as f32 * 1e-3
            });
            Ok(StepOutput {
                logits,
                chunk_embeds,
                silence: vec![-1.0; HIDDEN],
            })
        }
    }

    /// Tones switched on and off over a little noise, deterministic.
    fn test_audio(seconds: usize) -> Vec<f32> {
        let mut state = 12_345u32;
        (0..seconds * 16_000 + 77)
            .map(|i| {
                state = state.wrapping_mul(1_103_515_245).wrapping_add(12_345);
                let noise = (state >> 9) as f32 / (1u32 << 23) as f32 - 0.5;
                let gate = ((i / 4_000) % 2) as f32;
                0.3 * (i as f32 * 0.05).sin() + 0.2 * gate * (i as f32 * 0.31).sin() + 0.05 * noise
            })
            .collect()
    }

    /// `audio` in uneven pieces of 1, 159, 160, 513 and 7_919 samples, over and over.
    fn uneven_pieces(audio: &[f32]) -> Vec<&[f32]> {
        let sizes = [1, 159, 160, 513, 7_919];
        let mut pieces = Vec::new();
        let mut at = 0;
        for size in sizes.iter().cycle() {
            if at >= audio.len() {
                break;
            }
            let end = (at + size).min(audio.len());
            pieces.push(&audio[at..end]);
            at = end;
        }
        pieces
    }

    fn stacked(parts: Vec<Array2<f32>>, columns: usize) -> Array2<f32> {
        let views: Vec<_> = parts.iter().map(|p| p.view()).collect();
        if views.is_empty() {
            return Array2::zeros((0, columns));
        }
        concatenate(Axis(0), &views).unwrap()
    }

    #[test]
    fn mel_frames_arriving_piece_by_piece_are_the_whole_file_ones() {
        let audio = test_audio(3);
        let (whole, valid) = log_mel_features(&audio);
        let mut stream = MelStream::new();
        let mut parts: Vec<Array2<f32>> =
            uneven_pieces(&audio).into_iter().map(|p| stream.push(p)).collect();
        parts.push(stream.finish());
        assert_eq!(stream.valid(), valid);
        assert_eq!(stacked(parts, N_MELS), whole.slice(s![..valid, ..]));
    }

    #[test]
    fn probabilities_streamed_are_the_whole_file_ones() {
        // 70 s: enough low-latency steps for the speaker cache to fill and be compressed
        let audio = test_audio(70);
        for latency in [Latency::OFFLINE, Latency::LOW] {
            let whole = probs_offline(&mut FakeModel, &audio, latency).unwrap();
            let mut stream = ProbStream::new(latency);
            let mut parts: Vec<Array2<f32>> = uneven_pieces(&audio)
                .into_iter()
                .map(|p| stream.push(&mut FakeModel, p).unwrap())
                .collect();
            parts.push(stream.finish(&mut FakeModel).unwrap());
            let streamed = stacked(parts, NUM_SPEAKERS);
            assert_eq!(streamed.dim(), whole.dim(), "{latency:?}");
            assert_eq!(streamed, whole, "{latency:?}");
        }
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
        let mut cache = SpeakerCache::new(Latency::OFFLINE);
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
