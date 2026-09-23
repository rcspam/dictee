#!/usr/bin/env bash
# What install.sh reports as orphans before makepkg on Arch: files a previous
# tarball install left at paths the package ships, which make pacman refuse it
# ("exists in filesystem"). pacman checks each path with lstat, so a symlink
# whose target is gone blocks the install as much as a real file does.
#
# /usr/lib/dictee also holds files no package owns that must stay: the links
# the CUDA post-install makes to the NVIDIA libraries of its venv, and the
# SONAME link ldconfig makes (libonnxruntime.so.1). Listing them would offer
# to delete them, and would stop a --non-interactive install for nothing.
# Also covers the question that offers the removal, with and without a
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
LIB="$FAKE/usr/lib/dictee"

fails=0
check() {  # label, got, expected
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: got '$2', expected '$3'"; fails=$((fails+1)); fi
}

# pacman -Qo PATH: owned when PATH is listed in owned.txt. sudo: just run it.
mkdir -p "$FAKE/bin"
printf '#!/bin/sh\ngrep -qxF "$2" "%s/owned.txt"\n' "$FAKE" > "$FAKE/bin/pacman"
printf '#!/bin/sh\nexec "$@"\n' > "$FAKE/bin/sudo"
chmod +x "$FAKE/bin/pacman" "$FAKE/bin/sudo"

reset_root() {
    rm -rf "$FAKE/usr" "$FAKE/venv"
    : > "$FAKE/owned.txt"
    mkdir -p "$FAKE/usr/bin" "$LIB" "$FAKE/usr/lib/systemd/user" "$FAKE/venv"
}
own() { local f; for f in "$@"; do echo "$f" >> "$FAKE/owned.txt"; done; }

# Links nobody owns that belong to the installed CUDA package's runtime.
runtime_links() {
    echo x > "$FAKE/venv/libcublas.so.12"
    ln -s libonnxruntime.so "$LIB/libonnxruntime.so.1"
    ln -s "$FAKE/venv/libcublas.so.12" "$LIB/libcublas.so.12"
    ln -s /nonexistent/venv/libcudnn.so.9 "$LIB/libcudnn.so.9"
}

# A CUDA tarball install replaced by the package, with its leftovers.
tarball_leftovers() {
    reset_root
    echo x > "$FAKE/usr/bin/dictee-setup"
    echo x > "$FAKE/usr/bin/transcribe"
    own "$FAKE/usr/bin/transcribe"
    local f
    for f in libonnxruntime.so libonnxruntime_providers_cuda.so \
             libonnxruntime_providers_shared.so setup-cuda-venv.sh dictee_models.py; do
        echo x > "$LIB/$f"
    done
    # A development install links shipped paths into a checkout; once the
    # checkout moves, the links dangle.
    ln -s /nonexistent/checkout/dictee-common.sh "$LIB/dictee-common.sh"
    ln -s /nonexistent/dictee.service "$FAKE/usr/lib/systemd/user/dictee.service"
    runtime_links
}

# The package alone, as its post-install and ldconfig leave it.
package_only() {
    reset_root
    local f
    for f in libonnxruntime.so libonnxruntime_providers_cuda.so \
             libonnxruntime_providers_shared.so setup-cuda-venv.sh \
             dictee-common.sh dictee_models.py; do
        echo x > "$LIB/$f"
        own "$LIB/$f"
    done
    runtime_links
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
tarball_leftovers
out=$(bash "$(case_script 1)" 2>&1); rc=$?
listed() { local f n=""; for f in "$@"; do n="$n$(grep -cxF "WARN   $f" <<<"$out")"; done; echo "$n"; }
check "leftover file reported" "$(listed "$FAKE/usr/bin/dictee-setup")" "1"
check "the tarball's files in /usr/lib/dictee reported" \
    "$(listed "$LIB/libonnxruntime.so" "$LIB/libonnxruntime_providers_cuda.so" \
              "$LIB/libonnxruntime_providers_shared.so" "$LIB/setup-cuda-venv.sh" \
              "$LIB/dictee_models.py")" "11111"
check "dangling symlink at a shipped path reported" "$(listed "$LIB/dictee-common.sh")" "1"
check "dangling symlink among the fixed paths reported" \
    "$(listed "$FAKE/usr/lib/systemd/user/dictee.service")" "1"
check "file owned by a package not reported" "$(listed "$FAKE/usr/bin/transcribe")" "0"
check "ldconfig and CUDA venv links not reported" \
    "$(listed "$LIB/libonnxruntime.so.1" "$LIB/libcublas.so.12" "$LIB/libcudnn.so.9")" "000"
check "nothing else reported, no unexpanded glob" \
    "$(grep -c '^WARN Detected' <<<"$out") $(grep -o 'Detected [0-9]* orphan' <<<"$out")" \
    "1 Detected 8 orphan"
check "non-interactive mode stops before makepkg" "$rc" "1"

# --- The package alone: nothing to report, a --non-interactive run goes on.
package_only
out=$(bash "$(case_script 1)" 2>&1); rc=$?
check "package alone: nothing reported, the install goes on" \
    "$rc $(grep -c '^RETURNED$' <<<"$out") $(grep -c 'Detected' <<<"$out")" "0 1 0"

# --- The question, without a terminal: the default (remove) is taken quietly.
tarball_leftovers
out=$(setsid -w bash "$(case_script 0)" 2>"$FAKE/err" </dev/null); rc=$?
check "no terminal: nothing on stderr" "$(cat "$FAKE/err")" ""
check "no terminal: the install goes on" "$rc $(grep -c '^RETURNED$' <<<"$out")" "0 1"
check "no terminal: the orphans are removed" \
    "$(present "$FAKE/usr/bin/dictee-setup") $(present "$LIB/libonnxruntime.so") $(present "$LIB/dictee-common.sh")" \
    "no no no"
check "no terminal: the owned file and the runtime links are kept" \
    "$(present "$FAKE/usr/bin/transcribe") $(present "$LIB/libonnxruntime.so.1") $(present "$LIB/libcublas.so.12") $(present "$LIB/libcudnn.so.9")" \
    "yes yes yes yes"

# --- The question, with a terminal: it shows, and "n" stops the install.
tarball_leftovers
out=$(printf 'n\n' | script -qec "bash $(case_script 0)" /dev/null 2>&1)
check "terminal: the question is shown" \
    "$(grep -cF 'Remove these orphan files now? [Y/n]' <<<"$out")" "1"
check "terminal: answering n stops the install" \
    "$(grep -cF 'DIE Aborted. Remove orphan files manually and retry.' <<<"$out")" "1"
check "terminal: answering n keeps the files" \
    "$(present "$FAKE/usr/bin/dictee-setup") $(present "$LIB/libonnxruntime.so")" \
    "yes yes"

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; echo "--- last output"; echo "$out"; exit 1; fi
echo OK
