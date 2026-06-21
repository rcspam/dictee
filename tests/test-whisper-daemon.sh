#!/bin/bash
# Integration: daemon --whisper serves a real FR transcription over the socket.
# Requires the build from Task 1 + the ggml on disk.
set -u
SOCK=/tmp/test-whisper-daemon.sock
GGML=/home/rapha/.local/share/voxtype/models/ggml-large-v3.bin
WAV="$PWD/tests/poc-kyutai/ref-fr.wav"
rm -f "$SOCK"
DICTEE_WHISPER_GGML=$GGML DICTEE_TRANSCRIBE_SOCKET=$SOCK ./target/release/transcribe-daemon --whisper --socket "$SOCK" >/tmp/test-whisper-daemon.log 2>&1 &
DPID=$!
until [ -S "$SOCK" ]; do sleep 1; done
sleep 2
OUT=$(DICTEE_TRANSCRIBE_SOCKET=$SOCK ./target/release/transcribe-client "$WAV")
kill -9 $DPID 2>/dev/null; rm -f "$SOCK"
echo "OUT: $OUT"
echo "$OUT" | grep -q "Bonjour" && echo "PASS" || { echo "FAIL"; cat /tmp/test-whisper-daemon.log; exit 1; }
