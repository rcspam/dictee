//! Streaming transcription with speaker diarization (English only)
//!
//! Usage:
//!   transcribe-stream-diarize [audio]     # From file (any format)
//!   transcribe-stream-diarize             # From microphone (record until Ctrl+C)
//!
//! Requires: nemotron model + sortformer model

#[cfg(feature = "sortformer")]
use parakeet_rs::sortformer::{DiarizationConfig, Sortformer};
#[cfg(feature = "sortformer")]
use parakeet_rs::{best_provider, ExecutionConfig, ExecutionProvider, Nemotron};
#[cfg(feature = "sortformer")]
use std::env;
use std::path::Path;
#[cfg(feature = "sortformer")]
use std::fs;
#[cfg(feature = "sortformer")]
use std::io::Write;
#[cfg(feature = "sortformer")]
use std::process::{Command, Stdio};
#[cfg(feature = "sortformer")]
use std::sync::atomic::{AtomicBool, Ordering};
#[cfg(feature = "sortformer")]
use std::sync::Arc;

#[cfg(feature = "sortformer")]
const TEMP_CONVERTED: &str = "/tmp/transcribe_stream_converted.wav";

fn main() -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(not(feature = "sortformer"))]
    {
        eprintln!("Error: This binary requires the 'sortformer' feature.");
        std::process::exit(1);
    }

    #[cfg(feature = "sortformer")]
    {
        let args: Vec<String> = env::args().collect();

        if args.iter().any(|a| a == "--help" || a == "-h") {
            eprintln!("transcribe-stream-diarize - Transcription streaming + diarisation (anglais uniquement)");
            eprintln!();
            eprintln!("Usage:");
            eprintln!("  transcribe-stream-diarize [audio]   Transcrire un fichier (tout format)");
            eprintln!("  transcribe-stream-diarize            Enregistrer depuis le micro (Ctrl+C)");
            eprintln!();
            eprintln!("Variables d'environnement:");
            eprintln!("  NEMOTRON_DIR    Répertoire Nemotron (défaut: /usr/share/dictee/nemotron)");
            eprintln!("  SORTFORMER_DIR  Répertoire Sortformer (défaut: /usr/share/dictee/sortformer)");
            eprintln!();
            eprintln!("Le micro est automatiquement démuté si nécessaire.");
            return Ok(());
        }

        let home = env::var("HOME").unwrap_or_else(|_| "/root".to_string());
        let nemotron_dir = env::var("NEMOTRON_DIR").unwrap_or_else(|_| {
            let user = format!("{}/.local/share/dictee/nemotron", home);
            if Path::new(&user).exists() { user }
            else { "/usr/share/dictee/nemotron".to_string() }
        });
        let sortformer_dir = env::var("SORTFORMER_DIR").unwrap_or_else(|_| {
            let user = format!("{}/.local/share/dictee/sortformer", home);
            if Path::new(&user).exists() { user }
            else { "/usr/share/dictee/sortformer".to_string() }
        });

        let audio: Vec<f32> = if args.len() > 1 {
            // Load from file (any format via ffmpeg)
            let path = resolve_path(&args[1])?;
            let (wav_path, needs_cleanup) = ensure_wav(&path)?;
            let audio = load_audio_file(&wav_path)?;
            if needs_cleanup {
                let _ = fs::remove_file(&wav_path);
            }
            audio
        } else {
            // Record from microphone (auto-unmute)
            let was_muted = unmute_mic();
            let result = record_from_mic();
            if was_muted { mute_mic(); }
            result?
        };

        if audio.is_empty() {
            eprintln!("No audio captured.");
            return Ok(());
        }

        let duration = audio.len() as f32 / 16000.0;
        eprintln!("\nProcessing {:.1}s of audio...\n", duration);

        // Load models — try CUDA first, fallback to CPU
        eprint!("Loading Nemotron... ");
        std::io::stderr().flush()?;
        // Runtime provider probe + safety-net retry on CPU if GPU init crashes late.
        let provider = best_provider();
        let cfg = ExecutionConfig::new().with_execution_provider(provider);
        let (mut nemotron, config) = match Nemotron::from_pretrained(&nemotron_dir, Some(cfg.clone())) {
            Ok(n) => {
                eprintln!("OK ({:?})", provider);
                (n, cfg)
            }
            Err(e) if provider != ExecutionProvider::Cpu => {
                eprintln!("GPU init failed ({}); retrying on CPU", e);
                let cpu_cfg = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cpu);
                eprint!("Loading Nemotron... ");
                let n = Nemotron::from_pretrained(&nemotron_dir, Some(cpu_cfg.clone()))?;
                eprintln!("OK (CPU)");
                (n, cpu_cfg)
            }
            Err(e) => return Err(e.into()),
        };

        eprint!("Loading Sortformer... ");
        std::io::stderr().flush()?;
        let sortformer_path = format!("{}/diar_streaming_sortformer_4spk-v2.1.onnx", sortformer_dir);
        let mut sortformer = Sortformer::with_config(
            &sortformer_path,
            Some(config),
            DiarizationConfig::callhome(),
        )?;
        eprintln!("OK\n");

        // Get speaker segments
        eprint!("Diarizing... ");
        std::io::stderr().flush()?;
        let speaker_segments = sortformer.diarize(audio.clone(), 16000, 1)?;
        eprintln!("found {} segments", speaker_segments.len());

        // Stream transcription and collect with timestamps
        eprintln!("\n=== Streaming transcription ===\n");

        let chunk_size = 8960; // 560ms for Nemotron
        let mut current_time = 0.0f32;
        let mut transcriptions: Vec<(f32, f32, String)> = Vec::new();
        let mut current_text = String::new();
        let mut segment_start = 0.0f32;

        for chunk in audio.chunks(chunk_size) {
            let chunk_vec = if chunk.len() < chunk_size {
                let mut p = chunk.to_vec();
                p.resize(chunk_size, 0.0);
                p
            } else {
                chunk.to_vec()
            };

            let text = nemotron.transcribe_chunk(&chunk_vec)?;
            if !text.is_empty() {
                print!("{}", text);
                std::io::stdout().flush()?;

                // Check for sentence boundaries
                if text.contains('.') || text.contains('?') || text.contains('!') {
                    current_text.push_str(&text);
                    transcriptions.push((segment_start, current_time, current_text.trim().to_string()));
                    current_text = String::new();
                    segment_start = current_time;
                } else {
                    current_text.push_str(&text);
                }
            }
            current_time += chunk_size as f32 / 16000.0;
        }

        // Flush remaining
        for _ in 0..3 {
            let text = nemotron.transcribe_chunk(&vec![0.0; chunk_size])?;
            if !text.is_empty() {
                print!("{}", text);
                current_text.push_str(&text);
            }
        }

        if !current_text.trim().is_empty() {
            transcriptions.push((segment_start, current_time, current_text.trim().to_string()));
        }

        println!("\n");

        // Match speakers to transcriptions
        eprintln!("=== Diarized result ===\n");

        for (start, end, text) in &transcriptions {
            if text.is_empty() {
                continue;
            }

            let speaker = speaker_segments
                .iter()
                .filter_map(|s| {
                    let overlap_start = start.max(s.start);
                    let overlap_end = end.min(s.end);
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

            println!("[{:05.2}s - {:05.2}s] {}: {}", start, end, speaker, text);
        }

        Ok(())
    }
}

#[cfg(feature = "sortformer")]
fn load_audio_file(path: &str) -> Result<Vec<f32>, Box<dyn std::error::Error>> {
    let mut reader = hound::WavReader::open(path)?;
    let spec = reader.spec();

    let mut audio: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().collect::<Result<Vec<_>, _>>()?,
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.map(|s| s as f32 / 32768.0))
            .collect::<Result<Vec<_>, _>>()?,
    };

    // Convert to mono if needed
    if spec.channels > 1 {
        audio = audio
            .chunks(spec.channels as usize)
            .map(|c| c.iter().sum::<f32>() / spec.channels as f32)
            .collect();
    }

    // Resample to 16kHz if needed (simple linear interpolation)
    if spec.sample_rate != 16000 {
        let ratio = spec.sample_rate as f32 / 16000.0;
        let new_len = (audio.len() as f32 / ratio) as usize;
        let mut resampled = Vec::with_capacity(new_len);
        for i in 0..new_len {
            let src_idx = i as f32 * ratio;
            let idx = src_idx as usize;
            let frac = src_idx - idx as f32;
            let sample = if idx + 1 < audio.len() {
                audio[idx] * (1.0 - frac) + audio[idx + 1] * frac
            } else {
                audio[idx]
            };
            resampled.push(sample);
        }
        audio = resampled;
    }

    // Normalize
    let max_val = audio.iter().fold(0.0f32, |a, &b| a.max(b.abs()));
    if max_val > 1e-6 {
        for s in &mut audio {
            *s /= max_val + 1e-5;
        }
    }

    Ok(audio)
}

#[cfg(feature = "sortformer")]
fn record_from_mic() -> Result<Vec<f32>, Box<dyn std::error::Error>> {
    let temp_file = "/tmp/stream_diarize_recording.wav";

    eprintln!("Recording from microphone... (Press Ctrl+C to stop)");
    eprintln!();

    // Set up Ctrl+C handler
    let running = Arc::new(AtomicBool::new(true));
    let r = running.clone();

    ctrlc::set_handler(move || {
        r.store(false, Ordering::SeqCst);
    })?;

    // Start recording with pw-record
    let mut child = Command::new("pw-record")
        .args([
            "--rate", "16000",
            "--channels", "1",
            "--format", "s16",
            temp_file,
        ])
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .spawn()?;

    // Wait for Ctrl+C
    while running.load(Ordering::SeqCst) {
        std::thread::sleep(std::time::Duration::from_millis(100));
    }

    // Stop recording
    unsafe {
        libc::kill(child.id() as i32, libc::SIGINT);
    }
    let _ = child.wait();

    eprintln!("\nRecording stopped.");

    // Load the recorded audio
    let audio = load_audio_file(temp_file)?;

    // Cleanup
    let _ = std::fs::remove_file(temp_file);

    Ok(audio)
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

#[cfg(feature = "sortformer")]
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
