#!/usr/bin/env bash
# Dev build helper for the Kyutai daemon crate (separate candle crate).
# Builds into dictee-kyutai-daemon/target/ — never the root target/release/,
# so it cannot stub the diarization binaries the cargo-build guard protects.
set -euo pipefail
cd "$(dirname "$0")"
CUDA_LOCAL="${CUDA_LOCAL:-$PWD/tests/poc-kyutai/cuda-12.8-local/usr/local/cuda-12.8}"
export CUDARC_CUDA_VERSION="${CUDARC_CUDA_VERSION:-12090}"
export CUDA_COMPUTE_CAP="${CUDA_COMPUTE_CAP:-89}"
export PATH="$CUDA_LOCAL/bin:$PATH"
export CUDA_ROOT="$CUDA_LOCAL"
exec cargo build --release --features cuda \
  --manifest-path dictee-kyutai-daemon/Cargo.toml "$@"
