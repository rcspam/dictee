#!/bin/bash
# The plasmoid level meter without numpy. dictee-plasmoid-level-fft imports
# numpy on its first lines; when numpy is missing it dies at once, the daemon
# sees its pipeline end and exits, and the meter stays flat. The daemon has a
# plain RMS fallback, which must take over in that case. With numpy present,
# the FFT path must still be the one used.
#
# numpy is faked through PYTHONPATH, so the result does not depend on what the
# machine has installed: an empty module for "present", a module that raises
# ImportError for "missing". Runs a copy of the daemon with its /dev/shm paths
# redirected into a temp dir, so it never disturbs a live session.
#
# Usage: bash tests/test-level-daemon-no-numpy.sh
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAEMON_SRC="$ROOT/pkg/dictee/usr/bin/dictee-plasmoid-level-daemon"
FFT_SRC="$ROOT/pkg/dictee/usr/bin/dictee-plasmoid-level-fft"
for f in "$DAEMON_SRC" "$FFT_SRC"; do
    [ -f "$f" ] || { echo "not found: $f"; exit 2; }
done

WORK=$(mktemp -d /tmp/dictee-nonumpy-XXXXXX)
DAEMON_PID=""
stop_daemon() {
    [ -n "$DAEMON_PID" ] && kill -TERM "$DAEMON_PID" 2>/dev/null && wait "$DAEMON_PID" 2>/dev/null
    DAEMON_PID=""
    pkill -f "$WORK/" 2>/dev/null
    sleep 0.2
}
trap 'stop_daemon; rm -rf "$WORK"' EXIT

mkdir -p "$WORK/bin" "$WORK/np-ok/numpy" "$WORK/np-missing/numpy"
: > "$WORK/np-ok/numpy/__init__.py"
echo 'raise ImportError("No module named numpy (test)")' > "$WORK/np-missing/numpy/__init__.py"

# A microphone that never stops: 80 ms blocks of loud s16le samples (0x3fff).
cat > "$WORK/bin/parec" <<EOF
#!/bin/bash
# marker: $WORK
block=\$(printf '\\\\xff\\\\x3f%.0s' \$(seq 1 1280))
while :; do printf "\$block" || exit 0; sleep 0.08; done
EOF
chmod +x "$WORK/bin/parec"

sed "s#/dev/shm/#$WORK/#g" "$DAEMON_SRC" > "$WORK/bin/level-daemon"
chmod +x "$WORK/bin/level-daemon"
BANDS="$WORK/.dictee_audio_bands"
export PATH="$WORK/bin:$PATH"

fails=0
start_daemon() {
    rm -f "$BANDS"
    "$WORK/bin/level-daemon" 6 "" &
    DAEMON_PID=$!
}
# Waits up to 4 s for the bands file to hold $1 (an awk condition on its fields).
wait_bands() {
    for _ in $(seq 1 40); do
        if [ -f "$BANDS" ] && awk "{ $1 }" "$BANDS" 2>/dev/null | grep -q yes; then
            return 0
        fi
        sleep 0.1
    done
    return 1
}

# --- numpy present: the FFT script runs. A stand-in writes a marker band.
cat > "$WORK/bin/dictee-plasmoid-level-fft" <<EOF
#!/bin/bash
# marker: $WORK
while :; do printf '0.777 ' > "\$2"; sleep 0.1; done
EOF
chmod +x "$WORK/bin/dictee-plasmoid-level-fft"
export PYTHONPATH="$WORK/np-ok"
start_daemon
if wait_bands 'if ($1 == "0.777") print "yes"'; then
    echo "PASS numpy present: the FFT path is used"
else
    echo "FAIL numpy present: the FFT path was not used (bands: $(cat "$BANDS" 2>/dev/null || echo none))"
    fails=$((fails+1))
fi
stop_daemon

# --- numpy missing: the real FFT script dies on import; RMS must take over.
cp "$FFT_SRC" "$WORK/bin/dictee-plasmoid-level-fft"
chmod +x "$WORK/bin/dictee-plasmoid-level-fft"
export PYTHONPATH="$WORK/np-missing"
start_daemon
if wait_bands 'for (i = 1; i <= NF; i++) if ($i + 0 > 0) { print "yes"; exit }'; then
    echo "PASS numpy missing: the RMS fallback shows the level"
else
    alive=no; kill -0 "$DAEMON_PID" 2>/dev/null && alive=yes
    echo "FAIL numpy missing: no level (daemon alive: $alive, bands: $(cat "$BANDS" 2>/dev/null || echo none))"
    fails=$((fails+1))
fi
stop_daemon

[ "$fails" -eq 0 ] && echo "ALL PASS" || echo "$fails FAILED"
exit "$fails"
