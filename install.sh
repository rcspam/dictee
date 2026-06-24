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
# Use /releases/latest (newest stable, skips prereleases and drafts) so that
# curl|bash always lands on the latest STABLE release. Prereleases stay opt-in:
# reachable from the Releases page / a direct link (e.g. targeted user testing),
# but never auto-installed for everyone. Override a specific version with --version.
GITHUB_API="https://api.github.com/repos/${REPO}/releases/latest"

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

# Parse a package manager's dry-run output and echo the THIRD-PARTY packages it
# would REMOVE (manager-specific). Empty output = nothing of yours removed.
# dictee's own packages are filtered out: dictee-cuda Conflicts dictee-cpu (and
# vice-versa), so switching CPU<->GPU legitimately replaces one with the other
# and must not trip the guard.
_removed_by() {
    case "$1" in
        apt)    awk '/^Remv /{print $2}' ;;
        dnf)    awk '/^(Removing|Erasing)/{f=1;next} /^[[:space:]]*$/{f=0} f&&NF{print $1}' ;;
        zypper) awk '/going to be REMOVED/{f=1;next} f&&/^  /{print $1} f&&/^[^ ]/{f=0}' ;;
    esac | grep -vE '^dictee([-_.]|$)' | tr '\n' ' '
}

# Install a local .deb/.rpm WITHOUT ever letting the package manager uninstall
# the user's existing software to resolve a conflict (#21). Three levels:
#   1. nothing would be removed → normal install (with recommendations);
#   2. else retry WITHOUT optional (weak) dependencies — keeps dictee
#      installable while PRESERVING the conflicting package (this was the #21
#      case: docker.io was only a Recommends);
#   3. else (a hard Depends conflict) → abort cleanly, change nothing.
safe_install() {
    local mgr="$1" pkg="$2" norec="" remv
    case "$mgr" in
        apt)    norec="--no-install-recommends" ;;
        dnf)    norec="--setopt=install_weak_deps=False" ;;
        zypper) norec="--no-recommends" ;;
    esac

    # Simulate; $1 = extra flag (e.g. the no-weak-deps flag). Echoes removals.
    _dry() {
        case "$mgr" in
            apt)    sudo apt-get install -s $1 "./${pkg}" 2>/dev/null | _removed_by apt ;;
            dnf)    sudo dnf install --assumeno $1 "./${pkg}" 2>&1 | _removed_by dnf ;;
            zypper) sudo zypper --non-interactive install --dry-run $1 --allow-unsigned-rpm "./${pkg}" 2>/dev/null | _removed_by zypper ;;
        esac
    }
    # Real install; $1 = extra flag.
    _run() {
        case "$mgr" in
            apt)    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y $1 "./${pkg}" || die "Install failed" ;;
            dnf)    sudo dnf install -y $1 "./${pkg}" || die "Install failed" ;;
            zypper) sudo zypper --non-interactive install $1 --allow-unsigned-rpm "./${pkg}" || die "Install failed" ;;
        esac
    }

    # 1. No removals → normal install.
    remv=$(_dry "")
    if [[ -z "${remv// }" ]]; then _run ""; return; fi

    # 2. Removals → retry without optional (weak) deps to preserve them.
    warn "Installing dictee would REMOVE existing packages: ${remv}"
    warn "Retrying without optional (recommended) packages to keep yours..."
    remv=$(_dry "$norec")
    if [[ -z "${remv// }" ]]; then
        warn "Installing dictee WITHOUT optional extras to avoid the conflict."
        warn "Your packages are preserved; you can add the optional extras later."
        _run "$norec"
        return
    fi

    # 3. Still removing → hard (mandatory) dependency conflict → abort.
    err "Cannot install dictee without removing: ${remv}"
    err "This is a mandatory-dependency conflict. Resolve it manually, then re-run."
    err "dictee did not change anything on your system."
    exit 1
}

# Offer to launch dictee-setup when a graphical session is available.
# Usage: launch_wizard [user]  (user = optional; defaults to current user)
auto_reset_services() {
    # Si dictee.conf existe (réinstall avec config préservée), restart
    # dictee-ptt pour qu'il relise DICTEE_PTT_KEY. Le %post du paquet le
    # fait déjà, mais au 1er restart python3-evdev n'est pas encore
    # déployé (transaction dnf installe les weak deps après dictee-cpu)
    # → service coincé en mode raw où la touche fuit vers les apps. Un
    # 2e restart ici, après que tous les paquets soient en place, force
    # le passage en mode evdev (grab exclusif).
    #
    # On NE lance PAS dictee-reset complet : il restart le ASR daemon qui
    # bloque ~20-30s pour charger le modèle ONNX → risque de timeout SSH
    # ou de coupure de session. Le ASR daemon est déjà démarré par %post.
    #
    # systemctl --user nécessite un user bus → JAMAIS en tant que root.
    # Si on tourne en root (curl | sudo bash), on bascule via sudo -u
    # $SUDO_USER. Pas de SUDO_USER → on skip (root pur, pas de session).
    local target_user="${1:-}"
    if [[ -z "$target_user" && "$(id -u)" -eq 0 ]]; then
        target_user="${SUDO_USER:-}"
        [[ -z "$target_user" ]] && return 0
    fi

    local conf_path uid
    if [[ -n "$target_user" && "$target_user" != "$(id -un)" ]]; then
        conf_path="$(eval echo "~$target_user")/.config/dictee.conf"
        [[ -f "$conf_path" ]] || return 0
        uid=$(id -u "$target_user" 2>/dev/null) || return 0
        info "Existing configuration detected — restarting dictee-ptt..."
        sudo -u "$target_user" XDG_RUNTIME_DIR="/run/user/${uid}" \
            systemctl --user restart dictee-ptt 2>/dev/null || true
    else
        conf_path="$HOME/.config/dictee.conf"
        [[ -f "$conf_path" ]] || return 0
        info "Existing configuration detected — restarting dictee-ptt..."
        systemctl --user restart dictee-ptt 2>/dev/null || true
    fi
}

launch_wizard() {
    local target_user="${1:-}"
    local sudo_env=""
    local gui_display="${DISPLAY:-}"
    local gui_wayland="${WAYLAND_DISPLAY:-}"

    # Auto-détection du vrai user quand on tourne en root (curl | sudo bash).
    # Sans ça, dictee-setup serait lancé en root → ~/.config/dictee.conf
    # résolu en /root/.config/dictee.conf qui n'existe pas → wizard_mode=True
    # à tort + écriture polluante dans /root au Apply.
    if [[ -z "$target_user" && "$(id -u)" -eq 0 ]]; then
        target_user="${SUDO_USER:-}"
        [[ -z "$target_user" ]] && return 0
    fi

    # In tarball/root mode, inspect the real user's environment instead of root's.
    if [[ -n "$target_user" && "$target_user" != "$(id -un)" ]]; then
        local uid; uid=$(id -u "$target_user" 2>/dev/null) || return 0
        gui_display=$(sudo -u "$target_user" sh -c 'echo "${DISPLAY:-}"' 2>/dev/null || echo "")
        gui_wayland=$(sudo -u "$target_user" sh -c 'echo "${WAYLAND_DISPLAY:-}"' 2>/dev/null || echo "")
        sudo_env="sudo -u $target_user -E env DISPLAY=${gui_display} WAYLAND_DISPLAY=${gui_wayland} XDG_RUNTIME_DIR=/run/user/${uid}"
    fi

    if [[ -z "$gui_display" && -z "$gui_wayland" ]]; then
        return 0
    fi

    local ans=""
    if [[ -r /dev/tty ]]; then
        echo
        read -p "Launch dictee-setup now? [Y/n] " -t 10 -r ans < /dev/tty || ans=""
    fi
    case "${ans:-y}" in
        [Nn]*) return 0 ;;
    esac

    info "Launching dictee-setup..."
    # Launch from a directory that still exists after this installer exits.
    # We currently sit in the temp dir that the EXIT trap removes moments later;
    # a child inheriting that deleted CWD makes "python -m pip" fail with
    # FileNotFoundError on os.getcwd() when the user later installs Vosk/Whisper
    # from the setup window (observed on Fedora 44 KDE, issue #18).
    cd / 2>/dev/null || true
    if [[ -n "$sudo_env" ]]; then
        nohup $sudo_env dictee-setup >/dev/null 2>&1 &
    else
        nohup dictee-setup >/dev/null 2>&1 &
    fi
    disown || true
}

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

    # Download helper with retry in bash (keeps curl's --progress-bar clean;
    # curl's own --retry prints warnings that collide with the progress bar).
    download_with_retry() {
        local out="$1" url="$2" attempts=3
        for ((i=1; i<=attempts; i++)); do
            curl -fL --progress-bar -o "$out" "$url" && return 0
            if (( i < attempts )); then
                warn "Download failed, retrying in 2s (attempt $((i+1))/${attempts})..."
                sleep 2
            fi
        done
        return 1
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
    # Expand $TMPDIR at trap-registration time — the local var is gone by EXIT.
    trap "rm -rf '$TMPDIR'" EXIT
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
        download_with_retry "$deb_file" "$deb_url" || die "Download failed"
        ok "Downloaded"

        info "Installing..."
        # DEBIAN_FRONTEND=noninteractive: under curl|bash, stdin is the pipe (not
        # a tty), so a debconf prompt from any pulled-in dependency would hang the
        # install with no way to answer (#16). Force the non-interactive frontend.
        safe_install apt "${deb_file}"

        # The GNOME AppIndicator extension ships as a Suggests, not a Recommends:
        # as a Recommends it dragged gnome-shell + gdm3 onto non-GNOME systems
        # (Kubuntu/KDE — #16). Install it only on a GNOME session, where the
        # system-tray icon actually needs it.
        if printf '%s' "${XDG_CURRENT_DESKTOP:-}" | grep -qi gnome; then
            info "GNOME session detected — installing the AppIndicator extension for the tray icon..."
            sudo DEBIAN_FRONTEND=noninteractive apt-get install -y gnome-shell-extension-appindicator \
                || warn "Could not install gnome-shell-extension-appindicator — the GNOME tray icon may not appear"
        fi
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
        download_with_retry "$rpm_file" "$rpm_url"
        ok "Downloaded"

        info "Installing..."
        safe_install dnf "${rpm_file}"

        # GNOME-only: the AppIndicator extension is a Suggests now (it used to be a
        # weak dep that pulled gnome-shell onto KDE Fedora — #16). Install it only
        # on a GNOME session, where the tray icon needs it.
        if printf '%s' "${XDG_CURRENT_DESKTOP:-}" | grep -qi gnome; then
            info "GNOME session detected — installing the AppIndicator extension..."
            sudo dnf install -y gnome-shell-extension-appindicator gnome-extensions-app \
                || warn "Could not install the GNOME AppIndicator extension — the tray icon may not appear"
        fi
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
        download_with_retry "$rpm_file" "$rpm_url"
        ok "Downloaded"

        info "Installing (zypper)..."
        safe_install zypper "${rpm_file}"
    }

    # Detect orphan files from a previous install.sh tarball mode that
    # would cause pacman file conflicts (Arch is strict, dpkg/rpm overwrite
    # silently — issue #4 follow-up).
    check_arch_orphans() {
        local static_files=(
            /etc/modules-load.d/dictee-uinput.conf
            /etc/udev/rules.d/80-dotool.rules
            /etc/ld.so.conf.d/dictee.conf
            /usr/lib/dictee/dictee-common.sh
            /usr/lib/dictee/dictee_models.py
            /usr/lib/systemd/user/dictee.service
            /usr/lib/systemd/user/dictee-tray.service
            /usr/lib/systemd/user/dictee-ptt.service
            /usr/lib/systemd/user/dictee-vosk.service
            /usr/lib/systemd/user/dictee-whisper.service
            /usr/lib/systemd/user/dictee-canary.service
            /usr/lib/systemd/user-preset/90-dictee.preset
            /usr/share/applications/dictee-setup.desktop
            /usr/share/applications/dictee-transcribe.desktop
            /usr/share/applications/dictee-tray.desktop
            /usr/share/dictee/dictee.conf.example
            /usr/share/dictee/rules.conf.default
            /usr/share/dictee/dictionary.conf.default
            /usr/share/dictee/continuation.conf.default
            /usr/share/dictee/VERSION
            /usr/share/dictee/dictee.plasmoid
        )
        local glob_patterns=(
            "/usr/bin/dictee"
            "/usr/bin/dictee-"*
            "/usr/bin/diarize-only"
            "/usr/bin/transcribe"
            "/usr/bin/transcribe-"*
            "/usr/share/dictee/assets/banner-"*.svg
            "/usr/share/dictee/assets/logos/"*.svg
            "/usr/share/dictee/assets/icons/"*.svg
            "/usr/share/icons/hicolor/scalable/apps/parakeet-"*.svg
            "/usr/share/locale/"*"/LC_MESSAGES/dictee.mo"
            "/usr/share/man/man1/dictee"*.1
            "/usr/share/man/fr/man1/dictee"*.1
        )

        local candidates=()
        local f
        for f in "${static_files[@]}"; do
            [[ -e "$f" ]] && candidates+=("$f")
        done
        local pattern
        for pattern in "${glob_patterns[@]}"; do
            for f in $pattern; do
                [[ -e "$f" ]] && candidates+=("$f")
            done
        done

        # Filter to orphans only (not owned by any pacman package)
        local orphans=()
        for f in "${candidates[@]}"; do
            if ! pacman -Qo "$f" >/dev/null 2>&1; then
                orphans+=("$f")
            fi
        done

        if [[ ${#orphans[@]} -eq 0 ]]; then
            return 0
        fi

        warn "Detected ${#orphans[@]} orphan file(s) from a previous install"
        warn "(probably from a previous install.sh tarball mode):"
        local o
        for o in "${orphans[@]}"; do
            warn "  $o"
        done
        warn ""
        warn "These will cause pacman file conflicts during the dictee install."

        if [[ $NON_INTERACTIVE -eq 1 ]]; then
            warn ""
            warn "Non-interactive mode → cannot prompt. Remove them manually:"
            warn "  sudo rm ${orphans[*]}"
            die "Aborted: orphan files present, cannot auto-clean in --non-interactive mode."
        fi

        echo
        local REPLY=""
        read -rp "Remove these orphan files now? [Y/n] " REPLY < /dev/tty || REPLY="y"
        if [[ "$REPLY" =~ ^[Nn] ]]; then
            die "Aborted. Remove orphan files manually and retry."
        fi

        info "Removing orphan files..."
        for o in "${orphans[@]}"; do
            if sudo rm -f "$o" 2>/dev/null; then
                ok "Removed: $o"
            else
                warn "Failed to remove: $o"
            fi
        done
        ok "Orphan cleanup complete."
    }

    install_arch() {
        need git
        command -v makepkg >/dev/null 2>&1 \
            || die "makepkg missing — install base-devel first: sudo pacman -S --needed base-devel"
        command -v cargo >/dev/null 2>&1 \
            || die "cargo missing — install rust first: sudo pacman -S --needed rust"

        # Clean up orphan files from a previous tarball-mode install before
        # makepkg -si triggers pacman file conflicts.
        check_arch_orphans

        # dictee depends on 'dotool' which lives in AUR, not the official repos.
        # makepkg alone cannot resolve AUR deps → we need an AUR helper (yay/paru).
        local aur_helper=""
        for h in yay paru; do
            if command -v "$h" >/dev/null 2>&1; then aur_helper="$h"; break; fi
        done

        if [[ -z "$aur_helper" ]]; then
            # Fallback : bootstrap dotool directement via git+makepkg sans
            # dépendre d'un AUR helper installé. Évite le poulet/œuf yay/paru
            # qui sont eux-mêmes dans l'AUR. Self-contained sur Arch fresh.
            info "No AUR helper found — bootstrapping 'dotool' directly via makepkg"
            command -v git >/dev/null 2>&1 \
                || die "git missing — sudo pacman -S --needed git"
            local _aur_tmpdir
            _aur_tmpdir=$(mktemp -d -t dictee-aur-bootstrap.XXXXXX)
            if ! git clone --depth 1 https://aur.archlinux.org/dotool.git \
                    "$_aur_tmpdir/dotool" 2>&1; then
                rm -rf "$_aur_tmpdir"
                die "Failed to clone dotool from AUR (offline?)"
            fi
            if ! (cd "$_aur_tmpdir/dotool" && makepkg -si --noconfirm); then
                rm -rf "$_aur_tmpdir"
                die "Failed to build/install dotool — see makepkg output above"
            fi
            rm -rf "$_aur_tmpdir"
            ok "dotool installed (no AUR helper required)"
        else
            info "Using AUR helper: ${C_BOLD}${aur_helper}${C_OFF}"
            info "Installing AUR dependency 'dotool'..."
            "$aur_helper" -S --needed --noconfirm dotool \
                || die "${aur_helper} failed to install dotool"
        fi

        # translate-shell is in optdepends of the PKGBUILD (so makepkg -si
        # won't install it), but DEB/RPM packages have it as Recommends and
        # apt/dnf install it by default. Install it here for cross-distro
        # consistency — it's in the official Arch `extra` repo (~5 MB),
        # provides the `trans` CLI used by Google/Bing translation backends.
        info "Installing translate-shell (Google/Bing translation)..."
        sudo pacman -S --needed --noconfirm translate-shell \
            || warn "Failed to install translate-shell — Google/Bing translation will be unavailable"

        # Docker is needed only for LibreTranslate (offline self-hosted translation).
        # Other backends (Google, Bing, Ollama) work without it. .deb/.rpm install
        # docker via Recommends (docker.io / moby-engine), but pacman has no
        # equivalent — prompt the user (~250 MB). If they skip now, the setup
        # wizard will surface a "Setup Docker" button later in the LT page.
        if ! command -v docker >/dev/null 2>&1; then
            local install_docker="n"
            if [[ $NON_INTERACTIVE -eq 1 ]]; then
                info "Docker not installed — skipping (non-interactive). Install later if you want LibreTranslate."
            elif [[ -r /dev/tty ]]; then
                echo
                echo "Docker is needed for LibreTranslate (offline self-hosted translation, ~250 MB)."
                echo "Other translation backends (Google, Bing, Ollama) work without it."
                read -rp "Install Docker now? [y/N] " install_docker < /dev/tty || install_docker="n"
            fi
            if [[ "$install_docker" =~ ^[Yy] ]]; then
                info "Installing docker..."
                sudo pacman -S --needed --noconfirm docker \
                    || warn "Failed to install docker — LibreTranslate will be unavailable"
            fi
        fi

        info "Cloning dictee at the latest release tag (${RELEASE_TAG})..."
        # Clone the resolved release TAG ($RELEASE_TAG), NOT master. This
        # mirrors what the deb/rpm/tarball paths already do — they pull assets
        # from the release tag — so all four targets follow the same published
        # release. The Arch path builds from source, so it clones the tag to
        # read its PKGBUILD; makepkg then builds it via source=()
        # (archive/v$_tag.tar.gz). Cloning the tag guarantees that archive
        # exists: a published tag always has a downloadable archive, and the
        # tag's PKGBUILD pins _tag to that same version. master must NOT be
        # cloned — it can sit ahead on an unreleased dev version (e.g.
        # 1.4.0-beta) whose tag does not exist yet, making makepkg fetch a 404
        # archive and abort (issue #17). Tracking $RELEASE_TAG also means Arch
        # follows the latest published release automatically, nothing
        # hard-coded. $RELEASE_TAG is set above (latest stable, or --version).
        git clone --depth 1 --branch "$RELEASE_TAG" "https://github.com/${REPO}.git" dictee-src
        cd dictee-src

        # Pre-build heads-up: makepkg compiles parakeet-rs (Rust+ONNX) from
        # source, which is silent and slow. Without this warning, users
        # routinely Ctrl-C around minute 4-5 thinking the install hung.
        echo
        warn "About to build dictee from source via makepkg."
        warn "Compilation: ~5-10 min on a 4-core CPU, ~3 GB of disk in /tmp."
        warn "Output will be terse — this is normal, please be patient."
        echo

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
        download_with_retry "$tar_file" "$tar_url"
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

    auto_reset_services
    launch_wizard
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

    # --- Dependencies notice (tarball ships binaries only) ---
    # The .deb / .rpm / Arch packages declare their distro deps in the
    # package metadata (Depends/Requires/depends), so apt/dnf/pacman
    # install them before the postinst runs. The tarball is for distros
    # without an official package — there's no metadata, no automatic
    # install, and we can't safely guess the right command across
    # Slackware / Gentoo / Void / NixOS / etc.
    #
    # We just print the list. If something is missing, dictee-setup will
    # die with `ImportError: No module named PyQt6` (or similar) and the
    # user has at least seen this message.
    cat <<EOF

${C_YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_OFF}
${C_BOLD}REQUIRED SYSTEM DEPENDENCIES${C_OFF}

The tarball ships binaries only — install these via your distro's
package manager BEFORE running dictee-setup (names vary by distro):

  • python3 (≥3.10), python3-pip, python3-venv
  • python3-evdev, python3-pyqt6 (+ qtmultimedia + qtsvg), python3-numpy
  • pulseaudio-utils, pipewire (or alsa-utils), libnotify(-bin), sox
  • wl-clipboard (Wayland), xclip (X11)
  • translate-shell, curl

Debian-like example:
  sudo apt install python3 python3-pip python3-venv python3-evdev \\
      python3-pyqt6 python3-pyqt6.qtmultimedia python3-pyqt6.qtsvg \\
      python3-numpy pulseaudio-utils pipewire libnotify-bin sox \\
      wl-clipboard xclip translate-shell curl
${C_YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_OFF}

EOF

    # --- Binaries ---
    info "Installing binaries into $PREFIX/bin/"
    local bins=(
        transcribe transcribe-daemon transcribe-client transcribe-diarize
        transcribe-stream-diarize dictee dictee-setup dictee-tray dictee-ptt
        dictee-postprocess dictee-diarize-llm dictee-switch-backend dictee-test-rules
        dictee-transcribe transcribe-daemon-vosk transcribe-daemon-whisper
        dictee-plasmoid-level dictee-plasmoid-level-daemon
        dictee-plasmoid-level-fft dotool dotoold dictee-reset
        dictee-translate-langs dictee-audio-sources dictee-meeting-live
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

    # --- NVIDIA CUDA runtime libs via pip (mirrors postinst .deb) ---
    # Only when the CUDA provider .so is actually present. Creates
    # /opt/dictee/cuda-venv, pip installs nvidia-*-cu12 wheels, then
    # symlinks their .so files into /usr/lib/dictee/ so ldconfig picks
    # them up. Keeps the tarball portable on any distro without
    # depending on the NVIDIA repo.
    #
    # Skip the ~1.5 GB download if no NVIDIA GPU is detected — the runtime
    # fallback (v1.3.1) picks CPU automatically.
    if [[ ! -d /proc/driver/nvidia && ! -e /dev/nvidia0 ]]; then
        if [[ -f /usr/lib/dictee/libonnxruntime_providers_cuda.so ]]; then
            info "No NVIDIA GPU detected — skipping CUDA libs download (~1.5 GB)."
            info "The runtime will automatically fall back to CPU."
            info "To enable CUDA after installing an NVIDIA driver:"
            info "  sudo python3 -m venv /opt/dictee/cuda-venv"
            info "  sudo /opt/dictee/cuda-venv/bin/pip install nvidia-cuda-runtime-cu12 \\"
            info "       nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cufft-cu12 \\"
            info "       nvidia-curand-cu12 nvidia-cuda-nvrtc-cu12"
            info "  sudo ldconfig"
        fi
    elif [[ -f /usr/lib/dictee/libonnxruntime_providers_cuda.so ]] \
            && command -v python3 >/dev/null 2>&1; then
        local CUDA_VENV="/opt/dictee/cuda-venv"
        info "Setting up NVIDIA CUDA libs via pip into $CUDA_VENV (≈ 1.5 GB)"
        mkdir -p /opt/dictee
        if [[ ! -x "$CUDA_VENV/bin/pip" ]]; then
            if ! python3 -m venv "$CUDA_VENV" 2>/dev/null; then
                warn "python3 -m venv failed — is python3-venv installed?"
            else
                "$CUDA_VENV/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
            fi
        fi
        if [[ -x "$CUDA_VENV/bin/pip" ]]; then
            if "$CUDA_VENV/bin/pip" install --quiet --upgrade \
                    nvidia-cuda-runtime-cu12 \
                    nvidia-cublas-cu12 \
                    nvidia-cudnn-cu12 \
                    nvidia-cufft-cu12 \
                    nvidia-curand-cu12 \
                    nvidia-cuda-nvrtc-cu12 2>/dev/null; then
                local _py_ver
                _py_ver=$(ls "$CUDA_VENV/lib/" 2>/dev/null | grep -E "^python" | head -1)
                if [[ -n "$_py_ver" ]]; then
                    local _nvidia_root="$CUDA_VENV/lib/$_py_ver/site-packages/nvidia"
                    local _count=0
                    for _sub in "$_nvidia_root"/*/lib; do
                        [[ -d "$_sub" ]] || continue
                        for _so in "$_sub"/lib*.so*; do
                            [[ -f "$_so" ]] || continue
                            ln -sf "$_so" "/usr/lib/dictee/$(basename "$_so")"
                            _count=$((_count + 1))
                        done
                    done
                    ok "Linked $_count NVIDIA libs into /usr/lib/dictee/"
                    ldconfig 2>/dev/null || true
                fi
            else
                warn "pip install of nvidia-*-cu12 failed (offline? disk full?)"
                warn "Re-run later: sudo $CUDA_VENV/bin/pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cufft-cu12 nvidia-curand-cu12 nvidia-cuda-nvrtc-cu12 && sudo ldconfig"
            fi
        fi
    fi

    # --- udev rule for dotool ---
    info "Installing udev rules"
    install -Dm644 "$SCRIPT_DIR/etc/udev/rules.d/80-dotool.rules" /etc/udev/rules.d/80-dotool.rules
    # uinput needs group rw (0660) — dotool/evdev open it O_RDWR, so the shipped
    # 0620 (dotool upstream) locks out group members. Bump to 0660 like the
    # .deb postinst / .rpm %post do (installer-parity: tarball must match).
    sed -i 's/MODE="0620"/MODE="0660"/' /etc/udev/rules.d/80-dotool.rules
    # modules-load.d so uinput auto-loads at boot (Fedora/RHEL don't load it).
    if [ -f "$SCRIPT_DIR/etc/modules-load.d/dictee-uinput.conf" ]; then
        install -Dm644 "$SCRIPT_DIR/etc/modules-load.d/dictee-uinput.conf" \
            /etc/modules-load.d/dictee-uinput.conf
    fi
    modprobe uinput 2>/dev/null || true
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger /dev/uinput 2>/dev/null || true

    # --- Postprocess venv (text2num for number conversion) ---
    # Mirrors postinst .deb / %post .rpm / dictee.install Arch — without it,
    # dictee-postprocess crashes when it hits a number-conversion step.
    if command -v python3 >/dev/null 2>&1; then
        local PP_VENV="/usr/share/dictee/postprocess-env"
        if [[ ! -d "$PP_VENV" ]]; then
            info "Creating postprocess venv (text2num)"
            if python3 -m venv "$PP_VENV" 2>/dev/null; then
                "$PP_VENV/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
                if "$PP_VENV/bin/pip" install --quiet text2num 2>/dev/null; then
                    ok "Postprocess venv ready"
                else
                    warn "pip install text2num failed (offline?) — number conversion will be disabled"
                fi
            else
                warn "python3 -m venv failed — is python3-venv installed?"
            fi
        else
            "$PP_VENV/bin/pip" install --quiet --upgrade text2num 2>/dev/null || true
        fi
    fi

    # --- input group (dotool needs /dev/uinput) ---
    # No reboot needed: dictee-ptt.service runs the daemon under
    # `sg input -c …` so the new group is effective immediately.
    # GUI apps started before the install (terminals, file managers)
    # won't see the group until the next login, but dictee itself
    # runs through dictee-ptt → sg input → /dev/uinput → fine.
    if ! id -nG "$REAL_USER" | grep -qw input; then
        usermod -aG input "$REAL_USER"
        ok "$REAL_USER added to group 'input' (active immediately via dictee-ptt's sg wrapper)"
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

    auto_reset_services "${SUDO_USER:-}"
    launch_wizard "${SUDO_USER:-}"
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
