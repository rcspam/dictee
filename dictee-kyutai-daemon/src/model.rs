use anyhow::{Context, Result};
use candle::{Device, Tensor};
use rubato::{FftFixedInOut, Resampler};
use std::path::Path;

/// Streaming resampler chunk size (input frames). Same value kaudio's one-shot
/// `resample` passes to `FftFixedInOut::new` (kaudio 0.2.1 lib.rs:190).
const RESAMPLER_CHUNK_IN: usize = 1024;
/// moshi consumes 24 kHz PCM in fixed 1920-sample steps (80 ms @ 24 kHz).
const STEP_PCM: usize = 1920;

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
    /// Persistent 16 kHz input accumulation buffer for streaming. Holds raw
    /// samples not yet consumed by the resampler (leftover < one chunk).
    in_16k: Vec<f32>,
    /// Persistent 24 kHz output carry buffer for streaming. Holds resampled
    /// samples not yet drained in whole 1920-sample steps into the model.
    carry_24k: Vec<f32>,
    /// ONE persistent resampler for the whole streaming session, so FFT state
    /// (overlap/edges) is continuous across frame boundaries. Recreating it per
    /// frame (as kaudio's one-shot `resample` does) would inject block-quantized
    /// padding and FFT discontinuities mid-stream. Reset only via reset_stream.
    resampler: FftFixedInOut<f32>,
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

        let resampler = FftFixedInOut::<f32>::new(16_000, 24_000, RESAMPLER_CHUNK_IN, 1)?;

        Ok(KyutaiModel {
            state,
            text_tokenizer,
            config,
            dev: dev.clone(),
            in_16k: Vec::new(),
            carry_24k: Vec::new(),
            resampler,
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

    /// Decode one 24 kHz PCM chunk through the moshi state, collecting the text
    /// of any finalized words. Same logic as the batch loop body.
    fn step_chunk(&mut self, chunk: &[f32]) -> Result<Vec<String>> {
        let t = Tensor::new(chunk, &self.dev)?.reshape((1, 1, ()))?;
        let mut words = Vec::new();
        for msg in self.state.step_pcm(t, None, &().into(), |_, _, _| ())?.iter() {
            if let moshi::asr::AsrMsg::Word { tokens, .. } = msg {
                words.push(self.text_tokenizer.decode_piece_ids(tokens).unwrap_or_default());
            }
        }
        Ok(words)
    }

    /// Drain `self.carry_24k` in whole 1920-sample steps into the model, leaving
    /// any sub-step remainder buffered. Returns the newly finalized words.
    fn drain_carry(&mut self) -> Result<Vec<String>> {
        let mut words = Vec::new();
        let mut consumed = 0;
        while self.carry_24k.len() - consumed >= STEP_PCM {
            let chunk: Vec<f32> = self.carry_24k[consumed..consumed + STEP_PCM].to_vec();
            words.extend(self.step_chunk(&chunk)?);
            consumed += STEP_PCM;
        }
        if consumed > 0 {
            self.carry_24k.drain(0..consumed);
        }
        Ok(words)
    }

    /// Streaming: feed one frame of raw 16 kHz mono f32 samples. Appends to the
    /// persistent input buffer, resamples whole chunks to 24 kHz through the
    /// PERSISTENT resampler (continuous FFT state), then drains the 24 kHz carry
    /// in 1920-sample model steps. Returns the newly finalized words joined by
    /// spaces (may be empty). Does NOT reset state between frames.
    pub fn step_16k(&mut self, frame_16k: &[f32]) -> Result<String> {
        self.in_16k.extend_from_slice(frame_16k);

        let need = self.resampler.input_frames_next();
        let out_max = self.resampler.output_frames_max();
        let mut out_buf = vec![vec![0.0f32; out_max]];
        let mut pos = 0;
        while self.in_16k.len() - pos >= need {
            let (in_len, out_len) = self.resampler.process_into_buffer(
                &[&self.in_16k[pos..pos + need]],
                &mut out_buf,
                None,
            )?;
            self.carry_24k.extend_from_slice(&out_buf[0][..out_len]);
            pos += in_len;
        }
        if pos > 0 {
            self.in_16k.drain(0..pos);
        }

        let words = self.drain_carry()?;
        // Streaming fragments must carry a leading space per word: dictee-stream
        // injects no spacing of its own (it relies on ASR word-boundary spaces,
        // like Nemotron's). Without this, consecutive fragments glue together.
        Ok(words.iter().filter(|w| !w.is_empty()).map(|w| format!(" {w}")).collect())
    }

    /// Streaming: end of audio. Flush the leftover 16 kHz input through the
    /// resampler (partial, zero-padded), then append the model delay + ~1 s of
    /// 24 kHz silence (mirrors the batch tail) so the last words get emitted,
    /// and drain ALL of the 24 kHz carry. Returns the final words joined.
    pub fn flush(&mut self) -> Result<String> {
        let out_max = self.resampler.output_frames_max();
        let mut out_buf = vec![vec![0.0f32; out_max]];

        if !self.in_16k.is_empty() {
            let leftover = std::mem::take(&mut self.in_16k);
            let (_in_len, out_len) =
                self.resampler
                    .process_partial_into_buffer(Some(&[&leftover[..]]), &mut out_buf, None)?;
            self.carry_24k.extend_from_slice(&out_buf[0][..out_len]);
        }

        // Mirror the batch tail: model delay + 1 s of 24 kHz silence so the last
        // word(s) clear the ASR delay and get finalized.
        let suffix = (self.config.stt_config.audio_delay_seconds * 24000.0) as usize;
        self.carry_24k.resize(self.carry_24k.len() + suffix + 24000, 0.0);

        // Drain everything, padding the final partial step to a full 1920 chunk.
        let mut words = self.drain_carry()?;
        if !self.carry_24k.is_empty() {
            let mut last = std::mem::take(&mut self.carry_24k);
            last.resize(STEP_PCM, 0.0);
            words.extend(self.step_chunk(&last)?);
        }
        // Leading space per word (see step_16k) so live fragments and the final
        // transcript frame concatenate with correct spacing.
        Ok(words.iter().filter(|w| !w.is_empty()).map(|w| format!(" {w}")).collect())
    }

    /// Streaming: reset for the next session. Clears the input/carry buffers,
    /// recreates a FRESH resampler (clean FFT state), and resets the moshi state.
    pub fn reset_stream(&mut self) -> Result<()> {
        self.in_16k.clear();
        self.carry_24k.clear();
        self.resampler = FftFixedInOut::<f32>::new(16_000, 24_000, RESAMPLER_CHUNK_IN, 1)?;
        self.state.reset()?;
        Ok(())
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
