#!/bin/bash
set -e

cd "$(dirname "$0")"

VERSION="1.3.0~rc3"
PKG_DIR="pkg/dictee"

# Final artefacts go in .dev/dist/ (gitignored), keeping the repo root clean.
DIST_DIR=".dev/dist"
mkdir -p "$DIST_DIR"

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
cp ./dictee-transcribe.py "$PKG_DIR/usr/bin/dictee-transcribe"
cp ./dictee-reset "$PKG_DIR/usr/bin/dictee-reset"
cp ./dictee-translate-langs "$PKG_DIR/usr/bin/dictee-translate-langs"
cp ./dictee-audio-sources "$PKG_DIR/usr/bin/dictee-audio-sources"
cp ./dictee-cheatsheet "$PKG_DIR/usr/bin/dictee-cheatsheet"
mkdir -p "$PKG_DIR/usr/lib/dictee"
cp ./dictee-common.sh "$PKG_DIR/usr/lib/dictee/dictee-common.sh"
cp ./dictee_models.py "$PKG_DIR/usr/lib/dictee/dictee_models.py"
cp ./dictee.conf.example "$PKG_DIR/usr/share/dictee/dictee.conf.example"
chmod 755 "$PKG_DIR/usr/bin/dictee" "$PKG_DIR/usr/bin/dictee-setup" "$PKG_DIR/usr/bin/dictee-tray" "$PKG_DIR/usr/bin/dictee-ptt" "$PKG_DIR/usr/bin/dictee-postprocess" "$PKG_DIR/usr/bin/dictee-switch-backend" "$PKG_DIR/usr/bin/dictee-test-rules" "$PKG_DIR/usr/bin/dictee-transcribe" "$PKG_DIR/usr/bin/dictee-reset" "$PKG_DIR/usr/bin/dictee-translate-langs" "$PKG_DIR/usr/bin/dictee-audio-sources" "$PKG_DIR/usr/bin/dictee-cheatsheet"

# Copier les fichiers de post-traitement par défaut
cp ./rules.conf.default "$PKG_DIR/usr/share/dictee/rules.conf.default"

# Generate VERSION file
BUILD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "$VERSION build $BUILD_HASH" > "$PKG_DIR/usr/share/dictee/VERSION"
cp ./dictionary.conf.default "$PKG_DIR/usr/share/dictee/dictionary.conf.default"
cp ./continuation.conf.default "$PKG_DIR/usr/share/dictee/continuation.conf.default"
cp ./short_text_keepcaps.conf.default "$PKG_DIR/usr/share/dictee/short_text_keepcaps.conf.default"

# Copier les assets (bannières SVG pour le wizard)
echo "=== Copie des assets ==="
mkdir -p "$PKG_DIR/usr/share/dictee/assets"
cp ./assets/banner-dark.svg ./assets/banner-light.svg "$PKG_DIR/usr/share/dictee/assets/"
if [ -d "./assets/logos" ]; then
    mkdir -p "$PKG_DIR/usr/share/dictee/assets/logos"
    cp ./assets/logos/*.svg "$PKG_DIR/usr/share/dictee/assets/logos/"
fi
if [ -d "./assets/icons" ]; then
    mkdir -p "$PKG_DIR/usr/share/dictee/assets/icons"
    cp ./assets/icons/*.svg "$PKG_DIR/usr/share/dictee/assets/icons/"
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
    # Regenerate Defaults.js from config/main.xml (source of truth for kcfg
    # defaults, used by the "Reset icon settings" button).
    if [ -x plasmoid/gen-defaults.py ]; then
        python3 plasmoid/gen-defaults.py
    fi
    (cd "$PLASMOID_SRC" && zip -r "../../$DIST_DIR/dictee.plasmoid" metadata.json contents/)
    mkdir -p "$PKG_DIR/usr/share/dictee"
    cp "$DIST_DIR/dictee.plasmoid" "$PKG_DIR/usr/share/dictee/"
    echo "Plasmoid built and staged"
    echo ""
}

build_plasmoid

# Build CUDA version
build_cuda() {
    echo "=== [CUDA] Compiling binaries with GPU support ==="
    # CRITICAL: --no-default-features disables ort-defaults (static linking)
    # load-dynamic enables runtime loading of libonnxruntime.so for CUDA
    cargo build --release --no-default-features --features "cuda,sortformer,load-dynamic" \
        --bin transcribe \
        --bin transcribe-daemon \
        --bin transcribe-client \
        --bin transcribe-diarize \
        --bin transcribe-stream-diarize

    # Update control file for CUDA
    cat > "$PKG_DIR/DEBIAN/control" << 'EOF'
Package: dictee-cuda
Version: 1.3.0~rc3
Section: sound
Priority: optional
Architecture: amd64
Depends: python3, python3-venv, python3-pip, pulseaudio-utils, pipewire | alsa-utils, libnotify-bin, python3-pyqt6, python3-pyqt6.qtmultimedia, python3-pyqt6.qtsvg, sox
Recommends: python3-evdev, wl-clipboard, xclip | xsel, curl, translate-shell, python3-numpy, docker.io, gir1.2-ayatanaappindicator3-0.1, gnome-shell-extension-appindicator, qt6-gtk-platformtheme
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

    # ONNX Runtime CUDA libs (load-dynamic: libonnxruntime.so not in target/release)
    echo "=== Copie des libs CUDA ONNX Runtime ==="
    mkdir -p "$PKG_DIR/usr/lib/dictee"

    # Search paths for libonnxruntime.so (not produced by load-dynamic build)
    ORT_LIB=""
    for candidate in \
        "target/release/libonnxruntime.so" \
        "onnxruntime-linux-x64-gpu-*/lib/libonnxruntime.so" \
        "$HOME/.cache/ort.pyke.io/dfbin/*/libonnxruntime.so"; do
        # shellcheck disable=SC2086
        for f in $candidate; do
            if [ -f "$f" ]; then
                ORT_LIB="$f"
                break 2
            fi
        done
    done
    if [ -z "$ORT_LIB" ]; then
        echo "ERROR: libonnxruntime.so not found! Download ONNX Runtime GPU from:"
        echo "  https://github.com/microsoft/onnxruntime/releases"
        echo "Extract it in the project root (onnxruntime-linux-x64-gpu-*/lib/)"
        exit 1
    fi
    echo "Using libonnxruntime.so from: $ORT_LIB"
    cp -L "$ORT_LIB" "$PKG_DIR/usr/lib/dictee/"

    # Provider libs from the same directory as libonnxruntime.so.
    # ORT_DIR was historically undefined — fall back to dirname(ORT_LIB).
    ORT_LIB_DIR="$(dirname "$ORT_LIB")"
    _missing_providers=""
    for lib in libonnxruntime_providers_cuda.so libonnxruntime_providers_shared.so; do
        if [ -f "$ORT_LIB_DIR/$lib" ]; then
            cp -L "$ORT_LIB_DIR/$lib" "$PKG_DIR/usr/lib/dictee/"
            echo "  $lib ← $ORT_LIB_DIR/$lib"
        else
            _missing_providers="$_missing_providers $lib"
        fi
    done
    if [ -n "$_missing_providers" ]; then
        echo "ERROR: CUDA providers missing in $ORT_LIB_DIR:$_missing_providers" >&2
        echo "The CUDA package will silently fall back to CPU at runtime." >&2
        exit 1
    fi

    # CUDA runtime libs (cudart, cublas, cudnn, cufft, curand, nvrtc) are
    # NOT bundled here. They are pip-installed at postinst time into
    # /opt/dictee/cuda-venv and symlinked into /usr/lib/dictee/ so this
    # package stays portable on any distro without requiring the NVIDIA
    # repo. See pkg/dictee/DEBIAN/postinst.

    # ld.so.conf.d entry so the dynamic linker finds them
    mkdir -p "$PKG_DIR/etc/ld.so.conf.d"
    echo "/usr/lib/dictee" > "$PKG_DIR/etc/ld.so.conf.d/dictee.conf"

    chmod 755 "$PKG_DIR/usr/bin/"*
    chmod 755 "$PKG_DIR/DEBIAN/postinst"
    chmod 755 "$PKG_DIR/DEBIAN/postrm"

    # Compress man pages
    gzip -9 -f "$PKG_DIR/usr/share/man/man1/"*.1 2>/dev/null || true
    gzip -9 -f "$PKG_DIR/usr/share/man/fr/man1/"*.1 2>/dev/null || true

    dpkg-deb --build "$PKG_DIR" "$DIST_DIR/dictee-cuda_${VERSION}_amd64.deb"

    # Decompress for next build
    gunzip "$PKG_DIR/usr/share/man/man1/"*.gz 2>/dev/null || true
    gunzip "$PKG_DIR/usr/share/man/fr/man1/"*.gz 2>/dev/null || true

    # Cleanup CUDA libs for CPU build (keep shared scripts/modules).
    # Glob *.so* catches libcudart.so.12 / libcufft.so.11 too (the plain
    # *.so only matches libonnxruntime.so, leaving 278 MB of CUDA libs
    # behind inside the CPU .deb).
    rm -f "$PKG_DIR/usr/lib/dictee/"*.so \
          "$PKG_DIR/usr/lib/dictee/"*.so.* \
          "$PKG_DIR/etc/ld.so.conf.d/dictee.conf"
    echo "Built: $DIST_DIR/dictee-cuda_${VERSION}_amd64.deb"
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
Version: 1.3.0~rc3
Section: sound
Priority: optional
Architecture: amd64
Depends: python3, python3-venv, pulseaudio-utils, pipewire | alsa-utils, libnotify-bin, python3-pyqt6, python3-pyqt6.qtmultimedia, python3-pyqt6.qtsvg, sox
Recommends: python3-evdev, wl-clipboard, xclip | xsel, curl, translate-shell, python3-numpy, docker.io, gir1.2-ayatanaappindicator3-0.1, gnome-shell-extension-appindicator, qt6-gtk-platformtheme
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

    dpkg-deb --build "$PKG_DIR" "$DIST_DIR/dictee-cpu_${VERSION}_amd64.deb"
    echo "Built: $DIST_DIR/dictee-cpu_${VERSION}_amd64.deb"

    # Decompress for potential next build
    gunzip "$PKG_DIR/usr/share/man/man1/"*.gz 2>/dev/null || true
    gunzip "$PKG_DIR/usr/share/man/fr/man1/"*.gz 2>/dev/null || true
}

# Build standalone dictee-plasmoid .deb (Architecture: all, depends on dictee).
# Rebuild guarantees pkg/dictee-plasmoid/ is refreshed from source on every run
# so the .deb content always matches the just-built dictee.plasmoid.
build_plasmoid_deb() {
    echo ""
    echo "=== [PLASMOID] Building standalone dictee-plasmoid .deb ==="
    local PP="pkg/dictee-plasmoid"

    if [ ! -f "$DIST_DIR/dictee.plasmoid" ]; then
        echo "ERROR: $DIST_DIR/dictee.plasmoid not built (build_plasmoid must run first)." >&2
        exit 1
    fi

    # Refresh the raw .plasmoid file shipped under /usr/share/dictee/
    mkdir -p "$PP/usr/share/dictee"
    cp "$DIST_DIR/dictee.plasmoid" "$PP/usr/share/dictee/dictee.plasmoid"

    # Refresh the extracted plasmoid tree under /usr/share/plasma/plasmoids/
    local PLASMA_DIR="$PP/usr/share/plasma/plasmoids/com.github.rcspam.dictee"
    rm -rf "$PLASMA_DIR"
    mkdir -p "$PLASMA_DIR"
    unzip -q -o "$DIST_DIR/dictee.plasmoid" -d "$PLASMA_DIR"

    # Refresh locale .mo files from plasmoid source (system-wide install path)
    for _lang in fr de es it pt uk; do
        local _mo="plasmoid/package/contents/locale/$_lang/LC_MESSAGES/plasma_applet_com.github.rcspam.dictee.mo"
        if [ -f "$_mo" ]; then
            mkdir -p "$PP/usr/share/locale/$_lang/LC_MESSAGES"
            cp "$_mo" "$PP/usr/share/locale/$_lang/LC_MESSAGES/"
        fi
    done

    # Regenerate control file with current $VERSION
    cat > "$PP/DEBIAN/control" << EOF
Package: dictee-plasmoid
Version: ${VERSION}
Section: kde
Priority: optional
Architecture: all
Depends: dictee
Recommends: python3-numpy, pulseaudio-utils
Maintainer: rcspam <rcspams@gmail.com>
Description: KDE Plasma 6 widget for dictee voice dictation
 A native KDE Plasma 6 widget for dictee voice dictation.
 Displays real-time audio visualization during recording, daemon status,
 and provides quick controls (dictate, translate, meeting).
 .
 Five animation styles with configurable sensitivity and color gradients.
EOF

    chmod 755 "$PP/DEBIAN/postinst" "$PP/DEBIAN/postrm" 2>/dev/null || true

    dpkg-deb --build "$PP" "$DIST_DIR/dictee-plasmoid_${VERSION}_all.deb"
    echo "Built: $DIST_DIR/dictee-plasmoid_${VERSION}_all.deb"
    echo ""
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
    cp "$PKG_DIR/usr/bin/dictee-transcribe" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-cheatsheet" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/transcribe-daemon-vosk" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/transcribe-daemon-whisper" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level-daemon" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level-fft" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dotool" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dotoold" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-reset" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-translate-langs" "$TARBALL_DIR/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-audio-sources" "$TARBALL_DIR/usr/bin/"

    # Shared libraries
    mkdir -p "$TARBALL_DIR/usr/lib/dictee"
    cp "$PKG_DIR/usr/lib/dictee/dictee-common.sh" "$TARBALL_DIR/usr/lib/dictee/"
    cp "$PKG_DIR/usr/lib/dictee/dictee_models.py" "$TARBALL_DIR/usr/lib/dictee/"

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
    cp "$PKG_DIR/usr/share/dictee/short_text_keepcaps.conf.default" "$TARBALL_DIR/usr/share/dictee/"
    cp "$PKG_DIR/usr/share/dictee/dictee.conf.example" "$TARBALL_DIR/usr/share/dictee/"
    cp "$PKG_DIR/usr/share/dictee/assets/"*.svg "$TARBALL_DIR/usr/share/dictee/assets/"
    if [ -d "$PKG_DIR/usr/share/dictee/assets/logos" ]; then
        mkdir -p "$TARBALL_DIR/usr/share/dictee/assets/logos"
        cp "$PKG_DIR/usr/share/dictee/assets/logos/"*.svg "$TARBALL_DIR/usr/share/dictee/assets/logos/"
    fi
    if [ -d "$PKG_DIR/usr/share/dictee/assets/icons" ]; then
        mkdir -p "$TARBALL_DIR/usr/share/dictee/assets/icons"
        cp "$PKG_DIR/usr/share/dictee/assets/icons/"*.svg "$TARBALL_DIR/usr/share/dictee/assets/icons/"
    fi


    # ONNX Runtime CUDA libs (copy from deb pkg if available)
    if [ -d "$PKG_DIR/usr/lib/dictee" ]; then
        mkdir -p "$TARBALL_DIR/usr/lib/dictee"
        for lib in libonnxruntime.so libonnxruntime_providers_cuda.so libonnxruntime_providers_shared.so; do
            if [ -f "$PKG_DIR/usr/lib/dictee/$lib" ]; then
                cp "$PKG_DIR/usr/lib/dictee/$lib" "$TARBALL_DIR/usr/lib/dictee/"
            fi
        done
    fi

    # Scripts d'installation
    cp install.sh "$TARBALL_DIR/"
    cp uninstall.sh "$TARBALL_DIR/"
    chmod 755 "$TARBALL_DIR/install.sh" "$TARBALL_DIR/uninstall.sh"

    tar czf "$DIST_DIR/dictee-${VERSION}_amd64.tar.gz" "$TARBALL_DIR"
    rm -rf "$TARBALL_DIR"
    echo "Built: $DIST_DIR/dictee-${VERSION}_amd64.tar.gz"
}

# Build all Debian variants + tarball
build_cuda
build_cpu
build_plasmoid_deb
build_tarball

# Safeguard: the build MUST produce cuda + cpu + plasmoid .deb. If any is
# missing, someone removed or broke a build step — fail loud instead of
# shipping an incomplete release. Do not remove this check.
_expected_debs=(
    "$DIST_DIR/dictee-cuda_${VERSION}_amd64.deb"
    "$DIST_DIR/dictee-cpu_${VERSION}_amd64.deb"
    "$DIST_DIR/dictee-plasmoid_${VERSION}_all.deb"
)
_missing=""
for _d in "${_expected_debs[@]}"; do
    [ -f "$_d" ] || _missing="$_missing $_d"
done
if [ -n "$_missing" ]; then
    echo "" >&2
    echo "ERROR: expected .deb packages missing:$_missing" >&2
    echo "Every build must produce cuda + cpu + plasmoid .deb." >&2
    exit 1
fi

echo ""
echo "========================================"
echo "  Build complete!"
echo "========================================"
echo ""
echo "Packages created in $DIST_DIR/ :"
echo "  - dictee-cuda_${VERSION}_amd64.deb     (Debian/Ubuntu, NVIDIA GPU)"
echo "  - dictee-cpu_${VERSION}_amd64.deb      (Debian/Ubuntu, CPU)"
echo "  - dictee-plasmoid_${VERSION}_all.deb   (Debian/Ubuntu, plasmoid only)"
echo "  - dictee-${VERSION}_amd64.tar.gz       (Autres distributions)"
echo ""
echo "Install (.deb):"
echo "  sudo dpkg -i $DIST_DIR/dictee-{cuda,cpu}_${VERSION}_amd64.deb"
echo "  sudo dpkg -i $DIST_DIR/dictee-plasmoid_${VERSION}_all.deb  # plasmoid only"
echo "  sudo apt-get install -f  # if dependencies missing"
echo ""
echo "Install (.tar.gz):"
echo "  tar xzf $DIST_DIR/dictee-${VERSION}_amd64.tar.gz"
echo "  cd dictee-${VERSION}"
echo "  sudo ./install.sh"
echo ""
echo "Uninstall:"
echo "  sudo dpkg -r dictee-{cuda,cpu,plasmoid}"
echo "  sudo ./uninstall.sh  # tar.gz"
