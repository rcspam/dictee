#!/bin/bash
set -e

cd "$(dirname "$0")"

VERSION="1.2.0"
PKG_DIR="pkg/dictee"

DOTOOL_REPO="https://git.sr.ht/~geb/dotool"
DOTOOL_DIR="/tmp/dotool-build"

echo "========================================"
echo "  Building dictee $VERSION"
echo "========================================"
echo ""
echo "Build dependencies:"
echo "  sudo apt install golang-go scdoc libxkbcommon-dev"
echo ""

# Copier les scripts depuis les sources uniques (racine)
cp ./dictee "$PKG_DIR/usr/bin/dictee"
cp ./dictee-setup.py "$PKG_DIR/usr/bin/dictee-setup"
cp ./dictee-tray.py "$PKG_DIR/usr/bin/dictee-tray"
cp ./dictee-ptt.py "$PKG_DIR/usr/bin/dictee-ptt"
cp ./dictee-postprocess.py "$PKG_DIR/usr/bin/dictee-postprocess"
cp ./dictee-switch-backend "$PKG_DIR/usr/bin/dictee-switch-backend"
cp ./dictee-test-rules "$PKG_DIR/usr/bin/dictee-test-rules"
cp ./transcribe-daemon-canary "$PKG_DIR/usr/bin/transcribe-daemon-canary"
chmod 755 "$PKG_DIR/usr/bin/dictee" "$PKG_DIR/usr/bin/dictee-setup" "$PKG_DIR/usr/bin/dictee-tray" "$PKG_DIR/usr/bin/dictee-ptt" "$PKG_DIR/usr/bin/dictee-postprocess" "$PKG_DIR/usr/bin/dictee-switch-backend" "$PKG_DIR/usr/bin/dictee-test-rules" "$PKG_DIR/usr/bin/transcribe-daemon-canary"

# Copier les fichiers de post-traitement par défaut
cp ./rules.conf.default "$PKG_DIR/usr/share/dictee/rules.conf.default"

# Generate VERSION file
BUILD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "$VERSION build $BUILD_HASH" > "$PKG_DIR/usr/share/dictee/VERSION"
cp ./dictionary.conf.default "$PKG_DIR/usr/share/dictee/dictionary.conf.default"
cp ./continuation.conf.default "$PKG_DIR/usr/share/dictee/continuation.conf.default"

# Copier les assets (bannières SVG pour le wizard)
echo "=== Copie des assets ==="
mkdir -p "$PKG_DIR/usr/share/dictee/assets"
cp ./assets/banner-dark.svg ./assets/banner-light.svg "$PKG_DIR/usr/share/dictee/assets/"
if [ -d "./assets/logos" ]; then
    mkdir -p "$PKG_DIR/usr/share/dictee/assets/logos"
    cp ./assets/logos/*.svg "$PKG_DIR/usr/share/dictee/assets/logos/"
fi

# Compiler et copier les traductions
echo "=== Compilation des traductions ==="
for lang in fr de es it uk pt; do
    msgfmt -o "po/$lang.mo" "po/$lang.po" 2>/dev/null || true
    mkdir -p "$PKG_DIR/usr/share/locale/$lang/LC_MESSAGES"
    cp "po/$lang.mo" "$PKG_DIR/usr/share/locale/$lang/LC_MESSAGES/dictee.mo"
    # Copie interne (postinst les restaure si dpkg -r les a supprimées)
    mkdir -p "$PKG_DIR/usr/share/dictee/locale/$lang/LC_MESSAGES"
    cp "po/$lang.mo" "$PKG_DIR/usr/share/dictee/locale/$lang/LC_MESSAGES/dictee.mo"
done

# Build dotool (keyboard input tool)
build_dotool() {
    echo "=== Building dotool ==="

    # Vérifier les dépendances de compilation
    local missing=()
    command -v go >/dev/null || missing+=("golang-go")
    command -v scdoc >/dev/null || missing+=("scdoc")
    dpkg -s libxkbcommon-dev >/dev/null 2>&1 || missing+=("libxkbcommon-dev")
    if [ ${#missing[@]} -gt 0 ]; then
        echo "Dépendances manquantes pour compiler dotool : ${missing[*]}"
        echo "  sudo apt install ${missing[*]}"
        exit 1
    fi

    if [ ! -f "$DOTOOL_DIR/dotool" ]; then
        rm -rf "$DOTOOL_DIR"
        git clone "$DOTOOL_REPO" "$DOTOOL_DIR"
        (cd "$DOTOOL_DIR" && ./build.sh)
    else
        echo "dotool already built, skipping"
    fi

    # Install into package tree
    cp "$DOTOOL_DIR/dotool" "$PKG_DIR/usr/bin/"
    cp "$DOTOOL_DIR/dotoold" "$PKG_DIR/usr/bin/"
    mkdir -p "$PKG_DIR/etc/udev/rules.d"
    cp "$DOTOOL_DIR/80-dotool.rules" "$PKG_DIR/etc/udev/rules.d/"
    echo "dotool built and staged"
    echo ""
}

build_dotool

# Build plasmoid
build_plasmoid() {
    echo "=== Building dictee.plasmoid ==="
    local PLASMOID_SRC="plasmoid/package"
    if [ ! -d "$PLASMOID_SRC" ]; then
        echo "Plasmoid source not found, skipping"
        return
    fi
    (cd "$PLASMOID_SRC" && zip -r "../../dictee.plasmoid" metadata.json contents/)
    mkdir -p "$PKG_DIR/usr/share/dictee"
    cp dictee.plasmoid "$PKG_DIR/usr/share/dictee/"
    echo "Plasmoid built and staged"
    echo ""
}

build_plasmoid

# Build CUDA version
build_cuda() {
    echo "=== [CUDA] Compiling binaries with GPU support ==="
    cargo build --release --no-default-features --features "cuda,sortformer,load-dynamic" \
        --bin transcribe \
        --bin transcribe-daemon \
        --bin transcribe-client \
        --bin transcribe-diarize \
        --bin transcribe-stream-diarize

    # Update control file for CUDA
    cat > "$PKG_DIR/DEBIAN/control" << 'EOF'
Package: dictee-cuda
Version: 1.2.0
Section: sound
Priority: optional
Architecture: amd64
Depends: python3, python3-venv, pulseaudio-utils, pipewire | alsa-utils, libnotify-bin, python3-pyqt6, python3-pyqt6.qtmultimedia, python3-pyqt6.qtsvg
Recommends: libcublas12 | libcublas-12-8 | libcublas-12-6, libcudnn9-cuda-12 | libcudnn9-cuda-11, python3-evdev, wl-clipboard, xclip | xsel, curl, translate-shell, python3-numpy, docker.io, gir1.2-ayatanaappindicator3-0.1, gnome-shell-extension-appindicator
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
  - Push-to-talk dictation with dotool integration
  - Speaker diarization with Sortformer (who speaks when)
EOF

    # Copy binaries
    cp target/release/transcribe "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-daemon "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-client "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-diarize "$PKG_DIR/usr/bin/"
    cp target/release/transcribe-stream-diarize "$PKG_DIR/usr/bin/"

    # ONNX Runtime libs (load-dynamic nécessite libonnxruntime.so)
    echo "=== Copie des libs ONNX Runtime + CUDA ==="
    mkdir -p "$PKG_DIR/usr/lib/dictee"

    # Lib ORT principale (requise par load-dynamic)
    ORT_TGZ="onnxruntime-linux-x64-gpu-1.23.0.tgz"
    ORT_DIR="onnxruntime-linux-x64-gpu-1.23.0"
    if [ ! -d "$ORT_DIR" ]; then
        if [ ! -f "$ORT_TGZ" ]; then
            echo "Téléchargement d'ONNX Runtime GPU 1.23.0..."
            curl -LO "https://github.com/microsoft/onnxruntime/releases/download/v1.23.0/$ORT_TGZ"
        fi
        tar xzf "$ORT_TGZ"
    fi
    cp "$ORT_DIR/lib/libonnxruntime.so.1.23.0" "$PKG_DIR/usr/lib/dictee/"
    ln -sf libonnxruntime.so.1.23.0 "$PKG_DIR/usr/lib/dictee/libonnxruntime.so.1"
    ln -sf libonnxruntime.so.1 "$PKG_DIR/usr/lib/dictee/libonnxruntime.so"

    # Provider libs
    for lib in libonnxruntime_providers_cuda.so libonnxruntime_providers_shared.so; do
        if [ -f "$ORT_DIR/lib/$lib" ]; then
            cp "$ORT_DIR/lib/$lib" "$PKG_DIR/usr/lib/dictee/"
        fi
    done

    # CUDA runtime libs (chercher dans : CUDA toolkit, système, pip/uv)
    for lib in libcufft.so.11 libcudart.so.12; do
        sys_lib=$(find /usr/local/cuda/lib64 /usr/lib/x86_64-linux-gnu /usr/lib/dictee \
                       "$HOME"/.cache/uv/archive-v0/*/nvidia/*/lib \
                       "$HOME"/.local/share/dictee/*/lib/python*/site-packages/nvidia/*/lib \
                  -name "$lib" -type f 2>/dev/null | head -1)
        if [ -n "$sys_lib" ]; then
            cp -L "$sys_lib" "$PKG_DIR/usr/lib/dictee/$lib"
            echo "  $lib ← $sys_lib"
        else
            echo "ERREUR: $lib non trouvé — le paquet CUDA ne fonctionnera pas !"
            echo "  Installer avec : pip download nvidia-cufft-cu12 nvidia-cuda-runtime-cu12"
            exit 1
        fi
    done

    # ld.so.conf.d entry so the dynamic linker finds them
    mkdir -p "$PKG_DIR/etc/ld.so.conf.d"
    echo "/usr/lib/dictee" > "$PKG_DIR/etc/ld.so.conf.d/dictee.conf"

    chmod 755 "$PKG_DIR/usr/bin/"*
    chmod 755 "$PKG_DIR/DEBIAN/postinst"
    chmod 755 "$PKG_DIR/DEBIAN/postrm"

    # Compress man pages
    gzip -9 -f "$PKG_DIR/usr/share/man/man1/"*.1 2>/dev/null || true
    gzip -9 -f "$PKG_DIR/usr/share/man/fr/man1/"*.1 2>/dev/null || true

    dpkg-deb --build "$PKG_DIR" "dictee-cuda_${VERSION}_amd64.deb"

    # Decompress for next build
    gunzip "$PKG_DIR/usr/share/man/man1/"*.gz 2>/dev/null || true
    gunzip "$PKG_DIR/usr/share/man/fr/man1/"*.gz 2>/dev/null || true

    # Cleanup CUDA libs for CPU build
    rm -rf "$PKG_DIR/usr/lib/dictee" "$PKG_DIR/etc/ld.so.conf.d/dictee.conf"
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
Version: 1.2.0
Section: sound
Priority: optional
Architecture: amd64
Depends: python3, python3-venv, pulseaudio-utils, pipewire | alsa-utils, libnotify-bin, python3-pyqt6, python3-pyqt6.qtmultimedia, python3-pyqt6.qtsvg
Recommends: python3-evdev, wl-clipboard, xclip | xsel, curl, translate-shell, python3-numpy, docker.io, gir1.2-ayatanaappindicator3-0.1, gnome-shell-extension-appindicator
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
  - Push-to-talk dictation with dotool integration
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
    gzip -9 -f "$PKG_DIR/usr/share/man/fr/man1/"*.1 2>/dev/null || true

    dpkg-deb --build "$PKG_DIR" "dictee-cpu_${VERSION}_amd64.deb"
    echo "Built: dictee-cpu_${VERSION}_amd64.deb"

    # Decompress for potential next build
    gunzip "$PKG_DIR/usr/share/man/man1/"*.gz 2>/dev/null || true
    gunzip "$PKG_DIR/usr/share/man/fr/man1/"*.gz 2>/dev/null || true
}

# Build tar.gz (non-Debian)
build_tarball() {
    echo ""
    echo "=== [TAR.GZ] Creating universal archive ==="
    local TARBALL_DIR="dictee-${VERSION}"
    rm -rf "$TARBALL_DIR"
    mkdir -p "$TARBALL_DIR/usr/bin"
    mkdir -p "$TARBALL_DIR/usr/lib/systemd/user"
    mkdir -p "$TARBALL_DIR/usr/lib/systemd/user-preset"
    mkdir -p "$TARBALL_DIR/usr/share/man/man1"
    mkdir -p "$TARBALL_DIR/usr/share/man/fr/man1"
    mkdir -p "$TARBALL_DIR/usr/share/icons/hicolor/scalable/apps"
    for _lang in fr de es it pt uk; do
        mkdir -p "$TARBALL_DIR/usr/share/locale/$_lang/LC_MESSAGES"
    done
    mkdir -p "$TARBALL_DIR/usr/share/applications"
    mkdir -p "$TARBALL_DIR/etc/udev/rules.d"

    # Binaires (derniers compilés = CPU)
    for bin in transcribe transcribe-daemon transcribe-client transcribe-diarize transcribe-stream-diarize; do
        cp "target/release/$bin" "$TARBALL_DIR/usr/bin/"
    done
    cp "$PKG_DIR/usr/bin/dictee" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-setup" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-tray" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-ptt" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-switch-backend" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-postprocess" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-test-rules" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/transcribe-daemon-canary" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/transcribe-daemon-vosk" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/transcribe-daemon-whisper" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level-daemon" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level-fft" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dotool" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dotoold" "$TARBALL_DIR/usr/bin/"

    # Udev rules (dotool)
    cp "$PKG_DIR/etc/udev/rules.d/80-dotool.rules" "$TARBALL_DIR/etc/udev/rules.d/"

    # Services systemd + preset
    cp "$PKG_DIR/usr/lib/systemd/user/"*.service "$TARBALL_DIR/usr/lib/systemd/user/"
    cp "$PKG_DIR/usr/lib/systemd/user-preset/"*.preset "$TARBALL_DIR/usr/lib/systemd/user-preset/"

    # Man pages
    cp "$PKG_DIR/usr/share/man/man1/"*.1 "$TARBALL_DIR/usr/share/man/man1/" 2>/dev/null || true
    cp "$PKG_DIR/usr/share/man/fr/man1/"*.1 "$TARBALL_DIR/usr/share/man/fr/man1/" 2>/dev/null || true

    # Icônes
    cp "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/"*.svg "$TARBALL_DIR/usr/share/icons/hicolor/scalable/apps/"

    # Locales
    for _lang in fr de es it pt uk; do
        cp "$PKG_DIR/usr/share/locale/$_lang/LC_MESSAGES/"*.mo "$TARBALL_DIR/usr/share/locale/$_lang/LC_MESSAGES/" 2>/dev/null || true
    done

    # Desktop entry
    cp "$PKG_DIR/usr/share/applications/"*.desktop "$TARBALL_DIR/usr/share/applications/"

    # Plasmoid + assets
    mkdir -p "$TARBALL_DIR/usr/share/dictee/assets"
    cp "$PKG_DIR/usr/share/dictee/dictee.plasmoid" "$TARBALL_DIR/usr/share/dictee/" 2>/dev/null || true
    cp "$PKG_DIR/usr/share/dictee/rules.conf.default" "$TARBALL_DIR/usr/share/dictee/"
    cp "$PKG_DIR/usr/share/dictee/dictionary.conf.default" "$TARBALL_DIR/usr/share/dictee/"
    cp "$PKG_DIR/usr/share/dictee/continuation.conf.default" "$TARBALL_DIR/usr/share/dictee/"
    cp "$PKG_DIR/usr/share/dictee/assets/"*.svg "$TARBALL_DIR/usr/share/dictee/assets/"
    if [ -d "$PKG_DIR/usr/share/dictee/assets/logos" ]; then
        mkdir -p "$TARBALL_DIR/usr/share/dictee/assets/logos"
        cp "$PKG_DIR/usr/share/dictee/assets/logos/"*.svg "$TARBALL_DIR/usr/share/dictee/assets/logos/"
    fi

    # ONNX Runtime + CUDA libs (si le build CUDA a téléchargé le tgz ORT)
    ORT_DIR="onnxruntime-linux-x64-gpu-1.23.0"
    if [ -d "$ORT_DIR" ]; then
        mkdir -p "$TARBALL_DIR/usr/lib/dictee"
        cp "$ORT_DIR/lib/libonnxruntime.so.1.23.0" "$TARBALL_DIR/usr/lib/dictee/"
        ln -sf libonnxruntime.so.1.23.0 "$TARBALL_DIR/usr/lib/dictee/libonnxruntime.so.1"
        ln -sf libonnxruntime.so.1 "$TARBALL_DIR/usr/lib/dictee/libonnxruntime.so"
        for lib in libonnxruntime_providers_cuda.so libonnxruntime_providers_shared.so; do
            if [ -f "$ORT_DIR/lib/$lib" ]; then
                cp "$ORT_DIR/lib/$lib" "$TARBALL_DIR/usr/lib/dictee/"
            fi
        done
        # CUDA runtime libs
        for lib in libcufft.so.11 libcudart.so.12; do
            sys_lib=$(find /usr/local/cuda/lib64 /usr/lib/x86_64-linux-gnu /usr/lib/dictee \
                           "$HOME"/.cache/uv/archive-v0/*/nvidia/*/lib \
                           "$HOME"/.local/share/dictee/*/lib/python*/site-packages/nvidia/*/lib \
                      -name "$lib" -type f 2>/dev/null | head -1)
            if [ -n "$sys_lib" ]; then
                cp -L "$sys_lib" "$TARBALL_DIR/usr/lib/dictee/$lib"
            fi
        done
        mkdir -p "$TARBALL_DIR/etc/ld.so.conf.d"
        echo "/usr/lib/dictee" > "$TARBALL_DIR/etc/ld.so.conf.d/dictee.conf"
    fi

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
