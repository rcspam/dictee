#!/usr/bin/env bash
# Runner: NeMo Sortformer (diarize-only). Auto mode only (hard cap 4, no count forcing).
# Usage: runners/sortformer.sh <corpus>
. "$(dirname "$0")/../env.sh"

corpus="$1"; mode=auto; cand=sortformer
[ -d "$AUDIO/$corpus" ] || die "audio missing for $corpus"
out="$HYP/$cand/$corpus/$mode"; mkdir -p "$out"
errlog="$LOGS/$cand.$corpus.err"; : > "$errlog"

for wav in "$AUDIO/$corpus"/*.wav; do
  [ -e "$wav" ] || continue
  id="$(basename "$wav" .wav)"
  if "$DIARIZE_ONLY" "$wav" 2>>"$errlog" | lines_to_rttm "$id" > "$out/$id.rttm"; then :; else
    log "FAIL $cand $id"; fi
done
cat "$out"/*.rttm > "$out/_all.rttm" 2>/dev/null || true
log "done $cand / $corpus"
