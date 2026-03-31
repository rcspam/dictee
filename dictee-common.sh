#!/bin/bash
# dictee-common.sh — Shared functions and variables for all dictee shell scripts.
# Source this file at the top of each script:
#   _DBG_CONTEXT="my-script"
#   for _p in "$(dirname "$(readlink -f "$0")")" /usr/lib/dictee; do
#       [ -f "$_p/dictee-common.sh" ] && { source "$_p/dictee-common.sh"; break; }
#   done
#
# Provides: _dbg, write_state, notify_dictee, close_notification, asr_service,
#           NOTIFY_ID, STATE_FILE, STATE_LOCK, _UID_SUFFIX, _DBG_LOG

# === SHARED VARIABLES ===

_UID_SUFFIX="-$(id -u)"
DICTEE_CONF="${DICTEE_CONF:-${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf}"

# State file shared with plasmoid/tray (protected by flock)
STATE_FILE="/dev/shm/.dictee_state"
STATE_LOCK="/dev/shm/.dictee_state.lock"

# Fixed notification ID — all dictee notifications replace each other
NOTIFY_ID=424200

# === DEBUG ===
# Enable with DICTEE_DEBUG=true in dictee.conf or as environment variable

_DBG_LOG="/tmp/dictee-debug-$(id -u).log"

if [ "${DICTEE_DEBUG:-}" != "true" ] && [ -f "$DICTEE_CONF" ]; then
    _d=$(grep '^DICTEE_DEBUG=' "$DICTEE_CONF" 2>/dev/null | cut -d= -f2)
    [ "$_d" = "true" ] && DICTEE_DEBUG=true
fi
export DICTEE_DEBUG="${DICTEE_DEBUG:-false}"

_dbg() {
    [ "$DICTEE_DEBUG" = "true" ] || return 0
    printf '%s [%s] %s\n' "$(date '+%H:%M:%S.%3N')" "${_DBG_CONTEXT:-dictee}" "$*" >> "$_DBG_LOG"
}

# === SHARED FUNCTIONS ===

# Write state atomically (flock-protected)
write_state() {
    (
        flock -n 200 || return 1
        echo "$1" > "$STATE_FILE"
    ) 200>"$STATE_LOCK"
}

# Send a notification, always replacing the previous one
# Usage: notify_dictee TIMEOUT ICON MESSAGE [BODY]
notify_dictee() {
    local timeout="$1" icon="$2" msg="$3" body="${4:-}"
    _dbg "notify: timeout=$timeout msg='$msg'"
    notify-send --replace-id="$NOTIFY_ID" -t "$timeout" -i "$icon" -a Dictee "$msg" ${body:+"$body"} 2>/dev/null || true
}

# Silently close the persistent notification
close_notification() {
    notify-send --replace-id="$NOTIFY_ID" -t 1 -a Dictee "" 2>/dev/null || true
}

# Map ASR backend to systemd service name
asr_service() {
    case "${1:-${DICTEE_ASR_BACKEND:-parakeet}}" in
        parakeet) echo "dictee" ;;
        vosk)     echo "dictee-vosk" ;;
        whisper)  echo "dictee-whisper" ;;
        canary)   echo "dictee-canary" ;;
        *)        echo "dictee" ;;
    esac
}
