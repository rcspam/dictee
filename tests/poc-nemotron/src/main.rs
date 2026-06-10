// POC: Nemotron 3.5 multilingual (ONNX) via parakeet-rs.
// Loads the model ONCE, transcribes one or more 16 kHz mono WAVs.
//
// Usage: nemo-fr <lang|auto> <wav1> [wav2 ...]
//   lang: "auto" (no prompt) or e.g. "fr-FR" / "fr".
//   Prints ONE line per input WAV on stdout (its transcription).
//   Diagnostics go to stderr.
//
// Model dir: $NEMO_MODEL_DIR or ./nemotron_multi.

use parakeet_rs::{Nemotron, NemotronMode};
use std::env;
use std::time::Instant;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        return Err("usage: nemo-fr <lang|auto> <wav1> [wav2 ...]".into());
    }
    let lang = args[1].clone();
    let wavs = &args[2..];
    let model_dir = env::var("NEMO_MODEL_DIR").unwrap_or_else(|_| "./nemotron_multi".to_string());

    let t0 = Instant::now();
    let mut model = Nemotron::from_pretrained(&model_dir, None)?;
    eprintln!("[nemo] loaded in {:.1}s, mode={:?}", t0.elapsed().as_secs_f32(), model.mode());

    if let NemotronMode::Multilingual = model.mode() {
        if lang != "auto" {
            model.set_target_lang(&lang)?;
            eprintln!("[nemo] lang forced: {lang}");
        } else {
            eprintln!("[nemo] lang: auto-detect");
        }
    }

    for wav in wavs {
        // transcribe_file() resets state internally, so each clip is independent.
        let text = model.transcribe_file(wav).unwrap_or_default();
        println!("{}", text.trim().replace('\n', " "));
    }
    Ok(())
}
