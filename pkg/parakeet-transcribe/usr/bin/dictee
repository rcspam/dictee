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

notify() {
    if command -v notify-send >/dev/null 2>&1; then
        notify-send -a "Dictée" "$1" "$2" 2>/dev/null
    fi
}

check_deps() {
    local missing=""
    command -v pw-record >/dev/null 2>&1 || missing="$missing pw-record"
    command -v transcribe-client >/dev/null 2>&1 || missing="$missing transcribe-client"
    command -v ydotool >/dev/null 2>&1 || missing="$missing ydotool"
    if [ -n "$missing" ]; then
        notify "Erreur" "Commandes manquantes :$missing"
        exit 1
    fi
    # Vérifier que le daemon tourne
    if [ ! -S /tmp/transcribe.sock ]; then
        notify "Erreur" "transcribe-daemon n'est pas lancé"
        exit 1
    fi
}

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
        animation-speech &
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

cleanup() {
    stop_animation
    rm -f "$PID_FILE" "$WAV_FILE"
}

if [ -f "$PID_FILE" ]; then
    # === ARRÊT ===

    stop_animation

    # Arrêter l'enregistrement
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        kill -INT "$pid" 2>/dev/null
    fi
    rm -f "$PID_FILE"

    sleep 0.2  # Laisser le fichier se finaliser

    # Transcrire et taper
    if [ -f "$WAV_FILE" ]; then
        text=$(transcribe-client "$WAV_FILE" 2>/dev/null)
        rm -f "$WAV_FILE"

        if [ -n "$text" ]; then
            echo -n "$text" | ydotool type --file - 2>/dev/null
        else
            notify "Dictée" "Aucun texte reconnu"
        fi
    else
        notify "Erreur" "Fichier audio non trouvé"
    fi
else
    # === DÉMARRAGE ===

    check_deps

    rm -f "$WAV_FILE"

    start_animation

    # Démarrer l'enregistrement
    pw-record --rate 16000 --channels 1 --format s16 "$WAV_FILE" &
    rec_pid=$!

    # Vérifier que l'enregistrement a bien démarré
    sleep 0.3
    if ! kill -0 "$rec_pid" 2>/dev/null; then
        cleanup
        notify "Erreur" "Échec de l'enregistrement (pw-record)"
        exit 1
    fi

    echo "$rec_pid" > "$PID_FILE"
fi
