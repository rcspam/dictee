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
# 1. Every loop must now go through _user_session_uids, which keeps the
#    sessions of Class=user only.
# 2. Every post-install runs _clean_greeter_accounts, which undoes what the
#    old ones left on the display managers' accounts: input and docker
#    membership, dictee units enabled in their home.
#
# Reads the deb postinst/postrm, the two Arch .install files, the rpm
# scriptlets (%post and %postun of the cpu and cuda specs in build-rpm.sh)
# and install.sh, then runs each copy of the helpers against fake tools.
#
# Usage: bash tests/test-postinst-skips-greeter.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fails=0
check() {  # label, got, expected
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: got '$2', expected '$3'"; fails=$((fails+1)); fi
}
code() { grep -v '^[[:space:]]*#'; }

FAKE="$(mktemp -d)"
trap 'rm -rf "$FAKE"' EXIT
mkdir -p "$FAKE/bin"

# A fake loginctl, laid out like systemd 257: a greeter, a person with a
# graphical session and its service manager, and a second person on ssh.
cat > "$FAKE/bin/loginctl" <<'EOF_FAKE'
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
EOF_FAKE

# Accounts for the clean-up: plasmalogin was put in input and docker and got
# dictee units enabled by an old post-install; raf is a person and must be
# left alone even though it is in the same groups.
cat > "$FAKE/bin/getent" <<EOF_FAKE
#!/bin/sh
[ "\$1" = passwd ] || exit 2
case "\$2" in
    plasmalogin) echo "plasmalogin:x:964:964:Greeter:$FAKE/home/plasmalogin:/usr/bin/nologin" ;;
    raf)         echo "raf:x:1000:1000::$FAKE/home/raf:/bin/bash" ;;
    *) exit 2 ;;
esac
EOF_FAKE
cat > "$FAKE/bin/id" <<'EOF_FAKE'
#!/bin/sh
case "$1 $2" in
    "-nG plasmalogin") echo "plasmalogin input docker" ;;
    "-nG raf")         echo "raf wheel input docker" ;;
    "-u plasmalogin")  echo 964 ;;
    "-u raf")          echo 1000 ;;
    *) exit 1 ;;
esac
EOF_FAKE
cat > "$FAKE/bin/gpasswd" <<EOF_FAKE
#!/bin/sh
echo "gpasswd \$*" >> "$FAKE/calls"
EOF_FAKE
cat > "$FAKE/bin/sudo" <<EOF_FAKE
#!/bin/sh
echo "sudo \$*" >> "$FAKE/calls"
EOF_FAKE
chmod 755 "$FAKE/bin/"*

# The home an old post-install left: dictee units enabled for the greeter,
# next to a unit that is not ours and must stay.
fresh_homes() {
    rm -rf "$FAKE/home" "$FAKE/calls"; touch "$FAKE/calls"
    local u="$FAKE/home/plasmalogin/.config/systemd/user"
    mkdir -p "$u/default.target.wants" "$u/graphical-session.target.wants"
    ln -s /usr/lib/systemd/user/dictee.service "$u/default.target.wants/dictee.service"
    ln -s /usr/lib/systemd/user/dictee-ptt.service "$u/graphical-session.target.wants/dictee-ptt.service"
    ln -s /usr/lib/systemd/user/dictee-tray.service "$u/graphical-session.target.wants/dictee-tray.service"
    ln -s /usr/lib/systemd/user/pipewire.service "$u/default.target.wants/pipewire.service"
    u="$FAKE/home/raf/.config/systemd/user/graphical-session.target.wants"
    mkdir -p "$u"
    ln -s /usr/lib/systemd/user/dictee-ptt.service "$u/dictee-ptt.service"
}

helper_of() { awk -v f="$1" '$0 ~ "^"f"\\(\\) \\{" {p=1} p; p && /^\}/{exit}'; }

# Runs one copy of _user_session_uids and prints the uids it yields.
run_uids() {
    PATH="$FAKE/bin:$PATH" bash -c "$1"$'\n''_user_session_uids' 2>&1 | tr '\n' ' '
}

# Runs one copy of _clean_greeter_accounts under the strictest caller
# (install.sh: set -euo pipefail) and checks what it changed.
check_cleanup() {  # label, helper text
    fresh_homes
    local out
    out=$(PATH="$FAKE/bin:$PATH" bash -c "set -euo pipefail"$'\n'"$2"$'\n''_clean_greeter_accounts; echo done' 2>&1)
    check "$1: runs to the end under set -euo pipefail" "$(tail -1 <<<"$out")" "done"
    check "$1: greeter leaves input and docker, nobody else touched" \
        "$(grep gpasswd "$FAKE/calls" | sort | tr '\n' ';')" "gpasswd -d plasmalogin docker;gpasswd -d plasmalogin input;"
    check "$1: greeter's dictee units gone, its other units kept" \
        "$(cd "$FAKE/home/plasmalogin/.config/systemd/user" && find . ! -type d | sort | tr '\n' ' ')" \
        "./default.target.wants/pipewire.service "
    check "$1: a person's dictee units kept" \
        "$(cd "$FAKE/home/raf/.config/systemd/user" && find . ! -type d | tr '\n' ' ')" \
        "./graphical-session.target.wants/dictee-ptt.service "
}

# --- deb, Arch -------------------------------------------------------------
for f in pkg/dictee/DEBIAN/postinst pkg/dictee/DEBIAN/postrm dictee.install dictee-cuda.install; do
    body=$(code < "$ROOT/$f")
    check "$f: no loop on the raw session list" \
        "$(grep -cE 'for uid in \$\(loginctl list-sessions' <<<"$body")" "0"
    check "$f: defines _user_session_uids once" \
        "$(grep -cE '^_user_session_uids\(\) \{' <<<"$body")" "1"
    check "$f: the helper keeps people, drops the greeter" \
        "$(run_uids "$(helper_of _user_session_uids <<<"$body")")" "1000 1001 "
done

# The installs and upgrades clean up; removal has nothing to clean.
for f in pkg/dictee/DEBIAN/postinst:1 dictee.install:2 dictee-cuda.install:2; do
    calls=${f#*:}; f=${f%:*}
    body=$(code < "$ROOT/$f")
    check "$f: defines _clean_greeter_accounts once" \
        "$(grep -cE '^_clean_greeter_accounts\(\) \{' <<<"$body")" "1"
    check "$f: calls it $calls time(s)" \
        "$(grep -cE '^[[:space:]]*_clean_greeter_accounts$' <<<"$body")" "$calls"
    check_cleanup "$f" "$(helper_of _clean_greeter_accounts <<<"$body")"
done

# --- rpm -------------------------------------------------------------------
# Each scriptlet is its own shell, so each one defines what it uses. The spec
# is an unquoted heredoc: expand it the same way before running the helpers.
expand_heredoc() { eval "cat <<__SPEC__
$1
__SPEC__"; }
scriptlets=0; posts=0
while IFS= read -r -d '' s; do
    name=$(head -1 <<<"$s")
    body=$(expand_heredoc "$(tail -n +2 <<<"$s" | code)")
    if [[ $name == %post ]]; then
        posts=$((posts+1))
        check "build-rpm.sh %post #$posts: calls _clean_greeter_accounts once" \
            "$(grep -cE '^[[:space:]]*_clean_greeter_accounts$' <<<"$body")" "1"
        check_cleanup "build-rpm.sh %post #$posts" "$(helper_of _clean_greeter_accounts <<<"$body")"
    fi
    grep -qE 'loginctl list-sessions|_user_session_uids' <<<"$body" || continue
    scriptlets=$((scriptlets+1))
    check "build-rpm.sh $name #$scriptlets: no loop on the raw session list" \
        "$(grep -cE 'for uid in \$\(loginctl list-sessions' <<<"$body")" "0"
    check "build-rpm.sh $name #$scriptlets: the helper keeps people, drops the greeter" \
        "$(run_uids "$(helper_of _user_session_uids <<<"$body")")" "1000 1001 "
done < <(awk '
    /^%post$|^%postun$/ { if (buf != "") printf "%s%c", buf, 0; buf = $0 "\n"; next }
    /^%|^EOF$/          { if (buf != "") printf "%s%c", buf, 0; buf = ""; next }
    buf != ""           { buf = buf $0 "\n" }
' "$ROOT/build-rpm.sh")
check "build-rpm.sh: four scriptlets loop on the sessions (cpu and cuda, %post and %postun)" \
    "$scriptlets" "4"
check "build-rpm.sh: two %post scriptlets (cpu and cuda)" "$posts" "2"

# --- tarball ---------------------------------------------------------------
# install.sh targets $SUDO_USER, never the session list, but a machine moving
# from an old package to the tarball keeps what that package left.
body=$(code < "$ROOT/install.sh")
check "install.sh: defines _clean_greeter_accounts once" \
    "$(grep -cE '^_clean_greeter_accounts\(\) \{' <<<"$body")" "1"
check "install.sh: mode_tarball calls it" \
    "$(awk '/^mode_tarball\(\) \{/{p=1} p && /^\}/{exit} p' <<<"$body" | grep -cE '^[[:space:]]*_clean_greeter_accounts$')" "1"
check_cleanup "install.sh" "$(helper_of _clean_greeter_accounts <<<"$body")"

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; exit 1; fi
echo OK
