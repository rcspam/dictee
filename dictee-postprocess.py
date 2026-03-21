#!/usr/bin/env python3
"""dictee-postprocess — filtre post-traitement pour la dictée vocale.

Lit le texte transcrit sur stdin, applique séquentiellement :
  1.  Règles regex (annotations, hésitations, commandes vocales, dédup, ponctuation, élisions)
  2.  Élisions françaises avancées (avec h aspirés)
  3.  Conversion nombres en chiffres (text2num, optionnel)
  4.  Typographie française (espaces insécables)
  5.  Dictionnaire (système + personnel, avec matching phonétique jellyfish)
  6.  Capitalisation
  7.  Correction LLM optionnelle (ollama)

Écrit le résultat sur stdout.

Configuration via variables d'environnement :
  DICTEE_LANG_SOURCE       — langue source (fr, en, de, ...) pour filtrer les règles
  DICTEE_PP_ELISIONS       — true/false (défaut: true)  — élisions françaises avancées
  DICTEE_PP_NUMBERS        — true/false (défaut: true)  — conversion nombres→chiffres
  DICTEE_PP_TYPOGRAPHY     — true/false (défaut: true)  — typographie française
  DICTEE_PP_CAPITALIZATION — true/false (défaut: true)  — capitalisation automatique
  DICTEE_PP_FUZZY_DICT     — true/false (défaut: true)  — matching phonétique dictionnaire
  DICTEE_LLM_POSTPROCESS   — true/false (défaut: false) — correction LLM
  DICTEE_LLM_MODEL         — modèle ollama (défaut: gemma3:4b)
  DICTEE_LLM_TIMEOUT       — timeout en secondes (défaut: 10)
"""

import os
import re
import sys
import subprocess

# ── Venv bootstrap ───────────────────────────────────────────────────
# If a dedicated venv exists (with text2num, jellyfish, etc.),
# add its site-packages to sys.path so imports work without re-exec.
# Re-exec via os.execv would lose stdin (pipe), so we inject the path instead.

XDG_DATA = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
_VENV_DIR = os.path.join(XDG_DATA, "dictee", "postprocess-env")
_VENV_SITE = os.path.join(
    _VENV_DIR, "lib",
    f"python{sys.version_info.major}.{sys.version_info.minor}",
    "site-packages",
)
if os.path.isdir(_VENV_SITE) and _VENV_SITE not in sys.path:
    sys.path.insert(0, _VENV_SITE)

# ── Chemins ──────────────────────────────────────────────────────────

XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))

USER_RULES = os.path.join(XDG_CONFIG, "dictee", "rules.conf")
USER_DICT = os.path.join(XDG_CONFIG, "dictee", "dictionary.conf")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SYSTEM_RULES_CANDIDATES = [
    os.path.join(_SCRIPT_DIR, "rules.conf.default"),
    "/usr/share/dictee/rules.conf.default",
    os.path.join(XDG_DATA, "dictee", "rules.conf.default"),
]

SYSTEM_DICT_CANDIDATES = [
    os.path.join(_SCRIPT_DIR, "dictionary.conf.default"),
    "/usr/share/dictee/dictionary.conf.default",
    os.path.join(XDG_DATA, "dictee", "dictionary.conf.default"),
]

SYSTEM_CONT_CANDIDATES = [
    os.path.join(_SCRIPT_DIR, "continuation.conf.default"),
    "/usr/share/dictee/continuation.conf.default",
    os.path.join(XDG_DATA, "dictee", "continuation.conf.default"),
]

USER_CONT = os.path.join(XDG_CONFIG, "dictee", "continuation.conf")

LANG = os.environ.get("DICTEE_LANG_SOURCE", "").lower()[:2]


def _env_bool(var, default="true"):
    """Lit une variable d'environnement booléenne."""
    return os.environ.get(var, default).lower() == "true"


# ── Chargement des règles regex ──────────────────────────────────────

_RULE_RE = re.compile(
    r"^\s*\[([a-z]{2}|\*)\]\s*/(.+)/(.+)/([igm]*)\s*$"
)

# Règles avec remplacement vide : /PATTERN//FLAGS
_RULE_EMPTY_RE = re.compile(
    r"^\s*\[([a-z]{2}|\*)\]\s*/(.+)//([igm]*)\s*$"
)


def _parse_rules(path):
    """Parse un fichier de règles, retourne [(pattern_compiled, replacement)]."""
    rules = []
    if not os.path.isfile(path):
        return rules
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Essayer d'abord le remplacement vide
            m = _RULE_EMPTY_RE.match(line)
            if m:
                lang_tag, pattern, flags_str = m.groups()
                replacement = ""
            else:
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
            if "m" in flags_str:
                flags |= re.MULTILINE
            # \s dans les classes [,.\s] ne doit pas manger les \n produits par d'autres règles
            # Remplacer \s par \t  (espace + tab) dans les classes de caractères
            pattern = re.sub(r'\[([^\]]*?)\\s([^\]]*?)\]',
                             lambda m: '[' + m.group(1) + r' \t' + m.group(2) + ']',
                             pattern)
            try:
                compiled = re.compile(pattern, flags)
            except re.error:
                continue
            # Convertir les séquences d'échappement dans le remplacement
            replacement = (replacement
                           .replace("\\n", "\n")
                           .replace("\\t", "\t")
                           .replace("\\u00a0", "\u00a0")
                           .replace("\\u202f", "\u202f")
                           .replace("\\u2026", "\u2026")
                           .replace("\\u2014", "\u2014")
                           .replace("\\u00ab", "\u00ab")
                           .replace("\\u00bb", "\u00bb"))
            rules.append((compiled, replacement))
    return rules


def load_rules():
    """Charge les règles utilisateur (ou le système par défaut)."""
    if os.path.isfile(USER_RULES):
        return _parse_rules(USER_RULES)
    # Fallback : fichier système
    for candidate in SYSTEM_RULES_CANDIDATES:
        if os.path.isfile(candidate):
            return _parse_rules(candidate)
    return []


def apply_rules(text, rules):
    """Applique les règles regex séquentiellement."""
    for pattern, replacement in rules:
        text = pattern.sub(replacement, text)
    return text


# ── Continuation (suppression points erronés après mots de classe fermée) ──

_CONT_LINE_RE = re.compile(r"^\s*\[([a-z]{2}|\*)\]\s*(.+)$")

def _parse_continuation(path):
    words = set()
    if not os.path.isfile(path):
        return words
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _CONT_LINE_RE.match(line)
            if not m:
                continue
            lang_tag, word_list = m.groups()
            if lang_tag != "*" and LANG and lang_tag != LANG:
                continue
            for w in word_list.split():
                words.add(w.lower())
    return words

def load_continuation():
    """Charge les mots de continuation utilisateur (ou le système par défaut)."""
    if os.path.isfile(USER_CONT):
        return _parse_continuation(USER_CONT)
    # Fallback : fichier système
    for candidate in SYSTEM_CONT_CANDIDATES:
        if os.path.isfile(candidate):
            return _parse_continuation(candidate)
    return set()

def fix_continuation(text, continuation_words):
    """Supprime les points erronés après un mot de continuation.
    Préserve la casse du mot suivant (noms propres)."""
    if not continuation_words:
        return text

    def _fix(m):
        word = m.group(1)
        after_char = m.group(2)
        if word.lower() in continuation_words:
            return word + " " + after_char
        return m.group(0)

    return re.sub(r"(\w+)\.[ \t]+([A-Za-zÀ-ÿ])", _fix, text)


# ── Élisions françaises avancées ─────────────────────────────────────

# Mots commençant par h aspiré (PAS d'élision)
H_ASPIRE = frozenset({
    'hache', 'haie', 'haine', 'hall', 'halte', 'halo',
    'hamac', 'hameau', 'hamster', 'hanche', 'handicap', 'hangar',
    'hanter', 'happer', 'harasser', 'harceler', 'hardi', 'harem',
    'hareng', 'haricot', 'harpe', 'hasard', 'hâte',
    'hausse', 'haut', 'haute', 'hauts', 'hautes', 'hauteur', 'havre',
    'hérisson', 'hernie', 'héron', 'héros', 'herse', 'hêtre',
    'heurter', 'hibou', 'hiérarchie', 'hippie', 'hisser', 'hocher',
    'hockey', 'hollande', 'homard', 'hongrie', 'honte', 'hoquet',
    'horde', 'hors', 'hot', 'hotte', 'houblon', 'houille', 'houle',
    'housse', 'hublot', 'huer', 'huit', 'huitième', 'hurler', 'hutte',
    'hyène',
})

ELISION_WORDS = {
    'je': "j'", 'me': "m'", 'te': "t'", 'se': "s'",
    'le': "l'", 'la': "l'", 'ne': "n'", 'de': "d'",
    'que': "qu'", 'ce': "c'",
}

_VOWELS = 'aeiouyàâäéèêëîïôöùûüÿæœ'
_VOWEL_PATTERN = f'[{_VOWELS}{_VOWELS.upper()}]'
# h muet suivi de voyelle (mais PAS h aspiré)
_H_MUET_VOWEL = f'[hH]{_VOWEL_PATTERN}'

# Pré-compiler les patterns d'élision
_H_ASPIRE_SORTED = sorted(H_ASPIRE, key=len, reverse=True)
_H_ASPIRE_RE = '|'.join(re.escape(h) for h in _H_ASPIRE_SORTED)
_ELISION_PATTERNS = []
for _word, _elided in ELISION_WORDS.items():
    # Matche : mot + espace + (voyelle OU h muet), sauf h aspiré
    _pat = re.compile(
        rf'\b{re.escape(_word)}\s+(?!(?:{_H_ASPIRE_RE})\b)({_VOWEL_PATTERN}\w*|{_H_MUET_VOWEL}\w*)',
        re.IGNORECASE
    )
    _ELISION_PATTERNS.append((_pat, _elided))

_SI_IL_RE = re.compile(r'\bsi\s+(ils?)\b', re.IGNORECASE)


def fix_elisions(text):
    """Corrige les élisions manquantes (je ai → j'ai) avec h aspirés."""
    for pattern, elided in _ELISION_PATTERNS:
        def _elide(m, e=elided):
            rest = m.group(1)
            # Préserver la casse : si le mot original commençait par majuscule
            # et l'élision est en début de phrase, garder la majuscule sur l'élision
            return e + rest.lower() if rest[0].isupper() and len(rest) > 1 and rest[1:] == rest[1:].lower() else e + rest
        text = pattern.sub(_elide, text)
    text = _SI_IL_RE.sub(r"s'\1", text)
    return text


# ── Conversion nombres (text2num) ────────────────────────────────────

try:
    from text_to_num import alpha2digit
    _HAS_TEXT2NUM = True
except ImportError:
    _HAS_TEXT2NUM = False

_TEXT2NUM_LANGS = frozenset({'fr', 'en', 'es', 'pt', 'de', 'it', 'nl'})


def convert_numbers(text):
    """Convertit les nombres en toutes lettres en chiffres."""
    if not _HAS_TEXT2NUM or LANG not in _TEXT2NUM_LANGS:
        return text
    try:
        return alpha2digit(text, LANG)
    except Exception:
        return text


# ── Typographie française ────────────────────────────────────────────

_NBSP = '\u00a0'     # espace insécable (avant :, après «, avant »)
_NNBSP = '\u202f'    # espace fine insécable (avant ; ? !)

# Pré-compiler les patterns de typographie
_TYPO_BEFORE_THIN = re.compile(r'(?<=\S)\s*([;!?])') # espace fine insécable avant ; ! ? (sauf début de ligne)
_TYPO_BEFORE_COLON = re.compile(r'(?<=\S)\s*(:)')   # espace insécable avant : (sauf début de ligne)
_TYPO_AFTER_LGUILL = re.compile(r'«\s*')           # espace après «
_TYPO_BEFORE_RGUILL = re.compile(r'\s*»')          # espace avant »
_TYPO_ELLIPSIS = re.compile(r'\.{3,}')             # ... → …
_TYPO_EN_QUOTES = re.compile(r'"([^"]+)"')         # "x" → « x »


def fix_french_typography(text):
    """Applique les règles typographiques françaises."""
    # Points de suspension
    text = _TYPO_ELLIPSIS.sub('\u2026', text)
    # Guillemets anglais → français
    text = _TYPO_EN_QUOTES.sub(f'\u00ab{_NBSP}\\1{_NBSP}\u00bb', text)
    # Espaces insécables avant ponctuation haute
    text = _TYPO_BEFORE_THIN.sub(f'{_NNBSP}\\1', text)
    text = _TYPO_BEFORE_COLON.sub(f'{_NBSP}\\1', text)
    # Espaces autour des guillemets
    text = _TYPO_AFTER_LGUILL.sub(f'\u00ab{_NBSP}', text)
    text = _TYPO_BEFORE_RGUILL.sub(f'{_NBSP}\u00bb', text)
    return text


# ── Chargement du dictionnaire ───────────────────────────────────────

_DICT_RE = re.compile(
    r"^\s*\[([a-z]{2}|\*)\]\s*(.+?)=(.+?)\s*$"
)


def _parse_dictionary(path):
    """Parse un fichier de dictionnaire, retourne [(word, word_re, replacement)]."""
    entries = []
    if not os.path.isfile(path):
        return entries
    with open(path, encoding="utf-8") as f:
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
            word = word.strip()
            replacement = replacement.strip()
            try:
                word_re = re.compile(
                    r"\b" + re.escape(word) + r"\b",
                    re.IGNORECASE,
                )
            except re.error:
                continue
            entries.append((word, word_re, replacement))
    return entries


def load_dictionary():
    """Charge le dictionnaire utilisateur (ou le système par défaut)."""
    if os.path.isfile(USER_DICT):
        return _parse_dictionary(USER_DICT)
    # Fallback : fichier système
    for candidate in SYSTEM_DICT_CANDIDATES:
        if os.path.isfile(candidate):
            return _parse_dictionary(candidate)
    return []


# Import optionnel jellyfish pour matching phonétique
try:
    import jellyfish
    _HAS_JELLYFISH = True
except ImportError:
    _HAS_JELLYFISH = False

_FUZZY_THRESHOLD = 0.85


def apply_dictionary(text, entries, fuzzy=True):
    """Applique le dictionnaire avec préservation de casse + fallback phonétique."""
    # Phase 1 : remplacement exact par regex (rapide)
    matched_spans = set()
    for word, word_re, replacement in entries:
        def _replace(m, repl=replacement):
            matched_spans.add((m.start(), m.end()))
            orig = m.group(0)
            if orig.isupper():
                return repl.upper()
            if orig[0].isupper():
                return repl[0].upper() + repl[1:]
            return repl
        text = word_re.sub(_replace, text)

    # Phase 2 : matching phonétique jellyfish (si activé)
    if not fuzzy or not _HAS_JELLYFISH or not entries:
        return text

    words_in_text = re.findall(r'\b[a-zA-ZÀ-ÿ]{2,}\b', text)
    if not words_in_text:
        return text

    # Construire un index des clés du dictionnaire
    dict_keys = [(w.lower(), replacement) for w, _, replacement in entries]

    for text_word in set(words_in_text):
        text_word_lower = text_word.lower()
        best_score = 0.0
        best_replacement = None
        for dict_word, replacement in dict_keys:
            if dict_word == text_word_lower:
                break  # déjà matché en phase 1
            score = jellyfish.jaro_winkler_similarity(text_word_lower, dict_word)
            if score > best_score and score >= _FUZZY_THRESHOLD:
                best_score = score
                best_replacement = replacement
        else:
            # Pas de break → pas de match exact → appliquer fuzzy
            if best_replacement:
                pat = re.compile(r'\b' + re.escape(text_word) + r'\b')
                def _fuzzy_replace(m, repl=best_replacement):
                    orig = m.group(0)
                    if orig.isupper():
                        return repl.upper()
                    if orig[0].isupper():
                        return repl[0].upper() + repl[1:]
                    return repl
                text = pat.sub(_fuzzy_replace, text)

    return text


# ── Capitalisation ───────────────────────────────────────────────────

_CAP_AFTER_PUNCT = re.compile(r'([.!?\u2026])(\s+)([a-zà-ÿ])')
_CAP_AFTER_NEWLINE = re.compile(r'(\n\s*)([a-zà-ÿ])')


def fix_capitalization(text):
    """Capitalise après ponctuation de fin et en début de texte."""
    if not text:
        return text
    # Début du texte
    if text[0].islower():
        text = text[0].upper() + text[1:]
    # Après . ! ? … — préserver les sauts de ligne
    text = _CAP_AFTER_PUNCT.sub(
        lambda m: m.group(1) + m.group(2) + m.group(3).upper(), text)
    # Après saut de ligne
    text = _CAP_AFTER_NEWLINE.sub(
        lambda m: m.group(1) + m.group(2).upper(), text)
    return text


# ── Correction LLM (ollama) ─────────────────────────────────────────

DEFAULT_PROMPT = (
    "<role>\n"
    "Ton rôle est de corriger une transcription provenant d'un ASR. "
    "Tu n'es pas un assistant conversationnel.\n"
    "</role>\n"
    "<instructions>\n"
    "- Corrige l'orthographe et la grammaire.\n"
    "- Supprime les répétitions et hésitations.\n"
    "- Ne modifie jamais le sens ni le contenu.\n"
    "- Ne réponds pas aux questions et ne les commente pas.\n"
    "- Ne génère aucun commentaire ni introduction.\n"
    "- Si tu ne sais pas ou qu'il n'y a rien à modifier, "
    "renvoie la transcription telle quelle.\n"
    "</instructions>\n"
    "<input>{text}</input>"
)

PROMPT_PATH = os.path.join(XDG_CONFIG, "dictee", "llm-prompt.txt")


def _load_prompt():
    if os.path.isfile(PROMPT_PATH):
        with open(PROMPT_PATH, encoding="utf-8") as f:
            return f.read().strip()
    return DEFAULT_PROMPT


def llm_postprocess(text):
    """Envoie le texte à ollama pour correction grammaticale."""
    model = os.environ.get("DICTEE_LLM_MODEL", "gemma3:4b")
    timeout = int(os.environ.get("DICTEE_LLM_TIMEOUT", "10"))

    prompt_tpl = _load_prompt()
    prompt = prompt_tpl.format(text=text)

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
    # Supprimer le \n ajouté par echo (mais garder les \n intentionnels)
    if text.endswith('\n'):
        text = text[:-1]
    if not text.strip():
        sys.stdout.write(text)
        return

    # 0. Détection de mauvaise langue (ASR multilingue confus sur audio court)
    # Les règles tentent d'abord de récupérer les commandes vocales connues
    # (ex: cyrillique "А линия" → \n pour "à la ligne").
    # Si après les règles le texte est toujours dans le mauvais script, on le rejette.

    # 1-5. Règles regex (annotations, hésitations, commandes vocales,
    #       dédup, ponctuation, élisions basiques, nettoyage)
    rules = load_rules()
    if rules:
        text = apply_rules(text, rules)
    # Nettoyer les espaces en début (hésitations/annotations supprimées)
    # mais préserver les \n de fin (commandes vocales "à la ligne")
    text = text.lstrip(' \t').rstrip(' \t')

    # 5b. Rejet mauvaise langue (après les règles, qui ont pu convertir les commandes connues)
    if LANG:
        _LATIN_LANGS = {"fr", "en", "de", "es", "it", "pt", "nl", "pl", "ro", "cs", "sv", "da", "no", "fi", "hu", "tr"}
        _CYRILLIC_LANGS = {"ru", "uk", "bg", "sr", "mk", "be"}
        letters = [c for c in text if c.isalpha()]
        if letters:
            cyrillic = sum(1 for c in letters if '\u0400' <= c <= '\u04ff')
            ratio = cyrillic / len(letters)
            if LANG in _LATIN_LANGS and ratio > 0.5:
                sys.stdout.write("")
                return
            if LANG in _CYRILLIC_LANGS and ratio < 0.2:
                sys.stdout.write("")
                return

    # 5c. Continuation (suppression points erronés après mots de classe fermée)
    continuation_words = load_continuation()
    if continuation_words:
        text = fix_continuation(text, continuation_words)

    # 6. Élisions françaises avancées (avec h aspirés)
    if LANG == "fr" and _env_bool("DICTEE_PP_ELISIONS"):
        text = fix_elisions(text)

    # 7. Conversion nombres → chiffres
    if _env_bool("DICTEE_PP_NUMBERS"):
        text = convert_numbers(text)

    # 8. Typographie française (espaces insécables)
    if LANG == "fr" and _env_bool("DICTEE_PP_TYPOGRAPHY"):
        text = fix_french_typography(text)

    # 9. (nettoyage final déjà dans les règles regex étape 5)

    # 10. Dictionnaire (système + personnel, avec matching phonétique)
    dictionary = load_dictionary()
    if dictionary:
        text = apply_dictionary(
            text, dictionary,
            fuzzy=_env_bool("DICTEE_PP_FUZZY_DICT"),
        )

    # 11. Capitalisation
    if _env_bool("DICTEE_PP_CAPITALIZATION"):
        text = fix_capitalization(text)

    # 12. Correction LLM (optionnelle)
    if _env_bool("DICTEE_LLM_POSTPROCESS", "false"):
        text = llm_postprocess(text)

    sys.stdout.write(text)


if __name__ == "__main__":
    main()
