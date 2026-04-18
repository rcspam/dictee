#!/bin/bash
# uninstall-online.sh — One-shot uninstaller for dictee
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/uninstall-online.sh | bash
#   curl -fsSL ... | bash -s -- --purge
#   curl -fsSL ... | bash -s -- --non-interactive

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
    cat <<EOF
dictee online uninstaller

Usage:
  curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/uninstall-online.sh | bash [-- options]

Options:
  --purge             Also remove user configs (~/.config/dictee) and models
  --keep-models       Do not prompt about models (keep them)
  --non-interactive   No prompts; keep user data (equivalent to default 'no')
  --help              Show this help

This uninstaller auto-detects how dictee was installed (deb/rpm/pacman/tarball)
and uses the right tool to remove it. User data is preserved unless --purge.
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

need() { command -v "$1" >/dev/null 2>&1 || die "Missing required tool: $1"; }
need sudo

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
        if dpkg -s "$pkg" >/dev/null 2>&1; then
            DEB_PACKAGES="$DEB_PACKAGES $pkg"
        fi
    done
fi

if command -v rpm >/dev/null 2>&1; then
    for pkg in dictee-cuda dictee-cpu dictee-plasmoid; do
        if rpm -q "$pkg" >/dev/null 2>&1; then
            RPM_PACKAGES="$RPM_PACKAGES $pkg"
        fi
    done
fi

if command -v pacman >/dev/null 2>&1; then
    for pkg in dictee dictee-cpu dictee-cuda dictee-plasmoid; do
        if pacman -Q "$pkg" >/dev/null 2>&1; then
            PACMAN_PACKAGES="$PACMAN_PACKAGES $pkg"
        fi
    done
fi

# Tarball install → check /usr/local/bin for known binaries
if [[ -x /usr/local/bin/dictee ]] || [[ -x /usr/local/bin/dictee-setup ]]; then
    TARBALL_INSTALL=1
fi

DEB_PACKAGES="${DEB_PACKAGES# }"
RPM_PACKAGES="${RPM_PACKAGES# }"
PACMAN_PACKAGES="${PACMAN_PACKAGES# }"

if [[ -z "$DEB_PACKAGES" ]] && [[ -z "$RPM_PACKAGES" ]] && [[ -z "$PACMAN_PACKAGES" ]] && [[ $TARBALL_INSTALL -eq 0 ]]; then
    warn "No dictee install detected (no deb/rpm/pacman package, no tarball binaries in /usr/local/bin)."
    if [[ $PURGE -eq 0 ]]; then
        die "Nothing to do. Run with --purge to still clean user data (~/.config/dictee, models)."
    fi
fi

# ---- Confirm ----
echo
if [[ -n "$DEB_PACKAGES" ]]; then
    info "Found .deb install : ${C_BOLD}${DEB_PACKAGES}${C_OFF}"
fi
if [[ -n "$RPM_PACKAGES" ]]; then
    info "Found .rpm install : ${C_BOLD}${RPM_PACKAGES}${C_OFF}"
fi
if [[ -n "$PACMAN_PACKAGES" ]]; then
    info "Found Arch install: ${C_BOLD}${PACMAN_PACKAGES}${C_OFF}"
fi
if [[ $TARBALL_INSTALL -eq 1 ]]; then
    info "Found tarball install in ${C_BOLD}/usr/local${C_OFF}"
fi

if [[ $PURGE -eq 1 ]]; then
    warn "Purge mode ON — will also delete ~/.config/dictee and ONNX models"
fi

echo
ask_yes_no "Proceed with uninstall?" "y"
[[ "$REPLY" == "y" ]] || { info "Aborted."; exit 0; }

# ---- Stop user services ----
REAL_USER="${SUDO_USER:-$USER}"

stop_services() {
    info "Stopping user services..."
    for svc in dictee dictee-tray dictee-ptt dotoold dictee-vosk dictee-whisper dictee-canary; do
        systemctl --user stop "$svc" 2>/dev/null || true
        systemctl --user disable "$svc" 2>/dev/null || true
    done
}

# Services run as the user, not root → run outside sudo
stop_services

# ---- Remove packages ----
if [[ -n "$DEB_PACKAGES" ]]; then
    info "Removing .deb packages..."
    # shellcheck disable=SC2086
    sudo apt-get remove --purge -y $DEB_PACKAGES || warn "apt remove reported errors (continuing)"
    sudo apt-get autoremove -y || true
fi

if [[ -n "$RPM_PACKAGES" ]]; then
    info "Removing .rpm packages..."
    if command -v dnf >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        sudo dnf remove -y $RPM_PACKAGES || warn "dnf remove reported errors (continuing)"
    elif command -v zypper >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        sudo zypper --non-interactive remove $RPM_PACKAGES || warn "zypper remove reported errors (continuing)"
    fi
fi

if [[ -n "$PACMAN_PACKAGES" ]]; then
    info "Removing Arch packages..."
    # shellcheck disable=SC2086
    sudo pacman -Rns --noconfirm $PACMAN_PACKAGES || warn "pacman -Rns reported errors (continuing)"
fi

# ---- Tarball uninstall ----
if [[ $TARBALL_INSTALL -eq 1 ]]; then
    info "Running tarball uninstaller..."
    if [[ -x /usr/local/share/dictee/uninstall.sh ]]; then
        sudo /usr/local/share/dictee/uninstall.sh || warn "tarball uninstall reported errors"
    else
        # Fallback: fetch the remote uninstall.sh
        tmp=$(mktemp)
        trap 'rm -f "$tmp"' EXIT
        if curl -fsSL "https://raw.githubusercontent.com/rcspam/dictee/master/uninstall.sh" -o "$tmp"; then
            sudo bash "$tmp" || warn "remote uninstall.sh reported errors"
        else
            warn "Cannot fetch uninstall.sh — remove /usr/local/bin/dictee-* binaries manually"
        fi
    fi
fi

# ---- Purge user data ----
if [[ $PURGE -eq 1 ]]; then
    info "Purging user data..."
    REAL_HOME=$(eval echo "~$REAL_USER")
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
