#!/usr/bin/env bash
# Acquire diarization corpora -> audio/16k/<corpus>/*.wav + ref_rttm/<corpus>/*.rttm + uem/<corpus>.uem
# Big downloads: requires --yes to actually pull. --dry-run prints the shopping list.
# Usage: ./fetch-corpora.sh [--dry-run|--yes] [corpus ...]   (default: all)
. "$(dirname "$0")/env.sh"

MODE=dry
case "${1:-}" in --dry-run) MODE=dry; shift;; --yes) MODE=go; shift;; esac
SEL=("$@"); [ ${#SEL[@]} -eq 0 ] && SEL=("${CORPORA[@]}")

# approx download sizes (GB) for the shopping list
declare -A SIZE=( [voxconverse]=5 [aishell4]=5.2 [msdwild]=7.6 [icsi]=8.2 )

run(){ if [ "$MODE" = go ]; then "$@"; else printf '  WOULD: %s\n' "$*"; fi; }

prep_corpus_dirs(){ mkdir -p "$AUDIO/$1" "$REF/$1"; }
finalize_uem(){ gen_uem "$AUDIO/$1" > "$UEM/$1.uem"; log "uem  $1 ($(grep -c . "$UEM/$1.uem" 2>/dev/null || echo 0) files)"; }

corpus_voxconverse(){
  prep_corpus_dirs voxconverse
  local tmp="$BENCH/.dl/voxconverse"; mkdir -p "$tmp"
  run wget -c -O "$tmp/test_wav.zip" "https://www.robots.ox.ac.uk/~vgg/data/voxconverse/data/voxconverse_test_wav.zip"
  run bash -c "unzip -n '$tmp/test_wav.zip' -d '$tmp/wav'"
  run bash -c "[ -d '$tmp/voxconverse' ] || git clone --depth 1 https://github.com/joonson/voxconverse '$tmp/voxconverse'"
  if [ "$MODE" = go ]; then
    for r in "$tmp/voxconverse/test/"*.rttm; do
      id="$(basename "$r" .rttm)"; src="$(find "$tmp/wav" -name "$id.wav" | head -1)"
      [ -n "$src" ] || continue
      to16k "$src" "$AUDIO/voxconverse/$id.wav"; cp "$r" "$REF/voxconverse/$id.rttm"
    done
    finalize_uem voxconverse
  fi
}

corpus_msdwild(){
  prep_corpus_dirs msdwild
  local tmp="$BENCH/.dl/msdwild"; mkdir -p "$tmp"
  have gdown || { log "msdwild: 'gdown' required (pip install gdown)"; [ "$MODE" = go ] && die "gdown missing"; }
  run bash -c "[ -d '$tmp/MSDWILD' ] || git clone --depth 1 https://github.com/X-LANCE/MSDWILD '$tmp/MSDWILD'"
  run gdown 1I5qfuPPGBM9keJKz0VN-OYEeRMJ7dgpl -O "$tmp/wav.zip"
  run bash -c "unzip -n '$tmp/wav.zip' -d '$tmp/wav'"
  if [ "$MODE" = go ]; then
    # 'many' set = >4 speakers. Split concatenated many.val.rttm into per-file refs.
    local many="$tmp/MSDWILD/rttms/many.val.rttm"
    [ -s "$many" ] || die "msdwild many.val.rttm not found"
    awk '{print > ("'"$REF"'/msdwild/" $2 ".rttm")}' "$many"
    for r in "$REF/msdwild/"*.rttm; do
      id="$(basename "$r" .rttm)"; src="$(find "$tmp/wav" -name "$id.wav" | head -1)"
      [ -n "$src" ] && to16k "$src" "$AUDIO/msdwild/$id.wav" || log "msdwild: missing wav $id"
    done
    finalize_uem msdwild
  fi
}

corpus_hf(){ # $1 corpus  $2 dataset
  prep_corpus_dirs "$1"
  run bash -c "uv run --with datasets --with soundfile python '$BENCH/prep/hf2rttm.py' \
       --dataset '$2' --split test --wavdir '$AUDIO/$1' --refdir '$REF/$1'"
  [ "$MODE" = go ] && finalize_uem "$1"
}
corpus_aishell4(){ corpus_hf aishell4 argmaxinc/aishell-4; }
corpus_icsi(){ corpus_hf icsi argmaxinc/icsi-meetings; }

total=0
for c in "${SEL[@]}"; do total=$(awk -v a="$total" -v b="${SIZE[$c]:-0}" 'BEGIN{printf "%.1f", a+b}'); done
log "selected: ${SEL[*]}  (~${total} GB download)"
[ "$MODE" = dry ] && log "DRY-RUN — re-run with --yes to download"

for c in "${SEL[@]}"; do
  log "=== corpus: $c ==="
  case "$c" in
    voxconverse) corpus_voxconverse;;
    msdwild)     corpus_msdwild;;
    aishell4)    corpus_aishell4;;
    icsi)        corpus_icsi;;
    *) log "unknown corpus: $c";;
  esac
done
log "done."
