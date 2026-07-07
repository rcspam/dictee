use parakeet_rs::{
    best_provider, provider_status, Canary, ExecutionConfig, ExecutionProvider, Nemotron,
    ParakeetTDT, TimestampMode, Transcriber, TranscriptionResult,
};
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
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
    nemotron: bool,
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
            "--nemotron" => out.nemotron = true,
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

/// Unified ASR backend: Parakeet TDT, Canary AED, Nemotron RNNT, or Whisper (GPU-only)
enum AsrBackend {
    Parakeet(ParakeetTDT),
    Canary(Canary),
    Nemotron(Nemotron),
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
            AsrBackend::Nemotron(n) => {
                // Nemotron expects 16 kHz mono; the dictee pipeline already
                // delivers that. Guard loudly so wrong-rate audio is never
                // silently mistranscribed.
                if sample_rate != 16000 {
                    return Err(parakeet_rs::Error::Audio(format!(
                        "Nemotron expects 16000 Hz mono, got {} Hz",
                        sample_rate
                    )));
                }
                // No word timestamps -> empty tokens.
                let text = n.transcribe_audio(&audio)?;
                Ok(TranscriptionResult { text, tokens: Vec::new() })
            }
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
            AsrBackend::Nemotron(_) => false,
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
        eprintln!("transcribe-daemon - ASR daemon via Unix socket (Parakeet TDT / Canary AED / Nemotron RNNT)");
        eprintln!();
        eprintln!("Usage: transcribe-daemon [model_dir] [--canary|--nemotron] [--socket <path>]");
        eprintln!();
        eprintln!("Arguments:");
        eprintln!("  [model_dir]      Model directory (default: /usr/share/dictee/tdt, /canary, or /nemotron)");
        eprintln!("  --canary         Use Canary AED backend instead of Parakeet TDT");
        eprintln!("  --nemotron       Use Nemotron RNNT backend instead of Parakeet TDT");
        eprintln!("  --socket <path>  Listen on this socket path (default: $DICTEE_TRANSCRIBE_SOCKET or $XDG_RUNTIME_DIR/transcribe.sock)");
        eprintln!();
        eprintln!("Environment:");
        eprintln!("  DICTEE_ASR_BACKEND=canary    Select Canary backend");
        eprintln!("  DICTEE_ASR_BACKEND=nemotron  Select Nemotron backend");
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
    let use_nemotron = env::var("DICTEE_ASR_BACKEND")
        .map(|v| v == "nemotron")
        .unwrap_or(false)
        || parsed.nemotron;

    if use_canary && use_nemotron {
        eprintln!("[daemon] warning: --canary and --nemotron both set; using Canary");
    }

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
            let subdir = if use_canary { "canary" } else if use_nemotron { "nemotron" } else { "tdt" };
            let user_dir = format!(
                "{}/.local/share/dictee/{}",
                env::var("HOME").unwrap_or_else(|_| "/root".to_string()),
                subdir
            );
            let sys_dir = format!("/usr/share/dictee/{}", subdir);
            // Nemotron uses tokenizer.model as sentinel; Parakeet/Canary use vocab.txt.
            let sentinel = if use_nemotron { "tokenizer.model" } else { "vocab.txt" };
            // User dir takes priority (local overrides, test models)
            if Path::new(&user_dir).join(sentinel).exists() {
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
        // Same gate as the ORT path below: an ad-hoc daemon (spawned with
        // DICTEE_DAEMON_NO_PROVIDER=1) must never clobber the F9 badge.
        if env::var("DICTEE_DAEMON_NO_PROVIDER").as_deref() != Ok("1") {
            let _ = std::fs::write("/dev/shm/.dictee_provider", _provider);
        }
        eprintln!("Loading Whisper model from {} ({} device {})...", ggml, _provider, dev);
        let backend = AsrBackend::Whisper(
            parakeet_rs::whisper::WhisperBackend::from_ggml(&ggml, dev, &source_lang)?,
        );
        eprintln!("Model loaded. Listening on {}", socket_path);
        let listener = UnixListener::bind(&socket_path)?;
        fs::set_permissions(&socket_path, fs::Permissions::from_mode(0o600))?;
        return run_socket_loop(backend, listener, source_lang, None, debug);
    }

    // Parakeet int8 is forced to CPU: the ORT CUDA EP doesn't optimize int8
    // ops (slower than int8 on CPU/AVX-VNNI), so int8 on the GPU is never
    // worthwhile. Canary has no int8 variant. DICTEE_PARAKEET_QUANT=int8 lets
    // the user prefer int8 even when fp32 is present (cf. find_encoder).
    let prefers_int8 = std::env::var("DICTEE_PARAKEET_QUANT")
        .map(|v| v.eq_ignore_ascii_case("int8"))
        .unwrap_or(false);
    let force_cpu_int8 =
        !use_canary && !use_nemotron && parakeet_resolves_to_int8(Path::new(&model_dir), prefers_int8);
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
    // Only the F9 daemon owns the shared badge file. An isolated ad-hoc daemon
    // (spawned by dictee-transcribe for a one-off model) sets
    // DICTEE_DAEMON_NO_PROVIDER=1 so it never clobbers the F9 badge.
    if env::var("DICTEE_DAEMON_NO_PROVIDER").as_deref() != Ok("1") {
        let _ = std::fs::write(
            "/dev/shm/.dictee_provider",
            if force_cpu_int8 { "cpu-int8" } else { provider_status() },
        );
    }

    eprintln!(
        "Loading {} model from {}...",
        if use_canary { "Canary AED" } else if use_nemotron { "Nemotron RNNT" } else { "Parakeet TDT" },
        &model_dir
    );
    // Log the encoder variant being loaded. int8 is otherwise invisible: it is
    // read into a buffer rather than mmap'd, so it never appears in
    // /proc/<pid>/maps the way the fp32 encoder-model.onnx.data file does.
    // Mirrors the candidate order in ParakeetTDTModel::find_encoder.
    if !use_canary && !use_nemotron {
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

    // Capture the language that will actually be pinned at startup for the
    // Nemotron multilingual backend. Used to restore after a per-session
    // lang: override (see Fix 3 in handle_stream).  None means the model
    // keeps its default "auto" prompt (no set_target_lang call at startup).
    let nemotron_startup_lang: Option<String>;

    let backend = if use_canary {
        nemotron_startup_lang = None;
        AsrBackend::Canary(Canary::from_pretrained(
            &model_dir,
            Some(config),
            &source_lang,
            &target_lang,
        )?)
    } else if use_nemotron {
        let mut n = Nemotron::from_pretrained(&model_dir, Some(config))?;
        // Decision A: drive language from the global DICTEE_LANG_SOURCE; "auto"
        // (or unset) lets Nemotron pick — robust for FR. Only pin when set.
        if let parakeet_rs::NemotronMode::Multilingual = n.mode() {
            if source_lang != "auto" && !source_lang.is_empty() {
                if let Err(e) = n.set_target_lang(&source_lang) {
                    eprintln!("[daemon] nemotron lang '{}' rejected, using auto: {}", source_lang, e);
                    nemotron_startup_lang = None;
                } else {
                    nemotron_startup_lang = Some(source_lang.clone());
                }
            } else {
                nemotron_startup_lang = None; // stays on "auto"
            }
        } else {
            nemotron_startup_lang = None; // English-only variant: no lang pin
        }
        AsrBackend::Nemotron(n)
    } else {
        nemotron_startup_lang = None;
        AsrBackend::Parakeet(ParakeetTDT::from_pretrained(&model_dir, Some(config))?)
    };

    eprintln!("Model loaded. Listening on {}", socket_path);

    let listener = UnixListener::bind(&socket_path)?;
    fs::set_permissions(&socket_path, fs::Permissions::from_mode(0o600))?;

    run_socket_loop(backend, listener, source_lang, nemotron_startup_lang, debug)
}

fn run_socket_loop(
    mut backend: AsrBackend,
    listener: UnixListener,
    source_lang: String,
    // Startup-pinned Nemotron language to restore after a per-session
    // stream lang: override; None (whisper/canary/parakeet) restores "auto".
    nemotron_startup_lang: Option<String>,
    debug: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    for stream in listener.incoming() {
        match stream {
            Ok(mut stream) => {
                // Guard against a client that connects but never sends its
                // request line: without a read timeout it would block the
                // single-threaded accept loop and hang the whole UI.
                let _ = stream.set_read_timeout(Some(Duration::from_secs(30)));
                // Guard against a live-but-stalled client that stops draining
                // replies: once the socket send buffer fills, write_all would
                // block forever, freezing the single-threaded daemon.
                let _ = stream.set_write_timeout(Some(Duration::from_secs(30)));
                // Use read_line (borrows &mut self) instead of .lines()
                // (which consumes self) so we can pass the BufReader into
                // handle_stream without losing any bytes it may have buffered
                // after the handshake line.
                let mut reader = BufReader::new(&stream);
                let mut raw_line = String::new();
                match reader.read_line(&mut raw_line) {
                    Ok(0) | Err(_) => continue, // EOF or timeout before handshake
                    Ok(_) => {}
                }
                let line = raw_line.trim().to_string();

                // Stream mode: bidirectional persistent connection.
                // Handshake line: "stream" (optionally "stream\tlang:fr").
                // Pass the BufReader by value so any bytes it buffered
                // beyond the handshake line are not lost.
                if line == "stream" || line.starts_with("stream\t") {
                    if let Some(lang) = line.strip_prefix("stream\t")
                        .and_then(|s| s.strip_prefix("lang:"))
                    {
                        if let AsrBackend::Nemotron(ref mut n) = backend {
                            if let Err(e) = n.set_target_lang(lang) {
                                eprintln!("[daemon] stream: invalid lang '{}': {}", lang, e);
                            }
                        }
                    }
                    if let Err(e) = handle_stream(&mut backend, reader, debug) {
                        eprintln!("[daemon] stream error: {}", e);
                    }
                    // Restore the startup language so subsequent batch requests
                    // and lang-less stream sessions are not pinned to this
                    // session's lang: override.
                    if let AsrBackend::Nemotron(ref mut n) = backend {
                        let restore = nemotron_startup_lang.as_deref().unwrap_or("auto");
                        if let Err(e) = n.set_target_lang(restore) {
                            eprintln!("[daemon] lang restore '{}' failed: {}", restore, e);
                        }
                    }
                    continue;
                }

                // Batch mode: reader's borrow ends here; stream is free for
                // writeln! below.
                drop(reader);

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

/// Stream mode: read length-prefixed s16le audio frames, feed Nemotron's
/// `transcribe_chunk`, write back length-prefixed UTF-8 text fragments.
///
/// # Protocol contract
///
/// After sending the zero-length sentinel the client **must** read until EOF.
/// Zero or more flush fragment frames may arrive, and the **last** frame before
/// EOF is the full transcript (`get_transcript()`).  If the connection closes
/// before the client has sent the sentinel — or if an error occurs mid-stream —
/// the server closes without sending a final frame; the resulting EOF without a
/// preceding sentinel signals an aborted session to the client.
///
/// The client must pace audio frames so that each frame covers at most 560 ms
/// of audio (the engine processes at most one internal chunk per call; the
/// silence flush only covers a partial tail, not a backlog). `MAX_FRAME_LEN`
/// caps the largest accepted frame at ≈32 s regardless.
///
/// The `reader` is passed in by value (rather than reconstructed from
/// `&stream`) so that any bytes the BufReader already consumed past the
/// handshake line are not silently dropped.
fn handle_stream(
    backend: &mut AsrBackend,
    reader: BufReader<&UnixStream>,
    debug: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    use parakeet_rs::stream_proto::{frame, read_frame, s16le_to_f32};

    let nemo = match backend {
        AsrBackend::Nemotron(n) => n,
        _ => {
            // Stream mode requires Nemotron; refuse gracefully.
            let mut w = reader.get_ref().try_clone()?;
            w.write_all(&frame(b"ERROR: stream mode requires the Nemotron backend"))?;
            return Ok(());
        }
    };

    // Clone the underlying stream reference for writing; the BufReader keeps
    // the read side (including any bytes buffered after the handshake line).
    let mut writer = reader.get_ref().try_clone()?;
    let mut reader = reader;

    // Whether the loop ended on a proper sentinel (true) or abnormally (false).
    // Only a sentinel exit gets the silence flush + final transcript frame.
    let mut sentinel = false;

    loop {
        match read_frame(&mut reader) {
            Ok(None) => {
                sentinel = true;
                break; // clean end-of-stream sentinel
            }
            Err(e) => {
                // EOF, 30 s read timeout, or oversized frame (protocol error).
                dbg_print!(debug, "[daemon] stream read ended: {}", e);
                break; // abnormal exit — no final frame
            }
            Ok(Some(payload)) => {
                let samples = s16le_to_f32(&payload);
                let fragment = match nemo.transcribe_chunk(&samples) {
                    Ok(f) => f,
                    Err(e) => {
                        eprintln!("[daemon] stream transcribe_chunk error: {}", e);
                        break; // abnormal exit — no final frame
                    }
                };
                if !fragment.is_empty() {
                    if let Err(e) = writer.write_all(&frame(fragment.as_bytes())) {
                        eprintln!("[daemon] stream write error: {}", e);
                        break; // abnormal exit — no final frame
                    }
                    if let Err(e) = writer.flush() {
                        eprintln!("[daemon] stream flush error: {}", e);
                        break; // abnormal exit — no final frame
                    }
                }
            }
        }
    }

    if sentinel {
        // Flush the engine's buffered tail exactly like transcribe_audio
        // handles its last iteration: the final partial chunk is encoded
        // with its TRUE length — the explicit end-of-sequence that makes
        // the model decode the held-back tail tokens AND emit the final
        // punctuation. (Silence padding did neither reliably: the model
        // saw speech followed by silence, not an end of sequence.)
        // Write errors here are non-fatal: we must still reach nemo.reset().
        match nemo.finalize_transcript() {
            Ok(fragment) => {
                if !fragment.is_empty() {
                    if let Err(e) = writer.write_all(&frame(fragment.as_bytes())) {
                        eprintln!("[daemon] stream flush write error: {}", e);
                    } else if let Err(e) = writer.flush() {
                        eprintln!("[daemon] stream flush error: {}", e);
                    }
                }
            }
            Err(e) => {
                eprintln!("[daemon] stream finalize error: {}", e);
            }
        }

        let final_text = nemo.get_transcript();
        if let Err(e) = writer.write_all(&frame(final_text.as_bytes())) {
            eprintln!("[daemon] stream final write error: {}", e);
        } else if let Err(e) = writer.flush() {
            eprintln!("[daemon] stream final flush error: {}", e);
        }
    }
    // On abnormal exit: close without sending a final frame. The resulting EOF
    // signals the aborted session to the client (no duplicate text risk).

    nemo.reset();
    Ok(())
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
