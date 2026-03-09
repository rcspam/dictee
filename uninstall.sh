#!/bin/bash
# uninstall.sh — Désinstallation de dictee
# Usage : sudo ./uninstall.sh
set -e

PREFIX="/usr/local"
MODEL_DIR="/usr/share/dictee"

if [ "$(id -u)" -ne 0 ]; then
    echo "Ce script doit être lancé avec sudo :"
    echo "  sudo ./uninstall.sh"
    exit 1
fi

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")

echo "=== Désinstallation de dictee ==="
echo ""

# Arrêter les services
echo "→ Arrêt des services"
su "$REAL_USER" -c "systemctl --user stop dictee 2>/dev/null || true"
su "$REAL_USER" -c "systemctl --user stop dictee-tray 2>/dev/null || true"
su "$REAL_USER" -c "systemctl --user disable dictee 2>/dev/null || true"
su "$REAL_USER" -c "systemctl --user disable dictee-tray 2>/dev/null || true"

# Binaires
echo "→ Suppression des binaires"
for bin in transcribe transcribe-daemon transcribe-client transcribe-diarize \
           transcribe-stream-diarize dictee dictee-setup dictee-tray dotool dotoold; do
    rm -f "$PREFIX/bin/$bin"
done

# Udev rules
echo "→ Suppression des règles udev"
rm -f "/etc/udev/rules.d/80-dotool.rules"

# Man pages
echo "→ Suppression des pages de manuel"
for man in transcribe transcribe-daemon transcribe-client transcribe-diarize \
           transcribe-stream-diarize dictee dictee-setup dictee-tray; do
    rm -f "$PREFIX/share/man/man1/$man.1"
    rm -f "$PREFIX/share/man/fr/man1/$man.1"
done

# Services systemd
echo "→ Suppression des services systemd"
rm -f "$REAL_HOME/.config/systemd/user/dictee.service"
rm -f "$REAL_HOME/.config/systemd/user/dictee-tray.service"
su "$REAL_USER" -c "systemctl --user daemon-reload 2>/dev/null || true"

# Icônes
echo "→ Suppression des icônes"
for icon in parakeet-active parakeet-active-dark parakeet-inactive parakeet-inactive-dark; do
    rm -f "$REAL_HOME/.local/share/icons/hicolor/scalable/apps/$icon.svg"
done

# Modèles (demander confirmation)
if [ -d "$MODEL_DIR" ]; then
    echo ""
    read -p "Supprimer les modèles ONNX ($MODEL_DIR, ~5 Go) ? [o/N] " reply
    if [ "$reply" = "o" ] || [ "$reply" = "O" ]; then
        rm -rf "$MODEL_DIR"
        echo "  Modèles supprimés."
    else
        echo "  Modèles conservés."
    fi
fi

echo ""
echo "=== Désinstallation terminée ==="
echo ""
