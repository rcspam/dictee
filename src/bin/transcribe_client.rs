use std::env;
use std::fs;
use std::io::{BufRead, BufReader, IsTerminal, Read, Write};
use std::os::unix::net::UnixStream;
use std::process::{Command, Stdio};
use std::sync::LazyLock;
use std::time::Duration;

extern crate hound;

/// Chemins par utilisateur via $XDG_RUNTIME_DIR (ou /tmp fallback).
/// Chaque utilisateur a ses propres fichiers temporaires et socket.
fn user_path(name: &str) -> String {
    if let Ok(dir) = env::var("XDG_RUNTIME_DIR") {
        format!("{}/{}", dir, name)
    } else {
        format!("/tmp/{}-{}", name, unsafe { libc::getuid() })
    }
}

static SOCKET_PATH: LazyLock<String> = LazyLock::new(|| user_path("transcribe.sock"));

/// Parsed command-line arguments for transcribe-client.
#[derive(Debug, Default)]
struct ClientArgs {
    help: bool,
    /// Explicit daemon socket path (`--socket <path>`); overrides SOCKET_PATH.
    socket: Option<String>,
    /// Optional positional audio file. None means stdin or mic mode.
    audio: Option<String>,
}

/// Parse argv into [`ClientArgs`], rejecting unknown options loudly so a flag
/// the binary does not implement can never be silently taken as the audio path.
fn parse_client_args(args: &[String]) -> Result<ClientArgs, String> {
    let mut out = ClientArgs::default();
    let mut i = 1; // skip argv[0]
    while i < args.len() {
        match args[i].as_str() {
            "--help" | "-h" => out.help = true,
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
                if out.audio.is_some() {
                    return Err(format!("unexpected extra argument '{}'", s));
                }
                out.audio = Some(s.to_string());
            }
        }
        i += 1;
    }
    Ok(out)
}
static TEMP_WAV: LazyLock<String> = LazyLock::new(|| user_path("transcribe_recording.wav"));
static TEMP_CONVERTED: LazyLock<String> = LazyLock::new(|| user_path("transcribe_converted.wav"));
static TEMP_STDIN: LazyLock<String> = LazyLock::new(|| user_path("transcribe_stdin_input"));

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let parsed = match parse_client_args(&args) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("transcribe-client: {}", e);
            eprintln!("Try 'transcribe-client --help' for usage.");
            std::process::exit(2);
        }
    };

    if parsed.help {
        eprintln!("transcribe-client - Client de transcription (fichier, stdin, micro)");
        eprintln!();
        eprintln!("Usage:");
        eprintln!("  transcribe-client <fichier>       Transcrire un fichier audio (tout format)");
        eprintln!("  cat audio | transcribe-client     Transcrire depuis stdin");
        eprintln!("  transcribe-client                 Enregistrer depuis le micro");
        eprintln!();
        eprintln!("Options:");
        eprintln!("  --socket <path>  Daemon socket path (default: $XDG_RUNTIME_DIR/transcribe.sock)");
        eprintln!();
        eprintln!("Mode micro:");
        eprintln!("  Sans TRANSCRIBE_DURATION : enregistrement jusqu'à Entrée");
        eprintln!("  TRANSCRIBE_DURATION=10   : enregistrement de 10 secondes");
        eprintln!();
        eprintln!("Le micro est automatiquement démuté si nécessaire.");
        eprintln!("Nécessite transcribe-daemon en cours d'exécution.");
        return Ok(());
    }

    // Explicit --socket overrides the $XDG_RUNTIME_DIR-derived default.
    let socket_path = parsed.socket.clone().unwrap_or_else(|| SOCKET_PATH.clone());

    // Mode 1: Direct file path provided
    if let Some(audio) = parsed.audio.as_deref() {
        let audio_path = resolve_path(audio)?;
        let (wav_path, needs_cleanup) = ensure_wav(&audio_path)?;
        let text = send_to_daemon(&wav_path, &socket_path);
        if needs_cleanup {
            let _ = fs::remove_file(&wav_path);
        }
        println!("{}", text?);
        return Ok(());
    }

    // Mode 2: Audio piped via stdin
    if !std::io::stdin().is_terminal() {
        let mut input = Vec::new();
        std::io::stdin().read_to_end(&mut input)?;
        if input.is_empty() {
            return Err("No data received on stdin".into());
        }
        fs::write(TEMP_STDIN.as_str(), &input)?;

        // ffmpeg auto-détecte le format via les headers
        let status = Command::new("ffmpeg")
            .args(["-y", "-i", TEMP_STDIN.as_str(), "-ar", "16000", "-ac", "1", "-f", "wav", TEMP_CONVERTED.as_str()])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|e| format!("ffmpeg not found: {}. Install ffmpeg to read from stdin.", e))?;

        let _ = fs::remove_file(TEMP_STDIN.as_str());

        if !status.success() {
            return Err("ffmpeg failed to convert stdin audio (unsupported format?)".into());
        }

        let text = send_to_daemon(TEMP_CONVERTED.as_str(), &socket_path);
        let _ = fs::remove_file(TEMP_CONVERTED.as_str());
        println!("{}", text?);
        return Ok(());
    }

    // Mode 3: Record from microphone
    let duration: Option<u32> = env::var("TRANSCRIBE_DURATION")
        .ok()
        .and_then(|v| v.parse().ok());

    let was_muted = unmute_mic();

    let record_result = if let Some(duration) = duration {
        eprintln!("Recording for {} seconds... (Ctrl+C to stop early)", duration);
        record_with_pipewire(duration)
            .or_else(|_| record_with_pulseaudio(duration))
            .or_else(|_| record_with_alsa(duration))
    } else {
        eprintln!("Recording... Press Enter to stop.");
        record_pipewire_until_stopped()
            .or_else(|_| record_pulseaudio_until_stopped())
            .or_else(|_| record_alsa_until_stopped())
    };

    if let Err(e) = record_result {
        if was_muted { mute_mic(); }
        eprintln!("Failed to record audio: {}", e);
        eprintln!("Make sure pw-record, parecord, or arecord is installed.");
        std::process::exit(1);
    }

    eprintln!("Recording complete. Transcribing...");

    let text = send_to_daemon(TEMP_WAV.as_str(), &socket_path);
    if was_muted { mute_mic(); }
    let _ = fs::remove_file(TEMP_WAV.as_str());
    println!("{}", text?);

    Ok(())
}

fn record_with_pipewire(duration: u32) -> Result<(), Box<dyn std::error::Error>> {
    let _status = Command::new("timeout")
        .args([
            "--signal=INT",
            &format!("{}s", duration),
            "pw-record",
            "--rate", "16000",
            "--channels", "1",
            "--format", "s16",
            TEMP_WAV.as_str(),
        ])
        .stdin(Stdio::null())
        .stderr(Stdio::inherit())
        .status()?;

    if std::path::Path::new(TEMP_WAV.as_str()).exists() {
        Ok(())
    } else {
        Err("pw-record failed".into())
    }
}

fn record_with_pulseaudio(duration: u32) -> Result<(), Box<dyn std::error::Error>> {
    let _status = Command::new("timeout")
        .args([
            "--signal=INT",
            &format!("{}s", duration),
            "parecord",
            "--rate=16000",
            "--channels=1",
            "--format=s16le",
            "--file-format=wav",
            TEMP_WAV.as_str(),
        ])
        .stdin(Stdio::null())
        .stderr(Stdio::inherit())
        .status()?;

    if std::path::Path::new(TEMP_WAV.as_str()).exists() {
        Ok(())
    } else {
        Err("parecord failed".into())
    }
}

fn record_with_alsa(duration: u32) -> Result<(), Box<dyn std::error::Error>> {
    let status = Command::new("arecord")
        .args([
            "-r", "16000",
            "-c", "1",
            "-f", "S16_LE",
            "-d", &duration.to_string(),
            TEMP_WAV.as_str(),
        ])
        .stdin(Stdio::null())
        .stderr(Stdio::inherit())
        .status()?;

    if status.success() {
        Ok(())
    } else {
        Err("arecord failed".into())
    }
}

fn stop_recording(child: &mut std::process::Child) {
    let _ = Command::new("kill")
        .args(["-INT", &child.id().to_string()])
        .status();
    let _ = child.wait();
}

fn record_pipewire_until_stopped() -> Result<(), Box<dyn std::error::Error>> {
    let mut child = Command::new("pw-record")
        .args(["--rate", "16000", "--channels", "1", "--format", "s16", TEMP_WAV.as_str()])
        .stdin(Stdio::null())
        .stderr(Stdio::inherit())
        .spawn()?;

    let mut input = String::new();
    let _ = std::io::stdin().read_line(&mut input);
    stop_recording(&mut child);

    if std::path::Path::new(TEMP_WAV.as_str()).exists() {
        Ok(())
    } else {
        Err("pw-record failed".into())
    }
}

fn record_pulseaudio_until_stopped() -> Result<(), Box<dyn std::error::Error>> {
    let mut child = Command::new("parecord")
        .args(["--rate=16000", "--channels=1", "--format=s16le", "--file-format=wav", TEMP_WAV.as_str()])
        .stdin(Stdio::null())
        .stderr(Stdio::inherit())
        .spawn()?;

    let mut input = String::new();
    let _ = std::io::stdin().read_line(&mut input);
    stop_recording(&mut child);

    if std::path::Path::new(TEMP_WAV.as_str()).exists() {
        Ok(())
    } else {
        Err("parecord failed".into())
    }
}

fn record_alsa_until_stopped() -> Result<(), Box<dyn std::error::Error>> {
    let mut child = Command::new("arecord")
        .args(["-r", "16000", "-c", "1", "-f", "S16_LE", TEMP_WAV.as_str()])
        .stdin(Stdio::null())
        .stderr(Stdio::inherit())
        .spawn()?;

    let mut input = String::new();
    let _ = std::io::stdin().read_line(&mut input);
    stop_recording(&mut child);

    if std::path::Path::new(TEMP_WAV.as_str()).exists() {
        Ok(())
    } else {
        Err("arecord failed".into())
    }
}

fn unmute_mic() -> bool {
    // Try wpctl (PipeWire) first
    if let Ok(output) = Command::new("wpctl")
        .args(["get-volume", "@DEFAULT_AUDIO_SOURCE@"])
        .output()
    {
        if String::from_utf8_lossy(&output.stdout).contains("[MUTED]") {
            eprintln!("Warning: microphone is muted, unmuting...");
            let _ = Command::new("wpctl")
                .args(["set-mute", "@DEFAULT_AUDIO_SOURCE@", "0"])
                .status();
            return true;
        }
        return false;
    }
    // Fallback: pactl (PulseAudio) with LANG=C for English output
    if let Ok(output) = Command::new("env")
        .args(["LANG=C", "pactl", "get-source-mute", "@DEFAULT_SOURCE@"])
        .output()
    {
        if String::from_utf8_lossy(&output.stdout).contains("yes") {
            eprintln!("Warning: microphone is muted, unmuting...");
            let _ = Command::new("pactl")
                .args(["set-source-mute", "@DEFAULT_SOURCE@", "0"])
                .status();
            return true;
        }
    }
    false
}

fn mute_mic() {
    // Try wpctl first, fallback pactl
    if Command::new("wpctl")
        .args(["set-mute", "@DEFAULT_AUDIO_SOURCE@", "1"])
        .status()
        .is_err()
    {
        let _ = Command::new("pactl")
            .args(["set-source-mute", "@DEFAULT_SOURCE@", "1"])
            .status();
    }
}

/// Résout ~/..., ./..., ../... en chemin absolu pour le daemon
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

/// Vérifie si le fichier est un WAV 16kHz mono (compatible daemon).
fn is_wav_16k_mono(path: &str) -> bool {
    let Ok(reader) = hound::WavReader::open(path) else { return false };
    let spec = reader.spec();
    spec.sample_rate == 16000 && spec.channels == 1
}

/// Convertit le fichier audio en WAV 16kHz mono si nécessaire via ffmpeg.
/// Retourne (chemin_wav, needs_cleanup).
fn ensure_wav(audio_path: &str) -> Result<(String, bool), Box<dyn std::error::Error>> {
    if is_wav_16k_mono(audio_path) {
        return Ok((audio_path.to_string(), false));
    }

    let status = Command::new("ffmpeg")
        .args(["-y", "-i", audio_path, "-ar", "16000", "-ac", "1", "-f", "wav", TEMP_CONVERTED.as_str()])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|e| format!("ffmpeg not found or failed to start: {}. Install ffmpeg to convert audio files.", e))?;

    if !status.success() {
        return Err(format!("ffmpeg failed to convert '{}' (exit code: {:?})", audio_path, status.code()).into());
    }

    Ok((TEMP_CONVERTED.to_string(), true))
}

fn send_to_daemon(audio_path: &str, socket_path: &str) -> Result<String, Box<dyn std::error::Error>> {
    let mut stream = UnixStream::connect(socket_path).map_err(|e| {
        format!(
            "Cannot connect to daemon at {}. Is transcribe-daemon running? Error: {}",
            socket_path, e
        )
    })?;

    // 120 s instead of 30 s — fail-safe against a daemon hang, not a routing
    // mechanism. Parakeet/Canary respond in <2 s typically, but Whisper
    // large-v3 takes ~1 s per minute audio, so 30 s capped audio at ~25-30 min
    // on a fast GPU and made the WouldBlock error appear on slower hardware
    // well before the actual VRAM limit. 120 s covers ~2 h audio on RTX 4070
    // for Whisper, no-op for the other backends.
    stream.set_read_timeout(Some(Duration::from_secs(120)))?;

    writeln!(stream, "{}", audio_path)?;
    stream.flush()?;

    let reader = BufReader::new(&stream);
    let response = reader
        .lines()
        .next()
        .ok_or("No response from daemon")??;

    if response.starts_with("ERROR:") {
        Err(response.into())
    } else {
        Ok(response)
    }
}

#[cfg(test)]
mod arg_tests {
    use super::*;

    fn argv(extra: &[&str]) -> Vec<String> {
        std::iter::once("transcribe-client")
            .chain(extra.iter().copied())
            .map(String::from)
            .collect()
    }

    #[test]
    fn socket_flag_is_parsed() {
        let p = parse_client_args(&argv(&["--socket", "/tmp/x.sock"])).unwrap();
        assert_eq!(p.socket.as_deref(), Some("/tmp/x.sock"));
        assert_eq!(p.audio, None);
    }

    #[test]
    fn socket_then_audio_stay_distinct() {
        let p = parse_client_args(&argv(&["--socket", "/tmp/x.sock", "rec.wav"])).unwrap();
        assert_eq!(p.socket.as_deref(), Some("/tmp/x.sock"));
        assert_eq!(p.audio.as_deref(), Some("rec.wav"));
    }

    #[test]
    fn bare_audio_path() {
        let p = parse_client_args(&argv(&["rec.wav"])).unwrap();
        assert_eq!(p.socket, None);
        assert_eq!(p.audio.as_deref(), Some("rec.wav"));
    }

    #[test]
    fn no_args_is_mic_mode() {
        let p = parse_client_args(&argv(&[])).unwrap();
        assert_eq!(p.socket, None);
        assert_eq!(p.audio, None);
    }

    #[test]
    fn unknown_flag_is_rejected() {
        assert!(parse_client_args(&argv(&["--bogus"])).is_err());
    }

    #[test]
    fn socket_without_value_is_rejected() {
        assert!(parse_client_args(&argv(&["--socket"])).is_err());
    }

    #[test]
    fn help_flag_is_parsed() {
        assert!(parse_client_args(&argv(&["--help"])).unwrap().help);
    }
}
