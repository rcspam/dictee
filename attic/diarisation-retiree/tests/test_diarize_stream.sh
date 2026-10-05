#!/bin/bash
# Test du mode --stream de diarize-only
set -e
BIN="${BIN:-./target/release/diarize-only}"
SAMPLE="${SAMPLE:-tests/fixtures/diarize_sample_30s.wav}"

[ -x "$BIN" ] || { echo "FAIL: $BIN absent"; exit 1; }
[ -f "$SAMPLE" ] || { echo "SKIP: fixture $SAMPLE absente (créer avec: arecord -d 30 -f S16_LE -r 16000 -c 1 $SAMPLE)"; exit 0; }

{
  echo "FILE: $SAMPLE"
  sleep 1
  echo "FILE: $SAMPLE"
  sleep 1
} | $BIN --stream 2>/tmp/diarize_stream.err > /tmp/diarize_stream.out

chunk_count=$(awk 'NF==0 {c++} END {print c+0}' /tmp/diarize_stream.out)
if [ "$chunk_count" -lt 2 ]; then
  echo "FAIL: attendu >= 2 chunks délimités par ligne vide, vu $chunk_count"
  cat /tmp/diarize_stream.out
  exit 1
fi

grep -q "\[diarize-only --stream\] ready" /tmp/diarize_stream.err || {
  echo "FAIL: pas de message ready"
  exit 1
}

echo "PASS: stream mode emits $chunk_count chunks"

# Test RESET command
{
  echo "FILE: $SAMPLE"
  sleep 0.5
  echo "RESET"
  sleep 0.5
  echo "FILE: $SAMPLE"
} | $BIN --stream 2>>/tmp/diarize_stream.err >> /tmp/diarize_stream.out

grep -q "^RESET_OK$" /tmp/diarize_stream.out || {
  echo "FAIL: pas de RESET_OK dans l'output"
  exit 1
}

echo "PASS: RESET command acknowledged"
