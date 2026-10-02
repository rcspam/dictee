#!/usr/bin/env bash
# Packages the .deb and .rpm pull in through Recommends, which apt and dnf
# install by default. pacman has no Recommends and never installs optdepends,
# so on Arch these must be hard depends, or nothing installs them:
#   python-numpy  the plasmoid level meter (dictee-plasmoid-level-fft)
#   wl-clipboard  the "paste" and "clipboard" output modes on Wayland
#   xclip         the same two modes on X11
# All three used to sit in optdepends, and install.sh did not add them either.
# packaging/dependencies.yaml carries the same rule (arch_kind: hard) and
# packaging/audit-deps.py checks the builders against it.
#
# Sources each PKGBUILD in a subshell (top level is plain assignments) and
# reads its arrays.
#
# Usage: bash tests/test-arch-depends.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUIRED=(python-numpy wl-clipboard xclip)

fails=0
check() {  # label, got, expected
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: got '$2', expected '$3'"; fails=$((fails+1)); fi
}

for pb in PKGBUILD PKGBUILD-cuda; do
    deps=$(cd "$ROOT" && source "./$pb" && printf '%s\n' "${depends[@]}")
    opts=$(cd "$ROOT" && source "./$pb" && printf '%s\n' "${optdepends[@]%%:*}")
    for p in "${REQUIRED[@]}"; do
        check "$pb: $p in depends" "$(grep -cx "$p" <<<"$deps")" "1"
        check "$pb: $p not also in optdepends" "$(grep -cx "$p" <<<"$opts")" "0"
    done
done

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; exit 1; fi
echo OK
