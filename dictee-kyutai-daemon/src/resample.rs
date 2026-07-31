//! Resample dictee's 16 kHz mono audio to Kyutai's native 24 kHz.
pub fn to_24k(samples_16k: &[f32]) -> Vec<f32> {
    if samples_16k.is_empty() {
        return Vec::new();
    }
    kaudio::resample(samples_16k, 16_000, 24_000).expect("16k->24k resample")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn output_length_is_1_5x() {
        let out = to_24k(&vec![0.0f32; 16000]); // 1 s @ 16 kHz
        // Allow tolerance for resampler padding/rounding (roughly 1.5x the input)
        assert!((out.len() as i64 - 24000).abs() <= 1024, "got {}", out.len());
    }
    #[test]
    fn empty_input_empty_output() {
        assert!(to_24k(&[]).is_empty());
    }
}
