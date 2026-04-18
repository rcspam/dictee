#!/bin/bash
# install-online.sh — One-shot installer for dictee
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install-online.sh | bash
#   curl -fsSL ... | bash -s -- --cpu
#   curl -fsSL ... | bash -s -- --gpu --version 1.3.0
#   curl -fsSL ... | bash -s -- --non-interactive

set -euo pipefail

# ---- Config ----
REPO="rcspam/dictee"
GITHUB_API="https://api.github.com/repos/${REPO}/releases/latest"
TMPDIR="${TMPDIR:-/tmp}/dictee-install-$$"

BACKEND=""          # cpu | gpu (empty = auto)
NON_INTERACTIVE=0
VERSION=""

# ---- Colors ----
if [[ -t 1 ]]; then
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
    C_BLUE=$'\033[34m'; C_BOLD=$'\033[1m'; C_OFF=$'\033[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_OFF=""
fi

info()  { echo "${C_BLUE}▶${C_OFF} $*"; }
ok()    { echo "${C_GREEN}✓${C_OFF} $*"; }
warn()  { echo "${C_YELLOW}⚠${C_OFF} $*"; }
err()   { echo "${C_RED}✗${C_OFF} $*" >&2; }
die()   { err "$@"; exit 1; }

usage() {
    cat <<EOF
dictee online installer

Usage:
  curl -fsSL https://raw.githubusercontent.com/rcspam/dictee/master/install-online.sh | bash [-- options]

Options:
  --cpu                Force CPU version
  --gpu                Force GPU (CUDA) version
  --version X.Y.Z      Install a specific version (default: latest release)
  --non-interactive    No prompts; auto-detect GPU
  --help               Show this help

Supported distros: Ubuntu/Debian, Fedora, openSUSE, Arch Linux.
Other distros fall back to the .tar.gz installer.
EOF
}

# ---- Parse args ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --cpu)             BACKEND="cpu"; shift ;;
        --gpu)             BACKEND="gpu"; shift ;;
        --version)         VERSION="${2:-}"; shift 2 ;;
        --non-interactive) NON_INTERACTIVE=1; shift ;;
        --help|-h)         usage; exit 0 ;;
        *)                 die "Unknown option: $1 (run with --help)" ;;
    esac
done

# ---- Tools check ----
need() { command -v "$1" >/dev/null 2>&1 || die "Missing required tool: $1"; }
need curl
need sudo

# ---- Detect OS ----
[[ -f /etc/os-release ]] || die "Cannot detect OS: /etc/os-release missing"
# shellcheck disable=SC1091
. /etc/os-release
DISTRO_ID="${ID:-unknown}"
DISTRO_LIKE="${ID_LIKE:-}"
DISTRO_VERSION="${VERSION_ID:-}"
DISTRO_ARCH="$(uname -m)"

info "Detected: ${C_BOLD}${NAME:-$DISTRO_ID} ${DISTRO_VERSION}${C_OFF} (${DISTRO_ARCH})"

# Normalize distro family
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

# ---- Fetch release info ----
fetch_release_json() {
    if [[ -n "$VERSION" ]]; then
        curl -fsSL "https://api.github.com/repos/${REPO}/releases/tags/v${VERSION}"
    else
        curl -fsSL "$GITHUB_API"
    fi
}

info "Querying GitHub releases..."
RELEASE_JSON="$(fetch_release_json)" || die "Cannot reach GitHub API"
RELEASE_TAG=$(echo "$RELEASE_JSON" | grep -Po '"tag_name"\s*:\s*"\K[^"]+' | head -1)
[[ -n "$RELEASE_TAG" ]] || die "Cannot parse release tag"
ok "Target release: ${C_BOLD}${RELEASE_TAG}${C_OFF}"

# Extract .deb/.rpm/tarball URLs matching our backend
find_asset_url() {
    local pattern="$1"
    echo "$RELEASE_JSON" \
        | grep -Po '"browser_download_url"\s*:\s*"\K[^"]+' \
        | grep -E "$pattern" \
        | head -1
}

# ---- Temp dir ----
mkdir -p "$TMPDIR"
trap 'rm -rf "$TMPDIR"' EXIT
cd "$TMPDIR"

# ---- Distro-specific install ----

# Build NVIDIA CUDA keyring URL, with runtime fallback if the native version's
# directory does not exist (NVIDIA removes old ones and lags on new ones).
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

install_debian() {
    local deb_url
    if [[ "$BACKEND" == "gpu" ]]; then
        info "Adding NVIDIA CUDA APT repository..."
        local repo_id keyring_url
        case "$DISTRO_ID" in
            ubuntu)
                local ubuntu_ver="${DISTRO_VERSION//./}"
                repo_id="ubuntu${ubuntu_ver}"
                keyring_url=$(nvidia_keyring_url "$repo_id" "ubuntu2404")
                ;;
            debian)
                local debian_ver="${DISTRO_VERSION%%.*}"
                repo_id="debian${debian_ver}"
                keyring_url=$(nvidia_keyring_url "$repo_id" "debian12")
                ;;
            *)
                # Ubuntu-derivative (Linux Mint, Pop!_OS, Zorin) — use the underlying
                # Ubuntu codename when we can, else assume 24.04
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
        # openSUSE 15.x (Leap) → opensuse15 ; Tumbleweed → opensuse15 also works
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

install_tarball() {
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
    info "Running install.sh..."
    sudo ./install.sh || die "install.sh failed"
}

# ---- Arch check ----
if [[ "$DISTRO_ARCH" != "x86_64" ]] && [[ "$FAMILY" != "arch" ]]; then
    warn "Pre-built packages are x86_64 only. On ${DISTRO_ARCH} you need to build from source."
    die "Unsupported architecture for pre-built packages: ${DISTRO_ARCH}"
fi

# ---- Run install ----
case "$FAMILY" in
    debian) install_debian ;;
    fedora) install_fedora ;;
    suse)   install_suse ;;
    arch)   install_arch ;;
    *)      install_tarball ;;
esac

# ---- Done ----
echo
ok "dictee ${RELEASE_TAG} installed successfully"
echo
echo "Next steps:"
echo "  ${C_BOLD}dictee-setup${C_OFF}    # run the first-run wizard"
echo "  ${C_BOLD}dictee --help${C_OFF}   # CLI usage"
echo
echo "Documentation: https://github.com/${REPO}"
