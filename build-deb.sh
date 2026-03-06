#!/bin/bash
set -e

cd "$(dirname "$0")"

VERSION="0.3.2"
PKG_DIR="pkg/dictee"

echo "========================================"
echo "  Building dictee $VERSION"
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
Package: dictee-cuda
Version: 0.3.2
Section: sound
Priority: optional
Architecture: amd64
Depends: ydotool, pipewire | pulseaudio-utils | alsa-utils, curl, ffmpeg
Recommends: nvidia-cuda-toolkit, wl-clipboard, libnotify-bin, python3-gi, gir1.2-ayatanaappindicator3-0.1
Conflicts: dictee-cpu
Provides: dictee
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

    dpkg-deb --build "$PKG_DIR" "dictee-cuda_${VERSION}_amd64.deb"

    # Decompress for next build
    gunzip "$PKG_DIR/usr/share/man/man1/"*.gz 2>/dev/null || true
    echo "Built: dictee-cuda_${VERSION}_amd64.deb"
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
Package: dictee-cpu
Version: 0.3.2
Section: sound
Priority: optional
Architecture: amd64
Depends: ydotool, pipewire | pulseaudio-utils | alsa-utils, curl, ffmpeg
Recommends: wl-clipboard, libnotify-bin, python3-gi, gir1.2-ayatanaappindicator3-0.1
Conflicts: dictee-cuda
Provides: dictee
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

    dpkg-deb --build "$PKG_DIR" "dictee-cpu_${VERSION}_amd64.deb"
    echo "Built: dictee-cpu_${VERSION}_amd64.deb"

    # Decompress for potential next build
    gunzip "$PKG_DIR/usr/share/man/man1/"*.gz 2>/dev/null || true
}

# Build tar.gz (non-Debian)
build_tarball() {
    echo ""
    echo "=== [TAR.GZ] Creating universal archive ==="
    local TARBALL_DIR="dictee-${VERSION}"
    rm -rf "$TARBALL_DIR"
    mkdir -p "$TARBALL_DIR/usr/bin"
    mkdir -p "$TARBALL_DIR/usr/lib/systemd/user"
    mkdir -p "$TARBALL_DIR/usr/share/man/man1"
    mkdir -p "$TARBALL_DIR/usr/share/icons/hicolor/scalable/apps"

    # Binaires (derniers compilés = CPU)
    for bin in transcribe transcribe-daemon transcribe-client transcribe-diarize transcribe-stream-diarize; do
        cp "target/release/$bin" "$TARBALL_DIR/usr/bin/"
    done
    cp "$PKG_DIR/usr/bin/dictee" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-setup" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/parakeet-tray" "$TARBALL_DIR/usr/bin/"

    # Services systemd
    cp "$PKG_DIR/usr/lib/systemd/user/"*.service "$TARBALL_DIR/usr/lib/systemd/user/"

    # Man pages
    cp "$PKG_DIR/usr/share/man/man1/"*.1 "$TARBALL_DIR/usr/share/man/man1/" 2>/dev/null || true

    # Icônes
    cp "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/"*.svg "$TARBALL_DIR/usr/share/icons/hicolor/scalable/apps/"

    # Scripts d'installation
    cp install.sh "$TARBALL_DIR/"
    cp uninstall.sh "$TARBALL_DIR/"
    chmod 755 "$TARBALL_DIR/install.sh" "$TARBALL_DIR/uninstall.sh"

    tar czf "dictee-${VERSION}_amd64.tar.gz" "$TARBALL_DIR"
    rm -rf "$TARBALL_DIR"
    echo "Built: dictee-${VERSION}_amd64.tar.gz"
}

# Build both versions + tarball
build_cuda
build_cpu
build_tarball

echo ""
echo "========================================"
echo "  Build complete!"
echo "========================================"
echo ""
echo "Packages created:"
echo "  - dictee-cuda_${VERSION}_amd64.deb  (Debian/Ubuntu, NVIDIA GPU)"
echo "  - dictee-cpu_${VERSION}_amd64.deb   (Debian/Ubuntu, CPU)"
echo "  - dictee-${VERSION}_amd64.tar.gz    (Autres distributions)"
echo ""
echo "Install (.deb):"
echo "  sudo dpkg -i dictee-{cuda,cpu}_${VERSION}_amd64.deb"
echo "  sudo apt-get install -f  # if dependencies missing"
echo ""
echo "Install (.tar.gz):"
echo "  tar xzf dictee-${VERSION}_amd64.tar.gz"
echo "  cd dictee-${VERSION}"
echo "  sudo ./install.sh"
echo ""
echo "Uninstall:"
echo "  sudo dpkg -r dictee-{cuda,cpu}"
echo "  sudo ./uninstall.sh  # tar.gz"
