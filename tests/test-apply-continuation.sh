#!/bin/bash
# Isolated tests for the apply_continuation bash function in dictee.
# Mocks safe_dotool to count backspaces without sending real key events.
#
# Usage: bash tests/test-apply-continuation.sh

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DICTEE_SCRIPT="$PROJECT_DIR/dictee"

TMPDIR=$(mktemp -d /tmp/dictee-test-apply-cont.XXXXXX)
trap "rm -rf $TMPDIR" EXIT

LAST_WORD_FILE="$TMPDIR/last_word"
BS_LOG="$TMPDIR/bs_count"

LANG_SOURCE="fr"
CONTINUATION_INDICATOR=">>"
CONTINUATION_INDICATOR_LEN=2
DICTEE_PP_TYPOGRAPHY=true

# Minimal continuation words (real lists come from continuation.conf)
CONTINUATION_WORDS_FR=" dans sur sous avec sans pour par vers depuis chez entre de du des la le les un une et ou mais "
CONTINUATION_WORDS_EN=" in on for with by from of the a an and or but "

_dbg() { :; }

safe_dotool() {
    local input
    input=$(cat)
    local n
    n=$(echo -n "$input" | grep -c "^key backspace$" || true)
    echo "$n" >> "$BS_LOG"
}

# Extract apply_continuation from the live dictee script
eval "$(awk '/^apply_continuation\(\) \{/,/^\}/' "$DICTEE_SCRIPT")"

# Keyword regex is not used by these scenarios
_CONT_KEYWORD_RE=""

pass=0
fail=0

run_case() {
    local label="$1" state="$2" input="$3" lang="$4" displayed_before="$5" expected="$6"
    echo "$state" > "$LAST_WORD_FILE"
    : > "$BS_LOG"
    LANG_SOURCE="$lang"
    local text="$input"
    apply_continuation text
    local total_bs=0
    while read -r n; do total_bs=$((total_bs + n)); done < "$BS_LOG"
    local displayed="$displayed_before"
    if (( total_bs > 0 )); then
        displayed="${displayed:0:${#displayed}-total_bs}"
    fi
    local text_printable="${text//$'\x02'/}"
    displayed="${displayed}${text_printable}"
    if [ "$displayed" = "$expected" ]; then
        printf "  \033[32mPASS\033[0m  %s\n" "$label"
        pass=$((pass + 1))
    else
        printf "  \033[31mFAIL\033[0m  %s\n        got:      %q\n        expected: %q\n" \
            "$label" "$displayed" "$expected"
        fail=$((fail + 1))
    fi
}

echo "── apply_continuation: hourglass + voice-command punctuation (FR/EN)"

run_case "1. hourglass + point final" \
    "H2_:dans" $'.\x02 Je pars' "fr" "je suis dans>>" \
    "je suis dans. Je pars"

run_case "2. hourglass + virgule" \
    "H2_:dans" ", puis là" "fr" "je suis dans>>" \
    "je suis dans, puis là"

run_case "3. hourglass + point d'exclamation" \
    "H2_:dans" "! Allons-y" "fr" "je suis dans>>" \
    $'je suis dans\u202f! Allons-y'

run_case "4. hourglass + deux points" \
    "H2_:dans" ": voici" "fr" "je suis dans>>" \
    $'je suis dans\u00a0: voici'

run_case "5. non-régression: continuation texte normal" \
    "H2_:dans" "pour aller loin" "fr" "je suis dans>>" \
    "je suis dans pour aller loin"

run_case "6. non-hourglass FR + !" \
    ".1:bonjour" "! Allons-y" "fr" "bonjour." \
    $'bonjour\u202f! Allons-y'

run_case "7. non-hourglass FR + :" \
    ".1:bonjour" ": voici" "fr" "bonjour." \
    $'bonjour\u00a0: voici'

run_case "8. EN hourglass + ! (pas de NNBSP)" \
    "H2_:in" "! Let's go" "en" "I am in>>" \
    "I am in! Let's go"

echo ""
echo "Résultat: $pass passed, $fail failed"
exit $fail
