#!/usr/bin/env python3
"""dictee-postprocess — filtre post-traitement pour la dictée vocale.

Lit le texte transcrit sur stdin, applique séquentiellement :
  1. Règles regex (système + utilisateur)
  2. Dictionnaire personnel (remplacement mot-à-mot)
  3. Correction LLM optionnelle (ollama)

Écrit le résultat sur stdout.

Configuration via variables d'environnement :
  DICTEE_LANG_SOURCE  — langue source (fr, en, de, ...) pour filtrer les règles [lang]
  DICTEE_LLM_POSTPROCESS — true/false (défaut: false)
  DICTEE_LLM_MODEL    — modèle ollama (défaut: ministral:3b)
  DICTEE_LLM_TIMEOUT  — timeout en secondes (défaut: 10)
"""

import os
import re
import sys
import subprocess

# ── Chemins ──────────────────────────────────────────────────────────

XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
USER_RULES = os.path.join(XDG_CONFIG, "dictee", "rules.conf")
USER_DICT = os.path.join(XDG_CONFIG, "dictee", "dictionary.conf")

XDG_DATA = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
SYSTEM_RULES_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.conf.default"),
    "/usr/share/dictee/rules.conf.default",
    os.path.join(XDG_DATA, "dictee", "rules.conf.default"),
]

LANG = os.environ.get("DICTEE_LANG_SOURCE", "").lower()[:2]

# ── Chargement des règles regex ──────────────────────────────────────

_RULE_RE = re.compile(
    r"^\s*\[([a-z]{2}|\*)\]\s*/(.+)/(.+)/([ig]*)\s*$"
)


def _parse_rules(path):
    """Parse un fichier de règles, retourne [(pattern_compiled, replacement, lang)]."""
    rules = []
    if not os.path.isfile(path):
        return rules
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _RULE_RE.match(line)
            if not m:
                continue
            lang_tag, pattern, replacement, flags_str = m.groups()
            # Filtrer par langue
            if lang_tag != "*" and LANG and lang_tag != LANG:
                continue
            flags = 0
            if "i" in flags_str:
                flags |= re.IGNORECASE
            try:
                compiled = re.compile(pattern, flags)
            except re.error:
                continue
            # Convertir les séquences d'échappement dans le remplacement
            replacement = replacement.replace("\\n", "\n").replace("\\t", "\t")
            rules.append((compiled, replacement))
    return rules


def load_rules():
    """Charge les règles système puis utilisateur."""
    rules = []
    for candidate in SYSTEM_RULES_CANDIDATES:
        if os.path.isfile(candidate):
            rules.extend(_parse_rules(candidate))
            break
    rules.extend(_parse_rules(USER_RULES))
    return rules


def apply_rules(text, rules):
    """Applique les règles regex séquentiellement."""
    for pattern, replacement in rules:
        text = pattern.sub(replacement, text)
    return text


# ── Chargement du dictionnaire ───────────────────────────────────────

_DICT_RE = re.compile(
    r"^\s*\[([a-z]{2}|\*)\]\s*(.+?)=(.+?)\s*$"
)


def load_dictionary():
    """Charge le dictionnaire personnel, retourne [(word_re, replacement)]."""
    entries = []
    if not os.path.isfile(USER_DICT):
        return entries
    with open(USER_DICT, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _DICT_RE.match(line)
            if not m:
                continue
            lang_tag, word, replacement = m.groups()
            if lang_tag != "*" and LANG and lang_tag != LANG:
                continue
            try:
                word_re = re.compile(
                    r"\b" + re.escape(word.strip()) + r"\b",
                    re.IGNORECASE,
                )
            except re.error:
                continue
            entries.append((word_re, replacement.strip()))
    return entries


def apply_dictionary(text, entries):
    """Applique le dictionnaire avec préservation de casse."""
    for word_re, replacement in entries:
        def _replace(m, repl=replacement):
            orig = m.group(0)
            if orig.isupper():
                return repl.upper()
            if orig[0].isupper():
                return repl[0].upper() + repl[1:]
            return repl
        text = word_re.sub(_replace, text)
    return text


# ── Correction LLM (ollama) ─────────────────────────────────────────

DEFAULT_PROMPT = (
    "Fix grammar, spelling, and punctuation in this {lang} text from speech "
    "recognition. Preserve meaning exactly. Output ONLY the corrected text, "
    "nothing else.\n\n{text}"
)

PROMPT_PATH = os.path.join(XDG_CONFIG, "dictee", "llm-prompt.txt")


def _load_prompt():
    if os.path.isfile(PROMPT_PATH):
        with open(PROMPT_PATH, encoding="utf-8") as f:
            return f.read().strip()
    return DEFAULT_PROMPT


def llm_postprocess(text):
    """Envoie le texte à ollama pour correction grammaticale."""
    model = os.environ.get("DICTEE_LLM_MODEL", "ministral:3b")
    timeout = int(os.environ.get("DICTEE_LLM_TIMEOUT", "10"))
    lang_name = {
        "fr": "French", "en": "English", "de": "German",
        "es": "Spanish", "it": "Italian", "pt": "Portuguese",
        "uk": "Ukrainian",
    }.get(LANG, LANG or "the original")

    prompt_tpl = _load_prompt()
    prompt = prompt_tpl.format(lang=lang_name, text=text)

    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return text  # fallback : texte inchangé


# ── Main ─────────────────────────────────────────────────────────────

def main():
    text = sys.stdin.read()
    if not text.strip():
        sys.stdout.write(text)
        return

    # 1. Règles regex
    rules = load_rules()
    if rules:
        text = apply_rules(text, rules)

    # 2. Dictionnaire personnel
    dictionary = load_dictionary()
    if dictionary:
        text = apply_dictionary(text, dictionary)

    # 3. Correction LLM (optionnelle)
    if os.environ.get("DICTEE_LLM_POSTPROCESS", "false").lower() == "true":
        text = llm_postprocess(text)

    sys.stdout.write(text)


if __name__ == "__main__":
    main()
