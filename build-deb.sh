#!/bin/bash
set -e

cd "$(dirname "$0")"

VERSION="0.3.2"
PKG_DIR="pkg/parakeet-transcribe"

echo "========================================"
echo "  Building parakeet-transcribe $VERSION"
echo "========================================"
echo ""

# Build CUDA version
build_cuda() {
    echo "=== [CUDA] Compiling binaries with GPU support ==="
    cargo build --release --features "cuda,sortformer" \
        --bin transcribe \
        --bin transcribe-daemon \
        --bin transcribe-client \
        --bin transcribe-diarize \
        --bin transcribe-stream-diarize

    # Update control file for CUDA
    cat > "$PKG_DIR/DEBIAN/control" << 'EOF'
Package: parakeet-transcribe-cuda
Version: 0.3.2
Section: sound
Priority: optional
Architecture: amd64
Depends: ydotool, pipewire | pulseaudio-utils | alsa-utils, curl, ffmpeg
Recommends: nvidia-cuda-toolkit, wl-clipboard, libnotify-bin
Conflicts: parakeet-transcribe-cpu
Provides: parakeet-transcribe
Maintainer: rcspam <rcspams@gmail.com>
Description: Fast speech-to-text with NVIDIA Parakeet (CUDA GPU version)
 A daemon-based speech recognition system using NVIDIA's Parakeet TDT model.
 This version uses CUDA for GPU acceleration (NVIDIA GPUs only).
 Falls back to CPU if CUDA is not available.
 .
 Features:
  - GPU-accelerated transcription via CUDA
  - Low-latency daemon mode with preloaded model
  - Push-to-talk dictation with ydotool integration
  - Speaker diarization with Sortformer (who speaks when)
EOF

    # Copy binaries
    cp target/release/transcribe "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-daemon "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-client "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-diarize "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-stream-diarize "$PKG_DIR/usr/bin/"

    chmod 755 "$PKG_DIR/usr/bin/"*
    chmod 755 "$PKG_DIR/DEBIAN/postinst"
    chmod 755 "$PKG_DIR/DEBIAN/postrm"

    # Compress man pages
    gzip -9 -f "$PKG_DIR/usr/share/man/man1/"*.1 2>/dev/null || true

    dpkg-deb --build "$PKG_DIR" "parakeet-transcribe-cuda_${VERSION}_amd64.deb"

    # Decompress for next build
    gunzip "$PKG_DIR/usr/share/man/man1/"*.gz 2>/dev/null || true
    echo "Built: parakeet-transcribe-cuda_${VERSION}_amd64.deb"
}

# Build CPU version
build_cpu() {
    echo ""
    echo "=== [CPU] Compiling binaries for CPU-only ==="
    cargo build --release --features "sortformer" \
        --bin transcribe \
        --bin transcribe-daemon \
        --bin transcribe-client \
        --bin transcribe-diarize \
        --bin transcribe-stream-diarize

    # Update control file for CPU
    cat > "$PKG_DIR/DEBIAN/control" << 'EOF'
Package: parakeet-transcribe-cpu
Version: 0.3.2
Section: sound
Priority: optional
Architecture: amd64
Depends: ydotool, pipewire | pulseaudio-utils | alsa-utils, curl, ffmpeg
Recommends: wl-clipboard, libnotify-bin
Conflicts: parakeet-transcribe-cuda
Provides: parakeet-transcribe
Maintainer: rcspam <rcspams@gmail.com>
Description: Fast speech-to-text with NVIDIA Parakeet (CPU version)
 A daemon-based speech recognition system using NVIDIA's Parakeet TDT model.
 This version runs on CPU only (works on any computer, slower than GPU).
 .
 Features:
  - CPU-based transcription (no GPU required)
  - Low-latency daemon mode with preloaded model
  - Push-to-talk dictation with ydotool integration
  - Speaker diarization with Sortformer (who speaks when)
EOF

    # Copy binaries
    cp target/release/transcribe "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-daemon "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-client "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-diarize "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-stream-diarize "$PKG_DIR/usr/bin/"

    chmod 755 "$PKG_DIR/usr/bin/"*

    # Compress man pages
    gzip -9 -f "$PKG_DIR/usr/share/man/man1/"*.1 2>/dev/null || true

    dpkg-deb --build "$PKG_DIR" "parakeet-transcribe-cpu_${VERSION}_amd64.deb"
    echo "Built: parakeet-transcribe-cpu_${VERSION}_amd64.deb"

    # Decompress for potential next build
    gunzip "$PKG_DIR/usr/share/man/man1/"*.gz 2>/dev/null || true
}

# Build both versions
build_cuda
build_cpu

echo ""
echo "========================================"
echo "  Build complete!"
echo "========================================"
echo ""
echo "Packages created:"
echo "  - parakeet-transcribe-cuda_${VERSION}_amd64.deb (for NVIDIA GPU)"
echo "  - parakeet-transcribe-cpu_${VERSION}_amd64.deb  (for any computer)"
echo ""
echo "Install with:"
echo "  sudo dpkg -i parakeet-transcribe-{cuda,cpu}_${VERSION}_amd64.deb"
echo "  sudo apt-get install -f  # if dependencies missing"
echo ""
echo "Uninstall with:"
echo "  sudo dpkg -r parakeet-transcribe-cuda"
echo "  sudo dpkg -r parakeet-transcribe-cpu"
