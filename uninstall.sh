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
for svc in dictee dictee-tray dictee-ptt dotoold dictee-vosk dictee-whisper dictee-canary; do
    su "$REAL_USER" -c "systemctl --user stop $svc 2>/dev/null || true"
    su "$REAL_USER" -c "systemctl --user disable $svc 2>/dev/null || true"
done

# Binaires
echo "→ Suppression des binaires"
for bin in transcribe transcribe-daemon transcribe-client transcribe-diarize \
           transcribe-stream-diarize dictee dictee-setup dictee-tray dictee-ptt dictee-postprocess \
           dictee-ptt dotool dotoold transcribe-daemon-vosk transcribe-daemon-whisper; do
    rm -f "$PREFIX/bin/$bin"
done

# Udev rules
echo "→ Suppression des règles udev"
rm -f "/etc/udev/rules.d/80-dotool.rules"
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger /dev/uinput 2>/dev/null || true

# Man pages
echo "→ Suppression des pages de manuel"
for man in transcribe transcribe-daemon transcribe-client transcribe-diarize \
           transcribe-stream-diarize dictee dictee-setup dictee-tray; do
    rm -f "$PREFIX/share/man/man1/$man.1"
    rm -f "$PREFIX/share/man/fr/man1/$man.1"
done

# Desktop entry
echo "→ Suppression du fichier .desktop"
rm -f "$PREFIX/share/applications/dictee-setup.desktop"
rm -f "$PREFIX/share/applications/dictee-tray.desktop"

# Services systemd
echo "→ Suppression des services systemd"
for svc in dictee dictee-tray dictee-ptt dotoold dictee-vosk dictee-whisper dictee-canary; do
    rm -f "$REAL_HOME/.config/systemd/user/$svc.service"
done
su "$REAL_USER" -c "systemctl --user daemon-reload 2>/dev/null || true"

# Locales
echo "→ Suppression des traductions"
for lang in fr de es it uk pt; do
    rm -f "/usr/share/locale/$lang/LC_MESSAGES/dictee.mo"
    rm -f "$PREFIX/share/locale/$lang/LC_MESSAGES/dictee.mo"
done

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
