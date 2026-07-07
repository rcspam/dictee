#!/usr/bin/env bash
# Score every hyp/<cand>/<corpus>/<mode>/_all.rttm with dscore, in 2 conventions:
#   dihard  : --collar 0.0                 (overlaps included)  [default, modern/severe]
#   ami     : --collar 0.25 --ignore_overlaps                  [historical comparability]
# Raw dscore outputs -> results/raw/<cand>__<corpus>__<mode>__<conv>.txt
# Then: python report.py  (parses OVERALL DER/JER into the matrix)
. "$(dirname "$0")/env.sh"

DSCORE="${DSCORE:-$BENCH/.tools/dscore/score.py}"
if [ ! -f "$DSCORE" ]; then
  log "dscore missing -> cloning into $BENCH/.tools/dscore"
  mkdir -p "$BENCH/.tools"
  git clone --depth 1 https://github.com/nryant/dscore "$BENCH/.tools/dscore" || die "clone dscore failed"
fi
# dscore deps (numpy/scipy/intervaltree/tabulate) provided on the fly via uv
DSCORE_RUN=(uv run --with numpy --with scipy --with intervaltree --with tabulate python)
RAW="$RESULTS/raw"; mkdir -p "$RAW" "$BENCH/.refall"

score_one(){ # conv extra cand corpus mode refall hyp uem
  local conv="$1" extra="$2" cand="$3" corpus="$4" mode="$5" refall="$6" hyp="$7" uem="$8"
  local o="$RAW/${cand}__${corpus}__${mode}__${conv}.txt"
  local uarg=(); [ -n "$uem" ] && [ -f "$uem" ] && uarg=(-u "$uem")
  # shellcheck disable=SC2086
  "${DSCORE_RUN[@]}" "$DSCORE" $extra "${uarg[@]}" -r "$refall" -s "$hyp" > "$o" 2>>"$LOGS/dscore.err" \
    && log "scored $cand/$corpus/$mode [$conv]" || log "FAIL dscore $cand/$corpus/$mode [$conv]"
}

# corpora = any ref_rttm/<corpus>/ that exists (auto-discovery, incl. validation subsets)
mapfile -t ALL_CORPORA < <(for d in "$REF"/*/; do [ -d "$d" ] && basename "$d"; done)

for cand_dir in "$HYP"/*/; do
  cand="$(basename "$cand_dir")"
  for corpus in "${ALL_CORPORA[@]}"; do
    [ -d "$cand_dir$corpus" ] || continue
    refall="$BENCH/.refall/$corpus.rttm"
    cat "$REF/$corpus"/*.rttm > "$refall" 2>/dev/null || continue
    [ -s "$refall" ] || continue
    uem="$UEM/$corpus.uem"
    for mode_dir in "$cand_dir$corpus"/*/; do
      [ -d "$mode_dir" ] || continue
      mode="$(basename "$mode_dir")"
      hyp="${mode_dir}_all.rttm"
      [ -s "$hyp" ] || cat "$mode_dir"*.rttm > "$hyp" 2>/dev/null
      [ -s "$hyp" ] || continue
      score_one dihard "--collar 0.0"                   "$cand" "$corpus" "$mode" "$refall" "$hyp" "$uem"
      score_one ami    "--collar 0.25 --ignore_overlaps" "$cand" "$corpus" "$mode" "$refall" "$hyp" "$uem"
    done
  done
done
log "scoring done. Now: python report.py"
