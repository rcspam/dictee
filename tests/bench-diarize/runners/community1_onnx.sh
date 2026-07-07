#!/usr/bin/env bash
# Runner: community-1 ONNX port (pyannote-rs PR#24 fork + our iterator fix,
# see .tools/pyannote-rs-c1) via the bench_rttm example CLI.
# Usage: runners/community1_onnx.sh <corpus> <auto|oracle> [threshold]
# Candidate id = community1-onnx-th<thr> | community1-onnx-oracle.
# CPU only on purpose: 32 MB models, RTF ~0.07, no GPU contention.
. "$(dirname "$0")/../env.sh"

corpus="$1"; mode="$2"; thr="${3:-0.5}"
TC="$BENCH/.tools/pyannote-rs-c1"
BIN="$TC/target/release/examples/bench_rttm"
[ -x "$BIN" ] || die "bench_rttm not built — cargo build --release --example bench_rttm in $TC"
[ -d "$AUDIO/$corpus" ] || die "audio missing for $corpus (run fetch-corpora.sh)"

if [ "$mode" = oracle ]; then cand="community1-onnx-oracle"; else cand="community1-onnx-th$thr"; fi
out="$HYP/$cand/$corpus/$mode"; mkdir -p "$out"
errlog="$LOGS/$cand.$corpus.$mode.err"; : > "$errlog"

for wav in "$AUDIO/$corpus"/*.wav; do
  [ -e "$wav" ] || continue
  id="$(basename "$wav" .wav)"
  if [ "$mode" = oracle ]; then
    n="$(count_speakers "$REF/$corpus/$id.rttm" "$id")"; [ "$n" -ge 1 ] || n=1
    C1_MODELS="$TC" "$BIN" "$wav" "$id" oracle "$n" "$thr" > "$out/$id.rttm" 2>>"$errlog" \
      || log "FAIL $cand $id"
  else
    C1_MODELS="$TC" "$BIN" "$wav" "$id" auto "$thr" > "$out/$id.rttm" 2>>"$errlog" \
      || log "FAIL $cand $id"
  fi
done
cat "$out"/*.rttm > "$out/_all.rttm" 2>/dev/null || true
log "done $cand / $corpus / $mode"
