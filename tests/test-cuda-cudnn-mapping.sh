#!/usr/bin/env bash
# Teste les fonctions pures de setup-cuda-venv.sh (sans GPU réel).
set -u
SCRIPT="$(dirname "$0")/../setup-cuda-venv.sh"
# shellcheck disable=SC1090
DICTEE_CUDA_LIB_SOURCED=1 source "$SCRIPT"   # source sans lancer main

fail=0
check() { # check <desc> <attendu> <obtenu>
  if [ "$2" = "$3" ]; then echo "ok   - $1"; else echo "FAIL - $1 : attendu '$2', obtenu '$3'"; fail=1; fi
}

# --- mapping cc_int -> spec cuDNN ---
check "Pascal 6.1 -> pin 9.0.0.312" "nvidia-cudnn-cu12==9.0.0.312" "$(dictee_cudnn_spec 61)"
check "Maxwell 5.0 -> pin 9.0.0.312" "nvidia-cudnn-cu12==9.0.0.312" "$(dictee_cudnn_spec 50)"
check "Volta 7.0 -> pin 9.0.0.312"   "nvidia-cudnn-cu12==9.0.0.312" "$(dictee_cudnn_spec 70)"
check "Turing 7.5 -> latest"         "nvidia-cudnn-cu12"            "$(dictee_cudnn_spec 75)"
check "Ada 8.9 -> latest"            "nvidia-cudnn-cu12"            "$(dictee_cudnn_spec 89)"
check "Blackwell 12.0 -> latest"     "nvidia-cudnn-cu12"            "$(dictee_cudnn_spec 120)"
check "cc vide (détection KO) -> latest" "nvidia-cudnn-cu12"        "$(dictee_cudnn_spec '')"

# --- parsing compute_cap via nvidia-smi mocké ---
mock_nvsmi() { # crée un faux nvidia-smi dans un PATH temporaire ; $1 = sortie
  MOCKDIR="$(mktemp -d)"; printf '#!/bin/sh\nprintf "%%s\\n" "%s"\n' "$1" > "$MOCKDIR/nvidia-smi"
  chmod +x "$MOCKDIR/nvidia-smi"; PATH="$MOCKDIR:$PATH"
}
( mock_nvsmi "6.1";        check "1 GPU 6.1 -> 61"        "61" "$(dictee_detect_cc_int)" )
( mock_nvsmi $'8.9\n6.1';  check "multi-GPU -> min (61)"  "61" "$(dictee_detect_cc_int)" )
( mock_nvsmi "12.0";       check "Blackwell -> 120"       "120" "$(dictee_detect_cc_int)" )
( mock_nvsmi "";           check "sortie vide -> rien"    ""  "$(dictee_detect_cc_int)" )
( mock_nvsmi "N/A";        check "N/A -> rien"            ""  "$(dictee_detect_cc_int)" )

exit $fail
