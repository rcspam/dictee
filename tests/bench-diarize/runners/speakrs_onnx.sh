#!/usr/bin/env bash
# Runner: speakrs (avencera/speakrs) — pyannote seg-3.0 + WeSpeaker ResNet34
# with native Rust AHC + PLDA + VBx clustering, via our fork in .tools/speakrs
# (fork adds the AHC count-cut oracle mode and the bench_rttm example CLI).
# Usage: runners/speakrs_onnx.sh <corpus> <auto|oracle> [threshold] [jobs]
# Candidate id = speakrs-th<thr> | speakrs-oracle.
# CPU only: single-file RTF is ~0.9, so files run in parallel (default 8 jobs).
. "$(dirname "$0")/../env.sh"

corpus="$1"; mode="$2"; thr="${3:-0.6}"; jobs="${4:-8}"
TC="$BENCH/.tools/speakrs"
BIN="$TC/target/release/examples/bench_rttm"
[ -x "$BIN" ] || die "bench_rttm not built — cargo build --release --no-default-features --features openblas-system --example bench_rttm in $TC"
[ -d "$AUDIO/$corpus" ] || die "audio missing for $corpus (run fetch-corpora.sh)"

if [ "$mode" = oracle ]; then cand="speakrs-oracle"; else cand="speakrs-th$thr"; fi
out="$HYP/$cand/$corpus/$mode"; mkdir -p "$out"
errlog="$LOGS/$cand.$corpus.$mode.err"; : > "$errlog"

export SPEAKRS_MODELS_DIR="$MODELS/speakrs"
# openblas eigendecomposition needs more stack than the 2 MB thread default
export RUST_MIN_STACK=33554432

running=0
for wav in "$AUDIO/$corpus"/*.wav; do
  [ -e "$wav" ] || continue
  id="$(basename "$wav" .wav)"
  if [ "$mode" = oracle ]; then
    n="$(count_speakers "$REF/$corpus/$id.rttm" "$id")"; [ "$n" -ge 1 ] || n=1
    set -- oracle "$n" "$thr"
  else
    set -- auto "$thr"
  fi
  ( "$BIN" "$wav" "$id" "$@" > "$out/$id.rttm" 2>>"$errlog" \
      || log "FAIL $cand $id" ) &
  running=$((running + 1))
  if [ "$running" -ge "$jobs" ]; then
    wait -n || true
    running=$((running - 1))
  fi
done
wait

cat "$out"/*.rttm > "$out/_all.rttm" 2>/dev/null || true
log "done $cand / $corpus / $mode"
