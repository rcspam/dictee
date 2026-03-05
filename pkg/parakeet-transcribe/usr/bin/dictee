#!/bin/bash
# Dictée vocale - push-to-talk avec animation
# Premier appui : démarre l'enregistrement + animation
# Deuxième appui : arrête et tape le texte
#
# Nécessite : transcribe-daemon (en cours), ydotool, pw-record
# Optionnel : animation-speech (https://github.com/rcspam/animation-speech)

PID_FILE="/tmp/dictee.pid"
WAV_FILE="/tmp/dictee_recording.wav"
ANIM_PID_FILE="${XDG_RUNTIME_DIR:-/tmp}/speech-animation.pid"

# Animation (configurable)
ANIMATION_CONFIG="circular"
ANIMATION_PARAM="-p center -w 1000 -H 150"

get_anim_pid() {
    if [ -f "$ANIM_PID_FILE" ]; then
        local pid
        pid=$(cat "$ANIM_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
    fi
    return 1
}

start_animation() {
    if command -v animation-speech >/dev/null 2>&1; then
        animation-speech $ANIMATION_CONFIG $ANIMATION_PARAM &
        sleep 0.5
        local pid
        pid=$(get_anim_pid) && kill -SIGUSR1 "$pid" 2>/dev/null
    fi
}

stop_animation() {
    local pid
    pid=$(get_anim_pid) && {
        kill -SIGUSR2 "$pid" 2>/dev/null
        sleep 0.2
        kill "$pid" 2>/dev/null
    }
}

if [ -f "$PID_FILE" ]; then
    # === ARRÊT ===

    stop_animation

    # Arrêter l'enregistrement
    pid=$(cat "$PID_FILE")
    kill -INT "$pid" 2>/dev/null
    rm -f "$PID_FILE"

    sleep 0.2  # Laisser le fichier se finaliser

    # Transcrire et taper
    if [ -f "$WAV_FILE" ]; then
        text=$(transcribe-client "$WAV_FILE" 2>/dev/null)
        rm -f "$WAV_FILE"

        if [ -n "$text" ]; then
            echo -n "$text" | ydotool type --file - 2>/dev/null
        fi
    fi
else
    # === DÉMARRAGE ===

    rm -f "$WAV_FILE"

    start_animation

    # Démarrer l'enregistrement
    pw-record --rate 16000 --channels 1 --format s16 "$WAV_FILE" &
    echo $! > "$PID_FILE"
fi
