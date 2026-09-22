#!/usr/bin/env bash
# A failing sound-server call must not cancel the dictation.
#
# dictee installs `trap 'cleanup_on_error $LINENO' ... ERR` for the whole
# recording path. A bare `var=$(cmd)` whose cmd exits non-zero fires that
# trap, and cleanup_on_error runs stop_recording + restore_audio + the
# "Enregistrement interrompu" notification: the dictation dies before
# pw-record ever starts.
#
# It happened for real on 2026-09-22 (dictee-error-1000.log, line 2101,
# exit=1, 15 times in four minutes): `pactl get-default-sink` returns 1
# while the sound server is busy, which a Bluetooth sink reconnecting is
# enough to cause. The headset detection added for issue #37 put that call
# on the start path, so every dictation attempt was cancelled.
#
# This test runs the real lines from `dictee` against a pactl/wpctl that
# always fail, under the same trap, and checks nothing fires.
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

# Every sound-server call in the audio block, each failing the way pactl
# does when it cannot reach the server.
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
# code: from the mute setting down to the decision log.
block=$(awk '/^        _mute_setting=/, /^        _dbg "output:/' "$DICTEE")
if [ -z "$block" ]; then
    echo "FAIL could not find the audio block in $DICTEE"
    exit 1
fi

# The helpers the block calls, plus a _dbg that says nothing.
helpers=$(awk '/^_sink_is_headset\(\) \{/, /^\}/' "$DICTEE"
          awk '/^_duck_target\(\) \{/, /^\}/' "$DICTEE"
          awk '/^_pct_to_fraction\(\) \{/, /^\}/' "$DICTEE"
          awk '/^_sink_volume\(\) \{/, /^\}/' "$DICTEE"
          awk '/^_should_mute_output\(\) \{/, /^\}/' "$DICTEE"
          awk '/^_output_action\(\) \{/, /^\}/' "$DICTEE")

run_block() {
    # Same trap as the recording path, reporting instead of cancelling.
    PATH="$stub_dir:$PATH" bash -c "
        $helpers
        _dbg() { :; }
        trap 'echo \"ERR-TRAP line \$LINENO\"' ERR
        ${DICTEE_MUTE_OUTPUT:+DICTEE_MUTE_OUTPUT=$DICTEE_MUTE_OUTPUT}
        ${DICTEE_DUCK_LEVEL:+DICTEE_DUCK_LEVEL=$DICTEE_DUCK_LEVEL}
        ${DICTEE_DUCK_LEVEL_HEADSET:+DICTEE_DUCK_LEVEL_HEADSET=$DICTEE_DUCK_LEVEL_HEADSET}
$block
        echo \"REACHED-END is_headset=\$_is_headset action=\$_action\"
    " 2>/dev/null
}

DICTEE_MUTE_OUTPUT="" DICTEE_DUCK_LEVEL="" DICTEE_DUCK_LEVEL_HEADSET="" \
    out=$(DICTEE_MUTE_OUTPUT= DICTEE_DUCK_LEVEL= DICTEE_DUCK_LEVEL_HEADSET= run_block)
check "no ERR trap when the sound server is unreachable" \
    "$(printf '%s' "$out" | grep -c 'ERR-TRAP')" "0"
check "the block still reaches its decision" \
    "$(printf '%s' "$out" | grep -c 'REACHED-END')" "1"

# The user's own setup when the bug hit: a duck level set on both rows.
out=$(DICTEE_MUTE_OUTPUT=auto DICTEE_DUCK_LEVEL=15 DICTEE_DUCK_LEVEL_HEADSET=100 run_block)
check "no ERR trap with both duck levels set" \
    "$(printf '%s' "$out" | grep -c 'ERR-TRAP')" "0"
check "an unreachable server means no headset, so the speaker level applies" \
    "$(printf '%s' "$out" | sed -n 's/.*REACHED-END is_headset=\([a-z]*\) action=\(.*\)/\1 \2/p')" \
    "no 15"

if [ "$fails" -gt 0 ]; then
    echo
    echo "$fails FAILED"
    exit 1
fi
echo
echo "OK"
