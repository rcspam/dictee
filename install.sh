#!/bin/bash
# install.sh — dictee installer (dual-mode: online + tarball)
#
# Online mode (default when piped from curl):
#   curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install.sh | bash
#   curl ... | bash -s -- --cpu
#   curl ... | bash -s -- --gpu --version 1.3.0
#   curl ... | bash -s -- --non-interactive
#
# Tarball mode (after extracting the release .tar.gz):
#   sudo ./install.sh
#
# Mode is auto-detected: if the script's directory contains a tarball
# layout (./usr/bin/dictee and ./usr/share/dictee/VERSION) we go tarball;
# otherwise online. Override with --online or --tarball.

set -euo pipefail

REPO="rcspam/dictee"
# Use /releases?per_page=1 (newest release, including prereleases) rather than
# /releases/latest which skips prereleases — needed as long as 1.3.0 ships as beta.
GITHUB_API="https://api.github.com/repos/${REPO}/releases?per_page=1"

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
need() { command -v "$1" >/dev/null 2>&1 || die "Missing required tool: $1"; }

usage() {
    cat <<'EOF'
dictee installer (dual-mode)

Online mode (downloads the right package from GitHub Releases):
  curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install.sh | bash

Tarball mode (from an extracted release .tar.gz):
  sudo ./install.sh

Options:
  --online             Force online mode
  --tarball            Force tarball mode (current directory must contain ./usr/bin/dictee)
  --cpu                Online: force CPU version
  --gpu                Online: force GPU (CUDA) version
  --version X.Y.Z      Online: install a specific version (default: latest)
  --non-interactive    Online: no prompts; auto-detect GPU
  --help, -h           Show this help

Supported distros (online mode): Ubuntu/Debian, Fedora, openSUSE, Arch Linux.
Unsupported distros fall back to the .tar.gz installer (same as tarball mode).
EOF
}

# =============================================================================
# ONLINE MODE — fetches release asset and hands it to the package manager.
# =============================================================================

mode_online() {
    local BACKEND="" NON_INTERACTIVE=0 REQUESTED_VERSION=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --cpu)             BACKEND="cpu"; shift ;;
            --gpu)             BACKEND="gpu"; shift ;;
            --version)         REQUESTED_VERSION="${2:-}"; shift 2 ;;
            --non-interactive) NON_INTERACTIVE=1; shift ;;
            *)                 die "Unknown online option: $1 (run with --help)" ;;
        esac
    done

    need curl
    need sudo

    # ---- Detect OS ----
    [[ -f /etc/os-release ]] || die "Cannot detect OS: /etc/os-release missing"
    # shellcheck disable=SC1091
    . /etc/os-release
    local DISTRO_ID="${ID:-unknown}"
    local DISTRO_LIKE="${ID_LIKE:-}"
    local DISTRO_VERSION="${VERSION_ID:-}"
    local DISTRO_ARCH; DISTRO_ARCH="$(uname -m)"

    info "Detected: ${C_BOLD}${NAME:-$DISTRO_ID} ${DISTRO_VERSION}${C_OFF} (${DISTRO_ARCH})"

    local FAMILY
    case "$DISTRO_ID $DISTRO_LIKE" in
        *ubuntu*|*debian*)        FAMILY="debian" ;;
        *fedora*|*rhel*|*centos*) FAMILY="fedora" ;;
        *opensuse*|*suse*)        FAMILY="suse" ;;
        *arch*|*manjaro*)         FAMILY="arch" ;;
        *)                        FAMILY="unknown" ;;
    esac

    # ---- Detect GPU ----
    detect_gpu() {
        if command -v lspci >/dev/null 2>&1 && lspci 2>/dev/null | grep -qi 'NVIDIA'; then
            return 0
        fi
        [[ -d /proc/driver/nvidia ]] && return 0
        [[ -e /dev/nvidia0 ]] && return 0
        return 1
    }

    # ---- Choose backend ----
    if [[ -z "$BACKEND" ]]; then
        if detect_gpu; then
            info "NVIDIA GPU detected"
            if [[ $NON_INTERACTIVE -eq 1 ]]; then
                BACKEND="gpu"
            else
                read -rp "Install the GPU (CUDA) version? [Y/n] " REPLY < /dev/tty || REPLY="y"
                [[ "$REPLY" =~ ^[Nn] ]] && BACKEND="cpu" || BACKEND="gpu"
            fi
        else
            info "No NVIDIA GPU detected — using CPU version"
            BACKEND="cpu"
        fi
    fi
    ok "Backend: ${C_BOLD}${BACKEND}${C_OFF}"

    # ---- Arch sanity check ----
    if [[ "$DISTRO_ARCH" != "x86_64" ]] && [[ "$FAMILY" != "arch" ]]; then
        warn "Pre-built packages are x86_64 only. On ${DISTRO_ARCH} you need to build from source."
        die "Unsupported architecture for pre-built packages: ${DISTRO_ARCH}"
    fi

    # ---- Fetch release info ----
    local RELEASE_JSON RELEASE_TAG
    if [[ -n "$REQUESTED_VERSION" ]]; then
        RELEASE_JSON="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/tags/v${REQUESTED_VERSION}")" \
            || die "Cannot fetch release v${REQUESTED_VERSION}"
    else
        RELEASE_JSON="$(curl -fsSL "$GITHUB_API")" || die "Cannot reach GitHub API"
    fi
    RELEASE_TAG=$(echo "$RELEASE_JSON" | grep -Po '"tag_name"\s*:\s*"\K[^"]+' | head -1)
    [[ -n "$RELEASE_TAG" ]] || die "Cannot parse release tag"
    ok "Target release: ${C_BOLD}${RELEASE_TAG}${C_OFF}"

    # Extract download URL matching a filename pattern
    find_asset_url() {
        local pattern="$1"
        echo "$RELEASE_JSON" \
            | grep -Po '"browser_download_url"\s*:\s*"\K[^"]+' \
            | grep -E "$pattern" \
            | head -1
    }

    # Build NVIDIA CUDA keyring URL with runtime fallback if the native repo
    # does not exist (NVIDIA removes old ones and lags on new releases).
    nvidia_keyring_url() {
        local base="https://developer.download.nvidia.com/compute/cuda/repos"
        local keyring="cuda-keyring_1.1-1_all.deb"
        local native="$1" fallback="$2"
        local url="${base}/${native}/x86_64/${keyring}"
        if curl -fsI "$url" >/dev/null 2>&1; then
            echo "$url"
        else
            warn "NVIDIA repo for ${native} not found, falling back to ${fallback}"
            echo "${base}/${fallback}/x86_64/${keyring}"
        fi
    }

    # ---- Temp dir ----
    local TMPDIR; TMPDIR="${TMPDIR:-/tmp}/dictee-install-$$"
    mkdir -p "$TMPDIR"
    trap 'rm -rf "$TMPDIR"' EXIT
    cd "$TMPDIR"

    # ---- Distro-specific install ----

    install_debian() {
        local deb_url
        if [[ "$BACKEND" == "gpu" ]]; then
            info "Adding NVIDIA CUDA APT repository..."
            local keyring_url
            case "$DISTRO_ID" in
                ubuntu)
                    local ubuntu_ver="${DISTRO_VERSION//./}"
                    keyring_url=$(nvidia_keyring_url "ubuntu${ubuntu_ver}" "ubuntu2404")
                    ;;
                debian)
                    local debian_ver="${DISTRO_VERSION%%.*}"
                    keyring_url=$(nvidia_keyring_url "debian${debian_ver}" "debian12")
                    ;;
                *)
                    warn "Ubuntu-derivative '${DISTRO_ID}' — using ubuntu2404 NVIDIA repo"
                    keyring_url=$(nvidia_keyring_url "ubuntu2404" "ubuntu2204")
                    ;;
            esac
            local keyring="${keyring_url##*/}"
            if ! dpkg -s cuda-keyring >/dev/null 2>&1; then
                curl -fsSLo "$keyring" "$keyring_url" || die "Failed to download cuda-keyring"
                sudo dpkg -i "$keyring" || die "Failed to install cuda-keyring"
            fi
            sudo apt-get update -qq
            deb_url=$(find_asset_url "dictee-cuda_.*_amd64\\.deb\$")
        else
            deb_url=$(find_asset_url "dictee-cpu_.*_amd64\\.deb\$")
        fi

        [[ -n "$deb_url" ]] || die "No matching .deb asset in release ${RELEASE_TAG}"
        local deb_file="${deb_url##*/}"
        info "Downloading ${deb_file}..."
        curl -fL --progress-bar -o "$deb_file" "$deb_url" || die "Download failed"
        ok "Downloaded"

        info "Installing..."
        sudo apt-get install -y "./${deb_file}" || die "Install failed"
    }

    install_fedora() {
        local rpm_url
        if [[ "$BACKEND" == "gpu" ]]; then
            info "Adding NVIDIA CUDA repository..."
            local fedora_ver="${DISTRO_VERSION}"
            local repo_url="https://developer.download.nvidia.com/compute/cuda/repos/fedora${fedora_ver}/x86_64/cuda-fedora${fedora_ver}.repo"
            if ! sudo dnf repolist 2>/dev/null | grep -qi cuda; then
                sudo dnf config-manager --add-repo "$repo_url" \
                    || sudo dnf config-manager addrepo --from-repofile="$repo_url"
            fi
            rpm_url=$(find_asset_url "dictee-cuda-.*\\.x86_64\\.rpm\$")
        else
            rpm_url=$(find_asset_url "dictee-cpu-.*\\.x86_64\\.rpm\$")
        fi

        [[ -n "$rpm_url" ]] || die "No matching .rpm asset in release ${RELEASE_TAG}"
        local rpm_file="${rpm_url##*/}"
        info "Downloading ${rpm_file}..."
        curl -fL --progress-bar -o "$rpm_file" "$rpm_url"
        ok "Downloaded"

        info "Installing..."
        sudo dnf install -y "./${rpm_file}" || die "Install failed"
    }

    install_suse() {
        local rpm_url
        if [[ "$BACKEND" == "gpu" ]]; then
            info "Adding NVIDIA CUDA repository for openSUSE..."
            local suse_repo_url="https://developer.download.nvidia.com/compute/cuda/repos/opensuse15/x86_64/cuda-opensuse15.repo"
            if ! sudo zypper repos 2>/dev/null | grep -qi 'cuda-opensuse15'; then
                sudo zypper --non-interactive addrepo "$suse_repo_url" \
                    || warn "Could not add NVIDIA repo (already present?)"
            fi
            sudo zypper --gpg-auto-import-keys --non-interactive refresh >/dev/null \
                || warn "zypper refresh reported errors"
            rpm_url=$(find_asset_url "dictee-cuda-.*\\.x86_64\\.rpm\$")
        else
            rpm_url=$(find_asset_url "dictee-cpu-.*\\.x86_64\\.rpm\$")
        fi

        [[ -n "$rpm_url" ]] || die "No matching .rpm asset in release ${RELEASE_TAG}"
        local rpm_file="${rpm_url##*/}"
        info "Downloading ${rpm_file}..."
        curl -fL --progress-bar -o "$rpm_file" "$rpm_url"
        ok "Downloaded"

        info "Installing (zypper)..."
        sudo zypper --non-interactive install --allow-unsigned-rpm "./${rpm_file}" \
            || die "Install failed"
    }

    install_arch() {
        need git
        command -v makepkg >/dev/null 2>&1 \
            || die "makepkg missing — install base-devel first: sudo pacman -S --needed base-devel"
        command -v cargo >/dev/null 2>&1 \
            || die "cargo missing — install rust first: sudo pacman -S --needed rust"

        # dictee depends on 'dotool' which lives in AUR, not the official repos.
        # makepkg alone cannot resolve AUR deps → we need an AUR helper (yay/paru).
        local aur_helper=""
        for h in yay paru; do
            if command -v "$h" >/dev/null 2>&1; then aur_helper="$h"; break; fi
        done

        if [[ -z "$aur_helper" ]]; then
            warn "No AUR helper (yay/paru) found."
            warn "dictee depends on 'dotool' from AUR, which makepkg cannot install on its own."
            warn ""
            warn "Install an AUR helper first:"
            warn "  sudo pacman -S --needed git base-devel"
            warn "  git clone https://aur.archlinux.org/yay.git && cd yay && makepkg -si"
            warn ""
            warn "Then re-run this installer, or install dictee directly via:"
            warn "  yay -S dictee   # if dictee is published to AUR"
            die "Missing AUR helper"
        fi

        info "Using AUR helper: ${C_BOLD}${aur_helper}${C_OFF}"
        info "Installing AUR dependency 'dotool'..."
        "$aur_helper" -S --needed --noconfirm dotool \
            || die "${aur_helper} failed to install dotool"

        info "Cloning the dictee repository..."
        git clone --depth 1 --branch "$RELEASE_TAG" "https://github.com/${REPO}.git" dictee-src \
            || git clone --depth 1 "https://github.com/${REPO}.git" dictee-src
        cd dictee-src

        info "Building via makepkg (this will compile from source)..."
        makepkg -si --noconfirm || die "makepkg failed"
    }

    install_tarball_fallback() {
        warn "Unsupported distro family — falling back to the tarball installer"
        local tar_url
        tar_url=$(find_asset_url "dictee-.*_amd64\\.tar\\.gz\$")
        [[ -n "$tar_url" ]] || die "No tarball found in release ${RELEASE_TAG}"
        local tar_file="${tar_url##*/}"
        info "Downloading ${tar_file}..."
        curl -fL --progress-bar -o "$tar_file" "$tar_url"
        tar xzf "$tar_file"
        local dir="${tar_file%.tar.gz}"
        cd "$dir" || die "Cannot enter extracted directory"
        info "Running install.sh (tarball mode)..."
        sudo ./install.sh --tarball || die "tarball install.sh failed"
    }

    case "$FAMILY" in
        debian) install_debian ;;
        fedora) install_fedora ;;
        suse)   install_suse ;;
        arch)   install_arch ;;
        *)      install_tarball_fallback ;;
    esac

    echo
    ok "dictee ${RELEASE_TAG} installed successfully"
    echo
    echo "Next steps:"
    echo "  ${C_BOLD}dictee-setup${C_OFF}    # run the first-run wizard"
    echo "  ${C_BOLD}dictee --help${C_OFF}   # CLI usage"
    echo
    echo "Documentation: https://github.com/${REPO}"
}

# =============================================================================
# TARBALL MODE — installs from files in the current directory.
# =============================================================================

mode_tarball() {
    local PREFIX="/usr/local"
    local MODEL_DIR="/usr/share/dictee"
    local SCRIPT_DIR
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    if [[ "$(id -u)" -ne 0 ]]; then
        die "Tarball mode needs root. Run as: sudo ./install.sh"
    fi

    local REAL_USER="${SUDO_USER:-$USER}"
    local REAL_HOME; REAL_HOME=$(eval echo "~$REAL_USER")
    local SYSTEMD_USER_DIR="$REAL_HOME/.config/systemd/user"
    local ICON_DIR="$REAL_HOME/.local/share/icons/hicolor/scalable/apps"
    local MAN_DIR="$PREFIX/share/man/man1"
    local MAN_FR_DIR="$PREFIX/share/man/fr/man1"

    info "Installing dictee from tarball at ${SCRIPT_DIR}"

    # --- Binaries ---
    info "Installing binaries into $PREFIX/bin/"
    local bins=(
        transcribe transcribe-daemon transcribe-client transcribe-diarize
        transcribe-stream-diarize dictee dictee-setup dictee-tray dictee-ptt
        dictee-postprocess dictee-switch-backend dictee-test-rules
        dictee-transcribe transcribe-daemon-vosk transcribe-daemon-whisper
        dictee-plasmoid-level dictee-plasmoid-level-daemon
        dictee-plasmoid-level-fft dotool dotoold dictee-reset
        dictee-translate-langs dictee-audio-sources
    )
    for b in "${bins[@]}"; do
        [[ -f "$SCRIPT_DIR/usr/bin/$b" ]] && install -Dm755 "$SCRIPT_DIR/usr/bin/$b" "$PREFIX/bin/$b"
    done

    # --- Shared libs ---
    info "Installing shared files into /usr/lib/dictee/"
    install -d /usr/lib/dictee
    [[ -f "$SCRIPT_DIR/usr/lib/dictee/dictee-common.sh" ]] \
        && install -Dm644 "$SCRIPT_DIR/usr/lib/dictee/dictee-common.sh" /usr/lib/dictee/dictee-common.sh
    [[ -f "$SCRIPT_DIR/usr/lib/dictee/dictee_models.py" ]] \
        && install -Dm644 "$SCRIPT_DIR/usr/lib/dictee/dictee_models.py" /usr/lib/dictee/dictee_models.py

    # --- CUDA libs (present only in the CUDA tarball variant) ---
    if [[ -d "$SCRIPT_DIR/usr/lib/dictee" ]]; then
        local have_cuda=0
        for lib in "$SCRIPT_DIR/usr/lib/dictee/"*.so "$SCRIPT_DIR/usr/lib/dictee/"*.so.*; do
            if [[ -f "$lib" ]]; then
                have_cuda=1
                install -Dm644 "$lib" "/usr/lib/dictee/$(basename "$lib")"
            fi
        done
        if [[ $have_cuda -eq 1 ]]; then
            info "Installed CUDA / ONNX Runtime libs"
            echo "/usr/lib/dictee" > /etc/ld.so.conf.d/dictee.conf
            ldconfig 2>/dev/null || true
        fi
    fi

    # --- udev rule for dotool ---
    info "Installing udev rules"
    install -Dm644 "$SCRIPT_DIR/etc/udev/rules.d/80-dotool.rules" /etc/udev/rules.d/80-dotool.rules
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger /dev/uinput 2>/dev/null || true

    # --- input group (dotool needs /dev/uinput) ---
    if ! id -nG "$REAL_USER" | grep -qw input; then
        usermod -aG input "$REAL_USER"
        ok "$REAL_USER added to group 'input' — reboot required to activate"
    fi

    # --- docker group (LibreTranslate runs in Docker) ---
    if command -v docker >/dev/null 2>&1; then
        if ! systemctl is-active --quiet docker 2>/dev/null; then
            systemctl start docker 2>/dev/null || true
            systemctl enable docker 2>/dev/null || true
        fi
        if ! id -nG "$REAL_USER" | grep -qw docker; then
            usermod -aG docker "$REAL_USER"
            ok "$REAL_USER added to group 'docker' (LibreTranslate)"
        fi
    fi

    # --- Man pages ---
    info "Installing man pages"
    mkdir -p "$MAN_DIR" "$MAN_FR_DIR"
    for f in "$SCRIPT_DIR/usr/share/man/man1/"*.1; do
        [[ -f "$f" ]] && install -Dm644 "$f" "$MAN_DIR/$(basename "$f")"
    done
    for f in "$SCRIPT_DIR/usr/share/man/fr/man1/"*.1; do
        [[ -f "$f" ]] && install -Dm644 "$f" "$MAN_FR_DIR/$(basename "$f")"
    done

    # --- Locales ---
    info "Installing translations"
    for lang_dir in "$SCRIPT_DIR/usr/share/locale/"*/LC_MESSAGES; do
        [[ -d "$lang_dir" ]] || continue
        local lang; lang=$(basename "$(dirname "$lang_dir")")
        install -d "$PREFIX/share/locale/$lang/LC_MESSAGES"
        for mo in "$lang_dir/"*.mo; do
            [[ -f "$mo" ]] && install -Dm644 "$mo" "$PREFIX/share/locale/$lang/LC_MESSAGES/$(basename "$mo")"
        done
    done

    # --- Desktop entries ---
    info "Installing .desktop entries"
    for entry in dictee-setup.desktop dictee-tray.desktop; do
        [[ -f "$SCRIPT_DIR/usr/share/applications/$entry" ]] \
            && install -Dm644 "$SCRIPT_DIR/usr/share/applications/$entry" "$PREFIX/share/applications/$entry"
    done

    # --- Icons (installed into the user's home) ---
    info "Installing icons"
    install -d "$ICON_DIR"
    for svg in "$SCRIPT_DIR/usr/share/icons/hicolor/scalable/apps/"*.svg; do
        [[ -f "$svg" ]] && install -Dm644 "$svg" "$ICON_DIR/$(basename "$svg")"
    done
    chown -R "$REAL_USER:" "$REAL_HOME/.local/share/icons"

    # --- systemd user units (rewrite /usr/bin to /usr/local/bin) ---
    info "Installing systemd user units"
    install -d "$SYSTEMD_USER_DIR"
    for svc in "$SCRIPT_DIR/usr/lib/systemd/user/"*.service; do
        [[ -f "$svc" ]] || continue
        sed "s|/usr/bin/|$PREFIX/bin/|g" "$svc" > "$SYSTEMD_USER_DIR/$(basename "$svc")"
    done
    chown -R "$REAL_USER:" "$SYSTEMD_USER_DIR"

    # --- systemd preset (auto-enable at login) ---
    local PRESET_DIR="/usr/lib/systemd/user-preset"
    install -d "$PRESET_DIR"
    for preset in "$SCRIPT_DIR/usr/lib/systemd/user-preset/"*.preset; do
        [[ -f "$preset" ]] && install -Dm644 "$preset" "$PRESET_DIR/$(basename "$preset")"
    done

    # --- Wizard banners + logos ---
    info "Installing assets"
    install -d "$MODEL_DIR/assets"
    for svg in "$SCRIPT_DIR/usr/share/dictee/assets/"*.svg; do
        [[ -f "$svg" ]] && install -Dm644 "$svg" "$MODEL_DIR/assets/$(basename "$svg")"
    done
    if [[ -d "$SCRIPT_DIR/usr/share/dictee/assets/logos" ]]; then
        install -d "$MODEL_DIR/assets/logos"
        for svg in "$SCRIPT_DIR/usr/share/dictee/assets/logos/"*.svg; do
            [[ -f "$svg" ]] && install -Dm644 "$svg" "$MODEL_DIR/assets/logos/$(basename "$svg")"
        done
    fi

    # --- Default post-processing conf + VERSION file ---
    for conf in rules.conf.default dictionary.conf.default continuation.conf.default \
                short_text_keepcaps.conf.default dictee.conf.example VERSION; do
        [[ -f "$SCRIPT_DIR/usr/share/dictee/$conf" ]] \
            && install -Dm644 "$SCRIPT_DIR/usr/share/dictee/$conf" "$MODEL_DIR/$conf"
    done

    # --- Plasmoid (when KDE is available) ---
    if [[ -f "$SCRIPT_DIR/usr/share/dictee/dictee.plasmoid" ]]; then
        install -Dm644 "$SCRIPT_DIR/usr/share/dictee/dictee.plasmoid" "$MODEL_DIR/dictee.plasmoid"
        if command -v kpackagetool6 >/dev/null 2>&1; then
            info "Installing KDE Plasma widget"
            sudo -u "$REAL_USER" kpackagetool6 -t Plasma/Applet -u "$MODEL_DIR/dictee.plasmoid" 2>/dev/null \
                || sudo -u "$REAL_USER" kpackagetool6 -t Plasma/Applet -i "$MODEL_DIR/dictee.plasmoid" 2>/dev/null \
                || true
        fi
    fi

    # --- Model directories (writable for dictee-setup) ---
    for d in "$MODEL_DIR" "$MODEL_DIR/tdt" "$MODEL_DIR/sortformer" "$MODEL_DIR/nemotron"; do
        mkdir -p "$d"
        chmod 777 "$d"
    done

    # --- Enable & start user services for the real user ---
    info "Activating systemd user services"
    local REAL_UID; REAL_UID=$(id -u "$REAL_USER")
    if [[ -d "/run/user/$REAL_UID" ]]; then
        local _run="sudo -u $REAL_USER XDG_RUNTIME_DIR=/run/user/$REAL_UID DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$REAL_UID/bus"
        $_run systemctl --user daemon-reload 2>/dev/null || true
        $_run systemctl --user preset dictee dictee-vosk dictee-whisper dictee-canary dictee-ptt dictee-tray dotoold 2>/dev/null || true
        $_run systemctl --user enable dotoold dictee-ptt dictee-tray 2>/dev/null || true
        $_run systemctl --user restart dotoold 2>/dev/null || true
        $_run systemctl --user restart dictee-ptt 2>/dev/null || true
        if [[ -f "$REAL_HOME/.config/dictee.conf" ]]; then
            $_run systemctl --user restart dictee-tray 2>/dev/null || true
        fi
        local _asr_backend="parakeet"
        if [[ -f "$REAL_HOME/.config/dictee.conf" ]]; then
            _asr_backend=$(grep -s '^DICTEE_ASR_BACKEND=' "$REAL_HOME/.config/dictee.conf" | cut -d= -f2)
        fi
        local _asr_svc
        case "$_asr_backend" in
            vosk)    _asr_svc="dictee-vosk" ;;
            whisper) _asr_svc="dictee-whisper" ;;
            canary)  _asr_svc="dictee-canary" ;;
            *)       _asr_svc="dictee" ;;
        esac
        $_run systemctl --user stop dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
        $_run systemctl --user disable dictee dictee-vosk dictee-whisper dictee-canary 2>/dev/null || true
        $_run systemctl --user enable "$_asr_svc" 2>/dev/null || true
        $_run systemctl --user start "$_asr_svc" 2>/dev/null || true
        ok "ASR daemon: ${_asr_svc} (backend: ${_asr_backend})"
        # GNOME AppIndicator for the tray icon
        $_run gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || true
    fi

    # --- Icon cache (GNOME) ---
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true
    fi

    echo
    ok "dictee installed"
    echo
    echo "Next steps:"
    echo "  ${C_BOLD}dictee-setup${C_OFF}    # run the first-run wizard"
    echo "  ${C_BOLD}dictee --help${C_OFF}   # CLI usage"
    echo
    echo "Uninstall: sudo ./uninstall.sh"
}

# =============================================================================
# DISPATCH
# =============================================================================

MODE=""
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --online)  MODE="online" ;;
        --tarball) MODE="tarball" ;;
        --help|-h) usage; exit 0 ;;
        *)         ARGS+=("$arg") ;;
    esac
done

if [[ -z "$MODE" ]]; then
    SCRIPT_DIR_DETECT=""
    if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "${BASH_SOURCE[0]}" ]]; then
        SCRIPT_DIR_DETECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    fi
    if [[ -n "$SCRIPT_DIR_DETECT" ]] \
       && [[ -f "$SCRIPT_DIR_DETECT/usr/bin/dictee" ]] \
       && [[ -f "$SCRIPT_DIR_DETECT/usr/share/dictee/VERSION" ]]; then
        MODE="tarball"
    else
        MODE="online"
    fi
fi

case "$MODE" in
    online)  mode_online "${ARGS[@]+"${ARGS[@]}"}" ;;
    tarball) mode_tarball "${ARGS[@]+"${ARGS[@]}"}" ;;
    *)       die "Unknown mode: $MODE" ;;
esac
