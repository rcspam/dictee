#!/bin/bash
# Build the whisper-rust daemon binary with the standard features/env per GPU
# variant. ALWAYS --bin transcribe-daemon-whisper-rust (never touches the
# diarisation symlinks). Used by the packaging scripts and the dev workflow.
set -euo pipefail
case "${1:-}" in
  vulkan)  # needs glslc (shaderc) in PATH
    cargo build --release --features "sortformer,whisper-vulkan" \
      --bin transcribe-daemon-whisper-rust ;;
  cuda)
    # nvcc discovery: NVIDIA repo/runfile installs /usr/local/cuda[-X.Y],
    # the Arch `cuda` package installs /opt/cuda, Fedora puts it on PATH.
    CUDA_BIN=""
    for d in /usr/local/cuda-13.3/bin /usr/local/cuda/bin /opt/cuda/bin; do
      if [ -x "$d/nvcc" ]; then CUDA_BIN="$d"; break; fi
    done
    if [ -n "$CUDA_BIN" ]; then
      export PATH="$CUDA_BIN:$PATH"
      export CUDACXX="$CUDA_BIN/nvcc"
    elif command -v nvcc >/dev/null 2>&1; then
      export CUDACXX="$(command -v nvcc)"
    else
      echo "error: nvcc not found (looked in /usr/local/cuda*/bin, /opt/cuda/bin, PATH)" >&2
      exit 1
    fi
    # Kernel architectures. Distribution builds MUST cover the GPUs dictee
    # supports (Turing 75 through Blackwell 120, same floor as the ORT CUDA
    # EP). Building only the host arch (e.g. 89) ships a daemon that
    # silently has no kernels on other GPUs. NOTE: whisper.cpp's cmake
    # emits SASS only — no PTX, even for `-virtual` entries (verified with
    # cuobjdump on the built binary) — so post-Blackwell GPU families need
    # this list extended at the following release.
    # Dev fast path: DICTEE_CUDAARCHS=89 ./build-whisper-rust.sh cuda
    export CUDAARCHS="${DICTEE_CUDAARCHS:-75;80;86;89;90;120}"
    # whisper-rs-sys's build script does NOT re-run when CUDAARCHS changes
    # (no rerun-if-env-changed), so a warm target/ silently keeps kernels
    # built for the previous arch list. Stamp the arch list and force a
    # targeted rebuild when it differs.
    STAMP="target/.whisper-cudaarchs"
    if [ "$(cat "$STAMP" 2>/dev/null)" != "$CUDAARCHS" ]; then
      cargo clean --release -p whisper-rs-sys 2>/dev/null || true
      mkdir -p target && printf '%s' "$CUDAARCHS" > "$STAMP"
    fi
    cargo build --release --no-default-features \
      --features "cuda,sortformer,load-dynamic,whisper-cuda" \
      --bin transcribe-daemon-whisper-rust ;;
  *) echo "usage: $0 {vulkan|cuda}" >&2; exit 1 ;;
esac
