// Integration test for the daemon stream-mode framing helpers.
// The full end-to-end test (with the model) is #[ignore]; this one is pure.
use std::process::Command;

#[test]
fn frame_roundtrip_be_length_prefix() {
    // 4-byte big-endian length prefix + payload; length 0 = sentinel.
    let payload: &[u8] = &[1, 0, 2, 0]; // two s16 samples
    let framed = parakeet_rs::stream_proto::frame(payload);
    assert_eq!(&framed[0..4], &[0, 0, 0, 4]);
    assert_eq!(&framed[4..], payload);

    let sentinel = parakeet_rs::stream_proto::frame(&[]);
    assert_eq!(sentinel, vec![0, 0, 0, 0]);
}

#[test]
fn s16le_to_f32_scales_by_32768() {
    let bytes: &[u8] = &[0x00, 0x40]; // 0x4000 = 16384 little-endian
    let out = parakeet_rs::stream_proto::s16le_to_f32(bytes);
    assert_eq!(out.len(), 1);
    assert!((out[0] - 0.5).abs() < 1e-4);
}

#[test]
fn s16le_to_f32_min_value_is_neg_one() {
    // 0x00 0x80 = 0x8000 little-endian = -32768 → -32768 / 32768.0 = -1.0
    let bytes: &[u8] = &[0x00, 0x80];
    let out = parakeet_rs::stream_proto::s16le_to_f32(bytes);
    assert_eq!(out.len(), 1);
    assert!((out[0] - (-1.0f32)).abs() < 1e-6);
}

#[test]
fn read_frame_roundtrip() {
    use parakeet_rs::stream_proto::{frame, read_frame};
    let payload: &[u8] = b"hello stream";
    let framed = frame(payload);
    let result = read_frame(&mut framed.as_slice()).unwrap();
    assert_eq!(result, Some(payload.to_vec()));
}

#[test]
fn read_frame_sentinel_returns_none() {
    use parakeet_rs::stream_proto::{frame, read_frame};
    let sentinel = frame(&[]);
    let result = read_frame(&mut sentinel.as_slice()).unwrap();
    assert_eq!(result, None);
}

#[test]
fn read_frame_oversized_returns_invalid_data() {
    use parakeet_rs::stream_proto::{MAX_FRAME_LEN, read_frame};
    // Encode a length just above the cap.
    let too_big = (MAX_FRAME_LEN + 1) as u32;
    let header = too_big.to_be_bytes();
    let mut src = header.as_slice();
    let err = read_frame(&mut src).unwrap_err();
    assert_eq!(err.kind(), std::io::ErrorKind::InvalidData);
}

/// End-to-end stream test: spawn the daemon with the multilingual Nemotron
/// model, stream ref-fr.wav in 100ms frames, assert the final transcript
/// matches the known reference. Requires the model — run with:
///   DICTEE_NEMO_DIR=tests/poc-nemotron/nemotron_multi \
///   cargo test --release --features cpu --test streaming_daemon -- --ignored
#[test]
#[ignore]
fn stream_ref_fr_matches_reference() {
    use parakeet_rs::stream_proto::{frame, read_frame};
    use std::io::Write;
    use std::os::unix::net::UnixStream;

    let model_dir = std::env::var("DICTEE_NEMO_DIR")
        .expect("set DICTEE_NEMO_DIR to the multilingual Nemotron model dir");
    let sock = "/tmp/dictee-stream-test.sock";
    let _ = std::fs::remove_file(sock);

    let mut daemon = Command::new(env!("CARGO_BIN_EXE_transcribe-daemon"))
        .args(["--nemotron", &model_dir, "--socket", sock])
        .spawn()
        .expect("spawn daemon");

    // Wait for the socket to appear (model load ~3.5s).
    for _ in 0..120 {
        if std::path::Path::new(sock).exists() { break; }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }

    let mut conn = UnixStream::connect(sock).expect("connect");
    conn.write_all(b"stream\tlang:fr\n").unwrap();

    // Read ref-fr.wav, skip 44-byte header, stream s16 frames of 3200 bytes.
    let wav = std::fs::read("tests/poc-nemotron/ref-fr.wav").expect("ref-fr.wav");
    for chunk in wav[44..].chunks(3200) {
        conn.write_all(&frame(chunk)).unwrap();
    }
    conn.write_all(&frame(&[])).unwrap(); // sentinel

    // Collect all frames until EOF; the last one is the full transcript.
    let mut last = String::new();
    loop {
        match read_frame(&mut conn) {
            Ok(Some(buf)) => { last = String::from_utf8_lossy(&buf).to_string(); }
            Ok(None) | Err(_) => break,
        }
    }

    daemon.kill().ok();
    let _ = std::fs::remove_file(sock);

    let got = last.to_lowercase();
    // "français." WITH the final period: finalize_transcript() encodes the
    // last partial chunk with its true length (end-of-sequence), which is
    // what makes the model emit the final punctuation — parity with batch.
    assert!(got.contains("transcription") && got.contains("français."),
        "unexpected transcript: {last:?}");
}
