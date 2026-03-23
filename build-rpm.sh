#!/bin/bash
set -e

cd "$(dirname "$0")"

VERSION="1.1.3"
PKG_DIR="pkg/dictee"
RPMBUILD_DIR="$HOME/rpmbuild"

echo "========================================"
echo "  Building dictee RPM $VERSION"
echo "========================================"
echo ""

# Copier les scripts depuis les sources uniques (racine)
cp ./dictee "$PKG_DIR/usr/bin/dictee"
cp ./dictee-setup.py "$PKG_DIR/usr/bin/dictee-setup"
cp ./dictee-tray.py "$PKG_DIR/usr/bin/dictee-tray"
cp ./dictee-ptt.py "$PKG_DIR/usr/bin/dictee-ptt"
cp ./dictee-postprocess.py "$PKG_DIR/usr/bin/dictee-postprocess"
chmod 755 "$PKG_DIR/usr/bin/dictee" "$PKG_DIR/usr/bin/dictee-setup" "$PKG_DIR/usr/bin/dictee-tray" "$PKG_DIR/usr/bin/dictee-ptt" "$PKG_DIR/usr/bin/dictee-postprocess"

# Vérifier rpmbuild
if ! command -v rpmbuild >/dev/null 2>&1; then
    echo "rpmbuild non trouvé. Installer avec :"
    echo "  sudo dnf install rpm-build"
    echo "  # ou"
    echo "  sudo apt install rpm"
    exit 1
fi

# Vérifier que les binaires existent (compilés par build-deb.sh)
if [ ! -f "target/release/transcribe" ]; then
    echo "Binaires non trouvés. Lancez d'abord :"
    echo "  ./build-deb.sh"
    echo "  # ou"
    echo "  cargo build --release --features sortformer"
    exit 1
fi

# Préparer l'arborescence rpmbuild
mkdir -p "$RPMBUILD_DIR"/{SPECS,SOURCES,BUILD,RPMS,SRPMS}

# ============================================================
# Fonctions communes
# ============================================================

prepare_buildroot() {
    local buildroot="$1"
    rm -rf "$buildroot"

    # Binaires
    mkdir -p "$buildroot/usr/bin"
    for bin in transcribe transcribe-daemon transcribe-client transcribe-diarize transcribe-stream-diarize; do
        cp "target/release/$bin" "$buildroot/usr/bin/"
    done
    cp "$PKG_DIR/usr/bin/dictee" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-setup" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-tray" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-ptt" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-postprocess" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level-daemon" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level-fft" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dotool" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dotoold" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/transcribe-daemon-vosk" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/transcribe-daemon-whisper" "$buildroot/usr/bin/"
    chmod 755 "$buildroot/usr/bin/"*

    # Patcher shebangs pour packaging RPM (guidelines Fedora)
    # /usr/bin/env python3 → /usr/bin/python3 pour utiliser le Python système
    sed -i '1s|^#!/usr/bin/env python3|#!/usr/bin/python3|' \
        "$buildroot/usr/bin/dictee-setup" \
        "$buildroot/usr/bin/dictee-tray" \
        "$buildroot/usr/bin/dictee-ptt" \
        "$buildroot/usr/bin/dictee-postprocess" \
        "$buildroot/usr/bin/transcribe-daemon-vosk" \
        "$buildroot/usr/bin/transcribe-daemon-whisper" \
        "$buildroot/usr/bin/dictee-plasmoid-level" \
        "$buildroot/usr/bin/dictee-plasmoid-level-daemon" \
        "$buildroot/usr/bin/dictee-plasmoid-level-fft"

    # Udev
    mkdir -p "$buildroot/etc/udev/rules.d"
    cp "$PKG_DIR/etc/udev/rules.d/80-dotool.rules" "$buildroot/etc/udev/rules.d/"

    # Systemd
    mkdir -p "$buildroot/usr/lib/systemd/user"
    mkdir -p "$buildroot/usr/lib/systemd/user-preset"
    cp "$PKG_DIR/usr/lib/systemd/user/"*.service "$buildroot/usr/lib/systemd/user/"
    cp "$PKG_DIR/usr/lib/systemd/user-preset/"*.preset "$buildroot/usr/lib/systemd/user-preset/"

    # Man pages
    mkdir -p "$buildroot/usr/share/man/man1"
    mkdir -p "$buildroot/usr/share/man/fr/man1"
    cp "$PKG_DIR/usr/share/man/man1/"*.1 "$buildroot/usr/share/man/man1/" 2>/dev/null || true
    cp "$PKG_DIR/usr/share/man/fr/man1/"*.1 "$buildroot/usr/share/man/fr/man1/" 2>/dev/null || true
    gzip -9 -f "$buildroot/usr/share/man/man1/"*.1 2>/dev/null || true
    gzip -9 -f "$buildroot/usr/share/man/fr/man1/"*.1 2>/dev/null || true

    # Icônes
    mkdir -p "$buildroot/usr/share/icons/hicolor/scalable/apps"
    cp "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/"*.svg "$buildroot/usr/share/icons/hicolor/scalable/apps/"

    # Locales
    for lang in fr de es it pt uk; do
        mkdir -p "$buildroot/usr/share/locale/$lang/LC_MESSAGES"
        cp "$PKG_DIR/usr/share/locale/$lang/LC_MESSAGES/"*.mo "$buildroot/usr/share/locale/$lang/LC_MESSAGES/" 2>/dev/null || true
    done

    # Desktop entry
    mkdir -p "$buildroot/usr/share/applications"
    cp "$PKG_DIR/usr/share/applications/"*.desktop "$buildroot/usr/share/applications/"

    # Assets (bannières + logos)
    mkdir -p "$buildroot/usr/share/dictee/assets"
    cp ./assets/banner-dark.svg ./assets/banner-light.svg "$buildroot/usr/share/dictee/assets/"
    if [ -d "./assets/logos" ]; then
        mkdir -p "$buildroot/usr/share/dictee/assets/logos"
        cp ./assets/logos/*.svg "$buildroot/usr/share/dictee/assets/logos/"
    fi

    # Plasmoid + rules
    mkdir -p "$buildroot/usr/share/dictee"
    cp "$PKG_DIR/usr/share/dictee/dictee.plasmoid" "$buildroot/usr/share/dictee/" 2>/dev/null || true
    cp ./rules.conf.default "$buildroot/usr/share/dictee/rules.conf.default"

    # Doc
    mkdir -p "$buildroot/usr/share/doc/dictee"
    cp "$PKG_DIR/usr/share/doc/dictee/README" "$buildroot/usr/share/doc/dictee/" 2>/dev/null || true
}

# ============================================================
# Build RPM CUDA
# ============================================================

build_rpm_cuda() {
    echo ""
    echo "=== [RPM CUDA] Building dictee-cuda ==="

    # Recompiler en CUDA si nécessaire
    if ! nm target/release/transcribe 2>/dev/null | grep -q cuda; then
        echo "Recompilation CUDA..."
        cargo build --release --features "cuda,sortformer" \
            --bin transcribe \
            --bin transcribe-daemon \
            --bin transcribe-client \
            --bin transcribe-diarize \
            --bin transcribe-stream-diarize
    fi

    local buildroot="$RPMBUILD_DIR/BUILDROOT/dictee-cuda-$VERSION-1.x86_64"
    prepare_buildroot "$buildroot"

    cat > "$RPMBUILD_DIR/SPECS/dictee-cuda.spec" << EOF
Name:           dictee-cuda
Version:        $VERSION
Release:        1
Summary:        Fast speech-to-text with NVIDIA Parakeet (CUDA GPU version)
License:        GPL-3.0-or-later
URL:            https://github.com/rcspam/dictee
Group:          Applications/Multimedia

Requires:       python3
Requires:       pulseaudio-utils
Requires:       (pipewire or alsa-utils)
Requires:       libnotify
Requires:       (python3-pyqt6 or python3-qt6-PyQt6)
Recommends:     python3-qt6-PyQt6-Multimedia
Recommends:     python3-qt6-PyQt6-sip
Recommends:     (libcublas-12-8 or libcublas-12-6)
Recommends:     (libcudnn9-cuda-12 or libcudnn9-cuda-11)
Recommends:     nvidia-gpu-firmware
Recommends:     python3-evdev
Recommends:     wl-clipboard
Recommends:     xclip
Recommends:     curl
Recommends:     translate-shell
Recommends:     python3-numpy
Recommends:     moby-engine
Recommends:     libayatana-appindicator-gtk3
Conflicts:      dictee-cpu
Provides:       dictee = $VERSION

%description
A daemon-based speech recognition system using NVIDIA's Parakeet TDT model.
This version uses CUDA for GPU acceleration (NVIDIA GPUs only).
Falls back to CPU if CUDA is not available.

Features:
- GPU-accelerated transcription via CUDA
- Low-latency daemon mode with preloaded model
- Push-to-talk dictation with dotool integration
- Speaker diarization with Sortformer

%files
/usr/bin/*
/etc/udev/rules.d/80-dotool.rules
/usr/lib/systemd/user/*.service
/usr/lib/systemd/user-preset/*.preset
/usr/share/man/man1/*.gz
/usr/share/man/fr/man1/*.gz
/usr/share/icons/hicolor/scalable/apps/*.svg
/usr/share/locale/*/LC_MESSAGES/*.mo
/usr/share/applications/*.desktop
/usr/share/dictee/*
/usr/share/doc/dictee/*

%post
udevadm control --reload-rules 2>/dev/null || true

%postun
udevadm control --reload-rules 2>/dev/null || true
EOF

    rpmbuild --define "_topdir $RPMBUILD_DIR" \
             --buildroot "$buildroot" \
             -bb "$RPMBUILD_DIR/SPECS/dictee-cuda.spec"

    cp "$RPMBUILD_DIR/RPMS/x86_64/dictee-cuda-$VERSION-1.x86_64.rpm" .
    echo "Built: dictee-cuda-$VERSION-1.x86_64.rpm"
}

# ============================================================
# Build RPM CPU
# ============================================================

build_rpm_cpu() {
    echo ""
    echo "=== [RPM CPU] Building dictee-cpu ==="

    # Recompiler en CPU
    cargo build --release --features "sortformer" \
        --bin transcribe \
        --bin transcribe-daemon \
        --bin transcribe-client \
        --bin transcribe-diarize \
        --bin transcribe-stream-diarize

    local buildroot="$RPMBUILD_DIR/BUILDROOT/dictee-cpu-$VERSION-1.x86_64"
    prepare_buildroot "$buildroot"

    cat > "$RPMBUILD_DIR/SPECS/dictee-cpu.spec" << EOF
Name:           dictee-cpu
Version:        $VERSION
Release:        1
Summary:        Fast speech-to-text with NVIDIA Parakeet (CPU version)
License:        GPL-3.0-or-later
URL:            https://github.com/rcspam/dictee
Group:          Applications/Multimedia

Requires:       python3
Requires:       pulseaudio-utils
Requires:       (pipewire or alsa-utils)
Requires:       libnotify
Requires:       (python3-pyqt6 or python3-qt6-PyQt6)
Recommends:     python3-qt6-PyQt6-Multimedia
Recommends:     python3-qt6-PyQt6-sip
Recommends:     python3-evdev
Recommends:     wl-clipboard
Recommends:     xclip
Recommends:     curl
Recommends:     translate-shell
Recommends:     python3-numpy
Recommends:     moby-engine
Recommends:     libayatana-appindicator-gtk3
Conflicts:      dictee-cuda
Provides:       dictee = $VERSION

%description
A daemon-based speech recognition system using NVIDIA's Parakeet TDT model.
This version runs on CPU only (works on any computer, slower than GPU).

Features:
- CPU-based transcription (no GPU required)
- Low-latency daemon mode with preloaded model
- Push-to-talk dictation with dotool integration
- Speaker diarization with Sortformer

%files
/usr/bin/*
/etc/udev/rules.d/80-dotool.rules
/usr/lib/systemd/user/*.service
/usr/lib/systemd/user-preset/*.preset
/usr/share/man/man1/*.gz
/usr/share/man/fr/man1/*.gz
/usr/share/icons/hicolor/scalable/apps/*.svg
/usr/share/locale/*/LC_MESSAGES/*.mo
/usr/share/applications/*.desktop
/usr/share/dictee/*
/usr/share/doc/dictee/*

%post
udevadm control --reload-rules 2>/dev/null || true

%postun
udevadm control --reload-rules 2>/dev/null || true
EOF

    rpmbuild --define "_topdir $RPMBUILD_DIR" \
             --buildroot "$buildroot" \
             -bb "$RPMBUILD_DIR/SPECS/dictee-cpu.spec"

    cp "$RPMBUILD_DIR/RPMS/x86_64/dictee-cpu-$VERSION-1.x86_64.rpm" .
    echo "Built: dictee-cpu-$VERSION-1.x86_64.rpm"
}

# ============================================================
# Build RPM Plasmoid (noarch)
# ============================================================

build_rpm_plasmoid() {
    echo ""
    echo "=== [RPM Plasmoid] Building dictee-plasmoid ==="

    local buildroot="$RPMBUILD_DIR/BUILDROOT/dictee-plasmoid-$VERSION-1.noarch"
    rm -rf "$buildroot"

    # Plasmoid
    mkdir -p "$buildroot/usr/share/dictee"
    cp "$PKG_DIR/usr/share/dictee/dictee.plasmoid" "$buildroot/usr/share/dictee/" 2>/dev/null || true

    # Locales plasmoid
    local plasmoid_locale="plasmoid/package/contents/locale"
    if [ -d "$plasmoid_locale" ]; then
        for lang_dir in "$plasmoid_locale"/*/; do
            lang=$(basename "$lang_dir")
            mkdir -p "$buildroot/usr/share/locale/$lang/LC_MESSAGES"
            cp "$lang_dir/LC_MESSAGES/"*.mo "$buildroot/usr/share/locale/$lang/LC_MESSAGES/" 2>/dev/null || true
        done
    fi

    cat > "$RPMBUILD_DIR/SPECS/dictee-plasmoid.spec" << EOF
Name:           dictee-plasmoid
Version:        $VERSION
Release:        1
Summary:        KDE Plasma 6 widget for dictee voice dictation
License:        GPL-3.0-or-later
URL:            https://github.com/rcspam/dictee
Group:          System/GUI/KDE
BuildArch:      noarch

Requires:       dictee
Requires:       kf6-kpackage
Recommends:     python3-numpy
Recommends:     pulseaudio-utils

%description
A native KDE Plasma 6 widget for dictee voice dictation.
Displays real-time audio visualization during recording, daemon status,
and provides quick controls (dictate, translate, cancel).

Five animation styles with configurable sensitivity and color gradients.

%files
/usr/share/dictee/dictee.plasmoid
/usr/share/locale/*/LC_MESSAGES/*.mo

%post
if command -v kpackagetool6 >/dev/null 2>&1; then
    kpackagetool6 -t Plasma/Applet -u /usr/share/dictee/dictee.plasmoid 2>/dev/null || \
    kpackagetool6 -t Plasma/Applet -i /usr/share/dictee/dictee.plasmoid 2>/dev/null || true
fi

%postun
if [ "\$1" -eq 0 ] && command -v kpackagetool6 >/dev/null 2>&1; then
    kpackagetool6 -t Plasma/Applet -r com.github.rcspam.dictee 2>/dev/null || true
fi
EOF

    rpmbuild --define "_topdir $RPMBUILD_DIR" \
             --buildroot "$buildroot" \
             -bb "$RPMBUILD_DIR/SPECS/dictee-plasmoid.spec"

    cp "$RPMBUILD_DIR/RPMS/noarch/dictee-plasmoid-$VERSION-1.noarch.rpm" .
    echo "Built: dictee-plasmoid-$VERSION-1.noarch.rpm"
}

# ============================================================
# Build source tarball
# ============================================================

build_source_tarball() {
    echo ""
    echo "=== [SOURCE] Creating source archive ==="

    local SRC_DIR="dictee-$VERSION-source"
    rm -rf "$SRC_DIR"

    # Exporter depuis git
    git archive --format=tar --prefix="$SRC_DIR/" HEAD | tar xf -

    tar czf "dictee-$VERSION-source.tar.gz" "$SRC_DIR"
    rm -rf "$SRC_DIR"
    echo "Built: dictee-$VERSION-source.tar.gz"
}

# ============================================================
# Main
# ============================================================

build_rpm_cuda
build_rpm_cpu
build_rpm_plasmoid
build_source_tarball

echo ""
echo "========================================"
echo "  RPM Build complete!"
echo "========================================"
echo ""
echo "Packages created:"
echo "  - dictee-cuda-$VERSION-1.x86_64.rpm     (Fedora/openSUSE, NVIDIA GPU)"
echo "  - dictee-cpu-$VERSION-1.x86_64.rpm      (Fedora/openSUSE, CPU)"
echo "  - dictee-plasmoid-$VERSION-1.noarch.rpm  (KDE Plasma widget)"
echo "  - dictee-$VERSION-source.tar.gz          (Source archive)"
echo ""
echo "Install (Fedora):"
echo "  sudo dnf install ./dictee-{cuda,cpu}-$VERSION-1.x86_64.rpm"
echo "  sudo dnf install ./dictee-plasmoid-$VERSION-1.noarch.rpm"
echo ""
echo "Install (openSUSE):"
echo "  sudo zypper install ./dictee-{cuda,cpu}-$VERSION-1.x86_64.rpm"
echo "  sudo zypper install ./dictee-plasmoid-$VERSION-1.noarch.rpm"
