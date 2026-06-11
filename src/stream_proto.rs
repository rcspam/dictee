//! Wire framing for the daemon `stream` mode: 4-byte big-endian length
//! prefix + payload. A zero-length frame is the end-of-stream sentinel.

use std::io::Read;

/// Maximum accepted frame payload (≈32 s of s16 mono 16 kHz audio).
/// A bigger length is a protocol error (e.g. an endianness bug in a
/// client), not a legitimate frame.
pub const MAX_FRAME_LEN: usize = 1024 * 1024;

/// Prefix `payload` with its big-endian u32 byte length.
pub fn frame(payload: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(4 + payload.len());
    out.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    out.extend_from_slice(payload);
    out
}

/// Read one length-prefixed frame. Returns `Ok(None)` on the zero-length
/// sentinel, `Err` on I/O failure or a length above `MAX_FRAME_LEN`.
pub fn read_frame<R: Read>(r: &mut R) -> std::io::Result<Option<Vec<u8>>> {
    let mut len_buf = [0u8; 4];
    r.read_exact(&mut len_buf)?;
    let n = u32::from_be_bytes(len_buf) as usize;
    if n == 0 {
        return Ok(None);
    }
    if n > MAX_FRAME_LEN {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!("frame length {n} exceeds maximum {MAX_FRAME_LEN}"),
        ));
    }
    let mut payload = vec![0u8; n];
    r.read_exact(&mut payload)?;
    Ok(Some(payload))
}

/// Decode little-endian s16 PCM bytes into normalised f32 samples in [-1, 1).
pub fn s16le_to_f32(bytes: &[u8]) -> Vec<f32> {
    bytes
        .chunks_exact(2)
        .map(|b| i16::from_le_bytes([b[0], b[1]]) as f32 / 32768.0)
        .collect()
}
