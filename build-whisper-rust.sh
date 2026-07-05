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
    #
    # CUDA 12.x toolkits are preferred: the deb/rpm/tarball packages provision
    # their CUDA runtime from pip nvidia-*-cu12 wheels (postinst cuda-venv →
    # /usr/lib/dictee), so the daemon they ship must carry .so.12 DT_NEEDED
    # sonames — a 13.x-built daemon needs libcudart.so.13/libcublas.so.13 that
    # those packages never install, and fails to exec on every user machine.
    # /opt/cuda (Arch) builds against the system toolkit, which pacman keeps
    # coherent at runtime (`cuda` is in PKGBUILD-cuda depends).
    LOCAL_TC="${XDG_CACHE_HOME:-$HOME/.cache}/dictee-build/cuda-12.8/bin"
    CUDA_BIN=""
    for d in $(ls -d /usr/local/cuda-12* 2>/dev/null | sort -rV | sed 's|$|/bin|') \
             "$LOCAL_TC"; do
      if [ -x "$d/nvcc" ]; then CUDA_BIN="$d"; break; fi
    done
    # Distribution builds (soname guard armed) must link the cu12 runtime:
    # with no CUDA 12 toolkit around, bootstrap the local root-less one
    # (packaging/setup-cuda12-build-toolchain.sh — NVIDIA repo payloads
    # extracted under ~/.cache, the build-side mirror of setup-cuda-venv.sh).
    if [ -z "$CUDA_BIN" ] && [ -n "${DICTEE_REQUIRE_CUDART_SONAME:-}" ]; then
      CUDA_BIN="$("$(dirname "$0")/packaging/setup-cuda12-build-toolchain.sh")/bin"
    fi
    if [ -z "$CUDA_BIN" ]; then
      for d in /usr/local/cuda/bin /opt/cuda/bin; do
        if [ -x "$d/nvcc" ]; then CUDA_BIN="$d"; break; fi
      done
    fi
    if [ -n "$CUDA_BIN" ]; then
      export PATH="$CUDA_BIN:$PATH"
      export CUDACXX="$CUDA_BIN/nvcc"
    elif command -v nvcc >/dev/null 2>&1; then
      export CUDACXX="$(command -v nvcc)"
    else
      echo "error: nvcc not found (looked in /usr/local/cuda*/bin, the dictee-build cache, /opt/cuda/bin, PATH)" >&2
      exit 1
    fi
    # whisper-rs-sys hardcodes -L /usr/local/cuda/lib64 and /opt/cuda/lib64
    # (build.rs, non-Windows branch): with a 13.x toolkit there, the final
    # link would resolve cudart/cublas from the WRONG major even though the
    # objects were compiled with the toolkit chosen above (seen as
    # `undefined reference to cudaGetDeviceProperties_v2` — removed in 13).
    # Put the chosen toolkit's lib dirs first so compile and link agree.
    CUDA_HOME="$(dirname "$(dirname "$CUDACXX")")"
    if [ -d "$CUDA_HOME/lib64" ]; then
      export RUSTFLAGS="${RUSTFLAGS:-} -L $CUDA_HOME/lib64 -L $CUDA_HOME/lib64/stubs"
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
    # whisper-rs-sys's build script does NOT re-run when CUDAARCHS or the
    # toolkit changes (no rerun-if-env-changed), so a warm target/ silently
    # keeps kernels built for the previous arch list / CUDA version. Stamp
    # both and force a targeted rebuild when either differs.
    TARGET_DIR="${CARGO_TARGET_DIR:-target}"
    STAMP="$TARGET_DIR/.whisper-cudaarchs"
    STAMP_VAL="$CUDAARCHS@$("$CUDACXX" --version | grep -o 'release [0-9.]*')"
    if [ "$(cat "$STAMP" 2>/dev/null)" != "$STAMP_VAL" ]; then
      cargo clean --release -p whisper-rs-sys 2>/dev/null || true
      mkdir -p "$TARGET_DIR" && printf '%s' "$STAMP_VAL" > "$STAMP"
    fi
    cargo build --release --no-default-features \
      --features "cuda,sortformer,load-dynamic,whisper-cuda" \
      --bin transcribe-daemon-whisper-rust
    # Distribution guard: the packaging scripts export
    # DICTEE_REQUIRE_CUDART_SONAME=12 so a daemon accidentally linked against
    # another CUDA major (unusable with the packages' cu12 pip runtime) fails
    # the build instead of shipping. Arch/makepkg does not set it (system
    # toolkit == system runtime there).
    if [ -n "${DICTEE_REQUIRE_CUDART_SONAME:-}" ]; then
      BIN="$TARGET_DIR/release/transcribe-daemon-whisper-rust"
      GOT=$(objdump -p "$BIN" | sed -n 's/.*NEEDED *libcudart\.so\.\([0-9]*\).*/\1/p')
      if [ "$GOT" != "$DICTEE_REQUIRE_CUDART_SONAME" ]; then
        echo "error: $BIN links libcudart.so.${GOT:-?} but the packages ship" >&2
        echo "       the cu${DICTEE_REQUIRE_CUDART_SONAME} pip runtime — install a CUDA ${DICTEE_REQUIRE_CUDART_SONAME}.x toolkit" >&2
        exit 1
      fi
    fi ;;
  *) echo "usage: $0 {vulkan|cuda}" >&2; exit 1 ;;
esac
