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
    PATH="/usr/local/cuda-13.3/bin:$PATH" \
    CUDACXX="/usr/local/cuda-13.3/bin/nvcc" CUDAARCHS=89 \
      cargo build --release --no-default-features \
        --features "cuda,sortformer,load-dynamic,whisper-cuda" \
        --bin transcribe-daemon-whisper-rust ;;
  *) echo "usage: $0 {vulkan|cuda}" >&2; exit 1 ;;
esac
