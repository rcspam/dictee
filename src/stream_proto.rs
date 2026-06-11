//! Wire framing for the daemon `stream` mode: 4-byte big-endian length
//! prefix + payload. A zero-length frame is the end-of-stream sentinel.

/// Prefix `payload` with its big-endian u32 byte length.
pub fn frame(payload: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(4 + payload.len());
    out.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    out.extend_from_slice(payload);
    out
}

/// Decode little-endian s16 PCM bytes into normalised f32 samples in [-1, 1).
pub fn s16le_to_f32(bytes: &[u8]) -> Vec<f32> {
    bytes
        .chunks_exact(2)
        .map(|b| i16::from_le_bytes([b[0], b[1]]) as f32 / 32768.0)
        .collect()
}
