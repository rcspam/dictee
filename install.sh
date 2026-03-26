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
install -Dm755 "$SCRIPT_DIR/usr/bin/dictee-ptt" "$PREFIX/bin/dictee-ptt"
install -Dm755 "$SCRIPT_DIR/usr/bin/dictee-postprocess" "$PREFIX/bin/dictee-postprocess"
install -Dm755 "$SCRIPT_DIR/usr/bin/dictee-switch-backend" "$PREFIX/bin/dictee-switch-backend"
install -Dm755 "$SCRIPT_DIR/usr/bin/dictee-test-rules" "$PREFIX/bin/dictee-test-rules"
install -Dm755 "$SCRIPT_DIR/usr/bin/transcribe-daemon-canary" "$PREFIX/bin/transcribe-daemon-canary"
install -Dm755 "$SCRIPT_DIR/usr/bin/transcribe-daemon-vosk" "$PREFIX/bin/transcribe-daemon-vosk"
install -Dm755 "$SCRIPT_DIR/usr/bin/transcribe-daemon-whisper" "$PREFIX/bin/transcribe-daemon-whisper"
install -Dm755 "$SCRIPT_DIR/usr/bin/dictee-plasmoid-level" "$PREFIX/bin/dictee-plasmoid-level"
install -Dm755 "$SCRIPT_DIR/usr/bin/dictee-plasmoid-level-daemon" "$PREFIX/bin/dictee-plasmoid-level-daemon"
install -Dm755 "$SCRIPT_DIR/usr/bin/dictee-plasmoid-level-fft" "$PREFIX/bin/dictee-plasmoid-level-fft"
install -Dm755 "$SCRIPT_DIR/usr/bin/dotool" "$PREFIX/bin/dotool"
install -Dm755 "$SCRIPT_DIR/usr/bin/dotoold" "$PREFIX/bin/dotoold"

# ONNX Runtime CUDA libs (if present in the tarball — CUDA variant only)
if [ -d "$SCRIPT_DIR/usr/lib/dictee" ]; then
    echo "→ Installation des libs CUDA ONNX Runtime"
    install -d /usr/lib/dictee
    for lib in "$SCRIPT_DIR/usr/lib/dictee/"*.so; do
        [ -f "$lib" ] && install -Dm644 "$lib" "/usr/lib/dictee/$(basename "$lib")"
    done
    echo "/usr/lib/dictee" > /etc/ld.so.conf.d/dictee.conf
    ldconfig 2>/dev/null || true
fi

# Udev rules (dotool — accès uinput pour le groupe input)
echo "→ Installation des règles udev"
install -Dm644 "$SCRIPT_DIR/etc/udev/rules.d/80-dotool.rules" "/etc/udev/rules.d/80-dotool.rules"
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger /dev/uinput 2>/dev/null || true

# Groupe input (nécessaire pour les raccourcis clavier via dotool)
echo "→ Vérification du groupe input"
if ! id -nG "$REAL_USER" | grep -qw input; then
    usermod -aG input "$REAL_USER"
    echo "  ✓ $REAL_USER ajouté au groupe 'input' — redémarrez pour activer"
else
    echo "  ✓ $REAL_USER déjà dans le groupe 'input'"
fi
if command -v docker >/dev/null 2>&1; then
    if ! systemctl is-active --quiet docker 2>/dev/null; then
        systemctl start docker 2>/dev/null || true
        systemctl enable docker 2>/dev/null || true
        echo "  ✓ Docker démarré et activé"
    fi
    if ! id -nG "$REAL_USER" | grep -qw docker; then
        usermod -aG docker "$REAL_USER"
        echo "  ✓ $REAL_USER ajouté au groupe 'docker' (LibreTranslate)"
    else
        echo "  ✓ $REAL_USER déjà dans le groupe 'docker'"
    fi
fi

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

# Locale (gettext)
echo "→ Installation des traductions"
for lang_dir in "$SCRIPT_DIR/usr/share/locale/"*/LC_MESSAGES; do
    [ -d "$lang_dir" ] || continue
    lang=$(basename "$(dirname "$lang_dir")")
    install -d "$PREFIX/share/locale/$lang/LC_MESSAGES"
    for mo in "$lang_dir/"*.mo; do
        [ -f "$mo" ] && install -Dm644 "$mo" "$PREFIX/share/locale/$lang/LC_MESSAGES/$(basename "$mo")"
    done
done

# Desktop entry
echo "→ Installation du fichier .desktop"
install -Dm644 "$SCRIPT_DIR/usr/share/applications/dictee-setup.desktop" "$PREFIX/share/applications/dictee-setup.desktop"
install -Dm644 "$SCRIPT_DIR/usr/share/applications/dictee-tray.desktop" "$PREFIX/share/applications/dictee-tray.desktop"

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

# Assets (bannières SVG pour le wizard)
echo "→ Installation des assets"
install -d "$MODEL_DIR/assets"
for svg in "$SCRIPT_DIR/usr/share/dictee/assets/"*.svg; do
    [ -f "$svg" ] && install -Dm644 "$svg" "$MODEL_DIR/assets/$(basename "$svg")"
done
if [ -d "$SCRIPT_DIR/usr/share/dictee/assets/logos" ]; then
    install -d "$MODEL_DIR/assets/logos"
    for svg in "$SCRIPT_DIR/usr/share/dictee/assets/logos/"*.svg; do
        [ -f "$svg" ] && install -Dm644 "$svg" "$MODEL_DIR/assets/logos/$(basename "$svg")"
    done
fi

# Règles et configs de post-traitement par défaut
for conf in rules.conf.default dictionary.conf.default continuation.conf.default VERSION; do
    if [ -f "$SCRIPT_DIR/usr/share/dictee/$conf" ]; then
        install -Dm644 "$SCRIPT_DIR/usr/share/dictee/$conf" "$MODEL_DIR/$conf"
    fi
done

# Plasmoid KDE Plasma 6
if [ -f "$SCRIPT_DIR/usr/share/dictee/dictee.plasmoid" ]; then
    install -Dm644 "$SCRIPT_DIR/usr/share/dictee/dictee.plasmoid" "$MODEL_DIR/dictee.plasmoid"
    echo "→ Installation du widget KDE Plasma"
    if command -v kpackagetool6 >/dev/null 2>&1; then
        sudo -u "$REAL_USER" kpackagetool6 -t Plasma/Applet -u "$MODEL_DIR/dictee.plasmoid" 2>/dev/null || \
        sudo -u "$REAL_USER" kpackagetool6 -t Plasma/Applet -i "$MODEL_DIR/dictee.plasmoid" 2>/dev/null || true
        echo "  ✓ Widget Plasma installé"
    else
        echo "  ⚠ kpackagetool6 non trouvé — installez manuellement :"
        echo "    kpackagetool6 -t Plasma/Applet -i $MODEL_DIR/dictee.plasmoid"
    fi
fi

# Répertoire des modèles (accessible en écriture pour dictee-setup)
echo "→ Création du répertoire des modèles"
for d in "$MODEL_DIR" "$MODEL_DIR/tdt" "$MODEL_DIR/sortformer" "$MODEL_DIR/nemotron"; do
    mkdir -p "$d"
    chmod 777 "$d"
done

# Recharger et activer les services systemd
echo "→ Activation des services systemd"
REAL_UID=$(id -u "$REAL_USER")
if [ -d "/run/user/$REAL_UID" ]; then
    _run="sudo -u $REAL_USER XDG_RUNTIME_DIR=/run/user/$REAL_UID DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$REAL_UID/bus"
    $_run systemctl --user daemon-reload 2>/dev/null || true
    $_run systemctl --user preset dictee dictee-vosk dictee-whisper dictee-canary dictee-ptt dictee-tray dotoold 2>/dev/null || true
    $_run systemctl --user enable dotoold dictee-ptt dictee-tray dictee 2>/dev/null || true
    $_run systemctl --user restart dotoold 2>/dev/null || true
    echo "  ↳ dotoold démarré"
    $_run systemctl --user restart dictee-ptt 2>/dev/null || true
    echo "  ↳ dictee-ptt démarré"
    if [ -f "$REAL_HOME/.config/dictee.conf" ]; then
        $_run systemctl --user restart dictee-tray 2>/dev/null || true
        echo "  ↳ dictee-tray démarré"
    else
        echo "  ↳ dictee-tray : en attente de configuration (dictee-setup)"
    fi
    $_run systemctl --user start dictee 2>/dev/null || true
    echo "  ↳ dictee (daemon ASR) démarré"
    # Enable GNOME AppIndicator extension for tray icon
    $_run gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || true
fi

echo ""
echo "=== Installation terminée ==="
echo ""
echo "Les services seront activés automatiquement au prochain login."
echo "Pour les activer/désactiver, utilisez : dictee --setup"
echo ""
echo "Pour configurer le raccourci clavier et la traduction :"
echo "  dictee --setup"
echo ""
echo "Pour désinstaller :"
echo "  sudo ./uninstall.sh"
echo ""
