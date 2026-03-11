use parakeet_rs::{ExecutionConfig, ExecutionProvider, ParakeetTDT, TimestampMode, Transcriber};
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixListener;
use std::path::Path;

/// Retourne le chemin du socket par utilisateur.
/// Utilise $XDG_RUNTIME_DIR/transcribe.sock (par défaut /run/user/UID/),
/// ou /tmp/transcribe-UID.sock en fallback.
fn socket_path() -> String {
    if let Ok(dir) = env::var("XDG_RUNTIME_DIR") {
        format!("{}/transcribe.sock", dir)
    } else {
        format!("/tmp/transcribe-{}.sock", unsafe { libc::getuid() })
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let socket_path = socket_path();
    let args: Vec<String> = env::args().collect();

    if args.iter().any(|a| a == "--help" || a == "-h") {
        eprintln!("transcribe-daemon - Serveur de transcription via socket Unix");
        eprintln!();
        eprintln!("Usage: transcribe-daemon [model_dir]");
        eprintln!();
        eprintln!("Arguments:");
        eprintln!("  [model_dir]   Répertoire du modèle TDT (défaut: /usr/share/dictee/tdt)");
        eprintln!();
        eprintln!("Écoute sur {}. Utiliser avec transcribe-client.", socket_path);
        return Ok(());
    }

    let model_dir = if args.len() > 1 { &args[1] } else { "/usr/share/dictee/tdt" };

    // Remove existing socket
    if Path::new(&socket_path).exists() {
        fs::remove_file(&socket_path)?;
    }

    // Configure CUDA if available
    #[cfg(feature = "cuda")]
    let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cuda);
    #[cfg(not(feature = "cuda"))]
    let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cpu);

    eprintln!("Loading model from {}...", model_dir);
    let mut parakeet = ParakeetTDT::from_pretrained(model_dir, Some(config))?;
    eprintln!("Model loaded. Listening on {}", socket_path);

    let listener = UnixListener::bind(&socket_path)?;

    // Make socket accessible (only current user)
    fs::set_permissions(&socket_path, fs::Permissions::from_mode(0o600))?;

    for stream in listener.incoming() {
        match stream {
            Ok(mut stream) => {
                let reader = BufReader::new(&stream);

                // Read the audio file path from client
                if let Some(Ok(audio_path)) = reader.lines().next() {
                    let audio_path = audio_path.trim();

                    match transcribe_file(&mut parakeet, audio_path) {
                        Ok(text) => {
                            let _ = writeln!(stream, "{}", text);
                        }
                        Err(e) => {
                            let _ = writeln!(stream, "ERROR: {}", e);
                        }
                    }
                }
            }
            Err(e) => {
                eprintln!("Connection error: {}", e);
            }
        }
    }

    Ok(())
}

fn transcribe_file(
    parakeet: &mut ParakeetTDT,
    audio_path: &str,
) -> Result<String, Box<dyn std::error::Error>> {
    let mut reader = hound::WavReader::open(audio_path)?;
    let spec = reader.spec();

    let audio: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().collect::<Result<Vec<_>, _>>()?,
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.map(|s| s as f32 / 32768.0))
            .collect::<Result<Vec<_>, _>>()?,
    };

    let result = parakeet.transcribe_samples(
        audio,
        spec.sample_rate,
        spec.channels,
        Some(TimestampMode::Sentences),
    )?;

    Ok(result.text.trim().to_string())
}

use std::os::unix::fs::PermissionsExt;
