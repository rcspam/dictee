#!/usr/bin/env bash
# Download sherpa-onnx diarization models: 1 segmentation + N speaker embeddings.
# Idempotent: skips a file already present with the expected byte size.
# Usage: ./fetch-models.sh [--dry-run]
. "$(dirname "$0")/env.sh"

DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

SEG_BASE="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models"
EMB_BASE="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models"

# segmentation archive (tar.bz2) -> models/segmentation.onnx
SEG_ARCHIVE="sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
SEG_SIZE=6958444

# name<TAB>expected_size  (verified from GitHub release API 2026-06-28)
EMB_LIST="
3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx	26485263
3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx	29596978
3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx	28281164
wespeaker_en_voxceleb_resnet34_LM.onnx	26530550
wespeaker_en_voxceleb_resnet293_LM.onnx	114336527
wespeaker_en_voxceleb_CAM++_LM.onnx	29292687
nemo_en_titanet_large.onnx	101405493
"

fsize(){ stat -c%s "$1" 2>/dev/null || echo 0; }

dl(){ # url dst expected_size
  local url="$1" dst="$2" exp="$3"
  if [ "$(fsize "$dst")" = "$exp" ]; then log "ok   $(basename "$dst")"; return 0; fi
  if [ "$DRY" = 1 ]; then printf '  WOULD GET %s (%s bytes)\n' "$(basename "$dst")" "$exp"; return 0; fi
  log "get  $(basename "$dst")"
  if have aria2c; then aria2c -x8 -s8 -c -o "$(basename "$dst")" -d "$(dirname "$dst")" "$url"
  else wget -c -O "$dst" "$url"; fi
  local got; got="$(fsize "$dst")"
  [ "$got" = "$exp" ] || die "size mismatch $dst: got $got expected $exp"
}

# --- segmentation ---
if [ "$(fsize "$MODELS/segmentation.onnx")" -gt 1000000 ]; then
  log "ok   segmentation.onnx"
else
  dl "$SEG_BASE/$SEG_ARCHIVE" "$MODELS/$SEG_ARCHIVE" "$SEG_SIZE"
  if [ "$DRY" = 0 ]; then
    tar -xjf "$MODELS/$SEG_ARCHIVE" -C "$MODELS"
    # archive extracts a dir containing model.onnx -> normalize to segmentation.onnx
    found="$(find "$MODELS" -name 'model.onnx' -path '*segmentation*' | head -1)"
    [ -n "$found" ] || found="$(find "$MODELS/sherpa-onnx-pyannote-segmentation-3-0" -name 'model.onnx' | head -1)"
    [ -n "$found" ] || die "segmentation model.onnx not found after extract"
    cp "$found" "$MODELS/segmentation.onnx"
    log "ok   segmentation.onnx (extracted)"
  fi
fi

# --- embeddings ---
printf '%s\n' "$EMB_LIST" | while IFS=$'\t' read -r name size; do
  [ -n "$name" ] || continue
  dl "$EMB_BASE/$name" "$MODELS/emb/$name" "$size"
done

log "models dir: $MODELS"
[ "$DRY" = 1 ] && log "(dry-run, nothing downloaded)"
