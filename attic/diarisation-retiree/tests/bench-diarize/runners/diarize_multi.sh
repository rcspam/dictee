#!/usr/bin/env bash
# Runner: dictee's in-house diarize-multi binary (src/diar/ engine, port of
# the speakrs AHC+PLDA+VBx pipeline). GPU-capable via the dictee ort stack.
# Usage: runners/diarize_multi.sh <corpus> <auto|oracle> [threshold]
# Candidate id = diarize-multi-th<thr> | diarize-multi-oracle.
. "$(dirname "$0")/../env.sh"

corpus="$1"; mode="$2"; thr="${3:-0.6}"
BIN="${DIARIZE_MULTI:-/home/rapha/SOURCES/RAPHA_STT/dictee/target/release/diarize-multi}"
[ -x "$BIN" ] || die "diarize-multi not built — cargo build --release --features diar in the dictee repo"
[ -d "$AUDIO/$corpus" ] || die "audio missing for $corpus (run fetch-corpora.sh)"

if [ "$mode" = oracle ]; then cand="diarize-multi-oracle"; else cand="diarize-multi-th$thr"; fi
out="$HYP/$cand/$corpus/$mode"; mkdir -p "$out"
errlog="$LOGS/$cand.$corpus.$mode.err"; : > "$errlog"

export ORT_DYLIB_PATH="${ORT_DYLIB_PATH:-/usr/lib/dictee/libonnxruntime.so}"
MODELS_DIR="${DIAR_MODELS_DIR:-$HOME/.local/share/dictee/diar}"

for wav in "$AUDIO/$corpus"/*.wav; do
  [ -e "$wav" ] || continue
  id="$(basename "$wav" .wav)"
  if [ "$mode" = oracle ]; then
    n="$(count_speakers "$REF/$corpus/$id.rttm" "$id")"; [ "$n" -ge 1 ] || n=1
    "$BIN" --models-dir "$MODELS_DIR" --threshold "$thr" --num-speakers "$n" --rttm "$id" "$wav" \
      > "$out/$id.rttm" 2>>"$errlog" || log "FAIL $cand $id"
  else
    "$BIN" --models-dir "$MODELS_DIR" --threshold "$thr" --rttm "$id" "$wav" \
      > "$out/$id.rttm" 2>>"$errlog" || log "FAIL $cand $id"
  fi
done
cat "$out"/*.rttm > "$out/_all.rttm" 2>/dev/null || true
log "done $cand / $corpus / $mode"
