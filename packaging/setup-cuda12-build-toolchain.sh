#!/usr/bin/env bash
# dictee: assemble a LOCAL CUDA 12.8 build toolchain (nvcc + cudart + cublas
# headers/libs) from the NVIDIA repository .deb payloads — no root, nothing
# installed system-wide.
#
# This is the build-side mirror of the runtime philosophy established in 1.3
# by setup-cuda-venv.sh: the packages provision their CUDA runtime from pip
# nvidia-*-cu12 wheels, so the whisper-rust daemon must LINK CUDA 12 sonames
# (.so.12) and therefore must BUILD against a CUDA 12 toolkit — regardless of
# whatever toolkit the build host has installed system-wide. The pip wheels
# cannot serve the build side (nvidia-cuda-nvcc-cu12 ships ptxas/nvvm but NOT
# the nvcc frontend — verified 2026-07-05 on 12.6/12.8/12.9), so the toolchain
# comes from the same NVIDIA repository as extracted .deb payloads instead.
#
# Usage: packaging/setup-cuda12-build-toolchain.sh
#   Prints the toolkit root (bin/nvcc under it) on stdout.
#   Cached in ${XDG_CACHE_HOME:-$HOME/.cache}/dictee-build/cuda-12.8 —
#   ~1 GB download on first run, instant no-op afterwards.
set -euo pipefail

CUDA_VER="12.8"
REPO="https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64"
# Exact payload pins (reproducible builds — bump deliberately, then check
# `nvcc --list-gpu-arch` still covers CUDAARCHS in build-whisper-rust.sh).
DEBS=(
    cuda-nvcc-12-8_12.8.93-1_amd64.deb
    cuda-crt-12-8_12.8.93-1_amd64.deb
    cuda-nvvm-12-8_12.8.93-1_amd64.deb
    cuda-cudart-12-8_12.8.90-1_amd64.deb
    cuda-cudart-dev-12-8_12.8.90-1_amd64.deb
    cuda-cccl-12-8_12.8.90-1_amd64.deb
    libcublas-12-8_12.8.5.5-1_amd64.deb
    libcublas-dev-12-8_12.8.5.5-1_amd64.deb
)
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/dictee-build"
ROOT="$CACHE/cuda-$CUDA_VER"

if [ -x "$ROOT/bin/nvcc" ]; then
    printf '%s\n' "$ROOT"
    exit 0
fi

WORK=$(mktemp -d -t dictee-cuda-toolchain.XXXXXX)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$CACHE" "$WORK/x"

echo "→ Assembling the local CUDA $CUDA_VER build toolchain (~1 GB, one-time)..." >&2
for deb in "${DEBS[@]}"; do
    echo "  fetching $deb" >&2
    curl -fsSL -o "$WORK/$deb" "$REPO/$deb"
    # Portable .deb payload extraction: dpkg-deb where available, plain
    # binutils ar + tar everywhere else (Fedora/Arch build hosts).
    if command -v dpkg-deb >/dev/null 2>&1; then
        dpkg-deb -x "$WORK/$deb" "$WORK/x"
    else
        data=$(ar t "$WORK/$deb" | grep '^data\.tar')
        ( cd "$WORK/x" && ar p "$WORK/$deb" "$data" > ../data.tar && tar -xf ../data.tar )
    fi
done

[ -x "$WORK/x/usr/local/cuda-$CUDA_VER/bin/nvcc" ] \
    || { echo "error: extracted payloads carry no bin/nvcc — pins outdated?" >&2; exit 1; }
rm -rf "$ROOT"
mv "$WORK/x/usr/local/cuda-$CUDA_VER" "$ROOT"
printf '%s\n' "$ROOT"
