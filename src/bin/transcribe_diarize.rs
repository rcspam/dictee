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
            eprintln!("Usage: transcribe-diarize <audio> [model_dir] [sortformer_dir]");
            eprintln!();
            eprintln!("Arguments:");
            eprintln!("  <audio>          Fichier audio (tout format supporté par ffmpeg)");
            eprintln!("  [model_dir]      Répertoire du modèle TDT (défaut: /usr/share/parakeet-transcribe/tdt)");
            eprintln!("  [sortformer_dir] Répertoire Sortformer (défaut: /usr/share/parakeet-transcribe/sortformer)");
            return Ok(());
        }

        if args.len() < 2 {
            eprintln!("Usage: transcribe-diarize <audio> [model_dir] [sortformer_dir]");
            eprintln!("  audio:          Audio file (any format supported by ffmpeg)");
            eprintln!("  model_dir:      Path to TDT model (default: /usr/share/parakeet-transcribe/tdt)");
            eprintln!("  sortformer_dir: Path to Sortformer model (default: /usr/share/parakeet-transcribe/sortformer)");
            std::process::exit(1);
        }

        let audio_path = resolve_path(&args[1])?;
        let model_dir = args.get(2).map(|s| s.as_str()).unwrap_or("/usr/share/parakeet-transcribe/tdt");
        let sortformer_dir = args.get(3).map(|s| s.as_str()).unwrap_or("/usr/share/parakeet-transcribe/sortformer");

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

        // Configure execution
        #[cfg(feature = "cuda")]
        let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cuda);
        #[cfg(not(feature = "cuda"))]
        let config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cpu);

        // Load Sortformer for diarization
        let sortformer_path = format!("{}/diar_streaming_sortformer_4spk-v2.1.onnx", sortformer_dir);
        let mut sortformer = Sortformer::with_config(
            &sortformer_path,
            Some(config.clone()),
            DiarizationConfig::callhome(),
        )?;

        // Get speaker segments
        let speaker_segments = sortformer.diarize(audio.clone(), spec.sample_rate, spec.channels)?;

        // Load TDT for transcription
        let mut parakeet = ParakeetTDT::from_pretrained(model_dir, Some(config))?;

        // Transcribe with sentence timestamps
        let result = parakeet.transcribe_samples(
            audio,
            spec.sample_rate,
            spec.channels,
            Some(TimestampMode::Sentences),
        )?;

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

            println!("[{:.2}s - {:.2}s] {}: {}", segment.start, segment.end, speaker, segment.text);
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
