#[cfg(feature = "sortformer")]
use parakeet_rs::sortformer::{DiarizationConfig, Sortformer};
#[cfg(feature = "sortformer")]
use parakeet_rs::{ExecutionConfig, ExecutionProvider, ParakeetTDT, TimestampMode, Transcriber};
#[cfg(feature = "sortformer")]
use std::env;
#[cfg(feature = "sortformer")]
use std::fs;
#[cfg(feature = "sortformer")]
use std::process::{Command, Stdio};

#[cfg(feature = "sortformer")]
const TEMP_CONVERTED: &str = "/tmp/transcribe_diarize_converted.wav";

fn main() -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(not(feature = "sortformer"))]
    {
        eprintln!("Error: This binary requires the 'sortformer' feature.");
        eprintln!("Compile with: cargo build --features \"cuda,sortformer\"");
        std::process::exit(1);
    }

    #[cfg(feature = "sortformer")]
    {
        let args: Vec<String> = env::args().collect();

        if args.iter().any(|a| a == "--help" || a == "-h") {
            eprintln!("transcribe-diarize - Transcription + identification des locuteurs");
            eprintln!();
            eprintln!("Usage: transcribe-diarize [OPTIONS] <audio> [model_dir] [sortformer_dir]");
            eprintln!();
            eprintln!("Arguments:");
            eprintln!("  <audio>          Fichier audio (tout format supporté par ffmpeg)");
            eprintln!("  [model_dir]      Répertoire du modèle TDT (défaut: /usr/share/dictee/tdt)");
            eprintln!("  [sortformer_dir] Répertoire Sortformer (défaut: /usr/share/dictee/sortformer)");
            eprintln!();
            eprintln!("Options:");
            eprintln!("  --sensitivity <0.0-1.0>  Detection threshold (default: 0.5)");
            eprintln!("                           0.0 = very sensitive (more speakers detected)");
            eprintln!("                           1.0 = very strict (fewer speakers detected)");
            return Ok(());
        }

        if args.len() < 2 {
            eprintln!("Usage: transcribe-diarize <audio> [model_dir] [sortformer_dir]");
            eprintln!("  audio:          Audio file (any format supported by ffmpeg)");
            eprintln!("  model_dir:      Path to TDT model (default: /usr/share/dictee/tdt)");
            eprintln!("  sortformer_dir: Path to Sortformer model (default: /usr/share/dictee/sortformer)");
            std::process::exit(1);
        }

        // Parse --sensitivity option
        let mut sensitivity: f32 = 0.5;
        let mut positional_args: Vec<String> = Vec::new();
        let mut i = 1;
        while i < args.len() {
            if args[i] == "--sensitivity" && i + 1 < args.len() {
                sensitivity = args[i + 1].parse().unwrap_or(0.5);
                sensitivity = sensitivity.clamp(0.0, 1.0);
                i += 2;
            } else {
                positional_args.push(args[i].clone());
                i += 1;
            }
        }
        if positional_args.is_empty() {
            eprintln!("Error: missing audio file argument");
            std::process::exit(1);
        }

        let audio_path = resolve_path(&positional_args[0])?;
        let home = std::env::var("HOME").unwrap_or_else(|_| "/root".to_string());
        let default_tdt = if std::path::Path::new("/usr/share/dictee/tdt/vocab.txt").exists() {
            "/usr/share/dictee/tdt".to_string()
        } else {
            format!("{}/.local/share/dictee/tdt", home)
        };
        let default_sf = if std::path::Path::new("/usr/share/dictee/sortformer").exists() {
            "/usr/share/dictee/sortformer".to_string()
        } else {
            format!("{}/.local/share/dictee/sortformer", home)
        };
        let model_dir = positional_args.get(1).map(|s| s.to_string()).unwrap_or(default_tdt);
        let sortformer_dir = positional_args.get(2).map(|s| s.to_string()).unwrap_or(default_sf);

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

        // Free GPU VRAM: stop ASR daemons if they hold the GPU
        #[cfg(feature = "cuda")]
        let daemon_was_active = stop_daemons_for_vram();
        #[cfg(not(feature = "cuda"))]
        let daemon_was_active = false;

        // Configure execution
        #[cfg(feature = "cuda")]
        let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cuda);
        #[cfg(not(feature = "cuda"))]
        let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cpu);

        // Load Sortformer for diarization
        let sortformer_path = format!("{}/diar_streaming_sortformer_4spk-v2.1.onnx", sortformer_dir);
        // Map sensitivity (0=sensitive, 1=strict) to onset/offset thresholds
        let diar_config = if (sensitivity - 0.5).abs() < 0.01 {
            DiarizationConfig::callhome()  // default
        } else {
            // onset: 0.4 (sensitive) to 0.7 (strict)
            // offset: 0.3 (sensitive) to 0.6 (strict)
            let onset = 0.4 + sensitivity * 0.3;
            let offset = 0.3 + sensitivity * 0.3;
            DiarizationConfig::custom(onset, offset)
        };

        let mut sortformer = Sortformer::with_config(
            &sortformer_path,
            Some(config.clone()),
            diar_config,
        )?;

        // Get speaker segments
        let speaker_segments = sortformer.diarize(audio.clone(), spec.sample_rate, spec.channels)?;

        // Load TDT for transcription
        let mut parakeet = ParakeetTDT::from_pretrained(&model_dir, Some(config))?;

        // Transcribe with sentence timestamps
        let result = parakeet.transcribe_samples(
            audio,
            spec.sample_rate,
            spec.channels,
            Some(TimestampMode::Sentences),
        )?;

        // Check if dictee-postprocess is available
        let has_postprocess = which("dictee-postprocess");
        let lang_source = read_conf_value("DICTEE_LANG_SOURCE")
            .or_else(|| env::var("LANG").ok().map(|l| l[..2].to_string()))
            .unwrap_or_else(|| "fr".to_string());

        // Match speakers to sentences
        for segment in &result.tokens {
            let speaker = speaker_segments
                .iter()
                .filter_map(|s| {
                    let overlap_start = segment.start.max(s.start);
                    let overlap_end = segment.end.min(s.end);
                    let overlap = (overlap_end - overlap_start).max(0.0);
                    if overlap > 0.0 {
                        Some((s.speaker_id, overlap))
                    } else {
                        None
                    }
                })
                .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
                .map(|(id, _)| format!("Speaker {}", id))
                .unwrap_or_else(|| "UNKNOWN".to_string());

            let text = if has_postprocess {
                postprocess(&segment.text, &lang_source)
            } else {
                segment.text.clone()
            };

            println!("[{:.2}s - {:.2}s] {}: {}", segment.start, segment.end, speaker, text);
        }

        // Drop models to free VRAM before restarting daemon
        drop(parakeet);
        drop(sortformer);

        // Restart daemon if we stopped it
        if daemon_was_active {
            restart_daemons();
        }

        Ok(())
    }
}

#[cfg(feature = "sortformer")]
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

#[cfg(feature = "sortformer")]
fn is_wav_16k_mono(path: &str) -> bool {
    let Ok(reader) = hound::WavReader::open(path) else { return false };
    let spec = reader.spec();
    spec.sample_rate == 16000 && spec.channels == 1
}

#[cfg(feature = "sortformer")]
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

/// Check if a command exists in PATH.
#[cfg(feature = "sortformer")]
fn which(cmd: &str) -> bool {
    env::var("PATH")
        .unwrap_or_default()
        .split(':')
        .any(|dir| std::path::Path::new(dir).join(cmd).is_file())
}

/// Read a value from ~/.config/dictee.conf.
#[cfg(feature = "sortformer")]
fn read_conf_value(key: &str) -> Option<String> {
    let conf_path = format!(
        "{}/.config/dictee.conf",
        env::var("HOME").unwrap_or_else(|_| "/root".to_string())
    );
    fs::read_to_string(&conf_path)
        .unwrap_or_default()
        .lines()
        .find(|l| l.starts_with(&format!("{}=", key)))
        .and_then(|l| l.split('=').nth(1))
        .map(|v| v.trim().trim_matches('"').trim_matches('\'').to_string())
}

/// Pipe text through dictee-postprocess.
#[cfg(feature = "sortformer")]
fn postprocess(text: &str, lang: &str) -> String {
    Command::new("dictee-postprocess")
        .env("DICTEE_LANG_SOURCE", lang)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .and_then(|mut child| {
            if let Some(ref mut stdin) = child.stdin {
                use std::io::Write;
                let _ = stdin.write_all(text.as_bytes());
            }
            child.wait_with_output()
        })
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| text.to_string())
}

/// Stop ASR daemons to free GPU VRAM. Returns true if any daemon was active.
#[cfg(all(feature = "sortformer", feature = "cuda"))]
fn stop_daemons_for_vram() -> bool {
    // Check if any daemon is using the GPU
    let gpu_procs = Command::new("nvidia-smi")
        .args(["--query-compute-apps=name", "--format=csv,noheader"])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .unwrap_or_default();

    if !gpu_procs.contains("transcribe-daemon") {
        return false;
    }

    eprintln!("Stopping ASR daemon to free GPU VRAM...");
    let _ = Command::new("systemctl")
        .args(["--user", "stop", "dictee", "dictee-vosk", "dictee-whisper", "dictee-canary"])
        .status();
    // Wait for VRAM to be released
    std::thread::sleep(std::time::Duration::from_secs(1));
    true
}

/// Restart the configured ASR daemon.
#[cfg(feature = "sortformer")]
fn restart_daemons() {
    // Read config to find which backend to restart
    let conf_path = format!(
        "{}/.config/dictee.conf",
        env::var("HOME").unwrap_or_else(|_| "/root".to_string())
    );
    let backend = fs::read_to_string(&conf_path)
        .unwrap_or_default()
        .lines()
        .find(|l| l.starts_with("DICTEE_ASR_BACKEND="))
        .and_then(|l| l.split('=').nth(1))
        .map(|v| v.trim().trim_matches('"').trim_matches('\'').to_string())
        .unwrap_or_else(|| "parakeet".to_string());

    let svc = match backend.as_str() {
        "vosk" => "dictee-vosk",
        "whisper" => "dictee-whisper",
        "canary" => "dictee-canary",
        _ => "dictee",
    };
    eprintln!("Restarting {} daemon...", svc);
    let _ = Command::new("systemctl")
        .args(["--user", "start", svc])
        .status();
}
