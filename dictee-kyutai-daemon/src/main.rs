mod model;
#[allow(dead_code)]
mod resample;
#[allow(dead_code)]
mod stream_proto;

use anyhow::Result;
use candle::Device;
use std::path::PathBuf;

fn main() -> Result<()> {
    let model_dir = resolve_model_dir()?;
    let dev = Device::new_cuda(0)
        .map_err(|e| anyhow::anyhow!("Kyutai requires an NVIDIA GPU (CUDA): {e}"))?;
    eprintln!("[kyutai] loading model from {}", model_dir.display());
    let _model = model::KyutaiModel::load(&model_dir, &dev)?;
    eprintln!("[kyutai] model loaded OK");
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
