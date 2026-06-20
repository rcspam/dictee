// Warm-RTF bench for ParakeetTDT (mirror of tests/poc-whisper-rs for a fair
// engine comparison). Loads the model once, transcribes the SAME audio
// POC_PASSES times on the resident model. Pass 1 = cold, passes 2+ = warm.
//
// Usage: bench_parakeet <audio.wav> [model_dir]
//   fp32 GPU : bench_parakeet a.wav /usr/share/dictee/tdt
//   int8 CPU : DICTEE_PARAKEET_QUANT=int8 bench_parakeet a.wav /usr/share/dictee/tdt
//
// NOT shipped — dev bench only.

use parakeet_rs::{parakeet_provider, ExecutionConfig, ParakeetTDT, TimestampMode, Transcriber};
use std::env;
use std::time::Instant;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: bench_parakeet <audio.wav> [model_dir]");
        std::process::exit(1);
    }
    let audio_path = &args[1];
    let model_dir = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "/usr/share/dictee/tdt".to_string());
    let passes: usize = env::var("POC_PASSES").ok().and_then(|s| s.parse().ok()).unwrap_or(3);

    // Load audio (expect 16 kHz mono WAV)
    let mut reader = hound::WavReader::open(audio_path)?;
    let spec = reader.spec();
    let audio: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().collect::<Result<Vec<_>, _>>()?,
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.map(|s| s as f32 / 32768.0))
            .collect::<Result<Vec<_>, _>>()?,
    };
    let dur_s = audio.len() as f64 / spec.sample_rate as f64;
    eprintln!("audio: {} ({:.1}s, {} ch, {} Hz)", audio_path, dur_s, spec.channels, spec.sample_rate);

    // Load model (provider picks CPU/GPU; DICTEE_PARAKEET_QUANT picks int8/fp32 file)
    let config = ExecutionConfig::new()
        .with_execution_provider(parakeet_provider(std::path::Path::new(&model_dir)));
    let t = Instant::now();
    let mut parakeet = ParakeetTDT::from_pretrained(&model_dir, Some(config))?;
    eprintln!("model loaded in {:.1}s: {}", t.elapsed().as_secs_f64(), model_dir);

    for p in 1..=passes {
        let a = audio.clone();
        let t = Instant::now();
        let result = parakeet.transcribe_samples(a, spec.sample_rate, spec.channels, Some(TimestampMode::Sentences))?;
        let el = t.elapsed().as_secs_f64();
        let tag = if p == 1 { "cold" } else { "warm" };
        println!("pass {}/{} [{}]: {:.2}s (RTF {:.3})", p, passes, tag, el, el / dur_s);
        if p == passes {
            println!("--- text (last pass) ---\n{}", result.text.trim());
        }
    }
    Ok(())
}
