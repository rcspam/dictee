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
    # Guard : variante CUDA uniquement (provider .so présent)
    [ -f "$DICTEE_LIB_DIR/libonnxruntime_providers_cuda.so" ] || return 0

    # Pas de GPU NVIDIA → skip le téléchargement (~1,5 Go) ; le runtime bascule CPU.
    if [ ! -d /proc/driver/nvidia ] && [ ! -e /dev/nvidia0 ]; then
        echo "→ Pas de GPU NVIDIA détecté — skip téléchargement des libs CUDA (≈ 1,5 Go)."
        echo "  Le runtime bascule automatiquement en CPU."
        echo "  Après installation d'un driver NVIDIA, relancer : sudo bash $DICTEE_LIB_DIR/setup-cuda-venv.sh"
        return 0
    fi

    command -v python3 >/dev/null 2>&1 || { echo "⚠ python3 absent"; return 1; }

    mkdir -p /opt/dictee
    if [ ! -x "$CUDA_VENV/bin/pip" ]; then
        python3 -m venv "$CUDA_VENV" || { echo "⚠ python3 -m venv a échoué — python3-venv installé ?"; return 1; }
        "$CUDA_VENV/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
    fi

    local cc_int cudnn_spec
    cc_int="$(dictee_detect_cc_int)"
    cudnn_spec="$(dictee_cudnn_spec "$cc_int")"
    echo "→ GPU compute_cap détecté : ${cc_int:-inconnu} → cuDNN : $cudnn_spec"
    if [ -z "$cc_int" ]; then
        echo "  (détection GPU impossible — cuDNN latest par défaut ; le fallback CPU du daemon couvre les vieux GPU)"
    fi

    echo "→ Téléchargement des libs NVIDIA CUDA (≈ 1,5 Go, peut prendre plusieurs minutes)..."
    # shellcheck disable=SC2086
    if ! "$CUDA_VENV/bin/pip" install --quiet --upgrade $OTHER_CUDA_LIBS "$cudnn_spec"; then
        echo "⚠ pip install des libs NVIDIA a échoué (pas d'internet ? disque plein ?)"
        echo "  Relancer : sudo $CUDA_VENV/bin/pip install $OTHER_CUDA_LIBS $cudnn_spec && sudo ldconfig"
        return 2
    fi

    # Nettoyer les symlinks périmés de $DICTEE_LIB_DIR pointant vers le venv (cas downgrade de version)
    local _l _t
    for _l in "$DICTEE_LIB_DIR"/lib*.so*; do
        [ -L "$_l" ] || continue
        _t="$(readlink "$_l")"
        case "$_t" in "$CUDA_VENV"/*) [ -e "$_l" ] || rm -f "$_l" ;; esac
    done

    # (Re)symlink toutes les lib*.so* du venv → /usr/lib/dictee/
    local _py _root _sub _so _count=0
    _py="$(ls "$CUDA_VENV/lib/" 2>/dev/null | grep -E '^python' | head -1)"
    if [ -n "$_py" ]; then
        _root="$CUDA_VENV/lib/$_py/site-packages/nvidia"
        for _sub in "$_root"/*/lib; do
            [ -d "$_sub" ] || continue
            for _so in "$_sub"/lib*.so*; do
                [ -f "$_so" ] || continue
                ln -sf "$_so" "$DICTEE_LIB_DIR/$(basename "$_so")"
                _count=$((_count + 1))
            done
        done
        echo "✓ $_count libs NVIDIA liées dans $DICTEE_LIB_DIR/"
    fi
    ldconfig 2>/dev/null || true
    return 0
}

# Ne lance main que si exécuté directement (pas si sourcé par les tests).
if [ -z "${DICTEE_CUDA_LIB_SOURCED:-}" ]; then
    dictee_setup_cuda_venv_main "$@"
fi
