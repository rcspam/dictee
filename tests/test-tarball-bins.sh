#!/usr/bin/env bash
# The tarball carries whatever build-tar.sh copies into usr/bin, but it is
# install.sh (mode_tarball) that puts those files on the system and
# uninstall.sh that takes them away, each from its own hand-written list.
# When the three drift, a binary ships in the archive and never gets
# installed: diarize-only and transcribe-diarize-batch were in the 1.3.7
# tarball and absent from both lists, so the live meeting window and the
# two-phase diarization were missing on every tarball install.
#
# Reads the three lists straight from the scripts and compares them as sets.
#
# Usage: bash tests/test-tarball-bins.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

lists=$(python3 - "$ROOT" <<'EOF'
import re, sys
root = sys.argv[1]
def words(s):
    return sorted(set(w for w in re.sub(r"\\\n", " ", s).split() if w and not w.startswith("#")))

# build-tar.sh: every `for X in …; do` loop whose body copies into usr/bin.
tar = open(f"{root}/build-tar.sh", encoding="utf-8").read()
shipped = set()
for var, items, body in re.findall(r"for (\w+) in ([^;]+); do\n(.*?)\n\s*done\b", tar, re.S):
    if "$TARBALL_DIR/usr/bin/" in body:
        shipped.update(words(items))

# install.sh: the bins=( … ) array of mode_tarball.
inst = open(f"{root}/install.sh", encoding="utf-8").read()
m = re.search(r"^mode_tarball\(\) \{.*?local bins=\((.*?)\)", inst, re.S | re.M)
installed = set(words(m.group(1))) if m else set()

# uninstall.sh: the `for bin in …; do` loop that removes $PREFIX/bin/$bin.
un = open(f"{root}/uninstall.sh", encoding="utf-8").read()
removed = set()
for var, items, body in re.findall(r"for (\w+) in ([^;]+); do\n(.*?)\n\s*done\b", un, re.S):
    if "$PREFIX/bin/$" + var in body:
        removed.update(words(items))

print(" ".join(sorted(shipped)))
print(" ".join(sorted(installed)))
print(" ".join(sorted(removed)))
EOF
)
shipped=$(sed -n 1p <<<"$lists"); installed=$(sed -n 2p <<<"$lists"); removed=$(sed -n 3p <<<"$lists")
[[ -n "$shipped" && -n "$installed" && -n "$removed" ]] || { echo "FAIL: could not read the three lists"; exit 1; }

fails=0
diff_sets() {  # label, got, expected
    local only_a only_b
    only_a=$(comm -23 <(tr ' ' '\n' <<<"$2" | sort) <(tr ' ' '\n' <<<"$3" | sort) | tr '\n' ' ')
    only_b=$(comm -13 <(tr ' ' '\n' <<<"$2" | sort) <(tr ' ' '\n' <<<"$3" | sort) | tr '\n' ' ')
    if [[ -z "$only_a" && -z "$only_b" ]]; then
        echo "PASS $1"
    else
        echo "FAIL $1: extra [${only_a% }] missing [${only_b% }]"; fails=$((fails+1))
    fi
}
diff_sets "install.sh installs every binary the tarball ships" "$installed" "$shipped"
diff_sets "uninstall.sh removes every binary the tarball ships" "$removed" "$shipped"

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; exit 1; fi
echo OK
