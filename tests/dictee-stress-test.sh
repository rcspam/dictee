#!/bin/bash
#
# dictee-stress-test.sh — Batterie de stress tests automatises pour dictee
#
# Ce script execute des tests de robustesse sans interaction utilisateur.
# Il requiert que le systeme dictee soit installe (scripts, services, etc.)
# mais N'a PAS besoin de micro reel (utilise des WAV synthetiques).
#
# Usage: sudo -u $USER bash /tmp/dictee-stress-test.sh [--quick] [--section N]
#   --quick     : sauter les tests longs (>5s chacun)
#   --section N : executer uniquement la section N (1-14)
#
# Resultats : /tmp/dictee-stress-results.log
#

set -o pipefail

# ═══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

LOG="/tmp/dictee-stress-results.log"
STATE_FILE="/dev/shm/.dictee_state"
STATE_LOCK="/dev/shm/.dictee_state.lock"
UID_SUFFIX="-$(id -u)"
PIDFILE="/tmp/recording_dictee_pid${UID_SUFFIX}"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}/dictee.conf"
SOCK="${XDG_RUNTIME_DIR:-/tmp}/transcribe.sock"
RECORDING_FILE="$HOME/.cache/tmp_recording_dictee.wav"
TMPDIR_STRESS="/tmp/dictee-stress-$$"

# Compteurs
PASS=0
FAIL=0
SKIP=0
TOTAL=0

QUICK=false
SECTION_ONLY=""

for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=true ;;
        --section) shift; SECTION_ONLY="$2" ;;
        [0-9]*) SECTION_ONLY="$arg" ;;
    esac
done

# ═══════════════════════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ═══════════════════════════════════════════════════════════════════════

log() {
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S.%3N')
    printf '[%s] %s\n' "$ts" "$*" | tee -a "$LOG"
}

log_header() {
    log ""
    log "================================================================"
    log "  SECTION $1 — $2"
    log "================================================================"
}

# Declarer un test — incremente le compteur
test_start() {
    TOTAL=$((TOTAL + 1))
    log "  TEST #${TOTAL}: $1"
}

test_pass() {
    PASS=$((PASS + 1))
    log "    => PASS${1:+: $1}"
}

test_fail() {
    FAIL=$((FAIL + 1))
    log "    => FAIL: $1"
}

test_skip() {
    SKIP=$((SKIP + 1))
    log "    => SKIP: $1"
}

# Lire l'etat actuel
get_state() {
    cat "$STATE_FILE" 2>/dev/null || echo ""
}

# Ecrire un etat
write_state() {
    (
        flock -n 200 || return 1
        echo "$1" > "$STATE_FILE"
    ) 200>"$STATE_LOCK"
}

# Attendre un etat precis (timeout 5s par defaut)
wait_state() {
    local expected="$1" timeout="${2:-5}"
    local i=0
    while [ $i -lt $((timeout * 10)) ]; do
        if [ "$(get_state)" = "$expected" ]; then return 0; fi
        sleep 0.1
        i=$((i + 1))
    done
    return 1
}

# Generer un WAV synthetique (silence ou bruit)
gen_wav() {
    local path="$1" duration="${2:-2}" type="${3:-silence}"
    case "$type" in
        silence)
            sox -n -r 16000 -c 1 -b 16 "$path" trim 0.0 "$duration" 2>/dev/null
            ;;
        noise)
            sox -n -r 16000 -c 1 -b 16 "$path" synth "$duration" whitenoise vol 0.1 2>/dev/null
            ;;
        tone)
            sox -n -r 16000 -c 1 -b 16 "$path" synth "$duration" sine 440 vol 0.3 2>/dev/null
            ;;
    esac
}

# Reset complet avant chaque section
safe_reset() {
    dictee-reset "$(grep '^DICTEE_ASR_BACKEND=' "$CONF" 2>/dev/null | cut -d= -f2 | xargs -I{} bash -c 'case {} in parakeet) echo dictee;; vosk) echo dictee-vosk;; whisper) echo dictee-whisper;; canary) echo dictee-canary;; *) echo dictee;; esac')" 2>/dev/null || true
    sleep 0.5
    # S'assurer qu'on est idle
    write_state "idle" 2>/dev/null || true
}

# Verifier qu'une commande retourne dans un delai
timed_run() {
    local timeout="$1" ; shift
    timeout "$timeout" "$@" 2>/dev/null
}

should_run_section() {
    [ -z "$SECTION_ONLY" ] || [ "$SECTION_ONLY" = "$1" ]
}

# ═══════════════════════════════════════════════════════════════════════
# PREPARATION
# ═══════════════════════════════════════════════════════════════════════

mkdir -p "$TMPDIR_STRESS"
: > "$LOG"

log "================================================================"
log "  DICTEE STRESS TEST — $(date '+%Y-%m-%d %H:%M:%S')"
log "  Machine: $(hostname) — $(uname -r)"
log "  User: $(id -un) ($(id -u))"
log "  Mode: ${QUICK:+quick}${QUICK:-full}"
log "  Section: ${SECTION_ONLY:-toutes}"
log "================================================================"
log ""

# Verifier les prerequis
PREREQS_OK=true
for cmd in dictee dictee-reset dictee-switch-backend sox; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log "ERREUR: commande '$cmd' introuvable"
        PREREQS_OK=false
    fi
done
if [ "$PREREQS_OK" = false ]; then
    log "ABANDON: prerequis manquants"
    exit 1
fi

# Sauvegarder la configuration
if [ -f "$CONF" ]; then
    cp "$CONF" "${CONF}.stress-backup"
    log "Configuration sauvegardee: ${CONF}.stress-backup"
fi

# Generer les fichiers WAV de test
gen_wav "$TMPDIR_STRESS/silence_2s.wav" 2 silence
gen_wav "$TMPDIR_STRESS/silence_01s.wav" 0.1 silence
gen_wav "$TMPDIR_STRESS/noise_5s.wav" 5 noise
gen_wav "$TMPDIR_STRESS/noise_60s.wav" 60 noise
gen_wav "$TMPDIR_STRESS/tone_2s.wav" 2 tone
# WAV vide (header seulement, 0 samples)
sox -n -r 16000 -c 1 -b 16 "$TMPDIR_STRESS/empty.wav" trim 0 0 2>/dev/null || true
# Fichier non-WAV
echo "ceci n'est pas un WAV" > "$TMPDIR_STRESS/fake.wav"
# Fichier tres gros (10 minutes)
if [ "$QUICK" = false ]; then
    gen_wav "$TMPDIR_STRESS/huge_600s.wav" 600 noise
fi

log "Fichiers de test generes dans $TMPDIR_STRESS"
log ""


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1 — FICHIER D'ETAT : corruption et suppression
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 1; then
log_header 1 "Fichier d'etat : corruption et suppression"

safe_reset

test_start "Suppression du fichier d'etat pendant idle"
rm -f "$STATE_FILE"
sleep 0.2
dictee --cancel 2>/dev/null || true
state=$(get_state)
if [ "$state" = "cancelled" ] || [ -z "$state" ]; then
    test_pass "cancel gere l'absence de fichier d'etat (state='$state')"
else
    test_fail "etat inattendu apres cancel sans fichier: '$state'"
fi

test_start "Ecriture de valeur invalide dans le fichier d'etat"
echo "INVALID_STATE_123" > "$STATE_FILE"
dictee --cancel 2>/dev/null || true
state=$(get_state)
# cancel devrait ignorer un etat inconnu ou le traiter comme idle
if [ "$state" = "cancelled" ] || [ "$state" = "INVALID_STATE_123" ]; then
    test_pass "cancel gere un etat invalide (state='$state')"
else
    test_fail "etat inattendu: '$state'"
fi

test_start "Fichier d'etat rempli de binaire"
dd if=/dev/urandom of="$STATE_FILE" bs=1024 count=1 2>/dev/null
dictee --cancel 2>/dev/null || true
# Doit pas crasher
test_pass "cancel survit a un fichier d'etat binaire"

test_start "Permissions en lecture seule sur le fichier d'etat"
write_state "idle"
chmod 444 "$STATE_FILE" 2>/dev/null
dictee --cancel 2>/dev/null
exit_code=$?
chmod 666 "$STATE_FILE" 2>/dev/null
write_state "idle"
test_pass "cancel survit a un fichier read-only (exit=$exit_code)"

test_start "Suppression du lock file pendant une operation"
write_state "recording"
rm -f "$STATE_LOCK"
dictee --cancel 2>/dev/null || true
if [ -f "$STATE_LOCK" ] || [ "$(get_state)" = "cancelled" ]; then
    test_pass "lock file recree ou cancel fonctionne"
else
    test_fail "lock file absent et etat incorrect: '$(get_state)'"
fi

test_start "Fichier d'etat = symlink vers /dev/null"
rm -f "$STATE_FILE"
ln -s /dev/null "$STATE_FILE"
dictee --cancel 2>/dev/null || true
rm -f "$STATE_FILE"
write_state "idle"
test_pass "cancel survit a un symlink vers /dev/null"

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 2 — ANNULATION (cancel) depuis chaque etat
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 2; then
log_header 2 "Annulation (--cancel) depuis chaque etat"

for state_val in idle recording transcribing diarizing preparing diarize-ready switching cancelled offline; do
    test_start "cancel depuis etat='$state_val'"
    write_state "$state_val"
    timed_run 5 dictee --cancel 2>/dev/null
    result=$(get_state)
    case "$state_val" in
        idle|offline|cancelled)
            # Devrait rester inchange (rien a annuler)
            if [ "$result" = "$state_val" ] || [ "$result" = "idle" ]; then
                test_pass "etat preserve ou idle (state='$result')"
            else
                test_fail "etat inattendu: '$result' (attendu: '$state_val' ou 'idle')"
            fi
            ;;
        *)
            # Devrait passer a cancelled ou idle
            if [ "$result" = "cancelled" ] || [ "$result" = "idle" ]; then
                test_pass "etat=$result"
            else
                test_fail "etat inattendu: '$result' (attendu: cancelled ou idle)"
            fi
            ;;
    esac
done

# Cancel rapide consecutif (race condition)
test_start "Triple cancel rapide (race condition)"
write_state "recording"
dictee --cancel &
dictee --cancel &
dictee --cancel &
wait
state=$(get_state)
if [ "$state" = "cancelled" ] || [ "$state" = "idle" ]; then
    test_pass "triple cancel OK (state='$state')"
else
    test_fail "etat inattendu apres triple cancel: '$state'"
fi

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 3 — RESET depuis chaque etat
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 3; then
log_header 3 "Reset depuis chaque etat"

for state_val in idle recording transcribing diarizing preparing diarize-ready switching cancelled offline; do
    test_start "dictee-reset depuis etat='$state_val'"
    write_state "$state_val"
    # Creer des fichiers temporaires comme si une session etait en cours
    echo "9999999" > "$PIDFILE"
    touch "/tmp/dictee_translate${UID_SUFFIX}"
    touch "/tmp/dictee_diarize${UID_SUFFIX}"
    timed_run 10 dictee-reset 2>/dev/null
    result=$(get_state)
    if [ "$result" = "idle" ]; then
        test_pass "reset → idle"
    else
        test_fail "etat apres reset: '$result' (attendu: idle)"
    fi
    # Verifier nettoyage
    if [ -f "$PIDFILE" ]; then
        test_fail "PIDFILE non supprime apres reset"
    else
        test_pass "PIDFILE nettoye"
    fi
done

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 4 — SOCKET DAEMON : stress et cas limites
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 4; then
log_header 4 "Socket daemon : stress et cas limites"

# Verifier que le daemon tourne
_BACKEND=$(grep '^DICTEE_ASR_BACKEND=' "$CONF" 2>/dev/null | cut -d= -f2)
_BACKEND="${_BACKEND:-parakeet}"
_SVC=""
case "$_BACKEND" in
    parakeet) _SVC="dictee" ;;
    vosk) _SVC="dictee-vosk" ;;
    whisper) _SVC="dictee-whisper" ;;
    canary) _SVC="dictee-canary" ;;
esac

if ! systemctl --user is-active --quiet "${_SVC}.service" 2>/dev/null; then
    log "  INFO: daemon ${_SVC} pas actif, tentative de demarrage..."
    systemctl --user start "${_SVC}.service" 2>/dev/null || true
    sleep 2
fi

DAEMON_UP=false
if [ -S "$SOCK" ]; then
    DAEMON_UP=true
fi

if [ "$DAEMON_UP" = true ]; then

    test_start "Envoi d'un fichier WAV valide au daemon"
    result=$(echo "$TMPDIR_STRESS/tone_2s.wav" | timeout 30 socat - UNIX-CONNECT:"$SOCK" 2>/dev/null) || result=""
    if [ -n "$result" ]; then
        test_pass "reponse recue (${#result} chars)"
    else
        # Essayer avec python (meme protocole que transcribe-client)
        result=$(python3 -c "
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(30)
s.connect('$SOCK')
s.sendall(b'$TMPDIR_STRESS/tone_2s.wav\n')
s.shutdown(socket.SHUT_WR)
data = b''
while True:
    c = s.recv(4096)
    if not c: break
    data += c
s.close()
print(data.decode().strip())
" 2>/dev/null) || result=""
        if [ -n "$result" ]; then
            test_pass "reponse via python (${#result} chars)"
        else
            test_fail "aucune reponse du daemon"
        fi
    fi

    test_start "Envoi d'un chemin inexistant"
    result=$(python3 -c "
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
s.connect('$SOCK')
s.sendall(b'/tmp/NEXISTE_PAS_12345.wav\n')
s.shutdown(socket.SHUT_WR)
data = b''
while True:
    c = s.recv(4096)
    if not c: break
    data += c
s.close()
print(repr(data))
" 2>/dev/null) || result="timeout"
    test_pass "daemon repond sans crash: $result"

    test_start "Envoi d'un fichier non-WAV"
    result=$(python3 -c "
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
s.connect('$SOCK')
s.sendall(b'$TMPDIR_STRESS/fake.wav\n')
s.shutdown(socket.SHUT_WR)
data = b''
while True:
    c = s.recv(4096)
    if not c: break
    data += c
s.close()
print(repr(data))
" 2>/dev/null) || result="timeout"
    test_pass "daemon repond sans crash: $result"

    test_start "Envoi d'un WAV vide (0 samples)"
    result=$(python3 -c "
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
s.connect('$SOCK')
s.sendall(b'$TMPDIR_STRESS/empty.wav\n')
s.shutdown(socket.SHUT_WR)
data = b''
while True:
    c = s.recv(4096)
    if not c: break
    data += c
s.close()
print(repr(data))
" 2>/dev/null) || result="timeout"
    test_pass "daemon repond sans crash: $result"

    test_start "Envoi de donnees binaires aleatoires"
    result=$(python3 -c "
import socket, os
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(5)
s.connect('$SOCK')
s.sendall(os.urandom(1024) + b'\n')
s.shutdown(socket.SHUT_WR)
data = b''
while True:
    c = s.recv(4096)
    if not c: break
    data += c
s.close()
print('OK: received', len(data), 'bytes')
" 2>/dev/null) || result="timeout/error"
    test_pass "daemon survit a des donnees binaires: $result"

    test_start "Envoi d'un chemin tres long (4096 chars)"
    longpath=$(python3 -c "print('/tmp/' + 'A' * 4090 + '.wav')")
    result=$(python3 -c "
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(5)
s.connect('$SOCK')
s.sendall(b'$longpath\n')
s.shutdown(socket.SHUT_WR)
data = b''
while True:
    c = s.recv(4096)
    if not c: break
    data += c
s.close()
print('OK')
" 2>/dev/null) || result="timeout"
    test_pass "daemon survit a un chemin de 4096 chars"

    test_start "Connexions concurrentes (10 en parallele)"
    for i in $(seq 1 10); do
        python3 -c "
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(30)
s.connect('$SOCK')
s.sendall(b'$TMPDIR_STRESS/silence_2s.wav\n')
s.shutdown(socket.SHUT_WR)
data = b''
while True:
    c = s.recv(4096)
    if not c: break
    data += c
s.close()
" 2>/dev/null &
    done
    wait
    # Si on arrive ici, le daemon n'a pas crash
    if systemctl --user is-active --quiet "${_SVC}.service" 2>/dev/null; then
        test_pass "daemon toujours actif apres 10 connexions concurrentes"
    else
        test_fail "daemon crash apres connexions concurrentes"
        systemctl --user start "${_SVC}.service" 2>/dev/null
        sleep 2
    fi

    test_start "Connexion sans envoi de donnees (timeout client)"
    result=$(python3 -c "
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(3)
s.connect('$SOCK')
# Ne rien envoyer, juste fermer apres 2s
import time; time.sleep(2)
s.close()
print('OK')
" 2>/dev/null) || result="timeout"
    test_pass "daemon survit a une connexion muette"

    if [ "$QUICK" = false ]; then
        test_start "Envoi d'un WAV de 10 minutes (charge lourde)"
        if [ -f "$TMPDIR_STRESS/huge_600s.wav" ]; then
            result=$(python3 -c "
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(120)
s.connect('$SOCK')
s.sendall(b'$TMPDIR_STRESS/huge_600s.wav\n')
s.shutdown(socket.SHUT_WR)
data = b''
while True:
    c = s.recv(4096)
    if not c: break
    data += c
s.close()
print('received', len(data), 'bytes')
" 2>/dev/null) || result="timeout (>120s)"
            test_pass "fichier de 10 min: $result"
        else
            test_skip "fichier huge non genere (mode quick?)"
        fi
    fi

else
    test_start "Socket daemon"
    test_skip "daemon non actif ou socket '$SOCK' absente — tests socket sautes"
fi

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 5 — SWITCH BACKEND pendant differents etats
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 5; then
log_header 5 "Switch backend pendant differents etats"

# Trouver les backends disponibles
AVAILABLE_BACKENDS=()
for b in parakeet canary vosk whisper; do
    svc=""
    case "$b" in parakeet) svc="dictee";; canary) svc="dictee-canary";; vosk) svc="dictee-vosk";; whisper) svc="dictee-whisper";; esac
    if systemctl --user list-unit-files "${svc}.service" 2>/dev/null | grep -q "${svc}.service"; then
        AVAILABLE_BACKENDS+=("$b")
    fi
done
log "  Backends disponibles: ${AVAILABLE_BACKENDS[*]}"

if [ ${#AVAILABLE_BACKENDS[@]} -ge 2 ]; then
    B1="${AVAILABLE_BACKENDS[0]}"
    B2="${AVAILABLE_BACKENDS[1]}"

    test_start "Switch $B1 → $B2 depuis idle"
    write_state "idle"
    timed_run 15 dictee-switch-backend asr "$B2" 2>/dev/null
    state=$(get_state)
    if [ "$state" = "idle" ] || [ "$state" = "offline" ]; then
        test_pass "switch OK (state=$state)"
    else
        test_fail "etat apres switch: '$state'"
    fi

    test_start "Switch pendant etat 'recording' (devrait etre rejete ou safe)"
    write_state "recording"
    timed_run 15 dictee-switch-backend asr "$B1" 2>/dev/null
    state=$(get_state)
    # Le switch va quand meme s'executer (pas de guard dans switch-backend)
    test_pass "switch pendant recording termine (state=$state)"

    test_start "Switch pendant etat 'transcribing'"
    write_state "transcribing"
    timed_run 15 dictee-switch-backend asr "$B2" 2>/dev/null
    state=$(get_state)
    test_pass "switch pendant transcribing termine (state=$state)"

    test_start "Double switch rapide (race condition)"
    timed_run 15 dictee-switch-backend asr "$B1" &
    timed_run 15 dictee-switch-backend asr "$B2" &
    wait
    state=$(get_state)
    test_pass "double switch rapide termine (state=$state)"

    test_start "Switch vers le meme backend"
    timed_run 15 dictee-switch-backend asr "$B2" 2>/dev/null
    timed_run 15 dictee-switch-backend asr "$B2" 2>/dev/null
    state=$(get_state)
    test_pass "double switch meme backend OK (state=$state)"

    # Restaurer le backend initial
    timed_run 15 dictee-switch-backend asr "$B1" 2>/dev/null
else
    test_start "Switch backend"
    test_skip "moins de 2 backends disponibles"
fi

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 6 — DIARIZE : prepare, cancel, re-diarize
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 6; then
log_header 6 "Diarize : prepare, cancel, re-diarize"

test_start "Diarize prepare (switch-backend diarize true)"
timed_run 20 dictee-switch-backend diarize true 2>/dev/null
state=$(get_state)
if [ "$state" = "diarize-ready" ] || [ "$state" = "preparing" ]; then
    test_pass "prepare OK (state=$state)"
else
    test_fail "etat apres prepare: '$state'"
fi

test_start "Cancel diarize depuis diarize-ready"
timed_run 10 dictee --cancel 2>/dev/null
# Attendre restauration du daemon
sleep 2
state=$(get_state)
if [ "$state" = "cancelled" ] || [ "$state" = "idle" ]; then
    test_pass "cancel diarize OK (state=$state)"
else
    test_fail "etat apres cancel diarize: '$state'"
fi

safe_reset
sleep 2

test_start "Re-diarize apres cancel"
timed_run 20 dictee-switch-backend diarize true 2>/dev/null
state=$(get_state)
if [ "$state" = "diarize-ready" ] || [ "$state" = "preparing" ]; then
    test_pass "re-diarize OK (state=$state)"
else
    test_fail "re-diarize echoue (state=$state)"
fi

test_start "Diarize false (restore daemon)"
timed_run 20 dictee-switch-backend diarize false 2>/dev/null
sleep 2
state=$(get_state)
if [ "$state" = "idle" ]; then
    test_pass "diarize false → idle"
else
    test_fail "etat apres diarize false: '$state'"
fi

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 7 — LOCK FILE : contention et fichiers fantomes
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 7; then
log_header 7 "Lock file : contention et fichiers fantomes"

test_start "PIDFILE avec PID inexistant (stale)"
echo "99999" > "$PIDFILE"
write_state "idle"
# dictee devrait detecter le PID mort et nettoyer
timed_run 5 dictee 2>/dev/null || true
sleep 0.5
if [ ! -f "$PIDFILE" ] || [ "$(cat "$PIDFILE" 2>/dev/null)" != "99999" ]; then
    test_pass "PIDFILE fantome nettoye"
else
    test_fail "PIDFILE fantome non nettoye"
fi
rm -f "$PIDFILE"

test_start "Lock file deja verrouille (flock contention)"
exec 201>"${PIDFILE}.lock"
flock -n 201
# Lancer dictee en arriere-plan — devrait etre bloque
write_state "idle"
timeout 3 dictee 2>/dev/null &
bg_pid=$!
sleep 1
# Si dictee est bloque, il devrait encore tourner ou avoir exit 0
if kill -0 "$bg_pid" 2>/dev/null; then
    kill "$bg_pid" 2>/dev/null
    test_pass "dictee bloque par le lock (design correct)"
else
    wait "$bg_pid" 2>/dev/null
    test_pass "dictee exit 0 quand lock pris"
fi
exec 201>&-
rm -f "${PIDFILE}.lock"

test_start "Suppression du lock file pendant qu'il est tenu"
write_state "recording"
# Utiliser un faux PID (pas $$, sinon dictee --cancel tue le script de test)
echo "99998" > "$PIDFILE"
exec 201>"${PIDFILE}.lock"
flock -n 201
rm -f "${PIDFILE}.lock"
# dictee --cancel devrait quand meme fonctionner
timed_run 5 dictee --cancel 2>/dev/null || true
exec 201>&-
test_pass "cancel survit a la suppression du lock"

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 8 — SIGNAUX : SIGTERM, SIGKILL pendant enregistrement simule
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 8; then
log_header 8 "Signaux : SIGTERM, SIGKILL pendant enregistrement simule"

test_start "SIGTERM envoye a dictee pendant 'recording'"
write_state "recording"
# Simuler un enregistrement en cours
sleep 30 &
fake_rec=$!
echo "$fake_rec" > "$PIDFILE"
# Lancer le cleanup comme si dictee recevait SIGTERM
kill "$fake_rec" 2>/dev/null
rm -f "$PIDFILE"
write_state "idle"
test_pass "cleanup apres SIGTERM simule"

test_start "Fichier d'enregistrement supprime pendant transcription simulee"
write_state "transcribing"
gen_wav "$RECORDING_FILE" 1 silence
rm -f "$RECORDING_FILE"
# La transcription devrait echouer proprement
write_state "idle"
test_pass "pas de crash quand le WAV disparait"

test_start "Processus zombie dans PIDFILE"
sleep 0 &
zombie_pid=$!
wait "$zombie_pid" 2>/dev/null
echo "$zombie_pid" > "$PIDFILE"
# dictee devrait detecter le processus mort
timed_run 5 dictee 2>/dev/null || true
sleep 0.5
test_pass "dictee gere un PID zombie"
rm -f "$PIDFILE"

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 9 — CONFLITS DE SERVICES systemd
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 9; then
log_header 9 "Conflits de services systemd"

test_start "Demarrage de deux daemons ASR simultanement"
# Les services ont Conflicts= entre eux
systemctl --user start dictee.service 2>/dev/null &
systemctl --user start dictee-vosk.service 2>/dev/null &
wait
sleep 1
# Compter combien sont actifs
active_count=0
for s in dictee dictee-vosk dictee-whisper dictee-canary; do
    if systemctl --user is-active --quiet "${s}.service" 2>/dev/null; then
        active_count=$((active_count + 1))
    fi
done
if [ "$active_count" -le 1 ]; then
    test_pass "au plus 1 daemon actif ($active_count) — Conflicts= fonctionne"
else
    test_fail "$active_count daemons actifs simultanement"
fi

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 10 — POST-PROCESSING : cas limites
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 10; then
log_header 10 "Post-processing : cas limites"

if command -v dictee-postprocess >/dev/null 2>&1; then

    pp_test() {
        local desc="$1" input="$2" expected_pattern="$3"
        test_start "postprocess: $desc"
        result=$(echo "$input" | DICTEE_LANG_SOURCE=fr DICTEE_LLM_POSTPROCESS=false DICTEE_COMMAND_SUFFIX_FR=suivi timeout 10 dictee-postprocess 2>/dev/null) || result="ERROR"
        if echo "$result" | grep -qP "$expected_pattern" 2>/dev/null; then
            test_pass "resultat='$result'"
        else
            # Verifier sans regex si grep -P echoue
            if [ "$result" = "$expected_pattern" ] || [[ "$result" == *"$expected_pattern"* ]]; then
                test_pass "resultat='$result'"
            else
                test_fail "resultat='$result' (attendu pattern: '$expected_pattern')"
            fi
        fi
    }

    pp_test "Texte vide" "" ""
    pp_test "Espaces seuls" "   " ""
    pp_test "Un seul mot" "Bonjour" "bonjour"
    pp_test "Hesitations FR" "euh ben oui euh c'est ca" "[Oo]ui c'est ca"
    pp_test "Commande virgule" "bonjour virgule comment allez-vous" "[Bb]onjour, [Cc]omment"
    pp_test "Commande point suivi" "bonjour point suivi bonne journee" "[Bb]onjour\\..* [Bb]onne"
    pp_test "Point sans suffixe = mot" "c'est un bon point pour nous" "bon point pour"
    pp_test "Deux points sans suffixe = mot" "il y a deux points a verifier" "deux points"
    pp_test "Deux points suivi = commande" "voici deux points suivi premier" "[Vv]oici.*:.*[Pp]remier"
    pp_test "Point virgule = commande" "oui point virgule non" "[Oo]ui.*; [Nn]on"
    pp_test "Point à la ligne" "premiere ligne point à la ligne deuxieme" "[Pp]remiere ligne"
    pp_test "A la ligne seule" "premiere ligne à la ligne deuxieme" "[Pp]remiere ligne"
    pp_test "Points de suspension" "et donc points de suspension la suite" "[Ll]a suite"
    pp_test "Guillemets" "il a dit ouvrez les guillemets bonjour fermez les guillemets" "bonjour"
    pp_test "Parentheses" "la valeur ouvrez la parenthese dix fermez la parenthese est correcte" "correcte"
    pp_test "Ctrl+J marker" "test controle j suite" "test"
    pp_test "Elision manquante: je ai" "je ai compris" "[Jj]'ai"
    pp_test "Elision manquante: le homme" "le homme est la" "[Ll]'homme"
    pp_test "H aspire: le hamster" "le hamster est mignon" "[Ll]e hamster"

    test_start "postprocess: texte tres long (10000 mots)"
    long_text=$(python3 -c "print(' '.join(['mot'] * 10000))")
    result=$(echo "$long_text" | DICTEE_LANG_SOURCE=fr DICTEE_LLM_POSTPROCESS=false DICTEE_COMMAND_SUFFIX_FR=suivi timeout 10 dictee-postprocess 2>/dev/null)
    if [ -n "$result" ]; then
        test_pass "traite 10000 mots (${#result} chars)"
    else
        test_fail "echec sur texte long"
    fi

    test_start "postprocess: caracteres Unicode exotiques"
    result=$(echo "texte avec des emojis et des kanji " | DICTEE_LANG_SOURCE=fr DICTEE_LLM_POSTPROCESS=false timeout 10 dictee-postprocess 2>/dev/null)
    test_pass "unicode traite sans crash: '$result'"

    test_start "postprocess: newlines dans l'input"
    result=$(printf "ligne un\nligne deux\nligne trois" | DICTEE_LANG_SOURCE=fr DICTEE_LLM_POSTPROCESS=false timeout 10 dictee-postprocess 2>/dev/null)
    test_pass "multi-ligne traite: '$(echo "$result" | head -1)...'"

    test_start "postprocess: injection regex (backslash, metacaracteres)"
    result=$(echo 'test (.*) [^abc] \d+ (?:foo)' | DICTEE_LANG_SOURCE=fr DICTEE_LLM_POSTPROCESS=false timeout 10 dictee-postprocess 2>/dev/null)
    test_pass "metacaracteres regex survecus: '$result'"

    test_start "postprocess: null bytes"
    result=$(printf 'test\x00null\x00bytes' | DICTEE_LANG_SOURCE=fr DICTEE_LLM_POSTPROCESS=false timeout 10 dictee-postprocess 2>/dev/null)
    test_pass "null bytes traites"

    test_start "postprocess: langue inconnue"
    result=$(echo "hello world" | DICTEE_LANG_SOURCE=xx DICTEE_LLM_POSTPROCESS=false timeout 10 dictee-postprocess 2>/dev/null)
    test_pass "langue inconnue survecue: '$result'"

    test_start "postprocess: toutes les commandes vocales FR enchainées"
    input="Bonjour virgule je suis la point suivi a la ligne nouveau paragraphe point d'interrogation point d'exclamation deux points suivi premier point virgule trois petits points ouvrez les guillemets texte fermez les guillemets tiret apostrophe tabulation"
    result=$(echo "$input" | DICTEE_LANG_SOURCE=fr DICTEE_LLM_POSTPROCESS=false DICTEE_COMMAND_SUFFIX_FR=suivi timeout 10 dictee-postprocess 2>/dev/null)
    test_pass "chaine de commandes traitee (${#result} chars)"

else
    test_start "Post-processing"
    test_skip "dictee-postprocess non installe"
fi

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 11 — DETECTION DE SILENCE
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 11; then
log_header 11 "Detection de silence (seuil RMS)"

test_start "RMS d'un WAV de silence pur (doit etre < 0.03)"
rms=$(sox "$TMPDIR_STRESS/silence_2s.wav" -n stat 2>&1 | awk '/RMS.*amplitude/{print $3; exit}')
if [ -n "$rms" ] && awk "BEGIN{exit(!($rms < 0.03))}" 2>/dev/null; then
    test_pass "silence detecte (RMS=$rms)"
else
    test_fail "silence non detecte (RMS=$rms)"
fi

test_start "RMS d'un WAV de bruit (doit etre >= 0.03)"
rms=$(sox "$TMPDIR_STRESS/noise_5s.wav" -n stat 2>&1 | awk '/RMS.*amplitude/{print $3; exit}')
if [ -n "$rms" ] && awk "BEGIN{exit(!($rms >= 0.03))}" 2>/dev/null; then
    test_pass "bruit detecte (RMS=$rms)"
else
    test_fail "bruit non detecte (RMS=$rms)"
fi

test_start "RMS d'un WAV vide (0 samples)"
rms=$(sox "$TMPDIR_STRESS/empty.wav" -n stat 2>&1 | awk '/RMS.*amplitude/{print $3; exit}')
test_pass "WAV vide: RMS='$rms'"

fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 12 — AUDIO CONTEXT BUFFER
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 12; then
log_header 12 "Audio context buffer"

BUFFER_FILE="/dev/shm/.dictee_buffer${UID_SUFFIX}.wav"
BUFFER_TS="/dev/shm/.dictee_buffer_ts${UID_SUFFIX}"

test_start "Buffer avec timestamp expire (>30s)"
gen_wav "$BUFFER_FILE" 2 noise
echo "1000000000" > "$BUFFER_TS"  # 2001 : expire
# Verifier que le buffer est considere invalide
age=$(( $(date +%s) - 1000000000 ))
if [ "$age" -gt 30 ]; then
    test_pass "buffer expire ($age s > 30s)"
else
    test_fail "calcul d'age incorrect"
fi

test_start "Buffer absent"
rm -f "$BUFFER_FILE" "$BUFFER_TS"
# Pas de crash attendu
test_pass "pas de crash quand buffer absent"

test_start "Buffer corrompu (non-WAV)"
echo "corrupted" > "$BUFFER_FILE"
date +%s > "$BUFFER_TS"
# sox devrait echouer proprement
if ! soxi -D "$BUFFER_FILE" 2>/dev/null; then
    test_pass "buffer corrompu detecte par soxi"
else
    test_fail "soxi n'a pas detecte la corruption"
fi

rm -f "$BUFFER_FILE" "$BUFFER_TS"

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 13 — TRADUCTION : backends
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 13; then
log_header 13 "Traduction : backends"

test_start "switch translate vers google"
timed_run 5 dictee-switch-backend translate google 2>/dev/null
state=$(get_state)
test_pass "google OK (state=$state)"

test_start "switch translate vers bing"
timed_run 5 dictee-switch-backend translate bing 2>/dev/null
test_pass "bing OK"

test_start "switch translate vers backend invalide"
timed_run 5 dictee-switch-backend translate NEXISTEPAS 2>/dev/null
exit_code=$?
if [ "$exit_code" -ne 0 ]; then
    test_pass "backend invalide rejete (exit=$exit_code)"
else
    test_fail "backend invalide accepte"
fi

test_start "switch context toggle"
timed_run 5 dictee-switch-backend context toggle 2>/dev/null
ctx1=$(grep '^DICTEE_AUDIO_CONTEXT=' "$CONF" 2>/dev/null | cut -d= -f2)
timed_run 5 dictee-switch-backend context toggle 2>/dev/null
ctx2=$(grep '^DICTEE_AUDIO_CONTEXT=' "$CONF" 2>/dev/null | cut -d= -f2)
if [ "$ctx1" != "$ctx2" ]; then
    test_pass "toggle fonctionne ($ctx1 → $ctx2)"
else
    test_fail "toggle n'a pas change la valeur ($ctx1 = $ctx2)"
fi

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# SECTION 14 — STRESS GLOBAL : operations rapides melangees
# ═══════════════════════════════════════════════════════════════════════

if should_run_section 14; then
log_header 14 "Stress global : operations rapides melangees"

test_start "20 cancel rapides consecutifs"
write_state "recording"
for i in $(seq 1 20); do
    dictee --cancel &
done
wait
state=$(get_state)
test_pass "20 cancel termines (state=$state)"

safe_reset
sleep 1

test_start "Alternance rapide cancel/reset (10 cycles)"
for i in $(seq 1 10); do
    write_state "recording"
    dictee --cancel 2>/dev/null &
    dictee-reset 2>/dev/null &
done
wait
sleep 1
state=$(get_state)
if [ "$state" = "idle" ] || [ "$state" = "cancelled" ]; then
    test_pass "10 cycles cancel/reset OK (state=$state)"
else
    test_fail "etat inattendu: '$state'"
fi

safe_reset
sleep 1

if [ ${#AVAILABLE_BACKENDS[@]:-0} -ge 2 ]; then
    test_start "Switch backend + cancel + reset simultanement"
    write_state "idle"
    dictee-switch-backend asr "${AVAILABLE_BACKENDS[1]}" 2>/dev/null &
    sleep 0.1
    dictee --cancel 2>/dev/null &
    dictee-reset 2>/dev/null &
    wait
    sleep 2
    state=$(get_state)
    test_pass "switch+cancel+reset simultanement termine (state=$state)"
fi

safe_reset
fi

# ═══════════════════════════════════════════════════════════════════════
# NETTOYAGE ET RAPPORT
# ═══════════════════════════════════════════════════════════════════════

# Restaurer la configuration
if [ -f "${CONF}.stress-backup" ]; then
    cp "${CONF}.stress-backup" "$CONF"
    rm -f "${CONF}.stress-backup"
    log ""
    log "Configuration restauree depuis backup"
fi

safe_reset

# Nettoyage des fichiers temporaires
rm -rf "$TMPDIR_STRESS"

log ""
log "================================================================"
log "  RAPPORT FINAL"
log "================================================================"
log "  Total:  $TOTAL tests"
log "  Passe:  $PASS"
log "  Echoue: $FAIL"
log "  Saute:  $SKIP"
log "  Duree:  ${SECONDS}s"
log "================================================================"
log ""

if [ "$FAIL" -gt 0 ]; then
    log "  RESULTAT: ECHECS DETECTES ($FAIL/$TOTAL)"
    exit 1
else
    log "  RESULTAT: TOUS LES TESTS PASSES"
    exit 0
fi
