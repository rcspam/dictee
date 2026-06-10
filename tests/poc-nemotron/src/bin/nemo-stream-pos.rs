// Option α: stream a WAV file through Nemotron in 560 ms chunks and emit,
// per chunk, "<start_s> <end_s>\t<text>" — i.e. the streaming text WITH its
// approximate temporal position. A separate script then assigns each chunk to
// the dominant Sortformer speaker on that time window (alignment by position,
// since Nemotron has no word timestamps).
//
// Usage: nemo-stream-pos <lang|auto> <audio-16k-mono.wav>
// Env: NEMO_CUDA=1 for GPU, NEMO_MODEL_DIR to override ./nemotron_multi.

use parakeet_rs::{ExecutionConfig, ExecutionProvider, Nemotron, NemotronMode};
use std::env;

const CHUNK: usize = 8960; // 560 ms @ 16 kHz (Nemotron streaming chunk)
const SR: f32 = 16000.0;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let lang = env::args().nth(1).unwrap_or_else(|| "fr-FR".to_string());
    let wav = env::args().nth(2).ok_or("usage: nemo-stream-pos <lang|auto> <audio-16k-mono.wav>")?;
    let model_dir = env::var("NEMO_MODEL_DIR").unwrap_or_else(|_| "./nemotron_multi".to_string());

    // Read WAV (expect 16 kHz mono, PCM16 or float).
    let mut reader = hound::WavReader::open(&wav)?;
    let spec = reader.spec();
    if spec.sample_rate != 16000 || spec.channels != 1 {
        return Err(format!("expected 16kHz mono, got {} Hz / {} ch", spec.sample_rate, spec.channels).into());
    }
    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.unwrap_or(0) as f32 / 32768.0)
            .collect(),
        hound::SampleFormat::Float => reader.samples::<f32>().map(|s| s.unwrap_or(0.0)).collect(),
    };

    let cfg = if env::var("NEMO_CUDA").map(|v| v == "1").unwrap_or(false) {
        eprintln!("[nemo] provider: CUDA");
        Some(ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cuda))
    } else {
        eprintln!("[nemo] provider: CPU");
        None
    };
    let mut model = Nemotron::from_pretrained(&model_dir, cfg)?;
    if let NemotronMode::Multilingual = model.mode() {
        if lang != "auto" {
            model.set_target_lang(&lang)?;
        }
    }

    // Stream chunk by chunk; emit text with the chunk's time window.
    let mut i = 0usize;
    let mut idx = 0usize;
    while i < samples.len() {
        let end = (i + CHUNK).min(samples.len());
        let mut chunk = samples[i..end].to_vec();
        if chunk.len() < CHUNK {
            chunk.resize(CHUNK, 0.0);
        }
        let text = model.transcribe_chunk(&chunk)?;
        let start_s = idx as f32 * CHUNK as f32 / SR;
        let end_s = (idx + 1) as f32 * CHUNK as f32 / SR;
        // Keep the chunk's raw text (incl. leading SentencePiece spaces) so the
        // orchestrator can concatenate chunks WITHOUT inserting extra spaces.
        // Only drop newlines (they'd break the line format).
        let t = text.replace('\n', "");
        if !t.trim().is_empty() {
            println!("{:.2} {:.2}\t{}", start_s, end_s, t);
        }
        i += CHUNK;
        idx += 1;
    }
    Ok(())
}
