use parakeet_rs::{
    Canary, ExecutionConfig, ExecutionProvider, ParakeetTDT, TimestampMode, Transcriber,
    TranscriptionResult,
};
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixListener;
use std::path::Path;

macro_rules! dbg_print {
    ($debug:expr, $($arg:tt)*) => {
        if $debug { eprintln!($($arg)*); }
    };
}

/// User-specific socket path using XDG_RUNTIME_DIR or /tmp fallback.
fn socket_path() -> String {
    if let Ok(dir) = env::var("XDG_RUNTIME_DIR") {
        format!("{}/transcribe.sock", dir)
    } else {
        format!("/tmp/transcribe-{}.sock", unsafe { libc::getuid() })
    }
}

/// Unified ASR backend: Parakeet TDT or Canary AED
enum AsrBackend {
    Parakeet(ParakeetTDT),
    Canary(Canary),
}

impl AsrBackend {
    fn transcribe_samples(
        &mut self,
        audio: Vec<f32>,
        sample_rate: u32,
        channels: u16,
        mode: Option<TimestampMode>,
    ) -> parakeet_rs::Result<TranscriptionResult> {
        match self {
            AsrBackend::Parakeet(p) => p.transcribe_samples(audio, sample_rate, channels, mode),
            AsrBackend::Canary(c) => c.transcribe_samples(audio, sample_rate, channels, mode),
        }
    }

    /// Set decoder context for next transcription (Canary only, no-op for Parakeet)
    fn set_context(&mut self, text: &str) {
        if let AsrBackend::Canary(c) = self {
            let _ = c.set_context_text(text);
        }
    }

    /// Check if decoder context is set (Canary: last_token_ids present)
    fn has_context(&self) -> bool {
        match self {
            AsrBackend::Canary(c) => c.last_token_ids().is_some(),
            AsrBackend::Parakeet(_) => false,
        }
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let debug = env::var("DICTEE_DEBUG").unwrap_or_default() == "true";
    let socket_path = socket_path();
    let args: Vec<String> = env::args().collect();

    if args.iter().any(|a| a == "--help" || a == "-h") {
        eprintln!("transcribe-daemon - ASR daemon via Unix socket (Parakeet TDT / Canary AED)");
        eprintln!();
        eprintln!("Usage: transcribe-daemon [model_dir] [--canary]");
        eprintln!();
        eprintln!("Arguments:");
        eprintln!("  [model_dir]   Model directory (default: /usr/share/dictee/tdt or /canary)");
        eprintln!("  --canary      Use Canary AED backend instead of Parakeet TDT");
        eprintln!();
        eprintln!("Environment:");
        eprintln!("  DICTEE_ASR_BACKEND=canary    Select Canary backend");
        eprintln!("  DICTEE_LANG_SOURCE=fr        Source language (default: fr)");
        eprintln!("  DICTEE_LANG_TARGET=fr        Target language (default: source)");
        eprintln!();
        eprintln!("Socket protocol:");
        eprintln!("  path.wav                         → transcription");
        eprintln!("  path.wav\\ttimestamps              → word-level timestamps");
        eprintln!("  path.wav\\tcontext:previous text   → with decoder context (Canary)");
        eprintln!();
        eprintln!("Listening on {}", socket_path);
        return Ok(());
    }

    // Detect backend
    let use_canary = env::var("DICTEE_ASR_BACKEND")
        .map(|v| v == "canary")
        .unwrap_or(false)
        || args.iter().any(|a| a == "--canary");

    let source_lang = env::var("DICTEE_LANG_SOURCE").unwrap_or_else(|_| "fr".to_string());
    // For Canary: default target = source (transcription, not translation).
    // Translation is requested per-request via the socket protocol (lang:XX).
    // DICTEE_LANG_TARGET from dictee.conf is for external translation backends, not Canary.
    let target_lang = if use_canary {
        source_lang.clone()
    } else {
        env::var("DICTEE_LANG_TARGET").unwrap_or_else(|_| source_lang.clone())
    };

    // Find model directory
    let model_dir = args
        .iter()
        .skip(1)
        .find(|a| !a.starts_with("--"))
        .cloned()
        .unwrap_or_else(|| {
            let subdir = if use_canary { "canary" } else { "tdt" };
            let sys_dir = format!("/usr/share/dictee/{}", subdir);
            let user_dir = format!(
                "{}/.local/share/dictee/{}",
                env::var("HOME").unwrap_or_else(|_| "/root".to_string()),
                subdir
            );
            if Path::new(&sys_dir).join("vocab.txt").exists() {
                sys_dir
            } else {
                user_dir
            }
        });

    // Remove existing socket
    if Path::new(&socket_path).exists() {
        fs::remove_file(&socket_path)?;
    }

    // Configure execution provider
    #[cfg(feature = "cuda")]
    let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cuda);
    #[cfg(not(feature = "cuda"))]
    let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cpu);

    eprintln!(
        "Loading {} model from {}...",
        if use_canary { "Canary AED" } else { "Parakeet TDT" },
        &model_dir
    );

    let mut backend = if use_canary {
        AsrBackend::Canary(Canary::from_pretrained(
            &model_dir,
            Some(config),
            &source_lang,
            &target_lang,
        )?)
    } else {
        AsrBackend::Parakeet(ParakeetTDT::from_pretrained(&model_dir, Some(config))?)
    };

    eprintln!("Model loaded. Listening on {}", socket_path);

    let listener = UnixListener::bind(&socket_path)?;
    fs::set_permissions(&socket_path, fs::Permissions::from_mode(0o600))?;

    for stream in listener.incoming() {
        match stream {
            Ok(mut stream) => {
                let reader = BufReader::new(&stream);
                if let Some(Ok(line)) = reader.lines().next() {
                    let line = line.trim().to_string();
                    let (audio_path, mode_str, context) = parse_request(&line);
                    dbg_print!(debug, "[daemon] request: path={} mode={} context={}", audio_path, mode_str, context.is_some());

                    // Set decoder context if provided (Canary decodercontext)
                    if let Some(ctx) = context {
                        backend.set_context(&ctx);
                    }

                    let has_ctx = backend.has_context();
                    dbg_print!(debug, "[daemon] has_context={}", has_ctx);

                    match transcribe_file(&mut backend, audio_path, mode_str) {
                        Ok(text) => {
                            dbg_print!(debug, "[daemon] result: {} chars", text.len());
                            let _ = writeln!(stream, "{}", text);
                        }
                        Err(e) => {
                            eprintln!("[daemon] error: {}", e);
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

/// Parse request line:
///   path.wav
///   path.wav\ttimestamps
///   path.wav\tdiarize
///   path.wav\tcontext:previous transcription text
///   path.wav\ttimestamps\tcontext:previous text
fn parse_request(line: &str) -> (&str, &str, Option<String>) {
    let parts: Vec<&str> = line.splitn(3, '\t').collect();
    let path = parts[0].trim();
    let mut mode = "plain";
    let mut context = None;

    for &part in parts.iter().skip(1) {
        let part = part.trim();
        if let Some(ctx) = part.strip_prefix("context:") {
            context = Some(ctx.to_string());
        } else if part == "timestamps" || part == "diarize" {
            mode = part;
        }
    }

    (path, mode, context)
}

fn transcribe_file(
    backend: &mut AsrBackend,
    audio_path: &str,
    mode: &str,
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

    let ts_mode = match mode {
        "timestamps" => TimestampMode::Words,
        "diarize" => TimestampMode::Sentences,
        _ => TimestampMode::Sentences,
    };

    let result =
        backend.transcribe_samples(audio, spec.sample_rate, spec.channels, Some(ts_mode))?;

    match mode {
        "diarize" | "timestamps" => {
            let lines: Vec<String> = result
                .tokens
                .iter()
                .map(|t| format!("[{:.2}s - {:.2}s] {}", t.start, t.end, t.text))
                .collect();
            Ok(lines.join("\n"))
        }
        _ => Ok(result.text.trim().to_string()),
    }
}
