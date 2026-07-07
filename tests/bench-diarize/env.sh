#!/usr/bin/env bash
# Shared paths + helpers for the diarization benchmark harness.
# Source this from every script: . "$(dirname "$0")/env.sh"
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export BENCH="$HERE"
export MODELS="$BENCH/models"          # segmentation.onnx + emb/<name>.onnx
export AUDIO="$BENCH/audio/16k"        # <corpus>/<file-id>.wav (16k mono)
export REF="$BENCH/ref_rttm"           # <corpus>/<file-id>.rttm  (ground truth)
export UEM="$BENCH/uem"                # <corpus>.uem
export HYP="$BENCH/hyp"                # <candidate>/<corpus>/<mode>/<file-id>.rttm
export RESULTS="$BENCH/results"        # DER tables
export LOGS="$BENCH/logs"
mkdir -p "$MODELS/emb" "$AUDIO" "$REF" "$UEM" "$HYP" "$RESULTS" "$LOGS"

# Candidate binaries from the dictee repo (built separately). Override via env.
export DIARIZE_ONLY="${DIARIZE_ONLY:-diarize-only}"                       # Sortformer
export DIARIZE_ONLY_SHERPA="${DIARIZE_ONLY_SHERPA:-diarize-only-sherpa}"  # sherpa-onnx

export CORPORA=(voxconverse aishell4 msdwild icsi)

log(){ printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die(){ printf 'bench-diarize: %s\n' "$*" >&2; exit 1; }

# Number of distinct speakers for one file-id inside a (possibly concatenated) RTTM.
count_speakers(){ # $1 rttm, $2 file-id
  awk -v id="$2" '$1=="SPEAKER" && $2==id {print $8}' "$1" | sort -u | grep -c .
}

# Convert "start end label" lines (stdin) -> RTTM (stdout) for one file-id.
# Accepts 2- or 3-decimal start/end; skips comments/blank lines.
lines_to_rttm(){ # $1 file-id
  awk -v id="$1" 'NF>=3 && $1 !~ /^#/ {
    s=$1+0; e=$2+0; if (e>s) printf "SPEAKER %s 1 %.3f %.3f <NA> <NA> %s <NA> <NA>\n", id, s, e-s, $3 }'
}

# UEM covering the whole duration of every wav in a dir (stdout).
gen_uem(){ # $1 wavdir
  local w id dur
  for w in "$1"/*.wav; do
    [ -e "$w" ] || continue
    id="$(basename "$w" .wav)"
    dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$w" 2>/dev/null)"
    [ -n "$dur" ] && printf '%s 1 0.00 %s\n' "$id" "$dur"
  done
}

# Normalize any audio to 16 kHz mono single-channel WAV (idempotent on output path).
to16k(){ # $1 src, $2 dst
  [ -s "$2" ] && return 0
  ffmpeg -nostdin -v error -y -i "$1" -ac 1 -ar 16000 -f wav "$2"
}

have(){ command -v "$1" >/dev/null 2>&1; }
