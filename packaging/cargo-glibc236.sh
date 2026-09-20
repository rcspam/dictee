#!/bin/bash
# cargo-glibc236.sh — run cargo inside a Debian 12 (glibc 2.36) container.
#
# Used by build-deb.sh / build-rpm.sh / build-tar.sh for every release
# build so the shipped binaries only require glibc 2.36 (issue #32:
# binaries linked on the maintainer's Ubuntu 24.04 imported GLIBC_2.39 and
# transcribe-daemon refused to start on Debian 12).
#
# Usage: ./packaging/cargo-glibc236.sh build --release --features sortformer ...
#
# The repo is mounted at /src, the host crate registry is shared so nothing
# is downloaded twice, and the output goes to target/glibc236/ so it never
# mixes with host builds in target/release/.
set -e

cd "$(dirname "$0")/.."

IMAGE="localhost/dictee-build-glibc236"
RUNTIME="${CONTAINER_RUNTIME:-podman}"
if ! command -v "$RUNTIME" >/dev/null 2>&1; then
    echo "FATAL: $RUNTIME not found — install podman (or set CONTAINER_RUNTIME=docker)" >&2
    exit 1
fi

if ! "$RUNTIME" image exists "$IMAGE" 2>/dev/null; then
    echo "=== Building $IMAGE (one-off, Debian 12 + rustup stable) ==="
    "$RUNTIME" build -t "$IMAGE" -f packaging/Containerfile.glibc236 packaging
fi

mkdir -p "$HOME/.cargo/registry" target/glibc236

exec "$RUNTIME" run --rm \
    -v "$PWD:/src" \
    -v "$HOME/.cargo/registry:/usr/local/cargo/registry" \
    -w /src \
    -e CARGO_TARGET_DIR=/src/target/glibc236 \
    "$IMAGE" cargo "$@"
