#!/usr/bin/env bash
# Orchestrator: run candidates over corpora, both modes. Idempotent (skips a combo
# whose hyp/_all.rttm already exists). Each candidate failure is logged, never fatal.
#
# Usage: ./run.sh [corpus ...]            (default: all fetched corpora)
# Tunables (env):
#   CANDIDATES="sortformer sherpa pyannote"   which families (diarizen excluded by default)
#   EMBEDDINGS="eres2net campplus wespeaker"  sherpa embeddings (keys below)
#   SHERPA_THRESHOLDS="0.6 0.7"               auto-mode thresholds
#   PROVIDER=cpu|cuda  THREADS=N
#   PYANNOTE_MODEL=pyannote/speaker-diarization-community-1   (needs HF_TOKEN)
. "$(dirname "$0")/env.sh"

SEL=("$@"); [ ${#SEL[@]} -eq 0 ] && SEL=("${CORPORA[@]}")
CANDIDATES="${CANDIDATES:-sortformer sherpa pyannote}"
SHERPA_THRESHOLDS="${SHERPA_THRESHOLDS:-0.6 0.7}"

# embedding key -> filename
declare -A EMB=(
  [eres2net]=3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx
  [campplus]=3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx
  [campplus_multi]=3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx
  [wespeaker]=wespeaker_en_voxceleb_resnet34_LM.onnx
  [wespeaker293]=wespeaker_en_voxceleb_resnet293_LM.onnx
  [wespeaker_campp]=wespeaker_en_voxceleb_CAM++_LM.onnx
  [titanet]=nemo_en_titanet_large.onnx
)
EMBEDDINGS="${EMBEDDINGS:-eres2net campplus wespeaker titanet}"

done_already(){ [ -s "$HYP/$1/$2/$3/_all.rttm" ]; }

for corpus in "${SEL[@]}"; do
  [ -d "$AUDIO/$corpus" ] || { log "skip $corpus (not fetched)"; continue; }
  log "########## corpus: $corpus ##########"

  for fam in $CANDIDATES; do
    case "$fam" in
      sortformer)
        done_already sortformer "$corpus" auto || "$BENCH/runners/sortformer.sh" "$corpus" ;;
      sherpa)
        for k in $EMBEDDINGS; do
          f="${EMB[$k]:-}"; [ -n "$f" ] || { log "unknown emb key $k"; continue; }
          for thr in $SHERPA_THRESHOLDS; do
            cand="sherpa-$(basename "$f" .onnx)-th$thr"
            done_already "$cand" "$corpus" auto || "$BENCH/runners/sherpa.sh" "$corpus" auto "$f" "$thr"
          done
          cand="sherpa-$(basename "$f" .onnx)-oracle"
          done_already "$cand" "$corpus" oracle || "$BENCH/runners/sherpa.sh" "$corpus" oracle "$f"
        done ;;
      pyannote)
        if [ -z "${HF_TOKEN:-}${HUGGINGFACE_TOKEN:-}" ] && [ ! -s "$HOME/.cache/huggingface/token" ]; then
          log "skip pyannote (no HF auth: run 'huggingface-cli login' + accept model conditions)"; continue
        fi
        model="${PYANNOTE_MODEL:-pyannote/speaker-diarization-community-1}"
        cand="pyannote-$(basename "$model")"
        for m in auto oracle; do
          done_already "$cand" "$corpus" "$m" && continue
          o="$HYP/$cand/$corpus/$m"; mkdir -p "$o"
          uv run --with pyannote.audio --with torch python "$BENCH/runners/pyannote_run.py" \
            --model "$model" --audio "$AUDIO/$corpus" --ref "$REF/$corpus" --out "$o" \
            --mode "$m" --device "${PROVIDER:-cpu}" 2>>"$LOGS/$cand.$corpus.$m.err" || log "FAIL pyannote $corpus $m"
          cat "$o"/*.rttm > "$o/_all.rttm" 2>/dev/null || true
        done ;;
      diarizen)
        cand="diarizen"; m=auto
        done_already "$cand" "$corpus" "$m" && continue
        o="$HYP/$cand/$corpus/$m"; mkdir -p "$o"
        log "diarizen needs its own conda env (see README); attempting current env"
        python "$BENCH/runners/diarizen_run.py" --audio "$AUDIO/$corpus" --out "$o" \
          2>>"$LOGS/$cand.$corpus.err" || log "FAIL diarizen $corpus (env?)"
        cat "$o"/*.rttm > "$o/_all.rttm" 2>/dev/null || true ;;
      *) log "unknown candidate family: $fam" ;;
    esac
  done
done
log "run complete. Next: ./score.sh && python report.py"
