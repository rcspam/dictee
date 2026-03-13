#!/bin/bash
# install-fedora.sh — Installation script for Dictee on Fedora/Nobara (x86_64, CUDA version)

set -e

# --- Configuration ---
MODEL_REPO="istupakov/parakeet-tdt-0.6b-v3-onnx"
INSTALL_DIR="/usr"
DICTEE_SHARE="/usr/share/dictee"
TDT_DIR="$DICTEE_SHARE/tdt"

echo "=== Dictee Installation for Fedora/Nobara ==="

# 1. Check dependencies
echo ">> Checking dependencies..."
MISSING_DEPS=()
for dep in rsync unzip hf kpackagetool6 udevadm systemctl; do
    if ! command -v "$dep" >/dev/null 2>&1; then
        MISSING_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "Error: Missing dependencies: ${MISSING_DEPS[*]}"
    echo "Please install them first (e.g., 'sudo dnf install rsync unzip' and ensure 'hf' (huggingface-cli) is installed)."
    exit 1
fi

# 2. Copy files to system
echo ">> Copying files to $INSTALL_DIR..."
sudo rsync -av usr/ /usr/
sudo rsync -av etc/ /etc/

# 3. Reload udev rules
echo ">> Reloading udev rules..."
sudo udevadm control --reload-rules
sudo udevadm trigger

# 4. Reload systemd user services
echo ">> Reloading systemd user daemon..."
systemctl --user daemon-reload

# 5. Install/Update Plasma 6 widget
echo ">> Installing/Updating Plasma 6 widget..."
PLASMOID_PATH="$DICTEE_SHARE/dictee.plasmoid"
if [ -f "$PLASMOID_PATH" ]; then
    if kpackagetool6 -t Plasma/Applet -l | grep -q "com.github.rcspam.dictee"; then
        echo "Updating existing plasmoid..."
        kpackagetool6 -t Plasma/Applet -u "$PLASMOID_PATH"
    else
        echo "Installing new plasmoid..."
        kpackagetool6 -t Plasma/Applet -i "$PLASMOID_PATH"
    fi
else
    echo "Warning: $PLASMOID_PATH not found, skipping widget installation."
fi

# 6. Download ONNX models
echo ">> Downloading ONNX models from Hugging Face ($MODEL_REPO)..."
sudo mkdir -p "$TDT_DIR"
# Ensure the directory is clean for a fresh download
sudo rm -rf "${TDT_DIR:?}"/*
sudo hf download "$MODEL_REPO" --local-dir "$TDT_DIR"

echo "=== Installation Complete! ==="
echo "To start the transcription service, run:"
echo "  systemctl --user enable --now dictee"
echo ""
echo "To start the tray icon, run:"
echo "  systemctl --user enable --now dictee-tray"
echo ""
echo "Note: The model consumes around 4GB of RAM and requires a CUDA-capable GPU (or a fast CPU)."
