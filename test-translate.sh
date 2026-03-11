#!/bin/bash
# test-translate.sh — Compare les backends de traduction
# Usage: ./test-translate.sh [fr:en] ["texte à traduire"]

PAIR="${1:-fr:en}"
SRC="${PAIR%%:*}"
TGT="${PAIR##*:}"

TEXT="${2:-Bonjour, comment allez-vous ? Je suis très content de vous rencontrer.}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

printf "${BOLD}Traduction ${SRC} → ${TGT}${NC}\n"
printf "${CYAN}Texte :${NC} %s\n\n" "$TEXT"

sep() { printf '%.0s─' {1..60}; echo; }

benchmark() {
    local name="$1"
    shift
    local start end elapsed result
    start=$(date +%s%N)
    result=$("$@" 2>&1)
    end=$(date +%s%N)
    elapsed=$(( (end - start) / 1000000 ))

    if [ -n "$result" ] && ! echo "$result" | grep -qi "error\|erreur"; then
        printf "${GREEN}✓ %-20s${NC} %4d ms\n" "$name" "$elapsed"
        printf "  %s\n" "$result"
    else
        printf "${RED}✗ %-20s${NC} %4d ms\n" "$name" "$elapsed"
        printf "  ${RED}%s${NC}\n" "$result"
    fi
    echo
}

# --- translate-shell (Google) ---
if command -v trans &>/dev/null; then
    sep
    benchmark "trans (google)" trans -b -e google "${SRC}:${TGT}" "$TEXT"
    benchmark "trans (bing)" trans -b -e bing "${SRC}:${TGT}" "$TEXT"
else
    printf "${YELLOW}⚠ translate-shell non installé${NC}\n\n"
fi

# --- LibreTranslate (Docker) ---
sep
if curl -s --max-time 2 "http://localhost:5000/languages" &>/dev/null; then
    lt_translate() {
        local json_text
        json_text=$(printf '%s' "$TEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
        curl -s --max-time 15 "http://localhost:5000/translate" \
            -H "Content-Type: application/json" \
            -d "{\"q\":${json_text},\"source\":\"${SRC}\",\"target\":\"${TGT}\"}" \
            | python3 -c 'import json,sys; print(json.load(sys.stdin)["translatedText"])'
    }
    benchmark "LibreTranslate" lt_translate
else
    printf "${YELLOW}⚠ LibreTranslate non disponible (port 5000)${NC}\n\n"
fi

# --- ollama ---
if command -v ollama &>/dev/null; then
    sep
    ollama_translate() {
        local model="${DICTEE_OLLAMA_MODEL:-translategemma}"
        [[ "$model" == *:* ]] || model="${model}:latest"
        local prompt="Translate from ${SRC} to ${TGT}. Output ONLY the translation, nothing else: ${TEXT}"
        ollama run "$model" "$prompt" 2>/dev/null
    }
    benchmark "ollama" ollama_translate
else
    printf "${YELLOW}⚠ ollama non installé${NC}\n\n"
fi
