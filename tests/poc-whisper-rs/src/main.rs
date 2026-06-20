// POC: transcribe a 16 kHz mono WAV with ggml large-v3 via whisper.cpp (whisper-rs).
//
// Success criterion: the output keeps punctuation + capitalization + a complete
// onset — the three things our faster-whisper/ctranslate2 large-v3 currently drops.
//
// Usage: poc <model.bin> <audio.wav> [lang]
//   lang defaults to "fr"; pass "auto" to let whisper detect.

use std::time::Instant;
use whisper_rs::{
    convert_integer_to_float_audio, convert_stereo_to_mono_audio, FullParams, SamplingStrategy,
    WhisperContext, WhisperContextParameters,
};

fn main() {
    let mut args = std::env::args().skip(1);
    let model_path = args.next().expect("usage: poc <model.bin> <audio.wav> [lang]");
    let wav_path = args.next().expect("usage: poc <model.bin> <audio.wav> [lang]");
    let lang = args.next().unwrap_or_else(|| "fr".to_string());

    // --- Load audio (must end up f32 16 kHz mono) ---
    let reader = hound::WavReader::open(&wav_path).expect("failed to open WAV");
    let spec = reader.spec();
    let samples: Vec<i16> = reader
        .into_samples::<i16>()
        .collect::<Result<Vec<_>, _>>()
        .expect("failed to read samples");

    let mut audio = vec![0.0f32; samples.len()];
    convert_integer_to_float_audio(&samples, &mut audio).expect("int->float failed");
    if spec.channels == 2 {
        let mut mono = vec![0.0f32; audio.len() / 2];
        convert_stereo_to_mono_audio(&audio, &mut mono).expect("stereo->mono failed");
        audio = mono;
    }
    assert_eq!(
        spec.sample_rate, 16000,
        "POC expects 16 kHz audio, got {} Hz — resample first",
        spec.sample_rate
    );
    let dur_s = audio.len() as f64 / 16000.0;
    println!(
        "audio: {} ({:.1}s, {} ch -> mono, {} Hz)",
        wav_path, dur_s, spec.channels, spec.sample_rate
    );

    // --- Load model ---
    let t = Instant::now();
    let ctx = WhisperContext::new_with_params(&model_path, WhisperContextParameters::default())
        .expect("failed to load model");
    let mut state = ctx.create_state().expect("failed to create state");
    println!("model loaded in {:.1}s: {}", t.elapsed().as_secs_f64(), model_path);

    // --- Params (rebuilt each pass: FullParams is consumed by full()) ---
    let threads = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4) as i32;
    let make_params = || {
        let mut params = FullParams::new(SamplingStrategy::BeamSearch { beam_size: 5, patience: -1.0 });
        if lang == "auto" {
            params.set_detect_language(true);
        } else {
            params.set_language(Some(&lang));
        }
        params.set_n_threads(threads);
        params.set_token_timestamps(true);
        params.set_print_special(false);
        params.set_print_progress(false);
        params.set_print_realtime(false);
        params.set_print_timestamps(false);
        params
    };

    // --- Transcribe several times on the SAME state ---
    // Pass 1 = cold (kernel/shader warmup included); passes 2+ = warm,
    // i.e. the resident-daemon regime where the model stays loaded.
    let passes: usize = std::env::var("POC_PASSES").ok().and_then(|s| s.parse().ok()).unwrap_or(3);
    for p in 1..=passes {
        let t = Instant::now();
        state.full(make_params(), &audio).expect("transcription failed");
        let elapsed = t.elapsed().as_secs_f64();
        let tag = if p == 1 { "cold" } else { "warm" };
        println!(
            "pass {}/{} [{}]: {:.2}s with {} threads (RTF {:.3})",
            p, passes, tag, elapsed, threads, elapsed / dur_s
        );
    }
    println!("--- transcript (last pass) ---");

    let n = state.full_n_segments();
    let mut full = String::new();
    for i in 0..n {
        let Some(seg) = state.get_segment(i) else { continue };
        let text = seg.to_str_lossy().map(|c| c.into_owned()).unwrap_or_default();
        let t0 = seg.start_timestamp();
        let t1 = seg.end_timestamp();
        println!("[{:>6.2} -> {:>6.2}] {}", t0 as f64 / 100.0, t1 as f64 / 100.0, text.trim());
        full.push_str(&text);
    }

    println!("--- raw concatenation ---\n{}", full.trim());
}
