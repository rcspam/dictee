#[cfg(feature = "sortformer")]
use parakeet_rs::sortformer::{DiarizationConfig, Sortformer};
#[cfg(feature = "sortformer")]
use parakeet_rs::ExecutionConfig;
#[cfg(feature = "sortformer")]
use std::env;
#[cfg(feature = "sortformer")]
use std::fs;
#[cfg(feature = "sortformer")]
use std::process::{Command, Stdio};

#[cfg(feature = "sortformer")]
const TEMP_CONVERTED: &str = "/tmp/diarize_only_converted.wav";

fn main() -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(not(feature = "sortformer"))]
    {
        eprintln!("Error: This binary requires the 'sortformer' feature.");
        eprintln!("Compile with: cargo build --features \"sortformer\"");
        std::process::exit(1);
    }

    #[cfg(feature = "sortformer")]
    {
        let debug = env::var("DICTEE_DEBUG").unwrap_or_default() == "true";
        macro_rules! dbg_print {
            ($($arg:tt)*) => {
                if debug { eprintln!("[DBG diarize-only] {}", format!($($arg)*)); }
            };
        }

        let args: Vec<String> = env::args().collect();

        if args.iter().any(|a| a == "--help" || a == "-h") {
            eprintln!("diarize-only - Diarisation seule (Sortformer, sans transcription)");
            eprintln!();
            eprintln!("Usage: diarize-only [OPTIONS] <audio> [sortformer_dir]");
            eprintln!("       diarize-only --stream [OPTIONS] [sortformer_dir]");
            eprintln!();
            eprintln!("Arguments:");
            eprintln!("  <audio>          Fichier audio (tout format supporté par ffmpeg)");
            eprintln!("  [sortformer_dir] Répertoire Sortformer (défaut: /usr/share/dictee/sortformer)");
            eprintln!();
            eprintln!("Options:");
            eprintln!("  --sensitivity <0.0-1.0>  Detection threshold (default: 0.5)");
            eprintln!("  --stream                 Mode streaming (lit FILE: <path> sur stdin)");
            eprintln!();
            eprintln!("Output: start_seconds end_seconds speaker_id (one segment per line)");
            return Ok(());
        }

        if args.len() < 2 {
            eprintln!("Usage: diarize-only <audio> [sortformer_dir]");
            std::process::exit(1);
        }

        // Parse options
        let mut sensitivity: f32 = 0.5;
        let mut stream_mode = false;
        let mut positional_args: Vec<String> = Vec::new();
        let mut i = 1;
        while i < args.len() {
            if args[i] == "--sensitivity" && i + 1 < args.len() {
                sensitivity = args[i + 1].parse().unwrap_or(0.5);
                sensitivity = sensitivity.clamp(0.0, 1.0);
                i += 2;
            } else if args[i] == "--stream" {
                stream_mode = true;
                i += 1;
            } else {
                positional_args.push(args[i].clone());
                i += 1;
            }
        }
        if !stream_mode && positional_args.is_empty() {
            eprintln!("Error: missing audio file argument");
            std::process::exit(1);
        }

        let home = std::env::var("HOME").unwrap_or_else(|_| "/root".to_string());
        let default_sf = {
            let user = format!("{}/.local/share/dictee/sortformer", home);
            if std::path::Path::new(&user).exists() { user }
            else { "/usr/share/dictee/sortformer".to_string() }
        };
        // In stream mode, positional_args[0] is sortformer_dir (optional)
        let sortformer_dir = if stream_mode {
            positional_args.first().map(|s| s.to_string()).unwrap_or(default_sf)
        } else {
            positional_args.get(1).map(|s| s.to_string()).unwrap_or(default_sf)
        };

        if stream_mode {
            return run_stream_mode(&sortformer_dir, sensitivity);
        }

        let audio_path = resolve_path(&positional_args[0])?;
        dbg_print!("audio={}, sensitivity={:.2}", audio_path, sensitivity);

        dbg_print!("sortformer_dir={}", sortformer_dir);

        // Convert to WAV 16kHz mono if needed
        let (wav_path, needs_cleanup) = ensure_wav(&audio_path)?;
        dbg_print!("wav={}, converted={}", wav_path, needs_cleanup);

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

        // Load Sortformer — try CUDA first, fallback to CPU
        let sortformer_path = format!("{}/diar_streaming_sortformer_4spk-v2.1.onnx", sortformer_dir);
        let diar_config = if (sensitivity - 0.5).abs() < 0.01 {
            dbg_print!("config=callhome (default)");
            DiarizationConfig::callhome()
        } else {
            let onset = 0.4 + sensitivity * 0.3;
            let offset = 0.3 + sensitivity * 0.3;
            dbg_print!("config=custom onset={:.3} offset={:.3}", onset, offset);
            DiarizationConfig::custom(onset, offset)
        };
        // Runtime provider probe + safety-net retry on CPU if GPU init crashes
        // late (e.g. driver insufficient for runtime version).
        let provider = parakeet_rs::best_provider();
        let cfg = ExecutionConfig::new().with_execution_provider(provider);
        let mut sortformer = match Sortformer::with_config(&sortformer_path, Some(cfg), diar_config.clone()) {
            Ok(sf) => sf,
            Err(e) if provider != parakeet_rs::ExecutionProvider::Cpu => {
                eprintln!("[dictee] Sortformer GPU init failed ({}); retrying on CPU.", e);
                let cpu_cfg = ExecutionConfig::new()
                    .with_execution_provider(parakeet_rs::ExecutionProvider::Cpu);
                Sortformer::with_config(&sortformer_path, Some(cpu_cfg), diar_config)?
            }
            Err(e) => return Err(e.into()),
        };

        dbg_print!("model loaded, audio={} samples, rate={}, channels={}", audio.len(), spec.sample_rate, spec.channels);

        // Run diarization — output: start end speaker_id
        let segments = sortformer.diarize(audio, spec.sample_rate, spec.channels)?;

        let n_speakers: std::collections::HashSet<_> = segments.iter().map(|s| s.speaker_id).collect();
        dbg_print!("done: {} segments, {} speakers", segments.len(), n_speakers.len());

        for seg in &segments {
            println!("{:.2} {:.2} {}", seg.start, seg.end, seg.speaker_id);
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

#[cfg(feature = "sortformer")]
fn run_stream_mode(sortformer_dir: &str, sensitivity: f32) -> Result<(), Box<dyn std::error::Error>> {
    use std::io::{BufRead, BufReader, Write};

    let diar_config = if (sensitivity - 0.5).abs() < 0.01 {
        DiarizationConfig::callhome()
    } else {
        let onset = 0.4 + sensitivity * 0.3;
        let offset = 0.3 + sensitivity * 0.3;
        DiarizationConfig::custom(onset, offset)
    };

    let sortformer_path = format!("{}/diar_streaming_sortformer_4spk-v2.1.onnx", sortformer_dir);
    let provider = parakeet_rs::best_provider();
    let cfg = ExecutionConfig::new().with_execution_provider(provider);
    let mut sortformer = match Sortformer::with_config(&sortformer_path, Some(cfg), diar_config.clone()) {
        Ok(sf) => sf,
        Err(e) if provider != parakeet_rs::ExecutionProvider::Cpu => {
            eprintln!("[diarize-only --stream] GPU init failed ({}); retrying on CPU.", e);
            let cpu_cfg = ExecutionConfig::new()
                .with_execution_provider(parakeet_rs::ExecutionProvider::Cpu);
            Sortformer::with_config(&sortformer_path, Some(cpu_cfg), diar_config)?
        }
        Err(e) => return Err(e.into()),
    };

    let stdin = std::io::stdin();
    let mut stdout = std::io::stdout();
    let mut reader = BufReader::new(stdin.lock());
    let mut line = String::new();

    eprintln!("[diarize-only --stream] ready");

    loop {
        line.clear();
        let n = reader.read_line(&mut line)?;
        if n == 0 {
            eprintln!("[diarize-only --stream] EOF, exiting");
            break;
        }
        let cmd = line.trim();
        if cmd.is_empty() { continue; }
        if cmd == "RESET" {
            sortformer.reset_state();
            writeln!(stdout, "RESET_OK")?;
            stdout.flush()?;
        } else if let Some(path) = cmd.strip_prefix("FILE: ") {
            match diarize_chunk(&mut sortformer, path) {
                Ok(segments) => {
                    for seg in &segments {
                        writeln!(stdout, "{:.3} {:.3} {}", seg.start, seg.end, seg.speaker_id)?;
                    }
                    writeln!(stdout)?;
                    stdout.flush()?;
                }
                Err(e) => {
                    writeln!(stdout, "ERROR: {}", e)?;
                    stdout.flush()?;
                }
            }
        } else {
            writeln!(stdout, "ERROR: unknown command")?;
            stdout.flush()?;
        }
    }
    Ok(())
}

#[cfg(feature = "sortformer")]
fn diarize_chunk(
    sortformer: &mut Sortformer,
    path: &str,
) -> Result<Vec<parakeet_rs::sortformer::SpeakerSegment>, Box<dyn std::error::Error>> {
    let (wav_path, needs_cleanup) = ensure_wav(path)?;
    let mut reader = hound::WavReader::open(&wav_path)?;
    let spec = reader.spec();
    let audio: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().collect::<Result<Vec<_>, _>>()?,
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.map(|v| v as f32 / 32768.0))
            .collect::<Result<Vec<_>, _>>()?,
    };
    if needs_cleanup {
        let _ = fs::remove_file(&wav_path);
    }
    let segments = sortformer.diarize_streaming(audio, spec.sample_rate, spec.channels)?;
    Ok(segments)
}
