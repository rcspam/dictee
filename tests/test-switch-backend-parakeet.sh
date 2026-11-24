#!/bin/bash
# `dictee-switch-backend parakeet <v3|ultra> <fp32|int8>` writes the model and
# the quantization in one call (one daemon restart), for the plasmoid and the
# tray. systemctl / gdbus / notify-send are stubbed: the user's services are
# never touched.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d)"
mkdir -p "$T/bin" "$T/config"
for b in systemctl gdbus notify-send; do
    printf '#!/bin/sh\necho "%s $*" >> "%s/calls"\n' "$b" "$T" > "$T/bin/$b"
    chmod +x "$T/bin/$b"
done
export PATH="$T/bin:$PATH" XDG_CONFIG_HOME="$T/config" USER="sbtest$$"
CONF="$T/config/dictee.conf"
fail=0
check() {  # key expected
    local got; got=$(grep "^$1=" "$CONF" | tail -1 | cut -d= -f2)
    if [ "$got" = "$2" ]; then echo "PASS $1=$2"; else echo "FAIL $1: got '$got', want '$2'"; fail=1; fi
}

printf 'DICTEE_ASR_BACKEND=parakeet\nDICTEE_PARAKEET_QUANT=fp32\nDICTEE_FORCE_CPU=0\n' > "$CONF"
: > "$T/calls"
"$REPO/dictee-switch-backend" parakeet ultra int8 >/dev/null 2>&1
check DICTEE_PARAKEET_MODEL ultra
check DICTEE_PARAKEET_QUANT int8
# release/1.3: the daemon forces the CPU for int8 itself; the global flag,
# which would also put Whisper and Canary on the CPU, is left alone.
check DICTEE_FORCE_CPU 0
n=$(grep -c 'systemctl --user restart dictee.service' "$T/calls")
[ "$n" = 1 ] && echo "PASS one daemon restart" || { echo "FAIL restarts: $n"; fail=1; }

"$REPO/dictee-switch-backend" parakeet v3 fp32 >/dev/null 2>&1
check DICTEE_PARAKEET_MODEL v3
check DICTEE_PARAKEET_QUANT fp32
check DICTEE_FORCE_CPU 0

if "$REPO/dictee-switch-backend" parakeet v4 fp32 >/dev/null 2>&1; then
    echo "FAIL unknown model accepted"; fail=1
else
    echo "PASS unknown model refused"
fi
check DICTEE_PARAKEET_MODEL v3

rm -rf "${T:?}"
exit $fail
