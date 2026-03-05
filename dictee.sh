#!/bin/bash
# Dictée vocale - push-to-talk avec animation
# Premier appui : démarre l'enregistrement + animation
# Deuxième appui : arrête et tape le texte

PID_FILE="/tmp/dictee.pid"
PID_ANIM="/tmp/dictee_anim.pid"
WAV_FILE="/tmp/dictee_recording.wav"
CLIENT="/home/rapha/SOURCES/parakeet-rs/target/release/transcribe-client"

# Animation (configurable)
BIN_PATH="/home/rapha/.local/bin/rapha_bin"
ANIMATION_CONFIG="circular"
ANIMATION_PARAM="-p center -w 1000 -H 150"
ANIMATION_APP="${BIN_PATH}/animation-speech ${ANIMATION_CONFIG} ${ANIMATION_PARAM}"

if [ -f "$PID_FILE" ]; then
    # === ARRÊT ===

    # Arrêter l'animation
    if [ -f "$PID_ANIM" ]; then
        id_anim=$(cat "$PID_ANIM")
        kill -SIGUSR2 "$id_anim" 2>/dev/null
        sleep 0.2
        kill "$id_anim" 2>/dev/null
        kill -9 "$id_anim" 2>/dev/null
        rm -f "$PID_ANIM"
    fi

    # Arrêter l'enregistrement
    pid=$(cat "$PID_FILE")
    kill -INT "$pid" 2>/dev/null
    rm -f "$PID_FILE"

    sleep 0.2  # Laisser le fichier se finaliser

    # Transcrire et taper
    if [ -f "$WAV_FILE" ]; then
        text=$("$CLIENT" "$WAV_FILE" 2>/dev/null)
        rm -f "$WAV_FILE"

        if [ -n "$text" ]; then
            echo -n "$text" | ydotool type --file - 2>/dev/null
        fi
    fi
else
    # === DÉMARRAGE ===

    rm -f "$WAV_FILE"

    # Lancer l'animation
    if [ -x "${BIN_PATH}/animation-speech" ]; then
        $ANIMATION_APP &
        PID_A=$!
        echo "$PID_A" > "$PID_ANIM"
        sleep 0.5
        kill -SIGUSR1 "$PID_A" 2>/dev/null
    fi

    # Démarrer l'enregistrement
    pw-record --rate 16000 --channels 1 --format s16 "$WAV_FILE" &
    echo $! > "$PID_FILE"
fi
