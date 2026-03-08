#!/bin/bash
# install.sh — Installation de dictee pour distributions non-Debian
# Usage : sudo ./install.sh
set -e

PREFIX="/usr/local"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
MAN_DIR="$PREFIX/share/man/man1"
MODEL_DIR="/usr/share/dictee"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Vérifier les droits root pour /usr/local
if [ "$(id -u)" -ne 0 ]; then
    echo "Ce script doit être lancé avec sudo :"
    echo "  sudo ./install.sh"
    exit 1
fi

# Récupérer l'utilisateur réel (pas root)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")

SYSTEMD_USER_DIR="$REAL_HOME/.config/systemd/user"
ICON_DIR="$REAL_HOME/.local/share/icons/hicolor/scalable/apps"

echo "=== Installation de dictee ==="
echo ""

# Binaires
echo "→ Installation des binaires dans $PREFIX/bin/"
install -Dm755 "$SCRIPT_DIR/usr/bin/transcribe" "$PREFIX/bin/transcribe"
install -Dm755 "$SCRIPT_DIR/usr/bin/transcribe-daemon" "$PREFIX/bin/transcribe-daemon"
install -Dm755 "$SCRIPT_DIR/usr/bin/transcribe-client" "$PREFIX/bin/transcribe-client"
install -Dm755 "$SCRIPT_DIR/usr/bin/transcribe-diarize" "$PREFIX/bin/transcribe-diarize"
install -Dm755 "$SCRIPT_DIR/usr/bin/transcribe-stream-diarize" "$PREFIX/bin/transcribe-stream-diarize"
install -Dm755 "$SCRIPT_DIR/usr/bin/dictee" "$PREFIX/bin/dictee"
install -Dm755 "$SCRIPT_DIR/usr/bin/dictee-setup" "$PREFIX/bin/dictee-setup"
install -Dm755 "$SCRIPT_DIR/usr/bin/dictee-tray" "$PREFIX/bin/dictee-tray"

# Man pages
echo "→ Installation des pages de manuel"
mkdir -p "$MAN_DIR"
for f in "$SCRIPT_DIR/usr/share/man/man1/"*.1; do
    [ -f "$f" ] && install -Dm644 "$f" "$MAN_DIR/$(basename "$f")"
done
# Man pages FR
MAN_FR_DIR="$PREFIX/share/man/fr/man1"
mkdir -p "$MAN_FR_DIR"
for f in "$SCRIPT_DIR/usr/share/man/fr/man1/"*.1; do
    [ -f "$f" ] && install -Dm644 "$f" "$MAN_FR_DIR/$(basename "$f")"
done

# Icônes (dans le home de l'utilisateur réel)
echo "→ Installation des icônes"
install -d "$ICON_DIR"
for svg in "$SCRIPT_DIR/usr/share/icons/hicolor/scalable/apps/"*.svg; do
    [ -f "$svg" ] && install -Dm644 "$svg" "$ICON_DIR/$(basename "$svg")"
done
chown -R "$REAL_USER:" "$REAL_HOME/.local/share/icons"

# Services systemd (dans le home de l'utilisateur réel)
echo "→ Installation des services systemd"
install -d "$SYSTEMD_USER_DIR"
# Adapter les chemins pour /usr/local/bin
for svc in "$SCRIPT_DIR/usr/lib/systemd/user/"*.service; do
    [ -f "$svc" ] || continue
    name="$(basename "$svc")"
    sed "s|/usr/bin/|$PREFIX/bin/|g" "$svc" > "$SYSTEMD_USER_DIR/$name"
done
chown -R "$REAL_USER:" "$SYSTEMD_USER_DIR"

# Preset systemd (auto-enable au login)
echo "→ Installation du preset systemd"
PRESET_DIR="/usr/lib/systemd/user-preset"
install -d "$PRESET_DIR"
for preset in "$SCRIPT_DIR/usr/lib/systemd/user-preset/"*.preset; do
    [ -f "$preset" ] && install -Dm644 "$preset" "$PRESET_DIR/$(basename "$preset")"
done

# Répertoire des modèles
echo "→ Création du répertoire des modèles"
mkdir -p "$MODEL_DIR"

# Activer et démarrer le service pour l'utilisateur
echo "→ Activation du service dictee"
REAL_UID=$(id -u "$REAL_USER")
if [ -d "/run/user/$REAL_UID" ]; then
    sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$REAL_UID" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$REAL_UID/bus" \
        systemctl --user daemon-reload 2>/dev/null || true
    sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$REAL_UID" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$REAL_UID/bus" \
        systemctl --user enable --now dictee 2>/dev/null || true
fi

echo ""
echo "=== Installation terminée ==="
echo ""
echo "Le service dictee est activé et démarré."
echo "Il se relancera automatiquement à chaque connexion."
echo ""
echo "Pour configurer le raccourci clavier et la traduction :"
echo "  dictee --setup"
echo ""
echo "Pour désinstaller :"
echo "  sudo ./uninstall.sh"
echo ""
