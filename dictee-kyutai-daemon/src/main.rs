mod model;
#[allow(dead_code)]
mod resample;
mod stream_proto;

use anyhow::Result;
use candle::Device;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::time::Duration;

fn socket_path() -> String {
    if let Ok(p) = std::env::var("DICTEE_TRANSCRIBE_SOCKET") {
        return p;
    }
    if let Ok(dir) = std::env::var("XDG_RUNTIME_DIR") {
        format!("{dir}/transcribe.sock")
    } else {
        format!("/tmp/transcribe-{}.sock", unsafe { libc::getuid() })
    }
}

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let sock = args
        .windows(2)
        .find(|w| w[0] == "--socket")
        .map(|w| w[1].clone())
        .unwrap_or_else(socket_path);

    let model_dir = resolve_model_dir()?;
    let dev = Device::new_cuda(0)
        .map_err(|e| anyhow::anyhow!("Kyutai requires an NVIDIA GPU (CUDA): {e}"))?;
    let mut model = model::KyutaiModel::load(&model_dir, &dev)?;

    if std::env::var("DICTEE_DAEMON_NO_PROVIDER").as_deref() != Ok("1") {
        let _ = std::fs::write("/dev/shm/.dictee_provider", "cuda");
    }

    let _ = std::fs::remove_file(&sock);
    let listener = UnixListener::bind(&sock)?;
    std::fs::set_permissions(&sock, std::fs::Permissions::from_mode(0o600))?;
    eprintln!("[kyutai] listening on {sock}");

    for stream in listener.incoming() {
        let mut stream = match stream {
            Ok(s) => s,
            Err(_) => continue,
        };
        let _ = stream.set_read_timeout(Some(Duration::from_secs(30)));
        let _ = stream.set_write_timeout(Some(Duration::from_secs(30)));
        let mut reader = BufReader::new(&stream);
        let mut line = String::new();
        match reader.read_line(&mut line) {
            Ok(0) | Err(_) => continue,
            Ok(_) => {}
        }
        let line = line.trim().to_string();

        if line == "stream" || line.starts_with("stream\t") {
            if let Err(e) = handle_stream(&mut model, reader) {
                eprintln!("[kyutai] stream error: {e}");
            }
            continue;
        }

        drop(reader);
        let path = line.split('\t').next().unwrap_or("").trim();
        match (|| -> Result<String> {
            let pcm = model::wav_to_24k_mono(path)?;
            model.transcribe_samples(pcm)
        })() {
            Ok(text) => {
                let _ = writeln!(stream, "{}", text.trim());
            }
            Err(e) => {
                eprintln!("[kyutai] batch error: {e}");
                let _ = writeln!(stream, "ERROR: {e}");
            }
        }
    }
    Ok(())
}

fn resolve_model_dir() -> Result<PathBuf> {
    let candidates = model_dir_candidates();
    for c in &candidates {
        if c.join("model.safetensors").exists() {
            return Ok(c.clone());
        }
    }
    anyhow::bail!(
        "Kyutai model not found. Looked in: {}. Download it from dictee-setup.",
        candidates
            .iter()
            .map(|p| p.display().to_string())
            .collect::<Vec<_>>()
            .join(", ")
    )
}

fn model_dir_candidates() -> Vec<PathBuf> {
    let mut v = Vec::new();
    if let Ok(home) = std::env::var("HOME") {
        v.push(PathBuf::from(home).join(".local/share/dictee/kyutai"));
    }
    v.push(PathBuf::from("/usr/share/dictee/kyutai"));
    v
}

/// Streaming mode: read length-prefixed s16le 16 kHz mono frames, emit a frame
/// of newly-finalized words after each input frame, and a final frame with the
/// full transcript once the zero-length sentinel arrives. Mirrors the contract
/// of `transcribe_daemon.rs` stream mode (length-prefixed, fragments + final).
fn handle_stream(model: &mut model::KyutaiModel, reader: BufReader<&UnixStream>) -> Result<()> {
    let result = stream_session(model, reader);
    // ALWAYS reset, even if the session errored mid-stream — best-effort. Leaving
    // the streaming buffers / resampler FFT state / moshi state dirty would corrupt
    // the leading output of the NEXT stream session reusing this same model.
    let _ = model.reset_stream();
    result
}

fn stream_session(model: &mut model::KyutaiModel, reader: BufReader<&UnixStream>) -> Result<()> {
    use stream_proto::{frame, read_frame, s16le_to_f32};
    let mut writer = reader.get_ref().try_clone()?;
    let mut reader = reader;
    let mut full = String::new();
    let mut sentinel = false;
    loop {
        match read_frame(&mut reader) {
            Ok(None) => {
                sentinel = true;
                break;
            }
            Err(_) => break, // EOF/timeout/oversized = abnormal end
            Ok(Some(payload)) => {
                let frag = model.step_16k(&s16le_to_f32(&payload))?;
                if !frag.is_empty() {
                    // frag already carries a leading space per word; concatenate
                    // as-is (no extra separator) for the final-transcript frame.
                    full.push_str(&frag);
                    writer.write_all(&frame(frag.as_bytes()))?;
                    writer.flush()?;
                }
            }
        }
    }
    if sentinel {
        let tail = model.flush()?;
        if !tail.is_empty() {
            full.push_str(&tail); // tail carries its own leading spaces
            // Emit the flushed tail as a LIVE fragment too (not only inside the
            // final-transcript frame), mirroring the Nemotron daemon's
            // finalize_transcript fragment. dictee-stream types live fragments
            // even when re-transcribe is off; without this the last words held
            // back by the model's ASR delay would never be typed (end cut off).
            writer.write_all(&frame(tail.as_bytes()))?;
            writer.flush()?;
        }
        // Last frame = the full transcript.
        writer.write_all(&frame(full.trim().as_bytes()))?;
        writer.flush()?;
    }
    Ok(())
}
