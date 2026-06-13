use anyhow::{Context, Result};
use candle::{Device, Tensor};
use std::path::Path;

#[derive(Debug, serde::Deserialize)]
struct SttConfig {
    audio_silence_prefix_seconds: f64,
    audio_delay_seconds: f64,
}

#[derive(Debug, serde::Deserialize)]
#[allow(dead_code)]
struct Config {
    mimi_name: String,
    tokenizer_name: String,
    card: usize,
    text_card: usize,
    dim: usize,
    n_q: usize,
    context: usize,
    max_period: f64,
    num_heads: usize,
    num_layers: usize,
    causal: bool,
    stt_config: SttConfig,
}

impl Config {
    fn model_config(&self) -> moshi::lm::Config {
        let lm_cfg = moshi::transformer::Config {
            d_model: self.dim,
            num_heads: self.num_heads,
            num_layers: self.num_layers,
            dim_feedforward: self.dim * 4,
            causal: self.causal,
            norm_first: true,
            bias_ff: false,
            bias_attn: false,
            layer_scale: None,
            context: self.context,
            max_period: self.max_period as usize,
            use_conv_block: false,
            use_conv_bias: true,
            cross_attention: None,
            gating: Some(candle_nn::Activation::Silu),
            norm: moshi::NormType::RmsNorm,
            positional_embedding: moshi::transformer::PositionalEmbedding::Rope,
            conv_layout: false,
            conv_kernel_size: 3,
            kv_repeat: 1,
            max_seq_len: 4096 * 4,
            shared_cross_attn: false,
        };
        moshi::lm::Config {
            transformer: lm_cfg,
            depformer: None,
            audio_vocab_size: self.card + 1,
            text_in_vocab_size: self.text_card + 1,
            text_out_vocab_size: self.text_card,
            audio_codebooks: self.n_q,
            conditioners: Default::default(),
            extra_heads: None,
        }
    }
}

pub struct KyutaiModel {
    state: moshi::asr::State,
    text_tokenizer: sentencepiece::SentencePieceProcessor,
    config: Config,
    dev: Device,
    /// Carry-over buffer for streaming (Task 5).
    #[allow(dead_code)]
    carry_24k: Vec<f32>,
}

impl KyutaiModel {
    /// Load from a local dir containing config.json, model.safetensors, the mimi
    /// file and the tokenizer (both named inside config.json). GPU only.
    pub fn load(model_dir: &Path, dev: &Device) -> Result<Self> {
        let config_file = model_dir.join("config.json");
        let config: Config = serde_json::from_str(
            &std::fs::read_to_string(&config_file)
                .with_context(|| format!("reading {}", config_file.display()))?,
        )?;
        let tokenizer_file = model_dir.join(&config.tokenizer_name);
        let model_file = model_dir.join("model.safetensors");
        let mimi_file = model_dir.join(&config.mimi_name);

        let text_tokenizer =
            sentencepiece::SentencePieceProcessor::open(tokenizer_file.to_str().unwrap())?;
        let dtype = dev.bf16_default_to_f32();
        let vb_lm = unsafe {
            candle_nn::VarBuilder::from_mmaped_safetensors(&[&model_file], dtype, dev)?
        };
        let lm = moshi::lm::LmModel::new(
            &config.model_config(),
            moshi::nn::MaybeQuantizedVarBuilder::Real(vb_lm),
        )?;
        let audio_tokenizer = moshi::mimi::load(mimi_file.to_str().unwrap(), Some(32), dev)?;
        let asr_delay_in_tokens = (config.stt_config.audio_delay_seconds * 12.5) as usize;
        let state = moshi::asr::State::new(1, asr_delay_in_tokens, 0., audio_tokenizer, lm)?;

        Ok(KyutaiModel {
            state,
            text_tokenizer,
            config,
            dev: dev.clone(),
            carry_24k: Vec::new(),
        })
    }

    /// Transcribe a full buffer of 24 kHz mono f32 samples. Returns plain text.
    /// Resets state so the daemon can reuse the model.
    pub fn transcribe_samples(&mut self, mut pcm: Vec<f32>) -> Result<String> {
        // Defensive reset: start every request from clean state, regardless of
        // how the previous one ended (a `?` failure below would otherwise leave
        // the moshi State polluted for the next batch request).
        self.state.reset()?;
        if self.config.stt_config.audio_silence_prefix_seconds > 0.0 {
            let s = (self.config.stt_config.audio_silence_prefix_seconds * 24000.0) as usize;
            pcm.splice(0..0, vec![0.0; s]);
        }
        let suffix = (self.config.stt_config.audio_delay_seconds * 24000.0) as usize;
        pcm.resize(pcm.len() + suffix + 24000, 0.0);

        let mut words: Vec<String> = Vec::new();
        for chunk in pcm.chunks(1920) {
            let t = Tensor::new(chunk, &self.dev)?.reshape((1, 1, ()))?;
            for msg in self.state.step_pcm(t, None, &().into(), |_, _, _| ())?.iter() {
                if let moshi::asr::AsrMsg::Word { tokens, .. } = msg {
                    words.push(self.text_tokenizer.decode_piece_ids(tokens).unwrap_or_default());
                }
            }
        }
        self.state.reset()?;
        Ok(words.join(" "))
    }
}

/// Decode a WAV to 24 kHz mono f32 (downmix + resample as needed).
pub fn wav_to_24k_mono(path: &str) -> Result<Vec<f32>> {
    let mut r = hound::WavReader::open(path)?;
    let spec = r.spec();
    let raw: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => r.samples::<f32>().collect::<Result<_, _>>()?,
        hound::SampleFormat::Int => r
            .samples::<i16>()
            .map(|s| s.map(|s| s as f32 / 32768.0))
            .collect::<Result<_, _>>()?,
    };
    let mono: Vec<f32> = if spec.channels > 1 {
        raw.chunks(spec.channels as usize)
            .map(|c| c.iter().sum::<f32>() / spec.channels as f32)
            .collect()
    } else {
        raw
    };
    let out = if spec.sample_rate == 24_000 {
        mono
    } else {
        kaudio::resample(&mono, spec.sample_rate as usize, 24_000)?
    };
    Ok(out)
}
