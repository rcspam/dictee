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

    let model_dir = if args.len() > 1 {
        args[1].clone()
    } else {
        // Try system dir first, fallback to user dir
        let sys_dir = "/usr/share/dictee/tdt";
        let user_dir = format!("{}/.local/share/dictee/tdt",
            std::env::var("HOME").unwrap_or_else(|_| "/root".to_string()));
        if Path::new(sys_dir).join("vocab.txt").exists() {
            sys_dir.to_string()
        } else {
            user_dir
        }
    };

    // Remove existing socket
    if Path::new(&socket_path).exists() {
        fs::remove_file(&socket_path)?;
    }

    // Configure CUDA if available
    #[cfg(feature = "cuda")]
    let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cuda);
    #[cfg(not(feature = "cuda"))]
    let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cpu);

    eprintln!("Loading model from {}...", &model_dir);
    let mut parakeet = ParakeetTDT::from_pretrained(&model_dir, Some(config))?;
    eprintln!("Model loaded. Listening on {}", socket_path);

    let listener = UnixListener::bind(&socket_path)?;

    // Make socket accessible (only current user)
    fs::set_permissions(&socket_path, fs::Permissions::from_mode(0o600))?;

    for stream in listener.incoming() {
        match stream {
            Ok(mut stream) => {
                let reader = BufReader::new(&stream);

                // Read the request: "path.wav\n" or "path.wav\tdiarize\n"
                if let Some(Ok(line)) = reader.lines().next() {
                    let line = line.trim().to_string();
                    let (audio_path, timestamps) = if let Some((path, mode)) = line.split_once('\t') {
                        (path.trim(), mode.trim() == "diarize")
                    } else {
                        (line.as_str(), false)
                    };

                    match transcribe_file(&mut parakeet, audio_path, timestamps) {
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
    timestamps: bool,
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

    if timestamps {
        // Return timestamped sentences for diarization matching
        let lines: Vec<String> = result.tokens.iter()
            .map(|t| format!("[{:.2}s - {:.2}s] {}", t.start, t.end, t.text))
            .collect();
        Ok(lines.join("\n"))
    } else {
        Ok(result.text.trim().to_string())
    }
}

use std::os::unix::fs::PermissionsExt;
