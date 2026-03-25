use parakeet_rs::{ParakeetTDT, Transcriber, TimestampMode, ExecutionConfig, ExecutionProvider};
use std::env;
use std::fs;
use std::process::{Command, Stdio};

const TEMP_CONVERTED: &str = "/tmp/transcribe_converted.wav";

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();

    if args.iter().any(|a| a == "--help" || a == "-h") {
        eprintln!("transcribe - Transcription vocale (ParakeetTDT, multilingue)");
        eprintln!();
        eprintln!("Usage: transcribe <audio> [model_dir]");
        eprintln!();
        eprintln!("Arguments:");
        eprintln!("  <audio>       Fichier audio (tout format supporté par ffmpeg)");
        eprintln!("  [model_dir]   Répertoire du modèle TDT (défaut: /usr/share/dictee/tdt)");
        return Ok(());
    }

    if args.len() < 2 {
        eprintln!("Usage: transcribe <audio> [model_dir]");
        eprintln!("  audio:     Audio file (any format supported by ffmpeg)");
        eprintln!("  model_dir: Path to TDT model directory (default: /usr/share/dictee/tdt)");
        std::process::exit(1);
    }

    let audio_path = resolve_path(&args[1])?;
    let model_dir = if args.len() > 2 {
        args[2].clone()
    } else {
        let sys_dir = "/usr/share/dictee/tdt";
        let user_dir = format!("{}/.local/share/dictee/tdt",
            std::env::var("HOME").unwrap_or_else(|_| "/root".to_string()));
        if std::path::Path::new(sys_dir).join("vocab.txt").exists() {
            sys_dir.to_string()
        } else {
            user_dir
        }
    };

    // Convert to WAV 16kHz mono if needed
    let (wav_path, needs_cleanup) = ensure_wav(&audio_path)?;

    // Load audio
    let mut reader = hound::WavReader::open(&wav_path)?;
    let spec = reader.spec();

    let audio: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().collect::<Result<Vec<_>, _>>()?,
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.map(|s| s as f32 / 32768.0))
            .collect::<Result<Vec<_>, _>>()?,
    };

    if needs_cleanup {
        let _ = fs::remove_file(&wav_path);
    }

    // Configure execution provider
    #[cfg(feature = "cuda")]
    let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cuda);
    #[cfg(not(feature = "cuda"))]
    let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cpu);

    // Load TDT model (multilingual, supports French)
    let mut parakeet = ParakeetTDT::from_pretrained(model_dir, Some(config))?;

    // Transcribe
    let result = parakeet.transcribe_samples(
        audio,
        spec.sample_rate,
        spec.channels,
        Some(TimestampMode::Sentences),
    )?;

    // Output text only
    println!("{}", result.text.trim());

    Ok(())
}

/// Resolve ~/..., ./..., ../... to absolute path
fn resolve_path(path: &str) -> Result<String, Box<dyn std::error::Error>> {
    let expanded = if let Some(rest) = path.strip_prefix("~/") {
        let home = env::var("HOME").map_err(|_| "HOME not set")?;
        format!("{}/{}", home, rest)
    } else {
        path.to_string()
    };
    let canonical = fs::canonicalize(&expanded)
        .map_err(|e| format!("{}: {}", expanded, e))?;
    Ok(canonical.to_string_lossy().into_owned())
}

/// Check if file is already WAV 16kHz mono
fn is_wav_16k_mono(path: &str) -> bool {
    let Ok(reader) = hound::WavReader::open(path) else { return false };
    let spec = reader.spec();
    spec.sample_rate == 16000 && spec.channels == 1
}

/// Convert audio to WAV 16kHz mono via ffmpeg if needed.
/// Returns (wav_path, needs_cleanup).
fn ensure_wav(audio_path: &str) -> Result<(String, bool), Box<dyn std::error::Error>> {
    if is_wav_16k_mono(audio_path) {
        return Ok((audio_path.to_string(), false));
    }

    let status = Command::new("ffmpeg")
        .args(["-y", "-i", audio_path, "-ar", "16000", "-ac", "1", "-f", "wav", TEMP_CONVERTED])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|e| format!("ffmpeg not found: {}. Install ffmpeg to convert audio files.", e))?;

    if !status.success() {
        return Err(format!("ffmpeg failed to convert '{}' (exit code: {:?})", audio_path, status.code()).into());
    }

    Ok((TEMP_CONVERTED.to_string(), true))
}
