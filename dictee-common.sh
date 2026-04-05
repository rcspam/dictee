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
# Fixed notification replace-id — all dictee notifications replace each other
NOTIFY_ID=424200
# Server-side notification ID (for D-Bus CloseNotification)
NOTIFY_SERVER_ID=""

# === DEBUG ===
# Enable with DICTEE_DEBUG=true in dictee.conf or as environment variable

_DBG_LOG="/tmp/dictee-debug-$(id -u).log"

if [ "${DICTEE_DEBUG:-}" != "true" ] && [ -f "$DICTEE_CONF" ]; then
    _d=$(grep '^DICTEE_DEBUG=' "$DICTEE_CONF" 2>/dev/null | cut -d= -f2 || true)
    [ "$_d" = "true" ] && DICTEE_DEBUG=true
fi
export DICTEE_DEBUG="${DICTEE_DEBUG:-false}"

# Read notification settings live from conf (called by notify_dictee)
_read_notify_conf() {
    if [ -f "$DICTEE_CONF" ]; then
        DICTEE_NOTIFICATIONS=$(grep '^DICTEE_NOTIFICATIONS=' "$DICTEE_CONF" 2>/dev/null | cut -d= -f2 || true)
        DICTEE_NOTIFICATIONS_TEXT=$(grep '^DICTEE_NOTIFICATIONS_TEXT=' "$DICTEE_CONF" 2>/dev/null | cut -d= -f2 || true)
    fi
}

_dbg() {
    [ "$DICTEE_DEBUG" = "true" ] || return 0
    printf '%s [%s] %s\n' "$(date '+%H:%M:%S.%3N')" "${_DBG_CONTEXT:-dictee}" "$*" >> "$_DBG_LOG"
}

# === SHARED FUNCTIONS ===

# Write state atomically (flock-protected)
# Never overwrite "offline" with "idle" (user explicitly stopped the daemon)
write_state() {
    _dbg "state: $(cat "$STATE_FILE" 2>/dev/null) → $1"
    (
        flock -n 200 || return 1
        if [ "$1" = "idle" ]; then
            _cur=$(cat "$STATE_FILE" 2>/dev/null)
            if [ "$_cur" = "offline" ]; then
                return 0
            fi
        fi
        echo "$1" > "$STATE_FILE"
    ) 200>"$STATE_LOCK"
}

# Send a notification, replacing the previous one if possible.
# Uses -p to get the KDE-assigned ID, then --replace-id on subsequent calls.
# Usage: notify_dictee TIMEOUT ICON MESSAGE [BODY]
# Send a notification, always replacing the previous one
# Usage: notify_dictee TIMEOUT ICON MESSAGE [BODY]
_NOTIFY_SID_FILE="/tmp/.dictee_notify_sid${_UID_SUFFIX}"

notify_dictee() {
    local timeout="$1" icon="$2" msg="$3" body="${4:-}"
    _read_notify_conf
    # Skip if notifications disabled
    if [ "${DICTEE_NOTIFICATIONS:-true}" = "false" ]; then
        _dbg "notify: SKIPPED (disabled) msg='$msg'"
        return
    fi
    # Strip body text if text display disabled
    if [ "${DICTEE_NOTIFICATIONS_TEXT:-true}" = "false" ]; then body=""; fi
    _dbg "notify: timeout=$timeout icon=$icon msg='$msg' body='${body:0:80}'"
    # Read server ID from previous async notification if available
    if [ -f "$_NOTIFY_SID_FILE" ]; then
        local _prev
        _prev=$(cat "$_NOTIFY_SID_FILE" 2>/dev/null)
        if [ -n "$_prev" ] && [ "$_prev" != "0" ]; then
            NOTIFY_SERVER_ID="$_prev"
        fi
    fi
    local _sid
    _sid=$(notify-send -p --replace-id="$NOTIFY_ID" -t "$timeout" -i "$icon" -a Dictee "$msg" ${body:+"$body"} 2>/dev/null) || true
    if [ -n "$_sid" ] && [ "$_sid" != "0" ]; then
        NOTIFY_SERVER_ID="$_sid"
        echo "$_sid" > "$_NOTIFY_SID_FILE"
    fi
}

# Non-blocking notification (for recording start — don't delay pw-record)
notify_dictee_async() {
    local timeout="$1" icon="$2" msg="$3" body="${4:-}"
    _read_notify_conf
    # Skip if notifications disabled
    if [ "${DICTEE_NOTIFICATIONS:-true}" = "false" ]; then
        _dbg "notify-async: SKIPPED (disabled) msg='$msg'"
        return
    fi
    # Strip body text if text display disabled
    if [ "${DICTEE_NOTIFICATIONS_TEXT:-true}" = "false" ]; then body=""; fi
    _dbg "notify-async: timeout=$timeout icon=$icon msg='$msg'"
    (
        local _sid
        _sid=$(notify-send -p --replace-id="$NOTIFY_ID" -t "$timeout" -i "$icon" -a Dictee "$msg" ${body:+"$body"} 2>/dev/null) || true
        if [ -n "$_sid" ] && [ "$_sid" != "0" ]; then
            echo "$_sid" > "$_NOTIFY_SID_FILE"
        fi
    ) &
}

# Close notification via D-Bus (reliable, unlike notify-send --replace-id on expired notifs)
close_notification() {
    # Read server ID from async file if not yet available
    if [ -z "$NOTIFY_SERVER_ID" ] && [ -f "$_NOTIFY_SID_FILE" ]; then
        NOTIFY_SERVER_ID=$(cat "$_NOTIFY_SID_FILE" 2>/dev/null)
    fi
    if [ -n "$NOTIFY_SERVER_ID" ]; then
        _dbg "notify: close (dbus id=$NOTIFY_SERVER_ID)"
        gdbus call --session --dest org.freedesktop.Notifications \
            --object-path /org/freedesktop/Notifications \
            --method org.freedesktop.Notifications.CloseNotification \
            "$NOTIFY_SERVER_ID" >/dev/null 2>&1 || true
    fi
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
