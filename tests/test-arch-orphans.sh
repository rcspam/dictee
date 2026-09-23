#!/usr/bin/env bash
# What install.sh reports as orphans before makepkg on Arch. pacman refuses a
# package whose files already exist on disk, and it checks each path with
# lstat: a symlink whose target is gone blocks the install as much as a real
# file does. ldconfig leaves exactly that behind in /usr/lib/dictee after a
# CUDA tarball install is removed (libonnxruntime.so.1, pointing nowhere).
# Also covers the question that offers to remove them, with and without a
# terminal.
#
# Extracts check_arch_orphans() from install.sh, moves every path it scans
# under a temporary root, and runs it in a child bash against stand-ins for
# pacman and sudo. Nothing outside the temporary root is read or removed.
# The no-terminal case runs under setsid, the terminal case under script(1).
#
# Usage: bash tests/test-arch-orphans.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/install.sh"

fn=$(awk '/^    check_arch_orphans\(\) \{/{f=1} f{print} f&&/^    \}$/{exit}' "$SCRIPT")
[[ -n "$fn" ]] || { echo "FAIL: check_arch_orphans() not found in $SCRIPT"; exit 1; }
tty_fn=$(awk '/^have_tty\(\) \{/{f=1} f{print} f&&/\}$/{exit}' "$SCRIPT")
for t in setsid script; do
    command -v "$t" >/dev/null || { echo "FAIL: $t (util-linux) is needed"; exit 1; }
done

FAKE=$(mktemp -d)
trap 'rm -rf "$FAKE"' EXIT
fn=${fn//"/usr/"/"$FAKE/usr/"}
fn=${fn//"/etc/"/"$FAKE/etc/"}

fails=0
check() {  # label, got, expected
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: got '$2', expected '$3'"; fails=$((fails+1)); fi
}

# pacman -Qo PATH: owned when PATH is listed in owned.txt. sudo: just run it.
mkdir -p "$FAKE/bin"
printf '#!/bin/sh\ngrep -qxF "$2" "%s/owned.txt"\n' "$FAKE" > "$FAKE/bin/pacman"
printf '#!/bin/sh\nexec "$@"\n' > "$FAKE/bin/sudo"
chmod +x "$FAKE/bin/pacman" "$FAKE/bin/sudo"

make_fixtures() {
    rm -rf "$FAKE/usr"
    mkdir -p "$FAKE/usr/bin" "$FAKE/usr/lib/dictee" "$FAKE/usr/lib/systemd/user"
    # A tarball leftover nobody owns.
    echo x > "$FAKE/usr/bin/dictee-setup"
    # A file the installed package owns.
    echo x > "$FAKE/usr/bin/transcribe"
    echo "$FAKE/usr/bin/transcribe" > "$FAKE/owned.txt"
    # Two symlinks whose target is gone: one under a scanned glob, one in the
    # list of fixed paths.
    ln -s /nonexistent/libonnxruntime.so.1.23.0 "$FAKE/usr/lib/dictee/libonnxruntime.so.1"
    ln -s /nonexistent/dictee.service "$FAKE/usr/lib/systemd/user/dictee.service"
}
present() { [[ -e "$1" || -L "$1" ]] && echo yes || echo no; }

# The function under install.sh's options, with the helpers it calls.
case_script() {  # NON_INTERACTIVE value
    {
        echo 'set -euo pipefail'
        echo 'info() { echo "INFO $*"; }'
        echo 'ok()   { echo "OK $*"; }'
        echo 'warn() { echo "WARN $*"; }'
        echo 'die()  { echo "DIE $*"; exit 1; }'
        echo "$tty_fn"
        echo "$fn"
        echo "NON_INTERACTIVE=$1"
        echo "PATH=\"$FAKE/bin:\$PATH\""
        echo 'check_arch_orphans'
        echo 'echo RETURNED'
    } > "$FAKE/case.sh"
    echo "$FAKE/case.sh"
}

# --- What is reported (--non-interactive stops right after the list).
make_fixtures
out=$(bash "$(case_script 1)" 2>&1); rc=$?
listed() { grep -cxF "WARN   $1" <<<"$out"; }
check "dangling symlink in /usr/lib/dictee reported" \
    "$(listed "$FAKE/usr/lib/dictee/libonnxruntime.so.1")" "1"
check "dangling symlink among the fixed paths reported" \
    "$(listed "$FAKE/usr/lib/systemd/user/dictee.service")" "1"
check "leftover file reported" "$(listed "$FAKE/usr/bin/dictee-setup")" "1"
check "file owned by a package not reported" "$(listed "$FAKE/usr/bin/transcribe")" "0"
check "nothing else reported, no unexpanded glob" \
    "$(grep -c '^WARN Detected' <<<"$out") $(grep -o 'Detected [0-9]* orphan' <<<"$out")" \
    "1 Detected 3 orphan"
check "non-interactive mode stops before makepkg" "$rc" "1"

# --- The question, without a terminal: the default (remove) is taken quietly.
make_fixtures
out=$(setsid -w bash "$(case_script 0)" 2>"$FAKE/err" </dev/null); rc=$?
check "no terminal: nothing on stderr" "$(cat "$FAKE/err")" ""
check "no terminal: the install goes on" "$rc $(grep -c '^RETURNED$' <<<"$out")" "0 1"
check "no terminal: the orphans are removed" \
    "$(present "$FAKE/usr/bin/dictee-setup") $(present "$FAKE/usr/lib/dictee/libonnxruntime.so.1") $(present "$FAKE/usr/lib/systemd/user/dictee.service")" \
    "no no no"
check "no terminal: the owned file is kept" "$(present "$FAKE/usr/bin/transcribe")" "yes"

# --- The question, with a terminal: it shows, and "n" stops the install.
make_fixtures
out=$(printf 'n\n' | script -qec "bash $(case_script 0)" /dev/null 2>&1)
check "terminal: the question is shown" \
    "$(grep -cF 'Remove these orphan files now? [Y/n]' <<<"$out")" "1"
check "terminal: answering n stops the install" \
    "$(grep -cF 'DIE Aborted. Remove orphan files manually and retry.' <<<"$out")" "1"
check "terminal: answering n keeps the files" \
    "$(present "$FAKE/usr/bin/dictee-setup") $(present "$FAKE/usr/lib/dictee/libonnxruntime.so.1")" \
    "yes yes"

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; echo "--- last output"; echo "$out"; exit 1; fi
echo OK
