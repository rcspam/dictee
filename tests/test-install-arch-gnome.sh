#!/usr/bin/env bash
# The GNOME tray on Arch. dictee-tray needs python-gobject and
# libayatana-appindicator for its AppIndicator backend, and GNOME Shell needs
# the appindicator extension to show it. The .deb and .rpm pull the two
# libraries as Recommends and install.sh adds the extension on GNOME; on Arch
# all three are optdepends, which pacman never installs, and the Arch path of
# install.sh did nothing: no tray icon on GNOME. install_arch_gnome_tray()
# installs the three when the desktop is GNOME, like the Debian and Fedora
# paths, and stays out of the way elsewhere.
#
# Extracts the function from install.sh and runs it against a sudo stand-in
# that records what it is asked to run. Nothing is installed.
#
# Usage: bash tests/test-install-arch-gnome.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fn=$(awk '/^install_arch_gnome_tray\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$ROOT/install.sh")
[[ -n "$fn" ]] || { echo "FAIL: install_arch_gnome_tray() not found in install.sh"; exit 1; }
for h in info ok warn; do eval "$h() { :; }"; done
eval "$fn"

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"
cat > "$T/bin/sudo" <<EOF
#!/bin/sh
echo "\$*" >> "$T/calls"
EOF
chmod +x "$T/bin/sudo"

fails=0
check() {  # label, got, expected
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: got '$2', expected '$3'"; fails=$((fails+1)); fi
}
run_case() {  # desktop
    rm -f "$T/calls"
    XDG_CURRENT_DESKTOP="$1" PATH="$T/bin:$PATH" install_arch_gnome_tray >/dev/null 2>&1
    cat "$T/calls" 2>/dev/null || true
}

check "GNOME: the three tray packages, via pacman --needed" \
    "$(run_case GNOME)" \
    "pacman -S --needed --noconfirm python-gobject libayatana-appindicator gnome-shell-extension-appindicator"
check "ubuntu:GNOME spelling is still GNOME" \
    "$(run_case ubuntu:GNOME | grep -c pacman)" "1"
check "KDE: nothing installed" "$(run_case KDE)" ""
check "no desktop variable: nothing installed" "$(run_case '')" ""

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; exit 1; fi
echo OK
