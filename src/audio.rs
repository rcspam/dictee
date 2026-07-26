use crate::config::PreprocessorConfig;
use crate::error::{Error, Result};
use hound::{WavReader, WavSpec};
use ndarray::Array2;
use std::f32::consts::PI;
use std::path::Path;

pub fn load_audio<P: AsRef<Path>>(path: P) -> Result<(Vec<f32>, WavSpec)> {
    let mut reader = WavReader::open(path)?;
    let spec = reader.spec();

    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader
            .samples::<f32>()
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|e| Error::Audio(format!("Failed to read float samples: {e}")))?,
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.map(|s| s as f32 / 32768.0))
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|e| Error::Audio(format!("Failed to read int samples: {e}")))?,
    };

    Ok((samples, spec))
}

pub fn apply_preemphasis(audio: &[f32], coef: f32) -> Vec<f32> {
    let mut result = Vec::with_capacity(audio.len());
    result.push(audio[0]);

    for i in 1..audio.len() {
        result.push(audio[i] - coef * audio[i - 1]);
    }

    result
}

fn hann_window(window_length: usize) -> Vec<f32> {
    (0..window_length)
        .map(|i| 0.5 - 0.5 * ((2.0 * PI * i as f32) / (window_length as f32 - 1.0)).cos())
        .collect()
}

// We use proper FFT here instead of naive DFT because the model was trained
// on correctly computed spectrograms. Naive DFT produces wrong frequency bins
// and the model outputs all blank tokens. RustFFT gives us O(n log n) performance
// and numerically correct results that match what the model expects.
pub fn stft(audio: &[f32], n_fft: usize, hop_length: usize, win_length: usize) -> Array2<f32> {
    use rustfft::{num_complex::Complex, FftPlanner};

    let pad_amount = n_fft / 2;
    let mut padded = vec![0.0f32; pad_amount];
    padded.extend_from_slice(audio);
    padded.resize(padded.len() + pad_amount, 0.0);

    let window = hann_window(win_length);
    let num_frames = (padded.len() - n_fft) / hop_length + 1;
    let freq_bins = n_fft / 2 + 1;
    let mut spectrogram = Array2::<f32>::zeros((freq_bins, num_frames));

    let mut planner = FftPlanner::<f32>::new();
    let fft = planner.plan_fft_forward(n_fft);

    for frame_idx in 0..num_frames {
        let start = frame_idx * hop_length;

        let mut frame: Vec<Complex<f32>> = vec![Complex::new(0.0, 0.0); n_fft];
        for i in 0..win_length.min(padded.len() - start) {
            frame[i] = Complex::new(padded[start + i] * window[i], 0.0);
        }

        fft.process(&mut frame);

        for k in 0..freq_bins {
            let magnitude = frame[k].norm();
            spectrogram[[k, frame_idx]] = magnitude * magnitude;
        }
    }

    spectrogram
}

// Slaney mel scale (again librosa)
const F_SP: f64 = 200.0 / 3.0;
const MIN_LOG_HZ: f64 = 1000.0;
const MIN_LOG_MEL: f64 = MIN_LOG_HZ / F_SP;
const LOG_STEP: f64 = 0.06875177742094912;

fn hz_to_mel_slaney(hz: f64) -> f64 {
    if hz < MIN_LOG_HZ {
        hz / F_SP
    } else {
        MIN_LOG_MEL + (hz / MIN_LOG_HZ).ln() / LOG_STEP
    }
}

fn mel_to_hz_slaney(mel: f64) -> f64 {
    if mel < MIN_LOG_MEL {
        mel * F_SP
    } else {
        MIN_LOG_HZ * ((mel - MIN_LOG_MEL) * LOG_STEP).exp()
    }
}

pub fn create_mel_filterbank(n_fft: usize, n_mels: usize, sample_rate: usize) -> Array2<f32> {
    let freq_bins = n_fft / 2 + 1;
    let mut filterbank = Array2::<f32>::zeros((n_mels, freq_bins));

    let fmax = sample_rate as f64 / 2.0;
    let mel_min = hz_to_mel_slaney(0.0);
    let mel_max = hz_to_mel_slaney(fmax);

    // Mel cent freq
    let mel_points: Vec<f64> = (0..=n_mels + 1)
        .map(|i| mel_to_hz_slaney(mel_min + (mel_max - mel_min) * i as f64 / (n_mels + 1) as f64))
        .collect();

    // FFT bin freq
    let fft_freqs: Vec<f64> = (0..freq_bins)
        .map(|i| i as f64 * sample_rate as f64 / n_fft as f64)
        .collect();

    // librosa's ramp
    let fdiff: Vec<f64> = mel_points.windows(2).map(|w| w[1] - w[0]).collect();

    for i in 0..n_mels {
        for (k, &freq) in fft_freqs.iter().enumerate() {
            let lower = (freq - mel_points[i]) / fdiff[i];
            let upper = (mel_points[i + 2] - freq) / fdiff[i + 1];
            filterbank[[i, k]] = 0.0f64.max(lower.min(upper)) as f32;
        }
    }

    // Slaney norm
    for i in 0..n_mels {
        let enorm = 2.0 / (mel_points[i + 2] - mel_points[i]);
        for k in 0..freq_bins {
            filterbank[[i, k]] *= enorm as f32;
        }
    }

    filterbank
}

/// Extract mel spectrogram features from raw audio samples.
///
/// # Arguments
///
/// * `audio` - Audio samples as f32 values
/// * `sample_rate` - Sample rate in Hz
/// * `channels` - Number of audio channels
/// * `config` - Preprocessor configuration
///
/// # Returns
///
/// 2D array of mel spectrogram features (time_steps x feature_size)
pub fn extract_features_raw(
    mut audio: Vec<f32>,
    sample_rate: u32,
    channels: u16,
    config: &PreprocessorConfig,
) -> Result<Array2<f32>> {
    if sample_rate != config.sampling_rate as u32 {
        return Err(Error::Audio(format!(
            "Audio sample rate {} doesn't match expected {}. Please resample your audio first.",
            sample_rate, config.sampling_rate
        )));
    }

    if channels > 1 {
        let mono: Vec<f32> = audio
            .chunks(channels as usize)
            .map(|chunk| chunk.iter().sum::<f32>() / channels as f32)
            .collect();
        audio = mono;
    }

    // A header-only WAV (tap-and-release dictation) or a sub-hop clip would
    // panic in apply_preemphasis (audio[0]) or produce a single mel frame
    // whose Bessel-corrected normalization divides by zero (all-NaN
    // features). Reject both upfront with a clean error; the diarization
    // path has carried the equivalent guard in sortformer.rs all along.
    if audio.len() < config.hop_length {
        return Err(Error::Audio(format!(
            "Audio too short to transcribe: {} samples (need at least {})",
            audio.len(),
            config.hop_length
        )));
    }

    audio = apply_preemphasis(&audio, config.preemphasis);

    let spectrogram = stft(&audio, config.n_fft, config.hop_length, config.win_length);

    let mel_filterbank =
        create_mel_filterbank(config.n_fft, config.feature_size, config.sampling_rate);
    let mel_spectrogram = mel_filterbank.dot(&spectrogram);
    // Log with additive guard (NeMo: log_zero_guard_type="add", value=2^-24)
    let log_zero_guard: f32 = 2.0f32.powi(-24);
    let mel_spectrogram = mel_spectrogram.mapv(|x| (x + log_zero_guard).ln());

    let mut mel_spectrogram = mel_spectrogram.t().to_owned();

    // Normalize per_feature: mean=0, std=1 with Bessel's correction (N-1)
    let num_frames = mel_spectrogram.shape()[0];
    let num_features = mel_spectrogram.shape()[1];

    for feat_idx in 0..num_features {
        let mut column = mel_spectrogram.column_mut(feat_idx);
        let mean: f32 = column.iter().sum::<f32>() / num_frames as f32;
        let variance: f32 = column.iter().map(|&x| (x - mean).powi(2)).sum::<f32>()
            / (num_frames as f32 - 1.0);
        let std = variance.sqrt() + 1e-5;

        for val in column.iter_mut() {
            *val = (*val - mean) / std;
        }
    }

    Ok(mel_spectrogram)
}

#[cfg(test)]
mod tests {
    use super::*;

    // Regression (audit 2026-07-25): a header-only WAV (tap-and-release
    // dictation) reached apply_preemphasis with an empty slice and panicked
    // on audio[0], killing the single-threaded transcribe daemon. Sub-hop
    // inputs (1..160 samples) yielded a single mel frame whose Bessel
    // normalization divided by zero, feeding all-NaN features to the model.
    // Both must be a clean error, never a panic or NaN.

    #[test]
    fn empty_audio_is_a_clean_error() {
        let cfg = PreprocessorConfig::default();
        let res = extract_features_raw(Vec::new(), cfg.sampling_rate as u32, 1, &cfg);
        assert!(res.is_err(), "empty audio must be rejected, not panic");
    }

    #[test]
    fn sub_hop_audio_is_a_clean_error() {
        let cfg = PreprocessorConfig::default();
        let audio = vec![0.1_f32; 100]; // < hop_length (160) => 1 mel frame
        let res = extract_features_raw(audio, cfg.sampling_rate as u32, 1, &cfg);
        assert!(res.is_err(), "sub-hop audio must be rejected, not NaN");
    }

    #[test]
    fn normal_audio_still_extracts_finite_features() {
        let cfg = PreprocessorConfig::default();
        // 100 ms of a 440 Hz tone at the expected sample rate.
        let sr = cfg.sampling_rate as u32;
        let audio: Vec<f32> = (0..(sr / 10))
            .map(|i| (2.0 * std::f32::consts::PI * 440.0 * i as f32 / sr as f32).sin())
            .collect();
        let feats = extract_features_raw(audio, sr, 1, &cfg).expect("valid audio must pass");
        assert!(feats.shape()[0] > 1);
        assert!(feats.iter().all(|v| v.is_finite()), "features must be finite");
    }
}
