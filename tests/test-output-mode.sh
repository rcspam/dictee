#!/bin/bash
# Isolated tests for the DICTEE_OUTPUT_MODE dispatch (#28): emit_text,
# _emit_sanitize, _paste_typewriter, plus the clipboard-mode guards in
# apply_continuation and save_last_word.
# Mocks safe_dotool / safe_dotool_key_ctrl / force_copy_to_clipboard so no
# real key event or clipboard write ever happens.
#
# Usage: bash tests/test-output-mode.sh

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DICTEE_SCRIPT="$PROJECT_DIR/dictee"

TMPDIR=$(mktemp -d /tmp/dictee-test-output-mode.XXXXXX)
trap "rm -rf $TMPDIR" EXIT

LAST_WORD_FILE="$TMPDIR/last_word"
DOTOOL_LOG="$TMPDIR/dotool_log"     # every line piped into safe_dotool
CTRL_LOG="$TMPDIR/ctrl_log"         # every safe_dotool_key_ctrl combo
CLIP_FILE="$TMPDIR/clipboard"       # current fake clipboard content
COPY_LOG="$TMPDIR/copy_log"         # one line per force_copy_to_clipboard call

LANG_SOURCE="fr"
CONTINUATION_INDICATOR=">>"
CONTINUATION_INDICATOR_LEN=2
DICTEE_PP_TYPOGRAPHY=true
CONTINUATION_WORDS_FR=" dans sur sous avec sans pour par vers depuis chez entre de du des la le les un une et ou mais "
_CONT_KEYWORD_RE=""

_dbg() { :; }
sleep() { :; }   # speed: neutralize cadence/settle pauses
_DOTOOL_NEEDS_SG=0

# dotool mock: consumed by the persistent >(dotool) process substitution
# of _paste_typewriter (functions ARE visible in process substitutions of
# the same shell) as well as by safe_dotool below.
dotool() {
    cat >> "$DOTOOL_LOG"
}
safe_dotool() {
    cat >> "$DOTOOL_LOG"
}
safe_dotool_key_ctrl() {
    echo "$1" >> "$CTRL_LOG"
    # mirror the real chord into the dotool log for completeness
    echo "key $1" >> "$DOTOOL_LOG"
}
force_copy_to_clipboard() {
    printf '%s' "$1" > "$CLIP_FILE"
    printf '%s\x00' "$1" >> "$COPY_LOG"
}

# Extract the functions under test from the live dictee script
for fn in _emit_sanitize _paste_typewriter emit_text type_text \
          apply_continuation save_last_word; do
    body=$(awk "/^${fn}\(\) \{/,/^\}/" "$DICTEE_SCRIPT")
    [ -n "$body" ] || { echo "FATAL: function $fn not found in dictee"; exit 1; }
    eval "$body"
done

pass=0
fail=0

reset_logs() {
    : > "$DOTOOL_LOG"; : > "$CTRL_LOG"; : > "$COPY_LOG"
    printf 'SENTINEL' > "$CLIP_FILE"
    rm -f "$LAST_WORD_FILE"
}

check() {   # $1 label, $2 got, $3 expected
    if [ "$2" = "$3" ]; then
        printf "  \033[32mPASS\033[0m  %s\n" "$1"
        pass=$((pass + 1))
    else
        printf "  \033[31mFAIL\033[0m  %s\n        got:      %q\n        expected: %q\n" \
            "$1" "$2" "$3"
        fail=$((fail + 1))
    fi
}

count_ctrl_v() { grep -c '^ctrl+v$' "$CTRL_LOG" 2>/dev/null || true; }
count_bs()     { grep -c '^key backspace$' "$DOTOOL_LOG" 2>/dev/null || true; }
copy_calls()   { tr -cd '\0' < "$COPY_LOG" | wc -c; }

echo "── emit_text: mode type (défaut inchangé)"
reset_logs
OUTPUT_MODE="type"; PASTE_STYLE="block"
emit_text "Bonjour tout le monde."
check "type: dotool reçoit un type" "$(grep -c '^type ' "$DOTOOL_LOG")" "1"
check "type: aucune copie presse-papier" "$(copy_calls)" "0"
check "type: aucun ctrl+v" "$(count_ctrl_v)" "0"

echo "── emit_text: mode clipboard"
reset_logs
OUTPUT_MODE="clipboard"
emit_text "Bonjour."
check "clipboard: contenu copié" "$(cat "$CLIP_FILE")" "Bonjour."
check "clipboard: aucun événement dotool" "$(wc -l < "$DOTOOL_LOG")" "0"

reset_logs
emit_text $'Salut.\x02'
check "clipboard: \\x02 strippé (V3)" "$(cat "$CLIP_FILE")" "Salut."

reset_logs
emit_text $'ligne un\x01ligne deux'
check "clipboard: \\x01 devient newline (V9)" "$(cat "$CLIP_FILE")" $'ligne un\nligne deux'

reset_logs
emit_text $'\x01'
check "clipboard: push marqueur-seul ne touche pas le presse-papier (V10)" \
    "$(cat "$CLIP_FILE")" "SENTINEL"
reset_logs
emit_text "   "
check "clipboard: push espaces-seuls ne touche pas le presse-papier (V10)" \
    "$(cat "$CLIP_FILE")" "SENTINEL"

reset_logs
emit_text $'caf\xc3\xa9\xe2\x80\xa6 fin\x02'
check "clipboard: unicode riche conservé (… intact)" \
    "$(cat "$CLIP_FILE")" $'caf\xc3\xa9\xe2\x80\xa6 fin'

echo "── emit_text: mode paste (bloc)"
reset_logs
OUTPUT_MODE="paste"; PASTE_STYLE="block"
emit_text $'Il pense\xe2\x80\xa6 vraiment.\x02'
check "paste: … converti en ... (V2, décomptes backspace)" \
    "$(cat "$CLIP_FILE")" "Il pense... vraiment."
check "paste: exactement un ctrl+v" "$(count_ctrl_v)" "1"

reset_logs
emit_text $'\x01'
check "paste: push marqueur-seul = ni copie ni ctrl+v (V10)" \
    "$(cat "$CLIP_FILE")|$(count_ctrl_v)" "SENTINEL|0"

echo "── emit_text: mode paste (typewriter)"
reset_logs
PASTE_STYLE="typewriter"
emit_text "hello, how are you?"
command sleep 0.3   # real sleep: let the >(dotool) substitution flush its log
check "typewriter: 4 ctrl+v via le dotool persistant (un par mot)" \
    "$(grep -c '^key ctrl+v$' "$DOTOOL_LOG")" "4"
check "typewriter: 5 copies (4 chunks + texte complet final)" "$(copy_calls)" "5"
check "typewriter: presse-papier final = texte complet" \
    "$(cat "$CLIP_FILE")" "hello, how are you?"
# chunk concatenation must reproduce the text byte-for-byte
check "typewriter: concat(chunks) == texte" \
    "$(tr '\0' '|' < "$COPY_LOG")" \
    "hello,| how| are| you?|hello, how are you?|"

echo "── garde V1: save_last_word en mode clipboard"
reset_logs
OUTPUT_MODE="clipboard"
text="je vais dans le"
echo "H2_:précédent" > "$LAST_WORD_FILE"
save_last_word "$text" text
check "clipboard: state file purgé (pas de promesse de backspaces)" \
    "$([ -f "$LAST_WORD_FILE" ] && echo present || echo absent)" "absent"
check "clipboard: indicateur >> jamais appendu au texte" "$text" "je vais dans le"

echo "── garde V1: apply_continuation en mode clipboard (marqueur hérité)"
reset_logs
OUTPUT_MODE="clipboard"
echo "H2_:dans" > "$LAST_WORD_FILE"   # promesse laissée par un push type antérieur
text="la suite"
apply_continuation text
check "clipboard: zéro backspace émis" "$(count_bs)" "0"
check "clipboard: texte non modifié (pushes indépendants)" "$text" "la suite"
check "clipboard: state hérité purgé" \
    "$([ -f "$LAST_WORD_FILE" ] && echo present || echo absent)" "absent"

echo "── garde V1 croisée: retour en mode type après un push clipboard"
reset_logs
OUTPUT_MODE="type"
text="nouvelle phrase"
apply_continuation text   # state absent (purgé au push clipboard) → no-op
check "type après clipboard: zéro backspace fantôme" "$(count_bs)" "0"
check "type après clipboard: texte intact" "$text" "nouvelle phrase"

echo "── mode paste: la continuation reste active (V2)"
reset_logs
OUTPUT_MODE="paste"
echo "H2_:dans" > "$LAST_WORD_FILE"
text="pour la suite"
apply_continuation text
check "paste: les 2 backspaces de l'indicateur sont émis" "$(count_bs)" "2"
text2="je vais dans le"
save_last_word "$text2" text2
check "paste: l'indicateur est appendu comme en mode type" "$text2" "je vais dans le>>"
check "paste: marqueur H2_ écrit" "$(cat "$LAST_WORD_FILE")" "H2_:le"

echo "── save_last_word: mode type inchangé (non-régression)"
reset_logs
OUTPUT_MODE="type"
text3="je vais dans le"
save_last_word "$text3" text3
check "type: indicateur appendu" "$text3" "je vais dans le>>"
check "type: marqueur écrit" "$(cat "$LAST_WORD_FILE")" "H2_:le"

echo
echo "Résultat: $pass PASS, $fail FAIL"
[ "$fail" -eq 0 ]
