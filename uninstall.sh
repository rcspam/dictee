#!/bin/bash
# uninstall.sh — dictee uninstaller (universal)
#
# Auto-detects how dictee was installed (deb/rpm/pacman/tarball) and removes
# each layer. User data (configs, models) is preserved unless --purge.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/uninstall.sh | bash
#   sudo ./uninstall.sh               # local invocation
#   sudo ./uninstall.sh --purge       # also remove configs + models
#   sudo ./uninstall.sh --keep-models # skip the model prompt

set -euo pipefail

PURGE=0
NON_INTERACTIVE=0
KEEP_MODELS=0

# ---- Colors ----
if [[ -t 1 ]]; then
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
    C_BLUE=$'\033[34m'; C_BOLD=$'\033[1m'; C_OFF=$'\033[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_OFF=""
fi
info() { echo "${C_BLUE}▶${C_OFF} $*"; }
ok()   { echo "${C_GREEN}✓${C_OFF} $*"; }
warn() { echo "${C_YELLOW}⚠${C_OFF} $*"; }
err()  { echo "${C_RED}✗${C_OFF} $*" >&2; }
die()  { err "$@"; exit 1; }

usage() {
    cat <<'EOF'
dictee uninstaller (universal)

Usage:
  curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/uninstall.sh | bash
  sudo ./uninstall.sh [-- options]

Options:
  --purge             Also remove user configs (~/.config/dictee) and models
  --keep-models       Do not prompt about models (keep them)
  --non-interactive   No prompts; keep user data (same as declining all prompts)
  --help, -h          Show this help

Detects .deb / .rpm / pacman / tarball installs and removes each layer.
User data is preserved unless --purge.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --purge)           PURGE=1; shift ;;
        --keep-models)     KEEP_MODELS=1; shift ;;
        --non-interactive) NON_INTERACTIVE=1; shift ;;
        --help|-h)         usage; exit 0 ;;
        *)                 die "Unknown option: $1 (run with --help)" ;;
    esac
done

command -v sudo >/dev/null 2>&1 || die "sudo is required"

ask_yes_no() {
    # ask_yes_no "question" default(y|n) -> sets REPLY to y or n
    local question="$1" default="$2"
    if [[ $NON_INTERACTIVE -eq 1 ]]; then
        REPLY="$default"
        return
    fi
    local prompt
    if [[ "$default" == "y" ]]; then
        prompt="[Y/n]"
    else
        prompt="[y/N]"
    fi
    read -rp "$question $prompt " REPLY < /dev/tty || REPLY="$default"
    REPLY="${REPLY:-$default}"
    case "$REPLY" in
        [Yy]*) REPLY="y" ;;
        *)     REPLY="n" ;;
    esac
}

# ---- Detect install method ----
DEB_PACKAGES=""
RPM_PACKAGES=""
PACMAN_PACKAGES=""
TARBALL_INSTALL=0

if command -v dpkg >/dev/null 2>&1; then
    for pkg in dictee-cuda dictee-cpu dictee-plasmoid; do
        dpkg -s "$pkg" >/dev/null 2>&1 && DEB_PACKAGES="$DEB_PACKAGES $pkg"
    done
fi

if command -v rpm >/dev/null 2>&1; then
    for pkg in dictee-cuda dictee-cpu dictee-plasmoid; do
        rpm -q "$pkg" >/dev/null 2>&1 && RPM_PACKAGES="$RPM_PACKAGES $pkg"
    done
fi

if command -v pacman >/dev/null 2>&1; then
    for pkg in dictee dictee-cpu dictee-cuda dictee-plasmoid; do
        pacman -Q "$pkg" >/dev/null 2>&1 && PACMAN_PACKAGES="$PACMAN_PACKAGES $pkg"
    done
fi

# Tarball install → binaries present in /usr/local/bin
if [[ -x /usr/local/bin/dictee ]] || [[ -x /usr/local/bin/dictee-setup ]]; then
    TARBALL_INSTALL=1
fi

DEB_PACKAGES="${DEB_PACKAGES# }"
RPM_PACKAGES="${RPM_PACKAGES# }"
PACMAN_PACKAGES="${PACMAN_PACKAGES# }"

if [[ -z "$DEB_PACKAGES$RPM_PACKAGES$PACMAN_PACKAGES" ]] && [[ $TARBALL_INSTALL -eq 0 ]]; then
    warn "No dictee install detected."
    if [[ $PURGE -eq 0 ]]; then
        die "Nothing to do. Run with --purge to still clean user data."
    fi
fi

# ---- Confirm ----
echo
[[ -n "$DEB_PACKAGES"    ]] && info "Found .deb install : ${C_BOLD}${DEB_PACKAGES}${C_OFF}"
[[ -n "$RPM_PACKAGES"    ]] && info "Found .rpm install : ${C_BOLD}${RPM_PACKAGES}${C_OFF}"
[[ -n "$PACMAN_PACKAGES" ]] && info "Found Arch install : ${C_BOLD}${PACMAN_PACKAGES}${C_OFF}"
[[ $TARBALL_INSTALL -eq 1 ]] && info "Found tarball install in ${C_BOLD}/usr/local${C_OFF}"
[[ $PURGE -eq 1          ]] && warn "Purge mode ON — will also delete ~/.config/dictee and models"

echo
ask_yes_no "Proceed with uninstall?" "y"
[[ "$REPLY" == "y" ]] || { info "Aborted."; exit 0; }

# ---- Stop user services (run as the user, not root) ----
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")

info "Stopping user services..."
for svc in dictee dictee-tray dictee-ptt dotoold dictee-vosk dictee-whisper dictee-canary; do
    if [[ -n "${SUDO_USER:-}" ]]; then
        su "$REAL_USER" -c "systemctl --user stop $svc 2>/dev/null || true"
        su "$REAL_USER" -c "systemctl --user disable $svc 2>/dev/null || true"
    else
        systemctl --user stop "$svc" 2>/dev/null || true
        systemctl --user disable "$svc" 2>/dev/null || true
    fi
done

# ---- Remove distro packages ----
if [[ -n "$DEB_PACKAGES" ]]; then
    info "Removing .deb packages..."
    # shellcheck disable=SC2086
    sudo apt-get remove --purge -y $DEB_PACKAGES || warn "apt-get remove reported errors"
    sudo apt-get autoremove -y || true
fi

if [[ -n "$RPM_PACKAGES" ]]; then
    info "Removing .rpm packages..."
    if command -v dnf >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        sudo dnf remove -y $RPM_PACKAGES || warn "dnf remove reported errors"
    elif command -v zypper >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        sudo zypper --non-interactive remove $RPM_PACKAGES || warn "zypper remove reported errors"
    fi
fi

if [[ -n "$PACMAN_PACKAGES" ]]; then
    info "Removing Arch packages..."
    # shellcheck disable=SC2086
    sudo pacman -Rns --noconfirm $PACMAN_PACKAGES || warn "pacman -Rns reported errors"
fi

# ---- Tarball cleanup (inline, no remote fetch) ----
if [[ $TARBALL_INSTALL -eq 1 ]]; then
    info "Removing tarball install from /usr/local/..."
    PREFIX="/usr/local"

    # Binaries
    for bin in transcribe transcribe-daemon transcribe-client transcribe-diarize \
               transcribe-stream-diarize dictee dictee-setup dictee-tray dictee-ptt \
               dictee-postprocess dictee-switch-backend dictee-test-rules \
               dictee-transcribe dictee-reset dictee-translate-langs dictee-audio-sources \
               transcribe-daemon-vosk transcribe-daemon-whisper \
               dictee-plasmoid-level dictee-plasmoid-level-daemon dictee-plasmoid-level-fft \
               dotool dotoold; do
        sudo rm -f "$PREFIX/bin/$bin"
    done

    # udev rule
    sudo rm -f /etc/udev/rules.d/80-dotool.rules
    sudo udevadm control --reload-rules 2>/dev/null || true
    sudo udevadm trigger /dev/uinput 2>/dev/null || true

    # Man pages
    for m in transcribe transcribe-daemon transcribe-client transcribe-diarize \
             transcribe-stream-diarize dictee dictee-setup dictee-tray \
             dictee-switch-backend dictee-test-rules dictee-postprocess; do
        sudo rm -f "$PREFIX/share/man/man1/$m.1" "$PREFIX/share/man/fr/man1/$m.1"
    done

    # .desktop entries
    sudo rm -f "$PREFIX/share/applications/dictee-setup.desktop" \
               "$PREFIX/share/applications/dictee-tray.desktop"

    # systemd user units
    for svc in dictee dictee-tray dictee-ptt dotoold dictee-vosk dictee-whisper dictee-canary; do
        rm -f "$REAL_HOME/.config/systemd/user/$svc.service"
    done
    [[ -n "${SUDO_USER:-}" ]] && su "$REAL_USER" -c "systemctl --user daemon-reload 2>/dev/null || true"

    # systemd preset
    sudo rm -f /usr/lib/systemd/user-preset/90-dictee.preset

    # CUDA libs + ld.so.conf.d
    if [[ -d /usr/lib/dictee ]]; then
        sudo rm -rf /usr/lib/dictee
        sudo rm -f /etc/ld.so.conf.d/dictee.conf
        sudo ldconfig 2>/dev/null || true
    fi

    # Locales
    for lang in fr de es it uk pt; do
        sudo rm -f "/usr/share/locale/$lang/LC_MESSAGES/dictee.mo" \
                   "$PREFIX/share/locale/$lang/LC_MESSAGES/dictee.mo"
    done

    # Icons (in user's home)
    for icon in parakeet-active parakeet-active-dark parakeet-inactive parakeet-inactive-dark \
                parakeet-offline parakeet-recording parakeet-transcribing parakeet-diarize \
                dictee dictee-setup dictee-tray; do
        rm -f "$REAL_HOME/.local/share/icons/hicolor/scalable/apps/$icon.svg"
    done
fi

# ---- Plasmoid (user install) ----
if command -v kpackagetool6 >/dev/null 2>&1; then
    info "Removing KDE Plasma widget..."
    if [[ -n "${SUDO_USER:-}" ]]; then
        su "$REAL_USER" -c "kpackagetool6 -t Plasma/Applet -r com.github.rcspam.dictee 2>/dev/null || true"
    else
        kpackagetool6 -t Plasma/Applet -r com.github.rcspam.dictee 2>/dev/null || true
    fi
fi

# ---- Purge user data ----
if [[ $PURGE -eq 1 ]]; then
    info "Purging user data..."
    rm -rf "$REAL_HOME/.config/dictee" 2>/dev/null || true
    rm -rf "$REAL_HOME/.cache/dictee" 2>/dev/null || true
    rm -rf "$REAL_HOME/.local/share/dictee" 2>/dev/null || true
    ok "User configs removed"
fi

# ---- Models prompt ----
MODEL_DIR="/usr/share/dictee"
if [[ -d "$MODEL_DIR" ]] && [[ $KEEP_MODELS -eq 0 ]]; then
    if [[ $PURGE -eq 1 ]]; then
        REPLY="y"
    else
        echo
        ask_yes_no "Also delete ONNX models in ${MODEL_DIR} (~5 GB)?" "n"
    fi
    if [[ "$REPLY" == "y" ]]; then
        sudo rm -rf "$MODEL_DIR"
        ok "Models removed"
    else
        info "Models kept at $MODEL_DIR"
    fi
fi

# ---- LibreTranslate Docker volume (optional) ----
if command -v docker >/dev/null 2>&1; then
    if docker volume ls --format '{{.Name}}' 2>/dev/null | grep -q '^libretranslate-models$'; then
        if [[ $PURGE -eq 1 ]]; then
            REPLY="y"
        else
            ask_yes_no "Remove LibreTranslate Docker volume (translation models, ~several GB)?" "n"
        fi
        if [[ "$REPLY" == "y" ]]; then
            docker volume rm libretranslate-models 2>/dev/null || warn "docker volume rm failed"
            ok "LibreTranslate volume removed"
        else
            info "LibreTranslate volume kept"
        fi
    fi
fi

echo
ok "dictee uninstalled"
echo
echo "Note: Ollama models are untouched — remove with 'ollama rm <model>' if desired."
