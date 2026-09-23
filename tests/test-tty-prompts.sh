#!/usr/bin/env bash
# The questions install.sh and uninstall.sh ask on /dev/tty. Without a
# terminal (a service, the QEMU guest agent, a CI job) the shell cannot open
# /dev/tty and printed its own error before falling back to the default
# answer; [[ -r /dev/tty ]] did not help, the node is readable and only
# open() fails. With a terminal, the question must still show and the answer
# must still count.
#
# Extracts ask_yes_no() from uninstall.sh and have_tty() from install.sh. The
# no-terminal cases run under setsid, so they have no controlling terminal
# even when this test is started from one; the terminal cases run under
# script(1), which gives them a pty.
#
# Usage: bash tests/test-tty-prompts.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ask_fn=$(awk '/^ask_yes_no\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$ROOT/uninstall.sh")
[[ -n "$ask_fn" ]] || { echo "FAIL: ask_yes_no() not found in uninstall.sh"; exit 1; }
tty_fn=$(awk '/^have_tty\(\) \{/{f=1} f{print} f&&/\}$/{exit}' "$ROOT/install.sh")
[[ -n "$tty_fn" ]] || { echo "FAIL: have_tty() not found in install.sh"; exit 1; }
for t in setsid script; do
    command -v "$t" >/dev/null || { echo "FAIL: $t (util-linux) is needed"; exit 1; }
done

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

fails=0
check() {  # label, got, expected
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: got '$2', expected '$3'"; fails=$((fails+1)); fi
}

# --- uninstall.sh: one question with the given default, under its options.
ask_script() {  # default answer
    {
        echo 'set -euo pipefail'
        echo 'NON_INTERACTIVE=0'
        echo "$ask_fn"
        echo "ask_yes_no 'Proceed with uninstall?' $1"
        echo 'echo "REPLY=$REPLY"'
    } > "$T/ask-$1.sh"
    echo "$T/ask-$1.sh"
}

for d in y n; do
    out=$(setsid -w bash "$(ask_script "$d")" 2>"$T/err" </dev/null); rc=$?
    check "uninstall, no terminal, default $d: the default is taken" "$out" "REPLY=$d"
    check "uninstall, no terminal, default $d: nothing on stderr" "$(cat "$T/err")" ""
    check "uninstall, no terminal, default $d: exit status" "$rc" "0"
done

out=$(printf 'n\n' | script -qec "bash $(ask_script y)" /dev/null 2>&1)
check "uninstall, terminal: the question is shown" \
    "$(grep -cF 'Proceed with uninstall? [Y/n]' <<<"$out")" "1"
check "uninstall, terminal: the answer typed counts" "$(grep -cF 'REPLY=n' <<<"$out")" "1"

# --- install.sh: the probe its questions go through.
{
    echo 'set -euo pipefail'
    echo "$tty_fn"
    echo 'if have_tty; then echo "TTY=yes"; else echo "TTY=no"; fi'
} > "$T/have.sh"

out=$(setsid -w bash "$T/have.sh" 2>"$T/err" </dev/null)
check "install, no terminal: no terminal found" "$out" "TTY=no"
check "install, no terminal: nothing on stderr" "$(cat "$T/err")" ""
out=$(script -qec "bash $T/have.sh" /dev/null </dev/null 2>&1)
check "install, terminal: the terminal is found" "$(grep -cF 'TTY=yes' <<<"$out")" "1"

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; exit 1; fi
echo OK
