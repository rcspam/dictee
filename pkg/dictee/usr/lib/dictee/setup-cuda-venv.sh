#!/usr/bin/env bash
# dictee-cuda : met en place /opt/dictee/cuda-venv avec la BONNE cuDNN selon le GPU,
# puis symlinke les libs dans /usr/lib/dictee/ (ldconfig les trouve via ld.so.conf.d/dictee.conf).
# Sélection cuDNN : compute_cap < 7.5 (Pascal/Volta/Maxwell) -> 9.0.0.312 (dernière supportant Pascal) ;
#                   >= 7.5 (Turing -> Blackwell) -> latest.
# Voir docs/superpowers/specs/2026-05-24-cuda-cudnn-arch-detection-design.md

CUDA_VENV="/opt/dictee/cuda-venv"
DICTEE_LIB_DIR="/usr/lib/dictee"
CUDNN_LEGACY_PIN="nvidia-cudnn-cu12==9.0.0.312"   # dernière cuDNN supportant Pascal (cc 6.x), prouvée GTX 1060
CUDNN_LATEST="nvidia-cudnn-cu12"
OTHER_CUDA_LIBS="nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cufft-cu12 nvidia-curand-cu12 nvidia-cuda-nvrtc-cu12"

# Détecte le compute_cap minimum (entier X*10+Y) des GPU NVIDIA. Echo l'entier, ou rien si indétectable.
dictee_detect_cc_int() {
    command -v nvidia-smi >/dev/null 2>&1 || return 0
    local out cc major minor v min=""
    out="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null)" || return 0
    while IFS= read -r cc; do
        cc="${cc//[[:space:]]/}"
        case "$cc" in
            [0-9]*.[0-9]*) ;;          # garde uniquement "X.Y"
            *) continue ;;
        esac
        major="${cc%%.*}"; minor="${cc##*.}"
        v=$(( major * 10 + minor ))
        if [ -z "$min" ] || [ "$v" -lt "$min" ]; then min="$v"; fi
    done <<EOF
$out
EOF
    [ -n "$min" ] && printf '%s\n' "$min"
}

# Echo la spec pip pour nvidia-cudnn-cu12 selon le cc entier. cc vide => latest (détection KO).
dictee_cudnn_spec() {
    local cc="${1:-}"
    if [ -n "$cc" ] && [ "$cc" -lt 75 ] 2>/dev/null; then
        printf '%s\n' "$CUDNN_LEGACY_PIN"
    else
        printf '%s\n' "$CUDNN_LATEST"
    fi
}

dictee_setup_cuda_venv_main() {
    # Rempli en Task 2.
    :
}

# Ne lance main que si exécuté directement (pas si sourcé par les tests).
if [ -z "${DICTEE_CUDA_LIB_SOURCED:-}" ]; then
    dictee_setup_cuda_venv_main "$@"
fi
