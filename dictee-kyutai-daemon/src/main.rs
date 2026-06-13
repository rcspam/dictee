mod model;
#[allow(dead_code)]
mod resample;
#[allow(dead_code)]
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

// Temporary stub until Task 5 implements it.
fn handle_stream(_m: &mut model::KyutaiModel, _r: BufReader<&UnixStream>) -> Result<()> {
    Ok(())
}
