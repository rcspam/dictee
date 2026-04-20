#!/bin/bash
set -e

cd "$(dirname "$0")"

VERSION="1.3.0~rc1"
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
cp ./dictee-switch-backend "$PKG_DIR/usr/bin/dictee-switch-backend"
cp ./dictee-test-rules "$PKG_DIR/usr/bin/dictee-test-rules"
cp ./dictee-transcribe.py "$PKG_DIR/usr/bin/dictee-transcribe"
chmod 755 "$PKG_DIR/usr/bin/dictee" "$PKG_DIR/usr/bin/dictee-setup" "$PKG_DIR/usr/bin/dictee-tray" "$PKG_DIR/usr/bin/dictee-ptt" "$PKG_DIR/usr/bin/dictee-postprocess" "$PKG_DIR/usr/bin/dictee-switch-backend" "$PKG_DIR/usr/bin/dictee-test-rules" "$PKG_DIR/usr/bin/dictee-transcribe"

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
    cp "$PKG_DIR/usr/bin/dictee-switch-backend" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level-daemon" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-plasmoid-level-fft" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dotool" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dotoold" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/transcribe-daemon-vosk" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/transcribe-daemon-whisper" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-test-rules" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-transcribe" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-reset" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-translate-langs" "$buildroot/usr/bin/"
    cp "$PKG_DIR/usr/bin/dictee-audio-sources" "$buildroot/usr/bin/"
    chmod 755 "$buildroot/usr/bin/"*
    # Shared libraries
    mkdir -p "$buildroot/usr/lib/dictee"
    cp "$PKG_DIR/usr/lib/dictee/dictee-common.sh" "$buildroot/usr/lib/dictee/"
    cp "$PKG_DIR/usr/lib/dictee/dictee_models.py" "$buildroot/usr/lib/dictee/"

    # Patcher shebangs pour packaging RPM (guidelines Fedora)
    # /usr/bin/env python3 → /usr/bin/python3 pour utiliser le Python système.
    # dictee-ptt a un shebang spécial (#!/usr/bin/env -S python3 -u) pour
    # forcer unbuffered — on le patche séparément.
    sed -i '1s|^#!/usr/bin/env -S python3 -u|#!/usr/bin/python3 -u|' \
        "$buildroot/usr/bin/dictee-ptt"
    sed -i '1s|^#!/usr/bin/env python3|#!/usr/bin/python3|' \
        "$buildroot/usr/bin/dictee-setup" \
        "$buildroot/usr/bin/dictee-tray" \
        "$buildroot/usr/bin/dictee-ptt" \
        "$buildroot/usr/bin/dictee-postprocess" \
        "$buildroot/usr/bin/transcribe-daemon-vosk" \
        "$buildroot/usr/bin/transcribe-daemon-whisper" \
        "$buildroot/usr/bin/dictee-transcribe" \
        "$buildroot/usr/bin/dictee-audio-sources" \
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

    # Assets (bannières + logos + icons)
    mkdir -p "$buildroot/usr/share/dictee/assets"
    cp ./assets/banner-dark.svg ./assets/banner-light.svg "$buildroot/usr/share/dictee/assets/"
    if [ -d "./assets/logos" ]; then
        mkdir -p "$buildroot/usr/share/dictee/assets/logos"
        cp ./assets/logos/*.svg "$buildroot/usr/share/dictee/assets/logos/"
    fi
    if [ -d "./assets/icons" ]; then
        mkdir -p "$buildroot/usr/share/dictee/assets/icons"
        cp ./assets/icons/*.svg "$buildroot/usr/share/dictee/assets/icons/"
    fi


    # Plasmoid + rules
    mkdir -p "$buildroot/usr/share/dictee"
    cp "$PKG_DIR/usr/share/dictee/dictee.plasmoid" "$buildroot/usr/share/dictee/" 2>/dev/null || true
    cp ./rules.conf.default "$buildroot/usr/share/dictee/rules.conf.default"

    # Generate VERSION file
    BUILD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    echo "$VERSION build $BUILD_HASH" > "$buildroot/usr/share/dictee/VERSION"
    cp ./dictionary.conf.default "$buildroot/usr/share/dictee/dictionary.conf.default"
    cp ./continuation.conf.default "$buildroot/usr/share/dictee/continuation.conf.default"
    cp ./short_text_keepcaps.conf.default "$buildroot/usr/share/dictee/short_text_keepcaps.conf.default"
    cp ./dictee.conf.example "$buildroot/usr/share/dictee/dictee.conf.example"

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
        # CRITICAL: --no-default-features disables ort-defaults (static linking)
        # load-dynamic enables runtime loading of libonnxruntime.so for CUDA
        cargo build --release --no-default-features --features "cuda,sortformer,load-dynamic" \
            --bin transcribe \
            --bin transcribe-daemon \
            --bin transcribe-client \
            --bin transcribe-diarize \
            --bin transcribe-stream-diarize
    fi

    local buildroot="$RPMBUILD_DIR/BUILDROOT/dictee-cuda-$VERSION-1.x86_64"
    prepare_buildroot "$buildroot"

    # ONNX Runtime CUDA libs (load-dynamic: libonnxruntime.so not in target/release)
    echo "Copie des libs CUDA ONNX Runtime..."
    mkdir -p "$buildroot/usr/lib/dictee"

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
    cp -L "$ORT_LIB" "$buildroot/usr/lib/dictee/"

    # Provider libs from the same directory as libonnxruntime.so.
    # ORT_DIR was historically undefined — fall back to dirname(ORT_LIB).
    ORT_LIB_DIR="$(dirname "$ORT_LIB")"
    _missing_providers=""
    for lib in libonnxruntime_providers_cuda.so libonnxruntime_providers_shared.so; do
        if [ -f "$ORT_LIB_DIR/$lib" ]; then
            cp -L "$ORT_LIB_DIR/$lib" "$buildroot/usr/lib/dictee/"
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

    # CUDA runtime libs (chercher dans : CUDA toolkit, système, pip/uv)
    for lib in libcufft.so.11 libcudart.so.12; do
        sys_lib=$(find /usr/local/cuda/lib64 /usr/lib/x86_64-linux-gnu /usr/lib/dictee \
                       "$HOME"/.cache/uv/archive-v0/*/nvidia/*/lib \
                       "$HOME"/.local/share/dictee/*/lib/python*/site-packages/nvidia/*/lib \
                  -name "$lib" -type f 2>/dev/null | head -1)
        if [ -n "$sys_lib" ]; then
            cp -L "$sys_lib" "$buildroot/usr/lib/dictee/$lib"
            echo "  $lib ← $sys_lib"
        else
            echo "ERREUR: $lib non trouvé — le paquet CUDA ne fonctionnera pas !"
            echo "  Installer avec : pip download nvidia-cufft-cu12 nvidia-cuda-runtime-cu12"
            exit 1
        fi
    done

    mkdir -p "$buildroot/etc/ld.so.conf.d"
    echo "/usr/lib/dictee" > "$buildroot/etc/ld.so.conf.d/dictee.conf"

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
Requires:       sox
Requires:       (libcudart12 or cuda-cudart-12-8 or cuda-cudart-12-6)
Requires:       (libcublas-12-8 or libcublas-12-6)
Requires:       (libcufft11 or libcufft-12-8 or libcufft-12-6)
Requires:       (libcudnn9-cuda-12 or libcudnn9-cuda-11)
Requires:       (libnvrtc12 or libnvrtc-12-8 or libnvrtc-12-6)
Recommends:     python3-qt6-PyQt6-Multimedia
Recommends:     python3-qt6-PyQt6-sip
Recommends:     nvidia-gpu-firmware
Recommends:     python3-evdev
Recommends:     wl-clipboard
Recommends:     xclip
Recommends:     curl
Recommends:     translate-shell
Recommends:     python3-numpy
Recommends:     moby-engine
Recommends:     libayatana-appindicator-gtk3
Recommends:     gnome-shell-extension-appindicator
Recommends:     gnome-extensions-app
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
/usr/lib/dictee/*
/etc/ld.so.conf.d/dictee.conf
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
ldconfig 2>/dev/null || true
# Fix udev rule if old version with 0620 (RPM preserves config files)
UDEV_RULE="/etc/udev/rules.d/80-dotool.rules"
if [ -f "\$UDEV_RULE" ] && grep -q 'MODE="0620"' "\$UDEV_RULE"; then
    sed -i 's/MODE="0620"/MODE="0660"/' "\$UDEV_RULE"
fi
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger /dev/uinput 2>/dev/null || true

# Per-user setup for all logged-in users
for uid in \$(loginctl list-sessions --no-legend 2>/dev/null | awk '{print \$2}' | sort -u); do
    user=\$(id -nu "\$uid" 2>/dev/null) || continue
    [ "\$user" = "root" ] && continue
    [ -d "/run/user/\$uid" ] || continue
    _run="sudo -u \$user XDG_RUNTIME_DIR=/run/user/\$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/\$uid/bus"

    # Add user to input group if needed
    if ! id -nG "\$user" | grep -qw input; then
        usermod -aG input "\$user"
    fi

    # Start and enable Docker daemon if installed
    if command -v docker >/dev/null 2>&1; then
        if ! systemctl is-active --quiet docker 2>/dev/null; then
            systemctl start docker 2>/dev/null || true
            systemctl enable docker 2>/dev/null || true
        fi
        if ! id -nG "\$user" | grep -qw docker; then
            usermod -aG docker "\$user"
        fi
    fi

    # Install plasmoid if KDE Plasma 6 is available
    if command -v kpackagetool6 >/dev/null 2>&1 && [ -f /usr/share/dictee/dictee.plasmoid ]; then
        sudo -u "\$user" kpackagetool6 -t Plasma/Applet -u /usr/share/dictee/dictee.plasmoid 2>/dev/null || \
        sudo -u "\$user" kpackagetool6 -t Plasma/Applet -i /usr/share/dictee/dictee.plasmoid 2>/dev/null || true
    fi

    # Enable GNOME AppIndicator extension for tray icon
    \$_run gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || true

    # Refresh icon cache (needed on GNOME)
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true
    fi

    # Reload and enable systemd user services
    \$_run systemctl --user daemon-reload 2>/dev/null || true
    \$_run systemctl --user enable dotoold dictee-ptt dictee-tray 2>/dev/null || true
    \$_run systemctl --user preset dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
    \$_run systemctl --user restart dotoold 2>/dev/null || true
    \$_run systemctl --user restart dictee-ptt 2>/dev/null || true
    # Only restart tray if user has a config (avoid starting unconfigured tray)
    _user_home=\$(getent passwd "\$user" | cut -d: -f6)
    if [ -f "\$_user_home/.config/dictee.conf" ]; then
        \$_run systemctl --user restart dictee-tray 2>/dev/null || true
    fi
    # Start the correct ASR daemon based on user config
    _asr_backend="parakeet"
    if [ -f "\$_user_home/.config/dictee.conf" ]; then
        _asr_backend=\$(grep -s '^DICTEE_ASR_BACKEND=' "\$_user_home/.config/dictee.conf" | cut -d= -f2)
    fi
    case "\$_asr_backend" in
        vosk)    _asr_svc="dictee-vosk" ;;
        whisper) _asr_svc="dictee-whisper" ;;
        canary)  _asr_svc="dictee-canary" ;;
        *)       _asr_svc="dictee" ;;
    esac
    \$_run systemctl --user stop dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
    \$_run systemctl --user disable dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
    \$_run systemctl --user enable "\$_asr_svc" 2>/dev/null || true
    \$_run systemctl --user start "\$_asr_svc" 2>/dev/null || true
done

# Create Python venv for text2num (number conversion)
PP_VENV="/usr/share/dictee/postprocess-env"
if command -v python3 >/dev/null 2>&1; then
    if [ ! -d "\$PP_VENV" ]; then
        if python3 -m venv "\$PP_VENV" 2>/dev/null; then
            "\$PP_VENV/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
            "\$PP_VENV/bin/pip" install --quiet text2num 2>/dev/null || true
        fi
    else
        "\$PP_VENV/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
        "\$PP_VENV/bin/pip" install --quiet --upgrade text2num 2>/dev/null || true
    fi
fi

%postun
ldconfig 2>/dev/null || true
if [ "\$1" -eq 0 ]; then
    # Full uninstall (not upgrade)
    rm -rf /usr/share/dictee/postprocess-env
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger /dev/uinput 2>/dev/null || true
    # Stop and disable user services
    for uid in \$(loginctl list-sessions --no-legend 2>/dev/null | awk '{print \$2}' | sort -u); do
        user=\$(id -nu "\$uid" 2>/dev/null) || continue
        [ "\$user" = "root" ] && continue
        [ -d "/run/user/\$uid" ] || continue
        _run="sudo -u \$user XDG_RUNTIME_DIR=/run/user/\$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/\$uid/bus"
        \$_run systemctl --user stop dictee-ptt dictee-tray dotoold dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
        \$_run systemctl --user disable dictee-ptt dictee-tray dotoold dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
        \$_run systemctl --user daemon-reload 2>/dev/null || true
    done
    # Clean locales
    for lang in fr de es it uk pt; do
        rm -f "/usr/share/locale/\$lang/LC_MESSAGES/dictee.mo"
    done
fi
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
Requires:       sox
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
Recommends:     gnome-shell-extension-appindicator
Recommends:     gnome-extensions-app
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
/usr/lib/dictee/*
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
# Fix udev rule if old version with 0620 (RPM preserves config files)
UDEV_RULE="/etc/udev/rules.d/80-dotool.rules"
if [ -f "\$UDEV_RULE" ] && grep -q 'MODE="0620"' "\$UDEV_RULE"; then
    sed -i 's/MODE="0620"/MODE="0660"/' "\$UDEV_RULE"
fi
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger /dev/uinput 2>/dev/null || true

# Per-user setup for all logged-in users
for uid in \$(loginctl list-sessions --no-legend 2>/dev/null | awk '{print \$2}' | sort -u); do
    user=\$(id -nu "\$uid" 2>/dev/null) || continue
    [ "\$user" = "root" ] && continue
    [ -d "/run/user/\$uid" ] || continue
    _run="sudo -u \$user XDG_RUNTIME_DIR=/run/user/\$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/\$uid/bus"

    # Add user to input group if needed
    if ! id -nG "\$user" | grep -qw input; then
        usermod -aG input "\$user"
    fi

    # Start and enable Docker daemon if installed
    if command -v docker >/dev/null 2>&1; then
        if ! systemctl is-active --quiet docker 2>/dev/null; then
            systemctl start docker 2>/dev/null || true
            systemctl enable docker 2>/dev/null || true
        fi
        if ! id -nG "\$user" | grep -qw docker; then
            usermod -aG docker "\$user"
        fi
    fi

    # Install plasmoid if KDE Plasma 6 is available
    if command -v kpackagetool6 >/dev/null 2>&1 && [ -f /usr/share/dictee/dictee.plasmoid ]; then
        sudo -u "\$user" kpackagetool6 -t Plasma/Applet -u /usr/share/dictee/dictee.plasmoid 2>/dev/null || \
        sudo -u "\$user" kpackagetool6 -t Plasma/Applet -i /usr/share/dictee/dictee.plasmoid 2>/dev/null || true
    fi

    # Enable GNOME AppIndicator extension for tray icon
    \$_run gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || true

    # Refresh icon cache (needed on GNOME)
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true
    fi

    # Reload and enable systemd user services
    \$_run systemctl --user daemon-reload 2>/dev/null || true
    \$_run systemctl --user enable dotoold dictee-ptt dictee-tray 2>/dev/null || true
    \$_run systemctl --user preset dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
    \$_run systemctl --user restart dotoold 2>/dev/null || true
    \$_run systemctl --user restart dictee-ptt 2>/dev/null || true
    # Only restart tray if user has a config (avoid starting unconfigured tray)
    _user_home=\$(getent passwd "\$user" | cut -d: -f6)
    if [ -f "\$_user_home/.config/dictee.conf" ]; then
        \$_run systemctl --user restart dictee-tray 2>/dev/null || true
    fi
    # Start the correct ASR daemon based on user config
    _asr_backend="parakeet"
    if [ -f "\$_user_home/.config/dictee.conf" ]; then
        _asr_backend=\$(grep -s '^DICTEE_ASR_BACKEND=' "\$_user_home/.config/dictee.conf" | cut -d= -f2)
    fi
    case "\$_asr_backend" in
        vosk)    _asr_svc="dictee-vosk" ;;
        whisper) _asr_svc="dictee-whisper" ;;
        canary)  _asr_svc="dictee-canary" ;;
        *)       _asr_svc="dictee" ;;
    esac
    \$_run systemctl --user stop dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
    \$_run systemctl --user disable dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
    \$_run systemctl --user enable "\$_asr_svc" 2>/dev/null || true
    \$_run systemctl --user start "\$_asr_svc" 2>/dev/null || true
done

# Create Python venv for text2num (number conversion)
PP_VENV="/usr/share/dictee/postprocess-env"
if command -v python3 >/dev/null 2>&1; then
    if [ ! -d "\$PP_VENV" ]; then
        if python3 -m venv "\$PP_VENV" 2>/dev/null; then
            "\$PP_VENV/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
            "\$PP_VENV/bin/pip" install --quiet text2num 2>/dev/null || true
        fi
    else
        "\$PP_VENV/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
        "\$PP_VENV/bin/pip" install --quiet --upgrade text2num 2>/dev/null || true
    fi
fi

%postun
if [ "\$1" -eq 0 ]; then
    rm -rf /usr/share/dictee/postprocess-env
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger /dev/uinput 2>/dev/null || true
    for uid in \$(loginctl list-sessions --no-legend 2>/dev/null | awk '{print \$2}' | sort -u); do
        user=\$(id -nu "\$uid" 2>/dev/null) || continue
        [ "\$user" = "root" ] && continue
        [ -d "/run/user/\$uid" ] || continue
        _run="sudo -u \$user XDG_RUNTIME_DIR=/run/user/\$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/\$uid/bus"
        \$_run systemctl --user stop dictee-ptt dictee-tray dotoold dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
        \$_run systemctl --user disable dictee-ptt dictee-tray dotoold dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
        \$_run systemctl --user daemon-reload 2>/dev/null || true
    done
    for lang in fr de es it uk pt; do
        rm -f "/usr/share/locale/\$lang/LC_MESSAGES/dictee.mo"
    done
fi
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

    # Plasmoid — installer directement dans le répertoire KDE
    local plasmoid_dir="$buildroot/usr/share/plasma/plasmoids/com.github.rcspam.dictee"
    mkdir -p "$plasmoid_dir"
    cp -r plasmoid/package/* "$plasmoid_dir/"

    # Locales plasmoid (FHS standard)
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
Recommends:     python3-numpy
Recommends:     pulseaudio-utils

%description
A native KDE Plasma 6 widget for dictee voice dictation.
Displays real-time audio visualization during recording, daemon status,
and provides quick controls (dictate, translate, cancel).

Five animation styles with configurable sensitivity and color gradients.

%files
/usr/share/plasma/plasmoids/com.github.rcspam.dictee/
/usr/share/locale/*/LC_MESSAGES/*.mo

%postun
if [ "\$1" -eq 0 ]; then
    rm -rf /usr/share/plasma/plasmoids/com.github.rcspam.dictee 2>/dev/null || true
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
