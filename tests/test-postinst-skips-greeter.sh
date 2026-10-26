#!/usr/bin/env bash
# The post-install scripts act on "every logged-in user": they add them to
# the input and docker groups, enable and restart dictee's user services,
# and notify them. They found those users with `loginctl list-sessions`,
# skipping root only. The login screen holds a logind session too, under its
# own system account (sddm, gdm, plasmalogin) with Class=greeter, so it was
# treated as a person: added to input and docker (docker is root-equivalent)
# and given running dictee services. Seen on arch-test: pacman.log of
# 2026-07-13 and 2026-10-12, dictee-ptt running as plasmalogin.
#
# Every loop must now go through _user_session_uids, which keeps the
# sessions of Class=user only. Reads the deb postinst/postrm, the two Arch
# .install files and the four rpm scriptlets (%post and %postun of the cpu
# and cuda specs in build-rpm.sh), then runs each copy of the helper against
# a fake loginctl.
#
# Usage: bash tests/test-postinst-skips-greeter.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fails=0
check() {  # label, got, expected
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: got '$2', expected '$3'"; fails=$((fails+1)); fi
}
code() { grep -v '^[[:space:]]*#'; }

# A fake loginctl, laid out like systemd 257: a greeter, a person with a
# graphical session and its service manager, and a second person on ssh.
FAKE="$(mktemp -d)"
trap 'rm -rf "$FAKE"' EXIT
cat > "$FAKE/loginctl" <<'FAKE_LOGINCTL'
#!/bin/sh
case "$1" in
    list-sessions)
        echo "  c1  964 plasmalogin seat0 812  greeter tty1  no  -"
        echo "   3 1000 raf         seat0 1430 user    tty2  no  -"
        echo "   4 1000 raf         -     1431 manager -     no  -"
        echo "   7 1001 bob         -     2210 user    pts/0 no  -"
        ;;
    show-session)
        case "$2" in c1) echo greeter ;; 3|7) echo user ;; 4) echo manager ;; esac
        ;;
esac
FAKE_LOGINCTL
chmod 755 "$FAKE/loginctl"

# Runs one copy of the helper (shell text) and prints the uids it yields.
run_helper() {
    PATH="$FAKE:$PATH" bash -c "$1"$'\n''_user_session_uids' 2>&1 | tr '\n' ' '
}
helper_of() { awk '/^_user_session_uids\(\) \{/{f=1} f; f && /^\}/{exit}'; }

for f in pkg/dictee/DEBIAN/postinst pkg/dictee/DEBIAN/postrm dictee.install dictee-cuda.install; do
    body=$(code < "$ROOT/$f")
    check "$f: no loop on the raw session list" \
        "$(grep -cE 'for uid in \$\(loginctl list-sessions' <<<"$body")" "0"
    check "$f: defines _user_session_uids once" \
        "$(grep -cE '^_user_session_uids\(\) \{' <<<"$body")" "1"
    check "$f: the helper keeps people, drops the greeter" \
        "$(run_helper "$(helper_of <<<"$body")")" "1000 1001 "
done

# build-rpm.sh: each scriptlet is its own shell, so each one that loops on
# the sessions defines the helper. The spec is an unquoted heredoc: expand it
# the same way before running the helper.
expand_heredoc() { eval "cat <<__SPEC__
$1
__SPEC__"; }
scriptlets=0
while IFS= read -r -d '' s; do
    name=$(head -1 <<<"$s")
    body=$(expand_heredoc "$(tail -n +2 <<<"$s" | code)")
    grep -qE 'loginctl list-sessions|_user_session_uids' <<<"$body" || continue
    scriptlets=$((scriptlets+1))
    check "build-rpm.sh $name #$scriptlets: no loop on the raw session list" \
        "$(grep -cE 'for uid in \$\(loginctl list-sessions' <<<"$body")" "0"
    check "build-rpm.sh $name #$scriptlets: the helper keeps people, drops the greeter" \
        "$(run_helper "$(helper_of <<<"$body")")" "1000 1001 "
done < <(awk '
    /^%post$|^%postun$/ { if (buf != "") printf "%s%c", buf, 0; buf = $0 "\n"; next }
    /^%|^EOF$/          { if (buf != "") printf "%s%c", buf, 0; buf = ""; next }
    buf != ""           { buf = buf $0 "\n" }
' "$ROOT/build-rpm.sh")
check "build-rpm.sh: four scriptlets loop on the sessions (cpu and cuda, %post and %postun)" \
    "$scriptlets" "4"

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; exit 1; fi
echo OK
