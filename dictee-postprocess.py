#!/usr/bin/env python3
"""dictee-postprocess — post-processing filter for voice dictation.

Reads transcribed text from stdin, applies sequentially:
  1.  Regex rules (annotations, hesitations, voice commands, dedup, punctuation)
  2.  Language-specific rules (elisions, contractions, typography)
  3.  Number conversion (text2num, optional)
  4.  Dictionary (system + personal, exact match on word boundaries)
  5.  Capitalization
  6.  Optional LLM correction (ollama)

Writes result to stdout.

Environment variables:
  DICTEE_LANG_SOURCE       — source language (fr, en, de, ...) for rule filtering
  DICTEE_PP_ELISIONS       — true/false (default: true)  — French elisions (aspirated h)
  DICTEE_PP_ELISIONS_IT    — true/false (default: true)  — Italian elisions + contractions
  DICTEE_PP_SPANISH        — true/false (default: true)  — Spanish contractions al/del + ¿¡
  DICTEE_PP_PORTUGUESE     — true/false (default: true)  — Portuguese contractions (do, na, pelo...)
  DICTEE_PP_GERMAN         — true/false (default: true)  — German contractions (am, im...) + „"
  DICTEE_PP_DUTCH          — true/false (default: true)  — Dutch contractions ('t, 'n, 's)
  DICTEE_PP_ROMANIAN       — true/false (default: true)  — Romanian contractions (n-am, într-o) + „"
  DICTEE_PP_NUMBERS        — true/false (default: true)  — number→digit conversion
  DICTEE_PP_TYPOGRAPHY     — true/false (default: true)  — French typography
  DICTEE_PP_CAPITALIZATION — true/false (default: true)  — auto-capitalization
  DICTEE_PP_RULES          — true/false (default: true)  — regex rules
  DICTEE_PP_DICT           — true/false (default: true)  — dictionary

  DICTEE_PP_CONTINUATION   — true/false (default: true)  — continuation
  DICTEE_PP_SHORT_TEXT     — true/false (default: true)  — short text correction (< 3 words)
  DICTEE_LLM_POSTPROCESS   — true/false (default: false) — LLM correction
  DICTEE_LLM_MODEL         — ollama model (default: gemma3:4b)
  DICTEE_LLM_TIMEOUT       — timeout in seconds (default: 10)
  DICTEE_LLM_SYSTEM_PROMPT — preset name or "custom" (default: Correction FR)
  DICTEE_LLM_POSITION      — hybrid/first/last (default: hybrid)
"""

import json as _json
import os
import re
import socket
import sys
import urllib.request
import urllib.error

# ── text_to_num bootstrap ─────────────────────────────────────────────
# Priority order for finding text_to_num (used by convert_numbers):
#   1. User venv ~/.local/share/dictee/postprocess-env (if user created it)
#   2. System vendor dir /usr/lib/dictee/vendor (bundled in .deb/.rpm)
# sys.path injection — re-exec via os.execv would lose stdin (pipe).

XDG_DATA = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
_VENV_DIR = os.path.join(XDG_DATA, "dictee", "postprocess-env")
_VENV_SITE = os.path.join(
    _VENV_DIR, "lib",
    f"python{sys.version_info.major}.{sys.version_info.minor}",
    "site-packages",
)
if os.path.isdir(_VENV_SITE) and _VENV_SITE not in sys.path:
    sys.path.insert(0, _VENV_SITE)

# System-wide vendor directory (text2num bundled in the package)
_VENDOR_DIR = "/usr/lib/dictee/vendor"
if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    sys.path.append(_VENDOR_DIR)

# ── Chemins ──────────────────────────────────────────────────────────

XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))

USER_RULES = os.path.join(XDG_CONFIG, "dictee", "rules.conf")
USER_DICT = os.path.join(XDG_CONFIG, "dictee", "dictionary.conf")

_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

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

SYSTEM_KEEPCAPS_CANDIDATES = [
    os.path.join(_SCRIPT_DIR, "short_text_keepcaps.conf.default"),
    "/usr/share/dictee/short_text_keepcaps.conf.default",
    os.path.join(XDG_DATA, "dictee", "short_text_keepcaps.conf.default"),
]

USER_KEEPCAPS = os.path.join(XDG_CONFIG, "dictee", "short_text_keepcaps.conf")

LANG = os.environ.get("DICTEE_LANG_SOURCE", "").lower()[:2]

# Command suffix per language (disambiguates "point" from the word "point")
# e.g. DICTEE_COMMAND_SUFFIX_FR=finale?s? → "point final" → "."
_COMMAND_SUFFIXES = {}
for _code in ("fr", "en", "de", "es", "it", "pt", "uk"):
    _val = os.environ.get(f"DICTEE_COMMAND_SUFFIX_{_code.upper()}", "").strip()
    if _val:
        _COMMAND_SUFFIXES[_code] = _val


def _env_bool(var, default="true"):
    """Reads a boolean environment variable."""
    return os.environ.get(var, default).lower() == "true"


# ── Loading regex rules ──────────────────────────────────────

_RULE_RE = re.compile(
    r"^\s*\[([a-z]{2}|\*)\]\s*/(.+)/(.+)/([igm]*)\s*$"
)

# Rules with empty replacement : /PATTERN//FLAGS
_RULE_EMPTY_RE = re.compile(
    r"^\s*\[([a-z]{2}|\*)\]\s*/(.+)//([igm]*)\s*$"
)


def _parse_rules(path):
    """Parses a rules file, returns [(pattern_compiled, replacement)]."""
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
            # Replace %SUFFIX_XX% placeholders
            suffix_var = re.search(r'%SUFFIX_([A-Z]{2})%', pattern)
            if suffix_var:
                code = suffix_var.group(1).lower()
                suffix = _COMMAND_SUFFIXES.get(code, "")
                if not suffix:
                    # No suffix configured → skip this rule (command disabled)
                    continue
                pattern = pattern.replace(suffix_var.group(0), suffix)
            flags = 0
            if "i" in flags_str:
                flags |= re.IGNORECASE
            if "m" in flags_str:
                flags |= re.MULTILINE
            # \s in [,.\s] classes must not consume \n produced by other rules
            # Replace \s with \t  (space + tab) in character classes
            pattern = re.sub(r'\[([^\]]*?)\\s([^\]]*?)\]',
                             lambda m: '[' + m.group(1) + r' \t' + m.group(2) + ']',
                             pattern)
            try:
                compiled = re.compile(pattern, flags)
            except re.error:
                continue
            # Convert escape sequences in replacement
            replacement = (replacement
                           .replace("\\n", "\n")
                           .replace("\\t", "\t")
                           .replace("\\u00a0", "\u00a0")
                           .replace("\\u202f", "\u202f")
                           .replace("\\u2026", "\u2026")
                           .replace("\\u2014", "\u2014")
                           .replace("\\u00ab", "\u00ab")
                           .replace("\\u00bb", "\u00bb")
                           .replace("\\u002f", "/")
                           .replace("\\x01", "\x01")
                           .replace("\\x02", "\x02"))
            rules.append((compiled, replacement))
    return rules


def load_rules():
    """Loads user rules (or system defaults)."""
    if os.path.isfile(USER_RULES):
        return _parse_rules(USER_RULES)
    # Fallback: system file
    for candidate in SYSTEM_RULES_CANDIDATES:
        if os.path.isfile(candidate):
            return _parse_rules(candidate)
    return []


def apply_rules(text, rules):
    """Applies regex rules sequentially."""
    for pattern, replacement in rules:
        text = pattern.sub(replacement, text)
    return text


# ── Continuation (remove erroneous periods after closed-class words) ──

_CONT_LINE_RE = re.compile(r"^\s*\[([a-z]{2}|\*)\]\s*(.+)$")
_CONT_EXCLUDE_RE = re.compile(r"^\s*\[exclude:([a-z]{2}|\*)\]\s*(.+)$")

def _parse_continuation(path):
    """Returns (added_words, excluded_words) sets for the current LANG."""
    added = set()
    excluded = set()
    if not os.path.isfile(path):
        return added, excluded
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # [exclude:xx] must be checked BEFORE [xx] because the generic
            # regex also matches the bracket content.
            m = _CONT_EXCLUDE_RE.match(line)
            if m:
                lang_tag, word_list = m.groups()
                if lang_tag != "*" and LANG and lang_tag != LANG:
                    continue
                for w in word_list.split():
                    excluded.add(w.lower())
                continue
            m = _CONT_LINE_RE.match(line)
            if not m:
                continue
            lang_tag, word_list = m.groups()
            # Skip the [keyword:xx] lines handled elsewhere
            if lang_tag != "*" and LANG and lang_tag != LANG:
                continue
            for w in word_list.split():
                added.add(w.lower())
    return added, excluded

def load_continuation():
    """Loads system continuation words, merged with user additions/exclusions."""
    words = set()
    # Load system defaults first
    for candidate in SYSTEM_CONT_CANDIDATES:
        if os.path.isfile(candidate):
            sys_added, _ = _parse_continuation(candidate)
            words = sys_added
            break
    # Merge user file: add extras, then remove excluded words
    if os.path.isfile(USER_CONT):
        user_added, user_excluded = _parse_continuation(USER_CONT)
        words |= user_added
        words -= user_excluded
    return words

def fix_continuation(text, continuation_words):
    """Removes erroneous periods/ellipsis after a continuation word.
    The following character is lowercased; proper nouns are re-cased
    by the dictionary step later in the pipeline."""
    if not continuation_words:
        return text

    def _fix(m):
        word = m.group(1)
        after_char = m.group(2)
        if word.lower() not in continuation_words:
            return m.group(0)
        return word + " " + after_char.lower()

    return re.sub(r"(\w+)(?:\.{1,3}|…)[ \t]+([A-Za-zÀ-ÿ])", _fix, text)


# ── Short text correction ────────────────────────────────────────

try:
    _SHORT_TEXT_MAX_WORDS = max(1, int(os.environ.get("DICTEE_PP_SHORT_TEXT_MAX", "3")))
except ValueError:
    _SHORT_TEXT_MAX_WORDS = 3


_KEEPCAPS_LINE_RE = re.compile(r"^\s*\[([a-z]{2}|\*)\]\s*(.+)$")
_KEEPCAPS_EXCLUDE_RE = re.compile(r"^\s*\[exclude:([a-z]{2}|\*)\]\s*(.+)$")


def _normalize_keepcaps(s):
    """Lowercase + strip combining accents (NFD).

    Parakeet/Whisper sometimes emit "a demain" instead of "à demain"; the
    keepcaps match must be accent-insensitive so both forms trigger the
    exception."""
    import unicodedata
    nfd = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _parse_keepcaps(path):
    """Returns (added, excluded) sets of accent-normalized expressions for LANG."""
    added = set()
    excluded = set()
    if not os.path.isfile(path):
        return added, excluded
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _KEEPCAPS_EXCLUDE_RE.match(line)
            if m:
                lang_tag, expr_list = m.groups()
                if lang_tag != "*" and LANG and lang_tag != LANG:
                    continue
                for expr in expr_list.split(","):
                    expr = _normalize_keepcaps(expr.strip())
                    if expr:
                        excluded.add(expr)
                continue
            m = _KEEPCAPS_LINE_RE.match(line)
            if not m:
                continue
            lang_tag, expr_list = m.groups()
            if lang_tag != "*" and LANG and lang_tag != LANG:
                continue
            for expr in expr_list.split(","):
                expr = _normalize_keepcaps(expr.strip())
                if expr:
                    added.add(expr)
    return added, excluded


def load_keepcaps():
    """Loads system short-text exceptions, merged with user additions/exclusions."""
    exprs = set()
    for candidate in SYSTEM_KEEPCAPS_CANDIDATES:
        if os.path.isfile(candidate):
            sys_added, _ = _parse_keepcaps(candidate)
            exprs = sys_added
            break
    if os.path.isfile(USER_KEEPCAPS):
        user_added, user_excluded = _parse_keepcaps(USER_KEEPCAPS)
        exprs |= user_added
        exprs -= user_excluded
    return exprs


def fix_short_text(text, keepcaps=None, extended=False):
    """For transcriptions with fewer than 3 words, remove trailing
    punctuation and lowercase Capitalized words.  Preserves acronyms
    (ALL CAPS) and mixed-case words (iPhone).  Skips voice commands
    (pure punctuation, whitespace, or newlines).

    Keepcaps list: when a short text matches (full or first-word), the
    canonical form is emitted with a leading \\x03 marker — dictee bash
    uses it to skip lowercasing in apply_continuation mode "_".

    Extended mode (opt-in, via DICTEE_PP_KEEPCAPS_EXTENDED):
      - Full-list expressions match regardless of length (so
        "to whom it may concern" or "je vous prie de croire" trigger
        the keepcaps treatment even with 4+ words).
      - First-word match on a long text emits the \\x03 signal only
        (text unchanged) so apply_continuation can preserve case
        after a comma or a period+continuation word."""
    stripped = text.strip()
    # Skip voice commands: pure punctuation/whitespace/newlines
    if not stripped or not any(c.isalnum() for c in stripped):
        return text
    # Text with newlines (voice command "à la ligne") is never "short text"
    if '\n' in text:
        return text

    words = stripped.split()
    is_short = len(words) < _SHORT_TEXT_MAX_WORDS

    # Exception list handling (emits \x03 signal for downstream bash).
    # Rules for the tail:
    #   - \x02 marker (internal "point final") is ALWAYS dropped.
    #   - "." is dropped UNLESS \x02 was present (ASR often auto-inserts
    #     a period; we only keep it when the user explicitly said
    #     "point final"); in that case the "." is restored without \x02.
    #   - "," ";" ":" "!" "?" are always kept — they only appear via
    #     explicit voice commands ("virgule", "point d'exclamation"…).
    #   - Surrounding NNBSP/NBSP (from FR typography) preserved with them.
    # Accent-insensitive match (ASR sometimes drops accents).
    if keepcaps:
        _has_x02 = "\x02" in stripped
        # Strip ALL \x02 markers (defensive: the rules always place them at
        # the tail after ".", but don't depend on that position).
        _base = stripped.replace("\x02", "")
        _tail_m = re.search(r"[\s\u00a0\u202f]*[,.!?;:]$", _base)
        if _tail_m:
            _tail = _base[_tail_m.start():]
            _core = _base[:_tail_m.start()].rstrip()
        else:
            _tail = ""
            _core = _base.rstrip()

        def _build_out():
            out = _core[0].upper() + _core[1:] if _core[0].islower() else _core
            if _tail:
                _last = _tail[-1]
                if _last == "." and not _has_x02:
                    pass  # ASR auto-period → drop
                else:
                    out_with_tail = out + _tail
                    return out_with_tail
            return out

        # Full-text match: "bonjour", "bonne nuit", "au revoir",
        # "to whom it may concern", "je vous prie de croire"…
        # Short text: always triggers. Long text: only with extended mode.
        if _core and _normalize_keepcaps(_core) in keepcaps:
            if is_short or extended:
                return "\x03" + _build_out()

        # First-word match: "cher ami", "bonjour, monsieur"…
        _parts = _core.split(maxsplit=1) if _core else []
        if _parts:
            _first = _parts[0].rstrip(",.!?;:")
            if _first and _normalize_keepcaps(_first) in keepcaps:
                if is_short:
                    # Full keepcaps treatment — force upper, strip/keep tail
                    return "\x03" + _build_out()
                elif extended:
                    # Long text: emit the signal only. Text is untouched so
                    # fix_capitalization's work (if any) is preserved.
                    return "\x03" + text

    # Normal short-text handling (no match, or disabled)
    if not is_short:
        return text
    # Remove trailing punctuation
    if text and text[-1] in ".!?,":
        text = text[:-1]
    # Lowercase Capitalized words (first upper + second lower)
    parts = text.split()
    for i, w in enumerate(parts):
        if w[0].isupper() and (len(w) == 1 or w[1].islower()):
            parts[i] = w[0].lower() + w[1:]
    return " ".join(parts)


# ── Advanced French elisions ─────────────────────────────────────

# Words starting with aspirated h (NO elision)
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
# Mute h followed by vowel (but NOT aspirated h)
_H_MUET_VOWEL = f'[hH]{_VOWEL_PATTERN}'

# Pre-compile elision patterns
_H_ASPIRE_SORTED = sorted(H_ASPIRE, key=len, reverse=True)
_H_ASPIRE_RE = '|'.join(re.escape(h) for h in _H_ASPIRE_SORTED)
_ELISION_PATTERNS = []
for _word, _elided in ELISION_WORDS.items():
    # Matches: word + space + (vowel OR mute h), except aspirated h
    _pat = re.compile(
        rf'\b{re.escape(_word)}\s+(?!(?:{_H_ASPIRE_RE})\b)({_VOWEL_PATTERN}\w*|{_H_MUET_VOWEL}\w*)',
        re.IGNORECASE
    )
    _ELISION_PATTERNS.append((_pat, _elided))

_SI_IL_RE = re.compile(r'\bsi\s+(ils?)\b', re.IGNORECASE)


def fix_elisions(text):
    """Fixes missing elisions (je ai → j'ai) with aspirated h handling."""
    for pattern, elided in _ELISION_PATTERNS:
        def _elide(m, e=elided):
            rest = m.group(1)
            # Preserve case : if original word started with uppercase
            # and elision is at sentence start, keep uppercase on elision
            return e + rest.lower() if rest[0].isupper() and len(rest) > 1 and rest[1:] == rest[1:].lower() else e + rest
        text = pattern.sub(_elide, text)
    text = _SI_IL_RE.sub(r"s'\1", text)
    return text


# ── Italian elisions ──────────────────────────────────────────────

IT_ELISION_WORDS = {
    'lo': "l'", 'la': "l'",
    'una': "un'",
    'di': "d'", 'ci': "c'",
}

IT_ELISION_EXTENDED = {
    'quello': "quell'", 'quella': "quell'",
    'questo': "quest'", 'questa': "quest'",
    'bello': "bell'", 'bella': "bell'",
    'come': "com'", 'dove': "dov'",
}

_IT_VOWELS = 'aeiouyàèéìòóùAEIOUYÀÈÉÌÒÓÙ'
_IT_VOWEL_PAT = f'[{_IT_VOWELS}]'
_IT_ELISION_PATTERNS = []
for _w, _e in {**IT_ELISION_WORDS, **IT_ELISION_EXTENDED}.items():
    _pat = re.compile(
        rf'\b{re.escape(_w)}\s+({_IT_VOWEL_PAT}\w*|[hH]{_IT_VOWEL_PAT}\w*)',
        re.IGNORECASE)
    _IT_ELISION_PATTERNS.append((_pat, _e))

# Prepositional contractions : di + il → del, a + lo → allo, etc.
_IT_PREP_CONTRACTIONS = [
    (re.compile(r'\bdi\s+il\b', re.I), 'del'),
    (re.compile(r'\bdi\s+lo\b', re.I), 'dello'),
    (re.compile(r'\bdi\s+la\b', re.I), 'della'),
    (re.compile(r'\bdi\s+i\b', re.I), 'dei'),
    (re.compile(r'\bdi\s+gli\b', re.I), 'degli'),
    (re.compile(r'\bdi\s+le\b', re.I), 'delle'),
    (re.compile(r'\ba\s+il\b', re.I), 'al'),
    (re.compile(r'\ba\s+lo\b', re.I), 'allo'),
    (re.compile(r'\ba\s+la\b', re.I), 'alla'),
    (re.compile(r'\ba\s+i\b', re.I), 'ai'),
    (re.compile(r'\ba\s+gli\b', re.I), 'agli'),
    (re.compile(r'\ba\s+le\b', re.I), 'alle'),
    (re.compile(r'\bda\s+il\b', re.I), 'dal'),
    (re.compile(r'\bda\s+lo\b', re.I), 'dallo'),
    (re.compile(r'\bda\s+la\b', re.I), 'dalla'),
    (re.compile(r'\bda\s+i\b', re.I), 'dai'),
    (re.compile(r'\bda\s+gli\b', re.I), 'dagli'),
    (re.compile(r'\bda\s+le\b', re.I), 'dalle'),
    (re.compile(r'\bin\s+il\b', re.I), 'nel'),
    (re.compile(r'\bin\s+lo\b', re.I), 'nello'),
    (re.compile(r'\bin\s+la\b', re.I), 'nella'),
    (re.compile(r'\bin\s+i\b', re.I), 'nei'),
    (re.compile(r'\bin\s+gli\b', re.I), 'negli'),
    (re.compile(r'\bin\s+le\b', re.I), 'nelle'),
    (re.compile(r'\bsu\s+il\b', re.I), 'sul'),
    (re.compile(r'\bsu\s+lo\b', re.I), 'sullo'),
    (re.compile(r'\bsu\s+la\b', re.I), 'sulla'),
    (re.compile(r'\bsu\s+i\b', re.I), 'sui'),
    (re.compile(r'\bsu\s+gli\b', re.I), 'sugli'),
    (re.compile(r'\bsu\s+le\b', re.I), 'sulle'),
]


def _case_aware_replace(match, replacement):
    """Replaces while preserving the case of the original text."""
    original = match.group(0)
    if original.isupper():
        return replacement.upper()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def fix_italian_elisions(text):
    """Fixes Italian contractions and elisions."""
    # Contractions first (di il → del) before elisions (di → d')
    for pattern, contraction in _IT_PREP_CONTRACTIONS:
        text = pattern.sub(lambda m: _case_aware_replace(m, contraction), text)
    for pattern, elided in _IT_ELISION_PATTERNS:
        def _elide(m, e=elided):
            rest = m.group(1)
            if m.group(0)[0].isupper():
                return e[0].upper() + e[1:] + rest
            return e + rest
        text = pattern.sub(_elide, text)
    return text


# ── Spanish contractions + inverted punctuation ───────────────────

_ES_AL = re.compile(r'\b[Aa]\s+[Ee]l\b(?!\s+[A-ZÁ-Ú])')
_ES_DEL = re.compile(r'\b[Dd]e\s+[Ee]l\b(?!\s+[A-ZÁ-Ú])')
# Inverted punctuation: add ¿ / ¡ at sentence start
_ES_QUESTION = re.compile(r'(?:^|(?<=[.!?\n]\s))([^?]*\?)')
_ES_EXCLAIM = re.compile(r'(?:^|(?<=[.!?\n]\s))([^!]*!)')
# Question words (help locate the start of the question)
_ES_QW = re.compile(
    r'(?:^|(?<=[\s,;]))((?:qué|quién|quiénes|cómo|cuándo|dónde|'
    r'por qué|cuál|cuáles|cuánto|cuánta|cuántos|cuántas)\b[^?]*\?)',
    re.IGNORECASE)


def fix_spanish(text):
    """Contractions al/del and inverted punctuation ¿¡."""
    # Contractions (sauf noms propres : "de El Salvador")
    text = _ES_AL.sub('al', text)
    text = _ES_DEL.sub('del', text)
    # Inverted punctuation — question words first
    def _add_inv_q(m):
        s = m.group(1)
        if s.startswith('¿'):
            return s
        return '¿' + s
    text = _ES_QW.sub(_add_inv_q, text)
    # Exclamations
    def _add_inv_e(m):
        s = m.group(1)
        if s.startswith('¡'):
            return s
        return '¡' + s.lstrip()
    text = _ES_EXCLAIM.sub(_add_inv_e, text)
    return text


# ── Portuguese contractions ─────────────────────────────────────────

_PT_CONTRACTIONS = [
    # de + articles
    (re.compile(r'\bde\s+o\b', re.I), 'do'),
    (re.compile(r'\bde\s+a\b', re.I), 'da'),
    (re.compile(r'\bde\s+os\b', re.I), 'dos'),
    (re.compile(r'\bde\s+as\b', re.I), 'das'),
    # em + articles
    (re.compile(r'\bem\s+o\b', re.I), 'no'),
    (re.compile(r'\bem\s+a\b', re.I), 'na'),
    (re.compile(r'\bem\s+os\b', re.I), 'nos'),
    (re.compile(r'\bem\s+as\b', re.I), 'nas'),
    (re.compile(r'\bem\s+um\b', re.I), 'num'),
    (re.compile(r'\bem\s+uma\b', re.I), 'numa'),
    # por + articles
    (re.compile(r'\bpor\s+o\b', re.I), 'pelo'),
    (re.compile(r'\bpor\s+a\b', re.I), 'pela'),
    (re.compile(r'\bpor\s+os\b', re.I), 'pelos'),
    (re.compile(r'\bpor\s+as\b', re.I), 'pelas'),
    # de + demonstrativos
    (re.compile(r'\bde\s+este\b', re.I), 'deste'),
    (re.compile(r'\bde\s+esta\b', re.I), 'desta'),
    (re.compile(r'\bde\s+esse\b', re.I), 'desse'),
    (re.compile(r'\bde\s+essa\b', re.I), 'dessa'),
    (re.compile(r'\bde\s+aquele\b', re.I), 'daquele'),
    (re.compile(r'\bde\s+aquela\b', re.I), 'daquela'),
    (re.compile(r'\bde\s+isto\b', re.I), 'disto'),
    (re.compile(r'\bde\s+isso\b', re.I), 'disso'),
    (re.compile(r'\bde\s+aquilo\b', re.I), 'daquilo'),
    # em + demonstrativos
    (re.compile(r'\bem\s+este\b', re.I), 'neste'),
    (re.compile(r'\bem\s+esta\b', re.I), 'nesta'),
    (re.compile(r'\bem\s+esse\b', re.I), 'nesse'),
    (re.compile(r'\bem\s+essa\b', re.I), 'nessa'),
    (re.compile(r'\bem\s+aquele\b', re.I), 'naquele'),
    (re.compile(r'\bem\s+aquela\b', re.I), 'naquela'),
    # de/em + pronoms
    (re.compile(r'\bde\s+ele\b', re.I), 'dele'),
    (re.compile(r'\bde\s+ela\b', re.I), 'dela'),
    (re.compile(r'\bde\s+eles\b', re.I), 'deles'),
    (re.compile(r'\bde\s+elas\b', re.I), 'delas'),
    (re.compile(r'\bem\s+ele\b', re.I), 'nele'),
    (re.compile(r'\bem\s+ela\b', re.I), 'nela'),
    (re.compile(r'\bem\s+eles\b', re.I), 'neles'),
    (re.compile(r'\bem\s+elas\b', re.I), 'nelas'),
]


def fix_portuguese(text):
    """Fixes Portuguese contractions (de o → do, em a → na, etc.)."""
    for pattern, contraction in _PT_CONTRACTIONS:
        text = pattern.sub(lambda m: _case_aware_replace(m, contraction), text)
    return text


# ── German contractions ──────────────────────────────────────────

_DE_CONTRACTIONS = [
    (re.compile(r'\ban\s+dem\b', re.I), 'am'),
    (re.compile(r'\ban\s+das\b', re.I), 'ans'),
    (re.compile(r'\bauf\s+das\b', re.I), 'aufs'),
    (re.compile(r'\bbei\s+dem\b', re.I), 'beim'),
    (re.compile(r'\bin\s+dem\b', re.I), 'im'),
    (re.compile(r'\bin\s+das\b', re.I), 'ins'),
    (re.compile(r'\bvon\s+dem\b', re.I), 'vom'),
    (re.compile(r'\bzu\s+dem\b', re.I), 'zum'),
    (re.compile(r'\bzu\s+der\b', re.I), 'zur'),
]

_DE_TYPO_QUOTES = re.compile(r'"([^"]*)"')


def fix_german(text):
    """German contractions (an dem → am, etc.) et quotes „..."."""
    for pattern, contraction in _DE_CONTRACTIONS:
        text = pattern.sub(lambda m: _case_aware_replace(m, contraction), text)
    # English quotes → German
    text = _DE_TYPO_QUOTES.sub('\u201e\\1\u201c', text)
    return text


# ── Dutch contractions ────────────────────────────────────────

# Expressions fixes avec apostrophe
_NL_CONTRACTIONS = [
    # het → 't
    (re.compile(r'\b[Hh]et\b'), "'t"),
    # een → 'n (seulement devant minuscule — pas devant nom propre)
    (re.compile(r'\b[Ee]en\b(?=\s+[a-zà-ÿ])'), "'n"),
]
# Fixed time expressions
_NL_TIME_EXPRS = [
    (re.compile(r"\bin de morgens?\b", re.I), "'s morgens"),
    (re.compile(r"\bin de avonds?\b", re.I), "'s avonds"),
    (re.compile(r"\bin de nachts?\b", re.I), "'s nachts"),
    (re.compile(r"\bin de middags?\b", re.I), "'s middags"),
]


def fix_dutch(text):
    """Dutch contractions ('t, 'n, 's morgens, etc.)."""
    for pattern, replacement in _NL_TIME_EXPRS:
        text = pattern.sub(replacement, text)
    for pattern, replacement in _NL_CONTRACTIONS:
        text = pattern.sub(replacement, text)
    return text


# ── Romanian contractions ───────────────────────────────────────────

_RO_CONTRACTIONS = [
    # Negation contractions
    (re.compile(r'\bnu\s+am\b', re.I), "n-am"),
    (re.compile(r'\bnu\s+ai\b', re.I), "n-ai"),
    (re.compile(r'\bnu\s+a\b', re.I), "n-a"),
    (re.compile(r'\bnu\s+au\b', re.I), "n-au"),
    (re.compile(r'\bnu\s+o\b', re.I), "n-o"),
    # Prepositional contractions
    (re.compile(r'\bîntr\s+o\b', re.I), "într-o"),
    (re.compile(r'\bîntr\s+un\b', re.I), "într-un"),
    (re.compile(r'\bdintr\s+o\b', re.I), "dintr-o"),
    (re.compile(r'\bdintr\s+un\b', re.I), "dintr-un"),
    (re.compile(r'\bprintr\s+o\b', re.I), "printr-o"),
    (re.compile(r'\bprintr\s+un\b', re.I), "printr-un"),
]

_RO_TYPO_QUOTES = re.compile(r'"([^"]*)"')


def fix_romanian(text):
    """Romanian contractions (n-am, într-o, etc.) and quotes „..."."""
    for pattern, contraction in _RO_CONTRACTIONS:
        text = pattern.sub(lambda m: _case_aware_replace(m, contraction), text)
    # English quotes → Romanian (same style as German)
    text = _RO_TYPO_QUOTES.sub('\u201e\\1\u201c', text)
    return text


# ── Conversion nombres (text2num) ────────────────────────────────────

try:
    from text_to_num import alpha2digit
    _HAS_TEXT2NUM = True
except ImportError:
    _HAS_TEXT2NUM = False

_TEXT2NUM_LANGS = frozenset({'fr', 'en', 'es', 'pt', 'de', 'it', 'nl'})


# Small number words per language — for version numbers like "1.3.0".
# text_to_num does NOT reliably convert "un"/"one"/"zéro" in isolation
# (ambiguity with indefinite article / silent zero).
_VERSION_WORDS = {
    "fr": {
        "zéro": "0", "zero": "0",
        "un": "1", "une": "1",
        "deux": "2", "trois": "3", "quatre": "4", "cinq": "5",
        "six": "6", "sept": "7", "huit": "8", "neuf": "9",
        "dix": "10",
    },
    "en": {
        "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
        "ten": "10",
    },
    "de": {
        "null": "0", "eins": "1", "ein": "1", "eine": "1", "zwei": "2",
        "drei": "3", "vier": "4", "fünf": "5", "sechs": "6",
        "sieben": "7", "acht": "8", "neun": "9", "zehn": "10",
    },
    "es": {
        "cero": "0", "uno": "1", "una": "1", "un": "1", "dos": "2",
        "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6",
        "siete": "7", "ocho": "8", "nueve": "9", "diez": "10",
    },
    "it": {
        "zero": "0", "uno": "1", "una": "1", "un": "1", "due": "2",
        "tre": "3", "quattro": "4", "cinque": "5", "sei": "6",
        "sette": "7", "otto": "8", "nove": "9", "dieci": "10",
    },
    "pt": {
        "zero": "0", "um": "1", "uma": "1", "dois": "2", "duas": "2",
        "três": "3", "quatro": "4", "cinco": "5", "seis": "6",
        "sete": "7", "oito": "8", "nove": "9", "dez": "10",
    },
}

# Word for "point" (the version separator) per language.
_VERSION_POINT_WORDS = {
    "fr": "point",
    "en": "point",  # "dot" covered by dedicated rule elsewhere
    "de": "punkt",
    "es": "punto",
    "it": "punto",
    "pt": "ponto",
}


def _convert_version_number(text):
    """Turn "X point Y point Z" → "X.Y.Z" when the tokens are small
    numbers (word or digit). Safe against prose: requires a number-like
    token on BOTH sides of each "point", so "un point de vue" is not
    rewritten."""
    words = _VERSION_WORDS.get(LANG)
    point_word = _VERSION_POINT_WORDS.get(LANG)
    if not words or not point_word:
        return text
    alts = "|".join(sorted(map(re.escape, words.keys()),
                           key=len, reverse=True))
    num_re = rf"(?:{alts}|\d+)"
    # At least one "point" separator between two number tokens; may repeat.
    pattern = re.compile(
        rf"\b({num_re})(?:\s+{re.escape(point_word)}\s+(?:{num_re}))+\b",
        re.IGNORECASE)

    def _replace(m):
        tokens = re.split(rf"\s+{re.escape(point_word)}\s+",
                          m.group(0), flags=re.IGNORECASE)
        digits = []
        for tok in tokens:
            low = tok.lower()
            if low in words:
                digits.append(words[low])
            elif tok.isdigit():
                digits.append(tok)
            else:
                return m.group(0)  # unexpected, keep verbatim
        return ".".join(digits)

    return pattern.sub(_replace, text)


# Decimal comma: "1, 5" → "1,5" when it looks like a decimal (no other
# ", digit" nearby meaning a list). Applies to FR/DE/ES/IT/PT (comma as
# decimal separator). EN uses "." so no effect.
_DECIMAL_COMMA_LANGS = frozenset({'fr', 'de', 'es', 'it', 'pt'})
# Match "X, Y" pair of numbers only when NOT part of a list:
#   - no "digit or comma" + space immediately BEFORE (lookbehind)
#   - no ", digit" immediately AFTER (lookahead)
# So "1, 5" → "1,5" is compacted but "1, 2, 3" keeps its spaces.
_DECIMAL_COMMA_RE = re.compile(
    r'(?<![0-9,]\s)(\d+),\s+(\d+)(?!\s*,\s*\d)')


def convert_numbers(text):
    """Convertit les nombres en toutes lettres en chiffres."""
    text = _convert_version_number(text)
    if _HAS_TEXT2NUM and LANG in _TEXT2NUM_LANGS:
        try:
            text = alpha2digit(text, LANG)
        except Exception:
            pass
    # Compact decimal commas: "1, 5" → "1,5". Keep lists "1, 2, 3" intact
    # via the negative lookahead (another ", digit" after the pair).
    if LANG in _DECIMAL_COMMA_LANGS:
        text = _DECIMAL_COMMA_RE.sub(r'\1,\2', text)
    return text


# ── French typography ────────────────────────────────────────────

_NBSP = '\u00a0'     # non-breaking space (before :, after «, before »)
_NNBSP = '\u202f'    # narrow non-breaking space (before ; ? !)

# Pre-compile typography patterns
_TYPO_BEFORE_THIN = re.compile(r'(?<=\S)\s*([;!?])') # narrow non-breaking space before ; ! ? (except at line start)
_TYPO_BEFORE_COLON = re.compile(r'(?<=\S)\s*(:)')   # non-breaking space before : (except at line start)
_TYPO_AFTER_LGUILL = re.compile(r'«\s*')           # space after «
_TYPO_BEFORE_RGUILL = re.compile(r'\s*»')          # espace avant »
_TYPO_ELLIPSIS = re.compile(r'\.{3,}')             # ... → …
_TYPO_EN_QUOTES = re.compile(r'"([^"]+)"')         # "x" → « x »


def fix_french_typography(text):
    """Applies French typographic rules."""
    # Points de suspension
    text = _TYPO_ELLIPSIS.sub('\u2026', text)
    # English quotes → French
    text = _TYPO_EN_QUOTES.sub(f'\u00ab{_NBSP}\\1{_NBSP}\u00bb', text)
    # Non-breaking spaces before high punctuation
    text = _TYPO_BEFORE_THIN.sub(f'{_NNBSP}\\1', text)
    text = _TYPO_BEFORE_COLON.sub(f'{_NBSP}\\1', text)
    # Espaces autour des quotes
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
    """Loads user dictionary (or system defaults)."""
    if os.path.isfile(USER_DICT):
        return _parse_dictionary(USER_DICT)
    # Fallback: system file
    for candidate in SYSTEM_DICT_CANDIDATES:
        if os.path.isfile(candidate):
            return _parse_dictionary(candidate)
    return []


def apply_dictionary(text, entries):
    """Applies dictionary with case preservation (exact match on word boundaries)."""
    for word, word_re, replacement in entries:
        def _replace(m, repl=replacement):
            orig = m.group(0)
            if orig.isupper():
                return repl.upper()
            if orig[0].isupper():
                return repl[0].upper() + repl[1:]
            return repl
        text = word_re.sub(_replace, text)
    return text


# ── Capitalisation ───────────────────────────────────────────────────

_CAP_AFTER_PUNCT = re.compile(r'([.!?\u2026])\x02?(\s+)([a-zà-ÿ])')
_CAP_AFTER_NEWLINE = re.compile(r'(\n\s*)([a-zà-ÿ])')


def fix_capitalization(text):
    """Capitalizes after sentence-ending punctuation and at text start."""
    if not text:
        return text
    # Start of text
    if text[0].islower():
        text = text[0].upper() + text[1:]
    # After . ! ? … — preserve line breaks
    text = _CAP_AFTER_PUNCT.sub(
        lambda m: m.group(1) + m.group(2) + m.group(3).upper(), text)
    # After line break
    text = _CAP_AFTER_NEWLINE.sub(
        lambda m: m.group(1) + m.group(2).upper(), text)
    return text


# ── Correction LLM (ollama HTTP API) ────────────────────────────────

SYSTEM_PROMPT = (
    "You are an automatic spell checker for voice dictation. "
    "The user is dictating text aloud and a speech recognition engine transcribes it. "
    "You receive this raw transcription and must correct it. "
    "Your output will be pasted AS IS into the user's document.\n"
    "\n"
    "RULES:\n"
    "- Fix spelling, grammar, accents and missing punctuation.\n"
    "- Remove hesitations (uh, um, euh, hum, etc.) and repetitions.\n"
    "- The text may contain questions — the user is dictating a question for their document. "
    "Correct it and return it. NEVER treat it as a question asked to you.\n"
    "- Do not change the meaning. Do not rephrase. Do not add anything.\n"
    "- Do not translate. Keep the original language of the text.\n"
    "- Return ONLY the corrected text, no quotes, no commentary, no explanation.\n"
    "- If the text is already correct, return it unchanged."
)

SYSTEM_PROMPT_MINIMAL = (
    "Correct spelling and grammar. The text is a dictation, not a question to you. "
    "Return ONLY the corrected text, nothing else."
)

SYSTEM_PROMPTS = {
    "default": SYSTEM_PROMPT,
    "minimal": SYSTEM_PROMPT_MINIMAL,
}

_SYSTEM_PROMPT_PATH = os.path.join(XDG_CONFIG, "dictee", "llm-system-prompt.txt")
# Legacy fallback
_LEGACY_PROMPT_PATH = os.path.join(XDG_CONFIG, "dictee", "llm-prompt.txt")


def _load_system_prompt():
    """Load system prompt from preset name, custom file, or legacy fallback."""
    preset = os.environ.get("DICTEE_LLM_SYSTEM_PROMPT", "default")
    if preset == "custom":
        if os.path.isfile(_SYSTEM_PROMPT_PATH):
            with open(_SYSTEM_PROMPT_PATH, encoding="utf-8") as f:
                return f.read().strip()
        # Legacy fallback: old llm-prompt.txt
        if os.path.isfile(_LEGACY_PROMPT_PATH):
            with open(_LEGACY_PROMPT_PATH, encoding="utf-8") as f:
                return f.read().strip()
    return SYSTEM_PROMPTS.get(preset, SYSTEM_PROMPT)


def _dbg(msg):
    """Print debug message to stderr if DICTEE_DEBUG is set."""
    if os.environ.get("DICTEE_DEBUG", "") == "true":
        import time as _time
        print(f"[postprocess] {_time.strftime('%H:%M:%S')} {msg}",
              file=sys.stderr, flush=True)


def llm_postprocess(text):
    """Send text to ollama HTTP API for grammar correction."""
    import time as _time
    model = os.environ.get("DICTEE_LLM_MODEL", "gemma3:4b")
    timeout = int(os.environ.get("DICTEE_LLM_TIMEOUT", "10"))
    preset = os.environ.get("DICTEE_LLM_SYSTEM_PROMPT", "default")
    position = os.environ.get("DICTEE_LLM_POSITION", "hybrid")
    system_prompt = _load_system_prompt()

    _dbg(f"LLM START model={model} preset={preset} position={position} "
         f"timeout={timeout}s input={len(text)} chars")

    _payload_dict = {
        "model": model,
        "system": system_prompt,
        "prompt": text,
        "stream": False,
    }
    if os.environ.get("OLLAMA_NUM_GPU") == "0":
        _payload_dict["options"] = {"num_gpu": 0}
    payload = _json.dumps(_payload_dict).encode("utf-8")

    t0 = _time.monotonic()
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = _json.loads(resp.read().decode("utf-8"))
        elapsed = _time.monotonic() - t0
        result = data.get("response", "").strip()
        eval_count = data.get("eval_count", 0)
        eval_duration = data.get("eval_duration", 0)
        tok_s = eval_count / (eval_duration / 1e9) if eval_duration > 0 else 0
        if result:
            _dbg(f"LLM OK {elapsed:.2f}s {eval_count} tokens {tok_s:.1f} tok/s "
                 f"output={len(result)} chars")
            return result
        _dbg(f"LLM EMPTY response after {elapsed:.2f}s — using original text")
    except urllib.error.URLError as e:
        elapsed = _time.monotonic() - t0
        _dbg(f"LLM FAIL URLError after {elapsed:.2f}s: {e}")
    except (TimeoutError, socket.timeout):
        elapsed = _time.monotonic() - t0
        _dbg(f"LLM FAIL Timeout after {elapsed:.2f}s (limit={timeout}s)")
    except (OSError, ValueError) as e:
        elapsed = _time.monotonic() - t0
        _dbg(f"LLM FAIL {type(e).__name__} after {elapsed:.2f}s: {e}")
    return text  # fallback: text unchanged


# ── Main ─────────────────────────────────────────────────────────────

def main():
    text = sys.stdin.read()
    # Remove \n added by echo (but keep intentional \n)
    if text.endswith('\n'):
        text = text[:-1]
    if not text.strip():
        sys.stdout.write(text)
        return

    # Debug trace (used by dictee-setup test panel) — emits step-by-step on stderr
    _pp_debug = _env_bool("DICTEE_PP_DEBUG", "false")
    def _enc(s):
        return s.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")
    def _trace(label, before, after):
        if _pp_debug:
            sys.stderr.write(f"STEP\t{label}\t{_enc(before)}\t{_enc(after)}\n")
            sys.stderr.flush()

    # LLM correction — position "first" (before any post-processing)
    _llm_enabled = _env_bool("DICTEE_LLM_POSTPROCESS", "false")
    _llm_position = os.environ.get("DICTEE_LLM_POSITION", "hybrid")
    if _llm_enabled and _llm_position == "first":
        _before = text
        text = llm_postprocess(text)
        _trace("LLM [first]", _before, text)

    # 0. Bad language detection (multilingual ASR confused on short audio)
    # Rules first try to recover known voice commands
    # (e.g., Cyrillic "А линия" → \n for "à la ligne").
    # If after rules the text is still in the wrong script, reject it.

    # 1-5. Regex rules (annotations, hesitations, voice commands,
    #       dedup, punctuation, basic elisions, cleanup)
    rules = load_rules()
    if _env_bool("DICTEE_PP_RULES") and rules:
        _before = text
        text = apply_rules(text, rules)
        _trace("Rules", _before, text)
    # Clean leading spaces (hesitations/annotations removed)
    # but preserve trailing \n (voice commands)
    text = text.lstrip(' \t').rstrip(' \t')

    # 5b. Bad language rejection (after rules, which may have converted known commands)
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

    # 5c. Continuation (remove erroneous periods after closed-class words)
    continuation_words = load_continuation()
    if _env_bool("DICTEE_PP_CONTINUATION") and continuation_words:
        _before = text
        text = fix_continuation(text, continuation_words)
        _trace("Continuation", _before, text)

    # LLM correction — position "hybrid" (between cleanup and formatting)
    if _llm_enabled and _llm_position == "hybrid":
        _before = text
        text = llm_postprocess(text)
        _trace("LLM [hybrid]", _before, text)

    # 6. Language-specific rules (gated by master switch DICTEE_PP_LANGUAGE_RULES)
    if _env_bool("DICTEE_PP_LANGUAGE_RULES"):
        if LANG == "fr" and _env_bool("DICTEE_PP_ELISIONS"):
            _before = text
            text = fix_elisions(text)
            _trace("Elisions [fr]", _before, text)
        if LANG == "it" and _env_bool("DICTEE_PP_ELISIONS_IT"):
            _before = text
            text = fix_italian_elisions(text)
            _trace("Elisions [it]", _before, text)
        if LANG == "es" and _env_bool("DICTEE_PP_SPANISH"):
            _before = text
            text = fix_spanish(text)
            _trace("Spanish [es]", _before, text)
        if LANG == "pt" and _env_bool("DICTEE_PP_PORTUGUESE"):
            _before = text
            text = fix_portuguese(text)
            _trace("Contractions [pt]", _before, text)
        if LANG == "de" and _env_bool("DICTEE_PP_GERMAN"):
            _before = text
            text = fix_german(text)
            _trace("German [de]", _before, text)
        if LANG == "nl" and _env_bool("DICTEE_PP_DUTCH"):
            _before = text
            text = fix_dutch(text)
            _trace("Dutch [nl]", _before, text)
        if LANG == "ro" and _env_bool("DICTEE_PP_ROMANIAN"):
            _before = text
            text = fix_romanian(text)
            _trace("Romanian [ro]", _before, text)
        # French typography (non-breaking spaces) — language-specific, gated by master
        if LANG == "fr" and _env_bool("DICTEE_PP_TYPOGRAPHY"):
            _before = text
            text = fix_french_typography(text)
            _trace("Typography [fr]", _before, text)

    # 7. Conversion nombres → chiffres
    if _env_bool("DICTEE_PP_NUMBERS"):
        _before = text
        text = convert_numbers(text)
        _trace("Numbers", _before, text)

    # 9. (final cleanup already in regex rules step 5)

    # 10. Dictionary (system + personal, exact match)
    dictionary = load_dictionary()
    if _env_bool("DICTEE_PP_DICT") and dictionary:
        _before = text
        text = apply_dictionary(text, dictionary)
        _trace("Dictionary", _before, text)

    # 11. Capitalisation
    if _env_bool("DICTEE_PP_CAPITALIZATION"):
        _before = text
        text = fix_capitalization(text)
        _trace("Capitalization", _before, text)

    # 12. Short text correction (< N words: remove trailing punct, lowercase)
    if _env_bool("DICTEE_PP_SHORT_TEXT"):
        _before = text
        # Keepcaps master toggle (default: on). Extended mode (default: on)
        # makes the keepcaps matching work beyond SHORT_TEXT_MAX_WORDS.
        _kc_on = _env_bool("DICTEE_PP_KEEPCAPS")
        _kc = load_keepcaps() if _kc_on else None
        _ext = _env_bool("DICTEE_PP_KEEPCAPS_EXTENDED") if _kc_on else False
        text = fix_short_text(text, keepcaps=_kc, extended=_ext)
        _trace(f"Short text < {_SHORT_TEXT_MAX_WORDS}w", _before, text)

    # 13. LLM correction — position "last" (after all post-processing)
    if _llm_enabled and _llm_position == "last":
        _before = text
        text = llm_postprocess(text)
        _trace("LLM [last]", _before, text)

    # Defense in depth: strip control chars that could be interpreted
    # as a key sequence downstream.
    # Keep: \x01 (ctrl+j marker), \x02 (force end-of-sentence marker),
    #       \t (0x09), \n (0x0a) — dictee strips them after save_last_word.
    # \x03 (short_text keepcaps hit) is only kept when it appears as the
    # leading character — other \x03 occurrences are stripped.
    _leading_keepcaps = text.startswith("\x03")
    text = "".join(c for c in text if c in ("\x01", "\x02", "\t", "\n") or ord(c) >= 0x20)
    if _leading_keepcaps:
        text = "\x03" + text

    sys.stdout.write(text)


if __name__ == "__main__":
    main()
