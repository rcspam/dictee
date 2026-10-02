#!/usr/bin/env bash
# How the plasmoid asks whether the LibreTranslate container runs. Until 1.3.6
# its ltCheckCmd always went through `sg docker -c`; Arch dropped sg from shadow
# 4.20.0.arch1-1 (#35), so there the check printed nothing and the plasmoid
# showed LibreTranslate as stopped even while it ran.
#
# Extracts ltCheckCmd from main.qml (a QML string, possibly split with +) and
# runs it against a PATH of stand-ins for id, docker, sg and newgrp. The real
# docker is never called.
#
# Usage: bash tests/test-plasmoid-lt-check.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QML="$ROOT/plasmoid/package/contents/ui/main.qml"

cmd=$(python3 - "$QML" <<'EOF'
import json, re, sys
lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
start = next(i for i, l in enumerate(lines) if l.strip().startswith("property string ltCheckCmd:"))
expr = []
for l in lines[start:]:
    expr.append(l)
    if not l.rstrip().endswith("+"):
        break
lits = re.findall(r'"((?:[^"\\]|\\.)*)"', "\n".join(expr).split(":", 1)[1])
print("".join(json.loads('"' + s + '"') for s in lits))
EOF
)
[[ -n "$cmd" ]] || { echo "FAIL: ltCheckCmd not found in $QML"; exit 1; }

fails=0
check() {  # label, got, expected
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: got '$2', expected '$3'"; fails=$((fails+1)); fi
}

# Stand-ins. `id -nG` alone gives the groups of the running process (what
# plasmashell got at login); `id -nG "$USER"` reads /etc/group.
stub_dir() {  # effective groups, /etc/group groups, sg?(1/0), newgrp help ("" = none)
    local d; d=$(mktemp -d)
    cat > "$d/id" <<EOF
#!/bin/sh
if [ \$# -ge 2 ]; then echo "$2"; else echo "$1"; fi
EOF
    printf '#!/bin/sh\necho true\n' > "$d/docker"
    if [[ "$3" == 1 ]]; then
        printf '#!/bin/sh\n[ "$1" = docker ] && [ "$2" = -c ] || exit 9\nexec bash -c "$3"\n' > "$d/sg"
    fi
    if [[ -n "$4" ]]; then
        cat > "$d/newgrp" <<EOF
#!/bin/sh
if [ "\$1" = --help ]; then printf '%s\n' "$4"; exit 0; fi
case "$4" in *-c*) ;; *) exit 9 ;; esac
[ "\$1" = docker ] && [ "\$2" = -c ] || exit 9
exec bash -c "\$3"
EOF
    fi
    chmod +x "$d"/*
    echo "$d"
}
SHADOW_HELP='Usage: newgrp [-] [group]'
UTIL_LINUX_HELP='Usage: newgrp <group> [[-c] <command>]  -c, --command <command>'

# The real sg/newgrp/docker must stay out of reach: the PATH holds the stubs
# plus symlinks to the few base tools the command needs.
BASE=$(mktemp -d)
for t in bash sh grep; do ln -s "$(command -v $t)" "$BASE/$t"; done

run_case() {  # stub dir
    USER=raf PATH="$1:$BASE" sh -c "$cmd" 2>/dev/null
}

check "group effective, no sg (Arch after a new login)" \
    "$(run_case "$(stub_dir 'raf docker' 'raf docker' 0 "$UTIL_LINUX_HELP")")" "true"
check "group effective, sg present" \
    "$(run_case "$(stub_dir 'raf docker' 'raf docker' 1 "$SHADOW_HELP")")" "true"
check "group just added, sg (Debian/Fedora)" \
    "$(run_case "$(stub_dir 'raf' 'raf docker' 1 "$SHADOW_HELP")")" "true"
check "group just added, no sg, util-linux newgrp (Arch)" \
    "$(run_case "$(stub_dir 'raf' 'raf docker' 0 "$UTIL_LINUX_HELP")")" "true"
check "group just added, nothing can bridge it" \
    "$(run_case "$(stub_dir 'raf' 'raf docker' 0 "$SHADOW_HELP")")" "false"
check "not in the docker group" \
    "$(run_case "$(stub_dir 'raf' 'raf' 1 "$UTIL_LINUX_HELP")")" "false"

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; exit 1; fi
echo OK
