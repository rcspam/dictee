#[cfg(feature = "sortformer")]
use parakeet_rs::sortformer::{DiarizationConfig, Sortformer};
#[cfg(feature = "sortformer")]
use parakeet_rs::{
    best_provider, parakeet_provider, ExecutionConfig, ExecutionProvider, ParakeetTDT,
    TimestampMode, Transcriber,
};
#[cfg(feature = "sortformer")]
use std::env;
#[cfg(feature = "sortformer")]
use std::fs;
#[cfg(feature = "sortformer")]
use std::process::{Command, Stdio};

#[cfg(feature = "sortformer")]
const TEMP_CONVERTED: &str = "/tmp/transcribe_diarize_converted.wav";

/// Assign one speaker per transcription unit, scoring the whole sequence.
///
/// Port of dictee-transcribe.py's `_assign_speakers` (a323876 then d5cafd4),
/// kept parameter-for-parameter identical so the three fusion sites (file
/// path, live meeting, this binary) agree on the same output.
///
/// The diarization timeline is authoritative but locally imperfect: every
/// engine emits spurious islands or boundaries shifted by a few hundred ms,
/// and a per-unit geometric rule (max overlap, nearest segment) copies those
/// defects onto the text. So units are assigned as a sequence (min-cost
/// dynamic program): the per-unit cost of a speaker is the distance from the
/// unit midpoint to that speaker's nearest segment (0 when inside), and
/// switching speaker between consecutive units costs `switch_penalty`, except
/// after a clause-final punctuation or a silence of at least `free_gap`.
///
/// Returns one speaker per unit; `None` only when `segments` is empty. Unlike
/// max-overlap, a unit that overlaps nothing still gets its nearest speaker
/// instead of being dropped as UNKNOWN.
///
/// Gated on the feature like the rest of the binary, but kept available under
/// `test` so the fusion can be unit-tested without the ONNX models.
#[cfg(any(feature = "sortformer", test))]
fn assign_speakers(
    units: &[(f32, f32, String)],
    segments: &[(f32, f32, usize)],
    switch_penalty: f32,
    free_gap: f32,
) -> Vec<Option<usize>> {
    if units.is_empty() {
        return Vec::new();
    }
    if segments.is_empty() {
        return vec![None; units.len()];
    }

    let mut speakers: Vec<usize> = segments.iter().map(|s| s.2).collect();
    speakers.sort_unstable();
    speakers.dedup();
    let n_spk = speakers.len();

    // Per-unit emission costs: distance to each speaker's nearest segment.
    let emissions: Vec<Vec<f32>> = units
        .iter()
        .map(|(start, end, _)| {
            let mid = 0.5 * (start + end);
            let mut best = vec![f32::INFINITY; n_spk];
            for (s_start, s_end, spk) in segments {
                let dist = if *s_start <= mid && mid <= *s_end {
                    0.0
                } else {
                    (mid - s_start).abs().min((mid - s_end).abs())
                };
                let j = speakers.iter().position(|s| s == spk).unwrap();
                if dist < best[j] {
                    best[j] = dist;
                }
            }
            best
        })
        .collect();

    // Viterbi over (unit, speaker) with backpointers.
    let mut cost = emissions[0].clone();
    let mut backptrs: Vec<Vec<usize>> = Vec::with_capacity(units.len().saturating_sub(1));
    for i in 1..units.len() {
        let free = ends_clause(&units[i - 1].2) || units[i].0 - units[i - 1].1 >= free_gap;
        let mut new_cost = Vec::with_capacity(n_spk);
        let mut new_back = Vec::with_capacity(n_spk);
        for j in 0..n_spk {
            let (mut best_prev, mut best_cost) = (j, cost[j]);
            for k in 0..n_spk {
                let c = if free {
                    cost[k]
                } else {
                    cost[k] + if k == j { 0.0 } else { switch_penalty }
                };
                if c < best_cost {
                    best_cost = c;
                    best_prev = k;
                }
            }
            new_cost.push(best_cost + emissions[i][j]);
            new_back.push(best_prev);
        }
        cost = new_cost;
        backptrs.push(new_back);
    }

    let mut j = (0..n_spk)
        .min_by(|a, b| cost[*a].partial_cmp(&cost[*b]).unwrap())
        .unwrap();
    let mut path = vec![j];
    for back in backptrs.iter().rev() {
        j = back[j];
        path.push(j);
    }
    path.reverse();
    path.into_iter().map(|j| Some(speakers[j])).collect()
}

/// True when the text ends a clause (sentence-final punctuation, ignoring
/// trailing quotes and brackets). Same set as the Python original.
#[cfg(any(feature = "sortformer", test))]
fn ends_clause(text: &str) -> bool {
    let trimmed = text.trim_end_matches(['"', '\'', '»', '«', ')', ']', '}']);
    trimmed.ends_with(['.', '!', '?', '…'])
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
                if debug { eprintln!("[DBG transcribe-diarize] {}", format!($($arg)*)); }
            };
        }

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
        dbg_print!("audio={}, sensitivity={:.2}", audio_path, sensitivity);
        let home = std::env::var("HOME").unwrap_or_else(|_| "/root".to_string());
        let default_tdt = {
            let user = format!("{}/.local/share/dictee/tdt", home);
            if std::path::Path::new(&user).join("vocab.txt").exists() { user }
            else { "/usr/share/dictee/tdt".to_string() }
        };
        let default_sf = {
            let user = format!("{}/.local/share/dictee/sortformer", home);
            if std::path::Path::new(&user).exists() { user }
            else { "/usr/share/dictee/sortformer".to_string() }
        };
        let model_dir = positional_args.get(1).map(|s| s.to_string()).unwrap_or(default_tdt);
        let sortformer_dir = positional_args.get(2).map(|s| s.to_string()).unwrap_or(default_sf);

        dbg_print!("model_dir={}, sortformer_dir={}", model_dir, sortformer_dir);

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

        // Free GPU VRAM: stop ASR daemons if they hold the GPU
        #[cfg(feature = "cuda")]
        let daemon_was_active = stop_daemons_for_vram();
        #[cfg(not(feature = "cuda"))]
        let daemon_was_active = false;

        // Parakeet config: forces CPU for an int8 model (broken on the ORT
        // CUDA EP). Sortformer gets its own GPU-capable config below.
        let parakeet_config = ExecutionConfig::new()
            .with_execution_provider(parakeet_provider(std::path::Path::new(&model_dir)));

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

        // Sortformer has no int8 variant — run it on GPU when available (even
        // a small one), with a CPU retry if GPU init crashes late. Mirrors
        // diarize-only.
        let sortformer_provider = best_provider();
        let sortformer_config =
            ExecutionConfig::new().with_execution_provider(sortformer_provider);
        let mut sortformer = match Sortformer::with_config(
            &sortformer_path,
            Some(sortformer_config),
            diar_config.clone(),
        ) {
            Ok(sf) => sf,
            Err(e) if sortformer_provider != ExecutionProvider::Cpu => {
                eprintln!("[dictee] Sortformer GPU init failed ({e}); retrying on CPU.");
                let cpu_config =
                    ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cpu);
                Sortformer::with_config(&sortformer_path, Some(cpu_config), diar_config)?
            }
            Err(e) => return Err(e.into()),
        };

        dbg_print!("sortformer loaded, audio={} samples", audio.len());

        // Get speaker segments
        let speaker_segments = sortformer.diarize(audio.clone(), spec.sample_rate, spec.channels)?;
        let n_spk: std::collections::HashSet<_> = speaker_segments.iter().map(|s| s.speaker_id).collect();
        dbg_print!("diarization: {} segments, {} speakers", speaker_segments.len(), n_spk.len());

        // Load TDT for transcription
        let mut parakeet = ParakeetTDT::from_pretrained(&model_dir, Some(parakeet_config))?;

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

        // Match speakers to sentences, scoring the whole sequence at once
        // (same fusion as the file and live paths, see assign_speakers).
        let units: Vec<(f32, f32, String)> = result
            .tokens
            .iter()
            .map(|t| (t.start, t.end, t.text.clone()))
            .collect();
        let segs: Vec<(f32, f32, usize)> = speaker_segments
            .iter()
            .map(|s| (s.start, s.end, s.speaker_id))
            .collect();
        let assigned = assign_speakers(&units, &segs, 1.5, 1.0);

        for (segment, spk) in result.tokens.iter().zip(assigned) {
            let speaker = spk
                .map(|id| format!("Speaker {}", id))
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

#[cfg(test)]
mod tests {
    use super::*;

    /// The rule this binary used before: for each unit independently, the
    /// speaker with the largest overlap, or UNKNOWN when nothing overlaps.
    /// Kept here so the tests below show what the sequence fusion fixes — if
    /// anyone reverts to it, they fail.
    fn legacy_max_overlap(
        units: &[(f32, f32, String)],
        segments: &[(f32, f32, usize)],
    ) -> Vec<Option<usize>> {
        units
            .iter()
            .map(|(start, end, _)| {
                segments
                    .iter()
                    .filter_map(|(s_start, s_end, spk)| {
                        let overlap = (end.min(*s_end) - start.max(*s_start)).max(0.0);
                        if overlap > 0.0 {
                            Some((*spk, overlap))
                        } else {
                            None
                        }
                    })
                    .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
                    .map(|(id, _)| id)
            })
            .collect()
    }

    /// One continuous turn, cut in three by a 0.4 s diarizer blip.
    fn blip_fixture() -> (Vec<(f32, f32, String)>, Vec<(f32, f32, usize)>) {
        let units: Vec<_> = (0..20)
            .map(|i| (0.5 * i as f32, 0.5 * (i + 1) as f32, format!("mot{}", i)))
            .collect();
        let segments = vec![(0.0, 4.0, 0), (4.0, 4.4, 1), (4.4, 10.0, 0)];
        (units, segments)
    }

    #[test]
    fn legacy_copies_the_blip_onto_the_text() {
        let (units, segments) = blip_fixture();
        let got = legacy_max_overlap(&units, &segments);
        assert!(
            got.contains(&Some(1)),
            "precondition: the old rule must copy the blip, otherwise the \
             regression test below proves nothing"
        );
    }

    #[test]
    fn sequence_fusion_absorbs_a_short_blip() {
        let (units, segments) = blip_fixture();
        let got = assign_speakers(&units, &segments, 1.5, 1.0);
        assert_eq!(
            got,
            vec![Some(0); 20],
            "a 0.4 s island cannot pay the 3.0 s round trip"
        );
    }

    #[test]
    fn a_genuine_turn_still_switches() {
        let (units, _) = blip_fixture();
        let segments = vec![(0.0, 4.0, 0), (4.0, 7.0, 1), (7.0, 10.0, 0)];
        let got = assign_speakers(&units, &segments, 1.5, 1.0);
        assert_eq!(got[0], Some(0));
        assert_eq!(got[10], Some(1), "3 s of real mass must win over the penalty");
        assert_eq!(got[19], Some(0));
    }

    #[test]
    fn a_unit_overlapping_nothing_is_no_longer_dropped() {
        // The unit sits in a gap between two segments: max-overlap yields
        // UNKNOWN, the sequence rule attributes it to the nearest speaker.
        let units = vec![(5.0, 5.4, "orpheline".to_string())];
        let segments = vec![(0.0, 4.0, 0), (6.0, 10.0, 1)];
        assert_eq!(legacy_max_overlap(&units, &segments), vec![None]);
        assert_eq!(assign_speakers(&units, &segments, 1.5, 1.0), vec![Some(1)]);
    }

    #[test]
    fn clause_end_makes_switching_free() {
        // Same 0.4 s island, but BOTH boundaries are clause ends: entering
        // and leaving the island are free, so the fusion follows the diarizer
        // even for a very short turn. (With only the first boundary free the
        // return trip still costs switch_penalty and the island is absorbed —
        // that asymmetry is the intended behaviour, see the blip test.)
        let units = vec![
            (0.0, 4.0, "Fin de phrase.".to_string()),
            (4.0, 4.4, "Oui.".to_string()),
            (4.4, 8.0, "Et je reprends.".to_string()),
        ];
        let segments = vec![(0.0, 4.0, 0), (4.0, 4.4, 1), (4.4, 10.0, 0)];
        let got = assign_speakers(&units, &segments, 1.5, 1.0);
        assert_eq!(got, vec![Some(0), Some(1), Some(0)]);
    }

    #[test]
    fn no_segments_yields_no_speaker() {
        let (units, _) = blip_fixture();
        assert_eq!(assign_speakers(&units, &[], 1.5, 1.0), vec![None; 20]);
        assert!(assign_speakers(&[], &[(0.0, 1.0, 0)], 1.5, 1.0).is_empty());
    }

    #[test]
    fn ends_clause_ignores_trailing_quotes() {
        assert!(ends_clause("Bonjour."));
        assert!(ends_clause("Bonjour !»"));
        assert!(ends_clause("(vraiment ?)"));
        assert!(ends_clause("Vraiment ?"));
        assert!(!ends_clause("et donc"));
        assert!(!ends_clause("3,5"));
        // Like the Python original, a space before the quote stops the strip.
        assert!(!ends_clause("« Bonjour ! »"));
    }

    /// Parity with the Python original on a REAL 40 s window of the
    /// SUMM-RE bench (004c_PAPH, 120-160 s): same words, same
    /// diarize-multi segments, same expected speaker sequence. Guards
    /// against the f64 -> f32 port silently changing a decision.
    #[test]
    fn parity_with_python_on_real_data() {
        let units: Vec<(f32, f32, String)> = vec![
            (120.00, 120.22, "3".to_string()),
            (120.22, 120.37, "le".to_string()),
            (120.37, 120.96, "10,".to_string()),
            (120.97, 121.17, "par".to_string()),
            (121.19, 121.86, "exemple,".to_string()),
            (121.86, 122.17, "pour".to_string()),
            (122.17, 122.70, "arriver".to_string()),
            (122.70, 122.85, "à".to_string()),
            (122.85, 123.23, "faire".to_string()),
            (123.23, 123.38, "un".to_string()),
            (123.38, 123.83, "doodle".to_string()),
            (123.83, 124.13, "pour".to_string()),
            (124.13, 124.55, "3.".to_string()),
            (124.59, 124.95, "Parce".to_string()),
            (124.95, 125.16, "que".to_string()),
            (125.16, 125.77, "voilà,".to_string()),
            (125.77, 125.88, "si".to_string()),
            (125.93, 126.07, "on".to_string()),
            (126.07, 126.37, "fait".to_string()),
            (126.37, 126.52, "un".to_string()),
            (126.52, 126.74, "peu".to_string()),
            (126.74, 126.89, "un".to_string()),
            (126.89, 127.41, "caprice".to_string()),
            (127.41, 127.71, "pour".to_string()),
            (127.71, 127.93, "avoir".to_string()),
            (128.08, 128.30, "ces".to_string()),
            (128.31, 128.97, "3-là,".to_string()),
            (128.97, 130.25, "obligatoirement,".to_string()),
            (130.25, 130.40, "il".to_string()),
            (130.40, 130.70, "faut".to_string()),
            (130.70, 131.08, "quand".to_string()),
            (131.08, 131.44, "même".to_string()),
            (131.44, 131.91, "donner".to_string()),
            (131.97, 132.13, "une".to_string()),
            (132.13, 132.58, "petite".to_string()),
            (132.58, 132.95, "marge".to_string()),
            (132.95, 133.24, "dans".to_string()),
            (133.25, 133.40, "un".to_string()),
            (133.40, 133.93, "premier".to_string()),
            (133.93, 134.53, "temps.".to_string()),
            (134.53, 135.34, "D'accord.".to_string()),
            (135.34, 135.49, "On".to_string()),
            (135.49, 135.93, "affine".to_string()),
            (135.93, 136.15, "sur".to_string()),
            (136.15, 136.30, "la".to_string()),
            (136.30, 137.05, "semaine.".to_string()),
            (137.05, 137.20, "Et".to_string()),
            (137.20, 137.65, "donc,".to_string()),
            (137.65, 138.28, "contacter".to_string()),
            (138.36, 138.55, "les".to_string()),
            (138.55, 138.77, "3".to_string()),
            (138.78, 139.68, "intervenants".to_string()),
            (139.68, 139.82, "et".to_string()),
            (139.83, 139.91, "le".to_string()),
            (140.01, 140.50, "comité".to_string()),
            (140.50, 141.55, "scientifique,".to_string()),
            (141.55, 141.70, "on".to_string()),
            (141.70, 141.85, "le".to_string()),
            (141.85, 142.13, "fait".to_string()),
            (142.15, 142.30, "la".to_string()),
            (142.30, 142.82, "semaine".to_string()),
            (142.82, 143.05, "qui".to_string()),
            (143.05, 143.20, "va".to_string()),
            (143.20, 143.85, "suivre.".to_string()),
            (143.90, 144.32, "Donc,".to_string()),
            (144.32, 144.43, "à".to_string()),
            (144.49, 144.92, "partir".to_string()),
            (144.92, 145.07, "de".to_string()),
            (145.07, 145.52, "lundi,".to_string()),
            (145.60, 145.71, "on".to_string()),
            (145.73, 145.95, "est".to_string()),
            (145.95, 146.09, "le".to_string()),
            (146.21, 146.78, "combien,".to_string()),
            (146.78, 146.97, "là".to_string()),
            (146.99, 147.21, "?".to_string()),
            (147.22, 147.36, "Le".to_string()),
            (147.70, 147.87, "12.".to_string()),
            (148.05, 148.19, "On".to_string()),
            (148.19, 148.49, "sera".to_string()),
            (148.49, 148.61, "le".to_string()),
            (148.87, 150.00, "12.".to_string()),
            (150.00, 150.41, "Donc,".to_string()),
            (150.41, 150.55, "du".to_string()),
            (150.55, 150.97, "12".to_string()),
            (150.97, 151.11, "au".to_string()),
            (151.11, 151.73, "16.".to_string()),
            (151.73, 151.86, "Du".to_string()),
            (151.86, 152.42, "12,".to_string()),
            (152.42, 152.63, "ça".to_string()),
            (152.63, 152.98, "prend".to_string()),
            (152.98, 153.11, "à".to_string()),
            (153.12, 153.33, "peu".to_string()),
            (153.33, 153.68, "près".to_string()),
            (153.68, 153.82, "un".to_string()),
            (153.82, 154.10, "mois".to_string()),
            (154.10, 154.38, "pour".to_string()),
            (154.38, 154.72, "avoir".to_string()),
            (154.73, 154.94, "les".to_string()),
            (154.94, 155.55, "réponses".to_string()),
            (155.55, 155.69, "de".to_string()),
            (155.69, 155.97, "tout".to_string()),
            (155.97, 156.10, "le".to_string()),
            (156.15, 156.66, "monde.".to_string()),
            (156.66, 156.80, "Tu".to_string()),
            (156.80, 157.15, "crois".to_string()),
            (157.15, 157.35, "?".to_string()),
            (157.36, 157.57, "Des".to_string()),
            (157.57, 157.78, "3".to_string()),
            (157.78, 157.95, "?".to_string()),
            (157.98, 158.27, "Dans".to_string()),
            (158.27, 158.41, "un".to_string()),
            (158.41, 158.76, "monde".to_string()),
            (158.77, 159.37, "idéal.".to_string()),
            (159.37, 159.51, "Il".to_string()),
            (159.51, 159.79, "faut".to_string()),
            (159.79, 159.95, "leur".to_string()),
        ];
        let segments: Vec<(f32, f32, usize)> = vec![
            (106.816, 134.693, 1),
            (126.914, 127.184, 3),
            (127.842, 128.500, 3),
            (130.424, 130.559, 3),
            (131.791, 132.297, 3),
            (135.976, 153.340, 2),
            (147.097, 149.324, 3),
            (155.062, 159.567, 0),
            (155.433, 155.450, 2),
            (155.450, 156.158, 3),
            (156.158, 156.935, 1),
            (159.567, 160.850, 1),
        ];
        let expected: Vec<Option<usize>> = vec![
            Some(1), Some(1), Some(1), Some(1), Some(1), Some(1), Some(1), Some(1),
            Some(1), Some(1), Some(1), Some(1), Some(1), Some(1), Some(1), Some(1),
            Some(1), Some(1), Some(1), Some(1), Some(1), Some(1), Some(1), Some(1),
            Some(1), Some(1), Some(1), Some(1), Some(1), Some(1), Some(1), Some(1),
            Some(1), Some(1), Some(1), Some(1), Some(1), Some(1), Some(1), Some(1),
            Some(1), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2),
            Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2),
            Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2),
            Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2),
            Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2),
            Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2),
            Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(2), Some(0),
            Some(0), Some(0), Some(0), Some(0), Some(0), Some(0), Some(0), Some(0),
            Some(0), Some(0), Some(0), Some(0), Some(0), Some(0), Some(0), Some(0),
            Some(0), Some(1), Some(1), Some(1),
        ];
        assert_eq!(assign_speakers(&units, &segments, 1.5, 1.0), expected);
    }
}
