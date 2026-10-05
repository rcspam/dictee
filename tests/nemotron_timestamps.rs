//! Word timestamps of Nemotron 3.5 on a real recording.
//!
//! Marked `#[ignore]`: it loads the ~2.5 GB model, which is not in the repo.
//! Run it with the model directory and a 16 kHz mono speech recording:
//!
//! ```text
//! NEMOTRON_MODEL_DIR=~/.local/share/dictee/nemotron NEMOTRON_TEST_WAV=speech.wav \
//!   cargo test --release --test nemotron_timestamps -- --ignored --nocapture
//! ```

use parakeet_rs::{Nemotron, TimestampMode};

fn read_mono(path: &str) -> Vec<f32> {
    let mut reader = hound::WavReader::open(path).expect("open the test recording");
    let spec = reader.spec();
    assert_eq!(spec.sample_rate, 16_000, "16 kHz expected");
    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().map(|s| s.unwrap()).collect(),
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.unwrap() as f32 / 32768.0)
            .collect(),
    };
    samples
        .chunks(spec.channels as usize)
        .map(|c| c.iter().sum::<f32>() / c.len() as f32)
        .collect()
}

fn words(text: &str) -> Vec<String> {
    text.split_whitespace().map(str::to_lowercase).collect()
}

#[test]
#[ignore = "loads the ~2.5 GB Nemotron 3.5 model (NEMOTRON_MODEL_DIR, NEMOTRON_TEST_WAV)"]
fn words_come_with_their_time_and_the_text_is_unchanged() {
    let model_dir = std::env::var("NEMOTRON_MODEL_DIR").expect("NEMOTRON_MODEL_DIR");
    let audio = read_mono(&std::env::var("NEMOTRON_TEST_WAV").expect("NEMOTRON_TEST_WAV"));
    let duration = audio.len() as f32 / 16_000.0;
    let mut nemotron = Nemotron::from_pretrained(&model_dir, None).expect("load Nemotron");
    let _ = nemotron.set_target_lang("fr-FR");

    let plain = nemotron.transcribe_audio(&audio).expect("transcribe");
    let timed = nemotron
        .transcribe_audio_with_timestamps(&audio, Some(TimestampMode::Words))
        .expect("transcribe with timestamps");
    eprintln!("{} words over {duration:.1} s: {plain}", timed.tokens.len());

    assert_eq!(timed.text, plain, "the text must not change");
    assert!(!timed.tokens.is_empty(), "no word");
    let mut last_start = 0.0;
    for word in &timed.tokens {
        assert!(word.start >= last_start, "words out of order: {word:?}");
        assert!(word.end > word.start && word.end <= duration + 0.2, "{word:?}");
        last_start = word.start;
    }
    // every word of the text is there, in order, timed
    let joined: Vec<String> = timed.tokens.iter().flat_map(|w| words(&w.text)).collect();
    assert_eq!(joined.join(" ").replace(" ,", ",").replace(" .", "."),
               words(&plain).join(" "));
}

/// NEMOTRON_TEST_START: how the recording starts (e.g. "Et moi" for the LeCun
/// passage that used to lose it).
#[test]
#[ignore = "loads the ~2.5 GB Nemotron 3.5 model (NEMOTRON_MODEL_DIR, NEMOTRON_TEST_WAV, NEMOTRON_TEST_START)"]
fn the_first_words_are_kept_offline_and_live() {
    let model_dir = std::env::var("NEMOTRON_MODEL_DIR").expect("NEMOTRON_MODEL_DIR");
    let audio = read_mono(&std::env::var("NEMOTRON_TEST_WAV").expect("NEMOTRON_TEST_WAV"));
    let start = std::env::var("NEMOTRON_TEST_START").expect("NEMOTRON_TEST_START");
    let mut nemotron = Nemotron::from_pretrained(&model_dir, None).expect("load Nemotron");
    let _ = nemotron.set_target_lang("fr-FR");

    let offline = nemotron.transcribe_audio(&audio).expect("transcribe");
    nemotron.reset();
    for piece in audio.chunks(8_000) {
        nemotron.transcribe_chunk(piece).expect("stream");
    }
    nemotron.finalize_transcript().expect("finalize");
    let live = nemotron.get_transcript();
    eprintln!("offline: {offline}\nlive:    {live}");

    assert!(offline.starts_with(&start), "offline lost the start: {offline}");
    assert!(live.starts_with(&start), "live lost the start: {live}");
}
