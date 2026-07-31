#!/usr/bin/env bash
# Dev build helper for the Kyutai daemon crate (separate candle crate).
# Builds into dictee-kyutai-daemon/target/ — never the root target/release/,
# so it cannot stub the diarization binaries the cargo-build guard protects.
set -euo pipefail
cd "$(dirname "$0")"
# nvcc 12.8 is REQUIRED: the 595.x driver is CUDA 13.2 and rejects the PTX 9.3
# that nvcc 13.3 emits. Install with:
#   apt install cuda-nvcc-12-8 libcublas-dev-12-8 cuda-nvrtc-dev-12-8 libcurand-dev-12-8
# (coexists with a newer toolkit). A pip venv is NOT enough: nvidia-cuda-nvcc-cu12
# ships ptxas and nvvm/ but no nvcc binary.
CUDA_LOCAL="${CUDA_LOCAL:-/usr/local/cuda-12.8}"
export CUDARC_CUDA_VERSION="${CUDARC_CUDA_VERSION:-12090}"
export CUDA_COMPUTE_CAP="${CUDA_COMPUTE_CAP:-89}"
export PATH="$CUDA_LOCAL/bin:$PATH"
export CUDA_ROOT="$CUDA_LOCAL"
exec cargo build --release --features cuda \
  --manifest-path dictee-kyutai-daemon/Cargo.toml "$@"
