// Live mic streaming with Nemotron 3.5 multilingual.
// Captures the microphone via pw-record (16 kHz mono s16) and feeds 560 ms
// chunks to Nemotron's streaming transcriber, printing text as you speak.
//
// Usage (run from tests/poc-nemotron/, where ./nemotron_multi lives):
//   ./target/release/nemo-mic [lang]
//     lang: "fr-FR" (default), "fr", "auto", "en-US", …
// Stop with Ctrl+C.

use parakeet_rs::{Nemotron, NemotronMode};
use std::env;
use std::io::{Read, Write};
use std::process::{Command, Stdio};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let lang = env::args().nth(1).unwrap_or_else(|| "fr-FR".to_string());
    let model_dir = env::var("NEMO_MODEL_DIR").unwrap_or_else(|_| "./nemotron_multi".to_string());

    eprintln!("Loading Nemotron from {model_dir} …");
    let mut model = Nemotron::from_pretrained(&model_dir, None)?;
    match model.mode() {
        NemotronMode::Multilingual => {
            if lang != "auto" {
                model.set_target_lang(&lang)?;
                eprintln!("Language forced: {lang}");
            } else {
                eprintln!("Language: auto-detect");
            }
        }
        NemotronMode::EnglishOnly => eprintln!("English-only model (lang ignored)"),
    }
    eprintln!("Ready — speak into the mic. Ctrl+C to stop.\n----------------------------------------");

    // Capture the default mic: 16 kHz mono signed-16 PCM on stdout.
    let mut child = Command::new("pw-record")
        .args(["--format=s16", "--rate=16000", "--channels=1", "-"])
        .stdout(Stdio::piped())
        .spawn()
        .map_err(|e| format!("pw-record failed to start: {e}"))?;
    let mut audio = child.stdout.take().ok_or("no pw-record stdout")?;

    let chunk_samples = 8960usize; // 560 ms @ 16 kHz (Nemotron streaming chunk)
    let mut bytes = vec![0u8; chunk_samples * 2]; // s16 = 2 bytes/sample
    let stdout = std::io::stdout();

    loop {
        // Read exactly one 560 ms chunk.
        let mut filled = 0;
        while filled < bytes.len() {
            match audio.read(&mut bytes[filled..])? {
                0 => {
                    // pw-record ended: flush and print final transcript.
                    let _ = child.wait();
                    println!("\n----------------------------------------\nFinal: {}", model.get_transcript());
                    return Ok(());
                }
                n => filled += n,
            }
        }
        let samples: Vec<f32> = bytes
            .chunks_exact(2)
            .map(|b| i16::from_le_bytes([b[0], b[1]]) as f32 / 32768.0)
            .collect();
        let text = model.transcribe_chunk(&samples)?;
        if !text.is_empty() {
            print!("{text}");
            let _ = stdout.lock().flush();
        }
    }
}
