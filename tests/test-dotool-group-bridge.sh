#!/usr/bin/env bash
# How `dictee` runs dotool when its parent (plasmashell, the tray) lacks the
# input group the post-install just granted. Until 1.3.6 the wrapper was
# `sg input -c`, hard-coded; Arch dropped sg from shadow 4.20.0.arch1-1 (#35),
# so the text was never typed there and the error went to /dev/null.
#
# Extracts _dotool_group_bridge() from the dictee script and runs it against a
# PATH of stand-ins for id, sg and newgrp. Nothing touches uinput.
#
# Usage: bash tests/test-dotool-group-bridge.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/dictee"

fn=$(awk '/^_dotool_group_bridge\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$SCRIPT")
[[ -n "$fn" ]] || { echo "FAIL: _dotool_group_bridge() not found in $SCRIPT"; exit 1; }
eval "$fn"

fails=0
check() {  # label, got, expected
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: got '$2', expected '$3'"; fails=$((fails+1)); fi
}

stub_dir() {  # groups, sg?(1/0), newgrp help text ("" = no newgrp)
    local d; d=$(mktemp -d)
    printf '#!/bin/sh\necho "%s"\n' "$1" > "$d/id"; chmod +x "$d/id"
    if [[ "$2" == 1 ]]; then printf '#!/bin/sh\nexit 0\n' > "$d/sg"; chmod +x "$d/sg"; fi
    if [[ -n "$3" ]]; then printf '#!/bin/sh\nprintf "%%s\\n" "%s"\n' "$3" > "$d/newgrp"; chmod +x "$d/newgrp"; fi
    echo "$d"
}
SHADOW_HELP='Usage: newgrp [-] [group]'
UTIL_LINUX_HELP='Usage: newgrp <group> [[-c] <command>]  -c, --command <command>'

# The function needs grep and command; the real sg/newgrp must stay out of
# reach, so the PATH holds the stubs plus symlinks to the few base tools.
BASE=$(mktemp -d)
for t in grep sh; do ln -s "$(command -v $t)" "$BASE/$t"; done

run_case() {  # stub dir
    PATH="$1:$BASE" _dotool_group_bridge
}

check "group already effective: no wrapper" \
    "$(run_case "$(stub_dir 'raf input wheel' 1 "$UTIL_LINUX_HELP")")" ""
check "Debian/Fedora: sg" \
    "$(run_case "$(stub_dir 'raf wheel' 1 "$SHADOW_HELP")")" "sg input -c"
check "Arch: util-linux newgrp -c" \
    "$(run_case "$(stub_dir 'raf wheel' 0 "$UTIL_LINUX_HELP")")" "newgrp input -c"
check "sg preferred when both work" \
    "$(run_case "$(stub_dir 'raf wheel' 1 "$UTIL_LINUX_HELP")")" "sg input -c"
check "shadow newgrp without sg: no bridge, flagged" \
    "$(run_case "$(stub_dir 'raf wheel' 0 "$SHADOW_HELP")")" "none"
check "nothing installed: no bridge, flagged" \
    "$(run_case "$(stub_dir 'raf wheel' 0 "")")" "none"

# The script must not carry the old hard-coded helper any more.
check "no hard-coded 'sg input -c' left in dictee" "$(grep -c "sg input -c '" "$SCRIPT")" "0"
check "dotool stderr no longer dropped in the wrapper" \
    "$(awk '/^safe_dotool\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$SCRIPT" | grep -c '2>/dev/null')" "0"

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; exit 1; fi
echo OK
