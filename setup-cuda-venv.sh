#!/usr/bin/env bash
# dictee-cuda: set up /opt/dictee/cuda-venv with the RIGHT cuDNN for the GPU,
# then symlink the libs into /usr/lib/dictee/ (ldconfig finds them via ld.so.conf.d/dictee.conf).
# cuDNN selection: compute_cap < 7.5 (Pascal/Volta/Maxwell) -> 9.0.0.312 (last one supporting Pascal);
#                  >= 7.5 (Turing -> Blackwell) -> latest.
# See docs/superpowers/specs/2026-05-24-cuda-cudnn-arch-detection-design.md

CUDA_VENV="/opt/dictee/cuda-venv"
DICTEE_LIB_DIR="/usr/lib/dictee"
CUDNN_LEGACY_PIN="nvidia-cudnn-cu12==9.0.0.312"   # last cuDNN supporting Pascal (cc 6.x), proven on GTX 1060
CUDNN_LATEST="nvidia-cudnn-cu12"
OTHER_CUDA_LIBS="nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cufft-cu12 nvidia-curand-cu12 nvidia-cuda-nvrtc-cu12"

# Detect the minimum compute_cap (integer X*10+Y) across NVIDIA GPUs. Echoes the integer, or nothing if undetectable.
dictee_detect_cc_int() {
    command -v nvidia-smi >/dev/null 2>&1 || return 0
    local out cc major minor v min=""
    out="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null)" || return 0
    while IFS= read -r cc; do
        cc="${cc//[[:space:]]/}"
        case "$cc" in
            [0-9]*.[0-9]*) ;;          # keep only "X.Y"
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

# Echo the pip spec for nvidia-cudnn-cu12 based on the cc integer. Empty cc => latest (detection failed).
dictee_cudnn_spec() {
    local cc="${1:-}"
    if [ -n "$cc" ] && [ "$cc" -lt 75 ] 2>/dev/null; then
        printf '%s\n' "$CUDNN_LEGACY_PIN"
    else
        printf '%s\n' "$CUDNN_LATEST"
    fi
}

dictee_setup_cuda_venv_main() {
    # Guard: CUDA variant only (provider .so present)
    [ -f "$DICTEE_LIB_DIR/libonnxruntime_providers_cuda.so" ] || return 0

    # No NVIDIA GPU → skip the download (~1.5 GB); the runtime falls back to CPU.
    if [ ! -d /proc/driver/nvidia ] && [ ! -e /dev/nvidia0 ]; then
        echo "→ No NVIDIA GPU detected — skipping the CUDA libs download (~1.5 GB)."
        echo "  The runtime falls back to CPU automatically."
        echo "  After installing an NVIDIA driver, re-run: sudo bash $DICTEE_LIB_DIR/setup-cuda-venv.sh"
        return 0
    fi

    command -v python3 >/dev/null 2>&1 || { echo "⚠ python3 not found"; return 1; }

    mkdir -p /opt/dictee
    if [ ! -x "$CUDA_VENV/bin/pip" ]; then
        python3 -m venv "$CUDA_VENV" || { echo "⚠ python3 -m venv failed — is python3-venv installed?"; return 1; }
        "$CUDA_VENV/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
    fi

    local cc_int cudnn_spec
    cc_int="$(dictee_detect_cc_int)"
    cudnn_spec="$(dictee_cudnn_spec "$cc_int")"
    echo "→ Detected GPU compute_cap: ${cc_int:-unknown} → cuDNN: $cudnn_spec"
    if [ -z "$cc_int" ]; then
        echo "  (GPU detection failed — defaulting to cuDNN latest; the daemon's CPU fallback covers old GPUs)"
    fi

    echo "→ Downloading the NVIDIA CUDA libs (~1.5 GB, may take several minutes)..."
    # shellcheck disable=SC2086
    if ! "$CUDA_VENV/bin/pip" install --quiet --upgrade $OTHER_CUDA_LIBS "$cudnn_spec"; then
        echo "⚠ pip install of the NVIDIA libs failed (no internet? disk full?)"
        echo "  Re-run: sudo $CUDA_VENV/bin/pip install $OTHER_CUDA_LIBS $cudnn_spec && sudo ldconfig"
        return 2
    fi

    # Clean up stale symlinks in $DICTEE_LIB_DIR pointing into the venv (version downgrade case)
    local _l _t
    for _l in "$DICTEE_LIB_DIR"/lib*.so*; do
        [ -L "$_l" ] || continue
        _t="$(readlink "$_l")"
        case "$_t" in "$CUDA_VENV"/*) [ -e "$_l" ] || rm -f "$_l" ;; esac
    done

    # (Re)symlink all the venv's lib*.so* → /usr/lib/dictee/
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
        echo "✓ $_count NVIDIA libs linked into $DICTEE_LIB_DIR/"
    fi
    ldconfig 2>/dev/null || true
    return 0
}

# Only run main when executed directly (not when sourced by tests).
if [ -z "${DICTEE_CUDA_LIB_SOURCED:-}" ]; then
    dictee_setup_cuda_venv_main "$@"
fi
