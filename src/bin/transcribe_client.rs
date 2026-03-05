use std::env;
use std::fs;
use std::io::{BufRead, BufReader, IsTerminal, Read, Write};
use std::os::unix::net::UnixStream;
use std::process::{Command, Stdio};
use std::time::Duration;

extern crate hound;

const SOCKET_PATH: &str = "/tmp/transcribe.sock";
const TEMP_WAV: &str = "/tmp/transcribe_recording.wav";
const TEMP_CONVERTED: &str = "/tmp/transcribe_converted.wav";
const TEMP_STDIN: &str = "/tmp/transcribe_stdin_input";

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();

    if args.iter().any(|a| a == "--help" || a == "-h") {
        eprintln!("transcribe-client - Client de transcription (fichier, stdin, micro)");
        eprintln!();
        eprintln!("Usage:");
        eprintln!("  transcribe-client <fichier>       Transcrire un fichier audio (tout format)");
        eprintln!("  cat audio | transcribe-client     Transcrire depuis stdin");
        eprintln!("  transcribe-client                 Enregistrer depuis le micro");
        eprintln!();
        eprintln!("Mode micro:");
        eprintln!("  Sans TRANSCRIBE_DURATION : enregistrement jusqu'à Entrée");
        eprintln!("  TRANSCRIBE_DURATION=10   : enregistrement de 10 secondes");
        eprintln!();
        eprintln!("Le micro est automatiquement démuté si nécessaire.");
        eprintln!("Nécessite transcribe-daemon en cours d'exécution.");
        return Ok(());
    }

    // Mode 1: Direct file path provided
    if args.len() > 1 {
        let audio_path = resolve_path(&args[1])?;
        let (wav_path, needs_cleanup) = ensure_wav(&audio_path)?;
        let text = send_to_daemon(&wav_path);
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
        fs::write(TEMP_STDIN, &input)?;

        // ffmpeg auto-détecte le format via les headers
        let status = Command::new("ffmpeg")
            .args(["-y", "-i", TEMP_STDIN, "-ar", "16000", "-ac", "1", "-f", "wav", TEMP_CONVERTED])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|e| format!("ffmpeg not found: {}. Install ffmpeg to read from stdin.", e))?;

        let _ = fs::remove_file(TEMP_STDIN);

        if !status.success() {
            return Err("ffmpeg failed to convert stdin audio (unsupported format?)".into());
        }

        let text = send_to_daemon(TEMP_CONVERTED);
        let _ = fs::remove_file(TEMP_CONVERTED);
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

    let text = send_to_daemon(TEMP_WAV);
    if was_muted { mute_mic(); }
    let _ = fs::remove_file(TEMP_WAV);
    println!("{}", text?);

    Ok(())
}

fn record_with_pipewire(duration: u32) -> Result<(), Box<dyn std::error::Error>> {
    // Use timeout command to limit pw-record duration
    let _status = Command::new("timeout")
        .args([
            "--signal=INT",
            &format!("{}s", duration),
            "pw-record",
            "--rate", "16000",
            "--channels", "1",
            "--format", "s16",
            TEMP_WAV,
        ])
        .stdin(Stdio::null())
        .stderr(Stdio::inherit())
        .status()?;

    // timeout returns 124 on timeout, but file should be written
    if std::path::Path::new(TEMP_WAV).exists() {
        Ok(())
    } else {
        Err("pw-record failed".into())
    }
}

fn record_with_pulseaudio(duration: u32) -> Result<(), Box<dyn std::error::Error>> {
    // Use timeout command to limit parecord duration
    let _status = Command::new("timeout")
        .args([
            "--signal=INT",
            &format!("{}s", duration),
            "parecord",
            "--rate=16000",
            "--channels=1",
            "--format=s16le",
            "--file-format=wav",
            TEMP_WAV,
        ])
        .stdin(Stdio::null())
        .stderr(Stdio::inherit())
        .status()?;

    if std::path::Path::new(TEMP_WAV).exists() {
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
            TEMP_WAV,
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
        .args(["--rate", "16000", "--channels", "1", "--format", "s16", TEMP_WAV])
        .stdin(Stdio::null())
        .stderr(Stdio::inherit())
        .spawn()?;

    let mut input = String::new();
    let _ = std::io::stdin().read_line(&mut input);
    stop_recording(&mut child);

    if std::path::Path::new(TEMP_WAV).exists() {
        Ok(())
    } else {
        Err("pw-record failed".into())
    }
}

fn record_pulseaudio_until_stopped() -> Result<(), Box<dyn std::error::Error>> {
    let mut child = Command::new("parecord")
        .args(["--rate=16000", "--channels=1", "--format=s16le", "--file-format=wav", TEMP_WAV])
        .stdin(Stdio::null())
        .stderr(Stdio::inherit())
        .spawn()?;

    let mut input = String::new();
    let _ = std::io::stdin().read_line(&mut input);
    stop_recording(&mut child);

    if std::path::Path::new(TEMP_WAV).exists() {
        Ok(())
    } else {
        Err("parecord failed".into())
    }
}

fn record_alsa_until_stopped() -> Result<(), Box<dyn std::error::Error>> {
    let mut child = Command::new("arecord")
        .args(["-r", "16000", "-c", "1", "-f", "S16_LE", TEMP_WAV])
        .stdin(Stdio::null())
        .stderr(Stdio::inherit())
        .spawn()?;

    let mut input = String::new();
    let _ = std::io::stdin().read_line(&mut input);
    stop_recording(&mut child);

    if std::path::Path::new(TEMP_WAV).exists() {
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
        .args(["-y", "-i", audio_path, "-ar", "16000", "-ac", "1", "-f", "wav", TEMP_CONVERTED])
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

fn send_to_daemon(audio_path: &str) -> Result<String, Box<dyn std::error::Error>> {
    let mut stream = UnixStream::connect(SOCKET_PATH).map_err(|e| {
        format!(
            "Cannot connect to daemon at {}. Is transcribe-daemon running? Error: {}",
            SOCKET_PATH, e
        )
    })?;

    stream.set_read_timeout(Some(Duration::from_secs(30)))?;

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
