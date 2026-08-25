#!/bin/bash
# Reproducer: killing dictee-plasmoid-level-daemon must leave no capture process
# behind. cleanup() kills $PAREC_PID, but for `a | b &` bash sets $! to the LAST
# element of the pipeline — so parec (the mic capture) survives the daemon.
#
# Runs against a copy of the daemon with its /dev/shm paths redirected into a
# temp dir, so it never disturbs a live session.
#
# Usage: test-level-daemon-cleanup.sh [path-to-dictee-plasmoid-level-daemon]
set -u

DAEMON_SRC="${1:-$(dirname "$0")/../pkg/dictee/usr/bin/dictee-plasmoid-level-daemon}"
[ -f "$DAEMON_SRC" ] || { echo "daemon not found: $DAEMON_SRC"; exit 2; }
WORK=$(mktemp -d /tmp/dictee-leveltest-XXXXXX)
trap 'pkill -f "$WORK/bin/parec" 2>/dev/null; rm -rf "$WORK"' EXIT

mkdir -p "$WORK/bin"

# Stand-ins for the real audio tools. parec writes a burst to get the pipeline
# going, then goes quiet forever: that is what a suspended PipeWire stream looks
# like after resume. It matters because a talkative parec dies on SIGPIPE as
# soon as the FFT is killed, which would hide the leak we are testing for.
# Both are marked with $WORK so pgrep can find exactly ours.
cat > "$WORK/bin/parec" <<EOF
#!/bin/bash
# marker: $WORK
printf 'xxxxxxxx'
sleep 3600
EOF
cat > "$WORK/bin/dictee-plasmoid-level-fft" <<EOF
#!/bin/bash
# marker: $WORK
while read -r -n 8 _chunk; do :; done
EOF
chmod +x "$WORK/bin/parec" "$WORK/bin/dictee-plasmoid-level-fft"

# Copy the daemon with its /dev/shm state redirected into the temp dir.
sed "s#/dev/shm/#$WORK/#g" "$DAEMON_SRC" > "$WORK/bin/level-daemon"
chmod +x "$WORK/bin/level-daemon"

export PATH="$WORK/bin:$PATH"
"$WORK/bin/level-daemon" 6 "" &
DAEMON_PID=$!

# Wait for the capture process to actually be up (max 5 s).
for _ in $(seq 1 50); do
    pgrep -f "$WORK/bin/parec" >/dev/null 2>&1 && break
    sleep 0.1
done

if ! pgrep -f "$WORK/bin/parec" >/dev/null 2>&1; then
    echo "SETUP FAILED: the capture process never started"
    kill $DAEMON_PID 2>/dev/null
    exit 2
fi
echo "setup ok: capture running (daemon pid=$DAEMON_PID)"

# What a session teardown does: SIGTERM the daemon, which runs its trap.
kill -TERM $DAEMON_PID 2>/dev/null
wait $DAEMON_PID 2>/dev/null

sleep 1

leaked_capture=$(pgrep -f "$WORK/bin/parec" 2>/dev/null | wc -l)
leaked_fft=$(pgrep -f "$WORK/bin/dictee-plasmoid-level-fft" 2>/dev/null | wc -l)

echo "after SIGTERM: capture=$leaked_capture fft=$leaked_fft"

if [ "$leaked_capture" -ne 0 ]; then
    echo "FAIL: the microphone capture survived the daemon ($leaked_capture process(es))"
    exit 1
fi
if [ "$leaked_fft" -ne 0 ]; then
    echo "FAIL: the FFT process survived the daemon ($leaked_fft process(es))"
    exit 1
fi
echo "PASS: no process left behind"
