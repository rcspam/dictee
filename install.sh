#!/bin/bash
# install.sh — Dictée installation script for Fedora/Nobara and other non-Debian distros
# Usage: sudo ./install.sh
set -e

# Configuration
PREFIX="/usr/local"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
MAN_DIR="$PREFIX/share/man/man1"
MODEL_DIR="/usr/share/dictee"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Ensure the script is run with root privileges
if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run with sudo:"
    echo "  sudo ./install.sh"
    exit 1
fi

# Detect the real user (who called sudo)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")

# Update paths based on the real user's home
SYSTEMD_USER_DIR="$REAL_HOME/.config/systemd/user"
ICON_DIR="$REAL_HOME/.local/share/icons/hicolor/scalable/apps"

echo "=== Starting Dictée Installation ==="
echo ""

# 1. Install Rust Binaries (if compiled)
echo "→ Installing Rust binaries to $PREFIX/bin/"
RUST_BINARIES=("transcribe" "transcribe-daemon" "transcribe-client" "transcribe-diarize" "transcribe-stream-diarize")

for bin in "${RUST_BINARIES[@]}"; do
    if [ -f "$SCRIPT_DIR/target/release/$bin" ]; then
        install -Dm755 "$SCRIPT_DIR/target/release/$bin" "$PREFIX/bin/$bin"
        echo "  [OK] $bin installed"
    else
        echo "  [SKIP] $bin not found in target/release/. (Did you run 'cargo build --release'?)"
    fi
done

# 2. Install Scripts and Python UI (from pkg/ directory)
echo "→ Installing scripts and UI tools to $PREFIX/bin/"
SCRIPTS=("dictee" "dictee-setup" "dictee-tray" "dotool" "dotoold")

for script in "${SCRIPTS[@]}"; do
    if [ -f "$SCRIPT_DIR/pkg/dictee/usr/bin/$script" ]; then
        install -Dm755 "$SCRIPT_DIR/pkg/dictee/usr/bin/$script" "$PREFIX/bin/$script"
        echo "  [OK] $script installed"
    else
        echo "  [ERROR] $script not found in pkg/dictee/usr/bin/"
        exit 1
    fi
done

# 3. Udev Rules (needed for dotool to work without root)
echo "→ Installing udev rules"
install -Dm644 "$SCRIPT_DIR/pkg/dictee/etc/udev/rules.d/80-dotool.rules" "/etc/udev/rules.d/80-dotool.rules"
udevadm control --reload-rules 2>/dev/null || true
echo "  [OK] udev rules updated"

# 4. Man Pages
echo "→ Installing man pages"
mkdir -p "$MAN_DIR"
if [ -d "$SCRIPT_DIR/pkg/dictee/usr/share/man/man1" ]; then
    for f in "$SCRIPT_DIR/pkg/dictee/usr/share/man/man1/"*.1; do
        [ -f "$f" ] && install -Dm644 "$f" "$MAN_DIR/$(basename "$f")"
    done
fi
# French man pages (optional)
MAN_FR_DIR="$PREFIX/share/man/fr/man1"
mkdir -p "$MAN_FR_DIR"
if [ -d "$SCRIPT_DIR/pkg/dictee/usr/share/man/fr/man1" ]; then
    for f in "$SCRIPT_DIR/pkg/dictee/usr/share/man/fr/man1/"*.1; do
        [ -f "$f" ] && install -Dm644 "$f" "$MAN_FR_DIR/$(basename "$f")"
    done
fi
echo "  [OK] man pages installed"

# 5. Localization (Gettext)
echo "→ Installing translations"
if [ -d "$SCRIPT_DIR/pkg/dictee/usr/share/locale" ]; then
    for lang_dir in "$SCRIPT_DIR/pkg/dictee/usr/share/locale/"*/LC_MESSAGES; do
        [ -d "$lang_dir" ] || continue
        lang=$(basename "$(dirname "$lang_dir")")
        install -d "$PREFIX/share/locale/$lang/LC_MESSAGES"
        for mo in "$lang_dir/"*.mo; do
            [ -f "$mo" ] && install -Dm644 "$mo" "$PREFIX/share/locale/$lang/LC_MESSAGES/$(basename "$mo")"
        done
    done
fi
echo "  [OK] translations installed"

# 6. Desktop Entry
echo "→ Installing .desktop application file"
if [ -f "$SCRIPT_DIR/pkg/dictee/usr/share/applications/dictee-setup.desktop" ]; then
    install -Dm644 "$SCRIPT_DIR/pkg/dictee/usr/share/applications/dictee-setup.desktop" "$PREFIX/share/applications/dictee-setup.desktop"
    echo "  [OK] .desktop file installed"
fi

# 7. Icons (User space)
echo "→ Installing application icons"
install -d "$ICON_DIR"
if [ -d "$SCRIPT_DIR/pkg/dictee/usr/share/icons/hicolor/scalable/apps" ]; then
    for svg in "$SCRIPT_DIR/pkg/dictee/usr/share/icons/hicolor/scalable/apps/"*.svg; do
        [ -f "$svg" ] && install -Dm644 "$svg" "$ICON_DIR/$(basename "$svg")"
    done
fi
chown -R "$REAL_USER:" "$REAL_HOME/.local/share/icons"
echo "  [OK] icons installed in $ICON_DIR"

# 8. Systemd User Services
echo "→ Installing systemd user services"
install -d "$SYSTEMD_USER_DIR"
if [ -d "$SCRIPT_DIR/pkg/dictee/usr/lib/systemd/user" ]; then
    for svc in "$SCRIPT_DIR/pkg/dictee/usr/lib/systemd/user/"*.service; do
        [ -f "$svc" ] || continue
        name="$(basename "$svc")"
        # Update paths in service files to use /usr/local/bin
        sed "s|/usr/bin/|$PREFIX/bin/|g" "$svc" > "$SYSTEMD_USER_DIR/$name"
    done
fi
chown -R "$REAL_USER:" "$SYSTEMD_USER_DIR"
echo "  [OK] systemd services installed"

# 9. Systemd User Presets
echo "→ Installing systemd user presets"
PRESET_DIR="/usr/lib/systemd/user-preset"
install -d "$PRESET_DIR"
if [ -d "$SCRIPT_DIR/pkg/dictee/usr/lib/systemd/user-preset" ]; then
    for preset in "$SCRIPT_DIR/pkg/dictee/usr/lib/systemd/user-preset/"*.preset; do
        [ -f "$preset" ] && install -Dm644 "$preset" "$PRESET_DIR/$(basename "$preset")"
    done
fi
echo "  [OK] systemd presets installed"

# 10. ASR Models (TDT)
echo "→ Checking ASR models in $MODEL_DIR/tdt"
mkdir -p "$MODEL_DIR/tdt"
TDT_FILES=("encoder-model.onnx" "encoder-model.onnx.data" "decoder_joint-model.onnx" "vocab.txt")
TDT_BASE_URL="https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main"

for file in "${TDT_FILES[@]}"; do
    if [ ! -f "$MODEL_DIR/tdt/$file" ]; then
        echo "  [MISSING] $file - Downloading (this may take a few minutes, approx. 2.5 GB total)..."
        curl -L -# -o "$MODEL_DIR/tdt/$file" "$TDT_BASE_URL/$file"
    else
        echo "  [OK] $file already exists"
    fi
done

# 11. Finalizing
echo "→ Reloading systemd user daemon"
REAL_UID=$(id -u "$REAL_USER")
if [ -d "/run/user/$REAL_UID" ]; then
    sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$REAL_UID" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$REAL_UID/bus" \
        systemctl --user daemon-reload 2>/dev/null || true
fi

echo ""
echo "=== Installation Successful ==="
echo ""
echo "Configuration Notes:"
echo "1. Run 'dictee --setup' to configure your language and shortcut."
echo "2. IMPORTANT: To support special characters (like 'ç'), make sure"
echo "   'Copy transcription to clipboard' is ENABLED in the setup."
echo "3. The tool now uses 'Shift+Insert' for better terminal compatibility."
echo ""
echo "To uninstall, run: sudo ./uninstall.sh"
echo ""
