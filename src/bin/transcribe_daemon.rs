use parakeet_rs::{
    best_provider, provider_status, Canary, ExecutionConfig, ExecutionProvider, ParakeetTDT,
    TimestampMode, Transcriber, TranscriptionResult,
};
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixListener;
use std::path::Path;
use std::time::Duration;

macro_rules! dbg_print {
    ($debug:expr, $($arg:tt)*) => {
        if $debug { eprintln!($($arg)*); }
    };
}

/// User-specific socket path. Priority:
///   1. $DICTEE_TRANSCRIBE_SOCKET (used by dictee-setup wizard tests)
///   2. $XDG_RUNTIME_DIR/transcribe.sock
///   3. /tmp/transcribe-<uid>.sock fallback
fn socket_path() -> String {
    if let Ok(p) = env::var("DICTEE_TRANSCRIBE_SOCKET") {
        return p;
    }
    if let Ok(dir) = env::var("XDG_RUNTIME_DIR") {
        format!("{}/transcribe.sock", dir)
    } else {
        format!("/tmp/transcribe-{}.sock", unsafe { libc::getuid() })
    }
}

/// Parsed command-line arguments for transcribe-daemon.
#[derive(Debug, Default)]
struct DaemonArgs {
    help: bool,
    canary: bool,
    #[cfg(feature = "whisper")]
    whisper: bool,
    /// Explicit socket path (`--socket <path>`); overrides socket_path().
    socket: Option<String>,
    /// Optional positional model directory.
    model_dir: Option<String>,
}

/// Parse argv into [`DaemonArgs`], rejecting unknown options loudly.
///
/// Replaces the previous ad-hoc parsing (windows()-based --socket extraction +
/// `find(|a| !a.starts_with("--"))` for the model dir), which silently ignored
/// unrecognised flags. This keeps options and the single positional model dir
/// distinct and errors on anything it does not recognise.
fn parse_daemon_args(args: &[String]) -> Result<DaemonArgs, String> {
    let mut out = DaemonArgs::default();
    let mut i = 1; // skip argv[0]
    while i < args.len() {
        match args[i].as_str() {
            "--help" | "-h" => out.help = true,
            "--canary" => out.canary = true,
            #[cfg(feature = "whisper")]
            "--whisper" => out.whisper = true,
            "--socket" => {
                let path = args
                    .get(i + 1)
                    .ok_or_else(|| "--socket requires a path argument".to_string())?;
                out.socket = Some(path.clone());
                i += 1;
            }
            s if s.starts_with('-') => {
                return Err(format!("unknown option '{}'", s));
            }
            s => {
                if out.model_dir.is_some() {
                    return Err(format!("unexpected extra argument '{}'", s));
                }
                out.model_dir = Some(s.to_string());
            }
        }
        i += 1;
    }
    Ok(out)
}

/// Unified ASR backend: Parakeet TDT, Canary AED, or Whisper (GPU-only)
enum AsrBackend {
    Parakeet(ParakeetTDT),
    Canary(Canary),
    #[cfg(feature = "whisper")]
    Whisper(parakeet_rs::whisper::WhisperBackend),
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
            #[cfg(feature = "whisper")]
            AsrBackend::Whisper(w) => w.transcribe_samples(audio, sample_rate, channels, mode),
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
            #[cfg(feature = "whisper")]
            AsrBackend::Whisper(_) => false,
        }
    }
}

/// True si le modèle Parakeet qui SERA chargé depuis `model_dir` est int8.
/// Reproduit l'ordre de `ParakeetTDTModel::find_encoder` (master) : si
/// `prefers_int8` (DICTEE_PARAKEET_QUANT=int8), l'int8 est prioritaire (chargé
/// dès qu'il existe) ; sinon le FP32 gagne et l'int8 n'est retenu que s'il est
/// seul. `prefers_int8` passé en paramètre = helper pur, testable. À garder
/// synchrone avec find_encoder.
fn parakeet_resolves_to_int8(model_dir: &Path, prefers_int8: bool) -> bool {
    if !model_dir.join("encoder-model.int8.onnx").exists() {
        return false;
    }
    prefers_int8
        || (!model_dir.join("encoder-model.onnx").exists()
            && !model_dir.join("encoder.onnx").exists())
}

#[cfg(test)]
mod tests {
    use super::parakeet_resolves_to_int8;
    use std::fs;
    use std::path::PathBuf;

    fn tmp(tag: &str) -> PathBuf {
        let d = std::env::temp_dir()
            .join(format!("dictee_int8m_test_{}_{}", std::process::id(), tag));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn int8_only_is_int8() {
        let d = tmp("only_int8");
        fs::write(d.join("encoder-model.int8.onnx"), b"").unwrap();
        assert!(parakeet_resolves_to_int8(&d, false));
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn fp32_present_without_pref_is_not_int8() {
        let d = tmp("fp32_int8_nopref");
        fs::write(d.join("encoder-model.onnx"), b"").unwrap();
        fs::write(d.join("encoder-model.int8.onnx"), b"").unwrap();
        assert!(!parakeet_resolves_to_int8(&d, false));
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn prefers_int8_with_both_is_int8() {
        let d = tmp("fp32_int8_pref");
        fs::write(d.join("encoder-model.onnx"), b"").unwrap();
        fs::write(d.join("encoder-model.int8.onnx"), b"").unwrap();
        assert!(parakeet_resolves_to_int8(&d, true));
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn no_model_is_not_int8() {
        let d = tmp("empty");
        assert!(!parakeet_resolves_to_int8(&d, false));
        let _ = fs::remove_dir_all(&d);
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let debug = env::var("DICTEE_DEBUG").unwrap_or_default() == "true";
    let args: Vec<String> = env::args().collect();
    let parsed = match parse_daemon_args(&args) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("transcribe-daemon: {}", e);
            eprintln!("Try 'transcribe-daemon --help' for usage.");
            std::process::exit(2);
        }
    };
    // --socket overrides the socket_path() default (which itself honors
    // $DICTEE_TRANSCRIBE_SOCKET then $XDG_RUNTIME_DIR).
    let socket_path = parsed.socket.clone().unwrap_or_else(socket_path);

    if parsed.help {
        eprintln!("transcribe-daemon - ASR daemon via Unix socket (Parakeet TDT / Canary AED)");
        eprintln!();
        eprintln!("Usage: transcribe-daemon [model_dir] [--canary] [--socket <path>]");
        eprintln!();
        eprintln!("Arguments:");
        eprintln!("  [model_dir]      Model directory (default: /usr/share/dictee/tdt or /canary)");
        eprintln!("  --canary         Use Canary AED backend instead of Parakeet TDT");
        eprintln!("  --socket <path>  Listen on this socket path (default: $DICTEE_TRANSCRIBE_SOCKET or $XDG_RUNTIME_DIR/transcribe.sock)");
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
    #[cfg(feature = "whisper")]
    let use_whisper = env::var("DICTEE_ASR_BACKEND")
        .map(|v| v == "whisper")
        .unwrap_or(false)
        || parsed.whisper;
    let use_canary = env::var("DICTEE_ASR_BACKEND")
        .map(|v| v == "canary")
        .unwrap_or(false)
        || parsed.canary;

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
    let model_dir = parsed
        .model_dir
        .clone()
        .unwrap_or_else(|| {
            let subdir = if use_canary { "canary" } else { "tdt" };
            let user_dir = format!(
                "{}/.local/share/dictee/{}",
                env::var("HOME").unwrap_or_else(|_| "/root".to_string()),
                subdir
            );
            let sys_dir = format!("/usr/share/dictee/{}", subdir);
            // User dir takes priority (local overrides, test models)
            if Path::new(&user_dir).join("vocab.txt").exists() {
                user_dir
            } else {
                sys_dir
            }
        });

    // Remove existing socket
    if Path::new(&socket_path).exists() {
        fs::remove_file(&socket_path)?;
    }

    // Whisper is GPU-only via Vulkan; it bypasses the ORT config entirely.
    #[cfg(feature = "whisper")]
    if use_whisper {
        // FMA3 guard: whisper.cpp/Vulkan SIGILLs on x86 CPUs without FMA3 (Handy #537).
        // GPU-only with no CPU fallback — refuse with a clear message.
        #[cfg(target_arch = "x86_64")]
        if !std::arch::is_x86_feature_detected!("fma") {
            return Err("Whisper requires an x86 CPU with FMA3 (this CPU lacks it). \
                        Whisper is GPU-only with no CPU fallback — use Parakeet instead."
                .into());
        }
        let dev = parakeet_rs::whisper::select_vulkan_device()
            .ok_or("Whisper backend requires a usable Vulkan GPU — none found (no CPU fallback)")?;
        // Primary var is DICTEE_WHISPER_RUST_GGML (namespaced like the other
        // whisper-rust knobs); fall back to the legacy DICTEE_WHISPER_GGML so an
        // older conf keeps working during the transition.
        let ggml = env::var("DICTEE_WHISPER_RUST_GGML")
            .or_else(|_| env::var("DICTEE_WHISPER_GGML"))
            .map_err(|_| "DICTEE_WHISPER_RUST_GGML not set (path to ggml-*.bin)")?;
        // VRAM fit guard: ggml file size + ~0.75 GiB compute-buffer margin (spec §6)
        // must fit the chosen device's free VRAM. Refuse cleanly — never CPU.
        let need = fs::metadata(&ggml).map(|m| m.len() as usize).unwrap_or(0)
            + 768 * 1024 * 1024;
        if let Some(free) = parakeet_rs::whisper::device_free_vram(dev) {
            if need > free {
                return Err(format!(
                    "Whisper model {} needs ~{} MiB but Vulkan device {} has only {} MiB free \
                     — pick a smaller/quantized model or free VRAM (GPU-only, no CPU fallback).",
                    ggml, need / (1024 * 1024), dev, free / (1024 * 1024)
                )
                .into());
            }
        }
        // Report the actual GPU backend so the UI badge distinguishes the two
        // whisper-rust variants the user picks in dictee-setup:
        //   whisper-cuda   → "cuda"   → green "G"
        //   whisper-vulkan → "vulkan" → violet "V"
        #[cfg(feature = "whisper-cuda")]
        let _provider = "cuda";
        #[cfg(not(feature = "whisper-cuda"))]
        let _provider = "vulkan";
        let _ = std::fs::write("/dev/shm/.dictee_provider", _provider);
        eprintln!("Loading Whisper model from {} ({} device {})...", ggml, _provider, dev);
        let backend = AsrBackend::Whisper(
            parakeet_rs::whisper::WhisperBackend::from_ggml(&ggml, dev, &source_lang)?,
        );
        eprintln!("Model loaded. Listening on {}", socket_path);
        let listener = UnixListener::bind(&socket_path)?;
        fs::set_permissions(&socket_path, fs::Permissions::from_mode(0o600))?;
        return run_socket_loop(backend, listener, source_lang, debug);
    }

    // Parakeet int8 is forced to CPU: the ORT CUDA EP doesn't optimize int8
    // ops (slower than int8 on CPU/AVX-VNNI), so int8 on the GPU is never
    // worthwhile. Canary has no int8 variant. DICTEE_PARAKEET_QUANT=int8 lets
    // the user prefer int8 even when fp32 is present (cf. find_encoder).
    let prefers_int8 = std::env::var("DICTEE_PARAKEET_QUANT")
        .map(|v| v.eq_ignore_ascii_case("int8"))
        .unwrap_or(false);
    let force_cpu_int8 =
        !use_canary && parakeet_resolves_to_int8(Path::new(&model_dir), prefers_int8);
    let provider = if force_cpu_int8 {
        eprintln!("[dictee] Parakeet int8 model — forcing CPU (int8 is slow on the CUDA EP)");
        ExecutionProvider::Cpu
    } else {
        best_provider()
    };
    let config = ExecutionConfig::new().with_execution_provider(provider);

    // Write detailed provider status to /dev/shm/.dictee_provider for UI
    // consumers (plasmoid badge, tray menu, dictee-setup). "cpu-int8" is a
    // CPU-voulu value (blue badge); provider_status() would say "cuda" here.
    let _ = std::fs::write(
        "/dev/shm/.dictee_provider",
        if force_cpu_int8 { "cpu-int8" } else { provider_status() },
    );

    eprintln!(
        "Loading {} model from {}...",
        if use_canary { "Canary AED" } else { "Parakeet TDT" },
        &model_dir
    );
    // Log the encoder variant being loaded. int8 is otherwise invisible: it is
    // read into a buffer rather than mmap'd, so it never appears in
    // /proc/<pid>/maps the way the fp32 encoder-model.onnx.data file does.
    // Mirrors the candidate order in ParakeetTDTModel::find_encoder.
    if !use_canary {
        let dir = Path::new(&model_dir);
        let encoder_file = if force_cpu_int8 {
            "encoder-model.int8.onnx"
        } else if dir.join("encoder-model.onnx").exists() {
            "encoder-model.onnx"
        } else {
            "encoder.onnx"
        };
        eprintln!(
            "[dictee] Parakeet encoder: {} ({})",
            encoder_file,
            if force_cpu_int8 { "int8" } else { "fp32" }
        );
    }

    let backend = if use_canary {
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

    run_socket_loop(backend, listener, source_lang, debug)
}

fn run_socket_loop(
    mut backend: AsrBackend,
    listener: UnixListener,
    source_lang: String,
    debug: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    for stream in listener.incoming() {
        match stream {
            Ok(mut stream) => {
                // Guard against a client that connects but never sends its
                // request line: without a read timeout it would block the
                // single-threaded accept loop and hang the whole UI.
                let _ = stream.set_read_timeout(Some(Duration::from_secs(30)));
                let reader = BufReader::new(&stream);
                if let Some(Ok(line)) = reader.lines().next() {
                    let line = line.trim().to_string();
                    let req = parse_request(&line);
                    dbg_print!(debug, "[daemon] request: path={} mode={} context={} lang={:?}",
                        req.path, req.mode, req.context.is_some(), req.target_lang);

                    // Set decoder context if provided (Canary decodercontext)
                    if let Some(ctx) = req.context {
                        backend.set_context(&ctx);
                    }

                    // Set target language for Canary translation
                    if let Some(ref lang) = req.target_lang {
                        if let AsrBackend::Canary(ref mut canary) = backend {
                            if let Err(e) = canary.set_target_lang(lang) {
                                eprintln!("[daemon] invalid target lang '{}': {}", lang, e);
                            }
                        }
                    }

                    let has_ctx = backend.has_context();
                    dbg_print!(debug, "[daemon] has_context={}", has_ctx);

                    match transcribe_file(&mut backend, req.path, req.mode) {
                        Ok(text) => {
                            dbg_print!(debug, "[daemon] result: {} chars", text.len());
                            let _ = writeln!(stream, "{}", text);
                        }
                        Err(e) => {
                            eprintln!("[daemon] error: {}", e);
                            let _ = writeln!(stream, "ERROR: {}", e);
                        }
                    }

                    // Reset target language back to source after translation request
                    if req.target_lang.is_some() {
                        if let AsrBackend::Canary(ref mut canary) = backend {
                            let _ = canary.set_target_lang(&source_lang);
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
struct Request<'a> {
    path: &'a str,
    mode: &'a str,
    context: Option<String>,
    target_lang: Option<String>,
}

fn parse_request(line: &str) -> Request<'_> {
    let parts: Vec<&str> = line.splitn(4, '\t').collect();
    let path = parts[0].trim();
    let mut mode = "plain";
    let mut context = None;
    let mut target_lang = None;

    for &part in parts.iter().skip(1) {
        let part = part.trim();
        if let Some(ctx) = part.strip_prefix("context:") {
            context = Some(ctx.to_string());
        } else if let Some(lang) = part.strip_prefix("lang:") {
            target_lang = Some(lang.to_string());
        } else if part == "timestamps" || part == "diarize" {
            mode = part;
        }
    }

    Request { path, mode, context, target_lang }
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

#[cfg(test)]
mod arg_tests {
    use super::*;

    fn argv(extra: &[&str]) -> Vec<String> {
        std::iter::once("transcribe-daemon")
            .chain(extra.iter().copied())
            .map(String::from)
            .collect()
    }

    #[test]
    fn socket_flag_is_parsed() {
        let p = parse_daemon_args(&argv(&["--socket", "/tmp/x.sock"])).unwrap();
        assert_eq!(p.socket.as_deref(), Some("/tmp/x.sock"));
        assert_eq!(p.model_dir, None);
    }

    #[test]
    fn socket_path_does_not_become_model_dir() {
        let p = parse_daemon_args(&argv(&["--socket", "/tmp/x.sock", "/models/tdt"]))
            .unwrap();
        assert_eq!(p.socket.as_deref(), Some("/tmp/x.sock"));
        assert_eq!(p.model_dir.as_deref(), Some("/models/tdt"));
    }

    #[test]
    fn canary_and_positional_model_dir() {
        let p = parse_daemon_args(&argv(&["/models/tdt", "--canary"])).unwrap();
        assert!(p.canary);
        assert_eq!(p.model_dir.as_deref(), Some("/models/tdt"));
        assert_eq!(p.socket, None);
    }

    #[test]
    fn unknown_flag_is_rejected() {
        assert!(parse_daemon_args(&argv(&["--bogus"])).is_err());
    }

    #[test]
    fn socket_without_value_is_rejected() {
        assert!(parse_daemon_args(&argv(&["--socket"])).is_err());
    }

    #[test]
    fn help_flag_is_parsed() {
        assert!(parse_daemon_args(&argv(&["--help"])).unwrap().help);
        assert!(parse_daemon_args(&argv(&["-h"])).unwrap().help);
    }
}
