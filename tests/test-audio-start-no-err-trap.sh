#!/usr/bin/env bash
# A failing sound-server call must not cancel the dictation.
#
# dictee installs `trap 'cleanup_on_error $LINENO' ... ERR` for the whole
# recording path. Any command that exits non-zero there fires that trap,
# and cleanup_on_error runs stop_recording + restore_audio + the
# "Enregistrement interrompu" notification: the dictation dies before
# pw-record ever starts.
#
# It happened for real on 2026-09-22 (dictee-error-1000.log, line 2101,
# exit=1, fifteen times in four minutes): `pactl get-default-sink` returns 1
# while the sound server is busy, which a Bluetooth sink reconnecting is
# enough to cause. The headset detection added for issue #37 put that call
# on the start path, so every push-to-talk press was cancelled.
#
# This test takes the real audio block out of `dictee`, runs it under the
# same trap against a pactl/wpctl that always fail, and checks nothing
# fires. Every way the block can go gets its own run: the guards must hold
# whether the output ends up muted, ducked or left alone.
#
# Run: bash tests/test-audio-start-no-err-trap.sh
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DICTEE="$ROOT/dictee"
fails=0

check() {
    if [ "$2" = "$3" ]; then
        echo "PASS $1"
    else
        echo "FAIL $1: got '$2', expected '$3'"
        fails=$((fails + 1))
    fi
}

# pactl and wpctl failing the way they do when the server is unreachable.
stub_dir=$(mktemp -d)
trap 'rm -rf "$stub_dir"' EXIT
for cmd in pactl wpctl; do
    cat >"$stub_dir/$cmd" <<'STUB'
#!/bin/sh
echo "Connection failure: Connection terminated" >&2
exit 1
STUB
    chmod +x "$stub_dir/$cmd"
done

# The block under test, taken from dictee itself so the test follows the
# code: everything inside `if [ "$_IS_APP_SOURCE" = false ]`, mic unmute and
# output decision alike, without that `if`'s own two lines.
block=$(awk '/^    if \[ "\$_IS_APP_SOURCE" = false \]; then/, /^    fi$/' "$DICTEE" | sed '1d;$d')
if [ -z "$block" ] || ! printf '%s' "$block" | grep -q "_output_action"; then
    echo "FAIL could not find the audio block in $DICTEE"
    exit 1
fi

# The helpers it calls, straight from the script as well.
helpers=""
for fn in _sink_is_headset _duck_target _pct_to_fraction _sink_volume \
          _should_mute_output _output_action; do
    helpers="$helpers
$(awk "/^${fn}\\(\\) \\{/, /^\\}/" "$DICTEE")"
done

run_block() {
    PATH="$stub_dir:$PATH" bash -c "
        $helpers
        _dbg() { :; }
        SINK_MUT_FILE=\$(mktemp)
        MUT_FILE=\$(mktemp)
        _PA_SOURCE=any.source
        DICTEE_MUTE_OUTPUT='$1'
        DICTEE_DUCK_LEVEL='$2'
        DICTEE_DUCK_LEVEL_HEADSET='$3'
        trap 'echo \"ERR-TRAP: \$BASH_COMMAND\"' ERR
$block
        echo \"REACHED-END is_headset=\$_is_headset action=\$_action\"
        rm -f \"\$SINK_MUT_FILE\" \"\$MUT_FILE\"
    " 2>/dev/null
}

# label | setting | speaker level | headset level
while IFS='|' read -r label setting level head; do
    [ -n "$label" ] || continue
    out=$(run_block "$setting" "$level" "$head")
    check "no ERR trap, $label" \
        "$(printf '%s' "$out" | grep -c 'ERR-TRAP')" "0"
    check "the block runs to the end, $label" \
        "$(printf '%s' "$out" | grep -c 'REACHED-END')" "1"
done <<'CASES'
a plain mute (no level set)|auto||
both levels set, the setup that broke|auto|15|100
the mute forced on|true||
the mute turned off|false||
zero on both, muting speakers and headset|auto|0|0
CASES

# An unreachable server cannot tell a headset from speakers: the answer must
# be "no", so the speaker level applies rather than the headset one.
out=$(run_block auto 15 100)
check "an unreachable server means no headset" \
    "$(printf '%s' "$out" | sed -n 's/.*REACHED-END is_headset=\([a-z]*\).*/\1/p')" "no"
check "so the speaker level is what gets applied" \
    "$(printf '%s' "$out" | sed -n 's/.*action=\(.*\)/\1/p')" "15"

if [ "$fails" -gt 0 ]; then
    echo
    echo "$fails FAILED"
    exit 1
fi
echo
echo "OK"
