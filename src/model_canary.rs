use crate::error::{Error, Result};
use crate::execution::ModelConfig as ExecutionConfig;
use ndarray::{Array2, Array3, Array4};
use ort::session::Session;
use std::path::{Path, PathBuf};

/// Canary-1B-v2 AED model configuration
#[derive(Debug, Clone)]
pub struct CanaryModelConfig {
    /// Vocabulary size (16384 for Canary-1B-v2)
    pub vocab_size: usize,
    /// Maximum decoder sequence length
    pub max_sequence_length: usize,
    /// Number of decoder memory layers (KV-cache depth)
    pub n_layers_decoder_mems: usize,
    /// Hidden dimension of encoder/decoder embeddings
    pub decoder_hidden_dim: usize,
}

impl Default for CanaryModelConfig {
    fn default() -> Self {
        Self {
            vocab_size: 16384,
            max_sequence_length: 1024,
            n_layers_decoder_mems: 10,
            decoder_hidden_dim: 1024,
        }
    }
}

impl CanaryModelConfig {
    #[allow(dead_code)]
    pub fn new() -> Self {
        Self::default()
    }
}

/// Canary-1B-v2 AED (Attention Encoder-Decoder) model
///
/// Manages ONNX Runtime sessions for the encoder and decoder.
/// The decoder is auto-regressive with KV-cache (decoder_mems).
pub struct CanaryModel {
    encoder: Session,
    decoder: Session,
    pub config: CanaryModelConfig,
}

impl CanaryModel {
    /// Load Canary model from a directory containing encoder and decoder ONNX files
    ///
    /// # Arguments
    /// * `model_dir` - Directory containing `encoder-model.onnx` and `decoder-model.onnx`
    /// * `exec_config` - Execution configuration for ONNX Runtime
    pub fn from_pretrained<P: AsRef<Path>>(
        model_dir: P,
        exec_config: ExecutionConfig,
    ) -> Result<Self> {
        let model_dir = model_dir.as_ref();

        let encoder_path = Self::find_encoder(model_dir)?;
        let decoder_path = Self::find_decoder(model_dir)?;

        let config = CanaryModelConfig::default();

        // Load encoder session
        let builder = Session::builder()?;
        let builder = exec_config.apply_to_session_builder(builder)?;
        let encoder = builder.commit_from_file(&encoder_path)?;

        // Load decoder session
        let builder = Session::builder()?;
        let builder = exec_config.apply_to_session_builder(builder)?;
        let decoder = builder.commit_from_file(&decoder_path)?;

        Ok(Self {
            encoder,
            decoder,
            config,
        })
    }

    /// Find the encoder ONNX file in the model directory
    fn find_encoder(dir: &Path) -> Result<PathBuf> {
        let candidates = [
            "encoder-model.onnx",
            "encoder.onnx",
            "encoder-model.int8.onnx",
        ];
        for candidate in &candidates {
            let path = dir.join(candidate);
            if path.exists() {
                return Ok(path);
            }
        }
        // Fallback: any file starting with "encoder" and ending with ".onnx"
        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if let Some(name) = path.file_name().and_then(|s| s.to_str()) {
                    if name.starts_with("encoder") && name.ends_with(".onnx") {
                        return Ok(path);
                    }
                }
            }
        }
        Err(Error::Config(format!(
            "No encoder model found in {}",
            dir.display()
        )))
    }

    /// Find the decoder ONNX file in the model directory
    fn find_decoder(dir: &Path) -> Result<PathBuf> {
        let candidates = [
            "decoder-model.onnx",
            "decoder.onnx",
            "decoder-model.int8.onnx",
        ];
        for candidate in &candidates {
            let path = dir.join(candidate);
            if path.exists() {
                return Ok(path);
            }
        }
        // Fallback: any file starting with "decoder" and ending with ".onnx",
        // excluding "decoder_joint" (TDT model)
        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if let Some(name) = path.file_name().and_then(|s| s.to_str()) {
                    if name.starts_with("decoder")
                        && !name.starts_with("decoder_joint")
                        && name.ends_with(".onnx")
                    {
                        return Ok(path);
                    }
                }
            }
        }
        Err(Error::Config(format!(
            "No decoder model found in {}",
            dir.display()
        )))
    }

    /// Run the encoder on mel-spectrogram features
    ///
    /// # Arguments
    /// * `features` - Mel-spectrogram of shape (frames, 128)
    ///
    /// # Returns
    /// * `encoder_embeddings` - Shape (1, encoded_len, 1024)
    /// * `encoder_mask` - Shape (1, encoded_len)
    pub fn run_encoder(
        &mut self,
        features: Array2<f32>,
    ) -> Result<(Array3<f32>, Array2<i64>)> {
        let frames = features.shape()[0];
        let mel_bins = features.shape()[1]; // 128

        // Canary encoder expects (batch, mel_bins, frames) = (1, 128, frames)
        let input = features
            .t()
            .to_shape((1, mel_bins, frames))
            .map_err(|e| Error::Model(format!("Failed to reshape encoder input: {e}")))?
            .to_owned();

        let length = ndarray::Array1::from_vec(vec![frames as i64]);

        let input_value = ort::value::Value::from_array(input)?;
        let length_value = ort::value::Value::from_array(length)?;

        let outputs = self.encoder.run(ort::inputs!(
            "audio_signal" => input_value,
            "length" => length_value
        ))?;

        // Extract encoder_embeddings: [batch, encoded_len, 1024]
        let (emb_shape, emb_data) = outputs["encoder_embeddings"]
            .try_extract_tensor::<f32>()
            .map_err(|e| {
                Error::Model(format!("Failed to extract encoder_embeddings: {e}"))
            })?;

        let emb_dims = emb_shape.as_ref();
        if emb_dims.len() != 3 {
            return Err(Error::Model(format!(
                "Expected 3D encoder_embeddings, got shape: {emb_dims:?}"
            )));
        }

        let encoder_embeddings = Array3::from_shape_vec(
            (emb_dims[0] as usize, emb_dims[1] as usize, emb_dims[2] as usize),
            emb_data.to_vec(),
        )
        .map_err(|e| Error::Model(format!("Failed to create encoder_embeddings array: {e}")))?;

        // Extract encoder_mask: [batch, encoded_len]
        let (mask_shape, mask_data) = outputs["encoder_mask"]
            .try_extract_tensor::<i64>()
            .map_err(|e| {
                Error::Model(format!("Failed to extract encoder_mask: {e}"))
            })?;

        let mask_dims = mask_shape.as_ref();
        if mask_dims.len() != 2 {
            return Err(Error::Model(format!(
                "Expected 2D encoder_mask, got shape: {mask_dims:?}"
            )));
        }

        let encoder_mask = Array2::from_shape_vec(
            (mask_dims[0] as usize, mask_dims[1] as usize),
            mask_data.to_vec(),
        )
        .map_err(|e| Error::Model(format!("Failed to create encoder_mask array: {e}")))?;

        Ok((encoder_embeddings, encoder_mask))
    }

    /// Run one auto-regressive decoder step
    ///
    /// # Arguments
    /// * `input_ids` - Token IDs: full prompt on first step, single token thereafter. Shape (1, seq_len)
    /// * `encoder_embeddings` - From `run_encoder`. Shape (1, encoded_len, 1024)
    /// * `encoder_mask` - From `run_encoder`. Shape (1, encoded_len)
    /// * `decoder_mems` - KV-cache: shape (10, 1, mems_len, 1024). Use mems_len=0 for first step.
    ///
    /// # Returns
    /// * `logits` - Log-softmax output, shape (1, 1, 16384)
    /// * `decoder_hidden_states` - Updated KV-cache, shape (10, 1, new_mems_len, 1024)
    pub fn run_decoder(
        &mut self,
        input_ids: Array2<i64>,
        encoder_embeddings: Array3<f32>,
        encoder_mask: Array2<i64>,
        decoder_mems: Array4<f32>,
    ) -> Result<(Array3<f32>, Array4<f32>)> {
        let input_ids_value = ort::value::Value::from_array(input_ids)?;
        let emb_value = ort::value::Value::from_array(encoder_embeddings)?;
        let mask_value = ort::value::Value::from_array(encoder_mask)?;
        let mems_value = ort::value::Value::from_array(decoder_mems)?;

        let outputs = self.decoder.run(ort::inputs!(
            "input_ids" => input_ids_value,
            "encoder_embeddings" => emb_value,
            "encoder_mask" => mask_value,
            "decoder_mems" => mems_value
        ))?;

        // Extract logits: [batch, 1, vocab_size]
        let (logits_shape, logits_data) = outputs["logits"]
            .try_extract_tensor::<f32>()
            .map_err(|e| Error::Model(format!("Failed to extract logits: {e}")))?;

        let logits_dims = logits_shape.as_ref();
        if logits_dims.len() != 3 {
            return Err(Error::Model(format!(
                "Expected 3D logits, got shape: {logits_dims:?}"
            )));
        }

        let logits = Array3::from_shape_vec(
            (
                logits_dims[0] as usize,
                logits_dims[1] as usize,
                logits_dims[2] as usize,
            ),
            logits_data.to_vec(),
        )
        .map_err(|e| Error::Model(format!("Failed to create logits array: {e}")))?;

        // Extract decoder_hidden_states (updated KV-cache): [10, batch, new_mems_len, 1024]
        let (hs_shape, hs_data) = outputs["decoder_hidden_states"]
            .try_extract_tensor::<f32>()
            .map_err(|e| {
                Error::Model(format!("Failed to extract decoder_hidden_states: {e}"))
            })?;

        let hs_dims = hs_shape.as_ref();
        if hs_dims.len() != 4 {
            return Err(Error::Model(format!(
                "Expected 4D decoder_hidden_states, got shape: {hs_dims:?}"
            )));
        }

        let decoder_hidden_states = Array4::from_shape_vec(
            (
                hs_dims[0] as usize,
                hs_dims[1] as usize,
                hs_dims[2] as usize,
                hs_dims[3] as usize,
            ),
            hs_data.to_vec(),
        )
        .map_err(|e| {
            Error::Model(format!(
                "Failed to create decoder_hidden_states array: {e}"
            ))
        })?;

        Ok((logits, decoder_hidden_states))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_canary_config_default() {
        let config = CanaryModelConfig::default();
        assert_eq!(config.vocab_size, 16384);
        assert_eq!(config.max_sequence_length, 1024);
        assert_eq!(config.n_layers_decoder_mems, 10);
        assert_eq!(config.decoder_hidden_dim, 1024);
    }

    #[test]
    fn test_canary_config_new() {
        let config = CanaryModelConfig::new();
        assert_eq!(config.vocab_size, 16384);
        assert_eq!(config.max_sequence_length, 1024);
    }

    #[test]
    fn test_find_encoder_missing_dir() {
        let result = CanaryModel::find_encoder(Path::new("/nonexistent/path"));
        assert!(result.is_err());
        if let Err(Error::Config(msg)) = result {
            assert!(msg.contains("No encoder model found"));
        } else {
            panic!("Expected Error::Config");
        }
    }

    #[test]
    fn test_find_decoder_missing_dir() {
        let result = CanaryModel::find_decoder(Path::new("/nonexistent/path"));
        assert!(result.is_err());
        if let Err(Error::Config(msg)) = result {
            assert!(msg.contains("No decoder model found"));
        } else {
            panic!("Expected Error::Config");
        }
    }

    #[test]
    fn test_find_encoder_with_file() {
        let dir = std::env::temp_dir().join("canary_test_enc");
        let _ = std::fs::create_dir_all(&dir);
        let path = dir.join("encoder-model.onnx");
        std::fs::write(&path, b"dummy").unwrap();

        let result = CanaryModel::find_encoder(&dir);
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), path);

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_find_decoder_with_file() {
        let dir = std::env::temp_dir().join("canary_test_dec");
        let _ = std::fs::create_dir_all(&dir);
        let path = dir.join("decoder-model.onnx");
        std::fs::write(&path, b"dummy").unwrap();

        let result = CanaryModel::find_decoder(&dir);
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), path);

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_find_decoder_excludes_decoder_joint() {
        let dir = std::env::temp_dir().join("canary_test_joint");
        let _ = std::fs::create_dir_all(&dir);
        // Only a decoder_joint file — should NOT match
        std::fs::write(dir.join("decoder_joint-model.onnx"), b"dummy").unwrap();

        let result = CanaryModel::find_decoder(&dir);
        assert!(result.is_err());

        // Now add a proper decoder file
        let path = dir.join("decoder-model.onnx");
        std::fs::write(&path, b"dummy").unwrap();

        let result = CanaryModel::find_decoder(&dir);
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), path);

        let _ = std::fs::remove_dir_all(&dir);
    }
}
