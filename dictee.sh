#!/bin/bash
# Dictée vocale - push-to-talk avec animation
# Premier appui : démarre l'enregistrement + animation
# Deuxième appui : arrête et tape le texte
#
# Nécessite : transcribe-daemon (en cours), pw-record
#             ydotool-rebind (https://github.com/david-vct/ydotool-rebind)
#             ⚠ ydotool standard ne gère pas les accents - utiliser le fork ci-dessus
# Optionnel : animation-speech-ctl (https://github.com/rcspam/animation-speech)

PID_FILE="/tmp/dictee.pid"
WAV_FILE="/tmp/dictee_recording.wav"
MUTE_FLAG="/tmp/dictee_was_muted"

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

# --- Gestion du micro ---

# Vérifie si le micro est muté. Retourne 0 si muté, 1 sinon.
is_mic_muted() {
    # PipeWire (wpctl)
    if command -v wpctl >/dev/null 2>&1; then
        wpctl get-volume @DEFAULT_AUDIO_SOURCE@ 2>/dev/null | grep -q "\[MUTED\]"
        return $?
    fi
    # PulseAudio (pactl)
    if command -v pactl >/dev/null 2>&1; then
        LANG=C pactl get-source-mute @DEFAULT_SOURCE@ 2>/dev/null | grep -q "yes"
        return $?
    fi
    return 1
}

unmute_mic() {
    if is_mic_muted; then
        # Marquer qu'on a démuté (pour remuter après)
        touch "$MUTE_FLAG"
        if command -v wpctl >/dev/null 2>&1; then
            wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0
        elif command -v pactl >/dev/null 2>&1; then
            pactl set-source-mute @DEFAULT_SOURCE@ 0
        fi
    fi
}

remute_mic() {
    if [ -f "$MUTE_FLAG" ]; then
        rm -f "$MUTE_FLAG"
        if command -v wpctl >/dev/null 2>&1; then
            wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 1
        elif command -v pactl >/dev/null 2>&1; then
            pactl set-source-mute @DEFAULT_SOURCE@ 1
        fi
    fi
}

# Vérifie qu'une source audio est disponible
check_mic() {
    # PipeWire
    if command -v wpctl >/dev/null 2>&1; then
        if wpctl get-volume @DEFAULT_AUDIO_SOURCE@ >/dev/null 2>&1; then
            return 0
        fi
    fi
    # PulseAudio
    if command -v pactl >/dev/null 2>&1; then
        if pactl get-source-mute @DEFAULT_SOURCE@ >/dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# --- Animation (via animation-speech-ctl) ---

start_animation() {
    if command -v animation-speech-ctl >/dev/null 2>&1; then
        animation-speech-ctl start 2>/dev/null
    fi
}

stop_animation() {
    if command -v animation-speech-ctl >/dev/null 2>&1; then
        animation-speech-ctl stop 2>/dev/null
    fi
}

quit_animation() {
    if command -v animation-speech-ctl >/dev/null 2>&1; then
        animation-speech-ctl quit 2>/dev/null
    fi
}

cleanup() {
    quit_animation
    remute_mic
    rm -f "$PID_FILE" "$WAV_FILE"
}

# === LOGIQUE PRINCIPALE ===

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

    # Remuter le micro si on l'avait démuté
    remute_mic

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

    # Vérifier l'accès au micro
    if ! check_mic; then
        notify "Erreur" "Aucun microphone détecté"
        exit 1
    fi

    rm -f "$WAV_FILE"

    # Démuter le micro si nécessaire
    unmute_mic

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
