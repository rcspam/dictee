//! Compares `parakeet_rs::nemotron3_diar` with its numpy reference on a real recording.
//!
//! Ignored by default: it needs the model (~400 MB) and reference outputs that are not in the
//! repo. Produce the references with `tests/nemotron3-ref/reference.py dump` (see its docstring),
//! then:
//!
//! ```text
//! NEMOTRON3_MODEL=/path/to/model.onnx NEMOTRON3_REF=/path/to/ref_dir \
//! NEMOTRON3_AUDIO=/path/to/004c_PAPH.wav ORT_DYLIB_PATH=/usr/lib/dictee/libonnxruntime.so \
//! cargo test --release --no-default-features --features "cuda,load-dynamic" \
//!     --test nemotron3_golden -- --ignored --nocapture --test-threads 1
//! ```
//!
//! Both sides run on the CPU. Set NEMOTRON3_OUT to a directory to get the RTTM of the whole file,
//! for a DER with dscore.

use parakeet_rs::nemotron3_diar::{log_mel_features, Nemotron3Diarizer, NUM_SPEAKERS};
use parakeet_rs::{ExecutionConfig, ExecutionProvider};
use std::path::PathBuf;

const EXCERPT_SECONDS: usize = 65;

fn env_path(name: &str) -> PathBuf {
    PathBuf::from(std::env::var(name).unwrap_or_else(|_| panic!("{name} is not set")))
}

fn read_wav(path: &PathBuf) -> Vec<f32> {
    let mut reader = hound::WavReader::open(path).expect("open the recording");
    let spec = reader.spec();
    assert_eq!(
        (spec.sample_rate, spec.channels),
        (16_000, 1),
        "16 kHz mono expected"
    );
    match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().map(|s| s.unwrap()).collect(),
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.unwrap() as f32 / 32768.0)
            .collect(),
    }
}

/// Raw little-endian float32 rows written by the reference.
fn read_f32(path: PathBuf, columns: usize) -> Vec<Vec<f32>> {
    let bytes = std::fs::read(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    let values: Vec<f32> = bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .collect();
    values
        .chunks_exact(columns)
        .map(|row| row.to_vec())
        .collect()
}

/// Largest absolute difference over the first `rows` rows.
fn max_abs_diff(ours: &ndarray::Array2<f32>, reference: &[Vec<f32>], rows: usize) -> f32 {
    (0..rows)
        .flat_map(|r| (0..ours.ncols()).map(move |c| (r, c)))
        .map(|(r, c)| (ours[[r, c]] - reference[r][c]).abs())
        .fold(0.0, f32::max)
}

fn diarizer() -> Nemotron3Diarizer {
    let cpu = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cpu);
    Nemotron3Diarizer::with_config(env_path("NEMOTRON3_MODEL"), Some(cpu), 0.5)
        .expect("load the model")
}

fn stem() -> String {
    env_path("NEMOTRON3_AUDIO")
        .file_stem()
        .unwrap()
        .to_string_lossy()
        .into_owned()
}

#[test]
#[ignore]
fn features_match_the_reference() {
    let audio = read_wav(&env_path("NEMOTRON3_AUDIO"));
    let excerpt = &audio[..EXCERPT_SECONDS * 16_000];
    let (features, valid) = log_mel_features(excerpt);
    let reference = read_f32(
        env_path("NEMOTRON3_REF").join(format!("{}.excerpt.mel.f32", stem())),
        128,
    );
    assert_eq!(features.nrows(), reference.len());
    let diff = max_abs_diff(&features, &reference, valid);
    println!(
        "log-mel: {} frames, max |diff| {diff:.2e}",
        features.nrows()
    );
    // measured 5e-5 on the first run (2026-10-03)
    assert!(
        diff < 2e-4,
        "log-mel features drift from the reference: {diff}"
    );
}

/// Probabilities of `audio` against the reference `name`: largest difference, and how many
/// (frame, speaker) activity decisions at 0.5 differ.
fn compare_probs(audio: &[f32], name: &str) -> (f32, usize, usize) {
    let mut diarizer = diarizer();
    let start = std::time::Instant::now();
    let probs = diarizer.speaker_probs(audio).expect("diarize");
    let elapsed = start.elapsed().as_secs_f32();
    let reference = read_f32(
        env_path("NEMOTRON3_REF").join(format!("{name}.probs.f32")),
        NUM_SPEAKERS,
    );
    assert_eq!(probs.nrows(), reference.len());
    let valid = audio.len() / 160;
    let diff = max_abs_diff(&probs, &reference, valid);
    let flips = (0..valid)
        .flat_map(|r| (0..NUM_SPEAKERS).map(move |c| (r, c)))
        .filter(|&(r, c)| (probs[[r, c]] > 0.5) != (reference[r][c] > 0.5))
        .count();
    println!(
        "{name}: {:.1} s of audio in {elapsed:.1} s, max |diff| {diff:.2e}, {flips} of {} decisions differ",
        audio.len() as f32 / 16_000.0,
        valid * NUM_SPEAKERS
    );
    (diff, flips, valid * NUM_SPEAKERS)
}

#[test]
#[ignore]
fn probabilities_match_the_reference_on_an_excerpt() {
    let audio = read_wav(&env_path("NEMOTRON3_AUDIO"));
    let (diff, flips, _) = compare_probs(
        &audio[..EXCERPT_SECONDS * 16_000],
        &format!("{}.excerpt", stem()),
    );
    // measured 4.5e-6 and no differing decision on the first run (2026-10-03)
    assert!(
        diff < 1e-4,
        "probabilities drift from the reference: {diff}"
    );
    assert_eq!(flips, 0, "activity decisions differ");
}

#[test]
#[ignore]
fn the_whole_recording_matches_the_reference() {
    let audio = read_wav(&env_path("NEMOTRON3_AUDIO"));
    let (_, flips, decisions) = compare_probs(&audio, &stem());
    // none differed on the first run (2026-10-03); a few may on another CPU, after 21 minutes
    assert!(
        flips * 100_000 <= decisions,
        "{flips} of {decisions} activity decisions differ"
    );

    if let Ok(out) = std::env::var("NEMOTRON3_OUT") {
        let segments = diarizer().diarize(audio, 16_000, 1).expect("diarize");
        let rttm: String = segments
            .iter()
            .map(|g| {
                format!(
                    "SPEAKER {} 1 {:.3} {:.3} <NA> <NA> spk{} <NA> <NA>\n",
                    stem(),
                    g.start,
                    g.end - g.start,
                    g.speaker_id
                )
            })
            .collect();
        let path = PathBuf::from(out).join(format!("{}.rttm", stem()));
        std::fs::write(&path, rttm).unwrap();
        println!("RTTM: {}", path.display());
    }
}
