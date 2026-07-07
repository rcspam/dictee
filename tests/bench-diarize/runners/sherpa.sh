#!/usr/bin/env bash
# Runner: sherpa-onnx (diarize-only-sherpa) for one corpus/mode/embedding.
# Usage: runners/sherpa.sh <corpus> <auto|oracle> <emb-file.onnx> [threshold]
# The production binary loads fixed model names from --models-dir, so we build a
# per-embedding models dir with symlinks (segmentation + chosen emb under the name
# the binary expects). Candidate id = sherpa-<emb-stem>[-th<thr>|-oracle].
. "$(dirname "$0")/../env.sh"

corpus="$1"; mode="$2"; emb="$3"; thr="${4:-0.6}"
embkey="$(basename "$emb" .onnx)"
[ -f "$MODELS/emb/$emb" ] || die "embedding not found: $MODELS/emb/$emb (run fetch-models.sh)"
[ -d "$AUDIO/$corpus" ]   || die "audio missing for $corpus (run fetch-corpora.sh)"

if [ "$mode" = oracle ]; then cand="sherpa-$embkey-oracle"; else cand="sherpa-$embkey-th$thr"; fi

# per-embedding models dir (binary expects segmentation.onnx + the eres2net filename)
md="$BENCH/.mdir/$embkey"; mkdir -p "$md"
ln -sf "$MODELS/segmentation.onnx" "$md/segmentation.onnx"
ln -sf "$MODELS/emb/$emb" "$md/3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx"

out="$HYP/$cand/$corpus/$mode"; mkdir -p "$out"
errlog="$LOGS/$cand.$corpus.$mode.err"; : > "$errlog"

for wav in "$AUDIO/$corpus"/*.wav; do
  [ -e "$wav" ] || continue
  id="$(basename "$wav" .wav)"
  args=(--models-dir "$md" --provider "${PROVIDER:-cpu}" --threads "${THREADS:-$(nproc)}")
  if [ "$mode" = oracle ]; then
    n="$(count_speakers "$REF/$corpus/$id.rttm" "$id")"; [ "$n" -ge 1 ] || n=1
    args+=(--num-clusters "$n")
  else
    args+=(--threshold "$thr")
  fi
  if "$DIARIZE_ONLY_SHERPA" "${args[@]}" "$wav" 2>>"$errlog" | lines_to_rttm "$id" > "$out/$id.rttm"; then :; else
    log "FAIL $cand $id"; fi
done
cat "$out"/*.rttm > "$out/_all.rttm" 2>/dev/null || true
log "done $cand / $corpus / $mode"
