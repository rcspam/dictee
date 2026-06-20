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

# Legacy fixed notification ID — kept for compatibility but no longer used
# as --replace-id (GNOME is strict and requires the server-assigned ID).
# shellcheck disable=SC2034
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

# Detect GNOME Shell (includes Ubuntu's default session).
_is_gnome_shell() {
    case "${XDG_CURRENT_DESKTOP:-}" in
        *GNOME*|*gnome*) return 0 ;;
    esac
    case "${DESKTOP_SESSION:-}" in
        *gnome*|*ubuntu*) return 0 ;;
    esac
    return 1
}

# Strip HTML tags for plain-text display (used when merging body into summary).
_strip_html() {
    printf '%s' "$1" | sed -E 's/<[^>]*>//g'
}

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

# Resolve the keyboard layout+variant that dotool must assume. dotool emits
# evdev keycodes that the X server / Wayland compositor decodes with its ACTIVE
# layout, so we must match it. There is no universal API for the active layout,
# so query per desktop (KDE via DBus + kxkbrc, GNOME via gsettings), then fall
# back to the static system config. Echoes "layout|variant".
# An explicit DOTOOL_XKB_LAYOUT (env / dictee.conf) always wins — this is also
# how users on sway/Hyprland/other compositors (no queryable API) pin theirs.
resolve_active_layout() {
    if [ -n "${DOTOOL_XKB_LAYOUT:-}" ]; then
        printf '%s|%s' "$DOTOOL_XKB_LAYOUT" "${DOTOOL_XKB_VARIANT:-}"
        return 0
    fi

    local layout="" variant="" _qdbus=""
    local _b
    for _b in qdbus6 qdbus-qt6 qdbus; do
        command -v "$_b" >/dev/null 2>&1 && { _qdbus="$_b"; break; }
    done

    # KDE Plasma (X11 + Wayland): active index via DBus, codes via kxkbrc
    # (the DBus interface does not expose the variant, only the layout list).
    if [ -n "$_qdbus" ]; then
        local _idx
        _idx=$("$_qdbus" org.kde.keyboard /Layouts getLayout 2>/dev/null)
        if [ -n "$_idx" ] && [ "$_idx" -ge 0 ] 2>/dev/null; then
            local _kxkb="${XDG_CONFIG_HOME:-$HOME/.config}/kxkbrc" _i=$((_idx + 1))
            if [ -f "$_kxkb" ]; then
                layout=$(awk -F= -v i="$_i" '/^LayoutList=/{split($2,a,",")} END{gsub(/[\r ]/,"",a[i]); print a[i]}' "$_kxkb")
                variant=$(awk -F= -v i="$_i" '/^VariantList=/{split($2,a,",")} END{gsub(/[\r ]/,"",a[i]); print a[i]}' "$_kxkb")
            fi
        fi
    fi

    # GNOME (X11 + Wayland): mru-sources[0] is the active source once the user
    # has switched layouts; with a single layout that was never switched it is
    # empty (@a(ss) []), so fall back to sources[0] -- otherwise we'd lose a
    # non-default layout/variant (e.g. a permanent us+altgr-intl) and drop its
    # accents. Format: [('xkb', 'us+altgr-intl'), ...]; the xkb id is
    # "layout+variant" or just "layout". ('current' is deprecated upstream.)
    if [ -z "$layout" ] && command -v gsettings >/dev/null 2>&1; then
        local _src _id _key
        for _key in mru-sources sources; do
            _src=$(gsettings get org.gnome.desktop.input-sources "$_key" 2>/dev/null)
            if printf '%s' "$_src" | grep -q "^\[('xkb'"; then
                _id=$(printf '%s' "$_src" | sed -E "s/^\[\('xkb', *'([^']*)'\).*/\1/")
                layout="${_id%%+*}"
                [ "$_id" != "$layout" ] && variant="${_id#*+}"
                break
            fi
        done
    fi

    # Static fallback: freedesktop localed, then setxkbmap, then us.
    if [ -z "$layout" ]; then
        layout=$(localectl status 2>/dev/null | awk '/X11 Layout/{print $3}')
        [ -z "$layout" ] && layout=$(setxkbmap -query 2>/dev/null | awk '/layout/{print $2}')
    fi
    printf '%s|%s' "${layout:-us}" "$variant"
}

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
    # GNOME Shell only shows the Summary on banners — the Body stays hidden in
    # the notification tray. Merge body into summary so the user sees the full
    # transcribed text inline (like KDE does natively).
    if [ -n "$body" ] && _is_gnome_shell; then
        # GNOME Shell treats " — " as a title/subtitle separator and renders
        # the part after it in the banner. Without it the merged summary
        # gets truncated and the transcribed text disappears. Keep the em-
        # dash exactly as below — tested on Ubuntu 24.04.
        msg="$msg — $(_strip_html "$body")"
        body=""
    fi
    _dbg "notify: timeout=$timeout icon=$icon msg='$msg' body='${body:0:80}'"
    # Read the SERVER-assigned ID from the previous notification (stored by
    # notify-send -p) so we can actually replace it. On GNOME, --replace-id
    # must be the server-side ID; passing an arbitrary fixed ID (like the
    # legacy NOTIFY_ID=424200) creates a brand new notification each time,
    # which is why dictee notifs were piling up on Ubuntu/GNOME.
    local _prev=""
    if [ -f "$_NOTIFY_SID_FILE" ]; then
        _prev=$(cat "$_NOTIFY_SID_FILE" 2>/dev/null)
    fi
    local _sid
    if [ -n "$_prev" ] && [ "$_prev" != "0" ]; then
        _sid=$(notify-send -p --replace-id="$_prev" -t "$timeout" -i "$icon" -a Dictee "$msg" ${body:+"$body"} 2>/dev/null) || true
    else
        _sid=$(notify-send -p -t "$timeout" -i "$icon" -a Dictee "$msg" ${body:+"$body"} 2>/dev/null) || true
    fi
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
    # Same GNOME merge logic as notify_dictee (see above).
    if [ -n "$body" ] && _is_gnome_shell; then
        # GNOME Shell treats " — " as a title/subtitle separator and renders
        # the part after it in the banner. Without it the merged summary
        # gets truncated and the transcribed text disappears. Keep the em-
        # dash exactly as below — tested on Ubuntu 24.04.
        msg="$msg — $(_strip_html "$body")"
        body=""
    fi
    _dbg "notify-async: timeout=$timeout icon=$icon msg='$msg'"
    local _prev=""
    if [ -f "$_NOTIFY_SID_FILE" ]; then
        _prev=$(cat "$_NOTIFY_SID_FILE" 2>/dev/null)
    fi
    (
        local _sid
        if [ -n "$_prev" ] && [ "$_prev" != "0" ]; then
            _sid=$(notify-send -p --replace-id="$_prev" -t "$timeout" -i "$icon" -a Dictee "$msg" ${body:+"$body"} 2>/dev/null) || true
        else
            _sid=$(notify-send -p -t "$timeout" -i "$icon" -a Dictee "$msg" ${body:+"$body"} 2>/dev/null) || true
        fi
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
