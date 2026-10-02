#!/usr/bin/env bash
# dotool's daemon, dotoold, is not something dictee talks to: the text is
# typed through the one-shot `dotool`, and no script ever called dotoolc. A
# March 2026 attempt at the fresh-install shortcut problem made every
# installer enable and restart dotoold anyway. Started right after the
# install, before the user's next login, it cannot open /dev/uinput and
# fails in a loop; afterwards it runs for nothing.
#
# Every post-install must now leave dotoold alone, and switch off the one an
# earlier version enabled. Reads the five installers; the rpm scriptlets are
# the two %post sections of build-rpm.sh.
#
# Usage: bash tests/test-dotoold-not-started.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fails=0
check() {  # label, got, expected
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: got '$2', expected '$3'"; fails=$((fails+1)); fi
}
# Lines that do something, comments left out.
code() { grep -v '^[[:space:]]*#' "$1"; }

for f in pkg/dictee/DEBIAN/postinst dictee.install dictee-cuda.install install.sh; do
    check "$f: no 'enable … dotoold'" \
        "$(code "$ROOT/$f" | grep -cE 'systemctl --user enable[^#]*\bdotoold\b')" "0"
    check "$f: no 'restart dotoold'" \
        "$(code "$ROOT/$f" | grep -cE 'restart[^#]*\bdotoold\b')" "0"
    check "$f: switches dotoold off" \
        "$(code "$ROOT/$f" | grep -cE 'disable --now dotoold')" "1"
done

# build-rpm.sh carries two %post scriptlets (cpu, cuda): each must do the same.
rpm_post=$(awk '/^%post$/{f=1;next} /^%postun$/{f=0} f' "$ROOT/build-rpm.sh" | grep -v '^[[:space:]]*#')
check "build-rpm.sh %post: no 'enable … dotoold'" \
    "$(grep -cE 'systemctl --user enable[^#]*\bdotoold\b' <<<"$rpm_post")" "0"
check "build-rpm.sh %post: no 'restart dotoold'" \
    "$(grep -cE 'restart[^#]*\bdotoold\b' <<<"$rpm_post")" "0"
check "build-rpm.sh %post: switches dotoold off in both variants" \
    "$(grep -cE 'disable --now dotoold' <<<"$rpm_post")" "2"

# The preset shipped with the packages must not enable it either.
check "90-dictee.preset keeps dotoold disabled" \
    "$(grep -c '^disable dotoold.service' "$ROOT/pkg/dictee/usr/lib/systemd/user-preset/90-dictee.preset")" "1"

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; exit 1; fi
echo OK
