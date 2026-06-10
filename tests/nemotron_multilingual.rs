//! Integration test for the multilingual Nemotron 3.5 engine.
//!
//! Marked `#[ignore]` because it loads a ~2.5 GB model that is not shipped in
//! the repo (see `tests/poc-nemotron/.gitignore`). Run it explicitly with:
//!
//! ```text
//! cargo test --release --test nemotron_multilingual -- --ignored --nocapture
//! ```
//!
//! Prerequisites (both gitignored, fetched/recorded locally):
//! - `tests/poc-nemotron/nemotron_multi/` : encoder.onnx + encoder.onnx.data
//!   + decoder_joint.onnx + tokenizer.model
//! - `tests/poc-nemotron/ref-fr.wav`      : 16 kHz mono reference clip
//!
//! The published parakeet-rs 0.3.6 POC transcribes the reference clip to
//! exactly: "Bonjour, ceci est un test de transcription automatique en
//! français." This test asserts the French text is reproduced.

use parakeet_rs::{Nemotron, NemotronMode};
use std::path::PathBuf;

fn poc_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/poc-nemotron")
}

/// Read a 16 kHz mono WAV (i16 or f32) into a `Vec<f32>` in [-1, 1].
fn read_wav_f32(path: &std::path::Path) -> Vec<f32> {
    let mut reader = hound::WavReader::open(path).expect("open ref-fr.wav");
    let spec = reader.spec();
    let mut samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader
            .samples::<f32>()
            .map(|s| s.expect("read f32 sample"))
            .collect(),
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.expect("read i16 sample") as f32 / 32768.0)
            .collect(),
    };
    if spec.channels > 1 {
        samples = samples
            .chunks(spec.channels as usize)
            .map(|c| c.iter().sum::<f32>() / spec.channels as f32)
            .collect();
    }
    samples
}

#[test]
#[ignore = "loads ~2.5 GB local model (tests/poc-nemotron/nemotron_multi)"]
fn multilingual_french_transcription() {
    let model_dir = poc_dir().join("nemotron_multi");
    let wav_path = poc_dir().join("ref-fr.wav");

    assert!(
        model_dir.join("encoder.onnx").exists(),
        "missing model at {} — see tests/poc-nemotron/.gitignore",
        model_dir.display()
    );
    assert!(wav_path.exists(), "missing {}", wav_path.display());

    // CPU load (None => default execution config). Provider selection is the
    // daemon's job, not the engine's.
    let mut nemotron =
        Nemotron::from_pretrained(&model_dir, None).expect("load multilingual Nemotron");

    // The encoder graph exposes `prompt_index` => Multilingual.
    assert_eq!(
        nemotron.mode(),
        NemotronMode::Multilingual,
        "model did not detect as Multilingual (prompt_index input missing?)"
    );

    // Pick French explicitly (more accurate than 'auto').
    nemotron
        .set_target_lang("fr-FR")
        .expect("set_target_lang fr-FR");

    let samples = read_wav_f32(&wav_path);
    assert!(!samples.is_empty(), "empty audio");

    let text = nemotron.transcribe_audio(&samples).expect("transcribe");
    eprintln!("FR transcription: {text:?}");

    assert!(
        text.contains("transcription automatique"),
        "unexpected transcription: {text:?}"
    );
}

#[test]
#[ignore = "loads ~2.5 GB local model (tests/poc-nemotron/nemotron_multi)"]
fn set_target_lang_rejects_unknown() {
    let model_dir = poc_dir().join("nemotron_multi");
    let mut nemotron =
        Nemotron::from_pretrained(&model_dir, None).expect("load multilingual Nemotron");
    assert!(nemotron.set_target_lang("xx-XX").is_err());
    assert!(nemotron.set_target_lang("fr").is_ok());
    assert!(!nemotron.available_languages().is_empty());
}
