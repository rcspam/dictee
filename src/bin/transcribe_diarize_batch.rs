#[cfg(feature = "sortformer")]
use parakeet_rs::sortformer::{DiarizationConfig, Sortformer};
#[cfg(feature = "sortformer")]
use parakeet_rs::{best_provider, ExecutionConfig, ParakeetTDT, TimestampMode, Transcriber};
#[cfg(feature = "sortformer")]
use std::env;
#[cfg(feature = "sortformer")]
use std::fs;
#[cfg(feature = "sortformer")]
use std::io::{self, BufRead, Write};
#[cfg(feature = "sortformer")]
use std::process::{Command, Stdio};

#[cfg(feature = "sortformer")]
fn temp_converted_path() -> String {
    // PID-scoped path so two concurrent transcribe-diarize-batch
    // invocations (e.g. two open dictee-transcribe windows) cannot
    // race-write the same /tmp file.
    format!(
        "/tmp/transcribe_diarize_batch_converted_{}.wav",
        std::process::id()
    )
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(not(feature = "sortformer"))]
    {
        eprintln!("Error: This binary requires the 'sortformer' feature.");
        eprintln!("Compile with: cargo build --features \"cuda,sortformer\"");
        std::process::exit(1);
    }

    #[cfg(feature = "sortformer")]
    {
        let debug = env::var("DICTEE_DEBUG").unwrap_or_default() == "true";
        macro_rules! dbg_print {
            ($($arg:tt)*) => {
                if debug { eprintln!("[DBG batch] {}", format!($($arg)*)); }
            };
        }

        let args: Vec<String> = env::args().collect();

        if args.iter().any(|a| a == "--help" || a == "-h") {
            print_help();
            return Ok(());
        }

        let mut sensitivity: f32 = 0.5;
        let mut model_dir_arg: Option<String> = None;
        let mut sortformer_dir_arg: Option<String> = None;
        let mut files_from_stdin = false;
        let mut apply_postprocess = true;
        let mut no_diarize = false;
        let mut positional: Vec<String> = Vec::new();
        let mut i = 1;
        while i < args.len() {
            match args[i].as_str() {
                "--sensitivity" if i + 1 < args.len() => {
                    sensitivity = args[i + 1].parse().unwrap_or(0.5);
                    sensitivity = sensitivity.clamp(0.0, 1.0);
                    i += 2;
                }
                "--model-dir" if i + 1 < args.len() => {
                    model_dir_arg = Some(args[i + 1].clone());
                    i += 2;
                }
                "--sortformer-dir" if i + 1 < args.len() => {
                    sortformer_dir_arg = Some(args[i + 1].clone());
                    i += 2;
                }
                "--stdin" => {
                    files_from_stdin = true;
                    i += 1;
                }
                "--no-postprocess" => {
                    apply_postprocess = false;
                    i += 1;
                }
                "--no-diarize" => {
                    no_diarize = true;
                    i += 1;
                }
                _ => {
                    positional.push(args[i].clone());
                    i += 1;
                }
            }
        }

        // Collect files list
        let mut files: Vec<String> = if files_from_stdin {
            let stdin = io::stdin();
            stdin
                .lock()
                .lines()
                .filter_map(|l| l.ok())
                .map(|l| l.trim().to_string())
                .filter(|l| !l.is_empty())
                .collect()
        } else {
            positional.clone()
        };

        if files.is_empty() {
            eprintln!("Error: no input files. Use positional args or --stdin.");
            print_help();
            std::process::exit(1);
        }

        // Resolve paths (expand ~/ and canonicalize)
        files = files
            .into_iter()
            .map(|p| resolve_path(&p).unwrap_or(p))
            .collect();

        let home = env::var("HOME").unwrap_or_else(|_| "/root".to_string());
        let model_dir = model_dir_arg.unwrap_or_else(|| {
            let user = format!("{}/.local/share/dictee/tdt", home);
            if std::path::Path::new(&user).join("vocab.txt").exists() {
                user
            } else {
                "/usr/share/dictee/tdt".to_string()
            }
        });
        let sortformer_dir = sortformer_dir_arg.unwrap_or_else(|| {
            let user = format!("{}/.local/share/dictee/sortformer", home);
            if std::path::Path::new(&user).exists() {
                user
            } else {
                "/usr/share/dictee/sortformer".to_string()
            }
        });

        dbg_print!(
            "files={}, model_dir={}, sortformer_dir={}, sensitivity={:.2}",
            files.len(),
            model_dir,
            sortformer_dir,
            sensitivity
        );

        // Free GPU VRAM upfront: stop any running ASR daemon
        #[cfg(feature = "cuda")]
        let daemon_was_active = stop_daemons_for_vram();
        #[cfg(not(feature = "cuda"))]
        let daemon_was_active = false;

        // Build execution config ONCE — runtime probe + CPU fallback.
        let config = ExecutionConfig::new().with_execution_provider(best_provider());

        // Load Sortformer ONCE (skip if --no-diarize)
        let mut sortformer_opt: Option<Sortformer> = if !no_diarize {
            let sortformer_path =
                format!("{}/diar_streaming_sortformer_4spk-v2.1.onnx", sortformer_dir);
            let diar_config = if (sensitivity - 0.5).abs() < 0.01 {
                DiarizationConfig::callhome()
            } else {
                let onset = 0.4 + sensitivity * 0.3;
                let offset = 0.3 + sensitivity * 0.3;
                DiarizationConfig::custom(onset, offset)
            };
            eprintln!("Loading Sortformer...");
            Some(Sortformer::with_config(
                &sortformer_path,
                Some(config.clone()),
                diar_config,
            )?)
        } else {
            dbg_print!("sortformer SKIPPED (--no-diarize)");
            None
        };
        dbg_print!("sortformer loaded={}", sortformer_opt.is_some());

        // Load Parakeet-TDT ONCE
        eprintln!("Loading Parakeet-TDT...");
        let mut parakeet = ParakeetTDT::from_pretrained(&model_dir, Some(config))?;
        dbg_print!("parakeet loaded");

        // Prepare postprocess context
        let has_postprocess = apply_postprocess && which("dictee-postprocess");
        let lang_source = read_conf_value("DICTEE_LANG_SOURCE")
            .or_else(|| env::var("LANG").ok().map(|l| l[..2].to_string()))
            .unwrap_or_else(|| "fr".to_string());

        // Iterate files
        let stdout = io::stdout();
        let mut stdout_lock = stdout.lock();
        let mut failures = 0;
        let total = files.len();
        for (idx, path) in files.iter().enumerate() {
            let t_start = std::time::Instant::now();
            eprintln!("[{}/{}] {}", idx + 1, total, path);

            // Prefix header
            writeln!(stdout_lock, "===CHUNK {} {}===", idx, path).ok();

            match process_one(
                path,
                sortformer_opt.as_mut(),
                &mut parakeet,
                has_postprocess,
                &lang_source,
                &mut stdout_lock,
            ) {
                Ok(n_seg) => {
                    eprintln!(
                        "    {} segments in {:.1}s",
                        n_seg,
                        t_start.elapsed().as_secs_f32()
                    );
                }
                Err(e) => {
                    failures += 1;
                    eprintln!("    FAILED: {}", e);
                    writeln!(stdout_lock, "===ERROR {} {}===", idx, e).ok();
                }
            }
            stdout_lock.flush().ok();
        }

        // Cleanup
        drop(parakeet);
        drop(sortformer_opt);

        #[cfg(feature = "cuda")]
        if daemon_was_active {
            restart_daemons();
        }
        #[cfg(not(feature = "cuda"))]
        let _ = daemon_was_active;

        eprintln!(
            "Done: {}/{} files OK",
            total - failures,
            total
        );
        if failures > 0 {
            std::process::exit(2);
        }
        Ok(())
    }
}

#[cfg(feature = "sortformer")]
fn print_help() {
    eprintln!("transcribe-diarize-batch - Batch transcription + diarisation");
    eprintln!();
    eprintln!("Usage:");
    eprintln!("  transcribe-diarize-batch [OPTIONS] <file1.wav> [file2.wav ...]");
    eprintln!("  transcribe-diarize-batch [OPTIONS] --stdin  < file_list.txt");
    eprintln!();
    eprintln!("Charge les modèles UNE SEULE FOIS et traite tous les fichiers en séquence.");
    eprintln!();
    eprintln!("Options:");
    eprintln!("  --sensitivity <0.0-1.0>  Detection threshold (default: 0.5)");
    eprintln!("  --model-dir <path>       Parakeet-TDT model dir");
    eprintln!("  --sortformer-dir <path>  Sortformer model dir");
    eprintln!("  --stdin                  Read file list from stdin (one path per line)");
    eprintln!("  --no-postprocess         Skip dictee-postprocess");
    eprintln!("  --no-diarize             Skip Sortformer (transcription only, no speaker labels)");
    eprintln!();
    eprintln!("Output: lines grouped by chunk with header:");
    eprintln!("  ===CHUNK <idx> <path>===");
    eprintln!("  [<start>s - <end>s] Speaker N: text   (default)");
    eprintln!("  [<start>s - <end>s] text              (with --no-diarize)");
    eprintln!("  ...");
}

#[cfg(feature = "sortformer")]
fn process_one<W: Write>(
    path: &str,
    sortformer: Option<&mut Sortformer>,
    parakeet: &mut ParakeetTDT,
    has_postprocess: bool,
    lang_source: &str,
    out: &mut W,
) -> Result<usize, Box<dyn std::error::Error>> {
    let (wav_path, needs_cleanup) = ensure_wav(path)?;

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

    // Diarize only if Sortformer is available; otherwise emit tokens without speaker label.
    let speaker_segments = if let Some(sf) = sortformer {
        sf.diarize(audio.clone(), spec.sample_rate, spec.channels)?
    } else {
        Vec::new()
    };

    let result = parakeet.transcribe_samples(
        audio,
        spec.sample_rate,
        spec.channels,
        Some(TimestampMode::Sentences),
    )?;

    let mut n_written = 0;
    for segment in &result.tokens {
        let text = if has_postprocess {
            postprocess(&segment.text, lang_source)
        } else {
            segment.text.clone()
        };

        if speaker_segments.is_empty() {
            // --no-diarize mode: emit token with timestamps but no speaker label.
            writeln!(
                out,
                "[{:.2}s - {:.2}s] {}",
                segment.start, segment.end, text
            )?;
        } else {
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

            writeln!(
                out,
                "[{:.2}s - {:.2}s] {}: {}",
                segment.start, segment.end, speaker, text
            )?;
        }
        n_written += 1;
    }
    Ok(n_written)
}

#[cfg(feature = "sortformer")]
fn resolve_path(path: &str) -> Result<String, Box<dyn std::error::Error>> {
    let expanded = if let Some(rest) = path.strip_prefix("~/") {
        let home = env::var("HOME").map_err(|_| "HOME not set")?;
        format!("{}/{}", home, rest)
    } else {
        path.to_string()
    };
    let canonical = fs::canonicalize(&expanded).map_err(|e| format!("{}: {}", expanded, e))?;
    Ok(canonical.to_string_lossy().into_owned())
}

#[cfg(feature = "sortformer")]
fn is_wav_16k_mono(path: &str) -> bool {
    let Ok(reader) = hound::WavReader::open(path) else {
        return false;
    };
    let spec = reader.spec();
    spec.sample_rate == 16000 && spec.channels == 1
}

#[cfg(feature = "sortformer")]
fn ensure_wav(audio_path: &str) -> Result<(String, bool), Box<dyn std::error::Error>> {
    if is_wav_16k_mono(audio_path) {
        return Ok((audio_path.to_string(), false));
    }
    let temp_path = temp_converted_path();
    let status = Command::new("ffmpeg")
        .args(["-y", "-i", audio_path, "-ar", "16000", "-ac", "1", "-f", "wav", &temp_path])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|e| format!("ffmpeg not found: {}", e))?;
    if !status.success() {
        return Err(format!("ffmpeg failed to convert '{}'", audio_path).into());
    }
    Ok((temp_path, true))
}

#[cfg(feature = "sortformer")]
fn which(cmd: &str) -> bool {
    env::var("PATH")
        .unwrap_or_default()
        .split(':')
        .any(|dir| std::path::Path::new(dir).join(cmd).is_file())
}

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

#[cfg(all(feature = "sortformer", feature = "cuda"))]
fn stop_daemons_for_vram() -> bool {
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
    std::thread::sleep(std::time::Duration::from_secs(1));
    true
}

#[cfg(feature = "sortformer")]
fn restart_daemons() {
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
    let _ = Command::new("systemctl").args(["--user", "start", svc]).status();
}
