use parakeet_rs::diar_pieces::{PieceParams, SpeakerSegment};
use parakeet_rs::nemotron3_diar::{Latency, Nemotron3Diarizer};
use parakeet_rs::ExecutionConfig;
use std::env;
use std::fs;
use std::process::{Command, Stdio};

const TEMP_CONVERTED: &str = "/tmp/diarize_only_converted.wav";

#[derive(Debug)]
struct DiarizeArgs {
    sensitivity: f32,
    stream: bool,
    /// `--pieces`: transcription pieces instead of speaker segments.
    pieces: Option<PieceParams>,
    /// `--latency`: Nemotron 3's chunking, offline for a file and low for a stream when not given.
    latency: Option<Latency>,
    positional: Vec<String>,
}

/// Seconds given to a piece option: a number, at least 1 for `--max-piece`, not negative for the
/// others.
fn piece_seconds(option: &str, value: Option<&String>) -> Result<f32, String> {
    let seconds = value
        .and_then(|v| v.parse::<f32>().ok())
        .filter(|s| s.is_finite())
        .ok_or_else(|| format!("{option} needs a number of seconds"))?;
    let min = if option == "--max-piece" { 1.0 } else { 0.0 };
    if seconds < min {
        return Err(format!("{option} must be at least {min} s"));
    }
    Ok(seconds)
}

/// Parse argv. Options and positional arguments mix in any order; anything that is not an option
/// stays a positional argument. `--engine nemotron3` is still accepted, Nemotron 3 being the only
/// engine since Sortformer was retired (2026-10).
fn parse_diarize_args(args: &[String]) -> Result<DiarizeArgs, String> {
    let mut out = DiarizeArgs {
        sensitivity: 0.5,
        stream: false,
        pieces: None,
        latency: None,
        positional: Vec::new(),
    };
    let mut pieces = false;
    let mut params = PieceParams::default();
    let mut piece_option = None; // first piece option met, for the error without --pieces
    let mut i = 1; // skip argv[0]
    while i < args.len() {
        match args[i].as_str() {
            "--pieces" => pieces = true,
            option @ ("--max-piece" | "--gap" | "--margin") => {
                let seconds = piece_seconds(option, args.get(i + 1))?;
                match option {
                    "--max-piece" => params.max_len = seconds,
                    "--gap" => params.max_gap = seconds,
                    _ => params.margin = seconds,
                }
                piece_option.get_or_insert(option);
                i += 1;
            }
            "--sensitivity" if i + 1 < args.len() => {
                out.sensitivity = args[i + 1].parse::<f32>().unwrap_or(0.5).clamp(0.0, 1.0);
                i += 1;
            }
            "--stream" => out.stream = true,
            "--latency" => {
                out.latency = Some(match args.get(i + 1).map(String::as_str) {
                    Some("low") => Latency::LOW,
                    Some("offline") => Latency::OFFLINE,
                    _ => return Err("--latency needs low or offline".into()),
                });
                i += 1;
            }
            "--engine" => {
                match args.get(i + 1).map(String::as_str) {
                    Some("nemotron3") => {}
                    Some(other) => return Err(format!("unknown engine '{other}' (nemotron3)")),
                    None => return Err("--engine needs a value (nemotron3)".into()),
                }
                i += 1;
            }
            other => out.positional.push(other.to_string()),
        }
        i += 1;
    }
    if let (false, Some(option)) = (pieces, piece_option) {
        return Err(format!("{option} needs --pieces"));
    }
    out.pieces = pieces.then_some(params);
    Ok(out)
}

/// Nemotron 3 threshold from --sensitivity (0 to 1): the speaker probability above which a 10 ms
/// frame is speech, from 0.1 to 0.5, 0.3 at the default 0.5. Swept on 2026-10-04 (DER, collar 0,
/// overlaps scored): French SUMM-RE meetings are best at 0.2 to 0.3 (11.3 % against 11.8 % at
/// 0.5), seven-speaker AISHELL-4 meetings at 0.4 to 0.5 (10.2 % against 13.3 % at 0.2); 0.3 gives
/// 11.3 % on both.
fn nemotron3_threshold(sensitivity: f32) -> f32 {
    0.1 + 0.4 * sensitivity.clamp(0.0, 1.0)
}

/// Loads Nemotron 3 from `model_dir/model.onnx` on the best provider, retrying on the CPU when
/// the GPU fails to initialise.
fn load_nemotron3(
    model_dir: &str,
    threshold: f32,
) -> Result<Nemotron3Diarizer, Box<dyn std::error::Error>> {
    let model_path = format!("{}/model.onnx", model_dir);
    if !std::path::Path::new(&model_path).exists() {
        return Err(format!(
            "Nemotron 3 model not found: {} (install it from dictee-setup)",
            model_path
        )
        .into());
    }
    let provider = parakeet_rs::best_provider();
    let cfg = ExecutionConfig::new().with_execution_provider(provider);
    match Nemotron3Diarizer::with_config(&model_path, Some(cfg), threshold) {
        Ok(diarizer) => Ok(diarizer),
        Err(e) if provider != parakeet_rs::ExecutionProvider::Cpu => {
            eprintln!("[dictee] Nemotron 3 GPU init failed ({}); retrying on CPU.", e);
            let cpu_cfg = ExecutionConfig::new()
                .with_execution_provider(parakeet_rs::ExecutionProvider::Cpu);
            Ok(Nemotron3Diarizer::with_config(&model_path, Some(cpu_cfg), threshold)?)
        }
        Err(e) => Err(e.into()),
    }
}

/// Output contract: `start end speaker_id`, one segment per line.
fn print_segments(segments: &[SpeakerSegment]) {
    for seg in segments {
        println!("{:.2} {:.2} {}", seg.start, seg.end, seg.speaker_id);
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let debug = env::var("DICTEE_DEBUG").unwrap_or_default() == "true";
    macro_rules! dbg_print {
        ($($arg:tt)*) => {
            if debug { eprintln!("[DBG diarize-only] {}", format!($($arg)*)); }
        };
    }

    let args: Vec<String> = env::args().collect();

    if args.iter().any(|a| a == "--help" || a == "-h") {
        eprintln!("diarize-only - Speaker diarization with Nemotron 3 (up to 8 speakers, no transcription)");
        eprintln!();
        eprintln!("Usage: diarize-only [OPTIONS] <audio> [model_dir]");
        eprintln!("       diarize-only --stream [OPTIONS] [model_dir]");
        eprintln!();
        eprintln!("Arguments:");
        eprintln!("  <audio>          Audio file (any format ffmpeg reads)");
        eprintln!("  [model_dir]      Model directory (default: ~/.local/share/dictee/nemotron3-diar,");
        eprintln!("                   else /usr/share/dictee/nemotron3-diar)");
        eprintln!();
        eprintln!("Options:");
        eprintln!("  --engine nemotron3       The engine (the only one, accepted for older callers)");
        eprintln!("  --sensitivity <0.0-1.0>  Detection threshold (default: 0.5, a probability of 0.1 to 0.5)");
        eprintln!("  --stream                 Streaming mode: reads FILE: <path> from stdin, the model kept alive;");
        eprintln!("                           each file continues the recording; answers the pieces it");
        eprintln!("                           settles, in seconds since the start; FLUSH ends it, RESET restarts");
        eprintln!("  --latency <low|offline>  Chunking: offline (30.4 s, files) or low (1.04 s, streams)");
        eprintln!("  --pieces                 Pieces to transcribe one by one (one speaker at a time,");
        eprintln!("                           long turns cut in a pause the diarizer heard, else the quietest point)");
        eprintln!("  --max-piece <seconds>    Longest piece (default: 30)");
        eprintln!("  --gap <seconds>          Pause of a speaker kept inside a piece (default: 0.5)");
        eprintln!("  --margin <seconds>       Audio added before and after each piece (default: 0)");
        eprintln!();
        eprintln!("Output: start_seconds end_seconds speaker_id (one segment per line)");
        return Ok(());
    }

    if args.len() < 2 {
        eprintln!("Usage: diarize-only <audio> [model_dir]");
        std::process::exit(1);
    }

    let parsed = match parse_diarize_args(&args) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("diarize-only: {}", e);
            eprintln!("Try 'diarize-only --help' for usage.");
            std::process::exit(2);
        }
    };
    let sensitivity = parsed.sensitivity;
    let stream_mode = parsed.stream;
    let pieces = parsed.pieces;
    let latency = parsed.latency;
    let positional_args = parsed.positional;
    if !stream_mode && positional_args.is_empty() {
        eprintln!("Error: missing audio file argument");
        std::process::exit(1);
    }

    let home = std::env::var("HOME").unwrap_or_else(|_| "/root".to_string());
    let default_dir = {
        let user = format!("{}/.local/share/dictee/nemotron3-diar", home);
        if std::path::Path::new(&user).exists() {
            user
        } else {
            "/usr/share/dictee/nemotron3-diar".to_string()
        }
    };
    // In stream mode, positional_args[0] is the model dir (optional)
    let model_dir = if stream_mode {
        positional_args.first().map(|s| s.to_string()).unwrap_or(default_dir)
    } else {
        positional_args.get(1).map(|s| s.to_string()).unwrap_or(default_dir)
    };

    if stream_mode {
        return run_nemotron3_stream(
            &model_dir,
            nemotron3_threshold(sensitivity),
            latency.unwrap_or(Latency::LOW),
            pieces.unwrap_or_default(),
        );
    }

    let audio_path = resolve_path(&positional_args[0])?;
    dbg_print!("audio={}, sensitivity={:.2}, model_dir={}", audio_path, sensitivity, model_dir);

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

    let threshold = nemotron3_threshold(sensitivity);
    let mut diarizer = load_nemotron3(&model_dir, threshold)?;
    diarizer.set_latency(latency.unwrap_or(Latency::OFFLINE));
    dbg_print!("model loaded, threshold={:.2}, audio={} samples", threshold, audio.len());
    let segments = match &pieces {
        Some(params) => diarizer.pieces(audio, spec.sample_rate, spec.channels, params)?,
        None => diarizer.diarize(audio, spec.sample_rate, spec.channels)?,
    };
    dbg_print!("done: {} segments (pieces: {:?})", segments.len(), pieces);
    print_segments(&segments);
    Ok(())
}

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

fn is_wav_16k_mono(path: &str) -> bool {
    let Ok(reader) = hound::WavReader::open(path) else { return false };
    let spec = reader.spec();
    spec.sample_rate == 16000 && spec.channels == 1
}

fn ensure_wav(audio_path: &str) -> Result<(String, bool), Box<dyn std::error::Error>> {
    ensure_wav_with_tmp(audio_path, TEMP_CONVERTED)
}

fn ensure_wav_with_tmp(audio_path: &str, tmp_path: &str) -> Result<(String, bool), Box<dyn std::error::Error>> {
    if is_wav_16k_mono(audio_path) {
        return Ok((audio_path.to_string(), false));
    }

    let status = Command::new("ffmpeg")
        .args(["-y", "-i", audio_path, "-ar", "16000", "-ac", "1", "-f", "wav", tmp_path])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|e| format!("ffmpeg not found: {}. Install ffmpeg to convert audio files.", e))?;

    if !status.success() {
        return Err(format!("ffmpeg failed to convert '{}' (exit code: {:?})", audio_path, status.code()).into());
    }

    Ok((tmp_path.to_string(), true))
}

/// A recording followed as it arrives (`--stream`): every `FILE: <path>` line adds that file's
/// audio (16 kHz mono after conversion) to the recording, and the answer is the pieces it
/// settles, `start end speaker` in seconds since the start, then an empty line. `FLUSH` ends the
/// recording with the pieces left and starts a new one; `RESET` starts a new one at once.
fn run_nemotron3_stream(
    model_dir: &str,
    threshold: f32,
    latency: Latency,
    params: PieceParams,
) -> Result<(), Box<dyn std::error::Error>> {
    use std::io::{BufRead, Write};
    let mut diarizer = load_nemotron3(model_dir, threshold)?;
    let mut stream = diarizer.stream(latency, params);
    eprintln!("[diarize-only --stream] ready");
    let stdin = std::io::stdin();
    let mut reader = stdin.lock();
    let mut stdout = std::io::stdout();
    let mut line = String::new();
    loop {
        line.clear();
        if reader.read_line(&mut line)? == 0 {
            eprintln!("[diarize-only --stream] EOF, exiting");
            return Ok(());
        }
        let cmd = line.trim();
        let answer = match cmd {
            "" => continue,
            "RESET" => {
                stream = diarizer.stream(latency, params);
                writeln!(stdout, "RESET_OK")?;
                stdout.flush()?;
                continue;
            }
            "FLUSH" => {
                let pieces = diarizer.stream_finish(&mut stream);
                stream = diarizer.stream(latency, params);
                pieces.map_err(|e| e.to_string())
            }
            _ => match cmd.strip_prefix("FILE: ") {
                Some(path) => read_mono_16k(path)
                    .and_then(|audio| {
                        diarizer.stream_push(&mut stream, &audio).map_err(|e| e.into())
                    })
                    .map_err(|e| e.to_string()),
                None => Err("unknown command".to_string()),
            },
        };
        match answer {
            Ok(pieces) => {
                for piece in &pieces {
                    writeln!(stdout, "{:.2} {:.2} {}", piece.start, piece.end, piece.speaker_id)?;
                }
                writeln!(stdout)?;
            }
            Err(e) => writeln!(stdout, "ERROR: {}", e)?,
        }
        stdout.flush()?;
    }
}

/// The audio of `path` as 16 kHz mono samples (converted by ffmpeg when needed, channels averaged).
fn read_mono_16k(path: &str) -> Result<Vec<f32>, Box<dyn std::error::Error>> {
    if !std::path::Path::new(path).exists() {
        return Err(format!("file not found: {}", path).into());
    }
    let tmp_path = format!("/tmp/diarize_only_stream_{}.wav", std::process::id());
    let (wav_path, needs_cleanup) = ensure_wav_with_tmp(path, &tmp_path)?;
    let mut reader = hound::WavReader::open(&wav_path)?;
    let spec = reader.spec();
    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().collect::<Result<Vec<_>, _>>()?,
        hound::SampleFormat::Int => reader
            .samples::<i16>()
            .map(|s| s.map(|v| v as f32 / 32768.0))
            .collect::<Result<Vec<_>, _>>()?,
    };
    if needs_cleanup {
        let _ = fs::remove_file(&wav_path);
    }
    if spec.sample_rate != 16_000 {
        return Err(format!("expected 16 kHz audio, got {} Hz", spec.sample_rate).into());
    }
    let channels = spec.channels.max(1) as usize;
    Ok(samples
        .chunks(channels)
        .map(|frame| frame.iter().sum::<f32>() / channels as f32)
        .collect())
}

#[cfg(test)]
mod arg_tests {
    use super::*;

    fn argv(extra: &[&str]) -> Vec<String> {
        std::iter::once("diarize-only")
            .chain(extra.iter().copied())
            .map(String::from)
            .collect()
    }

    #[test]
    fn defaults() {
        let p = parse_diarize_args(&argv(&["rec.wav"])).unwrap();
        assert_eq!(p.positional, vec!["rec.wav".to_string()]);
        assert_eq!(p.sensitivity, 0.5);
        assert!(!p.stream);
        assert_eq!(p.pieces, None);
        assert_eq!(p.latency, None);
    }

    #[test]
    fn engine_nemotron3_is_still_accepted_anywhere() {
        let p = parse_diarize_args(&argv(&[
            "--engine", "nemotron3", "--sensitivity", "0.65", "rec.wav", "/models/n3",
        ]))
        .unwrap();
        assert_eq!(p.sensitivity, 0.65);
        assert_eq!(p.positional, vec!["rec.wav".to_string(), "/models/n3".to_string()]);
        let p = parse_diarize_args(&argv(&["rec.wav", "--engine", "nemotron3"])).unwrap();
        assert_eq!(p.positional, vec!["rec.wav".to_string()]);
    }

    #[test]
    fn retired_or_unknown_engines_are_an_error() {
        for engine in ["sortformer", "pyannote"] {
            let err = parse_diarize_args(&argv(&["--engine", engine, "rec.wav"])).unwrap_err();
            assert!(err.contains("nemotron3"), "{err}");
        }
        assert!(parse_diarize_args(&argv(&["rec.wav", "--engine"])).is_err());
    }

    #[test]
    fn stream_mode() {
        assert!(parse_diarize_args(&argv(&["--stream"])).unwrap().stream);
        assert!(parse_diarize_args(&argv(&["--stream", "--engine", "nemotron3"])).unwrap().stream);
    }

    #[test]
    fn latency_low_or_offline() {
        let parse = |extra: &[&str]| parse_diarize_args(&argv(extra));
        assert_eq!(parse(&["--latency", "low", "rec.wav"]).unwrap().latency, Some(Latency::LOW));
        assert_eq!(parse(&["--latency", "offline", "--stream"]).unwrap().latency, Some(Latency::OFFLINE));
        assert!(parse(&["--latency", "fast", "rec.wav"]).unwrap_err().contains("--latency"));
        assert!(parse(&["rec.wav", "--latency"]).is_err());
    }

    #[test]
    fn sensitivity_keeps_its_lenient_parsing() {
        let p = parse_diarize_args(&argv(&["--sensitivity", "abc", "rec.wav"])).unwrap();
        assert_eq!(p.sensitivity, 0.5);
        let p = parse_diarize_args(&argv(&["--sensitivity", "3", "rec.wav"])).unwrap();
        assert_eq!(p.sensitivity, 1.0);
    }

    #[test]
    fn segments_unless_pieces_are_asked_for() {
        let p = parse_diarize_args(&argv(&["--pieces", "rec.wav"])).unwrap();
        assert_eq!(p.pieces, Some(PieceParams::default()));
        assert_eq!(p.positional, vec!["rec.wav".to_string()]);
    }

    #[test]
    fn piece_options_override_the_defaults() {
        let p = parse_diarize_args(&argv(&[
            "--pieces", "--max-piece", "8", "--gap", "1", "--margin", "0.15", "rec.wav",
        ]))
        .unwrap();
        let want = PieceParams {
            max_len: 8.0,
            max_gap: 1.0,
            margin: 0.15,
            ..PieceParams::default()
        };
        assert_eq!(p.pieces, Some(want));
    }

    #[test]
    fn piece_options_need_pieces_and_sane_values() {
        let parse = |extra: &[&str]| {
            let mut args = extra.to_vec();
            args.push("rec.wav");
            parse_diarize_args(&argv(&args))
        };
        assert!(parse(&["--max-piece", "8"]).unwrap_err().contains("--pieces"));
        assert!(parse(&["--pieces", "--max-piece", "abc"]).is_err());
        assert!(parse(&["--pieces", "--max-piece", "0.5"]).is_err());
        assert!(parse(&["--pieces", "--gap", "-1"]).is_err());
        assert!(parse(&["--pieces", "--margin"]).is_err());
    }

    #[test]
    fn nemotron3_threshold_spans_its_useful_range() {
        let close = |a: f32, b: f32| (a - b).abs() < 1e-6;
        assert!(close(nemotron3_threshold(0.5), 0.3), "the default sensitivity gives 0.3");
        assert!(close(nemotron3_threshold(0.0), 0.1));
        assert!(close(nemotron3_threshold(1.0), 0.5));
        // no dead zone: every step of the slider moves the threshold
        assert!(nemotron3_threshold(0.0) < nemotron3_threshold(0.1));
        assert!(nemotron3_threshold(0.9) < nemotron3_threshold(1.0));
    }
}
