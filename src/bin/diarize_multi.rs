// diarize-multi — multi-speaker diarization (no 4-speaker cap) via the
// in-house src/diar/ engine (pyannote segmentation + WeSpeaker embeddings +
// AHC/PLDA/VBx clustering).
//
// Drop-in sibling of diarize-only: same stdout contract, one line per speaker
// turn: "start end speaker_id" (seconds, contiguous integer ids in order of
// first appearance).

#[cfg(feature = "diar")]
use parakeet_rs::diar::{Diarizer, PipelineConfig};
#[cfg(feature = "diar")]
use parakeet_rs::ExecutionConfig;
#[cfg(feature = "diar")]
use std::env;
#[cfg(feature = "diar")]
use std::fs;
#[cfg(feature = "diar")]
use std::path::PathBuf;
#[cfg(feature = "diar")]
use std::process::{Command, Stdio};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(not(feature = "diar"))]
    {
        eprintln!("Error: This binary requires the 'diar' feature.");
        eprintln!("Compile with: cargo build --features \"diar\"");
        std::process::exit(1);
    }

    #[cfg(feature = "diar")]
    {
        let debug = env::var("DICTEE_DEBUG").unwrap_or_default() == "true";
        macro_rules! dbg_print {
            ($($arg:tt)*) => {
                if debug { eprintln!("[DBG diarize-multi] {}", format!($($arg)*)); }
            };
        }

        let args: Vec<String> = env::args().collect();
        if args.iter().any(|a| a == "--help" || a == "-h") {
            eprintln!("Usage: diarize-multi [OPTIONS] <audio>");
            eprintln!();
            eprintln!("Multi-speaker diarization (no 4-speaker cap). Prints one speaker");
            eprintln!("turn per line: 'start end speaker_id' in seconds.");
            eprintln!();
            eprintln!("Options:");
            eprintln!("  --num-speakers <N>     Force the exact speaker count (default: auto)");
            eprintln!("  --threshold <0.0-2.0>  AHC distance threshold (default: 0.6, lower = more speakers)");
            eprintln!("  --min-turn <secs>      Absorb speaker islands shorter than this when");
            eprintln!("                         bracketed by the same other speaker (default: 0.5, 0 = off)");
            eprintln!("  --models-dir <dir>     Model directory (default: ~/.local/share/dictee/diar");
            eprintln!("                         then /usr/share/dictee/diar)");
            eprintln!("  --rttm <file-id>       Output RTTM lines instead of 'start end id'");
            eprintln!("  --live                 Streaming mode: read 'FILE: <wav>' chunk paths on");
            eprintln!("                         stdin, print chunk-relative 'start end id' segments");
            eprintln!("                         plus a blank terminator line per chunk (drop-in");
            eprintln!("                         replacement for diarize-only --stream, no 4-cap)");
            eprintln!("  --overlap-secs <S>     Live mode: seconds of overlap between consecutive");
            eprintln!("                         chunks (default: 10)");
            std::process::exit(0);
        }

        let mut threshold: f32 = 0.6;
        let mut num_speakers: Option<usize> = None;
        let mut models_dir: Option<PathBuf> = None;
        let mut rttm_id: Option<String> = None;
        let mut live = false;
        let mut overlap_secs: f64 = 10.0;
        let mut min_turn: Option<f64> = None;
        let mut positional: Vec<String> = Vec::new();
        let mut i = 1;
        while i < args.len() {
            match args[i].as_str() {
                "--live" => {
                    live = true;
                }
                "--overlap-secs" if i + 1 < args.len() => {
                    overlap_secs = args[i + 1].parse()?;
                    i += 1;
                }
                "--threshold" if i + 1 < args.len() => {
                    threshold = args[i + 1].parse()?;
                    i += 1;
                }
                "--min-turn" if i + 1 < args.len() => {
                    min_turn = Some(args[i + 1].parse()?);
                    i += 1;
                }
                "--num-speakers" if i + 1 < args.len() => {
                    num_speakers = Some(args[i + 1].parse()?);
                    i += 1;
                }
                "--models-dir" if i + 1 < args.len() => {
                    models_dir = Some(PathBuf::from(&args[i + 1]));
                    i += 1;
                }
                "--rttm" if i + 1 < args.len() => {
                    rttm_id = Some(args[i + 1].clone());
                    i += 1;
                }
                s if s.starts_with('-') => {
                    return Err(format!("unknown option '{s}' (see --help)").into());
                }
                s => positional.push(s.to_string()),
            }
            i += 1;
        }
        let models_dir = match models_dir {
            Some(dir) => dir,
            None => default_models_dir()?,
        };
        dbg_print!("models dir: {}", models_dir.display());

        if live {
            return run_live_mode(&models_dir, threshold, overlap_secs, debug);
        }

        let audio_path = positional
            .first()
            .ok_or("missing <audio> argument (see --help)")?
            .clone();

        // Convert to WAV 16kHz mono if needed (same idiom as diarize-only).
        let (wav_path, needs_cleanup) = ensure_wav(&audio_path)?;
        dbg_print!("wav={}, converted={}", wav_path, needs_cleanup);

        let mut reader = hound::WavReader::open(&wav_path)?;
        let spec = reader.spec();
        if spec.sample_rate != 16000 || spec.channels != 1 {
            if needs_cleanup {
                let _ = fs::remove_file(&wav_path);
            }
            return Err(format!(
                "expected 16 kHz mono WAV after conversion, got {} Hz / {} ch",
                spec.sample_rate, spec.channels
            )
            .into());
        }
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
        dbg_print!("audio: {:.1}s", audio.len() as f64 / 16000.0);

        // Runtime provider probe + safety-net retry on CPU if GPU init crashes
        // late (e.g. driver insufficient for runtime version).
        let provider = parakeet_rs::best_provider();
        let cfg = ExecutionConfig::new().with_execution_provider(provider);
        let mut diarizer = match Diarizer::from_dir(&models_dir, Some(cfg)) {
            Ok(d) => d,
            Err(e) if provider != parakeet_rs::ExecutionProvider::Cpu => {
                eprintln!("[dictee] diarize-multi GPU init failed ({}); retrying on CPU.", e);
                let cpu_cfg = ExecutionConfig::new()
                    .with_execution_provider(parakeet_rs::ExecutionProvider::Cpu);
                Diarizer::from_dir(&models_dir, Some(cpu_cfg))?
            }
            Err(e) => return Err(e.into()),
        };

        let mut config = PipelineConfig::default();
        config.ahc.threshold = threshold;
        config.ahc.num_clusters = num_speakers;
        if let Some(mt) = min_turn {
            config.min_turn_duration = mt;
        }

        let result = diarizer.diarize(&audio, &config)?;

        if let Some(file_id) = rttm_id {
            print!("{}", result.rttm(&file_id));
        } else {
            // Map "SPEAKER_NN" labels to contiguous integer ids in order of
            // first appearance, mirroring the sortformer diarize-only output.
            let mut ids: Vec<String> = Vec::new();
            for seg in &result.segments {
                let id = match ids.iter().position(|s| s == &seg.speaker) {
                    Some(idx) => idx,
                    None => {
                        ids.push(seg.speaker.clone());
                        ids.len() - 1
                    }
                };
                println!("{:.2} {:.2} {}", seg.start, seg.end, id);
            }
        }

        let n_speakers: std::collections::HashSet<_> =
            result.segments.iter().map(|s| &s.speaker).collect();
        dbg_print!(
            "done: {} segments, {} speakers",
            result.segments.len(),
            n_speakers.len()
        );

        Ok(())
    }
}

/// Streaming mode: drop-in replacement for `diarize-only --stream` without
/// the 4-speaker cap. Same wire protocol: `FILE: <wav>` per stdin line (16 kHz
/// mono chunks that overlap the previous chunk by `overlap_secs`), chunk-
/// relative `start end speaker_id` lines plus one blank terminator line on
/// stdout, `RESET`/`RESET_OK`, `ERROR: ...` on chunk failure, and a stderr
/// line containing "ready" once the models are loaded.
#[cfg(feature = "diar")]
fn run_live_mode(
    models_dir: &std::path::Path,
    threshold: f32,
    overlap_secs: f64,
    debug: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    use std::io::{BufRead, Write};

    use parakeet_rs::diar::live::{LiveConfig, LiveDiarizer};

    let mut config = LiveConfig::default();
    config.pipeline.ahc.threshold = threshold;

    let provider = parakeet_rs::best_provider();
    let exec = ExecutionConfig::new().with_execution_provider(provider);
    let mut diarizer = match LiveDiarizer::from_dir(models_dir, Some(exec), config.clone()) {
        Ok(d) => d,
        Err(e) if provider != parakeet_rs::ExecutionProvider::Cpu => {
            eprintln!(
                "[diarize-multi --live] GPU init failed ({}); retrying on CPU.",
                e
            );
            let cpu = ExecutionConfig::new()
                .with_execution_provider(parakeet_rs::ExecutionProvider::Cpu);
            LiveDiarizer::from_dir(models_dir, Some(cpu), config)?
        }
        Err(e) => return Err(e.into()),
    };

    let stdin = std::io::stdin();
    let mut reader = stdin.lock();
    let stdout_handle = std::io::stdout();
    let mut stdout = stdout_handle.lock();
    let mut first_chunk = true;

    eprintln!("[diarize-multi --live] ready");

    let mut line = String::new();
    loop {
        line.clear();
        if reader.read_line(&mut line)? == 0 {
            eprintln!("[diarize-multi --live] EOF, exiting");
            break;
        }
        let cmd = line.trim();
        if cmd.is_empty() {
            continue;
        }
        if cmd == "RESET" {
            diarizer.reset();
            first_chunk = true;
            writeln!(stdout, "RESET_OK")?;
            stdout.flush()?;
            continue;
        }
        if let Some(path) = cmd.strip_prefix("FILE: ") {
            match live_chunk(&mut diarizer, path, first_chunk, overlap_secs) {
                Ok((turns, chunk_start)) => {
                    for t in &turns {
                        writeln!(
                            stdout,
                            "{:.3} {:.3} {}",
                            t.start - chunk_start,
                            t.end - chunk_start,
                            t.speaker
                        )?;
                    }
                    writeln!(stdout)?;
                    stdout.flush()?;
                    first_chunk = false;
                    if debug {
                        eprintln!(
                            "[DBG diarize-multi --live] {} turns, timeline end {:.1}s",
                            turns.len(),
                            diarizer.total_seconds()
                        );
                    }
                }
                Err(e) => {
                    writeln!(stdout, "ERROR: {e}")?;
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

/// Feed one meeting chunk into the live diarizer and return its speaker
/// turns (global timeline) plus the chunk's global start time.
#[cfg(feature = "diar")]
fn live_chunk(
    diarizer: &mut parakeet_rs::diar::live::LiveDiarizer,
    path: &str,
    first_chunk: bool,
    overlap_secs: f64,
) -> Result<(Vec<parakeet_rs::diar::live::LiveTurn>, f64), Box<dyn std::error::Error>> {
    if !std::path::Path::new(path).exists() {
        return Err(format!("file not found: {}", path).into());
    }
    let mut reader = hound::WavReader::open(path)?;
    let spec = reader.spec();
    if spec.sample_rate != 16000 || spec.channels != 1 {
        return Err(format!(
            "expected 16 kHz mono WAV chunk, got {} Hz / {} ch",
            spec.sample_rate, spec.channels
        )
        .into());
    }
    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().collect::<Result<Vec<_>, _>>()?,
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.map(|v| v as f32 / 32768.0))
            .collect::<Result<Vec<_>, _>>()?,
    };
    let chunk_secs = samples.len() as f64 / 16000.0;
    // Every chunk after the first re-sends `overlap_secs` of already-pushed
    // audio (the meeting chunker's fixed overlap): skip it.
    let skip = if first_chunk {
        0
    } else {
        ((overlap_secs * 16000.0).round() as usize).min(samples.len())
    };
    diarizer.push_audio(&samples[skip..])?;
    let end = diarizer.total_seconds();
    let chunk_start = (end - chunk_secs).max(0.0);
    let turns = diarizer.turns_in_range(chunk_start, end)?;
    Ok((turns, chunk_start))
}

/// User model dir first (local overrides), then the system dir. The
/// segmentation model is the sentinel.
#[cfg(feature = "diar")]
fn default_models_dir() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let sentinel = parakeet_rs::diar::SEGMENTATION_ONNX;
    let user_dir = PathBuf::from(format!(
        "{}/.local/share/dictee/diar",
        env::var("HOME").unwrap_or_else(|_| "/root".to_string())
    ));
    if user_dir.join(sentinel).exists() {
        return Ok(user_dir);
    }
    let sys_dir = PathBuf::from("/usr/share/dictee/diar");
    if sys_dir.join(sentinel).exists() {
        return Ok(sys_dir);
    }
    Err(format!(
        "diarization models not found ({} missing from {} and {})",
        sentinel,
        user_dir.display(),
        sys_dir.display()
    )
    .into())
}

#[cfg(feature = "diar")]
fn is_wav_16k_mono(path: &str) -> bool {
    let Ok(reader) = hound::WavReader::open(path) else {
        return false;
    };
    let spec = reader.spec();
    spec.sample_rate == 16000 && spec.channels == 1
}

#[cfg(feature = "diar")]
fn ensure_wav(audio_path: &str) -> Result<(String, bool), Box<dyn std::error::Error>> {
    if is_wav_16k_mono(audio_path) {
        return Ok((audio_path.to_string(), false));
    }

    let uid = unsafe { libc::getuid() };
    let tmp_path = format!("/tmp/diarize_multi_converted-{uid}.wav");
    let status = Command::new("ffmpeg")
        .args(["-y", "-i", audio_path, "-ar", "16000", "-ac", "1", "-f", "wav", &tmp_path])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|e| format!("ffmpeg not found: {}. Install ffmpeg to convert audio files.", e))?;

    if !status.success() {
        return Err(format!(
            "ffmpeg failed to convert '{}' (exit code: {:?})",
            audio_path,
            status.code()
        )
        .into());
    }

    Ok((tmp_path, true))
}
