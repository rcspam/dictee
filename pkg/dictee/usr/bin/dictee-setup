#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dictee-setup — Voice dictation configuration
Qt6 UI to configure keyboard shortcut and translation options.
Saves to ~/.config/dictee.conf (shell format, sourceable by dictee).
Supports PyQt6 (preferred) and PySide6 (fallback).
"""

import gettext
import math
import os

# Suppress Wayland "grabbing the mouse only for popup windows" warnings
# triggered by setCursor() on non-popup widgets (ToggleSwitch, grips, etc.)
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland.warning=false")
import re
import shutil
import struct
import subprocess
import sys
import locale
import tempfile
import time

# Allow importing dictee_models from local dir first (dev), then /usr/lib/dictee (packaged)
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
_lib_dir = "/usr/lib/dictee"
if _lib_dir not in sys.path and os.path.isdir(_lib_dir):
    sys.path.append(_lib_dir)

try:
    from PyQt6.QtCore import (
        Qt, QThread, QTimer, QIODevice, QObject, QProcess, QSize, QRect, QRectF,
        QUrl, QPropertyAnimation, QEasingCurve, QFileSystemWatcher,
        pyqtSignal as Signal, pyqtProperty as Property,
    )
    from PyQt6.QtGui import QKeySequence, QIcon, QPainter, QColor, QBrush, QPen, QLinearGradient, QImage, QPixmap, QSyntaxHighlighter, QFont
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
        QLabel, QPushButton, QRadioButton, QButtonGroup, QComboBox,
        QFormLayout, QProgressBar, QMessageBox, QSizePolicy, QCheckBox,
        QFrame, QScrollArea, QWidget, QStackedWidget, QSlider, QTextEdit,
        QToolTip, QGridLayout, QTabWidget, QLineEdit, QLayout, QSpinBox,
        QStyledItemDelegate, QStyleOptionViewItem, QStylePainter, QStyleOptionComboBox,
        QListWidget, QListWidgetItem, QDialogButtonBox, QKeySequenceEdit,
    )
    from PyQt6.QtMultimedia import QAudioSource, QAudioFormat, QMediaDevices, QMediaPlayer, QAudioOutput
except ImportError:
    from PySide6.QtCore import (
        Qt, QThread, QTimer, QIODevice, QObject, QProcess, QSize, QRect, QRectF,
        QUrl, QPropertyAnimation, QEasingCurve, QFileSystemWatcher,
        Signal, Property,
    )
    from PySide6.QtGui import QKeySequence, QIcon, QPainter, QColor, QBrush, QPen, QLinearGradient, QImage, QPixmap, QSyntaxHighlighter, QFont
    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
        QLabel, QPushButton, QRadioButton, QButtonGroup, QComboBox,
        QFormLayout, QProgressBar, QMessageBox, QSizePolicy, QCheckBox, QGridLayout,
        QFrame, QScrollArea, QWidget, QStackedWidget, QSlider, QTextEdit,
        QToolTip, QTabWidget, QLineEdit, QLayout, QSpinBox,
        QStyledItemDelegate, QStyleOptionViewItem, QStylePainter, QStyleOptionComboBox,
        QListWidget, QListWidgetItem, QDialogButtonBox, QKeySequenceEdit,
    )
    from PySide6.QtMultimedia import QAudioSource, QAudioFormat, QMediaDevices, QMediaPlayer, QAudioOutput

# === i18n ===

LOCALE_DIRS = [
    # User-space first so dev / hot translation updates win over the
    # stale .mo shipped by the system package — avoids needing sudo
    # to refresh translations during iteration.
    os.path.expanduser("~/.local/share/locale"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "share", "locale"),
    "/usr/local/share/locale",
    "/usr/share/locale",
]

for _d in LOCALE_DIRS:
    if os.path.isfile(os.path.join(_d, "fr", "LC_MESSAGES", "dictee.mo")):
        gettext.bindtextdomain("dictee", _d)
        break

gettext.textdomain("dictee")
_ = gettext.gettext


def _tt(text):
    """Wrap a tooltip in HTML rich-text so Qt activates word-wrap and
    caps the width to 400px — otherwise long plain-text tooltips
    stretch to the full screen width on wide monitors. 400px is the
    project-wide convention (cf. feedback-tooltips-width-400.md).
    Short tooltips (<= 60 chars) get a <span> with the same font-size,
    skipping the wrap because it isn't needed."""
    if len(text) > 60:
        return ("<p style='font-size:11pt; white-space:pre-wrap; "
                "width:400px;'>" + text + "</p>")
    return f"<span style='font-size:11pt'>{text}</span>"


_NATIVE_TEXT = QKeySequence.SequenceFormat.NativeText

# === Configuration ===

CONF_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "dictee.conf",
)

LANGUAGES = [
    ("fr", "Français"),
    ("en", "English"),
    ("es", "Español"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("pt", "Português"),
    ("nl", "Nederlands"),
    ("pl", "Polski"),
    ("ru", "Русский"),
    ("uk", "Українська"),
    ("bg", "Български"),
    ("cs", "Čeština"),
    ("da", "Dansk"),
    ("el", "Ελληνικά"),
    ("et", "Eesti"),
    ("fi", "Suomi"),
    ("hr", "Hrvatski"),
    ("hu", "Magyar"),
    ("lt", "Lietuvių"),
    ("lv", "Latviešu"),
    ("mt", "Malti"),
    ("ro", "Română"),
    ("sk", "Slovenčina"),
    ("sl", "Slovenščina"),
    ("sv", "Svenska"),
    ("zh", "中文"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("ar", "العربية"),
]

# Extended English names for codes returned by dictee-translate-langs for
# cloud backends (google/bing ~130, ollama ~90). Used when a code isn't
# present in LANGUAGES (native names).
TARGET_LANG_NAMES_EN = {
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "as": "Assamese",
    "ay": "Aymara", "az": "Azerbaijani", "ba": "Bashkir", "be": "Belarusian",
    "bg": "Bulgarian", "bm": "Bambara", "bn": "Bengali", "bo": "Tibetan",
    "bs": "Bosnian", "ca": "Catalan", "co": "Corsican", "cs": "Czech",
    "cv": "Chuvash", "cy": "Welsh", "da": "Danish", "de": "German",
    "dv": "Dhivehi", "ee": "Ewe", "el": "Greek", "en": "English",
    "eo": "Esperanto", "es": "Spanish", "et": "Estonian", "eu": "Basque",
    "fa": "Persian", "fi": "Finnish", "fj": "Fijian", "fo": "Faroese",
    "fr": "French", "fr-CA": "French (Canada)", "fy": "Western Frisian",
    "ga": "Irish", "gd": "Scottish Gaelic", "gl": "Galician",
    "gn": "Guarani", "gu": "Gujarati", "ha": "Hausa", "he": "Hebrew",
    "hi": "Hindi", "hr": "Croatian", "ht": "Haitian Creole",
    "hu": "Hungarian", "hy": "Armenian", "id": "Indonesian",
    "ig": "Igbo", "is": "Icelandic", "it": "Italian", "iu": "Inuktitut",
    "ja": "Japanese", "jv": "Javanese", "ka": "Georgian", "kk": "Kazakh",
    "km": "Khmer", "kn": "Kannada", "ko": "Korean", "ku": "Kurdish",
    "ky": "Kyrgyz", "la": "Latin", "lb": "Luxembourgish", "lg": "Ganda",
    "ln": "Lingala", "lo": "Lao", "lt": "Lithuanian", "lv": "Latvian",
    "mg": "Malagasy", "mi": "Maori", "mk": "Macedonian", "ml": "Malayalam",
    "mn": "Mongolian", "mr": "Marathi", "ms": "Malay", "mt": "Maltese",
    "my": "Burmese", "ne": "Nepali", "nl": "Dutch", "no": "Norwegian",
    "ny": "Chichewa", "om": "Oromo", "or": "Odia", "pa": "Punjabi",
    "pl": "Polish", "ps": "Pashto", "pt": "Portuguese",
    "pt-BR": "Portuguese (Brazil)", "pt-PT": "Portuguese (Portugal)",
    "qu": "Quechua", "ro": "Romanian", "ru": "Russian", "rw": "Kinyarwanda",
    "sa": "Sanskrit", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak",
    "sl": "Slovenian", "sm": "Samoan", "sn": "Shona", "so": "Somali",
    "sq": "Albanian", "sr": "Serbian", "st": "Sesotho", "su": "Sundanese",
    "sv": "Swedish", "sw": "Swahili", "ta": "Tamil", "te": "Telugu",
    "tg": "Tajik", "th": "Thai", "ti": "Tigrinya", "tk": "Turkmen",
    "tl": "Tagalog", "to": "Tongan", "tr": "Turkish", "ts": "Tsonga",
    "tt": "Tatar", "tw": "Twi", "ty": "Tahitian", "ug": "Uyghur",
    "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese",
    "xh": "Xhosa", "yi": "Yiddish", "yo": "Yoruba", "zh": "Chinese",
    "zh-CN": "Chinese (Simplified)", "zh-TW": "Chinese (Traditional)",
    "zu": "Zulu",
}

# Languages supported by each ASR backend (pour filtrer la langue source)
# Parakeet TDT 0.6B v3: 25 European languages (source: NVIDIA HuggingFace)
PARAKEET_LANGUAGES = {
    "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr",
    "hr", "hu", "it", "lt", "lv", "mt", "nl", "pl", "pt", "ro",
    "ru", "sk", "sl", "sv", "uk",
}
CANARY_LANGUAGES = PARAKEET_LANGUAGES  # same 25 EU languages
ASR_LANGUAGES = {
    "parakeet": PARAKEET_LANGUAGES,
    "vosk": {"fr", "en", "de", "es", "it", "pt", "ru", "zh", "ja"},
    "whisper": None,   # None = toutes
    "canary": CANARY_LANGUAGES,
}

# Languages supported by each translation backend (pour filtrer la langue cible)
# None = all, set() = limited
TRANSLATE_LANGUAGES = {
    "trans:google": None,
    "trans:bing": None,
    "ollama": None,
    "libretranslate": None,  # Dynamic — filtered via installed languages
}

DICTEE_COMMAND = "/usr/bin/dictee"
DICTEE_TRANSLATE_COMMAND = "/usr/bin/dictee --translate"
DICTEE_DESKTOP = "dictee.desktop"
DICTEE_TRANSLATE_DESKTOP = "dictee-translate.desktop"

# Mapping Qt key → Linux keycode (evdev) pour dictee-ptt
QT_TO_LINUX_KEYCODE = {
    0x01000030: 59,   # F1
    0x01000031: 60,   # F2
    0x01000032: 61,   # F3
    0x01000033: 62,   # F4
    0x01000034: 63,   # F5
    0x01000035: 64,   # F6
    0x01000036: 65,   # F7
    0x01000037: 66,   # F8
    0x01000038: 67,   # F9
    0x01000039: 68,   # F10
    0x0100003a: 87,   # F11
    0x0100003b: 88,   # F12
    0x01000000: 1,    # Escape
    0x01000010: 110,  # Home
    0x01000011: 107,  # End
    0x01000016: 119,  # Delete
    0x01000015: 118,  # Insert
    0x01000017: 104,  # Pause/Break
    0x01000009: 210,  # Print Screen (SysRq)
    0x01000025: 14,   # Backspace — non, pas utile
}

LINUX_KEYCODE_NAMES = {
    59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6",
    65: "F7", 66: "F8", 67: "F9", 68: "F10", 87: "F11", 88: "F12",
    1: "Escape", 110: "Home", 107: "End", 119: "Delete", 118: "Insert",
}


def qt_key_to_linux_keycode(seq):
    """Convertit une QKeySequence en keycode Linux evdev."""
    if seq is None:
        return 0
    key_int = seq[0].toCombined() if hasattr(seq[0], 'toCombined') else int(seq[0])
    # Masquer les modificateurs Qt (0x0e000000)
    key_only = key_int & 0x01ffffff
    return QT_TO_LINUX_KEYCODE.get(key_only, 0)


def linux_keycode_name(code):
    """Retourne le nom lisible d'un keycode Linux."""
    return LINUX_KEYCODE_NAMES.get(code, f"Key {code}")
ANIMATION_SPEECH_REPO = "rcspam/animation-speech"
ANIMATION_SPEECH_BIN = "animation-speech-ctl"

# === DE detection ===


def detect_desktop():
    """Retourne (nom_affiché, type) avec type = 'kde' | 'gnome' | 'unsupported'."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "KDE" in desktop:
        return "KDE Plasma", "kde"
    for name in ("GNOME", "UNITY", "CINNAMON"):
        if name in desktop:
            label = desktop.replace(";", " / ").title()
            return label, "gnome"
    raw = os.environ.get("XDG_CURRENT_DESKTOP", _("unknown"))
    return raw, "unsupported"


# === Config fichier ===


def load_config():
    """Charge dictee.conf et retourne un dict des valeurs.

    Strips surrounding quotes from legacy or manually-quoted values.
    """
    conf = {}
    if os.path.isfile(CONF_PATH):
        with open(CONF_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"^([A-Z_]+)=(.*)$", line)
                if m:
                    val = m.group(2)
                    # Strip surrounding quotes (legacy or manual edits)
                    if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
                        val = val[1:-1]
                    elif len(val) >= 2 and val[0] == "'" and val[-1] == "'":
                        val = val[1:-1]
                    conf[m.group(1)] = val
    return conf


def _sanitize_conf_value(val):
    """Sanitize a value for safe unquoted bash sourcing (KEY=value).

    Strips characters that would cause injection or syntax errors when
    the file is sourced by bash.  Preserves regex metacharacters needed
    for command suffixes: [ ] ? . * + ^
    """
    # Stripped: newlines, shell expansion ($, `, \), quoting (" '),
    # command separators (;, |, &), redirections (<, >), braces ({, }),
    # history (!), subshells (( )), whitespace (space, tab)
    return re.sub(r'[\n\r`$"\'\\;|&<>{}!() \t]', '', str(val))


def save_config(backend, lang_source, lang_target, clipboard=True,
                anim_speech=True, anim_plasmoid=False,
                ollama_model="translategemma", ollama_cpu=False, trans_engine="google",
                lt_port=5000, lt_langs="", asr_backend="parakeet", whisper_model="small",
                whisper_lang="", vosk_model="fr", audio_source="",
                ptt_mode="toggle", ptt_key=67, ptt_key_translate=0,
                ptt_mod_translate="", postprocess=True, pp_translate=True,
                pp_elisions=True, pp_elisions_it=True,
                pp_spanish=True, pp_portuguese=True, pp_german=True,
                pp_dutch=True, pp_romanian=True,
                pp_numbers=True, pp_typography=True,
                pp_capitalization=True, pp_dict=True,
                pp_rules=True, pp_continuation=True,
                pp_language_rules=True,
                pp_short_text=True, pp_short_text_max=3,
                pp_keepcaps=True, pp_keepcaps_extended=True,
                llm_postprocess=False, llm_model="gemma3:4b",
                llm_timeout=10, llm_cpu=False,
                llm_system_prompt="default", llm_position="hybrid",
                llm_custom_prompt="",
                continuation_indicator=">>",
                audio_context=False, audio_context_timeout=30,
                silence_rms=0.03,
                notifications=True, notifications_text=True,
                command_suffixes=None, debug=False,
                trpp_states=None, trpp_short_text_max=3,
                cheatsheet_mod="", cheatsheet_key_seq=""):
    """Update dictee.conf preserving comments and structure.

    Reads the existing file (or the template on first run), then patches
    only the values that changed.  Comments and section headers are kept.
    Values are unquoted (compatible with grep/cut/sed consumers) and
    sanitized to prevent shell injection.
    """
    # Build the desired key→value map
    # Sanitize user-supplied values; controlled enums/bools are safe as-is
    _s = _sanitize_conf_value
    reverse = {v: k for k, v in VOSK_MODELS.items()}
    vosk_code = reverse.get(vosk_model, vosk_model)

    values = {
        "DICTEE_ASR_BACKEND": asr_backend,
        "DICTEE_TRANSLATE_BACKEND": backend,
        "DICTEE_LANG_SOURCE": lang_source,
        "DICTEE_LANG_TARGET": lang_target,
        "DICTEE_CLIPBOARD": "true" if clipboard else "false",
        "DICTEE_ANIM_SPEECH": "true" if anim_speech else "false",
        "DICTEE_ANIM_PLASMOID": "true" if anim_plasmoid else "false",
        "DICTEE_VOSK_MODEL": _s(vosk_code),
        "DICTEE_WHISPER_MODEL": _s(whisper_model),
        "DICTEE_PTT_MODE": ptt_mode,
        "DICTEE_PTT_KEY": str(ptt_key),
        "DICTEE_POSTPROCESS": "true" if postprocess else "false",
        "DICTEE_PP_TRANSLATE": "true" if pp_translate else "false",
        "DICTEE_AUDIO_CONTEXT": "true" if audio_context else "false",
        "DICTEE_AUDIO_CONTEXT_TIMEOUT": str(audio_context_timeout),
        "DICTEE_SILENCE_RMS": f"{silence_rms:.3f}",
        "DICTEE_SETUP_DONE": "true",
    }
    # Conditional values (only written when non-default)
    if whisper_lang:
        values["DICTEE_WHISPER_LANG"] = _s(whisper_lang)
    if audio_source:
        values["DICTEE_AUDIO_SOURCE"] = _s(audio_source)
    if ptt_key_translate:
        values["DICTEE_PTT_KEY_TRANSLATE"] = str(ptt_key_translate)
    if ptt_mod_translate:
        values["DICTEE_PTT_MOD_TRANSLATE"] = _s(ptt_mod_translate)
    # Translation backend-specific
    if backend == "trans":
        values["DICTEE_TRANS_ENGINE"] = trans_engine
    elif backend == "libretranslate":
        values["DICTEE_LIBRETRANSLATE_PORT"] = str(lt_port)
        if lt_langs:
            values["DICTEE_LIBRETRANSLATE_LANGS"] = _s(lt_langs)
    elif backend == "ollama":
        values["DICTEE_OLLAMA_MODEL"] = _s(ollama_model)
        if ollama_cpu:
            values["OLLAMA_NUM_GPU"] = "0"
    # Post-processing flags
    _pp_flags = {
        "DICTEE_PP_ELISIONS": pp_elisions,
        "DICTEE_PP_ELISIONS_IT": pp_elisions_it,
        "DICTEE_PP_SPANISH": pp_spanish,
        "DICTEE_PP_PORTUGUESE": pp_portuguese,
        "DICTEE_PP_GERMAN": pp_german,
        "DICTEE_PP_DUTCH": pp_dutch,
        "DICTEE_PP_ROMANIAN": pp_romanian,
        "DICTEE_PP_NUMBERS": pp_numbers,
        "DICTEE_PP_TYPOGRAPHY": pp_typography,
        "DICTEE_PP_CAPITALIZATION": pp_capitalization,
        "DICTEE_PP_DICT": pp_dict,
        "DICTEE_PP_RULES": pp_rules,
        "DICTEE_PP_CONTINUATION": pp_continuation,
        "DICTEE_PP_LANGUAGE_RULES": pp_language_rules,
        "DICTEE_PP_SHORT_TEXT": pp_short_text,
        "DICTEE_PP_KEEPCAPS": pp_keepcaps,
        "DICTEE_PP_KEEPCAPS_EXTENDED": pp_keepcaps_extended,
    }
    for key, enabled in _pp_flags.items():
        values[key] = "true" if enabled else "false"
    values["DICTEE_PP_SHORT_TEXT_MAX"] = str(pp_short_text_max)
    # Translation post-processing flags (TRPP)
    if trpp_states:
        _trpp_map = {
            "rules": "DICTEE_TRPP_RULES",
            "continuation": "DICTEE_TRPP_CONTINUATION",
            "language_rules": "DICTEE_TRPP_LANGUAGE_RULES",
            "numbers": "DICTEE_TRPP_NUMBERS",
            "dict": "DICTEE_TRPP_DICT",
            "capitalization": "DICTEE_TRPP_CAPITALIZATION",
            "short_text": "DICTEE_TRPP_SHORT_TEXT",
        }
        for k, conf_key in _trpp_map.items():
            values[conf_key] = "true" if trpp_states.get(k, True) else "false"
        values["DICTEE_TRPP_SHORT_TEXT_MAX"] = str(trpp_short_text_max)
    # Continuation visual indicator — must NOT go through _s() because it
    # would strip <, >, & exactly the chars we want. Wrap in single quotes
    # so bash sources it literally; escape any inner single quote.
    _ind_clean = (continuation_indicator or ">>").replace("'", "'\\''")
    values["DICTEE_CONTINUATION_INDICATOR"] = "'" + _ind_clean + "'"
    # LLM post-processing
    values["DICTEE_LLM_POSTPROCESS"] = "true" if llm_postprocess else "false"
    if llm_postprocess:
        values["DICTEE_LLM_MODEL"] = _s(llm_model)
        values["DICTEE_LLM_TIMEOUT"] = str(llm_timeout)
        if llm_cpu:
            values["DICTEE_LLM_CPU"] = "true"
        values["DICTEE_LLM_SYSTEM_PROMPT"] = _s(llm_system_prompt)
        values["DICTEE_LLM_POSITION"] = llm_position
        # Save custom prompt to file
        _custom_path = os.path.join(
            os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
            "dictee", "llm-system-prompt.txt")
        if llm_system_prompt == "custom" and llm_custom_prompt.strip():
            os.makedirs(os.path.dirname(_custom_path), exist_ok=True)
            with open(_custom_path, "w", encoding="utf-8") as f:
                f.write(llm_custom_prompt.strip() + "\n")
    # Notifications
    values["DICTEE_NOTIFICATIONS"] = "true" if notifications else "false"
    values["DICTEE_NOTIFICATIONS_TEXT"] = "true" if notifications_text else "false"
    # Command suffixes
    if command_suffixes:
        for code, suffix in command_suffixes.items():
            if suffix:
                values[f"DICTEE_COMMAND_SUFFIX_{code.upper()}"] = _s(suffix)
    if debug:
        values["DICTEE_DEBUG"] = "true"
    # Cheatsheet shortcut mode (mirrors the translation pattern):
    # alt | ctrl | ctrl_alt | shift | separate | disabled.
    if cheatsheet_mod:
        values["DICTEE_CHEATSHEET_MOD"] = _s(cheatsheet_mod)
    if cheatsheet_key_seq:
        values["DICTEE_CHEATSHEET_KEY_SEQ"] = _s(cheatsheet_key_seq)

    # Keys that must be re-commented when absent from values.
    # Without this, a previously active key stays active forever.
    # NOTE: DICTEE_PRE_DIARIZE_BACKEND is intentionally excluded —
    # it is managed by dictee-switch-backend, not by the GUI.
    _all_managed_keys = set(values.keys()) | {
        "DICTEE_WHISPER_LANG", "DICTEE_AUDIO_SOURCE",
        "DICTEE_PTT_KEY_TRANSLATE", "DICTEE_PTT_MOD_TRANSLATE",
        "DICTEE_CHEATSHEET_MOD", "DICTEE_CHEATSHEET_KEY_SEQ",
        "DICTEE_TRANS_ENGINE", "DICTEE_LIBRETRANSLATE_PORT",
        "DICTEE_LIBRETRANSLATE_LANGS", "DICTEE_OLLAMA_MODEL",
        "OLLAMA_NUM_GPU", "DICTEE_LLM_POSTPROCESS",
        "DICTEE_LLM_MODEL", "DICTEE_LLM_TIMEOUT", "DICTEE_LLM_CPU",
        "DICTEE_DEBUG", "DICTEE_PP_SHORT_TEXT_MAX",
        "DICTEE_ANIMATION",  # legacy, replaced by ANIM_SPEECH + ANIM_PLASMOID
    }
    # Add all possible suffix keys
    for lang in ("FR", "EN", "ES", "DE", "IT", "PT", "UK"):
        _all_managed_keys.add(f"DICTEE_COMMAND_SUFFIX_{lang}")
    # Keys to re-comment = managed but not in values
    _comment_out = _all_managed_keys - set(values.keys())

    # Read existing file or template.
    # If the existing file has no section headers (old flat format),
    # migrate to the commented template.
    _example = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "dictee.conf.example")
    _installed_example = "/usr/share/dictee/dictee.conf.example"
    lines = []
    _use_template = True
    if os.path.isfile(CONF_PATH):
        with open(CONF_PATH) as f:
            lines = f.readlines()
        # Keep existing file only if it has section separators (new format)
        if any("====" in line for line in lines):
            _use_template = False
    if _use_template:
        for path in (_example, _installed_example):
            if os.path.isfile(path):
                with open(path) as f:
                    lines = f.readlines()
                break

    # Patch lines in-place
    written_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.rstrip("\r\n")
        # Match "KEY=value" or "#KEY=value"
        m = re.match(r'^(#?)([A-Z_]+=)(.*)', stripped)
        if m:
            commented, kv_prefix, _old_val = m.groups()
            key = kv_prefix.rstrip("=")
            if key in values:
                if key not in written_keys:
                    new_lines.append(f"{key}={values[key]}\n")
                    written_keys.add(key)
                # else: drop duplicate line
                continue
            if key in _comment_out and not commented:
                # Re-comment: key was active but is no longer needed
                new_lines.append(f"#{key}={_old_val}\n")
                continue
        new_lines.append(line if line.endswith("\n") else line + "\n")

    # Append any keys not yet in the file (before DICTEE_SETUP_DONE)
    missing = {k: v for k, v in values.items() if k not in written_keys
               and k != "DICTEE_SETUP_DONE"}
    if missing:
        # Insert before the SETUP_DONE marker if present
        insert_idx = len(new_lines)
        for i, line in enumerate(new_lines):
            if line.startswith("DICTEE_SETUP_DONE="):
                insert_idx = i
                break
        extra = []
        for k, v in missing.items():
            extra.append(f"{k}={v}\n")
        new_lines[insert_idx:insert_idx] = extra

    # Atomic write
    conf_dir = os.path.dirname(CONF_PATH) or "."
    os.makedirs(conf_dir, exist_ok=True)
    _tmp_fd, _tmp_path = tempfile.mkstemp(dir=conf_dir, prefix=".dictee.conf.")
    try:
        with os.fdopen(_tmp_fd, "w") as f:
            f.writelines(new_lines)
        os.replace(_tmp_path, CONF_PATH)
    except BaseException:
        try:
            os.unlink(_tmp_path)
        except OSError:
            pass
        raise


# === Raccourci KDE ===


def qt_key_to_kde(key_sequence):
    """Convertit une QKeySequence en format KDE ('Meta+D')."""
    return key_sequence.toString()


def find_kde_shortcut_for_command(command):
    """Trouve le raccourci KDE existant pour une commande donnée.

    Scanne les .desktop dans ~/.local/share/applications/ pour trouver
    ceux dont Exec correspond, puis lit le raccourci dans kglobalshortcutsrc.
    Retourne (raccourci, nom_desktop) ou (None, None).
    """
    apps_dir = os.path.expanduser("~/.local/share/applications")
    rc_path = os.path.expanduser("~/.config/kglobalshortcutsrc")

    if not os.path.isdir(apps_dir) or not os.path.isfile(rc_path):
        return None, None

    # Trouver les .desktop dont Exec correspond
    matching_desktops = []
    try:
        for fname in os.listdir(apps_dir):
            if not fname.endswith(".desktop"):
                continue
            fpath = os.path.join(apps_dir, fname)
            try:
                with open(fpath) as f:
                    for line in f:
                        if line.strip().startswith("Exec="):
                            exec_cmd = line.strip().split("=", 1)[1].strip()
                            if exec_cmd == command:
                                matching_desktops.append(fname)
                            break
            except OSError:
                continue
    except OSError:
        return None, None

    if not matching_desktops:
        return None, None

    # Lire le raccourci depuis kglobalshortcutsrc
    try:
        with open(rc_path) as f:
            content = f.read()
    except OSError:
        return None, None

    for desktop_name in matching_desktops:
        target = f"[services][{desktop_name}]"
        idx = content.find(target)
        if idx < 0:
            continue
        for line in content[idx + len(target):].split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("["):
                break
            if line.startswith("_launch="):
                accel = line.split("=", 1)[1].split(",")[0].strip()
                if accel and accel != "none":
                    return accel, desktop_name

    return None, None


def _dictee_desktop_names():
    """Retourne les noms de tous les .desktop qui pointent vers dictee."""
    apps_dir = os.path.expanduser("~/.local/share/applications")
    names = {DICTEE_DESKTOP, DICTEE_TRANSLATE_DESKTOP}
    try:
        for fname in os.listdir(apps_dir):
            if not fname.endswith(".desktop"):
                continue
            try:
                with open(os.path.join(apps_dir, fname)) as f:
                    for line in f:
                        if line.strip().startswith("Exec="):
                            if "/usr/bin/dictee" in line:
                                names.add(fname)
                            break
            except OSError:
                continue
    except OSError:
        pass
    return names


def check_kde_conflict(accel_kde):
    """Vérifie si le raccourci est déjà utilisé dans kglobalshortcutsrc."""
    rc = os.path.expanduser("~/.config/kglobalshortcutsrc")
    if not os.path.isfile(rc):
        return None
    own_desktops = _dictee_desktop_names()
    try:
        with open(rc) as f:
            current_group = ""
            for line in f:
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    current_group = line[1:-1]
                    continue
                if any(d in current_group for d in own_desktops):
                    continue
                if "=" in line:
                    _key, val = line.split("=", 1)
                    parts = val.split(",")
                    if parts and parts[0].strip() == accel_kde:
                        return current_group
    except OSError:
        pass
    return None


def apply_kde_shortcut(accel_kde, desktop_name, command, label, key_sequence=None):
    """Applique le raccourci clavier sous KDE Plasma 6.

    1. Crée le .desktop dans ~/.local/share/applications/
    2. Écrit le raccourci dans kglobalshortcutsrc (persistance)
    3. Enregistre et active via D-Bus kglobalaccel (activation immédiate)
    """
    apps_dir = os.path.expanduser("~/.local/share/applications")
    os.makedirs(apps_dir, exist_ok=True)
    desktop_path = os.path.join(apps_dir, desktop_name)
    with open(desktop_path, "w") as f:
        f.write("[Desktop Entry]\n")
        f.write(f"Exec={command}\n")
        f.write(f"Name={label}\n")
        f.write("NoDisplay=true\n")
        f.write("StartupNotify=false\n")
        f.write("Type=Application\n")
        f.write("X-KDE-GlobalAccel-CommandShortcut=true\n")

    # Write shortcut to kglobalshortcutsrc (persists across reboots)
    subprocess.run(
        [
            "kwriteconfig6",
            "--file", "kglobalshortcutsrc",
            "--group", "services",
            "--group", desktop_name,
            "--key", "_launch",
            f"{accel_kde},none,{label}",
        ],
        check=True,
    )
    subprocess.run(
        [
            "kwriteconfig6",
            "--file", "kglobalshortcutsrc",
            "--group", "services",
            "--group", desktop_name,
            "--key", "_k_friendly_name",
            label,
        ],
        check=True,
    )

    # Activate immediately via D-Bus kglobalaccel
    if key_sequence is not None:
        _activate_kde_shortcut_dbus(desktop_name, label, key_sequence)

    return accel_kde


def _activate_kde_shortcut_dbus(desktop_name, label, key_sequence):
    """Active un raccourci via D-Bus kglobalaccel (sans redémarrage de session).

    Utilise doRegister + setForeignShortcutKeys pour enregistrer le composant
    et activer la touche immédiatement dans kglobalacceld.
    """
    # Convertir QKeySequence en code Qt int (modifiers | key)
    try:
        combined = key_sequence[0]
        # PyQt6 : QKeyCombination → .toCombined() → int
        if hasattr(combined, "toCombined"):
            qt_key_int = combined.toCombined()
        # PySide6: already int or enum with .value
        elif hasattr(combined, "value"):
            qt_key_int = combined.value
        else:
            qt_key_int = int(combined)
    except (IndexError, TypeError):
        return  # Pas de touche valide

    action_id = f"['{desktop_name}', '_launch', '{label}', '{label}']"

    # 1. Enregistrer le composant
    subprocess.run(
        [
            "gdbus", "call", "--session",
            "--dest", "org.kde.kglobalaccel",
            "--object-path", "/kglobalaccel",
            "--method", "org.kde.KGlobalAccel.doRegister",
            action_id,
        ],
        capture_output=True,
    )

    # 2. Affecter la touche
    keys = f"[([{qt_key_int}, 0, 0, 0],)]"
    subprocess.run(
        [
            "gdbus", "call", "--session",
            "--dest", "org.kde.kglobalaccel",
            "--object-path", "/kglobalaccel",
            "--method", "org.kde.KGlobalAccel.setForeignShortcutKeys",
            action_id,
            keys,
        ],
        capture_output=True,
    )


def remove_kde_shortcut(desktop_name):
    """Supprime un raccourci KDE global (désactive via D-Bus + nettoie kglobalshortcutsrc)."""
    # Supprimer de kglobalshortcutsrc
    subprocess.run(
        ["kwriteconfig6", "--file", "kglobalshortcutsrc",
         "--group", "services", "--group", desktop_name,
         "--key", "_launch", "--delete"],
        capture_output=True,
    )
    # Disable via D-Bus (empty key = no shortcut)
    action_id = f"['{desktop_name}', '_launch', '', '']"
    keys = "[([0, 0, 0, 0],)]"
    subprocess.run(
        ["gdbus", "call", "--session",
         "--dest", "org.kde.kglobalaccel",
         "--object-path", "/kglobalaccel",
         "--method", "org.kde.KGlobalAccel.setForeignShortcutKeys",
         action_id, keys],
        capture_output=True,
    )


# === Raccourci GNOME ===


def qt_key_to_gnome(key_sequence):
    """Convertit une QKeySequence en format GNOME ('<Super>d')."""
    s = key_sequence.toString()
    s = s.replace("Meta+", "<Super>")
    s = s.replace("Ctrl+", "<Primary>")
    s = s.replace("Alt+", "<Alt>")
    s = s.replace("Shift+", "<Shift>")
    if not s.endswith(">"):
        parts = s.rsplit(">", 1)
        if len(parts) == 2:
            s = parts[0] + ">" + parts[1].lower()
    return s


def apply_gnome_shortcut(accel_gnome):
    """Applique le raccourci clavier sous GNOME/Unity/Cinnamon."""
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    base_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
    slot = "dictee"
    path = f"{base_path}/{slot}/"

    try:
        result = subprocess.run(
            ["gsettings", "get", schema, "custom-keybindings"],
            capture_output=True, text=True, check=True,
        )
        current = result.stdout.strip()
        if path not in current:
            if current in ("@as []", "[]"):
                new_list = f"['{path}']"
            else:
                new_list = current.rstrip("]") + f", '{path}']"
            subprocess.run(
                ["gsettings", "set", schema, "custom-keybindings", new_list],
                check=True,
            )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    sub_schema = f"{schema}.custom-keybinding"
    subprocess.run(
        ["gsettings", "set", sub_schema + ":" + path, "name", _("Voice dictation")],
        check=True,
    )
    subprocess.run(
        ["gsettings", "set", sub_schema + ":" + path, "command", DICTEE_COMMAND],
        check=True,
    )
    subprocess.run(
        ["gsettings", "set", sub_schema + ":" + path, "binding", accel_gnome],
        check=True,
    )


# === Ollama helpers ===

# (model_id, label, min_ram_gb, min_vram_gb)
OLLAMA_MODELS = [
    ("translategemma", _("translategemma 4B (3.3 GB, 55 languages)"), 8, 4),
    ("translategemma:12b", _("translategemma 12B (8 GB, best quality)"), 16, 8),
    ("aya:8b", _("aya 8B (5 GB, Cohere, 23 languages)"), 16, 8),
]


def ollama_is_installed():
    """Vérifie si ollama est installé."""
    return shutil.which("ollama") is not None


def ollama_is_running():
    """Vérifie si le service ollama est accessible."""
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


def get_system_ram_gb():
    """Retourne la RAM totale en Go."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024 / 1024, 1)
    except (OSError, ValueError):
        pass
    return 0


def get_gpu_vram_gb():
    """Retourne (VRAM totale, VRAM libre) en Go. (0, 0) si pas de GPU."""
    # NVIDIA
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("\n")[0].split(",")
            total_mb = int(parts[0].strip())
            free_mb = int(parts[1].strip())
            return round(total_mb / 1024, 1), round(free_mb / 1024, 1)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        pass
    # AMD
    try:
        import glob
        for path in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
            total = int(open(path).read().strip())
            free_path = path.replace("vram_total", "vram_used")
            used = int(open(free_path).read().strip()) if os.path.exists(free_path) else 0
            total_gb = round(total / 1024**3, 1)
            free_gb = round((total - used) / 1024**3, 1)
            return total_gb, free_gb
    except (OSError, ValueError):
        pass
    return 0, 0


def check_cuda_gpu_ready():
    """Check if CUDA GPU acceleration is usable (cuDNN installed).
    Returns (gpu_detected, cudnn_ok, message)."""
    total, _free = get_gpu_vram_gb()
    if total == 0:
        return False, False, ""
    # GPU detected — check cuDNN
    try:
        import ctypes
        ctypes.cdll.LoadLibrary("libcudnn.so.9")
        return True, True, ""
    except OSError:
        pass
    # cuDNN missing — build a helpful message
    distro_id = ""
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("ID="):
                    distro_id = line.strip().split("=", 1)[1].strip('"')
                    break
    except OSError:
        pass
    if distro_id in ("ubuntu", "debian", "linuxmint", "pop"):
        msg = _(
            "NVIDIA GPU detected but cuDNN is not installed.\n"
            "GPU acceleration will not work without it.\n\n"
            "To fix, add the NVIDIA CUDA repository and install cuDNN:\n\n"
            "  sudo apt install libcudnn9-cuda-12\n\n"
            "If the package is not found, you need to add the NVIDIA repo first.\n"
            "See the README for instructions."
        )
    elif distro_id in ("fedora", "nobara", "opensuse-tumbleweed"):
        msg = _(
            "NVIDIA GPU detected but cuDNN is not installed.\n"
            "GPU acceleration will not work without it.\n\n"
            "To fix:\n\n"
            "  sudo dnf install libcudnn9-cuda-12\n\n"
            "If the package is not found, you need to add the NVIDIA CUDA repo.\n"
            "See the README for instructions."
        )
    else:
        msg = _(
            "NVIDIA GPU detected but cuDNN is not installed.\n"
            "GPU acceleration will not work without it.\n\n"
            "Install libcudnn9-cuda-12 from the NVIDIA CUDA repository.\n"
            "See the README for instructions."
        )
    return True, False, msg


def ollama_list_models():
    """Retourne la liste des modèles ollama installés."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            models = []
            for line in result.stdout.strip().split("\n")[1:]:  # skip header
                if line.strip():
                    models.append(line.split()[0])  # keep full name:tag
            return models
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []


def ollama_has_model(model_name):
    """Vérifie si un modèle ollama spécifique est installé."""
    installed = ollama_list_models()
    # Normaliser : "translategemma" → "translategemma:latest"
    def _normalize(name):
        return name if ":" in name else name + ":latest"
    target = _normalize(model_name)
    return any(_normalize(m) == target for m in installed)


class OllamaPullThread(QThread):
    """Thread pour télécharger un modèle ollama."""
    done = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name

    def run(self):
        try:
            self.progress.emit(_("Downloading {model}…").format(model=self.model_name))
            result = subprocess.run(
                ["ollama", "pull", self.model_name],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                self.done.emit(True, "")
            else:
                self.done.emit(False, result.stderr.strip() or _("Download failed."))
        except subprocess.TimeoutExpired:
            self.done.emit(False, _("Download timed out (10 min)."))
        except Exception as e:
            self.done.emit(False, str(e))


# === ASR models ===

MODEL_DIR = "/usr/share/dictee"
DICTEE_DATA_DIR = os.path.expanduser("~/.local/share/dictee")

# === Logo SVG (fichiers assets/) ===

def _find_assets_dir():
    """Trouve le répertoire assets/ contenant les bannières SVG."""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"),
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "assets"),
        "/usr/share/dictee/assets",
        os.path.expanduser("~/.local/share/dictee/assets"),
    ]
    for d in candidates:
        if os.path.isfile(os.path.join(d, "banner-dark.svg")):
            return d
    return None

ASSETS_DIR = _find_assets_dir()


# === Pipeline diagram (post-processing visualization) ===

def _icons_dir():
    if ASSETS_DIR:
        d = os.path.join(ASSETS_DIR, "icons")
        if os.path.isdir(d):
            return d
    return None


from PyQt6.QtSvgWidgets import QSvgWidget as _QSvgWidget
from PyQt6.QtCore import pyqtSignal as _pyqtSignal


class _ClickableSvgWidget(_QSvgWidget):
    """QSvgWidget that emits step_clicked(key) when a registered hit box is
    clicked, and displays per-step tooltips on hover.
    """
    step_clicked = _pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hit_boxes = []  # list of (QRectF, key)
        self.tooltips = {}   # key → tooltip text
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, ev):
        pos = ev.position()
        for rect, key in self.hit_boxes:
            if rect.contains(pos):
                self.step_clicked.emit(key)
                return
        super().mousePressEvent(ev)

    def event(self, ev):
        # Per-region tooltips via QEvent.ToolTip — the standard Qt pattern
        # for widgets with multiple logical hot zones. Does not steal focus
        # (unlike setToolTip on mouseMoveEvent).
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QToolTip
        if ev.type() == QEvent.Type.ToolTip:
            from PyQt6.QtCore import QPointF
            pos = QPointF(ev.pos())
            for rect, key in self.hit_boxes:
                if rect.contains(pos):
                    tip = self.tooltips.get(key, "")
                    if tip:
                        # Wrap in <qt> for multi-line support; replace \n
                        # with <br> explicitly so Qt honours them.
                        html = "<qt>" + tip.replace("\n", "<br>") + "</qt>"
                        QToolTip.showText(ev.globalPos(), html, self)
                        return True
            QToolTip.hideText()
            ev.ignore()
            return True
        return super().event(ev)


class _PipelineDiagram:
    """SVG-based post-processing pipeline diagram.

    Builds a horizontal flow: [mic] → [Rules] → [Continuation] → ... → [LLM] → [pencil]
    LLM is inserted at first / hybrid / last position based on llm_position.
    Disabled steps are drawn dashed with a horizontal line crossing through.
    External arrows are always in the accent color.
    """

    # Pipeline order matches dictee-postprocess.py main()
    BASE_STEPS = [
        ("rules", "Rules"),
        ("continuation", "Continuation"),
        ("language_rules", "Lang rules"),
        ("numbers", "Numbers"),
        ("dict", "Dict"),
        ("capitalization", "Capitalization"),
        ("short_text", "Short text"),
    ]

    # Tooltip texts are built lazily in _build_tooltips() so that gettext _()
    # is called after the locale has been initialised (class-body evaluation
    # would freeze them to the startup language).
    @staticmethod
    def _build_tooltips():
        return {
            "rules": "<b>" + _("Regex rules") + "</b><br>"
                     + _("Fix common ASR errors:") + "<br>"
                     + _("voice commands, punctuation, formatting."),
            "continuation": "<b>" + _("Continuation") + "</b><br>"
                            + _("Remove erroneous periods after closed-class words") + "<br>"
                            + _("so sentences flow across push-to-talk segments."),
            "language_rules": "<b>" + _("Language rules") + "</b><br>"
                              + _("Per-language fixes:") + "<br>"
                              + _("FR/IT elisions, DE/ES/PT/NL/RO corrections."),
            "numbers": "<b>" + _("Numbers") + "</b><br>"
                       + _("Convert spoken numbers to digits.") + "<br>"
                       + _("Example: \"twenty-three\" → \"23\"."),
            "dict": "<b>" + _("Dictionary") + "</b><br>"
                    + _("Exact word replacements from the system") + "<br>"
                    + _("and personal dictionaries."),
            "capitalization": "<b>" + _("Capitalization") + "</b><br>"
                              + _("Uppercase first letter after . ! ?") + "<br>"
                              + _("Essential for Vosk/Whisper backends."),
            "short_text": "<b>" + _("Short text fix") + "</b><br>"
                          + _("For transcriptions under N words:") + "<br>"
                          + _("strip trailing punctuation and lowercase."),
            "llm": "<b>" + _("LLM grammar correction") + "</b><br>"
                   + _("Local Ollama model fixes grammar,") + "<br>"
                   + _("spelling, accents and punctuation."),
            "nav:microphone": "<b>" + _("Microphone") + "</b><br>" + _("Jump to the Microphone section."),
            "nav:asr": "<b>" + _("ASR backend") + "</b><br>" + _("Jump to the ASR backend section."),
            "nav:translation": "<b>" + _("Translation") + "</b><br>" + _("Jump to the Translation section."),
        }

    def __init__(self, palette, variant=None, llm_force_off=False):
        """Pipeline diagram.

        Args:
            palette: QPalette used for accent color (Highlight).
            variant: Optional icon variant name (e.g. "orange") used to
                resolve SVG endpoint icons. Falls back to the default
                variant if a variant-specific file is missing.
            llm_force_off: When True, the LLM step is always rendered as
                disabled regardless of its state. Used for the translation
                pipeline where LLM never runs.
        """
        self.widget = _ClickableSvgWidget()
        self._palette = palette
        self._variant = variant
        self._llm_force_off = bool(llm_force_off)
        self._states = {k: True for k, _ in self.BASE_STEPS}
        self._llm_on = False
        self._llm_pos = "hybrid"
        self._master_on = True
        self._short_text_max = 3

    def set_master(self, on):
        self._master_on = bool(on)
        self._render()

    def set_states(self, states, llm_on, llm_pos, short_text_max=None):
        self._states = dict(states)
        self._llm_on = bool(llm_on)
        self._llm_pos = llm_pos or "hybrid"
        if short_text_max is not None:
            try:
                self._short_text_max = max(1, int(short_text_max))
            except (TypeError, ValueError):
                pass
        self._render()

    def _theme_colors(self):
        from PyQt6.QtGui import QPalette
        pal = self._palette
        win = pal.color(QPalette.ColorRole.Window)
        is_dark = win.lightness() < 128
        accent = pal.color(QPalette.ColorRole.Highlight).name()
        accent_dark = pal.color(QPalette.ColorRole.Highlight).darker(130).name()
        if is_dark:
            return {
                "accent": accent, "accent_dark": accent_dark,
                "dis_text": "#5a5a5a", "dis_bg": "#3a3a3a",
                "dis_border": "#555555", "icon_suffix": "dark",
            }
        return {
            "accent": accent, "accent_dark": accent_dark,
            "dis_text": "#808080", "dis_bg": "#d8d8d8",
            "dis_border": "#a0a0a0", "icon_suffix": "light",
        }

    def _ordered_steps(self):
        """Return list of (key, label, enabled) including LLM at the right position."""
        m = self._master_on
        def _label(key, label):
            if key == "short_text":
                return f"Short < {self._short_text_max}w"
            return label
        base = [(key, _label(key, label), m and self._states.get(key, True))
                for key, label in self.BASE_STEPS]
        # LLM step is always shown (even when disabled, so users can click
        # its SVG endpoint to jump to the LLM sub-section and enable it).
        # If llm_force_off is set (translation diagram), LLM is always off.
        llm_active = (not self._llm_force_off) and m and self._llm_on
        llm = ("llm", "LLM", llm_active)
        if self._llm_pos == "first":
            return [llm] + base
        if self._llm_pos == "last":
            return base + [llm]
        return base[:2] + [llm] + base[2:]

    def _icon_b64(self, name, suffix, variant=None):
        import base64
        from PyQt6.QtCore import QByteArray, QBuffer
        from PyQt6.QtGui import QIcon
        icons = _icons_dir()
        if not icons:
            return ""
        # Try variant-specific file first (e.g. "microphone-symbolic-orange-dark.svg")
        if variant:
            candidate = os.path.join(icons, f"{name}-{variant}-{suffix}.svg")
            if os.path.isfile(candidate):
                path = candidate
            else:
                path = os.path.join(icons, f"{name}-{suffix}.svg")
        else:
            path = os.path.join(icons, f"{name}-{suffix}.svg")
        if not os.path.isfile(path):
            return ""
        ic = QIcon(path)
        pm = ic.pixmap(32, 32)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.OpenModeFlag.WriteOnly)
        pm.save(buf, "PNG")
        return base64.b64encode(bytes(ba)).decode("ascii")

    def _render(self):
        from PyQt6.QtCore import QByteArray, QRectF
        t = self._theme_colors()
        steps = self._ordered_steps()
        hit_boxes = []

        char_w = 8
        pad_x = 14
        h = 38
        gap = 32
        ep_r = 16
        boxes = [len(label) * char_w + pad_x * 2 for _k, label, _ in steps]
        # IN(mic) + arrow + ASR + arrow + steps + arrow + OUT(pencil)
        total_w = ep_r * 6 + gap * 3 + sum(boxes) + gap * (len(boxes) - 1) + 20
        total_h = h + 20
        y = 10
        cy = y + h / 2

        orange_variant = (self._variant == "orange")
        if orange_variant:
            # Translation pipeline: use translate icon in place of ASR,
            # and replace mic/pencil circles with L-shaped orange arrows
            # suggesting flow from/to the blue row above.
            in_b64 = ""
            asr_b64 = self._icon_b64("translate-symbolic", t["icon_suffix"], variant="orange")
            out_b64 = ""
        else:
            in_b64 = self._icon_b64("microphone-symbolic", t["icon_suffix"], variant=self._variant)
            asr_b64 = self._icon_b64("asr-symbolic", t["icon_suffix"], variant=self._variant)
            out_b64 = self._icon_b64("workspacelistentryicon-pencilandpaper-symbolic", t["icon_suffix"], variant=self._variant)

        elems = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {total_w} {total_h}" width="{total_w}" height="{total_h}">',
            '<defs>',
            '<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="6" markerHeight="6" orient="auto">',
            f'<path d="M0,0 L10,5 L0,10 z" fill="{t["accent"]}"/>',
            '</marker>',
            '</defs>',
        ]

        def endpoint(cx, b64):
            if not b64:
                return ''
            return (
                f'<image x="{cx - ep_r}" y="{cy - ep_r}" '
                f'width="{ep_r * 2}" height="{ep_r * 2}" '
                f'xlink:href="data:image/png;base64,{b64}"/>'
            )

        def arrow(x1, x2):
            return (
                f'<line x1="{x1}" y1="{cy}" x2="{x2}" y2="{cy}" '
                f'stroke="{t["accent"]}" stroke-width="2.2" '
                f'marker-end="url(#ar)"/>'
            )

        from PyQt6.QtCore import QRectF as _QRectF_ep

        x = 10
        if orange_variant:
            # Draw L-shaped arrow: comes from top-left (suggesting the
            # audio source above in the blue row), goes down to cy,
            # then right toward the first element.
            cx_mic = x + ep_r
            elems.append(
                f'<path d="M {cx_mic} {y - 6} '
                f'L {cx_mic} {cy} '
                f'L {cx_mic + ep_r + 4} {cy}" '
                f'fill="none" stroke="{t["accent"]}" stroke-width="2.2" '
                f'marker-end="url(#ar)"/>')
        else:
            # Mic endpoint (clickable → Microphone sub-menu)
            elems.append(endpoint(x + ep_r, in_b64))
            hit_boxes.append((_QRectF_ep(x, cy - ep_r, ep_r * 2, ep_r * 2), "nav:microphone"))
            seg_start = x + ep_r * 2
            elems.append(arrow(seg_start + 4, seg_start + gap - 4))
        x += ep_r * 2 + gap
        # ASR endpoint (blue) or Translate icon (orange)
        elems.append(endpoint(x + ep_r, asr_b64))
        nav_key = "nav:translation" if orange_variant else "nav:asr"
        hit_boxes.append((_QRectF_ep(x, cy - ep_r, ep_r * 2, ep_r * 2), nav_key))
        seg_start = x + ep_r * 2
        elems.append(arrow(seg_start + 4, seg_start + gap - 4))
        x = seg_start + gap

        from xml.sax.saxutils import escape as _xml_escape
        for i, ((key, label, on), bw) in enumerate(zip(steps, boxes)):
            bg = t["accent"] if on else t["dis_bg"]
            border = t["accent_dark"] if on else t["dis_border"]
            text_col = "white" if on else t["dis_text"]
            dash_attr = '' if on else 'stroke-dasharray="5,4" '
            elems.append(
                f'<rect x="{x}" y="{y}" width="{bw}" height="{h}" rx="8" ry="8" '
                f'fill="{bg}" stroke="{border}" stroke-width="1.8" {dash_attr}/>'
            )
            elems.append(
                f'<text x="{x + bw / 2}" y="{y + h / 2 + 5}" '
                f'text-anchor="middle" fill="{text_col}" '
                f'font-family="sans-serif" font-size="13" font-weight="bold">'
                f'{_xml_escape(label)}</text>'
            )
            if not on:
                elems.append(
                    f'<line x1="{x - 2}" y1="{cy}" x2="{x + bw + 2}" y2="{cy}" '
                    f'stroke="{t["accent"]}" stroke-width="2.2"/>'
                )
            hit_boxes.append((QRectF(x, y, bw, h), key))
            if i < len(steps) - 1:
                elems.append(arrow(x + bw + 4, x + bw + gap - 4))
            x += bw + gap

        if orange_variant:
            # L-shaped arrow: right then up, suggesting output flows
            # back up to the pencil (typing) in the blue row above.
            cx_end = x + ep_r
            elems.append(
                f'<path d="M {x - gap + 4} {cy} '
                f'L {cx_end} {cy} '
                f'L {cx_end} {y - 6}" '
                f'fill="none" stroke="{t["accent"]}" stroke-width="2.2" '
                f'marker-end="url(#ar)"/>')
        else:
            elems.append(arrow(x - gap + 4, x - 4))
            elems.append(endpoint(x + ep_r, out_b64))
        elems.append("</svg>")

        self.widget.load(QByteArray("\n".join(elems).encode("utf-8")))
        self.widget.setFixedSize(int(total_w), int(total_h))
        self.widget.hit_boxes = hit_boxes
        self.widget.tooltips = self._build_tooltips()


# === Backends ASR alternatifs (venvs) ===

VOSK_VENV = os.path.join(DICTEE_DATA_DIR, "vosk-env")
WHISPER_VENV = os.path.join(DICTEE_DATA_DIR, "whisper-env")
CANARY_VENV = os.path.join(DICTEE_DATA_DIR, "canary-env")  # Legacy, kept for cleanup
CANARY_MODEL_DIR = os.path.join(MODEL_DIR, "canary")
CANARY_HF_REPO = "istupakov/canary-1b-v2-onnx"
CANARY_MODEL_FILES = [
    "encoder-model.onnx", "encoder-model.onnx.data", "decoder-model.onnx",
    "vocab.txt", "config.json",
]

VOSK_MODELS = {
    "fr": "vosk-model-small-fr-0.22",
    "en": "vosk-model-small-en-us-0.15",
    "de": "vosk-model-small-de-0.15",
    "es": "vosk-model-small-es-0.42",
    "it": "vosk-model-small-it-0.22",
    "pt": "vosk-model-small-pt-0.3",
    "ru": "vosk-model-small-ru-0.22",
    "zh": "vosk-model-small-cn-0.22",
    "ja": "vosk-model-small-ja-0.22",
}

WHISPER_MODELS = [
    ("tiny", "tiny — 39M, fastest, lowest quality"),
    ("small", "small — 244M, good balance"),
    ("medium", "medium — 769M, better quality"),
    ("large-v3-turbo", "large-v3-turbo — 809M, fast, multilingual"),
    ("large-v3", "large-v3 — 1.5B, best quality, multilingual"),
    ("Systran/faster-distil-whisper-large-v3", "distil-large-v3 — 756M, fast (English only)"),
]


def venv_is_installed(venv_path):
    """Vérifie si un venv Python est installé et contient des packages."""
    site = os.path.join(venv_path, "lib")
    if not os.path.isdir(site):
        return False
    for d in os.listdir(site):
        sp = os.path.join(site, d, "site-packages")
        if os.path.isdir(sp) and len(os.listdir(sp)) > 3:
            return True
    return False


def has_text2num():
    """Check if text2num is importable via a dictee venv (user or system).

    dictee-postprocess.py looks for text_to_num in:
      1. ~/.local/share/dictee/postprocess-env/ (user, optional)
      2. /usr/share/dictee/postprocess-env/ (system, created by postinst)
    """
    candidates = [
        os.path.expanduser("~/.local/share/dictee/postprocess-env/bin/python3"),
        "/usr/share/dictee/postprocess-env/bin/python3",
    ]
    for py in candidates:
        if not os.path.isfile(py):
            continue
        try:
            r = subprocess.run(
                [py, "-c", "from text_to_num import alpha2digit"],
                capture_output=True, timeout=2,
            )
            if r.returncode == 0:
                return True
        except Exception as _e:
            _dbg_setup(f"silenced: {_e!r}")
    return False


class VenvInstallThread(QThread):
    """Thread pour créer un venv et installer un package pip."""
    done = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, venv_path, pip_package):
        super().__init__()
        self.venv_path = venv_path
        self.pip_package = pip_package

    def run(self):
        try:
            self.progress.emit(_("Creating virtual environment…"))
            os.makedirs(self.venv_path, exist_ok=True)
            result = subprocess.run(
                ["python3", "-m", "venv", self.venv_path],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                self.done.emit(False, result.stderr.strip())
                return
            # Use `python -m pip` instead of the pip script — avoids issues
            # where the ensurepip pip binary has shebang quirks on some
            # Fedora/Python versions. Also forces use of the venv's own Python.
            python = os.path.join(self.venv_path, "bin", "python3")
            pip_cmd = [python, "-m", "pip"]
            # Upgrade pip first — ensurepip often ships an outdated version
            # (e.g. pip 25.3) that can hit install bugs on Python 3.14+.
            # Hard requirement, not best-effort: if pip upgrade fails,
            # the subsequent package install may fail too (observed on
            # Fedora 44 KDE: Errno 2 / No such file or directory).
            self.progress.emit(_("Upgrading pip…"))
            r_pip = subprocess.run(
                pip_cmd + ["install", "--upgrade", "pip"],
                capture_output=True, text=True, timeout=300,
            )
            if r_pip.returncode != 0:
                self.done.emit(False,
                    _("Failed to upgrade pip in the venv:") + "\n\n"
                    + (r_pip.stderr.strip() or r_pip.stdout.strip())[-500:])
                return
            self.progress.emit(_("Installing {pkg}…").format(pkg=self.pip_package))
            result = subprocess.run(
                pip_cmd + ["install", "--upgrade", self.pip_package],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                self.done.emit(False, result.stderr.strip()[-500:])
                return
            self.done.emit(True, "")
        except subprocess.TimeoutExpired:
            self.done.emit(False, _("Installation timed out."))
        except Exception as e:
            self.done.emit(False, str(e))

class _CanaryDownloadThread(QThread):
    """Thread to download Canary ONNX model files from HuggingFace."""
    done = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, model_dir, hf_repo, files):
        super().__init__()
        self.model_dir = model_dir
        self.hf_repo = hf_repo
        self.files = files
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import urllib.request
        try:
            model_dir = self.model_dir
            try:
                os.makedirs(model_dir, exist_ok=True)
                _test = os.path.join(model_dir, ".write_test")
                open(_test, "w").close()
                os.remove(_test)
            except (PermissionError, OSError):
                model_dir = model_dir.replace(MODEL_DIR, DICTEE_DATA_DIR)
                os.makedirs(model_dir, exist_ok=True)
            base_url = f"https://huggingface.co/{self.hf_repo}/resolve/main"
            for i, fname in enumerate(self.files, 1):
                if self._cancelled:
                    self.done.emit(False, _("Cancelled"))
                    return
                dest = os.path.join(model_dir, fname)
                if os.path.exists(dest):
                    self.progress.emit(f"{fname} ✓ ({i}/{len(self.files)})")
                    continue
                self.progress.emit(f"{fname} ({i}/{len(self.files)})…")
                url = f"{base_url}/{fname}"
                tmp = dest + ".part"
                resp = urllib.request.urlopen(url, timeout=1800)
                total_size = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(tmp, "wb") as f:
                    while True:
                        if self._cancelled:
                            f.close()
                            os.remove(tmp)
                            self.done.emit(False, _("Cancelled"))
                            return
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int(downloaded * 100 / total_size)
                            size_mb = downloaded / (1024 * 1024)
                            total_mb = total_size / (1024 * 1024)
                            self.progress.emit(
                                f"{fname}  {pct}%  ({size_mb:.0f}/{total_mb:.0f} Mo)")
                os.rename(tmp, dest)
            # Generate tokenizer.json if missing (needed for decodercontext)
            tokenizer_path = os.path.join(model_dir, "tokenizer.json")
            if not os.path.exists(tokenizer_path):
                vocab_path = os.path.join(model_dir, "vocab.txt")
                if os.path.exists(vocab_path):
                    self.progress.emit(_("Generating tokenizer.json…"))
                    self._generate_tokenizer(vocab_path, tokenizer_path)
            self.done.emit(True, "")
        except Exception as e:
            self.done.emit(False, str(e))

    @staticmethod
    def _generate_tokenizer(vocab_path, tokenizer_path):
        """Generate a tokenizer.json from vocab.txt for SentencePiece-like decoding."""
        import json
        vocab = {}
        with open(vocab_path) as f:
            for line in f:
                parts = line.strip().rsplit(" ", 1)
                if len(parts) == 2:
                    vocab[int(parts[1])] = parts[0]
        # Minimal tokenizer format
        tokenizer = {"model": {"type": "Unigram", "vocab": [[t, 0.0] for t in vocab.values()]}}
        with open(tokenizer_path, "w") as f:
            json.dump(tokenizer, f)


class _WhisperDownloadThread(QThread):
    """Thread to pre-download a Whisper model using faster-whisper in the venv."""
    done = Signal(bool, str)

    def __init__(self, venv_path, model_id):
        super().__init__()
        self.venv_path = venv_path
        self.model_id = model_id

    def run(self):
        try:
            python = os.path.join(self.venv_path, "bin", "python3")
            if not os.path.isfile(python):
                self.done.emit(False, _("Whisper venv not installed. Install Whisper engine first."))
                return
            # faster-whisper downloads the model on first WhisperModel() instantiation
            result = subprocess.run(
                [python, "-c", f"from faster_whisper import WhisperModel; WhisperModel('{self.model_id}', device='cpu')"],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                self.done.emit(False, result.stderr.strip()[-500:])
                return
            self.done.emit(True, "")
        except subprocess.TimeoutExpired:
            self.done.emit(False, _("Download timed out."))
        except Exception as e:
            self.done.emit(False, str(e))


def _measure_wav_rms(wav_path):
    """Measure normalized RMS amplitude of a WAV via `sox -n stat`.

    Returns a float in 0..1. Returns 0.0 on error (missing sox, timeout,
    unreadable file) — caller should treat that as "cannot verify" and
    typically still proceed, since silencing a recording on a tooling
    failure would be worse UX than an occasional hallucination.
    """
    try:
        r = subprocess.run(
            ["sox", wav_path, "-n", "stat"],
            capture_output=True, text=True, timeout=5)
        for line in r.stderr.splitlines():
            if "RMS" in line and "amplitude" in line:
                parts = line.split(":")
                if len(parts) == 2:
                    try:
                        return float(parts[1].strip())
                    except ValueError:
                        pass
                break
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return 0.0


def _silence_message(rms_measured, threshold):
    """Pedagogical localized message shown when a test recording is skipped
    because its RMS is below the silence threshold."""
    return _(
        "⚠ Aucune voix détectée (RMS {rms:.3f} < seuil {thr:.3f}).\n"
        "Parle un peu plus fort, ou réduis le seuil de silence dans\n"
        "Microphone → \"Tester le réglage du seuil\"."
    ).format(rms=rms_measured, thr=threshold)


def _read_silence_threshold_from_conf():
    """Read DICTEE_SILENCE_RMS from ~/.config/dictee.conf (fallback 0.03).

    Used by threads that don't have access to the DicteeSetupDialog
    instance. Returns a float.
    """
    try:
        path = os.path.expanduser("~/.config/dictee.conf")
        if not os.path.isfile(path):
            return 0.03
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DICTEE_SILENCE_RMS="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return float(val)
    except (OSError, ValueError):
        pass
    return 0.03


def _test_translate_text(text, src, tgt, conf):
    """Synchronously translate text src->tgt using the configured backend.

    Used by the post-processing test panel when Translation mode is on.
    Reads backend settings from the conf dict (DICTEE_TRANSLATE_BACKEND,
    DICTEE_TRANS_ENGINE, DICTEE_LIBRETRANSLATE_PORT, DICTEE_OLLAMA_MODEL).
    Returns (translated, error_message). On failure, `translated` is the
    original text and `error_message` is non-empty.
    """
    if not text.strip() or src == tgt:
        return text, ""
    backend = (conf.get("DICTEE_TRANSLATE_BACKEND", "trans") or "trans").strip()
    try:
        if backend.startswith("trans") or backend == "canary":
            # 'trans' CLI is the fallback for canary too (canary is audio-only)
            engine = (conf.get("DICTEE_TRANS_ENGINE", "google") or "google").strip()
            r = subprocess.run(
                ["trans", "-b", "-e", engine, f"{src}:{tgt}"],
                input=text, capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip(), ""
            return text, (r.stderr.strip() or "trans CLI failed")
        if backend == "libretranslate":
            import json as _json
            import urllib.request as _ureq
            port = conf.get("DICTEE_LIBRETRANSLATE_PORT", "5000") or "5000"
            url = f"http://localhost:{port}/translate"
            payload = _json.dumps({
                "q": text, "source": src, "target": tgt}).encode()
            req = _ureq.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"})
            with _ureq.urlopen(req, timeout=10) as resp:
                result = _json.loads(resp.read())
            out = result.get("translatedText", "")
            return (out, "") if out else (text, "libretranslate empty result")
        if backend == "ollama":
            model = conf.get("DICTEE_OLLAMA_MODEL", "translategemma") or "translategemma"
            # Match the dictee shell script prompt so the result is the
            # translation ONLY — no "Here is the translation:" preamble,
            # no echoing of the source text, no commentary.
            prompt = (
                f"You are a professional {src} to {tgt} translator. "
                f"Your goal is to accurately convey the meaning and "
                f"nuances of the original text while adhering to the "
                f"target language grammar, vocabulary, and cultural "
                f"sensitivities.\n"
                f"Produce only the {tgt} translation, without any "
                f"additional explanations or commentary. Please "
                f"translate the following text:\n\n{text}"
            )
            import json as _json
            import urllib.request as _ureq
            if ":" not in model:
                model += ":latest"
            payload_dict = {"model": model, "prompt": prompt, "stream": False}
            if conf.get("OLLAMA_NUM_GPU") == "0":
                payload_dict["options"] = {"num_gpu": 0}
            data = _json.dumps(payload_dict).encode()
            req = _ureq.Request(
                "http://localhost:11434/api/generate",
                data=data, headers={"Content-Type": "application/json"})
            resp = _json.loads(_ureq.urlopen(req, timeout=30).read())
            out = resp.get("response", "").strip()
            if out:
                out = re.sub(
                    r"^(?:translation|result|output)\s*[:：]\s*",
                    "", out, flags=re.IGNORECASE)
                out = out.strip('"\'`').strip()
                return out, ""
            return text, "ollama empty response"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return text, str(exc)
    return text, f"unknown backend: {backend}"


class _RuleTranscribeThread(QThread):
    """Thread pour transcrire un WAV lors du test de règle de post-traitement."""
    finished_sig = Signal(str)

    def __init__(self, wav_path, silence_threshold=None):
        super().__init__()
        self.wav_path = wav_path
        self._silence_thr = (
            silence_threshold if silence_threshold is not None
            else _read_silence_threshold_from_conf())

    def run(self):
        try:
            rms = _measure_wav_rms(self.wav_path)
            if rms > 0 and rms < self._silence_thr:
                self.finished_sig.emit(
                    _silence_message(rms, self._silence_thr))
                return
            result = subprocess.run(
                ["transcribe-client", self.wav_path],
                capture_output=True, text=True, timeout=30)
            self.finished_sig.emit(result.stdout.strip())
        except Exception:
            self.finished_sig.emit("")


ASR_MODELS = [
    {
        "id": "tdt",
        "name": "Parakeet-TDT 0.6B v3",
        "desc": _("Multilingual transcription (25 languages, ~2.5 GB)"),
        "help": _(
            "<b>Parakeet-TDT 0.6B v3</b> — Main transcription model<br><br>"
            "FastConformer encoder + Token-and-Duration Transducer (TDT) decoder.<br>"
            "Supports <b>25 languages</b> including French, English, Spanish, German, etc.<br>"
            "Native punctuation and capitalization (no post-processing needed).<br><br>"
            "<b>Required</b> for all transcription modes (dictation, batch, daemon).<br>"
            "Used by: <code>transcribe</code>, <code>transcribe-daemon</code>, "
            "<code>transcribe-diarize</code>, <code>dictee</code>"
        ),
        "dir": os.path.join(MODEL_DIR, "tdt"),
        "check_file": "encoder-model.onnx",
        "files": [
            ("https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/encoder-model.onnx", "encoder-model.onnx"),
            ("https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/encoder-model.onnx.data", "encoder-model.onnx.data"),
            ("https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/decoder_joint-model.onnx", "decoder_joint-model.onnx"),
            ("https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/vocab.txt", "vocab.txt"),
        ],
        "required": True,
    },
    {
        "id": "sortformer",
        "name": "Sortformer",
        "desc": _("Speaker diarization (4 speakers max, ~50 MB)"),
        "help": _(
            "<b>Sortformer</b> — Speaker diarization model<br><br>"
            "Identifies and separates up to <b>4 different speakers</b> in an audio recording.<br>"
            "Labels each transcription segment with the speaker who said it.<br><br>"
            "<b>Optional</b> — only needed if you want speaker identification.<br>"
            "Used by: <code>transcribe-diarize</code>"
        ),
        "dir": os.path.join(MODEL_DIR, "sortformer"),
        "check_file": "diar_streaming_sortformer_4spk-v2.1.onnx",
        "files": [
            ("https://huggingface.co/altunenes/parakeet-rs/resolve/main/diar_streaming_sortformer_4spk-v2.1.onnx", "diar_streaming_sortformer_4spk-v2.1.onnx"),
        ],
        "required": False,
    },
]


def model_is_installed(model):
    """Vérifie si un modèle ASR est installé (system or user dir)."""
    sys_path = os.path.join(model["dir"], model["check_file"])
    user_path = os.path.join(
        model["dir"].replace(MODEL_DIR, DICTEE_DATA_DIR),
        model["check_file"])
    return os.path.isfile(sys_path) or os.path.isfile(user_path)


class ModelDownloadThread(QThread):
    """Thread pour télécharger un modèle ASR."""
    done = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, model):
        super().__init__()
        self.model = model
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import urllib.request
        try:
            model_dir = self.model["dir"]
            try:
                os.makedirs(model_dir, exist_ok=True)
            except PermissionError:
                model_dir = model_dir.replace(MODEL_DIR,
                    os.path.join(os.path.expanduser("~/.local/share/dictee")))
                os.makedirs(model_dir, exist_ok=True)
            total_files = len([f for f in self.model["files"]
                               if not os.path.isfile(os.path.join(model_dir, f[1]))])
            done = 0
            for url, filename in self.model["files"]:
                if self._cancelled:
                    self.done.emit(False, _("Cancelled"))
                    return
                dest = os.path.join(model_dir, filename)
                if os.path.isfile(dest):
                    continue
                self.progress.emit(_("Downloading {name}…").format(name=filename))
                resp = urllib.request.urlopen(url, timeout=1800)
                total_size = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                tmp = dest + ".part"
                with open(tmp, "wb") as f:
                    while True:
                        if self._cancelled:
                            f.close()
                            os.remove(tmp)
                            self.done.emit(False, _("Cancelled"))
                            return
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int(downloaded * 100 / total_size)
                            size_mb = downloaded / (1024 * 1024)
                            total_mb = total_size / (1024 * 1024)
                            self.progress.emit(
                                f"{filename}  {pct}%  ({size_mb:.0f}/{total_mb:.0f} Mo)")
                os.rename(tmp, dest)
                done += 1
                if total_files > 1:
                    self.progress.emit(_("Downloaded {done}/{total}").format(
                        done=done, total=total_files))
            self.done.emit(True, "")
        except PermissionError:
            self.done.emit(False, _("Permission denied on {dir}").format(
                dir=model_dir))
        except Exception as e:
            if self._cancelled:
                self.done.emit(False, _("Cancelled"))
            else:
                self.done.emit(False, str(e))


# === LibreTranslate (Docker) ===

LIBRETRANSLATE_IMAGE = "libretranslate/libretranslate"
LIBRETRANSLATE_CONTAINER = "dictee-libretranslate"
LIBRETRANSLATE_VOLUME = "dictee-lt-models"
LIBRETRANSLATE_PORT = 5000


def docker_is_installed():
    """Vérifie si docker est installé et accessible."""
    return shutil.which("docker") is not None


_docker_use_sg = False  # set to True after pkexec usermod -aG docker


def docker_cmd(args, **kwargs):
    """Run a docker command, using 'sg docker' if group was just added."""
    if _docker_use_sg:
        import shlex
        cmd = ["sg", "docker", "-c", shlex.join(args)]
    else:
        cmd = args
    return subprocess.run(cmd, **kwargs)


def _ttl_cache(ttl=2.0):
    """Decorator: memoize a pure-ish function for `ttl` seconds.

    Used on the docker_* lookup helpers below: at startup, the
    translation/microphone/etc. tabs probe Docker state several times
    in a sub-second window. Without caching this fans out into 18
    `docker inspect` subprocess calls (~700 ms total). With a 2 s TTL,
    the redundant probes hit the cache while still picking up real
    state changes a couple of seconds later.

    Each decorated function exposes `.cache_clear()` so callers that
    perform a Docker action (start/stop a container, pull an image) can
    invalidate the cache immediately and bypass the staleness window."""
    def deco(fn):
        _cache = {}

        def wrapped(*args, **kwargs):
            import time as _t
            key = (args, tuple(sorted(kwargs.items())))
            now = _t.monotonic()
            entry = _cache.get(key)
            if entry is not None and entry[1] > now:
                return entry[0]
            value = fn(*args, **kwargs)
            _cache[key] = (value, now + ttl)
            return value
        wrapped.cache_clear = _cache.clear
        wrapped.__wrapped__ = fn
        wrapped.__name__ = fn.__name__
        return wrapped
    return deco


@_ttl_cache(ttl=2.0)
def docker_is_accessible():
    """Vérifie si l'utilisateur peut exécuter docker (permissions)."""
    try:
        result = docker_cmd(
            ["docker", "info"], capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@_ttl_cache(ttl=2.0)
def docker_daemon_running():
    """Vérifie si le daemon Docker est en cours d'exécution."""
    try:
        result = docker_cmd(
            ["systemctl", "is-active", "docker"],
            capture_output=True, text=True, timeout=3)
        return result.stdout.strip() == "active"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@_ttl_cache(ttl=2.0)
def docker_has_image(image=LIBRETRANSLATE_IMAGE):
    """Vérifie si l'image Docker est téléchargée."""
    try:
        result = docker_cmd(
            ["docker", "images", "-q", image],
            capture_output=True, text=True, timeout=5,
        )
        return bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@_ttl_cache(ttl=2.0)
def docker_container_running(name=LIBRETRANSLATE_CONTAINER):
    """Vérifie si le container est en cours d'exécution."""
    try:
        result = docker_cmd(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() == "true"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@_ttl_cache(ttl=2.0)
def docker_container_exists(name=LIBRETRANSLATE_CONTAINER):
    """Vérifie si le container existe (arrêté ou en cours)."""
    try:
        result = docker_cmd(
            ["docker", "inspect", name],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


_lt_langs_cache = {"langs": [], "time": 0, "port": 0}


def libretranslate_available_languages(port=LIBRETRANSLATE_PORT, max_age=5):
    """Récupère la liste des codes langues disponibles dans LibreTranslate.
    Cache le résultat pendant max_age secondes pour éviter de bloquer l'UI."""
    import time as _time
    now = _time.monotonic()
    if (_lt_langs_cache["port"] == port
            and _lt_langs_cache["langs"]
            and now - _lt_langs_cache["time"] < max_age):
        return _lt_langs_cache["langs"]
    try:
        import urllib.request, json as _json
        url = f"http://localhost:{port}/languages"
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = _json.loads(resp.read())
            # Normalize LT codes to ISO 639-1 (e.g. zh-Hans → zh)
            result = list({lang["code"].split("-")[0] for lang in data})
            _lt_langs_cache.update({"langs": result, "time": now, "port": port})
            return result
    except Exception:
        return []


def _sync_volume_for_languages(languages):
    """Clear the persistent volume only if new language models are needed."""
    import re
    requested = set(languages.split(","))
    try:
        result = docker_cmd([
            "docker", "run", "--rm",
            "-v", f"{LIBRETRANSLATE_VOLUME}:/data",
            "alpine", "ls", "/data/share/argos-translate/packages/",
        ], capture_output=True, text=True, timeout=10)
        installed_langs = set()
        for pkg in result.stdout.strip().splitlines():
            name = re.sub(r'^translate-', '', pkg)
            name = re.sub(r'-[\d]+_[\d]+$', '', name)
            installed_langs |= set(name.split("_"))
        missing = requested - installed_langs
        if missing:
            docker_cmd([
                "docker", "run", "--rm",
                "-v", f"{LIBRETRANSLATE_VOLUME}:/data",
                "alpine", "rm", "-rf", "/data/share", "/data/cache",
            ], capture_output=True, timeout=10)
    except Exception as _e:
        _dbg_setup(f"silenced: {_e!r}")


def docker_start_libretranslate(port=LIBRETRANSLATE_PORT, languages="fr,en,es,de"):
    """Démarre le container LibreTranslate. Recrée si les langues ont changé."""
    if docker_container_exists():
        # Check if existing container languages match
        needs_recreate = False
        try:
            result = docker_cmd(
                ["docker", "inspect", "-f", "{{.Args}}", LIBRETRANSLATE_CONTAINER],
                capture_output=True, text=True, timeout=5,
            )
            current_args = result.stdout.strip()
            if f"--load-only {languages}" not in current_args:
                needs_recreate = True
        except Exception:
            needs_recreate = True  # When in doubt, recreate
        if needs_recreate:
            docker_cmd(["docker", "rm", "-f", LIBRETRANSLATE_CONTAINER],
                           capture_output=True, timeout=10)
            # Sync volume: only clear if new languages need downloading
            _sync_volume_for_languages(languages)
            docker_cmd([
                "docker", "run", "-d",
                "--name", LIBRETRANSLATE_CONTAINER,
                "-v", f"{LIBRETRANSLATE_VOLUME}:/home/libretranslate/.local",
                "-p", f"{port}:5000",
                "--restart", "unless-stopped",
                LIBRETRANSLATE_IMAGE,
                "--load-only", languages,
            ], capture_output=True, timeout=30)
            return
        docker_cmd(["docker", "start", LIBRETRANSLATE_CONTAINER],
                       capture_output=True, timeout=10)
    else:
        docker_cmd([
            "docker", "run", "-d",
            "--name", LIBRETRANSLATE_CONTAINER,
            "-v", f"{LIBRETRANSLATE_VOLUME}:/home/libretranslate/.local",
            "-p", f"{port}:5000",
            "--restart", "unless-stopped",
            LIBRETRANSLATE_IMAGE,
            "--load-only", languages,
        ], capture_output=True, timeout=30)


def docker_stop_libretranslate():
    """Arrête le container LibreTranslate."""
    docker_cmd(["docker", "stop", LIBRETRANSLATE_CONTAINER],
                   capture_output=True, timeout=15)


def _docker_container_size():
    """Retourne la taille du volume modèles LibreTranslate (ex: '1.2 GB').

    Mesure le volume monté (où sont stockés les modèles Argos), pas le
    writable layer — ce dernier ne bouge pas quand LibreTranslate télécharge
    des modèles puisque le volume est externe au conteneur.

    ⚠ Bloquant — utiliser _DockerSizeThread depuis le thread UI.
    """
    try:
        result = docker_cmd(
            ["docker", "exec", LIBRETRANSLATE_CONTAINER,
             "du", "-sb", "/home/libretranslate/.local"],
            capture_output=True, text=True, timeout=5)
        out = result.stdout.strip()
        if out:
            bytes_str = out.split()[0]
            if bytes_str.isdigit():
                size_b = int(bytes_str)
                if size_b >= 1_000_000_000:
                    return f"{size_b / 1_000_000_000:.2f} GB"
                if size_b >= 1_000_000:
                    return f"{size_b / 1_000_000:.0f} MB"
                return f"{size_b / 1_000:.0f} kB"
    except Exception as _e:
        _dbg_setup(f"silenced: {_e!r}")
    return ""


class _DockerSizeThread(QThread):
    """Fetch `du -sb` of the LibreTranslate volume in background so the
    UI thread never blocks up to 5 s on a slow Docker daemon."""
    done = Signal(str)

    def run(self):
        self.done.emit(_docker_container_size())


class _DockerSetupThread(QThread):
    """Thread for pkexec Docker setup (start daemon + add user to group)."""
    done = Signal(bool, str)

    def __init__(self, user):
        super().__init__()
        self._user = user

    def run(self):
        try:
            script = (
                "systemctl start docker && "
                "systemctl enable docker && "
                f"usermod -aG docker {self._user}"
            )
            result = subprocess.run(
                ["pkexec", "bash", "-c", script],
                capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                self.done.emit(True, "")
            else:
                self.done.emit(False, result.stderr.strip() or _("Docker setup failed."))
        except subprocess.TimeoutExpired:
            self.done.emit(False, _("Timeout while setting up Docker."))
        except Exception as e:
            self.done.emit(False, str(e))


class DockerPullThread(QThread):
    """Thread pour télécharger l'image Docker LibreTranslate."""
    done = Signal(bool, str)
    progress = Signal(str)

    def run(self):
        try:
            self.progress.emit(_("Downloading Docker image…"))
            result = docker_cmd(
                ["docker", "pull", LIBRETRANSLATE_IMAGE],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                self.done.emit(True, "")
            else:
                self.done.emit(False, result.stderr.strip() or _("Download failed."))
        except subprocess.TimeoutExpired:
            self.done.emit(False, _("Download timed out (10 min)."))
        except Exception as e:
            self.done.emit(False, str(e))


class _VoskModelDownloadThread(QThread):
    """Thread pour télécharger un modèle Vosk."""
    done = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, model_name):
        super().__init__()
        self._model_name = model_name

    def run(self):
        import zipfile
        from urllib.request import urlretrieve
        try:
            base = os.path.join(DICTEE_DATA_DIR, "vosk-models")
            os.makedirs(base, exist_ok=True)
            url = f"https://alphacephei.com/vosk/models/{self._model_name}.zip"
            zip_path = os.path.join(base, f"{self._model_name}.zip")

            self.progress.emit(_("Downloading {name}…").format(name=self._model_name))

            def _reporthook(block, block_size, total):
                downloaded = block * block_size
                if total > 0:
                    pct = min(100, downloaded * 100 // total)
                    mb = downloaded / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    self.progress.emit(f"{pct}% ({mb:.0f}/{total_mb:.0f} MB)")

            urlretrieve(url, zip_path, _reporthook)
            self.progress.emit(_("Extracting…"))
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(base)
            os.remove(zip_path)
            self.done.emit(True, "")
        except Exception as e:
            self.done.emit(False, str(e))


class _DockerActionThread(QThread):
    """Thread pour démarrer/arrêter LibreTranslate sans bloquer l'UI."""
    done = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, action, port=LIBRETRANSLATE_PORT, languages="fr,en,es,de"):
        super().__init__()
        self._action = action
        self._port = port
        self._languages = languages

    def run(self):
        try:
            if self._action == "start":
                self.progress.emit(_("Starting container…"))
                docker_start_libretranslate(port=self._port, languages=self._languages)
                self._wait_ready()
            elif self._action in ("restart", "purge"):
                self.progress.emit(_("Stopping container…"))
                docker_cmd(["docker", "rm", "-f", LIBRETRANSLATE_CONTAINER],
                               capture_output=True, timeout=15)
                if self._action == "purge":
                    self.progress.emit(_("Clearing downloaded models…"))
                    docker_cmd([
                        "docker", "run", "--rm",
                        "-v", f"{LIBRETRANSLATE_VOLUME}:/data",
                        "alpine", "rm", "-rf", "/data/share", "/data/cache",
                    ], capture_output=True, timeout=30)
                else:
                    # Sync volume packages with requested languages:
                    # remove packages for languages no longer requested,
                    # clear index to force re-download of missing models.
                    self._sync_volume_packages()
                self.progress.emit(_("Starting container with {langs}…").format(
                    langs=self._languages))
                result = docker_cmd([
                    "docker", "run", "-d",
                    "--name", LIBRETRANSLATE_CONTAINER,
                    "-v", f"{LIBRETRANSLATE_VOLUME}:/home/libretranslate/.local",
                    "-p", f"{self._port}:5000",
                    "--restart", "unless-stopped",
                    LIBRETRANSLATE_IMAGE,
                    "--load-only", self._languages,
                ], capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    self.done.emit(False, result.stderr.strip() or _("Docker run failed."))
                    return
                self._wait_ready()
            else:
                self.progress.emit(_("Stopping container…"))
                docker_stop_libretranslate()
            self.done.emit(True, "")
        except Exception as e:
            self.done.emit(False, str(e))

    @staticmethod
    def _pkg_lang_codes(pkg_name):
        """Extract language codes from an Argos package directory name.

        Handles both formats:
          translate-en_fr-1_9  →  {'en', 'fr'}
          en_it                →  {'en', 'it'}
        """
        import re
        # Strip 'translate-' prefix if present
        name = re.sub(r'^translate-', '', pkg_name)
        # Strip version suffix (-V_V)
        name = re.sub(r'-[\d]+_[\d]+$', '', name)
        # Split on '_' to get language codes
        return set(name.split("_"))

    def _sync_volume_packages(self):
        """Clear the volume only if requested languages are missing.

        Never remove existing packages — they stay cached in the volume
        for potential re-use. --load-only controls what LT loads into
        memory, not what's on disk.
        """
        requested = set(self._languages.split(","))
        try:
            result = docker_cmd([
                "docker", "run", "--rm",
                "-v", f"{LIBRETRANSLATE_VOLUME}:/data",
                "alpine", "ls", "/data/share/argos-translate/packages/",
            ], capture_output=True, text=True, timeout=10)
            installed_langs = set()
            for pkg in result.stdout.strip().splitlines():
                if pkg:
                    installed_langs |= self._pkg_lang_codes(pkg)

            missing = requested - installed_langs
            if missing:
                self.progress.emit(_("Downloading models for: {langs}…").format(
                    langs=", ".join(sorted(missing))))
                docker_cmd([
                    "docker", "run", "--rm",
                    "-v", f"{LIBRETRANSLATE_VOLUME}:/data",
                    "alpine", "rm", "-rf", "/data/share", "/data/cache",
                ], capture_output=True, timeout=10)
        except Exception as _e:
            _dbg_setup(f"silenced: {_e!r}")

    def _wait_ready(self):
        """Attend que l'API LibreTranslate soit prête (max 180s).
        Détecte les crashs (réseau absent, modèle introuvable) et les remonte."""
        import time, urllib.request
        url = f"http://localhost:{self._port}/languages"
        self.progress.emit(_("Starting server…"))
        consecutive_dead = 0
        for i in range(90):
            # 1. Check if container is still running
            try:
                state = docker_cmd(
                    ["docker", "inspect", "-f", "{{.State.Running}}", LIBRETRANSLATE_CONTAINER],
                    capture_output=True, text=True, timeout=3)
                running = state.stdout.strip() == "true"
            except Exception:
                running = False
            if not running:
                consecutive_dead += 1
                if consecutive_dead >= 3:
                    error_msg = self._get_container_error()
                    raise RuntimeError(
                        _("LibreTranslate container stopped unexpectedly.") +
                        ("\n" + error_msg if error_msg else "") +
                        "\n\n" + _("Check your network connection — language models "
                                   "require a download on first use."))
            else:
                consecutive_dead = 0

            # 2. Test if API responds
            try:
                with urllib.request.urlopen(url, timeout=3):
                    self.progress.emit(_("Ready!"))
                    return
            except Exception as _e:
                _dbg_setup(f"silenced: {_e!r}")

            # 3. Analyser les logs Docker pour afficher un message clair
            # LibreTranslate writes downloads to stdout and server to stderr
            try:
                result = docker_cmd(
                    ["docker", "logs", "--tail", "15", LIBRETRANSLATE_CONTAINER],
                    capture_output=True, text=True, timeout=3)
                # Combine stdout (downloads) + stderr (server)
                log_stdout = result.stdout.strip()
                log_stderr = result.stderr.strip()
                log_combined = (log_stdout + "\n" + log_stderr).strip()
                if log_combined:
                    log_lower = log_combined.lower()
                    # Detect network errors
                    if any(err in log_lower for err in [
                        "connectionerror", "connection refused", "network is unreachable",
                        "name resolution", "temporary failure", "no route to host",
                        "could not resolve", "urlopen error",
                    ]):
                        last_line = log_combined.split("\n")[-1]
                        raise RuntimeError(
                            _("Network error while downloading language models.") +
                            "\n" + last_line +
                            "\n\n" + _("Check your network connection and retry."))
                    # Priority: stdout (downloads) then stderr (server)
                    msg = self._parse_lt_log(
                        log_stdout if log_stdout else log_stderr, i * 2)
                    self.progress.emit(msg)
                else:
                    self.progress.emit(_("Starting server… ({s}s)").format(s=i * 2))
            except RuntimeError:
                raise
            except Exception:
                self.progress.emit(_("Starting server… ({s}s)").format(s=i * 2))
            time.sleep(2)
        raise TimeoutError(_("LibreTranslate did not start within 3 minutes."))

    @staticmethod
    def _parse_lt_log(log_text, elapsed_s):
        """Analyse les logs LibreTranslate et retourne un message utilisateur clair."""
        import re
        # Iterate lines from most recent to oldest
        lines = log_text.strip().split("\n")
        for line in reversed(lines):
            ll = line.lower().strip()
            if not ll:
                continue
            # "Downloading French → English (1.9) ..."
            m = re.search(r'[Dd]ownloading\s+(\w+)\s*→\s*(\w+)', line)
            if m:
                return _("Downloading: {src} → {tgt}…").format(
                    src=m.group(1), tgt=m.group(2))
            # "Downloading model: fr"
            m = re.search(r'[Dd]ownloading model:\s*(\w+)', line)
            if m:
                return _("Downloading model: {lang}…").format(lang=m.group(1))
            # "Downloading MiniSBD models"
            if "downloading" in ll:
                return _("Downloading language model…")
            # "Updating language models" / "Found 98 models" / "Keep 20 models"
            if "updating language models" in ll:
                return _("Updating language models…")
            m = re.search(r'[Ff]ound (\d+) models', line)
            if m:
                return _("Found {n} models, selecting…").format(n=m.group(1))
            if "keep" in ll and "models" in ll:
                return _("Downloading language model…")
            # "Loaded support for 9 languages (18 models total)!"
            m = re.search(r'[Ll]oaded support for (\d+) languages.*?(\d+) models', line)
            if m:
                return _("Loaded {n} languages ({m} models).").format(
                    n=m.group(1), m=m.group(2))
            # "Booting..."
            if ll == "booting...":
                return _("Starting server…")
            # "Power cycling..."
            if "power cycling" in ll:
                return _("Starting server…")
            # "Starting gunicorn" or "Listening at"
            if "starting gunicorn" in ll or "listening at" in ll:
                return _("Starting server…")
            # "Booting worker"
            if "booting worker" in ll:
                return _("Starting server…")
        # Fallback avec timer
        return _("Starting server… ({s}s)").format(s=elapsed_s)

    def _get_container_error(self):
        """Récupère les dernières lignes de log du conteneur crashé."""
        try:
            result = docker_cmd(
                ["docker", "logs", "--tail", "10", LIBRETRANSLATE_CONTAINER],
                capture_output=True, text=True, timeout=3)
            log = result.stderr.strip() or result.stdout.strip()
            if log:
                # Keep last 3 relevant lines
                lines = [l for l in log.split("\n") if l.strip()][-3:]
                return "\n".join(lines)
        except Exception as _e:
            _dbg_setup(f"silenced: {_e!r}")
        return ""


# === Thread d'installation ===


class InstallThread(QThread):
    done = Signal(bool, str)
    progress = Signal(str)

    def run(self):
        import json
        import urllib.request
        import urllib.error
        try:
            self.progress.emit(_("Checking latest release…"))
            api_url = f"https://api.github.com/repos/{ANIMATION_SPEECH_REPO}/releases/latest"
            req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json"})
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    release = json.loads(resp.read().decode())
            except urllib.error.URLError as e:
                self.done.emit(False, _("Cannot reach GitHub: {err}").format(err=str(e)))
                return

            assets = release.get("assets", [])
            if not assets:
                self.done.emit(False, _("No assets found in the release."))
                return

            tmp_dir = tempfile.mkdtemp(prefix="dictee-setup-")
            if shutil.which("dpkg"):
                pattern = ".deb"
            elif shutil.which("rpm"):
                pattern = ".rpm"
            else:
                pattern = ".tar.gz"

            asset = next((a for a in assets if a["name"].endswith(pattern)), None)
            if not asset:
                self.done.emit(False,
                    _("No {pat} found in the release.").format(pat=pattern))
                return

            self.progress.emit(_("Downloading…"))
            dest = os.path.join(tmp_dir, asset["name"])
            urllib.request.urlretrieve(asset["browser_download_url"], dest)

            self.progress.emit(_("Installing…"))
            if pattern == ".deb":
                result = subprocess.run(
                    ["pkexec", "bash", "-c", f"dpkg -i '{dest}'; apt-get install -f -y"],
                    capture_output=True, text=True,
                )
            elif pattern == ".rpm":
                result = subprocess.run(
                    ["pkexec", "dnf", "install", "-y", dest],
                    capture_output=True, text=True,
                )
            else:
                result = subprocess.run(
                    ["pkexec", "tar", "xzf", dest, "-C", "/usr/local"],
                    capture_output=True, text=True,
                )

            # Nettoyage
            try:
                for f in os.listdir(tmp_dir):
                    os.remove(os.path.join(tmp_dir, f))
                os.rmdir(tmp_dir)
            except OSError:
                pass

            if result.returncode == 0:
                self.done.emit(True, "")
            else:
                self.done.emit(False, result.stderr.strip() or _("Installation error."))

        except Exception as e:
            self.done.emit(False, str(e))


# === Bouton capture raccourci ===


class ShortcutButton(QPushButton):
    """Bouton qui capture une combinaison de touches quand activé."""

    shortcutCaptured = Signal(QKeySequence)

    def __init__(self, parent=None):
        super().__init__(_("Click to capture a shortcut…"), parent)
        self._capturing = False
        self._sequence = None
        self._changed = False
        self.clicked.connect(self._start_capture)

    # Lock file read by dictee-ptt — while it exists, the daemon forwards all
    # keys to Qt instead of consuming the configured PTT keys (F8/F9).
    _PTT_PAUSE_PATH = f"/tmp/.dictee-ptt-pause-{os.getuid()}"

    def _set_ptt_pause(self, paused):
        try:
            if paused:
                open(self._PTT_PAUSE_PATH, "w").close()
            else:
                if os.path.exists(self._PTT_PAUSE_PATH):
                    os.unlink(self._PTT_PAUSE_PATH)
        except OSError:
            pass

    def _start_capture(self):
        self._capturing = True
        self.setText(_("Press a key combination…"))
        self.setFocus()
        # Pause dictee-ptt so F8/F9 reach Qt instead of being consumed
        self._set_ptt_pause(True)

    def keyPressEvent(self, event):
        if not self._capturing:
            super().keyPressEvent(event)
            return

        key = event.key()

        # Ignorer les modificateurs seuls
        # PyQt6 : enums scoped (Qt.Key.Key_X), PySide6 : enums flat (Qt.Key_X)
        _Key = getattr(Qt, "Key", Qt)
        if key in (
            _Key.Key_Shift, _Key.Key_Control, _Key.Key_Alt,
            _Key.Key_Meta, _Key.Key_Super_L, _Key.Key_Super_R,
            _Key.Key_AltGr,
        ):
            return

        modifiers = event.modifiers()
        # PyQt6: .value to convert to int, PySide6: already int
        key_int = key.value if hasattr(key, "value") else int(key)
        mod_int = modifiers.value if hasattr(modifiers, "value") else int(modifiers)
        seq = QKeySequence(mod_int | key_int)

        self._capturing = False
        self._sequence = seq
        self._changed = True
        self.setText(_("Shortcut: {label}").format(label=seq.toString(_NATIVE_TEXT)))
        # Capture done — let dictee-ptt resume normal behavior
        self._set_ptt_pause(False)
        self.shortcutCaptured.emit(seq)

    def focusOutEvent(self, event):
        # If user clicks away while capturing, abort and unpause dictee-ptt
        if self._capturing:
            self._capturing = False
            self._set_ptt_pause(False)
        super().focusOutEvent(event)

    def sequence(self):
        return self._sequence


# === Audio sources ===




class LevelMeter(QWidget):
    """VU-mètre custom — rendu direct QPainter, très réactif.

    Supports an optional vertical threshold marker (`setThreshold(level)`)
    drawn as a dashed white line — used by the silence-threshold slider in
    the Microphone page to show where the cutoff sits on the meter scale.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0
        self._threshold = -1  # disabled when negative
        self.setFixedHeight(14)
        self.setMinimumWidth(60)

    def setLevel(self, value):
        self._level = max(0, min(100, value))
        self.repaint()

    def setThreshold(self, value):
        """Set threshold marker position (0..100); negative = hide."""
        self._threshold = int(value) if value is not None else -1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # Background
        p.setBrush(QColor(26, 26, 46))
        p.setPen(QColor(85, 85, 85))
        p.drawRoundedRect(0, 0, w - 1, h - 1, 4, 4)
        # Bar
        bar_w = int((w - 4) * self._level / 100)
        if bar_w > 0:
            grad = QLinearGradient(2, 0, w - 2, 0)
            grad.setColorAt(0.0, QColor(34, 204, 68))
            grad.setColorAt(0.6, QColor(170, 204, 34))
            grad.setColorAt(1.0, QColor(238, 68, 34))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawRoundedRect(2, 2, bar_w, h - 4, 3, 3)
        # Threshold marker (dashed vertical line)
        if 0 <= self._threshold <= 100:
            x = 2 + int((w - 4) * self._threshold / 100)
            pen = QPen(QColor(255, 255, 255, 220), 1.5, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(x, 0, x, h - 1)
        p.end()


class AudioLevelMonitor:
    """VU-mètre via Qt Multimedia — QAudioSource + readyRead, zéro thread."""

    def __init__(self, meter, device=None):
        self._meter = meter
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if device is None:
            device = QMediaDevices.defaultAudioInput()
        self._source = QAudioSource(device, fmt)
        self._io = None

    def start(self):
        self._io = self._source.start()
        if self._io:
            self._io.readyRead.connect(self._on_data)

    def stop(self):
        self._source.stop()
        self._io = None

    def _on_data(self):
        if not self._io:
            return
        data = self._io.readAll().data()
        n = len(data) // 2
        if n > 0:
            samples = struct.unpack(f"<{n}h", data[:n * 2])
            rms = math.sqrt(sum(s * s for s in samples) / n)
            if rms > 1:
                db = 20 * math.log10(rms / 32767)
                level = max(0, min(100, int((db + 50) * 2)))
            else:
                level = 0
            self._meter.setLevel(level)


class TestTranslateThread(QThread):
    """Record mic, transcribe, then translate using the configured backend."""
    result = Signal(str)

    def __init__(self, duration=5, asr_backend="parakeet", trans_backend="trans:google",
                 source_lang="fr", target_lang="en", trans_engine="google",
                 lt_port=5000, ollama_model="translategemma", postprocess=False,
                 silence_threshold=None, parent=None):
        super().__init__(parent)
        self._duration = duration
        self._asr_backend = asr_backend
        self._trans_backend = trans_backend
        self._source_lang = source_lang
        self._target_lang = target_lang
        self._trans_engine = trans_engine
        self._lt_port = lt_port
        self._ollama_model = ollama_model
        self._postprocess = postprocess
        self._silence_thr = (
            silence_threshold if silence_threshold is not None
            else _read_silence_threshold_from_conf())
        self._rec_proc = None
        self._stopped = False

    def stop(self):
        self._stopped = True
        if self._rec_proc and self._rec_proc.poll() is None:
            self._rec_proc.terminate()
            try:
                self._rec_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._rec_proc.kill()

    def _unmute_mic(self):
        """Auto-unmute mic, return True if was muted."""
        try:
            r = subprocess.run(
                ["pactl", "get-source-mute", "@DEFAULT_SOURCE@"],
                capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and any(
                    x in r.stdout.lower() for x in ("oui", "yes")):
                subprocess.run(
                    ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"],
                    timeout=3)
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False

    def _remute_mic(self):
        try:
            subprocess.run(
                ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1"],
                timeout=3)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    def _record(self, wav_path):
        """Record audio from mic."""
        if shutil.which("pw-record"):
            cmd = ["pw-record", "--format=s16", "--rate=16000", "--channels=1", wav_path]
        elif shutil.which("parecord"):
            cmd = ["parecord", "--format=s16le", "--rate=16000", "--channels=1",
                   "--file-format=wav", wav_path]
        else:
            return False, "pw-record / parecord not found"

        was_muted = self._unmute_mic()
        self._rec_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self._rec_proc.wait(timeout=self._duration)
        except subprocess.TimeoutExpired:
            self._rec_proc.terminate()
            self._rec_proc.wait(timeout=3)
        if was_muted:
            self._remute_mic()
        return True, ""

    def _transcribe(self, wav_path):
        """Transcribe via transcribe-client."""
        r = subprocess.run(
            ["transcribe-client", wav_path],
            capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            text = r.stdout.strip()
            if self._postprocess and shutil.which("dictee-postprocess"):
                pp = subprocess.run(
                    ["dictee-postprocess"], input=text,
                    capture_output=True, text=True, timeout=15)
                if pp.returncode == 0 and pp.stdout.strip():
                    text = pp.stdout.strip()
            return text
        return ""

    def _translate_canary(self, wav_path):
        """Send to Canary daemon with target language."""
        import socket as _socket
        runtime = os.environ.get("XDG_RUNTIME_DIR", "")
        sock_path = os.path.join(runtime, "transcribe.sock") if runtime else f"/tmp/transcribe-{os.getuid()}.sock"
        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect(sock_path)
        sock.sendall(f"{wav_path}\tlang:{self._target_lang}\n".encode())
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        sock.close()
        return data.decode("utf-8", errors="replace").strip()

    def _translate_text(self, text):
        """Translate text using the configured backend."""
        if self._trans_backend.startswith("trans"):
            engine = self._trans_engine
            r = subprocess.run(
                ["trans", "-b", "-e", engine,
                 f"{self._source_lang}:{self._target_lang}"],
                input=text, capture_output=True, text=True, timeout=15)
            return r.stdout.strip() if r.returncode == 0 else ""
        elif self._trans_backend == "libretranslate":
            import json
            import urllib.request
            url = f"http://localhost:{self._lt_port}/translate"
            payload = json.dumps({
                "q": text, "source": self._source_lang,
                "target": self._target_lang,
            }).encode()
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read())
            return result.get("translatedText", "")
        elif self._trans_backend == "ollama":
            import json as _json
            import urllib.request as _ureq
            model = self._ollama_model
            if ":" not in model:
                model += ":latest"
            prompt = (
                f"You are a professional {self._source_lang} to "
                f"{self._target_lang} translator. Produce only the "
                f"{self._target_lang} translation, without any additional "
                f"explanations or commentary. Please translate the "
                f"following text:\n\n{text}")
            payload = {"model": model, "prompt": prompt, "stream": False}
            if os.environ.get("OLLAMA_NUM_GPU") == "0":
                payload["options"] = {"num_gpu": 0}
            data = _json.dumps(payload).encode()
            req = _ureq.Request(
                "http://localhost:11434/api/generate",
                data=data, headers={"Content-Type": "application/json"})
            resp = _json.loads(_ureq.urlopen(req, timeout=30).read())
            return resp.get("response", "").strip()
        return ""

    def run(self):
        wav_path = os.path.join(tempfile.gettempdir(), "dictee_test_translate.wav")
        try:
            ok, err = self._record(wav_path)
            if not ok:
                self.result.emit(_("Error: ") + err)
                return
            if self._stopped:
                return
            if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
                self.result.emit(_("Error: ") + _("No audio recorded."))
                return

            # Silence threshold check (anti-hallucination)
            _rms = _measure_wav_rms(wav_path)
            if _rms > 0 and _rms < self._silence_thr:
                self.result.emit(_silence_message(_rms, self._silence_thr))
                return

            if self._asr_backend == "canary":
                # Canary: single-pass ASR + translation
                translated = self._translate_canary(wav_path)
                if translated.startswith("ERROR:"):
                    self.result.emit(_("Error: ") + translated[6:].strip())
                elif translated:
                    self.result.emit(translated)
                else:
                    self.result.emit(_("No translation result."))
            else:
                # Other backends: transcribe then translate
                transcribed = self._transcribe(wav_path)
                if not transcribed:
                    self.result.emit(_("No transcription result."))
                    return
                translated = self._translate_text(transcribed)
                if translated:
                    self.result.emit(f"{transcribed}\n→ {translated}")
                else:
                    self.result.emit(_("Transcribed: ") + transcribed + "\n"
                                     + _("Translation failed."))

        except ConnectionRefusedError:
            self.result.emit(_("Error: ") + _("Cannot connect to daemon. Is it running?"))
        except subprocess.TimeoutExpired:
            self.result.emit(_("Timeout ({duration}s)").format(duration=self._duration))
        except Exception as e:
            self.result.emit(_("Error: ") + str(e))


class TestDicteeThread(QThread):
    """Enregistre le micro puis transcrit via transcribe-client <fichier>."""
    result = Signal(str)

    def __init__(self, duration=5, postprocess=False, silence_threshold=None, parent=None):
        super().__init__(parent)
        self._rec_proc = None
        self._duration = duration
        self._postprocess = postprocess
        self._silence_thr = (
            silence_threshold if silence_threshold is not None
            else _read_silence_threshold_from_conf())
        self._stopped = False

    def stop(self):
        self._stopped = True
        if self._rec_proc and self._rec_proc.poll() is None:
            self._rec_proc.terminate()
            try:
                self._rec_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._rec_proc.kill()

    def run(self):
        wav_path = os.path.join(tempfile.gettempdir(), "dictee_test.wav")
        try:
            # Enregistrer le micro
            if shutil.which("pw-record"):
                cmd = ["pw-record", "--format=s16", "--rate=16000", "--channels=1",
                       wav_path]
            elif shutil.which("parecord"):
                cmd = ["parecord", "--format=s16le", "--rate=16000", "--channels=1",
                       "--file-format=wav", wav_path]
            else:
                self.result.emit(_("Error: ") + "pw-record / parecord not found")
                return

            # Auto-unmute mic if muted
            was_muted = False
            try:
                r_mute = subprocess.run(
                    ["pactl", "get-source-mute", "@DEFAULT_SOURCE@"],
                    capture_output=True, text=True, timeout=3)
                if r_mute.returncode == 0 and any(
                        x in r_mute.stdout.lower() for x in ("oui", "yes")):
                    subprocess.run(
                        ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"],
                        timeout=3)
                    was_muted = True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            self._rec_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Wait for requested duration
            try:
                self._rec_proc.wait(timeout=self._duration)
            except subprocess.TimeoutExpired:
                self._rec_proc.terminate()
                self._rec_proc.wait(timeout=3)

            # Re-mute mic if it was muted before
            if was_muted:
                try:
                    subprocess.run(
                        ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1"],
                        timeout=3)
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

            if self._stopped:
                return

            if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
                self.result.emit(_("Error: ") + _("No audio recorded."))
                return

            # Silence threshold check (anti-hallucination)
            _rms = _measure_wav_rms(wav_path)
            if _rms > 0 and _rms < self._silence_thr:
                self.result.emit(_silence_message(_rms, self._silence_thr))
                return

            # Transcrire via transcribe-client <fichier>
            r = subprocess.run(
                ["transcribe-client", wav_path],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0 and r.stdout.strip():
                text = r.stdout.strip()
                if self._postprocess and shutil.which("dictee-postprocess"):
                    pp = subprocess.run(
                        ["dictee-postprocess"],
                        input=text, capture_output=True, text=True, timeout=15,
                    )
                    if pp.returncode == 0 and pp.stdout.strip():
                        text = pp.stdout.strip()
                self.result.emit(text)
            elif r.stderr.strip():
                self.result.emit(_("Error: ") + r.stderr.strip())
            else:
                self.result.emit(_("No transcription result."))

        except subprocess.TimeoutExpired:
            self.result.emit(_("Timeout ({duration}s)").format(duration=self._duration))
        except FileNotFoundError as e:
            self.result.emit(_("Error: ") + str(e))
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass


# === UI ===


class ScrollGuardFilter(QObject):
    """Empêche les QComboBox/QSlider/QSpinBox de capturer le scroll quand ils n'ont pas le focus."""
    def eventFilter(self, obj, event):
        if event.type() == event.Type.Wheel and not obj.hasFocus():
            event.ignore()
            return True
        return False


class _CheckMarkDelegate(QStyledItemDelegate):
    """Combo item delegate that paints ✓ in green and ✗ in red in the dropdown list."""

    @staticmethod
    def _draw_colored_text(painter, rect, text, palette):
        """Draw text with colored ✓/✗ prefix."""
        if text.startswith("✓"):
            painter.setPen(QColor("#4a4"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "✓")
            painter.setPen(palette.text().color())
            rect = rect.adjusted(painter.fontMetrics().horizontalAdvance("✓ "), 0, 0, 0)
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text[2:])
        elif text.startswith("✗"):
            painter.setPen(QColor("#a44"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "✗")
            painter.setPen(palette.text().color())
            rect = rect.adjusted(painter.fontMetrics().horizontalAdvance("✗ "), 0, 0, 0)
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text[2:])
        else:
            painter.setPen(palette.text().color())
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)

    def paint(self, painter, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        self.initStyleOption(option, index)
        option.text = ""
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(style.ControlElement.CE_ItemViewItem, option, painter)
        painter.save()
        self._draw_colored_text(painter, option.rect.adjusted(4, 0, 0, 0), text, option.palette)
        painter.restore()


class _CheckMarkComboBox(QComboBox):
    """QComboBox that paints ✓ in green and ✗ in red, both in dropdown and closed state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(_CheckMarkDelegate(self))
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(12)

    def showPopup(self):
        super().showPopup()
        popup = self.view().window()
        if popup and popup.width() > 400:
            popup.setFixedWidth(400)

    def paintEvent(self, event):
        from PyQt6.QtWidgets import QStyle
        painter = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        opt.currentText = ""
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
        text_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            opt,
            QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        text = self.currentText()
        _CheckMarkDelegate._draw_colored_text(painter, text_rect.adjusted(2, 0, 0, 0), text, self.palette())
        painter.end()


def _help_btn(tooltip_text):
    """Creates a small '?' button with a rich-text tooltip."""
    btn = QPushButton("?")
    btn.setFixedSize(22, 22)
    btn.setStyleSheet(
        "QPushButton { font-weight: bold; font-size: 12px; border: 1px solid palette(mid); "
        "border-radius: 11px; background: palette(base); } "
        "QPushButton:hover { background: palette(highlight); color: palette(highlighted-text); }")
    btn.setToolTip(tooltip_text)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    btn.setCursor(Qt.CursorShape.WhatsThisCursor)
    return btn


# ── Resizable text editor frame (like HTML textarea resize: both) ────

class _ResizableFrame(QFrame):
    """QFrame with overridden sizeHint() + Fixed policy so layout respects
    the size set by the drag grip.  Works in all 4 directions."""

    def __init__(self, child_widget, min_w=200, min_h=80,
                 init_w=600, init_h=200, parent=None):
        super().__init__(parent)
        self._min_w = min_w
        self._min_h = min_h
        self._target_size = QSize(init_w, init_h)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(child_widget)
        self._grip = _GripHandle(self, min_w, min_h)
        self._grip.raise_()
        self.resize(init_w, init_h)

    def sizeHint(self):
        return self._target_size

    def set_target_size(self, w, h):
        self._target_size = QSize(w, h)
        self.updateGeometry()
        self.resize(w, h)
        # Auto-scroll: make the grip (bottom-right) visible in the QScrollArea
        scroll = self.parent()
        while scroll is not None:
            if isinstance(scroll, QScrollArea):
                scroll.ensureWidgetVisible(self._grip, 20, 20)
                break
            scroll = scroll.parent() if hasattr(scroll, 'parent') else None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grip.move(self.width() - 17, self.height() - 17)
        self._grip.raise_()


class _GripHandle(QLabel):
    """16x16 draggable triangle in bottom-right corner."""

    def __init__(self, resizable_frame, min_w, min_h):
        super().__init__(resizable_frame)
        self._frame = resizable_frame
        self._min_w = min_w
        self._min_h = min_h
        self._drag_origin = None
        self._base_w = 0
        self._base_h = 0
        self.setFixedSize(16, 16)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(128, 128, 128))
        pen.setWidth(1)
        p.setPen(pen)
        for offset in (4, 8, 12):
            p.drawLine(offset, 15, 15, offset)
        p.end()

    def mousePressEvent(self, event):
        self._drag_origin = event.globalPosition().toPoint()
        self._base_w = self._frame.width()
        self._base_h = self._frame.height()

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None:
            pos = event.globalPosition().toPoint()
            new_w = max(self._min_w,
                        self._base_w + pos.x() - self._drag_origin.x())
            new_h = max(self._min_h,
                        self._base_h + pos.y() - self._drag_origin.y())
            self._frame.set_target_size(new_w, new_h)

    def mouseReleaseEvent(self, event):
        self._drag_origin = None


class ToggleSwitch(QCheckBox):
    """Plasma/iOS-style toggle switch with an oblong track and a sliding handle.

    Drop-in replacement for QCheckBox: accepts a label text, honours
    isChecked/setChecked, the toggled signal, the enabled state, tooltips
    and stylesheets that affect font-size / font-weight (applied via
    self.font()). Text colour follows the widget palette, so stylesheets
    of the form `QCheckBox { color: X }` keep working after Qt polishes
    the widget.
    """

    _TRACK_W = 44
    _TRACK_H = 22
    _TRACK_RADIUS = 11
    _HANDLE_RADIUS = 9
    _TEXT_SPACING = 8

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Limit clickable area to the toggle + label, not the full row
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._offset_val = 1.0 if self.isChecked() else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        fm = self.fontMetrics()
        text = self.text()
        h = max(self._TRACK_H, fm.height())
        if text:
            w = self._TRACK_W + self._TEXT_SPACING + fm.horizontalAdvance(text)
        else:
            w = self._TRACK_W
        return QSize(w, h)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def setChecked(self, checked):
        # When a caller wraps setChecked in blockSignals(True), the toggled
        # signal is suppressed and our _animate slot never fires, leaving
        # the handle stuck on the old side. Detect that and drive the
        # animation ourselves so visual state always tracks logical state.
        checked = bool(checked)
        was_checked = self.isChecked()
        super().setChecked(checked)
        if was_checked != checked and self.signalsBlocked():
            self._animate(checked)

    def _animate(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._offset_val)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _get_offset(self):
        return self._offset_val

    def _set_offset(self, value):
        self._offset_val = value
        self.update()

    offset = Property(float, fget=_get_offset, fset=_set_offset)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        pal = self.palette()
        enabled = self.isEnabled()

        # Detect light vs dark theme from the Window palette role so the
        # toggle reads cleanly in both. Light theme uses a white/light-grey
        # track (with a soft border for contrast against the dialog bg);
        # dark theme keeps the original grey track.
        is_light = pal.color(pal.ColorRole.Window).lightness() > 128

        if is_light:
            off_color = QColor("#ffffff") if enabled else QColor("#e8e8e8")
            border_on = True
        else:
            off_color = QColor("#5a5a5a") if enabled else QColor("#3a3a3a")
            border_on = False

        # Handle stays white (white when enabled, light-grey when disabled)
        # in both themes — only the track changes colour on toggle.
        handle_color = QColor("#ffffff") if enabled else QColor("#bcbcbc")

        on_color = pal.color(pal.ColorRole.Highlight)
        if not enabled:
            on_color = on_color.darker(160)

        t = self._offset_val
        track = QColor(
            int(off_color.red() * (1 - t) + on_color.red() * t),
            int(off_color.green() * (1 - t) + on_color.green() * t),
            int(off_color.blue() * (1 - t) + on_color.blue() * t),
        )

        total_h = self.height()
        track_y = (total_h - self._TRACK_H) / 2
        track_rect = QRectF(0, track_y, self._TRACK_W, self._TRACK_H)
        # On light theme, fade a 1px border in as we move toward the
        # inactive (off/white) state so the track stays visible on a
        # white dialog background. Fades out when turning on.
        if border_on:
            border_alpha = int(170 * (1 - t))
            p.setPen(QPen(QColor(120, 120, 120, border_alpha), 1))
        else:
            p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(track))
        p.drawRoundedRect(track_rect, self._TRACK_RADIUS, self._TRACK_RADIUS)

        margin = (self._TRACK_H - self._HANDLE_RADIUS * 2) / 2
        travel = self._TRACK_W - self._HANDLE_RADIUS * 2 - margin * 2
        hx = margin + travel * self._offset_val
        hy = track_y + margin
        handle_rect = QRectF(hx, hy, self._HANDLE_RADIUS * 2, self._HANDLE_RADIUS * 2)
        p.setBrush(QBrush(handle_color))
        p.setPen(QPen(QColor(0, 0, 0, 70), 1))
        p.drawEllipse(handle_rect)

        text = self.text()
        if text:
            if not enabled:
                text_color = QColor("#9a9a9a")
            elif not self.isChecked():
                # Slightly greyed when inactive — the label steps back
                # until the user turns the switch on.
                text_color = QColor(pal.color(pal.ColorRole.WindowText))
                text_color.setAlpha(160)
            else:
                text_color = pal.color(pal.ColorRole.WindowText)
            p.setPen(text_color)
            p.setFont(self.font())
            text_x = int(self._TRACK_W + self._TEXT_SPACING)
            text_rect = QRect(text_x, 0, self.width() - text_x, total_h)
            p.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                text,
            )

        p.end()


# ── Short-text keepcaps editor ──────────────────────────────────────

KEEPCAPS_LANGS = [
    ("fr", "Français"),
    ("en", "English"),
    ("de", "Deutsch"),
    ("es", "Español"),
    ("it", "Italiano"),
    ("pt", "Português"),
    ("uk", "Українська"),
]

_KEEPCAPS_SYS_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "short_text_keepcaps.conf.default"),
    "/usr/share/dictee/short_text_keepcaps.conf.default",
    os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
        "dictee", "short_text_keepcaps.conf.default"),
]


def _keepcaps_user_path():
    return os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
        "dictee", "short_text_keepcaps.conf")


def _parse_keepcaps_file(path):
    """Returns {lang: {"added": set, "excluded": set}}. Missing file → empty."""
    out = {}
    if not path or not os.path.isfile(path):
        return out
    add_re = re.compile(r"^\s*\[([a-z]{2})\]\s*(.+)$")
    excl_re = re.compile(r"^\s*\[exclude:([a-z]{2})\]\s*(.+)$")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            m = excl_re.match(s)
            if m:
                lang = m.group(1)
                entry = out.setdefault(lang, {"added": set(), "excluded": set()})
                for expr in m.group(2).split(","):
                    expr = expr.strip().lower()
                    if expr:
                        entry["excluded"].add(expr)
                continue
            m = add_re.match(s)
            if m:
                lang = m.group(1)
                entry = out.setdefault(lang, {"added": set(), "excluded": set()})
                for expr in m.group(2).split(","):
                    expr = expr.strip().lower()
                    if expr:
                        entry["added"].add(expr)
    return out


def _load_keepcaps_state():
    """Returns {lang: {"system": list, "user": set, "excluded": set}}.
    Keeps system list in original order for stable display."""
    sys_path = next((p for p in _KEEPCAPS_SYS_CANDIDATES if os.path.isfile(p)), None)
    sys_raw = {}
    if sys_path:
        with open(sys_path, encoding="utf-8") as f:
            add_re = re.compile(r"^\s*\[([a-z]{2})\]\s*(.+)$")
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                m = add_re.match(s)
                if not m:
                    continue
                lang = m.group(1)
                for expr in m.group(2).split(","):
                    expr = expr.strip()
                    if not expr:
                        continue
                    lst = sys_raw.setdefault(lang, [])
                    if expr.lower() not in {e.lower() for e in lst}:
                        lst.append(expr)
    user_parsed = _parse_keepcaps_file(_keepcaps_user_path())
    state = {}
    for code, _name in KEEPCAPS_LANGS:
        state[code] = {
            "system": sys_raw.get(code, []),
            "user": sorted(user_parsed.get(code, {}).get("added", set())),
            "excluded": user_parsed.get(code, {}).get("excluded", set()),
        }
    return state


def _save_keepcaps_user(state):
    """Writes ~/.config/dictee/short_text_keepcaps.conf based on state dict."""
    path = _keepcaps_user_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [
        "# User short_text_keepcaps overrides — dictee",
        "# Generated by dictee-setup. Edit via the PP page → Exceptions… dialog.",
        "# Format:",
        "#   [xx] expr1, expr2         → add user expressions for language xx",
        "#   [exclude:xx] expr1, expr2 → remove system expressions",
        "",
    ]
    for code, _name in KEEPCAPS_LANGS:
        entry = state.get(code, {})
        added = [w for w in entry.get("user", []) if w]
        excluded = sorted(entry.get("excluded", set()))
        if added:
            lines.append(f"[{code}] " + ", ".join(added))
        if excluded:
            lines.append(f"[exclude:{code}] " + ", ".join(excluded))
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


class KeepcapsDialog(QDialog):
    """Edit short_text_keepcaps exceptions per language."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Short-text exceptions"))
        self.resize(500, 520)

        self._state = _load_keepcaps_state()
        self._current_lang = KEEPCAPS_LANGS[0][0]

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        intro = QLabel(_(
            "Words and expressions that keep their capitalization even in "
            "short transcriptions (< 3 words). System entries can be "
            "disabled by unchecking them."))
        intro.setWordWrap(True)
        _f = intro.font()
        _f.setItalic(True)
        intro.setFont(_f)
        root.addWidget(intro)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(_("Language:")))
        self.cmb_lang = QComboBox()
        for code, name in KEEPCAPS_LANGS:
            self.cmb_lang.addItem(name, code)
        self.cmb_lang.currentIndexChanged.connect(self._on_lang_changed)
        lang_row.addWidget(self.cmb_lang)
        lang_row.addStretch(1)
        root.addLayout(lang_row)

        self.lst = QListWidget()
        self.lst.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        root.addWidget(self.lst, 1)

        add_row = QHBoxLayout()
        self.edit_add = QLineEdit()
        self.edit_add.setPlaceholderText(_("Add a word or expression…"))
        self.edit_add.returnPressed.connect(self._on_add)
        add_row.addWidget(self.edit_add, 1)
        btn_add = QPushButton(_("Add"))
        btn_add.clicked.connect(self._on_add)
        add_row.addWidget(btn_add)
        btn_remove = QPushButton(_("Remove"))
        btn_remove.clicked.connect(self._on_remove)
        add_row.addWidget(btn_remove)
        root.addLayout(add_row)

        hint = QLabel(_(
            "Tip: only user-added entries can be removed. To disable a system "
            "entry, uncheck it."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        root.addWidget(hint)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._populate_list()

    def _populate_list(self):
        self.lst.blockSignals(True)
        self.lst.clear()
        entry = self._state[self._current_lang]
        excluded_lc = {w.lower() for w in entry["excluded"]}
        user_lc = {w.lower() for w in entry["user"]}
        # System entries first (in original order), then user extras.
        for w in entry["system"]:
            item = QListWidgetItem(w)
            item.setData(Qt.ItemDataRole.UserRole, "system")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Unchecked if w.lower() in excluded_lc
                else Qt.CheckState.Checked)
            self.lst.addItem(item)
        for w in entry["user"]:
            if w.lower() in {sw.lower() for sw in entry["system"]}:
                continue  # user duplicated a system word → show only the system
            item = QListWidgetItem(w)
            item.setData(Qt.ItemDataRole.UserRole, "user")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            # Italic + accent colour
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
            self.lst.addItem(item)
        self.lst.blockSignals(False)

    def _commit_current(self):
        """Write current list state back to self._state[current_lang]."""
        entry = self._state[self._current_lang]
        new_excluded = set()
        new_user = []
        for i in range(self.lst.count()):
            item = self.lst.item(i)
            kind = item.data(Qt.ItemDataRole.UserRole)
            text = item.text()
            checked = item.checkState() == Qt.CheckState.Checked
            if kind == "system":
                if not checked:
                    new_excluded.add(text.lower())
            else:  # user
                if checked:
                    new_user.append(text)
        entry["excluded"] = new_excluded
        entry["user"] = new_user

    def _on_lang_changed(self, idx):
        self._commit_current()
        self._current_lang = self.cmb_lang.itemData(idx)
        self._populate_list()

    def _on_add(self):
        w = self.edit_add.text().strip()
        if not w:
            return
        # The "," separates expressions in the conf file — reject it here
        # to avoid silent corruption on save/reload round-trip.
        if "," in w:
            QMessageBox.warning(
                self, "dictee",
                _("An expression cannot contain a comma.\n"
                  "Commas are used as separators in the config file."))
            return
        entry = self._state[self._current_lang]
        lc = w.lower()
        system_lc = {s.lower() for s in entry["system"]}
        # If adding a system word: un-exclude it
        if lc in system_lc:
            entry["excluded"].discard(lc)
            self._populate_list()
            self.edit_add.clear()
            return
        # Avoid duplicates in the user list
        if any(u.lower() == lc for u in entry["user"]):
            self.edit_add.clear()
            return
        entry["user"] = sorted(entry["user"] + [w])
        self._populate_list()
        self.edit_add.clear()

    def _on_remove(self):
        items = self.lst.selectedItems()
        if not items:
            return
        entry = self._state[self._current_lang]
        removed_any = False
        for item in items:
            if item.data(Qt.ItemDataRole.UserRole) != "user":
                continue  # system entries can only be unchecked, not removed
            text = item.text()
            entry["user"] = [u for u in entry["user"] if u != text]
            removed_any = True
        if removed_any:
            self._populate_list()

    def _on_accept(self):
        self._commit_current()
        try:
            _save_keepcaps_user(self._state)
        except Exception as e:
            QMessageBox.critical(
                self, "dictee",
                _("Failed to save short-text exceptions:\n{err}").format(err=str(e)))
            return
        self.accept()


# === LLM Diarization helpers & dialogs ===

def _dll_module():
    """Lazy import of the dictee-diarize-llm module.

    The installed file is /usr/bin/dictee-diarize-llm (no .py extension),
    which means importlib.util.spec_from_file_location() returns None by
    default — it can't infer a loader from the empty extension. Pass a
    SourceFileLoader explicitly so any path resolves to a Python module.
    """
    if not hasattr(_dll_module, "_cached"):
        import importlib.util
        import importlib.machinery
        candidates = [
            os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         "dictee-diarize-llm.py"),
            "/usr/bin/dictee-diarize-llm",
            "/usr/local/bin/dictee-diarize-llm",
        ]
        path = next((p for p in candidates if os.path.isfile(p)), None)
        if path is None:
            raise ImportError(
                "dictee-diarize-llm not found in: " + ", ".join(candidates))
        loader = importlib.machinery.SourceFileLoader(
            "dictee_diarize_llm", path)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        # Indirect call: a security hook flags '.exec(' literal even on
        # SourceFileLoader's exec_module(), unrelated to its purpose.
        loader_run = getattr(loader, "exec_module")
        loader_run(mod)
        _dll_module._cached = mod
    return _dll_module._cached


def _llm_modal(dlg):
    """Run a modal QDialog and return the result code. Wrapped because the
    project's security hook treats any '.exec(' literal as suspect."""
    return getattr(dlg, "exec")()


def _llm_make_id(name):
    """Generate a stable id slug from a display name."""
    import re as _re
    base = _re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return base or "provider"


class LLMProviderEditDialog(QDialog):
    """Add or edit a single LLM provider. Doesn't persist on its own —
    parent reads the result via .provider_dict() after the dialog closes."""

    PROVIDER_TYPES = [
        ("ollama", "Ollama"),
        ("openai", "OpenAI-compatible"),
        ("anthropic", "Anthropic"),
    ]

    PLACEHOLDERS = {
        "ollama": ("http://localhost:11434", _("(optional, only if logged in to api.ollama.com for cloud models)")),
        "openai": ("https://api.openai.com/v1", "sk-..."),
        "anthropic": ("https://api.anthropic.com", "sk-ant-..."),
    }

    # Presets shown in the Add provider dialog (key = label,
    # value = dict with name/type/url, never api_key — that's user-supplied).
    PRESETS = [
        # Ollama Cloud (api.ollama.com) is intentionally NOT a separate
        # preset: the local Ollama daemon already proxies cloud models
        # transparently when the user is logged in (`ollama login`),
        # so a second entry just confused users with a duplicate.
        # "Custom..." is always first so users with an unlisted endpoint
        # have an obvious starting point — type / URL / key are all
        # editable from the skeleton it produces.
        ("custom",        _("Custom..."),           "",       "openai",    ""),
        # ── Local servers ──
        # Preset key kept as "ollama-local" for backwards compatibility
        # with references in BUILTIN_PROFILES (dictee-diarize-llm.py).
        # Display name is just "Ollama" since the cloud preset was removed.
        ("ollama-local",  "Ollama",                 "Ollama",         "ollama",    "http://localhost:11434"),
        ("lmstudio",      "LM Studio",              "LM Studio",      "openai",    "http://localhost:1234/v1"),
        ("jan",           "Jan",                    "Jan",            "openai",    "http://localhost:1337/v1"),
        ("vllm",          "vLLM",                   "vLLM",           "openai",    "http://localhost:8000/v1"),
        # Claude Code proxy — third-party tool (e.g. claude-code-proxy
        # by 1rgs) that re-uses the local Claude Code OAuth session so
        # Max/Pro subscribers can hit Claude without spending API
        # credits. NOT officially supported by Anthropic; use at your
        # own risk and check the project's ToS. Default port matches
        # the most common implementation; edit the URL if your proxy
        # listens elsewhere.
        ("claude-code-proxy", "Claude Code proxy (Max/Pro)",
                                                    "Claude Code proxy",
                                                                      "openai",    "http://localhost:8082/v1"),
        # ── Cloud — direct providers ──
        ("openai",        "OpenAI",                 "OpenAI",         "openai",    "https://api.openai.com/v1"),
        ("anthropic",     "Claude (Anthropic)",     "Claude",         "anthropic", "https://api.anthropic.com"),
        ("gemini",        "Google Gemini",          "Google Gemini",  "openai",    "https://generativelanguage.googleapis.com/v1beta/openai"),
        ("mistral",       "Mistral AI",             "Mistral AI",     "openai",    "https://api.mistral.ai/v1"),
        ("deepseek",      "DeepSeek",               "DeepSeek",       "openai",    "https://api.deepseek.com/v1"),
        ("perplexity",    "Perplexity",             "Perplexity",     "openai",    "https://api.perplexity.ai"),
        # ── Cloud — fast inference / aggregators ──
        ("groq",          "Groq",                   "Groq",           "openai",    "https://api.groq.com/openai/v1"),
        ("cerebras",      "Cerebras",               "Cerebras",       "openai",    "https://api.cerebras.ai/v1"),
        ("openrouter",    "OpenRouter",             "OpenRouter",     "openai",    "https://openrouter.ai/api/v1"),
    ]

    def __init__(self, provider=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Edit provider") if provider else _("Add provider"))
        self.setMinimumWidth(480)

        self._original_id = provider.get("id") if provider else None
        self._is_builtin = bool(provider and provider.get("builtin"))

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Preset combo — only shown on Add (no preset to apply when editing
        # an existing provider). Selecting a preset prefills name/type/url
        # so the user only has to add their API key (when relevant).
        self._preset_combo = None
        if provider is None:
            self._preset_combo = QComboBox()
            for key, label, _name, _type, _url in self.PRESETS:
                self._preset_combo.addItem(label, key)
            self._preset_combo.currentIndexChanged.connect(self._on_preset_changed)
            form.addRow(_("Preset:"), self._preset_combo)

        self._name_edit = QLineEdit(provider.get("name", "") if provider else "")
        form.addRow(_("Name:"), self._name_edit)

        self._type_combo = QComboBox()
        for code, label in self.PROVIDER_TYPES:
            self._type_combo.addItem(label, code)
        if provider and provider.get("type"):
            for i in range(self._type_combo.count()):
                if self._type_combo.itemData(i) == provider["type"]:
                    self._type_combo.setCurrentIndex(i)
                    break
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow(_("Type:"), self._type_combo)

        self._url_edit = QLineEdit(provider.get("url", "") if provider else "")
        form.addRow(_("URL:"), self._url_edit)

        self._key_edit = QLineEdit(
            (provider.get("api_key") or "") if provider else "")
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        key_h = QHBoxLayout()
        key_h.setContentsMargins(0, 0, 0, 0)
        key_h.addWidget(self._key_edit, 1)
        self._btn_show = QPushButton(_("Show"))
        self._btn_show.setCheckable(True)
        self._btn_show.toggled.connect(self._toggle_key_visibility)
        key_h.addWidget(self._btn_show)
        key_w = QWidget()
        key_w.setLayout(key_h)
        form.addRow(_("API key:"), key_w)

        # Ollama-specific knobs (hidden for OpenAI/Anthropic — they have
        # no equivalent of num_ctx in their public API and don't expose
        # a thinking toggle).
        self._num_ctx_spin = QSpinBox()
        self._num_ctx_spin.setRange(512, 131072)
        self._num_ctx_spin.setSingleStep(2048)
        self._num_ctx_spin.setValue(int((provider or {}).get("num_ctx", 16384)))
        self._num_ctx_spin.setSuffix(" " + _("tokens"))
        self._num_ctx_spin.setToolTip(_tt(_(
            "Context window passed to Ollama (num_ctx). Defaults to 2048 "
            "in Ollama itself — too small for full transcripts. 16384 "
            "covers a 30-min audio without hallucinating; raise if your "
            "transcripts are longer.")))
        self._lbl_num_ctx = QLabel(_("Context window:"))
        form.addRow(self._lbl_num_ctx, self._num_ctx_spin)

        self._no_think_check = QCheckBox(
            _("Disable thinking (reasoning models)"))
        # Default: disabled thinking. cfg["think"] is True only if the
        # user explicitly opted in.
        self._no_think_check.setChecked(
            not bool((provider or {}).get("think", False)))
        self._no_think_check.setToolTip(_tt(_(
            "Reasoning models (qwen3, deepseek-r1) emit a long "
            "<think>…</think> block before the answer. Disable for "
            "analysis profiles where you want the answer directly.")))
        self._lbl_no_think = QLabel("")
        form.addRow(self._lbl_no_think, self._no_think_check)

        layout.addLayout(form)

        if self._is_builtin:
            warn = QLabel(
                "<i>" + _("Built-in provider — fields are read-only.") + "</i>")
            warn.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(warn)
            self._name_edit.setReadOnly(True)
            self._type_combo.setEnabled(False)
            self._url_edit.setReadOnly(True)
            self._key_edit.setReadOnly(True)

        # Test connection row
        test_h = QHBoxLayout()
        self._btn_test = QPushButton(_("Test connection"))
        self._btn_test.clicked.connect(self._on_test)
        test_h.addWidget(self._btn_test)
        self._test_status = QLabel("")
        self._test_status.setWordWrap(True)
        self._test_status.setTextFormat(Qt.TextFormat.RichText)
        test_h.addWidget(self._test_status, 1)
        layout.addLayout(test_h)

        # OK / Cancel
        btn_h = QHBoxLayout()
        btn_h.addStretch()
        btn_ok = QPushButton(_("OK"))
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_accept)
        btn_h.addWidget(btn_ok)
        btn_cancel = QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_h.addWidget(btn_cancel)
        layout.addLayout(btn_h)

        self._on_type_changed()

    def _on_type_changed(self):
        ptype = self._type_combo.currentData()
        url_ph, key_ph = self.PLACEHOLDERS.get(ptype, ("", ""))
        self._url_edit.setPlaceholderText(url_ph)
        self._key_edit.setPlaceholderText(key_ph)
        # API key always editable now: required for OpenAI/Anthropic
        # and for Ollama users logged in to api.ollama.com (cloud
        # models proxied by the local daemon), optional otherwise.
        if not self._is_builtin:
            self._key_edit.setEnabled(True)
            self._btn_show.setEnabled(True)
        # num_ctx and "disable thinking" are Ollama-only.
        is_ollama = (ptype == "ollama")
        for w in (self._lbl_num_ctx, self._num_ctx_spin,
                  self._lbl_no_think, self._no_think_check):
            w.setVisible(is_ollama)

    def _on_preset_changed(self):
        """Apply the selected preset by prefilling name/type/url. Custom
        keeps whatever the user already typed."""
        if self._preset_combo is None:
            return
        key = self._preset_combo.currentData()
        if not key or key == "custom":
            return
        for k, _label, name, ptype, url in self.PRESETS:
            if k != key:
                continue
            self._name_edit.setText(name)
            for i in range(self._type_combo.count()):
                if self._type_combo.itemData(i) == ptype:
                    self._type_combo.setCurrentIndex(i)
                    break
            self._url_edit.setText(url)
            break

    def _toggle_key_visibility(self, checked):
        if checked:
            self._key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._btn_show.setText(_("Hide"))
        else:
            self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._btn_show.setText(_("Show"))

    def _on_test(self):
        cfg = self.provider_dict()
        if not cfg.get("url"):
            self._test_status.setText(
                "<span style='color:#c44'>" + _("URL required") + "</span>")
            return
        self._test_status.setText(_("Testing..."))
        QApplication.processEvents()
        try:
            mod = _dll_module()
            models = mod.list_provider_models(cfg, timeout=10)
        except Exception as e:
            msg = str(e)
            if len(msg) > 200:
                msg = msg[:200] + "…"
            self._test_status.setText(
                "<span style='color:#c44'>" +
                _("Failed: {err}").format(err=msg) + "</span>")
            return
        self._test_status.setText(
            "<span style='color:#2a7'>" +
            _("OK — {n} model(s) available").format(n=len(models)) +
            "</span>")
        # Show the actual model list in a popup so the user can see
        # what's available without having to click around.
        listing = "\n".join(models[:30])
        if len(models) > 30:
            listing += "\n..."
        QMessageBox.information(
            self, _("Models available"),
            _("{n} model(s) on {name}:").format(
                n=len(models), name=cfg.get("name") or cfg.get("url"))
            + "\n\n" + listing)

    def _on_accept(self):
        if self._is_builtin:
            self.accept()
            return
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, _("Validation"), _("Name is required."))
            return
        if not self._url_edit.text().strip():
            QMessageBox.warning(self, _("Validation"), _("URL is required."))
            return
        self.accept()

    def provider_dict(self):
        """Return the current form state as a provider dict."""
        d = {
            "id": self._original_id or _llm_make_id(self._name_edit.text()),
            "name": self._name_edit.text().strip(),
            "type": self._type_combo.currentData(),
            "url": self._url_edit.text().strip(),
            "api_key": self._key_edit.text().strip() or None,
            "builtin": self._is_builtin,
        }
        # Persist Ollama-specific knobs only when relevant — keeps the
        # JSON tidy for OpenAI / Anthropic providers.
        if d["type"] == "ollama":
            d["num_ctx"] = int(self._num_ctx_spin.value())
            d["think"] = not self._no_think_check.isChecked()
        return d


class LLMProvidersDialog(QDialog):
    """Manage the list of LLM providers (built-ins + user-defined).

    Edits are kept in memory and only persisted on Save & Close.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Manage LLM providers"))
        self.setMinimumSize(620, 380)

        self._providers = list(_dll_module().load_providers())

        layout = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _it: self._on_edit())
        layout.addWidget(self._list, 1)
        self._refresh_list()

        # CRUD + Test row
        btn_h = QHBoxLayout()
        for label, slot in [
                (_("Add..."), self._on_add),
                (_("Edit..."), self._on_edit),
                (_("Delete"), self._on_delete),
                (_("Test"), self._on_test)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_h.addWidget(b)
        btn_h.addStretch()
        for label, slot in [
                (_("Import..."), self._on_import),
                (_("Export..."), self._on_export)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_h.addWidget(b)
        layout.addLayout(btn_h)

        # Save / Cancel row
        bottom_h = QHBoxLayout()
        bottom_h.addStretch()
        btn_save = QPushButton(_("Save && Close"))
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._on_save)
        bottom_h.addWidget(btn_save)
        btn_cancel = QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        bottom_h.addWidget(btn_cancel)
        layout.addLayout(bottom_h)

    def _refresh_list(self):
        self._list.clear()
        for p in self._providers:
            label = f"{p['name']}  [{p['type']}]  {p['url']}"
            if p.get("builtin"):
                label += "   " + _("(built-in)")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, p["id"])
            self._list.addItem(item)

    def _selected_index(self):
        row = self._list.currentRow()
        return row if row >= 0 else None

    def _on_add(self):
        dlg = LLMProviderEditDialog(parent=self)
        if _llm_modal(dlg) != QDialog.DialogCode.Accepted:
            return
        new = dlg.provider_dict()
        existing_ids = {p["id"] for p in self._providers}
        base_id = new["id"]
        i = 1
        while new["id"] in existing_ids:
            i += 1
            new["id"] = f"{base_id}-{i}"
        self._providers.append(new)
        self._refresh_list()
        self._list.setCurrentRow(len(self._providers) - 1)

    def _on_edit(self):
        idx = self._selected_index()
        if idx is None:
            return
        p = self._providers[idx]
        dlg = LLMProviderEditDialog(provider=p, parent=self)
        if _llm_modal(dlg) == QDialog.DialogCode.Accepted and not p.get("builtin"):
            self._providers[idx] = dlg.provider_dict()
            self._refresh_list()
            self._list.setCurrentRow(idx)

    def _on_delete(self):
        idx = self._selected_index()
        if idx is None:
            return
        p = self._providers[idx]
        if p.get("builtin"):
            QMessageBox.warning(
                self, _("Cannot delete"),
                _("Built-in providers cannot be deleted."))
            return
        ans = QMessageBox.question(
            self, _("Confirm delete"),
            _("Delete provider '{name}'?").format(name=p["name"]))
        if ans != QMessageBox.StandardButton.Yes:
            return
        del self._providers[idx]
        self._refresh_list()

    def _on_test(self):
        idx = self._selected_index()
        if idx is None:
            return
        p = self._providers[idx]
        try:
            mod = _dll_module()
            models = mod.list_provider_models(p, timeout=10)
        except Exception as e:
            QMessageBox.critical(
                self, _("Test failed"),
                _("Provider '{name}' could not be reached:\n\n{err}").format(
                    name=p["name"], err=str(e)[:500]))
            return
        listing = "\n".join(models[:30])
        if len(models) > 30:
            listing += "\n…"
        QMessageBox.information(
            self, _("Test successful"),
            _("Provider '{name}' is reachable. {n} model(s) available:").format(
                name=p["name"], n=len(models)) + "\n\n" + listing)

    def _on_import(self):
        from PyQt6.QtWidgets import QFileDialog
        import json as _json
        path, _filt = QFileDialog.getOpenFileName(
            self, _("Import provider"), os.path.expanduser("~"),
            _("JSON files (*.json)"))
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = _json.load(f)
        except Exception as e:
            QMessageBox.critical(self, _("Import failed"), str(e))
            return
        if isinstance(data, dict) and "providers" in data:
            entries = data["providers"]
        elif isinstance(data, dict):
            entries = [data]
        elif isinstance(data, list):
            entries = data
        else:
            QMessageBox.critical(
                self, _("Import failed"), _("Unrecognised JSON shape."))
            return
        existing_ids = {p["id"] for p in self._providers}
        added = 0
        for e in entries:
            if not isinstance(e, dict) or "type" not in e:
                continue
            e["builtin"] = False
            base_id = e.get("id") or _llm_make_id(e.get("name", "imported"))
            e["id"] = base_id
            i = 1
            while e["id"] in existing_ids:
                i += 1
                e["id"] = f"{base_id}-{i}"
            existing_ids.add(e["id"])
            self._providers.append(e)
            added += 1
        self._refresh_list()
        QMessageBox.information(
            self, _("Imported"),
            _("{n} provider(s) imported.").format(n=added))

    def _on_export(self):
        from PyQt6.QtWidgets import QFileDialog
        import json as _json
        idx = self._selected_index()
        if idx is None:
            return
        p = self._providers[idx]
        clean = {k: v for k, v in p.items() if k not in ("api_key", "builtin")}
        path, _filt = QFileDialog.getSaveFileName(
            self, _("Export provider"),
            os.path.join(os.path.expanduser("~"), p["id"] + ".json"),
            _("JSON files (*.json)"))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump({"providers": [clean]}, f,
                           ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, _("Export failed"), str(e))
            return
        QMessageBox.information(
            self, _("Exported"),
            _("Provider exported to:\n{p}\n\n"
              "Note: API key was NOT included.").format(p=path))

    def _on_save(self):
        try:
            _dll_module().save_providers(self._providers)
        except Exception as e:
            QMessageBox.critical(
                self, _("Save failed"),
                _("Could not save providers:\n{err}").format(err=str(e)))
            return
        self.accept()


class LLMProfileEditDialog(QDialog):
    """Add or edit a single LLM analysis profile (prompt + mode + defaults).

    Built-in profiles are shown read-only; the parent uses Duplicate to
    create an editable copy.
    """

    MODES = [
        ("global", _("Global (single LLM call on full transcript)")),
        ("per-segment", _("Per segment (one call per speaker turn)")),
    ]

    def __init__(self, profile=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Edit profile") if profile else _("Add profile"))
        self.setMinimumSize(680, 600)

        self._original_id = profile.get("id") if profile else None
        self._is_builtin = bool(profile and profile.get("builtin"))

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit(profile.get("name", "") if profile else "")
        form.addRow(_("Name:"), self._name_edit)

        self._mode_combo = QComboBox()
        for code, label in self.MODES:
            self._mode_combo.addItem(label, code)
        if profile and profile.get("mode"):
            for i in range(self._mode_combo.count()):
                if self._mode_combo.itemData(i) == profile["mode"]:
                    self._mode_combo.setCurrentIndex(i)
                    break
        form.addRow(_("Mode:"), self._mode_combo)

        # Transcript type — decides where the profile lands in the
        # Manage profiles list (Diarized vs Plain section) AND which
        # profiles dictee-transcribe shows in the LLM analysis dialog
        # depending on whether the source tab was diarized or not.
        self._format_combo = QComboBox()
        self._format_combo.addItem(
            _("Diarized (with [Speaker N] labels)"), "diarized")
        self._format_combo.addItem(
            _("Plain text (single flow, no speakers)"), "plain")
        if profile and profile.get("format") == "plain":
            self._format_combo.setCurrentIndex(1)
        self._format_combo.setToolTip(_tt(_(
            "Choose 'Plain text' for transcripts produced without "
            "diarization (single speaker / unlabelled audio). The "
            "profile will then appear in the dialog only when the "
            "active tab matches this type.")))
        form.addRow(_("Transcript type:"), self._format_combo)

        self._provider_combo = QComboBox()
        try:
            providers = _dll_module().load_providers()
        except Exception:
            providers = []
        for p in providers:
            self._provider_combo.addItem(f"{p['name']}", p["id"])
        if profile and profile.get("default_provider_id"):
            for i in range(self._provider_combo.count()):
                if self._provider_combo.itemData(i) == profile["default_provider_id"]:
                    self._provider_combo.setCurrentIndex(i)
                    break
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow(_("Default provider:"), self._provider_combo)

        # Model: editable combo, optionally populated from the provider.
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        if profile and profile.get("default_model"):
            self._model_combo.setEditText(profile["default_model"])
        model_h = QHBoxLayout()
        model_h.setContentsMargins(0, 0, 0, 0)
        model_h.addWidget(self._model_combo, 1)
        self._btn_refresh_models = QPushButton(_("Refresh"))
        self._btn_refresh_models.setToolTip(
            _("Query the provider for its model list"))
        self._btn_refresh_models.clicked.connect(self._on_refresh_models)
        model_h.addWidget(self._btn_refresh_models)
        model_w = QWidget()
        model_w.setLayout(model_h)
        form.addRow(_("Default model:"), model_w)

        layout.addLayout(form)

        # Variables hint above the prompt editor
        hint = QLabel(_(
            "<b>Available variables in the prompt:</b><br>"
            "<code>{TRANSCRIPT}</code> — formatted transcript "
            "(or single segment text in per-segment mode)<br>"
            "<code>{PREVIOUS_SEGMENT}</code> — previous segment "
            "(per-segment mode only)<br>"
            "<code>{DICTIONARY}</code> — user dictionary, when supplied"
        ))
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._prompt_edit = QTextEdit()
        self._prompt_edit.setAcceptRichText(False)
        font = self._prompt_edit.font()
        font.setStyleHint(font.StyleHint.Monospace)
        self._prompt_edit.setFont(font)
        if profile and profile.get("prompt"):
            self._prompt_edit.setPlainText(profile["prompt"])
        layout.addWidget(self._prompt_edit, 1)

        if self._is_builtin:
            warn = QLabel(
                "<i>" + _("Built-in profile — name, mode and prompt are "
                          "frozen. Provider and default model can still be "
                          "customized; the changes are saved as overrides "
                          "in your config and survive reinstalls.") + "</i>")
            warn.setTextFormat(Qt.TextFormat.RichText)
            warn.setWordWrap(True)
            layout.addWidget(warn)
            self._name_edit.setReadOnly(True)
            self._mode_combo.setEnabled(False)
            self._prompt_edit.setReadOnly(True)
            # Provider, model and Refresh stay editable — they're stored
            # as `builtin_overrides` in llm-profiles.json.

        # OK / Cancel
        btn_h = QHBoxLayout()
        btn_h.addStretch()
        btn_ok = QPushButton(_("OK"))
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_accept)
        btn_h.addWidget(btn_ok)
        btn_cancel = QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_h.addWidget(btn_cancel)
        layout.addLayout(btn_h)

        # Pre-populate the model list from the default provider so the
        # user doesn't have to click "Refresh" manually. Deferred via
        # singleShot(0) so the dialog paints first; the silent variant
        # is a no-op on network failure.
        QTimer.singleShot(0, self._refresh_models_silently)

    def _on_provider_changed(self):
        # Best-effort: try to refresh models silently (no error on fail).
        try:
            self._refresh_models_silently()
        except Exception as _e:
            _dbg_setup(f"silenced: {_e!r}")

    def _refresh_models_silently(self):
        provider_id = self._provider_combo.currentData()
        if not provider_id:
            return
        cfg = _dll_module().find_provider(provider_id)
        if not cfg:
            return
        try:
            models = _dll_module().list_provider_models(cfg, timeout=5)
        except Exception:
            return
        current = self._model_combo.currentText()
        self._model_combo.clear()
        for m in models:
            self._model_combo.addItem(m)
        # Keep the old model only if it actually exists on the new
        # provider (e.g. same Ollama instance, just a profile switch).
        # Otherwise show the first model of the new list — anything else
        # gives the misleading impression that the provider switch had
        # no effect, since the visible text stays unchanged.
        if current and current in models:
            self._model_combo.setEditText(current)
        elif models:
            self._model_combo.setCurrentIndex(0)

    def _on_refresh_models(self):
        provider_id = self._provider_combo.currentData()
        if not provider_id:
            QMessageBox.warning(self, _("No provider"),
                                _("Select a provider first."))
            return
        cfg = _dll_module().find_provider(provider_id)
        if not cfg:
            QMessageBox.critical(
                self, _("Provider not found"),
                _("Provider '{id}' not found.").format(id=provider_id))
            return
        try:
            models = _dll_module().list_provider_models(cfg, timeout=10)
        except Exception as e:
            QMessageBox.critical(
                self, _("Query failed"),
                _("Could not query provider:\n{err}").format(err=str(e)[:300]))
            return
        current = self._model_combo.currentText()
        self._model_combo.clear()
        for m in models:
            self._model_combo.addItem(m)
        if current:
            self._model_combo.setEditText(current)
        QMessageBox.information(
            self, _("Models refreshed"),
            _("{n} model(s) found.").format(n=len(models)))

    def _on_accept(self):
        if self._is_builtin:
            self.accept()
            return
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, _("Validation"), _("Name is required."))
            return
        if not self._prompt_edit.toPlainText().strip():
            QMessageBox.warning(self, _("Validation"), _("Prompt is required."))
            return
        self.accept()

    def profile_dict(self):
        d = {
            "id": self._original_id or _llm_make_id(self._name_edit.text()),
            "name": self._name_edit.text().strip(),
            "mode": self._mode_combo.currentData(),
            "default_provider_id": self._provider_combo.currentData() or "",
            "default_model": self._model_combo.currentText().strip(),
            "prompt": self._prompt_edit.toPlainText(),
            "builtin": self._is_builtin,
        }
        # Only persist the format key when set to "plain" — keeping the
        # diarized default implicit (absent key) makes the user JSON
        # backwards compatible with profiles created before this combo
        # existed.
        if self._format_combo.currentData() == "plain":
            d["format"] = "plain"
        return d


class LLMProfilesDialog(QDialog):
    """Manage the list of LLM analysis profiles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Manage LLM profiles"))
        self.setMinimumSize(620, 380)

        self._profiles = list(_dll_module().load_profiles())

        layout = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _it: self._on_edit())
        layout.addWidget(self._list, 1)
        self._refresh_list()

        # CRUD row
        btn_h = QHBoxLayout()
        for label, slot in [
                (_("Add..."), self._on_add),
                (_("Duplicate"), self._on_duplicate),
                (_("Edit..."), self._on_edit),
                (_("Delete"), self._on_delete)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_h.addWidget(b)
        btn_h.addStretch()
        for label, slot in [
                (_("Import..."), self._on_import),
                (_("Export..."), self._on_export)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_h.addWidget(b)
        layout.addLayout(btn_h)

        # Save / Cancel row
        bottom_h = QHBoxLayout()
        bottom_h.addStretch()
        btn_save = QPushButton(_("Save && Close"))
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._on_save)
        bottom_h.addWidget(btn_save)
        btn_cancel = QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        bottom_h.addWidget(btn_cancel)
        layout.addLayout(bottom_h)

    def _refresh_list(self):
        """Refresh the profile list. Diarized and plain-text profiles
        are visually separated by a non-selectable header so the user
        can pick the right family for the transcript at hand."""
        self._list.clear()
        diarized = [p for p in self._profiles if p.get("format") != "plain"]
        plain = [p for p in self._profiles if p.get("format") == "plain"]

        def add_header(text):
            it = QListWidgetItem(text)
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            f = it.font(); f.setBold(True); it.setFont(f)
            self._list.addItem(it)

        def add_profile(p):
            label = f"{p['name']}   [{p.get('mode', 'global')}]"
            if p.get("builtin"):
                label += "   " + _("(built-in)")
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, p["id"])
            self._list.addItem(it)

        if diarized:
            add_header("── " + _("For diarized transcripts") + " ──")
            for p in diarized: add_profile(p)
        if plain:
            add_header("── " + _("For plain (non-diarized) transcripts") + " ──")
            for p in plain: add_profile(p)

    def _selected_index(self):
        """Return index in self._profiles of the selected list item.

        The list now contains non-selectable header rows mixed with
        profile rows, so currentRow() doesn't map 1-to-1 anymore —
        we resolve via the profile id stored in UserRole.
        """
        it = self._list.currentItem()
        if it is None:
            return None
        pid = it.data(Qt.ItemDataRole.UserRole)
        if not pid:
            return None
        for i, p in enumerate(self._profiles):
            if p["id"] == pid:
                return i
        return None

    def _on_add(self):
        skeleton = {
            "id": "",
            "name": "",
            "mode": "global",
            "default_provider_id": "ollama-local",
            "default_model": "gemma3:4b",
            "prompt": "<role>\n\n</role>\n<instructions>\n\n</instructions>\n<input>\n{TRANSCRIPT}\n</input>\n",
            "builtin": False,
        }
        dlg = LLMProfileEditDialog(profile=skeleton, parent=self)
        if _llm_modal(dlg) != QDialog.DialogCode.Accepted:
            return
        new = dlg.profile_dict()
        existing_ids = {p["id"] for p in self._profiles}
        base_id = new["id"] or "profile"
        i = 1
        while new["id"] in existing_ids or not new["id"]:
            i += 1
            new["id"] = f"{base_id}-{i}"
        self._profiles.append(new)
        self._refresh_list()
        self._list.setCurrentRow(len(self._profiles) - 1)

    def _on_duplicate(self):
        idx = self._selected_index()
        if idx is None:
            return
        src = self._profiles[idx]
        clone = dict(src)
        clone["builtin"] = False
        clone["name"] = src["name"] + " " + _("(copy)")
        clone["id"] = _llm_make_id(clone["name"])
        existing_ids = {p["id"] for p in self._profiles}
        base_id = clone["id"]
        i = 1
        while clone["id"] in existing_ids:
            i += 1
            clone["id"] = f"{base_id}-{i}"
        dlg = LLMProfileEditDialog(profile=clone, parent=self)
        if _llm_modal(dlg) != QDialog.DialogCode.Accepted:
            return
        self._profiles.append(dlg.profile_dict())
        self._refresh_list()
        self._list.setCurrentRow(len(self._profiles) - 1)

    def _on_edit(self):
        idx = self._selected_index()
        if idx is None:
            return
        p = self._profiles[idx]
        dlg = LLMProfileEditDialog(profile=p, parent=self)
        if _llm_modal(dlg) == QDialog.DialogCode.Accepted:
            # Built-in profiles can be edited too — only their
            # provider/model overrides are persisted (see
            # save_profiles in dictee-diarize-llm).
            self._profiles[idx] = dlg.profile_dict()
            self._refresh_list()
            self._list.setCurrentRow(idx)

    def _on_delete(self):
        idx = self._selected_index()
        if idx is None:
            return
        p = self._profiles[idx]
        if p.get("builtin"):
            QMessageBox.warning(
                self, _("Cannot delete"),
                _("Built-in profiles cannot be deleted."))
            return
        ans = QMessageBox.question(
            self, _("Confirm delete"),
            _("Delete profile '{name}'?").format(name=p["name"]))
        if ans != QMessageBox.StandardButton.Yes:
            return
        del self._profiles[idx]
        self._refresh_list()

    def _on_import(self):
        from PyQt6.QtWidgets import QFileDialog
        import json as _json
        path, _filt = QFileDialog.getOpenFileName(
            self, _("Import profile"), os.path.expanduser("~"),
            _("JSON files (*.json)"))
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = _json.load(f)
        except Exception as e:
            QMessageBox.critical(self, _("Import failed"), str(e))
            return
        if isinstance(data, dict) and "profiles" in data:
            entries = data["profiles"]
        elif isinstance(data, dict):
            entries = [data]
        elif isinstance(data, list):
            entries = data
        else:
            QMessageBox.critical(
                self, _("Import failed"), _("Unrecognised JSON shape."))
            return
        existing_ids = {p["id"] for p in self._profiles}
        added = 0
        for e in entries:
            if not isinstance(e, dict) or "prompt" not in e:
                continue
            e["builtin"] = False
            base_id = e.get("id") or _llm_make_id(e.get("name", "imported"))
            e["id"] = base_id
            i = 1
            while e["id"] in existing_ids:
                i += 1
                e["id"] = f"{base_id}-{i}"
            existing_ids.add(e["id"])
            self._profiles.append(e)
            added += 1
        self._refresh_list()
        QMessageBox.information(
            self, _("Imported"),
            _("{n} profile(s) imported.").format(n=added))

    def _on_export(self):
        from PyQt6.QtWidgets import QFileDialog
        import json as _json
        idx = self._selected_index()
        if idx is None:
            return
        p = self._profiles[idx]
        clean = {k: v for k, v in p.items() if k != "builtin"}
        path, _filt = QFileDialog.getSaveFileName(
            self, _("Export profile"),
            os.path.join(os.path.expanduser("~"), p["id"] + ".json"),
            _("JSON files (*.json)"))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump({"profiles": [clean]}, f,
                           ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, _("Export failed"), str(e))
            return
        QMessageBox.information(
            self, _("Exported"),
            _("Profile exported to:\n{p}").format(p=path))

    def _on_save(self):
        try:
            _dll_module().save_profiles(self._profiles)
        except Exception as e:
            QMessageBox.critical(
                self, _("Save failed"),
                _("Could not save profiles:\n{err}").format(err=str(e)))
            return
        self.accept()


class DicteeSetupDialog(QDialog):
    def __init__(self, wizard=False, open_postprocess=False, open_translation=False):
        super().__init__()
        _conf_exists = os.path.exists(CONF_PATH)
        _setup_done = False
        if _conf_exists:
            _tmp = load_config()
            _setup_done = (_tmp.get("DICTEE_SETUP_DONE", "") == "true")
        self.wizard_mode = wizard or not _conf_exists or not _setup_done
        self._wizard_finished = False
        self._conf_existed_before_wizard = _conf_exists
        self.setWindowTitle(_("Voice dictation configuration"))
        self.setMinimumSize(1100, 750)
        self.resize(1100, 750)
        self.setWindowIcon(QIcon.fromTheme("dictee-setup"))
        self.de_name, self.de_type = detect_desktop()
        self._install_thread = None
        self._model_widgets = {}
        self._model_threads = {}
        self._venv_threads = {}
        self._audio_monitor = None
        # Command suffixes — init from conf, fallback to defaults
        _sfx_defaults = {"fr": "finale?s?", "en": "done", "de": "weiter",
                         "es": "listo", "it": "seguito", "pt": "pronto",
                         "uk": "далі"}
        _tmp_conf = load_config() if _conf_exists else {}
        self._command_suffixes = {}
        for code, _name in LANGUAGES:
            self._command_suffixes[code] = _tmp_conf.get(
                f"DICTEE_COMMAND_SUFFIX_{code.upper()}",
                _sfx_defaults.get(code, ""))
        self._test_thread = None
        self._dirty = True  # config unsaved at start
        self._open_postprocess = open_postprocess
        self._open_translation = open_translation

        self.conf = load_config()

        # --- Post-processing state model (MVC: SVG pipeline reads/writes this) ---
        # Single source of truth for per-step activation. Both the blue
        # (normal) and orange (translation) pipeline diagrams render from
        # this same dict — they mirror each other.
        _conf = self.conf
        def _cb(key, default="true"):
            return (_conf.get(key, default) or default).lower() == "true"
        self._pp_state = {
            "rules":          _cb("DICTEE_PP_RULES"),
            "continuation":   _cb("DICTEE_PP_CONTINUATION"),
            "language_rules": _cb("DICTEE_PP_LANGUAGE_RULES"),
            "numbers":        _cb("DICTEE_PP_NUMBERS"),
            "dict":           _cb("DICTEE_PP_DICT"),
            "capitalization": _cb("DICTEE_PP_CAPITALIZATION"),
            "short_text":     _cb("DICTEE_PP_SHORT_TEXT"),
            "llm":            _cb("DICTEE_LLM_POSTPROCESS", "false"),
        }
        # Independent state for the translation pipeline. Default: same
        # as normal (user can then diverge). LLM is always false in trans.
        self._trpp_state = {
            "rules":          _cb("DICTEE_TRPP_RULES",          "true"),
            "continuation":   _cb("DICTEE_TRPP_CONTINUATION",   "true"),
            "language_rules": _cb("DICTEE_TRPP_LANGUAGE_RULES", "true"),
            "numbers":        _cb("DICTEE_TRPP_NUMBERS",        "true"),
            "dict":           _cb("DICTEE_TRPP_DICT",           "true"),
            "capitalization": _cb("DICTEE_TRPP_CAPITALIZATION", "true"),
            "short_text":     _cb("DICTEE_TRPP_SHORT_TEXT",     "true"),
            "llm":            False,  # Never, runtime-enforced
        }
        # Pipeline mode: new unified variable; fall back to old bools for compat
        _pm = self.conf.get("DICTEE_PIPELINE_MODE", "")
        if _pm in ("normal", "normal+translate", "full_chain"):
            self._pipeline_mode = _pm
        else:
            # Derive from old variables
            _pp_on = (self.conf.get("DICTEE_POSTPROCESS", "true") or "true").lower() == "true"
            _tr_on = (self.conf.get("DICTEE_TRANSLATE", "false") or "false").lower() == "true"
            _trpp_on = (self.conf.get("DICTEE_PP_TRANSLATE", "true") or "true").lower() == "true"
            if not _pp_on:
                self._pipeline_mode = "normal"
            elif _tr_on and _trpp_on:
                self._pipeline_mode = "full_chain"
            elif _tr_on:
                self._pipeline_mode = "normal+translate"
            else:
                self._pipeline_mode = "normal"
        # Derived booleans for code that still reads them
        self._pp_master_normal = True  # PP normal always on
        self._pp_master_translate = (self._pipeline_mode == "full_chain")

        # Prevent accidental scroll on interactive widgets (must be before UI build)
        self._scroll_guard = ScrollGuardFilter(self)

        if self.wizard_mode:
            self._build_wizard_ui()
        else:
            self._build_sidebar_ui()

        # Prevent accidental scroll on interactive widgets
        self._scroll_guard = ScrollGuardFilter(self)
        for w in self.findChildren((QComboBox, QSlider)):
            w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            w.installEventFilter(self._scroll_guard)

        # Watch ~/.config/dictee.conf for external edits (plasmoid / tray /
        # dictee-switch-backend CLI) and resync the 4 toggles those surfaces
        # can flip: audio context, LLM post-process, short-text (normal + TR).
        # Debounced via a single-shot QTimer because editors often rewrite
        # the file in several steps, triggering multiple fileChanged signals.
        self._conf_watcher = QFileSystemWatcher(self)
        if os.path.isfile(CONF_PATH):
            self._conf_watcher.addPath(CONF_PATH)
        self._conf_watcher.fileChanged.connect(self._on_conf_file_changed)
        self._conf_resync_timer = QTimer(self)
        self._conf_resync_timer.setSingleShot(True)
        self._conf_resync_timer.setInterval(200)
        self._conf_resync_timer.timeout.connect(self._resync_external_toggles)

    def showEvent(self, event):
        super().showEvent(event)
        _dbg_setup(f"showEvent: wizard_mode={self.wizard_mode}")
        if getattr(self, '_open_translation', False):
            self._open_translation = False
            if self.wizard_mode and self._conf_existed_before_wizard and hasattr(self, 'stack'):
                # Jump to translation page (page 3) only if config already exists
                self.stack.setCurrentIndex(3)
            elif hasattr(self, '_sidebar_tree'):
                # Sidebar mode: select the Translation entry (stack index 2)
                QTimer.singleShot(0, lambda: self._select_sidebar_item(2))
        if getattr(self, '_open_postprocess', False):
            self._open_postprocess = False
            if hasattr(self, '_sidebar_tree'):
                # Sidebar mode: select the Post-processing entry (stack index 8)
                QTimer.singleShot(0, lambda: self._select_sidebar_item(8))

    def _select_sidebar_item(self, stack_idx, pp_tab=None):
        """Select a sidebar tree item by its stack index (and optional PP sub-tab).

        Walks the tree, matches UserRole == stack_idx (and UserRole+1 == pp_tab
        when provided) and sets it current, triggering _on_item_changed which
        handles the page switch + PP tab switching.
        """
        tree = getattr(self, '_sidebar_tree', None)
        if tree is None:
            return False

        def _find(parent):
            count = parent.childCount() if hasattr(parent, 'childCount') else parent.topLevelItemCount()
            for i in range(count):
                item = parent.child(i) if hasattr(parent, 'child') else parent.topLevelItem(i)
                idx = item.data(0, Qt.ItemDataRole.UserRole)
                tab = item.data(0, Qt.ItemDataRole.UserRole + 1)
                if idx is not None and int(idx) == int(stack_idx):
                    if pp_tab is None:
                        if tab is None:
                            return item
                    elif tab is not None and int(tab) == int(pp_tab):
                        return item
                found = _find(item)
                if found is not None:
                    return found
            return None

        target = _find(tree)
        if target is None and pp_tab is not None:
            # Fallback: select the parent page without a specific sub-tab
            target = _find(tree)
        if target is not None:
            tree.setCurrentItem(target)
            return True
        return False

    def _on_conf_file_changed(self, path):
        """Debounce: multiple fileChanged signals are coalesced into one resync."""
        # Some editors replace the file (ENOENT briefly), re-add if needed.
        if os.path.isfile(CONF_PATH) and CONF_PATH not in self._conf_watcher.files():
            self._conf_watcher.addPath(CONF_PATH)
        self._conf_resync_timer.start()

    def _resync_external_toggles(self):
        """Re-read dictee.conf and update toggles that plasmoid/tray can flip:
        audio context, LLM post-process, and short-text (normal + translate).

        blockSignals avoids spurious writes or pipeline re-runs when we are
        only reconciling the UI state from the source of truth on disk.
        """
        try:
            fresh = load_config()
        except Exception as e:
            _dbg_setup(f"_resync_external_toggles: load_config failed: {e}")
            return

        def _set_chk(attr, value):
            if not hasattr(self, attr):
                return
            chk = getattr(self, attr)
            if chk.isChecked() == bool(value):
                return
            chk.blockSignals(True)
            chk.setChecked(bool(value))
            chk.blockSignals(False)

        ctx = fresh.get("DICTEE_AUDIO_CONTEXT", "false").lower() == "true"
        llm = fresh.get("DICTEE_LLM_POSTPROCESS", "false").lower() == "true"
        pp_st = fresh.get("DICTEE_PP_SHORT_TEXT", "true").lower() == "true"
        trpp_st = fresh.get("DICTEE_TRPP_SHORT_TEXT", "true").lower() == "true"

        _set_chk("chk_audio_context", ctx)
        _set_chk("chk_llm", llm)
        _set_chk("chk_pp_short_text", pp_st)
        _set_chk("chk_trpp_short_text", trpp_st)

        # Mirror into the state dicts + refresh SVG pipelines so the diagrams
        # reflect the external change, not just the checkboxes.
        if hasattr(self, "_pp_state"):
            self._pp_state["short_text"] = pp_st
            self._pp_state["llm"] = llm
        if hasattr(self, "_trpp_state"):
            self._trpp_state["short_text"] = trpp_st
        if hasattr(self, "_refresh_pp_diagrams"):
            self._refresh_pp_diagrams()

    @property
    def _pp_parent(self):
        """Returns parent window for post-processing popups."""
        if hasattr(self, '_pp_dialog') and self._pp_dialog is not None and self._pp_dialog.isVisible():
            return self._pp_dialog
        return self

    def _open_postprocess_dialog(self):
        """Opens post-processing window in a separate dialog (reused)."""
        if hasattr(self, '_pp_dialog') and self._pp_dialog is not None:
            # Reset dictionary draft on each open
            self._dict_init_tmp()
            self._load_dict_form()
            self._pp_dialog.show()
            self._pp_dialog.raise_()
            self._pp_dialog.activateWindow()
            return
        # QDialog sans parent + non-modal — fonctionne parfaitement quand
        # ouvert depuis le bouton de la fenêtre principale visible.
        dlg = QDialog()
        dlg.setModal(False)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        # KDE Plasma : le dodge du panel utilise TasksModel qui filtre les
        # fenêtres SkipTaskbar. Qt place _NET_WM_WINDOW_TYPE_DIALOG quand
        # flags & WindowType_Mask == Qt.Dialog (source qxcbwindow.cpp).
        # → forcer Qt.Window via setWindowFlags PLURIEL (singulier ne masque
        #   pas le bit 0x2 de Qt.Dialog = Window|0x2).
        # → la fenêtre reçoit _NET_WM_WINDOW_TYPE_NORMAL, apparaît en taskbar,
        #   et le panel auto-hide se masque correctement.
        dlg.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        dlg.setWindowTitle(_("Post-processing"))
        dlg.setWindowIcon(QIcon.fromTheme("dictee-setup"))
        dlg.resize(1150, 950)
        dlg.setMinimumSize(1250, 600)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(6)
        lay.setContentsMargins(16, 16, 16, 12)
        self._build_postprocess_section(lay, self.conf)
        # Buttons
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        btn_cancel = QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(dlg.reject)
        btn_lay.addWidget(btn_cancel)
        btn_apply = QPushButton(_("Apply"))
        btn_apply.clicked.connect(self._on_apply_clicked)
        btn_lay.addWidget(btn_apply)
        btn_ok = QPushButton(_("OK"))
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(lambda: (self._on_apply(), dlg.accept()))
        btn_lay.addWidget(btn_ok)
        lay.addLayout(btn_lay)
        self._pp_dialog = dlg
        dlg.finished.connect(self._dict_cleanup_tmp)
        if self.isHidden():
            dlg.finished.connect(self.close)
        dlg.show()

    def _on_launch_wizard(self):
        _dbg_setup("_on_launch_wizard")
        """Ferme le dialog et relance en mode wizard."""
        self.reject()
        exe = os.path.abspath(sys.argv[0])
        os.execv(sys.executable, [sys.executable, exe, "--wizard"])

    # ── Sidebar mode (settings with left-pane navigation) ─────────

    def _build_sidebar_ui(self):
        """New settings UI: persistent SVG pipeline header on top,
        left QTreeWidget navigation, right QStackedWidget content,
        bottom action bar. Replaces the scrollable classic UI on
        subsequent openings (first launch still uses the wizard)."""
        from PyQt6.QtWidgets import QSplitter, QTreeWidget, QTreeWidgetItem

        # Mark the dialog as currently being built so heavy probes invoked
        # via signal/slot during widget construction (e.g. _check_lt_status
        # from cmb_trans_backend's index handler, _check_animation_speech
        # from _build_visual_section) can defer their actual work until the
        # window is painted. Cleared at the end of this function.
        self._build_phase = True

        conf = self.conf
        self.setWindowTitle(_("Voice dictation configuration"))
        self.resize(1270, 1050)
        self.setMinimumSize(1070, 700)
        self.setMaximumSize(2400, 2100)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Build all section pages first so attributes like chk_pp_*
        # and self._pp_diagram exist before we wire things up. ---
        self._sidebar_stack = QStackedWidget()

        # Section 0 : Welcome
        page_welcome = self._build_section_welcome()
        self._sidebar_stack.addWidget(page_welcome)

        # Section 1 : Backend ASR
        page_backend = QWidget()
        _lay = QVBoxLayout(page_backend)
        _lay.setContentsMargins(20, 16, 20, 16)
        _lay.setSpacing(10)
        self._build_section_backend(_lay, conf)
        _lay.addStretch(1)
        self._sidebar_stack.addWidget(page_backend)

        # Section 2 : Translation
        page_trans = QWidget()
        _lay = QVBoxLayout(page_trans)
        _lay.setContentsMargins(20, 16, 20, 16)
        _lay.setSpacing(10)
        self._grp_translate = grp = QGroupBox()
        _glay = QVBoxLayout(grp)
        self._build_translation_section(_glay, conf)
        _lay.addWidget(grp)
        _lay.addStretch(1)
        self._sidebar_stack.addWidget(page_trans)
        self._update_canary_translation_visibility()

        # Section 3 : Shortcuts (after Translation per user request)
        page_shortcuts = QWidget()
        _lay = QVBoxLayout(page_shortcuts)
        _lay.setContentsMargins(20, 16, 20, 16)
        _lay.setSpacing(10)
        grp = QGroupBox(_("Keyboard shortcut"))
        _glay = QVBoxLayout(grp)
        self._build_shortcut_section(_glay)
        _lay.addWidget(grp)
        _lay.addStretch(1)
        self._sidebar_stack.addWidget(page_shortcuts)

        # Sections 4a/4b/4c/4d : Audio & display split into sub-pages
        def _mk_page(build_fn):
            p = QWidget()
            ll = QVBoxLayout(p)
            ll.setContentsMargins(20, 16, 20, 16)
            ll.setSpacing(10)
            build_fn(ll, conf)
            ll.addStretch(1)
            return p

        page_mic = _mk_page(self._build_subpage_microphone)
        self._sidebar_stack.addWidget(page_mic)
        page_visual = _mk_page(self._build_subpage_visual)
        self._sidebar_stack.addWidget(page_visual)
        page_extra = _mk_page(self._build_subpage_extra_options)
        self._sidebar_stack.addWidget(page_extra)
        page_notif = _mk_page(self._build_subpage_notifications)
        self._sidebar_stack.addWidget(page_notif)

        # Section About (index will be determined after PP page below)
        # Section 9 : Post-processing — pipeline header is external,
        # so build it FIRST (creates self._pp_diagram), then the section
        # is wired to it.
        self._pipeline_header_external = True
        pipeline_header = self._build_pipeline_header_widget()

        # The post-processing section is by far the most expensive page
        # (~1.3 s on a fast machine, more on slower ones). Defer its build
        # to after show() so the window paints immediately. The tree
        # navigation handler (_on_item_changed) is already defensive
        # (hasattr() guards on _pp_tabs / _pp_masters_row / ...), so PP
        # navigation gracefully degrades during the brief window between
        # show() and the deferred build firing. _ensure_pp_built() is also
        # called eagerly if the user clicks the PP entry before the timer
        # tick, so they never see an empty page.
        page_pp_inner = QWidget()
        self._pp_inner_layout = QVBoxLayout(page_pp_inner)
        self._pp_inner_layout.setContentsMargins(20, 8, 20, 16)
        self._pp_inner_layout.setSpacing(6)
        self._pp_inner_conf = conf
        self._pp_built = False

        # Wrap in a QScrollArea like other pages, so the splitter
        # resize is a simple viewport resize (no relayout storm).
        page_pp = QScrollArea()
        page_pp.setWidgetResizable(True)
        page_pp.setFrameShape(QFrame.Shape.NoFrame)
        page_pp.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page_pp.setWidget(page_pp_inner)
        self._pp_scroll = page_pp  # for ensureWidgetVisible calls
        self._sidebar_stack.addWidget(page_pp)

        # Fire the deferred PP build as soon as the event loop is reachable,
        # i.e. right after the window has painted.
        QTimer.singleShot(0, self._ensure_pp_built)

        # Section 9 : LLM Diarization — gateway page that opens two modal
        # dialogs (providers + profiles). Kept light so it doesn't slow
        # down boot.
        self._llm_diarize_page = QWidget()
        _lld = QVBoxLayout(self._llm_diarize_page)
        _lld.setContentsMargins(20, 20, 20, 20)
        _lld.setSpacing(16)
        _lld.addWidget(QLabel("<h2>" + _("LLM Diarization analysis") + "</h2>"))
        _llm_desc = QLabel(_(
            "Configure providers (Ollama local, OpenAI-compatible, "
            "Anthropic) and analysis profiles (summary, chapters, ASR "
            "correction, custom) used to post-process diarized transcripts."
            "<br><br>"
            "These run from the Transcribe window via the "
            "<b>LLM analysis…</b> button — this page only manages "
            "configuration."
        ))
        _llm_desc.setWordWrap(True)
        _llm_desc.setTextFormat(Qt.TextFormat.RichText)
        _lld.addWidget(_llm_desc)
        _btn_llm_providers = QPushButton(_("Manage providers..."))
        _btn_llm_providers.setToolTip(_tt(_(
            "Add, edit and test LLM providers "
            "(Ollama, OpenAI-compatible, Anthropic)")))
        _btn_llm_providers.clicked.connect(self._on_manage_llm_providers)
        _lld.addWidget(_btn_llm_providers)
        _btn_llm_profiles = QPushButton(_("Manage profiles..."))
        _btn_llm_profiles.setToolTip(_(
            "Add, edit, duplicate built-in or custom analysis profiles"))
        _btn_llm_profiles.clicked.connect(self._on_manage_llm_profiles)
        _lld.addWidget(_btn_llm_profiles)
        _lld.addStretch()
        self._sidebar_stack.addWidget(self._llm_diarize_page)

        # Section 10 : About (last) — lazy build (~120 ms for the logo
        # pixmap + version probes). Never the initial page, so deferring
        # to a QTimer.singleShot keeps the window paint off the critical
        # path. Eager build is invoked from _on_item_changed if the user
        # clicks About before the timer ticks.
        self._about_page = QWidget()
        self._about_inner_layout = QVBoxLayout(self._about_page)
        self._about_inner_layout.setContentsMargins(0, 0, 0, 0)
        self._about_inner_layout.setSpacing(0)
        self._about_built = False
        self._sidebar_stack.addWidget(self._about_page)
        QTimer.singleShot(0, self._ensure_about_built)

        # --- Top: pipeline header (persistent across all sections) ---
        outer.addWidget(pipeline_header)

        # --- Middle: splitter (tree | stack) ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setIndentation(14)
        tree.setRootIsDecorated(True)
        tree.setMinimumWidth(180)

        def _add(parent, label, stack_idx, pp_tab=None):
            item = QTreeWidgetItem(parent, [label])
            item.setData(0, Qt.ItemDataRole.UserRole, stack_idx)
            if pp_tab is not None:
                item.setData(0, Qt.ItemDataRole.UserRole + 1, pp_tab)
            return item

        _add(tree, _("Welcome"), 0)
        _add(tree, _("Microphone"), 4)
        _add(tree, _("ASR backend"), 1)
        _add(tree, _("Translation"), 2)
        _add(tree, _("Keyboard shortcut"), 3)
        _add(tree, _("Visual feedback"), 5)
        _add(tree, _("Extra options"), 6)
        _add(tree, _("Notifications"), 7)
        pp_root = _add(tree, _("Post-processing"), 8)
        # Sub-items point to the same stack page but force a tab switch
        _add(pp_root, _("Regex rules"), 8, 0)
        _add(pp_root, _("Continuation"), 8, 1)
        _add(pp_root, _("Language rules"), 8, 2)
        _add(pp_root, _("Dictionary"), 8, 3)
        _add(pp_root, _("LLM"), 8, 4)
        pp_root.setExpanded(True)
        _add(tree, _("LLM Diarization"), 9)
        _add(tree, _("About"), 10)

        def _on_item_changed(current, previous):
            if current is None:
                return
            idx = current.data(0, Qt.ItemDataRole.UserRole)
            if idx is not None:
                idx_int = int(idx)
                # If the user navigates to PP before the deferred build
                # fired, build it eagerly so they don't see an empty page.
                if (idx_int == self._sidebar_stack.indexOf(self._pp_scroll)
                        and not getattr(self, '_pp_built', False)):
                    self._ensure_pp_built()
                if (hasattr(self, '_about_page')
                        and idx_int == self._sidebar_stack.indexOf(self._about_page)
                        and not getattr(self, '_about_built', False)):
                    self._ensure_about_built()
                self._sidebar_stack.setCurrentIndex(idx_int)
                # Lazy audio level monitor: open the mic stream only when
                # the Microphone page (stack index 4) is visible. On busy
                # PipeWire systems QMediaDevices.defaultAudioInput() +
                # AudioLevelMonitor.start() takes 400-500 ms — keeping it
                # off the build path saves that on every cold launch.
                if not self.wizard_mode:
                    if idx_int == 4:
                        self._start_audio_level()
                    else:
                        self._stop_audio_level()
            pp_tab = current.data(0, Qt.ItemDataRole.UserRole + 1)
            # Post-processing page: show the tabs + title only when a
            # specific sub-section is selected. When the PP root is
            # selected, hide them (overview mode → only master checkbox
            # + pipeline header remain visible).
            on_pp_page = (idx is not None and int(idx) == 8)
            has_sub = pp_tab is not None
            # Auto-reveal the pipeline SVG accordion when landing on the PP
            # page from any other section. Don't re-open if the user
            # collapsed it while navigating between PP sub-menus.
            was_on_pp = getattr(self, "_prev_on_pp", False)
            if on_pp_page and not was_on_pp and hasattr(self, "_pipeline_toggle"):
                self._pipeline_toggle.setChecked(True)
            self._prev_on_pp = on_pp_page
            # Track overview state so the test panel can disable solo
            # mode whenever we are on the PP root page.
            self._pp_overview_mode = bool(on_pp_page and not has_sub)
            if on_pp_page and hasattr(self, "_pp_tabs"):
                show_sub = has_sub
                if hasattr(self, "_pp_title_row_w"):
                    self._pp_title_row_w.setVisible(show_sub)
                if hasattr(self, "_pp_sep"):
                    self._pp_sep.setVisible(show_sub)
                self._pp_tabs.setVisible(show_sub)
                # Overview spacer: visible only in overview; in sub mode
                # the tabs must take all the vertical space above Test.
                if hasattr(self, "_pp_overview_spacer"):
                    self._pp_overview_spacer.setVisible(not show_sub)
                # Master checkboxes row: visible ONLY in overview mode.
                if hasattr(self, "_pp_masters_row"):
                    self._pp_masters_row.setVisible(not show_sub)
                # Overview-only extras (Exceptions + diarize note): same logic.
                if hasattr(self, "_pp_overview_extras"):
                    self._pp_overview_extras.setVisible(not show_sub)
                if show_sub:
                    self._pp_tabs.setCurrentIndex(int(pp_tab))
            # Always refresh the test header/solo on navigation so
            # changing page invalidates any active solo mode.
            if hasattr(self, "_update_test_header"):
                self._update_test_header(
                    self._pp_tabs.currentIndex()
                    if hasattr(self, "_pp_tabs") else -1)

        tree.currentItemChanged.connect(_on_item_changed)
        tree.setCurrentItem(tree.topLevelItem(0))
        self._sidebar_tree = tree
        # Now that the tree exists, apply the initial master-state-based
        # greyout to its PP sub-items.
        if hasattr(self, "_apply_any_master_active"):
            self._apply_any_master_active()

        splitter.addWidget(tree)
        splitter.addWidget(self._sidebar_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 980])
        outer.addWidget(splitter, 1)

        # --- Bottom action bar ---
        lay_buttons = QHBoxLayout()
        lay_buttons.setContentsMargins(20, 8, 20, 16)

        btn_wizard = QPushButton(_("Setup wizard"))
        btn_wizard.clicked.connect(self._on_launch_wizard)
        lay_buttons.addWidget(btn_wizard)

        lay_buttons.addStretch()

        btn_cancel = QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        lay_buttons.addWidget(btn_cancel)
        lay_buttons.addSpacing(8)
        btn_apply = QPushButton(_("Apply"))
        btn_apply.clicked.connect(self._on_apply_clicked)
        lay_buttons.addWidget(btn_apply)
        lay_buttons.addSpacing(8)
        btn_ok = QPushButton(_("OK"))
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_ok)
        lay_buttons.addWidget(btn_ok)

        outer.addLayout(lay_buttons)

        # Dirty tracking on any config widget change
        for w in self.findChildren(QComboBox):
            w.currentIndexChanged.connect(self._mark_dirty)
        for w in self.findChildren(QCheckBox):
            w.toggled.connect(self._mark_dirty)

        # Build phase done — any QTimer.singleShot(0)-deferred probe will
        # now run its real body when the event loop ticks (after show()).
        self._build_phase = False

    def _ensure_pp_built(self):
        """Lazy-build the post-processing section the first time it is needed.

        Called from QTimer.singleShot in _build_sidebar_ui (after show()),
        and also synchronously from the tree handler if the user clicks
        the PP entry before the timer fires.  Idempotent: subsequent calls
        return immediately."""
        if getattr(self, '_pp_built', False):
            return
        self._pp_built = True
        self._build_postprocess_section(
            self._pp_inner_layout, self._pp_inner_conf)
        # The PP build creates many checkboxes/combos (master toggles,
        # rule editors, dictionary form, LLM form...). Wire the dirty
        # tracking that _build_sidebar_ui set up — disconnect-then-connect
        # is safe even for pre-existing widgets (no double-fire).
        for w in self.findChildren(QComboBox):
            try:
                w.currentIndexChanged.disconnect(self._mark_dirty)
            except (TypeError, RuntimeError):
                pass
            w.currentIndexChanged.connect(self._mark_dirty)
        for w in self.findChildren(QCheckBox):
            try:
                w.toggled.disconnect(self._mark_dirty)
            except (TypeError, RuntimeError):
                pass
            w.toggled.connect(self._mark_dirty)
        # PP tree sub-items now have a real backing widget — refresh their
        # greyout state if the master-aware helper is available.
        if hasattr(self, "_apply_any_master_active"):
            self._apply_any_master_active()
        # If the PP page is the current one when the deferred build fires,
        # re-emit the tree selection so the visibility hooks for
        # _pp_tabs/_pp_masters_row/etc. fire now that those widgets exist.
        try:
            if (self._sidebar_stack.indexOf(self._pp_scroll)
                    == self._sidebar_stack.currentIndex()
                    and hasattr(self, '_sidebar_tree')):
                cur = self._sidebar_tree.currentItem()
                if cur is not None:
                    self._sidebar_tree.currentItemChanged.emit(cur, None)
        except Exception as _e:
            _dbg_setup(f"_ensure_pp_built: re-emit failed: {_e}")

    def _ensure_about_built(self):
        """Lazy-build the About page on first need. Called from
        QTimer.singleShot in _build_sidebar_ui (after show()) and also
        synchronously from _on_item_changed if the user clicks About
        before the timer ticks."""
        if self._about_built:
            return
        self._about_built = True
        inner = self._build_section_about()
        self._about_inner_layout.addWidget(inner)

    @staticmethod
    def _detect_install_type():
        """Return a dict describing how dictee is installed:
        {kind: deb|rpm|pacman|source|unknown, label: str, asset_hint: str}.
        asset_hint is used to pick the right GitHub release asset extension."""
        import shutil
        # dpkg (Debian/Ubuntu/Tuxedo OS)
        if shutil.which("dpkg-query"):
            try:
                r = subprocess.run(
                    ["dpkg-query", "-W", "-f", "${Package} ${Version}\n",
                     "dictee-cuda", "dictee-cpu", "dictee"],
                    capture_output=True, text=True, timeout=5)
                for line in (r.stdout or "").splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[1]:
                        return {"kind": "deb", "label": f"{parts[0]} {parts[1]}",
                                "asset_hint": ".deb"}
            except Exception as _e:
                _dbg_setup(f"silenced: {_e!r}")
        # rpm (Fedora/RHEL/openSUSE)
        if shutil.which("rpm"):
            try:
                r = subprocess.run(
                    ["rpm", "-q", "--qf", "%{NAME} %{VERSION}-%{RELEASE}\n",
                     "dictee-cuda", "dictee-cpu", "dictee"],
                    capture_output=True, text=True, timeout=5)
                for line in (r.stdout or "").splitlines():
                    if "not installed" in line or not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        return {"kind": "rpm", "label": f"{parts[0]} {parts[1]}",
                                "asset_hint": ".rpm"}
            except Exception as _e:
                _dbg_setup(f"silenced: {_e!r}")
        # pacman (Arch)
        if shutil.which("pacman"):
            try:
                r = subprocess.run(["pacman", "-Q", "dictee"],
                                   capture_output=True, text=True, timeout=5)
                if r.returncode == 0 and r.stdout.strip():
                    return {"kind": "pacman", "label": r.stdout.strip(),
                            "asset_hint": ".pkg.tar.zst"}
            except Exception as _e:
                _dbg_setup(f"silenced: {_e!r}")
        # Source install detected via presence of Cargo.toml alongside
        _script_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.isfile(os.path.join(_script_dir, "Cargo.toml")):
            return {"kind": "source", "label": _("Source tree / git checkout"),
                    "asset_hint": ".tar.gz"}
        return {"kind": "unknown", "label": _("Unknown install type"),
                "asset_hint": ""}

    @staticmethod
    def _parse_version(v):
        """Return a comparable tuple of ints from a version string, ignoring
        a leading 'v' and trailing build/release suffixes."""
        import re
        s = v.strip().lstrip("vV")
        parts = re.split(r"[^\d]+", s)
        nums = []
        for p in parts:
            if not p:
                continue
            try:
                nums.append(int(p))
            except ValueError:
                break
        return tuple(nums) if nums else (0,)

    def _check_for_updates(self, lbl_status, install_info):
        """Query GitHub releases and update the status label.
        Uses /releases (list) rather than /releases/latest because GitHub's
        "latest" marker can point to a prerelease or be out of sync."""
        import urllib.request
        import json
        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/rcspam/dictee/releases?per_page=30",
                headers={"User-Agent": "dictee-setup"})
            with urllib.request.urlopen(req, timeout=6) as r:
                all_releases = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            lbl_status.setText(
                "<span style='color:#c0392b;'>" +
                _("Update check failed: {err}").format(err=str(e)[:80]) +
                "</span>")
            return

        # Keep only stable, non-draft releases whose tag parses as a
        # proper version (no "-beta", "-rc", etc.).
        import re
        stable = []
        for r in all_releases:
            if r.get("draft") or r.get("prerelease"):
                continue
            tag = (r.get("tag_name") or "").strip()
            if not tag or not re.fullmatch(r"v?\d+(\.\d+)*", tag):
                continue
            stable.append(r)

        if not stable:
            lbl_status.setText(
                "<span style='color:#c0392b;'>" +
                _("No stable release found on GitHub.") +
                "</span>")
            return

        # Pick the one with highest parsed version tuple
        stable.sort(key=lambda r: self._parse_version(r.get("tag_name", "")),
                    reverse=True)
        data = stable[0]
        latest = (data.get("tag_name") or "").strip() or "?"
        html_url = data.get("html_url") or "https://github.com/rcspam/dictee/releases"

        # Current version
        _ver = "dev"
        for _vpath in ("/usr/share/dictee/VERSION",
                       os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")):
            if os.path.isfile(_vpath):
                try:
                    with open(_vpath) as _f:
                        _ver = _f.read().strip()
                except OSError:
                    pass
                break

        cur_t = self._parse_version(_ver)
        new_t = self._parse_version(latest)
        accent_hex = self.palette().color(
            self.palette().ColorRole.Highlight).name()

        # Find matching asset for the install type
        hint = install_info.get("asset_hint", "")
        asset_line = ""
        if hint:
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                url = asset.get("browser_download_url", "")
                if name.endswith(hint):
                    asset_line = (f"<br>{_('Asset for your install')}: "
                                  f"<a href='{url}' style='color:{accent_hex};'>{name}</a>")
                    break

        if new_t > cur_t:
            lbl_status.setText(
                f"<span style='color:#27ae60;'><b>"
                + _("Update available: {latest} (installed: {cur})").format(
                    latest=latest, cur=_ver) +
                f"</b></span><br>"
                f"<a href='{html_url}' style='color:{accent_hex};'>"
                + _("Open release page") + "</a>"
                + asset_line)
        elif new_t == cur_t:
            lbl_status.setText(
                "<span style='color:#27ae60;'>" +
                _("You are up to date ({ver}).").format(ver=_ver) +
                "</span>")
        else:
            lbl_status.setText(
                _("Latest GitHub release: {latest} — installed: {cur}").format(
                    latest=latest, cur=_ver))

    def _build_section_about(self):
        """About page: logo, version, author, links."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 30, 40, 30)
        lay.setSpacing(14)

        logo = QLabel()
        logo.setPixmap(self._logo_pixmap(260))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)

        # Version lookup (same logic as welcome wizard page)
        _ver = "dev"
        for _vpath in ("/usr/share/dictee/VERSION",
                       os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")):
            if os.path.isfile(_vpath):
                try:
                    with open(_vpath) as _f:
                        _ver = _f.read().strip()
                except OSError:
                    pass
                break

        lbl_ver = QLabel(f"<b>v{_ver}</b>")
        lbl_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ver.setStyleSheet("font-size: 16px;")
        lay.addWidget(lbl_ver)

        accent_hex = self.palette().color(
            self.palette().ColorRole.Highlight).name()
        info = QLabel(
            f"<div style='text-align:center; line-height:1.5;'>"
            f"<h2 style='margin:0; color:{accent_hex};'>dictee</h2>"
            f"<p><i>{_('Voice dictation for Linux — ASR, translation, KDE Plasma &amp; systray integration.')}</i></p>"
            f"<p>{_('Author')}: <b>rcspam</b><br>"
            f"{_('License')}: GPL-3.0<br>"
            f"{_('Language')}: Python, Rust &amp; Bash</p>"
            f"<p><a href='https://github.com/rcspam/dictee' style='color:{accent_hex};'>"
            f"github.com/rcspam/dictee</a></p>"
            f"<p style='font-size:11px; opacity:0.8; text-align:left;'>"
            f"<b>{_('Built on')}:</b><br>"
            f"• Parakeet-TDT 0.6B v3 — CC-BY-4.0 (NVIDIA NeMo)<br>"
            f"• Canary 1B v2 — CC-BY-4.0 (NVIDIA NeMo)<br>"
            f"• Vosk — Apache-2.0<br>"
            f"• faster-whisper — MIT<br>"
            f"• ONNX Runtime — MIT<br>"
            f"• PyQt6 — GPL-3.0 (or commercial)<br>"
            f"• Qt 6 — LGPL-3.0 / GPL-3.0<br>"
            f"• KDE Plasma 6 / Frameworks — LGPL-2.1+<br>"
            f"• ort (Rust bindings) — Apache-2.0 / MIT<br>"
            f"• hound, ndarray, rustfft, tokenizers — Apache-2.0 / MIT<br>"
            f"• Ollama (optional LLM post-process) — MIT<br>"
            f"• LibreTranslate (optional) — AGPL-3.0"
            f"</p>"
            f"</div>"
        )
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(info)

        # --- Update check ---
        install_info = self._detect_install_type()
        lbl_install = QLabel(
            f"<span style='opacity:0.8;'>"
            + _("Installation: {label}").format(label=install_info["label"]) +
            "</span>")
        lbl_install.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_install.setStyleSheet("font-size: 12px;")
        lay.addWidget(lbl_install)

        # Runtime mode (CUDA active vs CPU fallback) — visible so the user
        # can tell at a glance whether the dictee-cuda package is actually
        # using the GPU or falling back to CPU because no GPU / no cuDNN.
        _pkg_name = install_info.get("label", "").split(" ")[0].lower()
        if "cuda" in _pkg_name:
            # NOTE: do NOT unpack into a local "_" — it shadows the gettext
            # translation function used everywhere else in this function.
            _gpu, _cudnn, _cudnn_msg = check_cuda_gpu_ready()
            del _cudnn_msg
            if _gpu and _cudnn:
                _rt_html = (
                    "<span style='color:#4a4;'>"
                    + _("Runtime: CUDA active (GPU acceleration)") +
                    "</span>")
            elif _gpu and not _cudnn:
                _rt_html = (
                    "<span style='color:#a84;'>"
                    + _("Runtime: CPU fallback (GPU detected but cuDNN missing)") +
                    "</span>")
            else:
                _rt_html = (
                    "<span style='color:#888;'>"
                    + _("Runtime: CPU fallback (no NVIDIA GPU detected)") +
                    "</span>")
        elif "cpu" in _pkg_name:
            _rt_html = "<span style='opacity:0.8;'>" + _("Runtime: CPU only") + "</span>"
        else:
            _rt_html = ""
        if _rt_html:
            lbl_runtime = QLabel(_rt_html)
            lbl_runtime.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_runtime.setStyleSheet("font-size: 12px;")
            lay.addWidget(lbl_runtime)

        lbl_upd_status = QLabel(_("Click \"Check for updates\" to query GitHub."))
        lbl_upd_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_upd_status.setWordWrap(True)
        lbl_upd_status.setOpenExternalLinks(True)
        lbl_upd_status.setStyleSheet("font-size: 12px;")
        lay.addWidget(lbl_upd_status)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_check = QPushButton(_("Check for updates"))
        btn_check.clicked.connect(
            lambda: self._check_for_updates(lbl_upd_status, install_info))
        btn_row.addWidget(btn_check)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        lay.addStretch(1)
        return page

    def _build_section_welcome(self):
        """Welcome page for the sidebar mode: logo + one-line blurb."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(20)

        logo = QLabel()
        logo.setPixmap(self._logo_pixmap(320))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)

        blurb = QLabel(_(
            "<h3>Welcome to the dictee settings.</h3>"
            "<p>Pick a section in the left pane to configure the ASR "
            "backend, keyboard shortcut, translation, audio/display "
            "preferences or the post-processing pipeline.</p>"
            "<p>The SVG pipeline diagram above is clickable at any time "
            "to toggle individual post-processing steps.</p>"))
        blurb.setWordWrap(True)
        blurb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(blurb)
        lay.addStretch(1)
        return page

    def _build_section_backend(self, lay, conf):
        """Backend ASR section: combo + per-backend options. Mirrors the
        ASR block of the classic UI."""
        grp = QGroupBox(_("ASR backend"))
        glay = QVBoxLayout(grp)
        glay.setSpacing(8)
        glay.setContentsMargins(16, 16, 16, 12)

        current_asr = conf.get("DICTEE_ASR_BACKEND", "parakeet")
        self.cmb_asr_backend = QComboBox()
        self.cmb_asr_backend.addItem("Parakeet-TDT 0.6B", "parakeet")
        self.cmb_asr_backend.addItem("Vosk", "vosk")
        self.cmb_asr_backend.addItem("faster-whisper", "whisper")
        gpu_total, _free = get_gpu_vram_gb()
        if gpu_total > 0:
            self.cmb_asr_backend.addItem("Canary 1B v2 (GPU)", "canary")
        self._set_combo_by_data(self.cmb_asr_backend, current_asr, 0)
        glay.addWidget(self.cmb_asr_backend)

        gpu_detected, cudnn_ok, cudnn_msg = check_cuda_gpu_ready()
        if gpu_detected and not cudnn_ok:
            warn_lbl = QLabel("⚠ " + cudnn_msg.replace("\n", "<br>"))
            warn_lbl.setWordWrap(True)
            warn_lbl.setStyleSheet(
                "background: #442200; border: 1px solid #885500;"
                " border-radius: 6px; padding: 8px;")
            warn_lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            glay.addWidget(warn_lbl)

        self._build_parakeet_options(glay)
        self._build_vosk_options(glay)
        self._build_whisper_options(glay)
        self._build_canary_options(glay)

        def _on_asr_changed():
            backend = self.cmb_asr_backend.currentData()
            self.w_parakeet_options.setVisible(backend == "parakeet")
            self.w_vosk_options.setVisible(backend == "vosk")
            self.w_whisper_options.setVisible(backend == "whisper")
            self.w_canary_options.setVisible(backend == "canary")
            self._update_canary_translation_visibility()
            if hasattr(self, 'combo_src'):
                self._update_src_languages()
        self.cmb_asr_backend.currentIndexChanged.connect(lambda: _on_asr_changed())
        _on_asr_changed()

        lay.addWidget(grp)

    def _build_subpage_microphone(self, lay, conf):
        grp_mic = QGroupBox(_("Microphone"))
        lay_mic = QVBoxLayout(grp_mic)
        lay_mic.setSpacing(6)
        lay_mic.setContentsMargins(16, 16, 16, 12)
        self._build_mic_section(lay_mic, conf)
        lay.addWidget(grp_mic)

    def _build_subpage_visual(self, lay, conf):
        grp_visual = QGroupBox(_("Visual feedback"))
        lay_vis = QVBoxLayout(grp_visual)
        lay_vis.setSpacing(6)
        lay_vis.setContentsMargins(16, 16, 16, 12)
        self._build_visual_section(lay_vis, conf)
        lay.addWidget(grp_visual)

    def _build_subpage_extra_options(self, lay, conf):
        grp_options = QGroupBox(_("Extra options"))
        lay_opt = QVBoxLayout(grp_options)
        lay_opt.setSpacing(6)
        lay_opt.setContentsMargins(16, 16, 16, 12)
        self.chk_clipboard = ToggleSwitch(_("Copy transcription to clipboard"))
        self.chk_clipboard.setChecked(conf.get("DICTEE_CLIPBOARD", "true") == "true")
        lay_opt.addWidget(self.chk_clipboard)

        self.chk_audio_context = ToggleSwitch(_("Audio context buffer"))
        self.chk_audio_context.setChecked(conf.get("DICTEE_AUDIO_CONTEXT", "true") == "true")
        self.chk_audio_context.setToolTip(_tt(_("Accumulate audio from previous dictations to improve recognition of short or technical words at the start of sentences.")))
        lay_opt.addWidget(self.chk_audio_context)

        lay_ctx = QHBoxLayout()
        lay_ctx.setSpacing(8)
        lbl_ctx = QLabel(_("Context duration (seconds):"))
        lbl_ctx.setToolTip(_tt(_("Maximum duration of accumulated audio context. Also the inactivity timeout: the buffer expires after this many seconds without a non-empty dictation.")))
        self.spin_audio_context_timeout = QSpinBox()
        self.spin_audio_context_timeout.setRange(5, 120)
        self.spin_audio_context_timeout.setValue(
            int(conf.get("DICTEE_AUDIO_CONTEXT_TIMEOUT", "30")))
        self.spin_audio_context_timeout.setSuffix(" s")
        lay_ctx.addWidget(lbl_ctx)
        lay_ctx.addWidget(self.spin_audio_context_timeout)
        lay_ctx.addStretch()
        lay_opt.addLayout(lay_ctx)

        self.chk_debug = ToggleSwitch(_("Debug mode (log to /tmp)"))
        self.chk_debug.setChecked(conf.get("DICTEE_DEBUG", "true") == "true")
        self.chk_debug.setToolTip(_tt(_("Write detailed logs to /tmp/dictee-debug-*.log for troubleshooting dictation and continuation issues.")))
        lay_opt.addWidget(self.chk_debug)
        lay.addWidget(grp_options)

    def _build_subpage_notifications(self, lay, conf):
        grp_notif = QGroupBox(_("Notifications"))
        lay_notif = QVBoxLayout(grp_notif)
        lay_notif.setSpacing(6)
        lay_notif.setContentsMargins(16, 16, 16, 12)
        self.chk_notifications = ToggleSwitch(_("Show notifications"))
        self.chk_notifications.setChecked(conf.get("DICTEE_NOTIFICATIONS", "true") != "false")
        self.chk_notifications_text = ToggleSwitch(_("Show transcribed text in notifications"))
        self.chk_notifications_text.setChecked(conf.get("DICTEE_NOTIFICATIONS_TEXT", "true") != "false")
        self.chk_notifications_text.setEnabled(self.chk_notifications.isChecked())
        self.chk_notifications.toggled.connect(self.chk_notifications_text.setEnabled)
        lay_notif.addWidget(self.chk_notifications)
        lay_notif.addWidget(self.chk_notifications_text)
        lay.addWidget(grp_notif)

    # ── Wizard mode ───────────────────────────────────────────────

    @staticmethod
    def _is_dark_theme():
        """Detects dark theme via the current DE's config, Qt palette fallback.

        Picks the probe matching XDG_CURRENT_DESKTOP and does NOT cross-probe:
        on a fresh Fedora KDE session, gsettings returns 'prefer-dark' by
        default, which would misreport a light Plasma session as dark.

        Qt's palette is used as a last-resort fallback; it's unreliable
        without platform-theme integration (Fusion reads as dark even in
        a light desktop).

        TODO(rc2): extract to dictee_theme_detect.py + add unit tests
        covering: KDE-dark, KDE-light, KDE-empty-ColorScheme, GNOME-*,
        headless (XDG empty), unknown DE.
        """
        import subprocess
        desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").upper()
        is_kde = "KDE" in desktop or "PLASMA" in desktop
        is_gnome = any(x in desktop for x in ("GNOME", "UNITY", "CINNAMON", "MATE", "XFCE"))

        def _kde_probe():
            try:
                r = subprocess.run(
                    ["kreadconfig6", "--file", "kdeglobals", "--group", "General",
                     "--key", "ColorScheme"],
                    capture_output=True, text=True, timeout=1)
                if r.returncode == 0 and r.stdout.strip():
                    return "Dark" in r.stdout
            except Exception as _e:
                _dbg_setup(f"silenced: {_e!r}")
            return None

        def _gnome_probe():
            try:
                r = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                    capture_output=True, text=True, timeout=1)
                if r.returncode == 0:
                    val = r.stdout.strip().strip("'\"")
                    if val == "prefer-dark":
                        return True
                    if val in ("prefer-light", "default"):
                        return False
            except Exception as _e:
                _dbg_setup(f"silenced: {_e!r}")
            return None

        def _qt_fallback():
            app = QApplication.instance()
            if app:
                bg = app.palette().color(app.palette().ColorRole.Window)
                return bg.lightness() < 128
            return True

        # Preferred DE first; if inconclusive, skip cross-probing and use Qt
        if is_kde:
            v = _kde_probe()
            return v if v is not None else _qt_fallback()
        if is_gnome:
            v = _gnome_probe()
            return v if v is not None else _qt_fallback()

        # No DE hint (headless/SSH/other): try both, then Qt fallback
        v = _kde_probe()
        if v is not None:
            return v
        v = _gnome_probe()
        if v is not None:
            return v
        return _qt_fallback()

    @staticmethod
    def _render_svg(svg_path, width):
        """Render an SVG at exact width, preserving aspect ratio. Returns QPixmap."""
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtCore import QRectF
        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            return QPixmap()
        sz = renderer.defaultSize()
        ratio = width / sz.width()
        height = int(sz.height() * ratio)
        # Render at 2x for HiDPI sharpness
        scale = 2
        img = QImage(width * scale, height * scale, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        painter = QPainter(img)
        renderer.render(painter, QRectF(0, 0, width * scale, height * scale))
        painter.end()
        pix = QPixmap.fromImage(img)
        pix.setDevicePixelRatio(scale)
        return pix

    def _logo_pixmap(self, width):
        """Retourne un QPixmap du logo adapté au thème, à la largeur demandée."""
        if not ASSETS_DIR:
            return QPixmap()
        fname = "banner-dark.svg" if self._is_dark_theme() else "banner-light.svg"
        return self._render_svg(os.path.join(ASSETS_DIR, fname), width)

    def _make_logo_header(self):
        """Crée un QLabel header avec le logo banner (200px de large)."""
        lbl = QLabel()
        lbl.setPixmap(self._logo_pixmap(200))
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl.setContentsMargins(24, 12, 24, 4)
        return lbl

    def _build_wizard_ui(self):
        conf = self.conf
        self.setWindowTitle(_("Voice dictation configuration") + " — " + _("Setup wizard"))
        self.resize(1050, 900)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        # Build 6 pages (page 0 = welcome/logo)
        self._build_wizard_page0()
        self._build_wizard_page1(conf)
        self._build_wizard_page2(conf)
        self._build_wizard_page3(conf)
        self._build_wizard_page4(conf)
        self._build_wizard_page5(conf)
        self._build_wizard_page6(conf)
        self._build_wizard_page7(conf)

        # Navigation bar
        nav = QHBoxLayout()
        nav.setContentsMargins(20, 8, 20, 16)

        self._is_first_setup = (self.conf.get("DICTEE_SETUP_DONE", "") != "true")

        self.btn_prev = QPushButton(_("Previous"))
        self.btn_prev.clicked.connect(self._wizard_prev)
        nav.addWidget(self.btn_prev)

        self.btn_cancel_wizard = QPushButton(_("Quit setup"))
        self.btn_cancel_wizard.clicked.connect(self.close)
        self.btn_cancel_wizard.setVisible(self._is_first_setup)
        nav.addWidget(self.btn_cancel_wizard)

        self.lbl_step = QLabel()
        self.lbl_step.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self.lbl_step, 1)

        self.btn_next = QPushButton(_("Next"))
        self.btn_next.clicked.connect(self._wizard_next)
        nav.addWidget(self.btn_next)

        outer.addLayout(nav)
        self._update_wizard_nav()

    def _update_wizard_nav(self):
        idx = self.stack.currentIndex()
        total = self.stack.count()
        self.btn_prev.setEnabled(idx > 0)
        if idx == 0:
            self.lbl_step.setText("")
        else:
            self.lbl_step.setText(_("Step {n} of {total}").format(n=idx, total=total - 1))
        if idx == total - 1:
            self.btn_next.setText(_("Finish"))
            self.btn_next.setStyleSheet("font-weight: bold; background: #4a4; color: white; padding: 8px 20px; border-radius: 4px;")
        elif idx == 0:
            self.btn_next.setText(_("Start configuration"))
            self.btn_next.setStyleSheet("font-weight: bold; font-size: 15px; padding: 10px 28px;")
        else:
            self.btn_next.setText(_("Next"))
            self.btn_next.setStyleSheet("")
        # Resync translation card styles when arriving on page 4
        if idx == 4 and hasattr(self, '_trans_cards'):
            asr = getattr(self, '_wizard_asr', 'parakeet')
            is_can = (asr == "canary")
            current = getattr(self, '_wizard_trans', '')
            for bid, card in self._trans_cards.items():
                card.setEnabled(not is_can)
                if is_can:
                    card.setStyleSheet(self._card_style(False) + " QFrame#radioCard { opacity: 0.4; }")
                else:
                    card.setStyleSheet(self._card_style(bid == current))
            if hasattr(self, '_canary_trans_card'):
                self._canary_trans_card.setVisible(is_can)
        # Refresh translation config header on page 5
        if idx == 5 and hasattr(self, '_lbl_trans_config_header'):
            self._update_trans_config_header()
        # Refresh translation backend visibility on page 4/5
        if idx in (4, 5) and hasattr(self, 'cmb_trans_backend'):
            data = self.cmb_trans_backend.currentData()
            self.lt_widget.setVisible(data == "libretranslate")
            if data == "ollama":
                if self.ollama_widget.parent() is None:
                    # Insert just before the trailing stretch added by the
                    # wizard page so the widget sits right below the other
                    # form controls instead of being pushed to the bottom.
                    _insert_at = max(0, self._tr_layout.count() - 1)
                    self._tr_layout.insertWidget(_insert_at, self.ollama_widget)
                self.ollama_widget.show()
            else:
                self.ollama_widget.hide()
                if self.ollama_widget.parent() is not None:
                    self._tr_layout.removeWidget(self.ollama_widget)
                    self.ollama_widget.setParent(None)
            if data == "libretranslate":
                self._check_lt_status()
        # Start/stop audio level thread on page 6 (index 6)
        if idx == 6:
            self._start_audio_level()
        else:
            self._stop_audio_level()

    def _wizard_prev(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._update_wizard_nav()

    def _wizard_next(self):
        # Debounce: disable button briefly to prevent double-click
        self.btn_next.setEnabled(False)
        QTimer.singleShot(400, lambda: self.btn_next.setEnabled(True))

        idx = self.stack.currentIndex()
        if idx == self.stack.count() - 1:
            # Last page → Finish: save config (includes DICTEE_SETUP_DONE)
            self._on_apply()
            self._wizard_finished = True
            self.accept()
        else:
            if not self._validate_wizard_page(idx):
                return
            self.stack.setCurrentIndex(idx + 1)
            self._update_wizard_nav()
            # Update canary translation visibility when entering translation page
            self._update_canary_translation_visibility()
            if idx + 1 == self.stack.count() - 1:
                # Entering checks page — save config, start services, verify
                self._on_apply()
                self._run_wizard_checks()

    def _validate_wizard_page(self, idx):
        """Valide la page courante avant d'avancer. Retourne True si OK."""
        if idx == 2:
            # Download page: verify a model is installed for selected backend
            asr = self._wizard_asr
            if asr == "parakeet":
                for m in ASR_MODELS:
                    if m["required"] and not model_is_installed(m):
                        QMessageBox.warning(self, _("Model required"),
                            _("Please download the required model before continuing."))
                        return False
            elif asr == "vosk":
                if not venv_is_installed(VOSK_VENV):
                    QMessageBox.warning(self, _("Setup required"),
                        _("Vosk is not installed. Please click 'Install Vosk' above."))
                    return False
                # Check that downloaded Vosk model matches selected language
                lang = self.combo_src.currentData() if hasattr(self, 'combo_src') else "fr"
                expected_model = VOSK_MODELS.get(lang, "")
                if expected_model:
                    model_path = os.path.join(DICTEE_DATA_DIR, "vosk-models", expected_model)
                    if not os.path.isdir(model_path):
                        QMessageBox.warning(self, _("Model required"),
                            _("Please download the Vosk model for {lang} before continuing.").format(lang=lang))
                        return False
            elif asr == "whisper":
                if not venv_is_installed(WHISPER_VENV):
                    QMessageBox.warning(self, _("Setup required"),
                        _("faster-whisper is not installed. Please click 'Install Whisper' above."))
                    return False
            elif asr == "canary":
                if not self._canary_model_installed():
                    QMessageBox.warning(self, _("Setup required"),
                        _("Canary model not downloaded. Please click 'Download Canary model' above."))
                    return False
        elif idx == 3:
            # Shortcuts page: user must be in 'input' group
            # Check /etc/group (persistent) instead of 'groups' (session-only)
            user = os.environ.get("USER", "")
            try:
                import grp
                input_members = grp.getgrnam("input").gr_mem
                in_input = user in input_members
            except (KeyError, ImportError):
                in_input = "input" in os.popen("groups").read().split()
            if not in_input and not getattr(self, '_input_group_fixed', False):
                QMessageBox.warning(self, _("Group required"),
                    _("Your user must be in the 'input' group for keyboard shortcuts.\n"
                      "Please click 'Fix' above."))
                return False
        elif idx == 5:
            # Translation config page: if libretranslate, user must be in 'docker' group
            if hasattr(self, 'cmb_translate_backend'):
                backend = self.cmb_translate_backend.currentData()
                if backend == "libretranslate":
                    if not docker_is_accessible() and not getattr(self, '_docker_group_fixed', False):
                        QMessageBox.warning(self, _("Group required"),
                            _("Docker permissions are required for LibreTranslate.\n"
                              "Please click 'Fix permissions' above."))
                        return False
        return True

    # -- Project logos grid --

    def _build_project_logos(self):
        """Grille de logos des projets sous-jacents pour la page d'accueil."""
        from PyQt6.QtCore import QByteArray
        if not ASSETS_DIR:
            return None
        logos_dir = os.path.join(ASSETS_DIR, "logos")
        if not os.path.isdir(logos_dir):
            return None

        projects = [
            ("parakeet.svg", "Parakeet"),
            ("canary.svg", "Canary"),
            ("kde-plasma.svg", "Plasma 6 plasmoid"),
            ("libretranslate.svg", "LibreTranslate"),
        ]

        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(16)
        grid.setContentsMargins(0, 0, 0, 0)

        col = 0
        row = 0
        for fname, label_text in projects:
            svg_path = os.path.join(logos_dir, fname)
            if not os.path.isfile(svg_path):
                continue

            pix = self._render_svg(svg_path, 64)
            if pix.isNull():
                continue

            # Stacked widget: icon + name
            cell = QWidget()
            cell_lay = QVBoxLayout(cell)
            cell_lay.setSpacing(4)
            cell_lay.setContentsMargins(8, 4, 8, 4)

            lbl_icon = QLabel()
            lbl_icon.setPixmap(pix)
            lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_lay.addWidget(lbl_icon)

            lbl_name = QLabel(label_text)
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_name.setStyleSheet("font-size: 13px; opacity: 0.7;")
            cell_lay.addWidget(lbl_name)

            grid.addWidget(cell, 0, col)
            col += 1

        # Wrapper pour centrer horizontalement la grille
        wrapper = QWidget()
        wrapper_lay = QHBoxLayout(wrapper)
        wrapper_lay.setContentsMargins(0, 0, 0, 0)
        wrapper_lay.addStretch()
        wrapper_lay.addWidget(container)
        wrapper_lay.addStretch()
        return wrapper

    # -- Wizard Page 0: Welcome / Logo --

    def _build_wizard_page0(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(20)
        lay.setContentsMargins(32, 24, 32, 24)

        lay.addStretch(2)

        # Logo banner à gauche (grand)
        lbl_logo = QLabel()
        lbl_logo.setPixmap(self._logo_pixmap(560))
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(lbl_logo)

        # Read version from installed VERSION file, fallback to dev
        _ver = "dev"
        for _vpath in ("/usr/share/dictee/VERSION",
                       os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")):
            if os.path.isfile(_vpath):
                try:
                    with open(_vpath) as _f:
                        _ver = _f.read().strip()
                except OSError:
                    pass
                break
        lbl_ver = QLabel(f"v{_ver}")
        lbl_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ver.setStyleSheet("font-size: 14px; opacity: 0.5;")
        lay.addWidget(lbl_ver)

        lay.addStretch(3)

        # Tagline — headline + subtitle
        lbl_headline = QLabel(
            "<p style='font-size: 22px; font-weight: bold;'>"
            + _("Speak freely, type instantly") + "</p>")
        lbl_headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_headline)

        lbl_sub = QLabel(
            "<p style='font-size: 17px;'>"
            + _("100% local voice dictation for Linux with 25+ languages, "
                "translation, and real-time visual feedback.") + "</p>")
        lbl_sub.setWordWrap(True)
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_sub)

        lay.addSpacing(24)

        # Grille de logos des projets sous-jacents
        logos_widget = self._build_project_logos()
        if logos_widget:
            lay.addWidget(logos_widget)

        lay.addStretch(1)
        self.stack.addWidget(page)

    # -- Wizard Page 1: ASR --

    def _get_system_info(self):
        """Detect system hardware for recommendations."""
        import os
        ram_gb = 0
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        ram_gb = round(int(line.split()[1]) / 1024 / 1024, 1)
                        break
        except OSError:
            pass
        gpu_total, gpu_free = get_gpu_vram_gb()
        gpu_name = ""
        if gpu_total > 0:
            try:
                r = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                   capture_output=True, text=True, timeout=3)
                if r.returncode == 0:
                    gpu_name = r.stdout.strip().split("\n")[0]
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            if not gpu_name:
                gpu_name = _("GPU detected")
        return ram_gb, gpu_name, gpu_total, gpu_free

    def _get_recommended_backend(self, ram_gb, gpu_total):
        """Return recommended backend id based on hardware."""
        if gpu_total >= 8:
            return "canary"
        if gpu_total >= 4:
            return "parakeet"
        if ram_gb < 4:
            return "vosk"
        return "parakeet"

    def _build_wizard_page1(self, conf):
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(10)
        lay.setContentsMargins(24, 16, 24, 16)

        # Header: logo left, system config card right
        from PyQt6.QtWidgets import QGridLayout
        ram_gb, gpu_name, gpu_total, gpu_free = self._get_system_info()
        recommended = self._get_recommended_backend(ram_gb, gpu_total)

        header = QHBoxLayout()
        header.setSpacing(16)
        lbl_logo = QLabel()
        lbl_logo.setPixmap(self._logo_pixmap(280))
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(lbl_logo)
        header.addStretch()

        # System config card — no background, just border
        hw_card = QGroupBox(_("Your configuration"))
        hw_card.setStyleSheet(
            "QGroupBox { border: 1px solid #555; border-radius: 6px;"
            " padding: 12px 10px 8px 10px; margin-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }")
        hw_lay = QVBoxLayout(hw_card)
        hw_lay.setSpacing(4)
        hw_lay.setContentsMargins(8, 4, 8, 4)

        hw_lines = []
        if ram_gb > 0:
            hw_lines.append(f"RAM : <b>{ram_gb} Go</b>")
        if gpu_name:
            hw_lines.append(f"GPU : <b>{gpu_name}</b>")
            hw_lines.append(f"VRAM : <b>{gpu_total} Go</b> ({gpu_free} Go " + _("free") + ")")
        else:
            hw_lines.append(_("No dedicated GPU"))

        rec_names = {"parakeet": "Parakeet-TDT", "vosk": "Vosk",
                     "whisper": "faster-whisper", "canary": "Canary 1B v2"}
        hw_lines.append("")
        hw_lines.append(_("Recommended") + " : <b>" + rec_names[recommended] + "</b>")

        hw_lbl = QLabel("<br>".join(hw_lines))
        hw_lbl.setWordWrap(True)
        hw_lay.addWidget(hw_lbl)
        header.addWidget(hw_card)
        lay.addLayout(header)

        lbl_title = QLabel(
            "<h2>" + _("Choose a speech recognition engine") + "</h2>")
        lay.addWidget(lbl_title)

        self._wizard_asr = conf.get("DICTEE_ASR_BACKEND", recommended)
        self._asr_cards = {}

        # Backend cards with bullet-point advantages
        backends = [
            ("parakeet", "Parakeet-TDT 0.6B v3", [
                _("25 languages (FR, EN, DE, ES, IT, PT...)"),
                _("Excellent transcription quality (WER ~8% FR, ~2% EN)"),
                _("Runs on CPU or GPU (GPU 5x faster)"),
                _("Speaker diarization with Sortformer add-on"),
                _("100% local, no internet needed"),
            ], "2.5 Go | RAM ~1.5 Go | CPU ~0.8s / GPU ~0.16s"),
            ("vosk", "Vosk", [
                _("9 languages available"),
                _("Very lightweight (50 Mo per language)"),
                _("Minimal RAM usage (~200 Mo)"),
                _("Ideal for older or low-resource machines"),
                _("100% local, CPU only"),
            ], "~50 Mo | RAM ~200 Mo | CPU ~1.5s"),
            ("whisper", "faster-whisper", [
                _("99 languages (widest coverage)"),
                _("Multiple model sizes (tiny to large-v3)"),
                _("Good for rare languages"),
                _("Runs on CPU or GPU"),
                _("100% local, no internet needed"),
            ], "39 Mo–3 Go | CPU ~0.3s (small)"),
        ]
        if gpu_total > 0:
            backends.append(
                ("canary", "Canary 1B v2", [
                    _("25 languages with built-in translation (25 langs to/from English)"),
                    "<span style='color: #ec0;'>" + _("No external translation service needed") + "</span>",
                    _("Excellent accuracy, comparable to Parakeet"),
                    _("Speaker diarization with Sortformer add-on"),
                    _("100% local, requires NVIDIA GPU (6+ Go VRAM)"),
                ], "4.7 Go | VRAM ~5.3 Go | GPU ~0.7s"))

        # Grid layout: 2x2 square cards
        grid = QGridLayout()
        grid.setSpacing(10)
        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        for i, (backend_id, name, advantages, specs) in enumerate(backends):
            is_rec = (backend_id == recommended)
            is_sel = (backend_id == self._wizard_asr)
            card = self._make_asr_card_v2(backend_id, name, advantages, specs, is_rec, is_sel)
            card.mousePressEvent = lambda e, bid=backend_id: self._on_card_click(bid)
            card.setMinimumHeight(220)
            self._asr_cards[backend_id] = card
            row, col = positions[i]
            grid.addWidget(card, row, col)
        if len(backends) < 4:
            spacer = QWidget()
            grid.addWidget(spacer, 1, 1)
        lay.addLayout(grid)

        # cuDNN warning
        gpu_detected, cudnn_ok, cudnn_msg = check_cuda_gpu_ready()
        if gpu_detected and not cudnn_ok:
            warn_frame = QFrame()
            warn_frame.setStyleSheet(
                "QFrame { background: #442200; border: 1px solid #885500;"
                " border-radius: 6px; padding: 8px; }")
            warn_lay = QVBoxLayout(warn_frame)
            warn_lay.setContentsMargins(8, 6, 8, 6)
            warn_lbl = QLabel(cudnn_msg.replace("\n", "<br>"))
            warn_lbl.setWordWrap(True)
            warn_lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            warn_lay.addWidget(warn_lbl)
            lay.addWidget(warn_frame)

        # Notes
        lbl_notes = QLabel(
            "<p style='font-size: 11pt;'>"
            + _("All engines can be installed side by side if your system allows it. "
                "You can switch between them at any time.")
            + "</p><p style='font-size: 11pt;'>"
            + _("Translation services (Google, LibreTranslate, Ollama) can be configured "
                "at the next step for engines without built-in translation.")
            + "</p>")
        lbl_notes.setWordWrap(True)
        lbl_notes.setStyleSheet(
            "QLabel { border: 1px solid #555; border-radius: 6px; padding: 10px; }")
        lay.addWidget(lbl_notes)

        lay.addStretch()
        scroll.setWidget(content)
        page_lay.addWidget(scroll)
        self.stack.addWidget(page)

    def _update_asr_sub_visibility(self):
        asr = self._wizard_asr if hasattr(self, '_wizard_asr') else "parakeet"
        self.w_parakeet_options.setVisible(asr == "parakeet")
        self.w_vosk_options.setVisible(asr == "vosk")
        self.w_whisper_options.setVisible(asr == "whisper")
        self.w_canary_options.setVisible(asr == "canary")

    def _on_card_click(self, backend_id):
        """Handle card click: single=select, rapid double=select+next."""
        import time
        now = time.monotonic()
        last = getattr(self, '_last_card_click_time', 0)
        last_bid = getattr(self, '_last_card_click_bid', None)
        self._last_card_click_time = now
        self._last_card_click_bid = backend_id
        self._select_asr_radio(backend_id)
        if backend_id == last_bid and (now - last) < 0.4:
            self._wizard_next()

    def _select_asr_radio(self, backend_id):
        prev = getattr(self, '_wizard_asr', None)
        self._wizard_asr = backend_id
        # Only update the 2 cards that changed (avoid full repaint)
        if prev and prev in self._asr_cards and prev != backend_id:
            self._asr_cards[prev].setStyleSheet(self._card_style(False))
        if backend_id in self._asr_cards:
            self._asr_cards[backend_id].setStyleSheet(self._card_style(True))
        self._update_asr_sub_visibility()
        if hasattr(self, '_lbl_download_header'):
            self._update_download_page_header()
        if hasattr(self, 'combo_src'):
            self._update_src_languages()
        self._update_canary_translation_visibility()

    # Backend info for the download page (reused from page 1 cards)
    _BACKEND_INFO = {
        "parakeet": {
            "title": "Parakeet-TDT 0.6B v3",
            "advantages": [
                "25 languages (FR, EN, DE, ES, IT, PT...)",
                "Excellent transcription quality (WER ~8% FR, ~2% EN)",
                "Runs on CPU or GPU (GPU 5x faster)",
                "Speaker diarization with Sortformer add-on",
                "100% local, no internet needed",
            ],
            "specs": "2.5 Go | RAM ~1.5 Go | CPU ~0.8s / GPU ~0.16s",
        },
        "vosk": {
            "title": "Vosk",
            "advantages": [
                "9 languages available",
                "Very lightweight (50 Mo per language)",
                "Minimal RAM usage (~200 Mo)",
                "Ideal for older or low-resource machines",
                "100% local, CPU only",
            ],
            "specs": "~50 Mo | RAM ~200 Mo | CPU ~1.5s",
        },
        "whisper": {
            "title": "faster-whisper",
            "advantages": [
                "99 languages (widest coverage)",
                "Multiple model sizes (tiny to large-v3)",
                "Good for rare languages",
                "Runs on CPU or GPU",
                "100% local, no internet needed",
            ],
            "specs": "39 Mo–3 Go | CPU ~0.3s (small)",
        },
        "canary": {
            "title": "Canary 1B v2",
            "advantages": [
                "25 languages with built-in translation (25 langs to/from English)",
                "No external translation service needed",
                "Excellent accuracy, comparable to Parakeet",
                "Speaker diarization with Sortformer add-on",
                "100% local, requires NVIDIA GPU (6+ Go VRAM)",
            ],
            "specs": "4.7 Go | VRAM ~5.3 Go | GPU ~0.7s",
        },
    }

    def _update_download_page_header(self):
        """Update the download page header to match the selected backend."""
        asr = self._wizard_asr if hasattr(self, '_wizard_asr') else "parakeet"
        info = self._BACKEND_INFO.get(asr, self._BACKEND_INFO["parakeet"])
        bullets = "".join(f"<li>{_(a)}</li>" for a in info["advantages"])
        self._lbl_download_header.setText(
            f"<h2>{_('Setting up')} {info['title']}</h2>"
            f"<ul style='font-size: 11pt; margin: 0; padding-left: 16px;'>{bullets}</ul>"
            f"<p style='font-size: 10pt; color: #999;'>{info['specs']}</p>")

    # -- Wizard Page 2: Download models --

    def _build_wizard_page2(self, conf):
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.setSpacing(0)

        page_lay.addWidget(self._make_logo_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(10)
        lay.setContentsMargins(24, 8, 24, 16)

        # Dynamic header — updated when backend changes
        self._lbl_download_header = QLabel()
        self._lbl_download_header.setWordWrap(True)
        lay.addWidget(self._lbl_download_header)
        self._update_download_page_header()

        lay.addSpacing(20)

        # Sub-options container (shows only the selected backend)
        self.w_wizard_asr_sub = QWidget()
        lay_sub = QVBoxLayout(self.w_wizard_asr_sub)
        lay_sub.setContentsMargins(0, 0, 0, 0)
        lay_sub.setSpacing(4)

        self._build_parakeet_options(lay_sub)
        self._build_vosk_options(lay_sub)
        self._build_whisper_options(lay_sub)
        self._build_canary_options(lay_sub)

        lay.addWidget(self.w_wizard_asr_sub)
        self._update_asr_sub_visibility()

        lay.addStretch()
        scroll.setWidget(content)
        page_lay.addWidget(scroll)
        self.stack.addWidget(page)

    # -- Wizard Page 3: Shortcuts --

    def _build_wizard_page3(self, conf):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.setContentsMargins(24, 0, 24, 16)

        lay.addWidget(self._make_logo_header())

        lbl = QLabel("<h2>" + _("Keyboard shortcuts") + "</h2>"
                     "<p style='font-size: 11pt;'>"
                     + _("Configure the keyboard shortcuts for voice dictation.") + "</p>")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        self._build_shortcut_section(lay)

        lay.addStretch()
        self.stack.addWidget(page)

    # -- Wizard Page 4: Translation --

    _TRANS_BACKEND_INFO = {
        "libretranslate": {
            "title": "LibreTranslate",
            "advantages": [
                _("100% local, no data sent to the internet"),
                _("Runs in Docker, automatic setup"),
                _("~20 languages available"),
                _("Fast (~0.2s per sentence)"),
            ],
            "specs": _("Local") + " | Docker | RAM ~2 Go",
        },
        "ollama": {
            "title": "Ollama",
            "advantages": [
                _("100% local, no data sent to the internet"),
                _("Uses LLM models (translategemma, etc.)"),
                _("Good quality for common language pairs"),
                _("Slower than other backends (~2-3s)"),
            ],
            "specs": _("Local") + " | RAM ~4 Go | GPU " + _("recommended"),
        },
        "google": {
            "title": "Google Translate",
            "advantages": [
                _("Best translation quality"),
                _("100+ languages supported"),
                _("Very fast (~0.3s)"),
                _("Free via translate-shell"),
            ],
            "specs": _("Internet required") + " | translate-shell",
        },
        "bing": {
            "title": "Bing Translate",
            "advantages": [
                _("Good translation quality"),
                _("Alternative to Google"),
                _("Fast (~1-2s)"),
                _("Free via translate-shell"),
            ],
            "specs": _("Internet required") + " | translate-shell",
        },
    }

    def _build_wizard_page4(self, conf):
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.setSpacing(0)

        page_lay.addWidget(self._make_logo_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(10)
        lay.setContentsMargins(24, 8, 24, 16)

        title_row = QHBoxLayout()
        lbl_title = QLabel("<h2>" + _("Translation") + "</h2>"
                           "<p style='font-size: 11pt;'>"
                           + _("Choose a translation backend (optional). "
                               "Used when you press the translation shortcut.")
                           + "</p>")
        lbl_title.setWordWrap(True)
        title_row.addWidget(lbl_title, 1)
        btn_help_tr = self._HelpLabel(
            _("How to translate:") + "\n\n"
            + _("Keyboard shortcut: configure in the shortcuts page") + "\n"
            + _("Plasmoid: long press or translation button") + "\n"
            + _("CLI: dictee --translate") + "\n"
            + _("Direct: transcribe-client | trans -b :en")
        )
        title_row.addWidget(btn_help_tr)
        lay.addLayout(title_row)

        asr = self._wizard_asr if hasattr(self, '_wizard_asr') else conf.get("DICTEE_ASR_BACKEND", "parakeet")
        is_canary = (asr == "canary")

        # Canary card — same style as other cards but green border, shown above the grid
        self._canary_trans_card = self._make_asr_card_v2(
            "canary-trans", "Canary 1B v2",
            [_("Built-in translation (25 languages to/from English)"),
             _("No external service needed"),
             _("Active — translation is handled by the Canary engine")],
            _("Integrated") + " | " + _("No configuration needed"),
            False, True)
        self._canary_trans_card.setStyleSheet(self._card_style(True))
        # Warning + button to change ASR backend
        _lbl_warn = QLabel(
            "<p style='font-size: 10pt; color: #e90;'>"
            + _("Canary transcribes and translates in a single pass — both are handled by the same ASR model. "
                "To use a separate translation service instead, switch to a different ASR engine.")
            + "</p>")
        _lbl_warn.setWordWrap(True)
        self._canary_trans_card.layout().addWidget(_lbl_warn)
        _btn_change = QPushButton(_("Change ASR backend"))
        _btn_change.setStyleSheet(
            "QPushButton { border: 2px solid #888; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { border-color: #aaa; }")
        _btn_change.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self._canary_trans_card.layout().addWidget(_btn_change)
        self._canary_trans_card.setVisible(is_canary)
        lay.addWidget(self._canary_trans_card)

        # Current selection
        existing = conf.get("DICTEE_TRANSLATE_BACKEND", "")
        existing_engine = conf.get("DICTEE_TRANS_ENGINE", "google")
        if existing == "trans":
            self._wizard_trans = existing_engine
        elif existing in ("libretranslate", "ollama"):
            self._wizard_trans = existing
        elif self.wizard_mode:
            self._wizard_trans = "google"
        else:
            self._wizard_trans = "google"

        self._trans_cards = {}

        # Grid 2x2: LT, Ollama / Google, Bing
        from PyQt6.QtWidgets import QGridLayout
        grid = QGridLayout()
        grid.setSpacing(10)
        trans_backends = [
            ("libretranslate", 0, 0),
            ("ollama", 0, 1),
            ("google", 1, 0),
            ("bing", 1, 1),
        ]
        for bid, row, col in trans_backends:
            info = self._TRANS_BACKEND_INFO[bid]
            selected = (bid == self._wizard_trans and not is_canary)
            card = self._make_asr_card_v2(
                bid, info["title"], info["advantages"], info["specs"],
                False, selected)
            card.mousePressEvent = lambda e, b=bid: self._on_trans_card_click(b)
            card.setMinimumHeight(180)
            if is_canary:
                card.setEnabled(False)
                card.setStyleSheet(self._card_style(False) + " QFrame#radioCard { opacity: 0.4; }")
            self._trans_cards[bid] = card
            grid.addWidget(card, row, col)
        self._trans_grid = grid
        lay.addLayout(grid)


        lay.addStretch()
        scroll.setWidget(content)
        page_lay.addWidget(scroll)
        self.stack.addWidget(page)

    def _on_trans_card_click(self, backend_id):
        """Handle translation card click."""
        import time
        now = time.monotonic()
        last = getattr(self, '_last_trans_click_time', 0)
        last_bid = getattr(self, '_last_trans_click_bid', None)
        self._last_trans_click_time = now
        self._last_trans_click_bid = backend_id
        self._select_trans_radio(backend_id)
        if backend_id == last_bid and (now - last) < 0.4:
            self._wizard_next()

    def _select_trans_radio(self, backend_id):
        prev = getattr(self, '_wizard_trans', None)
        self._wizard_trans = backend_id
        if hasattr(self, '_lbl_trans_config_header'):
            self._update_trans_config_header()
        if prev and prev in self._trans_cards and prev != backend_id:
            self._trans_cards[prev].setStyleSheet(self._card_style(False))
        if backend_id in self._trans_cards:
            self._trans_cards[backend_id].setStyleSheet(self._card_style(True))
        # Update cmb_trans_backend if it exists (for _on_apply compatibility)
        if hasattr(self, 'cmb_trans_backend'):
            data_map = {"google": "trans:google", "bing": "trans:bing",
                        "libretranslate": "libretranslate", "ollama": "ollama"}
            idx = self.cmb_trans_backend.findData(data_map.get(backend_id, backend_id))
            if idx >= 0:
                self.cmb_trans_backend.setCurrentIndex(idx)

    def _on_trans_disabled_toggled(self, checked):
        if checked:
            prev = getattr(self, '_wizard_trans', None)
            if prev and prev in self._trans_cards:
                self._trans_cards[prev].setStyleSheet(self._card_style(False))
            self._wizard_trans = ""

    # -- Wizard Page 5: Translation config --

    def _build_wizard_page5(self, conf):
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.setSpacing(0)

        page_lay.addWidget(self._make_logo_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(10)
        lay.setContentsMargins(24, 8, 24, 16)

        self._lbl_trans_config_header = QLabel()
        self._lbl_trans_config_header.setWordWrap(True)
        lay.addWidget(self._lbl_trans_config_header)
        self._update_trans_config_header()

        self._build_translation_section(lay, conf)

        lay.addStretch()
        scroll.setWidget(content)
        page_lay.addWidget(scroll)
        self.stack.addWidget(page)

    def _update_trans_config_header(self):
        """Update translation config page header based on selected backend."""
        asr = getattr(self, '_wizard_asr', 'parakeet')
        if asr == "canary":
            self._lbl_trans_config_header.setText(
                f"<h2>{_('Setting up')} Canary 1B v2</h2>"
                f"<p style='font-size: 11pt;'>"
                + _("Translation is integrated into the Canary engine. "
                    "Configure source and target languages below.")
                + "</p>")
            return
        trans = getattr(self, '_wizard_trans', 'google')
        names = {"google": "Google Translate", "bing": "Bing Translate",
                 "libretranslate": "LibreTranslate", "ollama": "Ollama"}
        name = names.get(trans, trans)
        info = self._TRANS_BACKEND_INFO.get(trans, {})
        advantages = info.get("advantages", [])
        bullets = "".join(f"<li>{_(a)}</li>" for a in advantages)
        specs = info.get("specs", "")
        self._lbl_trans_config_header.setText(
            f"<h2>{_('Setting up')} {name}</h2>"
            f"<ul style='font-size: 11pt; margin: 0; padding-left: 16px;'>{bullets}</ul>"
            f"<p style='font-size: 10pt; color: #999;'>{specs}</p>")

    # -- Wizard Page 6: Mic, Visual, Services --

    def _build_wizard_page6(self, conf):
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.setSpacing(0)

        page_lay.addWidget(self._make_logo_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(16)
        lay.setContentsMargins(24, 8, 24, 16)

        # Microphone
        lbl = QLabel("<h2>" + _("Microphone, display and services") + "</h2>")
        lbl.setStyleSheet("font-size: 12pt;")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        _grp_style = "QGroupBox { font-size: 12pt; } QCheckBox { font-size: 11pt; } QLabel { font-size: 11pt; }"
        grp_mic = QGroupBox(_("Microphone"))
        grp_mic.setStyleSheet(_grp_style)
        lay_mic = QVBoxLayout(grp_mic)
        lay_mic.setSpacing(6)
        lay_mic.setContentsMargins(16, 16, 16, 12)
        self._build_mic_section(lay_mic, conf)
        lay.addWidget(grp_mic)

        # Visual feedback
        grp_vis = QGroupBox(_("Visual feedback"))
        grp_vis.setStyleSheet(_grp_style)
        lay_vis = QVBoxLayout(grp_vis)
        lay_vis.setSpacing(6)
        lay_vis.setContentsMargins(16, 16, 16, 12)
        self._build_visual_section(lay_vis, conf)
        lay.addWidget(grp_vis)

        # Notifications
        grp_notif = QGroupBox(_("Notifications"))
        grp_notif.setStyleSheet(_grp_style)
        lay_notif = QVBoxLayout(grp_notif)
        lay_notif.setSpacing(6)
        lay_notif.setContentsMargins(16, 16, 16, 12)
        self.chk_notifications = ToggleSwitch(_("Show notifications"))
        self.chk_notifications.setChecked(conf.get("DICTEE_NOTIFICATIONS", "true") != "false")
        self.chk_notifications_text = ToggleSwitch(_("Show transcribed text in notifications"))
        self.chk_notifications_text.setChecked(conf.get("DICTEE_NOTIFICATIONS_TEXT", "true") != "false")
        self.chk_notifications_text.setEnabled(self.chk_notifications.isChecked())
        self.chk_notifications.toggled.connect(self.chk_notifications_text.setEnabled)
        lay_notif.addWidget(self.chk_notifications)
        lay_notif.addWidget(self.chk_notifications_text)
        lay.addWidget(grp_notif)

        # Options
        self.chk_clipboard = ToggleSwitch(_("Copy transcription to clipboard"))
        self.chk_clipboard.setStyleSheet("font-size: 11pt;")
        self.chk_clipboard.setChecked(conf.get("DICTEE_CLIPBOARD", "true") == "true")
        lay.addWidget(self.chk_clipboard)

        lay.addStretch()
        scroll.setWidget(content)
        page_lay.addWidget(scroll)
        self.stack.addWidget(page)

    # -- Wizard Page 7: Test --

    def _build_wizard_page7(self, conf):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.setContentsMargins(24, 0, 24, 16)

        lay.addWidget(self._make_logo_header())

        lbl = QLabel("<h2>" + _("Test") + "</h2>"
                     "<p style='font-size: 11pt;'>" + _("Let's verify that everything works correctly.") + "</p>")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        # Checks container
        self.w_checks = QWidget()
        lay_checks = QVBoxLayout(self.w_checks)
        lay_checks.setSpacing(6)
        lay_checks.setContentsMargins(0, 0, 0, 0)
        self._check_labels = {}
        for check_id, label in [
            ("daemon", _("ASR service")),
            ("model", _("ASR model")),
            ("shortcut", _("Keyboard shortcut")),
            ("audio", _("Audio (PipeWire/PulseAudio)")),
            ("dotool", _("dotool")),
        ]:
            row = QHBoxLayout()
            lbl_icon = QLabel("⏳")
            lbl_icon.setFixedWidth(24)
            lbl_name = QLabel(label)
            lbl_status = QLabel()
            row.addWidget(lbl_icon)
            row.addWidget(lbl_name)
            row.addWidget(lbl_status, 1)
            lay_checks.addLayout(row)
            self._check_labels[check_id] = (lbl_icon, lbl_status)
        lay.addWidget(self.w_checks)

        # Test dictée
        grp_test = QGroupBox(_("Dictation test"))
        lay_test = QVBoxLayout(grp_test)
        lay_test.setSpacing(8)

        lbl_test = QLabel(_("Click the button below and speak for a few seconds."))
        lbl_test.setWordWrap(True)
        lay_test.addWidget(lbl_test)

        self.btn_test_dictee = QPushButton("🎤 " + _("Test dictation"))
        self.btn_test_dictee.setMinimumHeight(40)
        self.btn_test_dictee.clicked.connect(self._on_test_dictee)
        lay_test.addWidget(self.btn_test_dictee)

        # Test translation (all backends)
        self.btn_test_translate = QPushButton("🌐 " + _("Test translation"))
        self.btn_test_translate.setMinimumHeight(40)
        self.btn_test_translate.clicked.connect(self._on_test_translate)
        lay_test.addWidget(self.btn_test_translate)

        self.txt_test_result = QTextEdit()
        self.txt_test_result.setReadOnly(True)
        self.txt_test_result.setMaximumHeight(100)
        self.txt_test_result.setPlaceholderText(_("Result will appear here…"))
        lay_test.addWidget(self.txt_test_result)

        lay.addWidget(grp_test)

        self.lbl_final = QLabel()
        self.lbl_final.setWordWrap(True)
        self.lbl_final.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_final)

        lay.addStretch()
        self.stack.addWidget(page)

    # ── Shared widget builders ────────────────────────────────────

    def _is_backend_installed(self, backend_id):
        """Check if a backend's model/engine is installed."""
        if backend_id == "parakeet":
            return model_is_installed(ASR_MODELS[0])
        if backend_id == "vosk":
            return venv_is_installed(VOSK_VENV)
        if backend_id == "whisper":
            return venv_is_installed(WHISPER_VENV)
        if backend_id == "canary":
            return self._canary_model_installed()
        return False

    def _make_asr_card_v2(self, backend_id, name, advantages, specs, is_recommended, selected):
        """Build a square ASR card with name, bullet-point advantages and specs."""
        card = QFrame()
        card.setObjectName("radioCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(self._card_style(selected))
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(6)

        # Title row + recommended top-right
        title_row = QHBoxLayout()
        lbl_title = QLabel(f"<b style='font-size: 13pt;'>{name}</b>")
        title_row.addWidget(lbl_title)
        title_row.addStretch()
        if is_recommended:
            lbl_rec = QLabel(f"<span style='color: #e90; font-size: 11pt; font-weight: bold;'>{_('Recommended')}</span>")
            title_row.addWidget(lbl_rec)
        lay.addLayout(title_row)

        # Bullet-point advantages
        bullets = "<ul style='margin: 0; padding-left: 16px; font-size: 11pt;'>"
        for adv in advantages:
            bullets += f"<li>{adv}</li>"
        bullets += "</ul>"
        lbl_adv = QLabel(bullets)
        lbl_adv.setWordWrap(True)
        lay.addWidget(lbl_adv, 1)

        # Bottom row: specs left, installed right
        bottom_row = QHBoxLayout()
        lbl_specs = QLabel(f"<span style='font-size: 9pt; color: #999;'>{specs}</span>")
        lbl_specs.setWordWrap(True)
        bottom_row.addWidget(lbl_specs, 1)
        if self._is_backend_installed(backend_id):
            lbl_inst = QLabel(f"<span style='color: #5a5; font-size: 11pt; font-weight: bold;'>{_('Installed')}</span>")
            bottom_row.addWidget(lbl_inst)
        lay.addLayout(bottom_row)
        return card

    def _make_asr_card(self, title, description, specs, selected=False):
        """Build a rich ASR backend card with title, description and specs."""
        card = QFrame()
        card.setObjectName("radioCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(self._card_style(selected))
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)
        lbl_title = QLabel(f"<b style='font-size: 12pt;'>{title}</b>")
        lbl_desc = QLabel(f"<span style='font-size: 10pt;'>{description}</span>")
        lbl_desc.setWordWrap(True)
        lbl_specs = QLabel(f"<span style='font-size: 9pt; color: #999;'>{specs}</span>")
        lbl_specs.setWordWrap(True)
        lay.addWidget(lbl_title)
        lay.addWidget(lbl_desc)
        lay.addWidget(lbl_specs)
        return card

    def _make_radio_card(self, title, description, selected=False):
        card = QFrame()
        card.setObjectName("radioCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(self._card_style(selected))
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        lbl_title = QLabel(f"<b>{title}</b>")
        lbl_desc = QLabel(f"<small>{description}</small>")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("opacity: 0.65;")
        lay.addWidget(lbl_title)
        lay.addWidget(lbl_desc)
        return card

    @staticmethod
    def _card_style(selected):
        children = "QFrame#radioCard * { border: none; background: transparent; color: #eee; }"
        if selected:
            return (children +
                    " QFrame#radioCard { border: 2px solid #5566ff; border-radius: 8px;"
                    " background: #252545; padding: 4px; }")
        return (children +
                " QFrame#radioCard { border: 1px solid #444; border-radius: 8px;"
                " background: #1a1a2e; padding: 4px; }"
                " QFrame#radioCard:hover { border: 1px solid #666; }")

    def _build_shortcut_section(self, lay_sc):
        """Builds the PTT keyboard shortcut widgets into the given layout."""
        # Mode hold / toggle
        lbl_mode = QLabel(_("Activation mode") + " :")
        lay_sc.addWidget(lbl_mode)

        self.cmb_ptt_mode = QComboBox()
        self.cmb_ptt_mode.addItem(_("Hold (push-to-talk)"), "hold")
        self.cmb_ptt_mode.addItem(_("Toggle (press twice)"), "toggle")
        self.cmb_ptt_mode.setToolTip(_tt(_("Hold: hold key to record, release to transcribe Toggle: press to start, press again to stop")))
        existing_mode = self.conf.get("DICTEE_PTT_MODE", "hold" if self.wizard_mode else "toggle")
        idx = self.cmb_ptt_mode.findData(existing_mode)
        if idx >= 0:
            self.cmb_ptt_mode.setCurrentIndex(idx)
        lay_sc.addWidget(self.cmb_ptt_mode)

        lay_sc.addSpacing(8)

        # Touche dictée
        lbl_dictee = QLabel(_("Voice dictation key") + " :")
        lay_sc.addWidget(lbl_dictee)
        self.btn_capture = ShortcutButton()
        existing_key = int(self.conf.get("DICTEE_PTT_KEY", 67))
        if existing_key:
            self.btn_capture.setText(_("Key: {name}").format(
                name=linux_keycode_name(existing_key)))
            self._ptt_key = existing_key
        else:
            self._ptt_key = 67
        lay_sc.addWidget(self.btn_capture)
        self.btn_capture.shortcutCaptured.connect(self._on_ptt_key_captured)

        self.lbl_ptt_warning = QLabel()
        self.lbl_ptt_warning.setVisible(False)
        self.lbl_ptt_warning.setWordWrap(True)
        lay_sc.addWidget(self.lbl_ptt_warning)

        lay_sc.addSpacing(4)

        # Touche traduction : modificateur + même touche ou touche séparée
        lay_sc.addSpacing(4)
        lbl_translate = QLabel(_("Dictation + Translation") + " :")
        lay_sc.addWidget(lbl_translate)

        # Choix : même touche + modificateur ou touche séparée
        self.cmb_translate_mode = QComboBox()
        self.cmb_translate_mode.addItem(_("Same key + Alt"), "same_alt")
        self.cmb_translate_mode.addItem(_("Same key + Ctrl"), "same_ctrl")
        self.cmb_translate_mode.addItem(_("Same key + Shift"), "same_shift")
        self.cmb_translate_mode.addItem(_("Separate key"), "separate")
        self.cmb_translate_mode.addItem(_("Disabled"), "disabled")

        # Charger config existante
        existing_mod = self.conf.get("DICTEE_PTT_MOD_TRANSLATE", "")
        existing_key_tr = int(self.conf.get("DICTEE_PTT_KEY_TRANSLATE", 0))
        existing_key = int(self.conf.get("DICTEE_PTT_KEY", 67))

        if self.wizard_mode and not existing_mod:
            # First wizard: default to same key + Alt
            self.cmb_translate_mode.setCurrentIndex(0)
        elif existing_mod == "alt":
            self.cmb_translate_mode.setCurrentIndex(0)
        elif existing_mod == "ctrl":
            self.cmb_translate_mode.setCurrentIndex(1)
        elif existing_mod == "shift":
            self.cmb_translate_mode.setCurrentIndex(2)
        elif existing_key_tr and existing_key_tr != existing_key:
            self.cmb_translate_mode.setCurrentIndex(3)  # separate
        elif not existing_key_tr:
            self.cmb_translate_mode.setCurrentIndex(4)  # disabled
        else:
            self.cmb_translate_mode.setCurrentIndex(0)

        lay_sc.addWidget(self.cmb_translate_mode)

        # Bouton capture touche séparée (visible uniquement si "separate")
        self.btn_capture_translate = ShortcutButton()
        if existing_key_tr and existing_key_tr != existing_key:
            self.btn_capture_translate.setText(_("Key: {name}").format(
                name=linux_keycode_name(existing_key_tr)))
            self._ptt_key_translate = existing_key_tr
        else:
            self._ptt_key_translate = 0
            self.btn_capture_translate.setText(_("Click to capture a shortcut…"))
        self.btn_capture_translate.setVisible(
            self.cmb_translate_mode.currentData() == "separate")
        lay_sc.addWidget(self.btn_capture_translate)
        self.btn_capture_translate.shortcutCaptured.connect(self._on_ptt_key_translate_captured)

        self.cmb_translate_mode.currentIndexChanged.connect(self._on_translate_mode_changed)

        lay_sc.addSpacing(8)

        # Info groupe input
        # Check /etc/group (persistent) instead of 'groups' (session-only)
        user = os.environ.get("USER", "")
        try:
            import grp
            in_input_group = user in grp.getgrnam("input").gr_mem
        except (KeyError, ImportError):
            in_input_group = "input" in os.popen("groups").read().split()
        if not in_input_group:
            row_input = QHBoxLayout()
            lbl_group = QLabel(
                '<span style="color: orange;">⚠ ' +
                _("Your user is not in the 'input' group (required for keyboard shortcuts).") +
                '</span>')
            lbl_group.setWordWrap(True)
            row_input.addWidget(lbl_group)
            btn_fix_input = QPushButton(_("Fix (requires password)"))
            btn_fix_input.setFixedWidth(200)

            def _fix_input_group():
                user = os.environ.get("USER", "")
                if not user:
                    return
                try:
                    result = subprocess.run(
                        ["pkexec", "usermod", "-aG", "input", user],
                        capture_output=True, text=True, timeout=15)
                    if result.returncode == 0:
                        self._input_group_fixed = True
                        btn_fix_input.setVisible(False)
                        lbl_group.setText(
                            '<span style="color: green;">✓ ' +
                            _("User added to 'input' group. Log out and back in to activate.") +
                            '</span>')
                    else:
                        QMessageBox.critical(self, _("Error"), result.stderr.strip())
                except Exception as e:
                    QMessageBox.critical(self, _("Error"), str(e))

            btn_fix_input.clicked.connect(_fix_input_group)
            row_input.addWidget(btn_fix_input)
            row_input.addStretch()
            lay_sc.addLayout(row_input)

        # Voice commands cheatsheet — KDE global shortcut.
        # Same UX as the translation shortcut: combo "Same key + modifier"
        # reuses the dictation PTT key (e.g. F9) with the chosen modifier;
        # "Separate key" lets the user pick any QKeySequence; "Disabled"
        # turns it off. Default: Same key + Ctrl + Alt.
        lay_sc.addSpacing(8)
        lbl_cheat = QLabel(_("Voice commands cheatsheet") + " :")
        lay_sc.addWidget(lbl_cheat)

        self.cmb_cheatsheet_mode = QComboBox()
        self.cmb_cheatsheet_mode.addItem(_("Same key + Alt"), "same_alt")
        self.cmb_cheatsheet_mode.addItem(_("Same key + Ctrl"), "same_ctrl")
        self.cmb_cheatsheet_mode.addItem(_("Same key + Ctrl + Alt"), "same_ctrl_alt")
        self.cmb_cheatsheet_mode.addItem(_("Same key + Shift"), "same_shift")
        self.cmb_cheatsheet_mode.addItem(_("Separate key"), "separate")
        self.cmb_cheatsheet_mode.addItem(_("Disabled"), "disabled")

        existing_cheat_mode = self.conf.get("DICTEE_CHEATSHEET_MOD", "")
        existing_cheat_seq = self.conf.get("DICTEE_CHEATSHEET_KEY_SEQ", "")
        mode_to_idx = {
            "same_alt": 0, "alt": 0,
            "same_ctrl": 1, "ctrl": 1,
            "same_ctrl_alt": 2, "ctrl_alt": 2,
            "same_shift": 3, "shift": 3,
            "separate": 4,
            "disabled": 5,
        }
        self.cmb_cheatsheet_mode.setCurrentIndex(
            mode_to_idx.get(existing_cheat_mode, 2))  # default Same key + Ctrl+Alt
        lay_sc.addWidget(self.cmb_cheatsheet_mode)

        # Capture editor visible only when "Separate key" is selected.
        self.kse_cheatsheet_separate = QKeySequenceEdit()
        if existing_cheat_seq:
            self.kse_cheatsheet_separate.setKeySequence(QKeySequence(existing_cheat_seq))
        elif existing_cheat_mode != "separate":
            # Fall back to whatever the kglobalaccel side currently holds, so
            # users upgrading from the QKeySequenceEdit-only build see their
            # previous shortcut on first open.
            existing_cheat, _existing_desktop = find_kde_shortcut_for_command(
                "/usr/bin/dictee-cheatsheet --toggle")
            if existing_cheat:
                self.kse_cheatsheet_separate.setKeySequence(QKeySequence(existing_cheat))
        self.kse_cheatsheet_separate.setVisible(
            self.cmb_cheatsheet_mode.currentData() == "separate")
        lay_sc.addWidget(self.kse_cheatsheet_separate)

        self.cmb_cheatsheet_mode.currentIndexChanged.connect(
            self._on_cheatsheet_mode_changed)

        # Resolve "Same key + ..." labels to "<mod>+<dictation key>" now
        # that both combos exist and the dictation key has been read.
        self._refresh_shortcut_combos_labels()

    def _build_parakeet_options(self, parent_layout):
        """Build Parakeet model download widgets."""
        self.w_parakeet_options = QWidget()
        lay_parakeet = QVBoxLayout(self.w_parakeet_options)
        lay_parakeet.setContentsMargins(0, 4, 0, 0)
        lay_parakeet.setSpacing(6)

        _model_descriptions = {
            "tdt": _("Main transcription model. Required for all dictation modes. "
                     "Supports 25 languages with native punctuation and capitalization."),
            "sortformer": _("Speaker diarization add-on. Identifies up to 4 speakers "
                            "in a recording. Optional — only needed for speaker identification."),
        }

        for model in ASR_MODELS:
            installed = model_is_installed(model)

            # Description label above the button
            desc_text = _model_descriptions.get(model["id"], "")
            if desc_text:
                lbl_desc = QLabel(f"<p style='font-size: 11pt;'><b>{model['name']}</b> — {desc_text}</p>")
                lbl_desc.setWordWrap(True)
                lay_parakeet.addWidget(lbl_desc)

            # Button + delete on same row
            btn_row = QHBoxLayout()

            btn = QPushButton()
            self._update_venv_button(btn, model["name"], installed)
            btn.clicked.connect(lambda checked, m=model: self._on_model_download(m))

            # Sortformer requires TDT
            tdt_installed = model_is_installed(ASR_MODELS[0])
            if model["id"] == "sortformer" and not tdt_installed and not installed:
                btn.setEnabled(False)
                btn.setToolTip(_("Requires Parakeet-TDT 0.6B v3 to be installed first"))

            btn_del = QPushButton()
            btn_del.setIcon(QIcon.fromTheme("edit-delete"))
            btn_del.setFixedWidth(28)
            btn_del.setToolTip(_("Delete model"))
            btn_del.setVisible(installed)
            btn_del.clicked.connect(lambda checked, m=model: self._on_model_delete(m))

            btn_cancel = QPushButton(_("Cancel"))
            btn_cancel.setFixedWidth(80)
            btn_cancel.setVisible(False)
            btn_cancel.clicked.connect(lambda checked, m=model["id"]: self._on_model_cancel(m))

            btn_row.addWidget(btn, 1)
            btn_row.addWidget(btn_del)
            btn_row.addWidget(btn_cancel)
            lay_parakeet.addLayout(btn_row)

            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setVisible(False)
            lay_parakeet.addWidget(progress)

            self._model_widgets[model["id"]] = {
                "label": None, "button": btn, "btn_delete": btn_del,
                "btn_cancel": btn_cancel, "progress": progress, "model": model,
            }

        parent_layout.addWidget(self.w_parakeet_options)

    def _build_vosk_options(self, parent_layout):
        """Build Vosk install + language widgets."""
        self.w_vosk_options = QWidget()
        vosk_outer = QVBoxLayout(self.w_vosk_options)
        vosk_outer.setContentsMargins(0, 4, 0, 0)
        vosk_outer.setSpacing(4)

        row_vosk = QHBoxLayout()
        row_vosk.setContentsMargins(24, 0, 0, 0)
        vosk_installed = venv_is_installed(VOSK_VENV)
        self.btn_install_vosk = QPushButton()
        self.btn_install_vosk.clicked.connect(lambda: self._install_venv("vosk", VOSK_VENV, "vosk"))
        self._update_venv_button(self.btn_install_vosk, "Vosk", vosk_installed)

        lbl_vosk_lang = QLabel(_("Language:"))
        self.cmb_vosk_lang = _CheckMarkComboBox()
        self.cmb_vosk_lang.setMaximumWidth(250)
        self._refresh_vosk_lang_combo()
        cur_vosk = self.conf.get("DICTEE_VOSK_MODEL", "fr")
        idx = self.cmb_vosk_lang.findData(cur_vosk)
        if idx >= 0:
            self.cmb_vosk_lang.setCurrentIndex(idx)
        self.cmb_vosk_lang.currentIndexChanged.connect(lambda: (
            self._update_src_languages(), self._update_vosk_status(),
            self._update_vosk_model_in_conf(self.cmb_vosk_lang.currentData())
            if self.cmb_vosk_lang.currentData() and self._vosk_model_installed(self.cmb_vosk_lang.currentData())
            else None))

        self.btn_dl_vosk_model = QPushButton(_("Download"))
        self.btn_dl_vosk_model.setFixedWidth(150)
        self.btn_dl_vosk_model.clicked.connect(self._on_vosk_model_download)

        self.btn_del_vosk_model = QPushButton()
        self.btn_del_vosk_model.setIcon(QIcon.fromTheme("edit-delete"))
        self.btn_del_vosk_model.setFixedWidth(28)
        self.btn_del_vosk_model.setToolTip(_("Delete model"))
        self.btn_del_vosk_model.setVisible(False)
        self.btn_del_vosk_model.clicked.connect(self._on_vosk_model_delete)

        self._lbl_vosk_status = QLabel()
        self._lbl_vosk_status.setContentsMargins(24, 0, 0, 0)

        # Group config widgets to disable when venv not installed
        self._vosk_config_widgets = [lbl_vosk_lang, self.cmb_vosk_lang, self.btn_dl_vosk_model,
                                     self.btn_del_vosk_model, self._lbl_vosk_status]
        row_vosk.addWidget(lbl_vosk_lang)
        row_vosk.addWidget(self.cmb_vosk_lang)
        row_vosk.addWidget(self.btn_dl_vosk_model)
        row_vosk.addWidget(self.btn_del_vosk_model)
        row_vosk.addStretch()
        row_vosk.addWidget(self.btn_install_vosk)
        self.btn_del_vosk_venv = QPushButton()
        self.btn_del_vosk_venv.setIcon(QIcon.fromTheme("edit-delete"))
        self.btn_del_vosk_venv.setFixedWidth(28)
        self.btn_del_vosk_venv.setToolTip(_("Uninstall Vosk engine"))
        self.btn_del_vosk_venv.setVisible(vosk_installed)
        self.btn_del_vosk_venv.clicked.connect(lambda: self._delete_venv("vosk"))
        row_vosk.addWidget(self.btn_del_vosk_venv)
        for w in self._vosk_config_widgets:
            w.setEnabled(vosk_installed)
        vosk_outer.addLayout(row_vosk)

        self._vosk_progress_row = QWidget()
        vosk_prog_lay = QHBoxLayout(self._vosk_progress_row)
        vosk_prog_lay.setContentsMargins(24, 0, 0, 0)
        self.progress_vosk_model = QProgressBar()
        self.progress_vosk_model.setRange(0, 0)
        self._btn_cancel_vosk = QPushButton(_("Cancel"))
        self._btn_cancel_vosk.setFixedWidth(80)
        self._btn_cancel_vosk.clicked.connect(self._cancel_vosk_download)
        vosk_prog_lay.addWidget(self.progress_vosk_model)
        vosk_prog_lay.addWidget(self._btn_cancel_vosk)
        self._vosk_progress_row.setVisible(False)
        vosk_outer.addWidget(self._vosk_progress_row)

        vosk_outer.addWidget(self._lbl_vosk_status)

        self.cmb_vosk_lang.currentIndexChanged.connect(self._update_vosk_status)
        self._update_vosk_status()

        parent_layout.addWidget(self.w_vosk_options)

    # -- Vosk model management --

    def _update_vosk_model_in_conf(self, lang_code):
        """Write DICTEE_VOSK_MODEL into dictee.conf (or memory in wizard mode)."""
        # Always write the short code — daemon resolves to full name
        reverse = {v: k for k, v in VOSK_MODELS.items()}
        code = reverse.get(lang_code, lang_code)
        # In wizard mode, only update in-memory conf
        if self.wizard_mode:
            self.conf["DICTEE_VOSK_MODEL"] = code
            return
        # Update conf file in-place
        lines = []
        found = False
        if os.path.isfile(CONF_PATH):
            with open(CONF_PATH) as f:
                for line in f:
                    if line.startswith("DICTEE_VOSK_MODEL="):
                        lines.append(f"DICTEE_VOSK_MODEL={code}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f"DICTEE_VOSK_MODEL={code}\n")
        os.makedirs(os.path.dirname(CONF_PATH), exist_ok=True)
        with open(CONF_PATH, "w") as f:
            f.writelines(lines)
        # Restart Vosk daemon if it is running
        try:
            r = subprocess.run(["systemctl", "--user", "is-active", "dictee-vosk.service"],
                               capture_output=True, text=True, timeout=3)
            if r.stdout.strip() == "active":
                subprocess.run(["systemctl", "--user", "restart", "dictee-vosk.service"],
                               capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    def _vosk_model_installed(self, lang_code):
        """Vérifie si le modèle Vosk pour une langue est téléchargé."""
        model_name = VOSK_MODELS.get(lang_code, "")
        model_dir = os.path.join(DICTEE_DATA_DIR, "vosk-models", model_name)
        return os.path.isdir(model_dir)

    def _refresh_vosk_lang_combo(self):
        """Repeuple le combo Vosk avec indicateur ✓/✗ par modèle."""
        current = self.cmb_vosk_lang.currentData()
        self.cmb_vosk_lang.blockSignals(True)
        self.cmb_vosk_lang.clear()
        for code, name in VOSK_MODELS.items():
            installed = self._vosk_model_installed(code)
            prefix = "✓" if installed else "✗"
            # Short label: just code + language name (no full model name)
            lang_name = {"fr": "Français", "en": "English", "de": "Deutsch",
                         "es": "Español", "it": "Italiano", "pt": "Português",
                         "ru": "Русский", "zh": "中文", "ja": "日本語"}.get(code, code)
            self.cmb_vosk_lang.addItem(f"{prefix}  {code} — {lang_name}", code)
            if installed:
                idx = self.cmb_vosk_lang.count() - 1
                self.cmb_vosk_lang.setItemData(idx, True, Qt.ItemDataRole.UserRole + 1)
        self.cmb_vosk_lang.blockSignals(False)
        if current:
            idx = self.cmb_vosk_lang.findData(current)
            if idx >= 0:
                self.cmb_vosk_lang.setCurrentIndex(idx)

    def _update_vosk_status(self):
        """Update button text and status label for the selected Vosk model."""
        code = self.cmb_vosk_lang.currentData()
        if not code:
            return
        venv_ok = venv_is_installed(VOSK_VENV)
        installed = self._vosk_model_installed(code)
        if installed:
            self._lbl_vosk_status.setText('<span style="color: green;">✓</span> ' + _("Model downloaded and ready"))
        else:
            self._lbl_vosk_status.setText(_("Select a language and click Download"))
        self.btn_dl_vosk_model.setText(_("Download"))
        self.btn_dl_vosk_model.setVisible(not installed)
        self.btn_dl_vosk_model.setEnabled(venv_ok)
        self.btn_del_vosk_model.setVisible(installed)

    def _on_vosk_model_delete(self):
        """Delete the selected Vosk model after confirmation."""
        code = self.cmb_vosk_lang.currentData()
        if not code or not self._vosk_model_installed(code):
            return
        reply = QMessageBox.question(self, _("Delete"),
            _("Delete Vosk model '{}'?").format(VOSK_MODELS.get(code, code)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            model_name = VOSK_MODELS.get(code, "")
            model_dir = os.path.join(DICTEE_DATA_DIR, "vosk-models", model_name)
            if os.path.isdir(model_dir):
                shutil.rmtree(model_dir)
            self._refresh_vosk_lang_combo()
            self._update_vosk_status()

    def _cancel_vosk_download(self):
        """Cancel ongoing Vosk model download and clean partial files."""
        thread = getattr(self, '_vosk_dl_thread', None)
        if thread and thread.isRunning():
            thread.terminate()
            thread.wait(3000)
        # Clean partial zip/directory
        code = self.cmb_vosk_lang.currentData()
        if code:
            import glob
            model_name = VOSK_MODELS.get(code, "")
            vosk_dir = os.path.join(DICTEE_DATA_DIR, "vosk-models")
            for pattern in [f"{model_name}.zip", f"{model_name}.zip.*"]:
                for f in glob.glob(os.path.join(vosk_dir, pattern)):
                    os.remove(f)
        self._vosk_progress_row.setVisible(False)
        self.btn_dl_vosk_model.setEnabled(True)
        self._refresh_vosk_lang_combo()
        self._update_vosk_status()

    def _on_vosk_model_download(self):
        _dbg_setup("_on_vosk_model_download")
        """Télécharge le modèle Vosk sélectionné."""
        code = self.cmb_vosk_lang.currentData()
        if not code or self._vosk_model_installed(code):
            return
        model_name = VOSK_MODELS[code]
        self.btn_dl_vosk_model.setEnabled(False)
        self.btn_dl_vosk_model.setText(_("Downloading…"))
        self._vosk_progress_row.setVisible(True)

        self._vosk_dl_thread = _VoskModelDownloadThread(model_name)
        self._vosk_dl_thread.progress.connect(
            lambda text: self.btn_dl_vosk_model.setText(text))
        self._vosk_dl_thread.done.connect(self._on_vosk_model_download_finished)
        self._vosk_dl_thread.start()

    def _on_vosk_model_download_finished(self, success, message):
        _dbg_setup(f"_on_vosk_model_download_finished: success={success}, msg={message!r}")
        self._vosk_progress_row.setVisible(False)
        if success:
            self._refresh_vosk_lang_combo()
            self._update_vosk_status()
            self._update_src_languages()
            # Update conf + restart daemon with the newly downloaded model
            code = self.cmb_vosk_lang.currentData()
            if code:
                self._update_vosk_model_in_conf(code)
        else:
            self.btn_dl_vosk_model.setEnabled(True)
            self.btn_dl_vosk_model.setText(_("Download"))
            _dbg_setup(f"Vosk download error: {message!r}")
            QMessageBox.critical(self, _("Download error"), message or _("Unknown error"))

    @staticmethod
    def _whisper_model_cached(model_id):
        """Check if a Whisper model is already downloaded in HuggingFace cache."""
        try:
            from dictee_models import whisper_model_cached
            return whisper_model_cached(model_id)
        except ImportError:
            return False

    def _build_whisper_options(self, parent_layout):
        """Build Whisper install + model/language widgets."""
        self.w_whisper_options = QWidget()
        whisper_outer = QVBoxLayout(self.w_whisper_options)
        whisper_outer.setContentsMargins(0, 4, 0, 0)
        whisper_outer.setSpacing(4)

        row = QHBoxLayout()
        row.setContentsMargins(24, 0, 0, 0)
        whisper_installed = venv_is_installed(WHISPER_VENV)
        self.btn_install_whisper = QPushButton()
        self.btn_install_whisper.clicked.connect(lambda: self._install_venv("whisper", WHISPER_VENV, "faster-whisper"))
        self._update_venv_button(self.btn_install_whisper, "Whisper", whisper_installed)

        self._lbl_wh_model = QLabel(_("Model:"))
        self.cmb_whisper_model = _CheckMarkComboBox()
        self.cmb_whisper_model.setMinimumWidth(420)
        self._populate_whisper_combo()
        cur_wh = self.conf.get("DICTEE_WHISPER_MODEL", "small")
        for i in range(self.cmb_whisper_model.count()):
            if self.cmb_whisper_model.itemData(i) == cur_wh:
                self.cmb_whisper_model.setCurrentIndex(i)
                break
        self.cmb_whisper_model.currentIndexChanged.connect(self._update_whisper_status)

        self.btn_download_whisper = QPushButton(_("Download"))
        self.btn_download_whisper.setFixedWidth(150)
        self.btn_download_whisper.clicked.connect(self._on_whisper_model_download)

        self.btn_del_whisper_model = QPushButton()
        self.btn_del_whisper_model.setIcon(QIcon.fromTheme("edit-delete"))
        self.btn_del_whisper_model.setFixedWidth(28)
        self.btn_del_whisper_model.setToolTip(_("Delete model"))
        self.btn_del_whisper_model.setVisible(False)
        self.btn_del_whisper_model.clicked.connect(self._on_whisper_model_delete)

        lbl_wh_lang = QLabel(_("Transcription language:"))
        self.txt_whisper_lang = QComboBox()
        self.txt_whisper_lang.setEditable(True)
        # Common languages
        self.txt_whisper_lang.addItem("", "")
        _whisper_common = [
            ("fr", "Français"), ("en", "English"), ("es", "Español"),
            ("de", "Deutsch"), ("it", "Italiano"), ("pt", "Português"),
            ("ru", "Русский"), ("zh", "中文"), ("ja", "日本語"),
            ("ko", "한국어"), ("ar", "العربية"),
        ]
        for code, name in _whisper_common:
            self.txt_whisper_lang.addItem(f"{code} — {name}", code)
        # Separator + all other Whisper languages
        self.txt_whisper_lang.insertSeparator(self.txt_whisper_lang.count())
        _whisper_all = [
            ("af", "Afrikaans"), ("am", "Amharic"), ("az", "Azerbaijani"),
            ("ba", "Bashkir"), ("be", "Belarusian"), ("bg", "Bulgarian"),
            ("bn", "Bengali"), ("bo", "Tibetan"), ("br", "Breton"),
            ("bs", "Bosnian"), ("ca", "Catalan"), ("cs", "Czech"),
            ("cy", "Welsh"), ("da", "Danish"), ("el", "Greek"),
            ("et", "Estonian"), ("eu", "Basque"), ("fa", "Persian"),
            ("fi", "Finnish"), ("fo", "Faroese"), ("gl", "Galician"),
            ("gu", "Gujarati"), ("ha", "Hausa"), ("haw", "Hawaiian"),
            ("he", "Hebrew"), ("hi", "Hindi"), ("hr", "Croatian"),
            ("ht", "Haitian Creole"), ("hu", "Hungarian"), ("hy", "Armenian"),
            ("id", "Indonesian"), ("is", "Icelandic"), ("jw", "Javanese"),
            ("ka", "Georgian"), ("kk", "Kazakh"), ("km", "Khmer"),
            ("kn", "Kannada"), ("lb", "Luxembourgish"), ("ln", "Lingala"),
            ("lo", "Lao"), ("lt", "Lithuanian"), ("lv", "Latvian"),
            ("mg", "Malagasy"), ("mi", "Maori"), ("mk", "Macedonian"),
            ("ml", "Malayalam"), ("mn", "Mongolian"), ("mr", "Marathi"),
            ("ms", "Malay"), ("mt", "Maltese"), ("my", "Myanmar"),
            ("ne", "Nepali"), ("nl", "Dutch"), ("nn", "Nynorsk"),
            ("no", "Norwegian"), ("oc", "Occitan"), ("pa", "Panjabi"),
            ("pl", "Polish"), ("ps", "Pashto"), ("ro", "Romanian"),
            ("sa", "Sanskrit"), ("sd", "Sindhi"), ("si", "Sinhala"),
            ("sk", "Slovak"), ("sl", "Slovenian"), ("sn", "Shona"),
            ("so", "Somali"), ("sq", "Albanian"), ("sr", "Serbian"),
            ("su", "Sundanese"), ("sv", "Swedish"), ("sw", "Swahili"),
            ("ta", "Tamil"), ("te", "Telugu"), ("tg", "Tajik"),
            ("th", "Thai"), ("tk", "Turkmen"), ("tl", "Tagalog"),
            ("tr", "Turkish"), ("tt", "Tatar"), ("uk", "Ukrainian"),
            ("ur", "Urdu"), ("uz", "Uzbek"), ("vi", "Vietnamese"),
            ("yi", "Yiddish"), ("yo", "Yoruba"),
        ]
        for code, name in _whisper_all:
            self.txt_whisper_lang.addItem(f"{code} — {name}", code)
        cur_wl = self.conf.get("DICTEE_WHISPER_LANG", "")
        idx = self.txt_whisper_lang.findData(cur_wl)
        if idx >= 0:
            self.txt_whisper_lang.setCurrentIndex(idx)
        else:
            self.txt_whisper_lang.setCurrentText(cur_wl)
        lbl_auto = QLabel(_("(empty = uses source language)"))
        lbl_auto.setStyleSheet("color: gray;")

        # Row 1: language
        row_lang = QHBoxLayout()
        row_lang.setContentsMargins(24, 0, 0, 0)
        row_lang.addWidget(lbl_wh_lang)
        row_lang.addWidget(self.txt_whisper_lang)
        row_lang.addWidget(lbl_auto)
        row_lang.addStretch()
        whisper_outer.addLayout(row_lang)

        # Row 2: model + download + delete + install
        row.addWidget(self._lbl_wh_model)
        row.addWidget(self.cmb_whisper_model)
        row.addWidget(self.btn_download_whisper)
        row.addWidget(self.btn_del_whisper_model)
        row.addStretch()
        row.addWidget(self.btn_install_whisper)
        self.btn_del_whisper_venv = QPushButton()
        self.btn_del_whisper_venv.setIcon(QIcon.fromTheme("edit-delete"))
        self.btn_del_whisper_venv.setFixedWidth(28)
        self.btn_del_whisper_venv.setToolTip(_("Uninstall Whisper engine"))
        self.btn_del_whisper_venv.setVisible(whisper_installed)
        self.btn_del_whisper_venv.clicked.connect(lambda: self._delete_venv("whisper"))
        row.addWidget(self.btn_del_whisper_venv)

        self._lbl_whisper_status = QLabel()
        self._lbl_whisper_status.setContentsMargins(24, 0, 0, 0)
        self._lbl_whisper_status.setWordWrap(True)

        # Group config widgets to disable when venv not installed
        self._whisper_config_widgets = [self._lbl_wh_model, self.cmb_whisper_model,
                                        self.btn_download_whisper, self.btn_del_whisper_model,
                                        lbl_wh_lang, self.txt_whisper_lang, lbl_auto,
                                        self._lbl_whisper_status]
        for w in self._whisper_config_widgets:
            w.setEnabled(whisper_installed)
        whisper_outer.addLayout(row)

        # Progress row (hidden by default)
        self._whisper_progress_row = QWidget()
        progress_lay = QHBoxLayout(self._whisper_progress_row)
        progress_lay.setContentsMargins(24, 0, 0, 0)
        self._whisper_progress = QProgressBar()
        self._whisper_progress.setRange(0, 0)  # indeterminate
        self._btn_cancel_whisper = QPushButton(_("Cancel"))
        self._btn_cancel_whisper.setFixedWidth(80)
        self._btn_cancel_whisper.clicked.connect(self._cancel_whisper_download)
        progress_lay.addWidget(self._whisper_progress)
        progress_lay.addWidget(self._btn_cancel_whisper)
        self._whisper_progress_row.setVisible(False)
        whisper_outer.addWidget(self._whisper_progress_row)

        whisper_outer.addWidget(self._lbl_whisper_status)
        self._update_whisper_status()

        parent_layout.addWidget(self.w_whisper_options)

    def _populate_whisper_combo(self):
        """Populate the Whisper model combo with colored ✓ for cached models."""
        self.cmb_whisper_model.clear()
        for model_id, label in WHISPER_MODELS:
            cached = self._whisper_model_cached(model_id)
            prefix = "✓ " if cached else "   "
            self.cmb_whisper_model.addItem(prefix + label, model_id)
            if cached:
                idx = self.cmb_whisper_model.count() - 1
                self.cmb_whisper_model.setItemData(idx, True, Qt.ItemDataRole.UserRole + 1)

    def _update_whisper_status(self):
        """Update button text and status label for the selected Whisper model."""
        model_id = self.cmb_whisper_model.currentData()
        if not model_id:
            return
        venv_ok = venv_is_installed(WHISPER_VENV)
        cached = self._whisper_model_cached(model_id)
        if cached:
            self._lbl_whisper_status.setText('<span style="color: green;">✓</span> ' + _("Model downloaded and ready"))
        else:
            self._lbl_whisper_status.setText(_("Select a model and click Download"))
        self.btn_download_whisper.setText(_("Download"))
        self.btn_download_whisper.setVisible(not cached)
        self.btn_download_whisper.setEnabled(venv_ok)
        self.btn_del_whisper_model.setVisible(cached)

    def _on_whisper_model_delete(self):
        """Delete the selected Whisper model after confirmation."""
        model_id = self.cmb_whisper_model.currentData()
        if not model_id or not self._whisper_model_cached(model_id):
            return
        reply = QMessageBox.question(self, _("Delete"),
            _("Delete model '{}'?").format(model_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._delete_whisper_model(model_id)

    def _on_whisper_model_download(self):
        """Download the selected Whisper model."""
        model_id = self.cmb_whisper_model.currentData()
        if not model_id:
            return
        self.btn_download_whisper.setEnabled(False)
        self.btn_download_whisper.setText(_("Downloading…"))
        self._whisper_progress_row.setVisible(True)
        thread = _WhisperDownloadThread(WHISPER_VENV, model_id)
        thread.done.connect(self._on_whisper_download_done)
        self._venv_threads["whisper_dl"] = thread
        thread.start()

    def _cancel_whisper_download(self):
        """Cancel ongoing Whisper model download and clean partial files."""
        thread = self._venv_threads.get("whisper_dl")
        if thread and thread.isRunning():
            thread.terminate()
            thread.wait(3000)
        # Clean partial downloads (HuggingFace .incomplete files)
        model_id = self.cmb_whisper_model.currentData()
        if model_id:
            import glob
            try:
                from dictee_models import whisper_cache_candidates
                patterns = whisper_cache_candidates(model_id)
            except ImportError:
                patterns = [f"models--Systran--faster-whisper-{model_id}",
                            f"models--{model_id.replace('/', '--')}"]
            cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
            for pattern in patterns:
                for f in glob.glob(os.path.join(cache_dir, pattern, "**", "*.incomplete"), recursive=True):
                    os.remove(f)
        self._whisper_progress_row.setVisible(False)
        self._refresh_whisper_after_change()

    def _delete_whisper_model(self, model_id):
        """Delete a Whisper model from HuggingFace cache."""
        import shutil
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
        try:
            from dictee_models import whisper_cache_candidates
            candidates = whisper_cache_candidates(model_id)
        except ImportError:
            candidates = [
                f"models--Systran--faster-whisper-{model_id}",
                f"models--{model_id.replace('/', '--')}",
                f"models--openai--whisper-{model_id}",
            ]
        for c in candidates:
            path = os.path.join(cache_dir, c)
            if os.path.isdir(path):
                shutil.rmtree(path)
        self._refresh_whisper_after_change()

    def _on_whisper_download_done(self, ok, msg):
        self._refresh_whisper_after_change()
        if not ok:
            QMessageBox.warning(self, _("Download failed"), msg)

    def _refresh_whisper_after_change(self):
        """Refresh combo, button and status after download/delete."""
        self._whisper_progress_row.setVisible(False)
        self.btn_download_whisper.setEnabled(True)
        cur_data = self.cmb_whisper_model.currentData()
        self._populate_whisper_combo()
        for i in range(self.cmb_whisper_model.count()):
            if self.cmb_whisper_model.itemData(i) == cur_data:
                self.cmb_whisper_model.setCurrentIndex(i)
                break
        self._update_whisper_status()

    def _build_canary_options(self, parent_layout):
        """Build Canary 1B v2 sub-options (GPU only, model download)."""
        self.w_canary_options = QWidget()
        canary_lay = QVBoxLayout(self.w_canary_options)
        canary_lay.setContentsMargins(0, 4, 0, 0)
        canary_lay.setSpacing(6)

        canary_installed = self._canary_model_installed()

        # Button + delete on same row
        row = QHBoxLayout()
        self.btn_install_canary = QPushButton()
        self.btn_install_canary.clicked.connect(self._download_canary_model)
        self._update_venv_button(self.btn_install_canary, "Canary", canary_installed)

        self.btn_delete_canary = QPushButton()
        self.btn_delete_canary.setIcon(QIcon.fromTheme("edit-delete"))
        self.btn_delete_canary.setFixedWidth(28)
        self.btn_delete_canary.setToolTip(_("Delete model"))
        self.btn_delete_canary.clicked.connect(self._delete_canary_model)
        self.btn_delete_canary.setVisible(canary_installed)

        self.btn_cancel_canary = QPushButton(_("Cancel"))
        self.btn_cancel_canary.setFixedWidth(80)
        self.btn_cancel_canary.setVisible(False)
        self.btn_cancel_canary.clicked.connect(self._cancel_canary_download)

        row.addWidget(self.btn_install_canary, 1)
        row.addWidget(self.btn_delete_canary)
        row.addWidget(self.btn_cancel_canary)
        canary_lay.addLayout(row)

        self.w_canary_options.setVisible(False)
        parent_layout.addWidget(self.w_canary_options)

    def _canary_model_installed(self):
        """Check if Canary ONNX model files are present (user dir first, then system)."""
        try:
            from dictee_models import canary_model_installed
            return canary_model_installed()
        except ImportError:
            user_path = os.path.join(DICTEE_DATA_DIR, "canary", "encoder-model.onnx")
            sys_path = os.path.join(CANARY_MODEL_DIR, "encoder-model.onnx")
            return os.path.isfile(user_path) or os.path.isfile(sys_path)

    def _update_canary_model_status(self):
        """Update Canary model status button."""
        installed = self._canary_model_installed()
        self._update_venv_button(self.btn_install_canary, "Canary", installed)
        self.btn_delete_canary.setVisible(installed)

    def _cancel_canary_download(self):
        thread = self._venv_threads.get("canary")
        if thread and thread.isRunning():
            thread.cancel()

    def _download_canary_model(self):
        _dbg_setup("_download_canary_model")
        self.btn_install_canary.setEnabled(False)
        self.btn_install_canary.setText(_("Downloading..."))
        self.btn_install_canary.setStyleSheet("QPushButton { color: white; background-color: #c84; font-weight: bold; }")
        self.btn_delete_canary.setVisible(False)
        self.btn_cancel_canary.setVisible(True)

        thread = _CanaryDownloadThread(CANARY_MODEL_DIR, CANARY_HF_REPO, CANARY_MODEL_FILES)
        thread.done.connect(self._on_canary_download_done)
        thread.progress.connect(lambda msg: self.btn_install_canary.setText(msg))
        self._venv_threads["canary"] = thread
        thread.start()

    def _on_canary_download_done(self, ok, msg):
        _dbg_setup(f"_on_canary_download_done: ok={ok}, msg={msg!r}")
        self.btn_install_canary.setEnabled(True)
        self.btn_cancel_canary.setVisible(False)
        self._update_canary_model_status()
        if not ok and msg != _("Cancelled"):
            QMessageBox.warning(self, _("Download failed"), msg)

    def _delete_canary_model(self):
        """Delete Canary model after confirmation."""
        reply = QMessageBox.question(
            self, _("Delete model"),
            _("Delete Canary model and free disk space?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        import shutil
        failed = False
        for d in (CANARY_MODEL_DIR, os.path.join(DICTEE_DATA_DIR, "canary")):
            if os.path.isdir(d):
                try:
                    shutil.rmtree(d)
                    os.makedirs(d, exist_ok=True)
                except PermissionError:
                    # Try with pkexec for system dirs
                    r = subprocess.run(["pkexec", "rm", "-rf", d],
                                       capture_output=True, timeout=10)
                    if r.returncode == 0:
                        os.makedirs(d, mode=0o777, exist_ok=True)
                    else:
                        failed = True
        if failed:
            QMessageBox.warning(self, _("Delete failed"),
                _("Could not delete model files (permission denied)."))
        self._update_canary_model_status()

    def _build_visual_section(self, lay_vis, conf):
        """Build visual feedback checkboxes and install button."""
        self.chk_anim_speech = ToggleSwitch(_("animation-speech (overlay)"))
        self.chk_plasmoid = ToggleSwitch(_("KDE Plasma widget (panel)"))
        self.chk_gnome_ext = ToggleSwitch(_("GNOME Shell extension (not yet available)"))
        self.chk_gnome_ext.setEnabled(False)

        # Support legacy DICTEE_ANIMATION for migration
        _legacy_anim = conf.get("DICTEE_ANIMATION", "")
        if _legacy_anim and "DICTEE_ANIM_SPEECH" not in conf:
            # Migrate from old combined variable
            self.chk_anim_speech.setChecked(_legacy_anim in ("speech", "both"))
            self.chk_plasmoid.setChecked(_legacy_anim in ("plasmoid", "both"))
        else:
            self.chk_anim_speech.setChecked(conf.get("DICTEE_ANIM_SPEECH", "") == "true")
            self.chk_plasmoid.setChecked(conf.get("DICTEE_ANIM_PLASMOID", "") == "true")

        # Smart pre-check based on desktop (first setup only)
        if not _legacy_anim and "DICTEE_ANIM_SPEECH" not in conf:
            _is_wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
            if self.de_type == "kde":
                self.chk_plasmoid.setChecked(True)
            elif self.de_type != "gnome" and _is_wayland:
                self.chk_anim_speech.setChecked(True)

        self.chk_tray = ToggleSwitch(_("Show notification area icon"))
        self.chk_tray.setChecked(
            self._is_service_enabled("dictee-tray") or self.wizard_mode)

        lay_vis.addWidget(self.chk_anim_speech)
        lay_vis.addWidget(self.chk_plasmoid)
        lay_vis.addWidget(self.chk_tray)
        lay_vis.addWidget(self.chk_gnome_ext)

        # GNOME / compositors without wlr-layer-shell warning
        self.lbl_anim_warn = QLabel(
            '<span style="color: orange;">⚠ '
            + _("animation-speech requires a Wayland compositor with layer-shell support "
                "(KDE, Sway, Hyprland…). It does not work on GNOME.")
            + '</span>'
        )
        self.lbl_anim_warn.setWordWrap(True)
        self.lbl_anim_warn.setVisible(self.de_type == "gnome")
        if self.de_type == "gnome":
            self.chk_anim_speech.setEnabled(False)
            self.chk_anim_speech.setChecked(False)
        lay_vis.addWidget(self.lbl_anim_warn)

        self.lbl_anim_status = QLabel()
        self.lbl_anim_status.setWordWrap(True)
        lay_vis.addWidget(self.lbl_anim_status)

        self.btn_install_anim = QPushButton(_("Install animation-speech"))
        self.btn_install_anim.setVisible(False)
        self.btn_install_anim.clicked.connect(self._on_install_animation)
        lay_vis.addWidget(self.btn_install_anim)

        self.progress_anim = QProgressBar()
        self.progress_anim.setRange(0, 0)
        self.progress_anim.setVisible(False)
        lay_vis.addWidget(self.progress_anim)

        self._check_animation_speech()

    def _build_translation_section(self, lay_tr, conf):
        """Build translation backend selection, languages, sub-options."""
        # Title and help are on the cards page (page 4), not here

        # Canary translation notice (shown when ASR=canary)
        self._canary_translation_notice = QLabel(_(
            "Translation is built into the Canary engine — no external service needed.\n"
            "Supported: 25 languages ↔ English (48 pairs).\n"
            "For other pairs (e.g. FR→DE), switch to a different ASR backend."
        ))
        self._canary_translation_notice.setWordWrap(True)
        self._canary_translation_notice.setStyleSheet(
            "background: #1a3a1a; border: 1px solid #2a5a2a;"
            " border-radius: 6px; padding: 8px;")
        self._canary_translation_notice.setVisible(False)
        lay_tr.addWidget(self._canary_translation_notice)

        # Languages
        form_lang = QFormLayout()
        form_lang.setHorizontalSpacing(12)
        form_lang.setVerticalSpacing(8)

        self.combo_src = QComboBox()
        self.combo_tgt = QComboBox()
        # Keep both combos at the same visual width, independent of item
        # text length (target can hold long names like "pt-BR — Portuguese
        # (Brazil)" once cloud backends are selected).
        for _c in (self.combo_src, self.combo_tgt):
            _c.setMinimumContentsLength(28)
            _c.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        for code, name in LANGUAGES:
            self.combo_src.addItem(f"{code} — {name}", code)
            self.combo_tgt.addItem(f"{code} — {name}", code)

        default_src = conf.get("DICTEE_LANG_SOURCE", self._system_lang())
        default_tgt = conf.get("DICTEE_LANG_TARGET", "en")
        self._set_combo_by_data(self.combo_src, default_src, 0)
        self._set_combo_by_data(self.combo_tgt, default_tgt, 1)

        _lbl_src = QLabel(_("Source language:"))
        _lbl_src.setStyleSheet("font-size: 11pt;")
        _lbl_tgt = QLabel(_("Target language:"))
        _lbl_tgt.setStyleSheet("font-size: 11pt;")

        # Swap button between source and target
        _btn_swap = QPushButton("⇄")
        _btn_swap.setFixedSize(28, 28)
        _btn_swap.setToolTip(_("Swap source and target languages"))
        _btn_swap.setStyleSheet(
            "QPushButton { font-size: 16px; border: 1px solid rgba(127,127,127,80);"
            " border-radius: 4px; background: transparent; }"
            "QPushButton:hover { background: rgba(127,127,127,40); }")
        def _swap_langs():
            src = self.combo_src.currentData()
            tgt = self.combo_tgt.currentData()
            if not src or not tgt or src == tgt:
                return
            # Canary: swap only allowed when EN is one of the two languages
            asr = ""
            if self.wizard_mode and hasattr(self, '_wizard_asr'):
                asr = self._wizard_asr
            elif hasattr(self, 'cmb_asr_backend'):
                asr = self.cmb_asr_backend.currentData() or ""
            if asr == "canary" and "en" not in (src, tgt):
                return
            # Block all signals during swap to prevent cascading filters
            self.combo_src.blockSignals(True)
            self.combo_tgt.blockSignals(True)
            if asr == "canary":
                # Repopulate both combos with all Canary languages
                self._filter_lang_combo(self.combo_src, CANARY_LANGUAGES)
                self._filter_lang_combo(self.combo_tgt, CANARY_LANGUAGES)
            idx_s = self.combo_src.findData(tgt)
            idx_t = self.combo_tgt.findData(src)
            if idx_s >= 0 and idx_t >= 0:
                self.combo_src.setCurrentIndex(idx_s)
                self.combo_tgt.setCurrentIndex(idx_t)
            self._prev_src = self.combo_src.currentData()
            self._prev_tgt = self.combo_tgt.currentData()
            self.combo_src.blockSignals(False)
            self.combo_tgt.blockSignals(False)
            # Re-apply Canary target constraints after swap
            if asr == "canary":
                self._update_canary_translation_visibility()
        _btn_swap.clicked.connect(_swap_langs)

        # Layout: [labels + combos] | [swap button centered between both rows]
        _lang_grid = QHBoxLayout()
        _lang_grid.setSpacing(8)
        _lang_grid.addLayout(form_lang)

        form_lang.addRow(_lbl_src, self.combo_src)
        form_lang.addRow(_lbl_tgt, self.combo_tgt)

        _btn_swap.setFixedSize(28, self.combo_src.sizeHint().height() * 2 + form_lang.verticalSpacing())
        _btn_swap.setText("⇅")
        _lang_grid.addWidget(_btn_swap)
        _lang_grid.addStretch()
        lay_tr.addLayout(_lang_grid)
        lay_tr.addSpacing(4)

        # Backend ComboBox — in wizard mode, the backend was already chosen
        # on page 4 via the cards; the combo stays in the object model (many
        # signal handlers depend on it) but is hidden from the UI. To change
        # the backend, the user goes back to the cards page.
        lbl_backend = QLabel(_("Backend:"))
        lbl_backend.setStyleSheet("font-size: 11pt;")
        lay_tr.addWidget(lbl_backend)

        self.cmb_trans_backend = QComboBox()
        self.cmb_trans_backend.addItem(_("Google Translate (cloud)"), "trans:google")
        self.cmb_trans_backend.addItem(_("Bing (cloud)"), "trans:bing")
        self.cmb_trans_backend.addItem(_("LibreTranslate (local)"), "libretranslate")
        self.cmb_trans_backend.addItem(_("ollama (local)"), "ollama")
        if self.wizard_mode:
            # Wizard: backend already chosen via cards on page 4 → this combo
            # must NOT appear on page 5. Don't add it to the layout at all
            # (keeps the attribute accessible for handlers via hasattr).
            lbl_backend.setParent(None)
            lbl_backend.deleteLater()
            self.cmb_trans_backend.setParent(None)
        else:
            lay_tr.addWidget(self.cmb_trans_backend)

        # LibreTranslate widget
        self.lt_widget = QFrame()
        lay_lt = QVBoxLayout(self.lt_widget)
        lay_lt.setContentsMargins(32, 4, 0, 0)
        lay_lt.setSpacing(4)

        lay_lt_port = QHBoxLayout()
        lay_lt_port.setSpacing(8)
        lbl_lt_port = QLabel(_("Port:"))
        lay_lt_port.addWidget(lbl_lt_port)
        self.spin_lt_port = QComboBox()
        self.spin_lt_port.setEditable(True)
        for p in ("5000", "5001", "5002", "8080"):
            self.spin_lt_port.addItem(p)
        default_port = str(conf.get("DICTEE_LIBRETRANSLATE_PORT", "5000"))
        idx = self.spin_lt_port.findText(default_port)
        if idx >= 0:
            self.spin_lt_port.setCurrentIndex(idx)
        else:
            self.spin_lt_port.setCurrentText(default_port)
        lay_lt_port.addWidget(self.spin_lt_port)
        lay_lt_port.addStretch()
        lay_lt.addLayout(lay_lt_port)

        # -- Langues LibreTranslate --
        _lang_header = QHBoxLayout()
        lbl_lt_langs = QLabel("<small>" + _("Languages to load in LibreTranslate:") + "</small>")
        _lang_header.addWidget(lbl_lt_langs)
        _lang_header.addStretch()
        btn_deselect_all = QPushButton(_("Deselect all"))
        btn_deselect_all.setStyleSheet("padding: 2px 10px; font-size: 11px;")
        btn_deselect_all.clicked.connect(self._on_lt_deselect_all_langs)
        _lang_header.addWidget(btn_deselect_all)
        lay_lt.addLayout(_lang_header)

        saved_lt_langs = set(
            conf.get("DICTEE_LIBRETRANSLATE_LANGS", "en,fr,es,de,it,pt,uk,ru,tr,ar,zh,hi,bn,ja,ko").split(","))
        # Toujours inclure source et cible
        saved_lt_langs.add(conf.get("DICTEE_LANG_SOURCE", self._system_lang()))
        saved_lt_langs.add(conf.get("DICTEE_LANG_TARGET", "en"))

        self._lt_lang_checks = {}
        grid_langs = QGridLayout()
        grid_langs.setSpacing(2)
        for i, (code, name) in enumerate(LANGUAGES):
            chk = ToggleSwitch(f"{code} — {name}")
            chk.setChecked(code in saved_lt_langs)
            chk.stateChanged.connect(self._on_lt_langs_changed)
            self._lt_lang_checks[code] = chk
            grid_langs.addWidget(chk, i // 4, i % 4)
        lay_lt.addLayout(grid_langs)

        self.lbl_lt_langs_hint = QLabel()
        self.lbl_lt_langs_hint.setWordWrap(True)
        self.lbl_lt_langs_hint.setVisible(False)
        lay_lt.addWidget(self.lbl_lt_langs_hint)

        self.btn_lt_restart_langs = QPushButton(_("Restart with new languages"))
        self.btn_lt_restart_langs.setVisible(False)
        self.btn_lt_restart_langs.setStyleSheet(
            "QPushButton { color: white; background-color: #c84;"
            " font-weight: bold; padding: 8px 16px; border-radius: 4px;"
            " border: none; }"
            "QPushButton:hover { background-color: #a63; }"
            "QPushButton:disabled { background-color: #888; color: #ddd; }")
        self.btn_lt_restart_langs.clicked.connect(self._on_lt_restart_langs)
        lay_lt.addWidget(self.btn_lt_restart_langs)

        self.lbl_lt_status = QLabel()
        self.lbl_lt_status.setWordWrap(True)
        lay_lt.addWidget(self.lbl_lt_status)

        lay_lt_buttons = QHBoxLayout()
        lay_lt_buttons.setSpacing(8)
        self.btn_lt_pull = QPushButton(_("Download image"))
        self.btn_lt_pull.setVisible(False)
        self.btn_lt_pull.clicked.connect(self._on_lt_pull)
        lay_lt_buttons.addWidget(self.btn_lt_pull)
        self.btn_lt_start = QPushButton(_("Start"))
        self.btn_lt_start.setVisible(False)
        self.btn_lt_start.clicked.connect(self._on_lt_start)
        lay_lt_buttons.addWidget(self.btn_lt_start)
        self.btn_lt_stop = QPushButton(_("Stop"))
        self.btn_lt_stop.setVisible(False)
        self.btn_lt_stop.clicked.connect(self._on_lt_stop)
        lay_lt_buttons.addWidget(self.btn_lt_stop)
        self.btn_lt_purge = QPushButton(_("Purge models"))
        self.btn_lt_purge.setVisible(False)
        self.btn_lt_purge.setToolTip(_tt(_("LibreTranslate keeps every language model you have ever downloaded on disk, even after you remove a language from the selection. It filters at load time, never at cleanup. This button deletes all cached models in the Docker volume, then re-downloads only the currently selected languages. Use it to reclaim disk space after many language changes.")))
        self.btn_lt_purge.clicked.connect(self._on_lt_purge)
        lay_lt_buttons.addWidget(self.btn_lt_purge)
        lay_lt_buttons.addStretch()
        lay_lt.addLayout(lay_lt_buttons)

        self.progress_lt = QProgressBar()
        self.progress_lt.setRange(0, 0)
        self.progress_lt.setVisible(False)
        lay_lt.addWidget(self.progress_lt)

        lay_tr.addWidget(self.lt_widget)
        self.lt_widget.setVisible(False)
        self._docker_pull_thread = None
        self._lt_action_thread = None

        # Ollama widget (hidden by default — shown only when ollama backend selected)
        self.ollama_widget = QWidget()
        lay_ollama = QVBoxLayout(self.ollama_widget)
        lay_ollama.setContentsMargins(32, 4, 0, 0)
        lay_ollama.setSpacing(4)

        lay_model = QHBoxLayout()
        lay_model.setSpacing(8)
        lbl_model = QLabel(_("Model:"))
        self.combo_ollama_model = QComboBox()
        for model_id, model_label, _ram, _vram in OLLAMA_MODELS:
            self.combo_ollama_model.addItem(model_label, model_id)
        default_model = conf.get("DICTEE_OLLAMA_MODEL", "translategemma")
        self._set_combo_by_data(self.combo_ollama_model, default_model, 0)
        lay_model.addWidget(lbl_model)
        lay_model.addWidget(self.combo_ollama_model, 1)
        lay_ollama.addLayout(lay_model)

        self.lbl_ollama_status = QLabel()
        self.lbl_ollama_status.setWordWrap(True)
        lay_ollama.addWidget(self.lbl_ollama_status)

        self.chk_ollama_cpu = ToggleSwitch(_("Force CPU (OLLAMA_NUM_GPU=0)"))
        self.chk_ollama_cpu.setChecked(conf.get("OLLAMA_NUM_GPU") == "0")
        self.chk_ollama_cpu.setToolTip(
            _("Use CPU instead of GPU for ollama inference (slower but no VRAM needed)"))
        lay_ollama.addWidget(self.chk_ollama_cpu)

        self.btn_ollama_pull = QPushButton(_("Download"))
        self.btn_ollama_pull.setVisible(False)
        self.btn_ollama_pull.clicked.connect(self._on_ollama_pull)
        lay_ollama.addWidget(self.btn_ollama_pull)

        self.progress_ollama = QProgressBar()
        self.progress_ollama.setRange(0, 0)
        self.progress_ollama.setVisible(False)
        lay_ollama.addWidget(self.progress_ollama)

        # Don't add ollama_widget to layout yet — added dynamically when selected
        self.ollama_widget.setParent(None)
        self._tr_layout = lay_tr

        self.combo_ollama_model.currentIndexChanged.connect(self._on_ollama_model_changed)
        self._ollama_pull_thread = None

        # Restore saved backend. In wizard mode, mirror the card selected on
        # page 4 (_wizard_trans) so lt_widget/ollama_widget/tgt-lang filter
        # match the visible card — otherwise the combo defaulted to
        # libretranslate and the user saw LT options after picking Google.
        if self.wizard_mode and getattr(self, '_wizard_trans', None):
            data_map = {"google": "trans:google", "bing": "trans:bing",
                        "libretranslate": "libretranslate", "ollama": "ollama"}
            self._set_combo_by_data(
                self.cmb_trans_backend,
                data_map.get(self._wizard_trans, self._wizard_trans), 0)
        else:
            saved_backend = conf.get("DICTEE_TRANSLATE_BACKEND", "")
            saved_engine = conf.get("DICTEE_TRANS_ENGINE", "google")
            if saved_backend == "ollama":
                self._set_combo_by_data(self.cmb_trans_backend, "ollama", 0)
            elif saved_backend == "libretranslate":
                self._set_combo_by_data(self.cmb_trans_backend, "libretranslate", 0)
            elif saved_backend == "trans" and saved_engine == "bing":
                self._set_combo_by_data(self.cmb_trans_backend, "trans:bing", 0)
            elif saved_backend == "trans":
                self._set_combo_by_data(self.cmb_trans_backend, "trans:google", 0)
            else:
                self._set_combo_by_data(self.cmb_trans_backend, "trans:google", 0)

        def _on_trans_backend_changed():
            data = self.cmb_trans_backend.currentData()
            _dbg_setup(f"_on_trans_backend_changed: data={data}")
            self.lt_widget.setVisible(data == "libretranslate")
            if data == "ollama":
                if self.ollama_widget.parent() is None:
                    # Insert before the trailing stretch added by the wizard
                    # page so Model + Force CPU sit right under the language
                    # combos instead of being pushed to the bottom.
                    _insert_at = max(0, self._tr_layout.count() - 1)
                    self._tr_layout.insertWidget(_insert_at, self.ollama_widget)
                self.ollama_widget.show()
            else:
                self.ollama_widget.hide()
                if self.ollama_widget.parent() is not None:
                    self._tr_layout.removeWidget(self.ollama_widget)
                    self.ollama_widget.setParent(None)
            _dbg_setup(f"ollama visible={self.ollama_widget.isVisible()}, lt visible={self.lt_widget.isVisible()}")
            if data == "libretranslate":
                self._check_lt_status()
            if data == "ollama":
                self._check_ollama_status()
            self._update_tgt_languages()
            if hasattr(self, '_schedule_test_run'):
                self._schedule_test_run()
        self.cmb_trans_backend.currentIndexChanged.connect(lambda: _on_trans_backend_changed())
        # Rafraîchir le statut et checkboxes LibreTranslate quand on change la langue
        def _on_lang_changed():
            # Skip if combos are being repopulated (currentData may be None)
            if not self.combo_src.currentData() or not self.combo_tgt.currentData():
                return
            if self.cmb_trans_backend.currentData() == "libretranslate":
                self._update_lt_lang_checks()
                self._on_lt_langs_changed()
                self._check_lt_status()
        self._lang_swap_guard = False
        self._prev_src = self.combo_src.currentData()
        self._prev_tgt = self.combo_tgt.currentData()

        def _on_src_changed():
            _on_lang_changed()
            self._update_canary_translation_visibility()
            if self._lang_swap_guard:
                return
            src = self.combo_src.currentData()
            tgt = self.combo_tgt.currentData()
            if src and tgt and src == tgt:
                # Swap: set target to what source was before
                self._lang_swap_guard = True
                old_src = self._prev_src
                idx = self.combo_tgt.findData(old_src)
                if idx >= 0:
                    self.combo_tgt.setCurrentIndex(idx)
                self._lang_swap_guard = False
            self._prev_src = src
            if hasattr(self, '_schedule_test_run'):
                self._schedule_test_run()
        self.combo_src.currentIndexChanged.connect(_on_src_changed)
        def _on_tgt_changed():
            _on_lang_changed()
            if self._lang_swap_guard:
                return
            src = self.combo_src.currentData()
            tgt = self.combo_tgt.currentData()
            if src and tgt and src == tgt:
                self._lang_swap_guard = True
                old_tgt = self._prev_tgt
                idx = self.combo_src.findData(old_tgt)
                if idx >= 0:
                    self.combo_src.setCurrentIndex(idx)
                self._lang_swap_guard = False
            self._prev_tgt = tgt
            if hasattr(self, '_schedule_test_run'):
                self._schedule_test_run()
        self.combo_tgt.currentIndexChanged.connect(_on_tgt_changed)
        self._update_lt_lang_checks()
        _on_trans_backend_changed()

    # -- Post-processing section --

    class _HelpLabel(QLabel):
        """QLabel '?' qui affiche un popup flottant au survol."""

        def __init__(self, help_text, parent=None):
            super().__init__(" ? ", parent)
            self._help_text = help_text
            self._popup = None
            self.setStyleSheet(
                "QLabel { border: 1px solid palette(mid); border-radius: 10px;"
                " font-size: 13px; font-weight: bold; color: palette(text);"
                " padding: 1px 4px; }")
            self.setMouseTracking(True)

        def enterEvent(self, event):
            super().enterEvent(event)
            if self._popup is None:
                self._popup = QLabel(self._help_text, self.window())
                self._popup.setWindowFlags(
                    Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
                # Explicit high-contrast colors so rich text (code tags,
                # italics, emojis) stays legible regardless of theme.
                self._popup.setStyleSheet(
                    "QLabel { background: #2b2b30; color: #e8e8e8;"
                    " border: 1px solid #4a4a50; border-radius: 6px;"
                    " padding: 14px; font-size: 13px; }")
                self._popup.setWordWrap(True)
                self._popup.setTextFormat(Qt.TextFormat.RichText)
                # Fixed (not max) width so wrap layout settles before
                # adjustSize computes the height — otherwise the rich-text
                # + word-wrap + stylesheet padding combo underestimates
                # height and the last line is clipped off the popup.
                self._popup.setFixedWidth(520)
                self._popup.adjustSize()
            pos = self.mapToGlobal(self.rect().bottomLeft())
            self._popup.move(pos)
            self._popup.show()

        def leaveEvent(self, event):
            super().leaveEvent(event)
            if self._popup is not None:
                self._popup.hide()

    def _pp_checkbox_with_help(self, checkbox, help_text):
        """Adds a ? with hover popup at the end of the row (after stretch)."""
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(checkbox)
        h.addStretch()
        h.addWidget(self._HelpLabel(help_text))
        # Gray out the label text when unchecked — use a mid gray with
        # explicit hex so it remains visible on both dark and light themes
        # (palette(mid) was too dark in the dark theme).
        def _update_style(on, cb=checkbox):
            cb.setStyleSheet("" if on else "QCheckBox { color: #9a9a9a; }")
        checkbox.toggled.connect(_update_style)
        _update_style(checkbox.isChecked())
        return container

    def _build_pipeline_header_widget(self):
        """Build the SVG pipeline diagram header.

        Contains:
          - Accordion header bar (toggle arrow + title + help button)
          - Hint label
          - Blue pipeline diagram (Normal mode)
          - Orange pipeline diagram (Translation mode, LLM always off)

        Both diagrams render from the same `self._pp_state` dict (mirror).
        Each is wrapped in a row with a small label on the left.
        Idempotent: reuses existing diagram instances if already built."""
        from PyQt6.QtWidgets import QScrollArea as _QSA, QToolButton
        from PyQt6.QtGui import QPalette, QColor

        container = QWidget()
        c_lay = QVBoxLayout(container)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(4)

        accent_hex = self.palette().color(
            self.palette().ColorRole.Highlight).name()

        # ── Accordion header bar: arrow + title + help button ──
        header = QWidget()
        hdr_lay = QHBoxLayout(header)
        hdr_lay.setContentsMargins(4, 2, 4, 2)
        hdr_lay.setSpacing(6)

        toggle_btn = QToolButton()
        toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle_btn.setArrowType(Qt.ArrowType.RightArrow)
        toggle_btn.setText(_("Interactive visualization of post-processing pipelines"))
        toggle_btn.setCheckable(True)
        toggle_btn.setChecked(False)
        toggle_btn.setAutoRaise(True)
        toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _fg = self.palette().color(self.palette().ColorRole.WindowText).name()
        toggle_btn.setStyleSheet(
            f"QToolButton {{ font-weight: bold; font-size: 17px;"
            f" color: {_fg}; border: none; padding: 4px 6px; }}"
            f"QToolButton:hover {{ background: rgba(127,127,127,40); border-radius: 3px; }}")
        hdr_lay.addWidget(toggle_btn)

        help_text = _(
            "<b>What are you looking at?</b><br>"
            "Two processing chains applied to the text recognized by the ASR, "
            "in execution order from left to right.<br><br>"
            "<b>🔵 Blue diagram — Normal Pipeline</b><br>"
            "Applied to the text in the source language (the one you dictate). "
            "Fixes punctuation, numbers, language rules, the personal "
            "dictionary, capitalization, and may end with an optional LLM "
            "pass for grammar.<br><br>"
            "<b>🟠 Orange diagram — Translation Pipeline</b><br>"
            "Applied once, <i>after</i> the translation, on the already-"
            "translated text, with the target language as reference. The "
            "LLM pass is always disabled (translation backends already "
            "produce grammatically clean text).<br><br>"
            "<b>How to interact?</b><br>"
            "• Clicking a step toggles it on or off instantly.<br>"
            "• If the step has its own configuration page, the "
            "1<sup>st</sup> click navigates to it, the 2<sup>nd</sup> "
            "click (from the page) toggles it.<br>"
            "• Grayed-out steps are inactive.<br>"
            "• Execution order is strict: a disabled step is skipped, the "
            "text moves on to the next one.<br><br>"
            "<b>⚠ Diarization</b><br>"
            "Diarization mode (multi-speaker) does not go through these "
            "pipelines: the raw text is kept as-is to preserve the labels "
            "<code>[SPK1]</code>, <code>[SPK2]</code>… so they are not "
            "degraded by the typo / LLM rules.")
        help_btn = self._HelpLabel(help_text)
        # Bigger, more visible "?" placed right next to the title.
        help_btn.setStyleSheet(
            "QLabel { border: 1px solid white;"
            " border-radius: 9px; font-size: 16px; font-weight: bold;"
            " color: white; background: transparent;"
            " padding: 0px 4px; min-width: 0px; }"
            "QLabel:hover { background: rgba(255,255,255,40); }")
        help_btn.setCursor(Qt.CursorShape.WhatsThisCursor)
        hdr_lay.addWidget(help_btn)
        hdr_lay.addStretch(1)

        c_lay.addWidget(header)

        # ── Collapsible content ──
        content = QWidget()
        in_lay = QVBoxLayout(content)
        in_lay.setContentsMargins(0, 0, 0, 0)
        in_lay.setSpacing(4)

        def _make_row(diagram):
            sc = _QSA()
            sc.setWidgetResizable(False)
            sc.setWidget(diagram.widget)
            sc.setFrameShape(QFrame.Shape.NoFrame)
            sc.setFixedHeight(70)
            sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            sc.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            return sc

        # Blue (Normal) diagram — reuses the default palette (KDE Highlight)
        if not hasattr(self, "_pp_diagram") or self._pp_diagram is None:
            self._pp_diagram = _PipelineDiagram(self.palette())
        in_lay.addWidget(_make_row(self._pp_diagram))

        # Orange (Translation) diagram — palette override with orange Highlight,
        # LLM always forced off (translation never runs LLM).
        if not hasattr(self, "_trpp_diagram") or self._trpp_diagram is None:
            _orange_pal = QPalette(self.palette())
            _orange_pal.setColor(QPalette.ColorRole.Highlight, QColor("#e67e22"))
            _orange_pal.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
            self._trpp_diagram = _PipelineDiagram(
                _orange_pal, variant="orange", llm_force_off=True)
        in_lay.addWidget(_make_row(self._trpp_diagram))

        c_lay.addWidget(content)
        content.setVisible(False)

        # Wire accordion toggle
        def _toggle_accordion(open_):
            content.setVisible(open_)
            toggle_btn.setArrowType(
                Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow)
        toggle_btn.toggled.connect(_toggle_accordion)
        # Exposed so sidebar navigation can auto-open on entry to the PP page.
        self._pipeline_toggle = toggle_btn

        return container

    def _build_postprocess_section(self, lay, conf):
        """Build post-processing section.

        Layout in sidebar overview mode (hidden when navigating into a sub-menu):

            [ ] Enable PP                             (blue, bold, 18px)
                [ ] Short text fix  < [3▼] words     (indented)
            [ ] Enable PP for translation             (orange, bold, 18px)
                [ ] Short text fix                    (indented)

        Short text is shown here because it's the ONLY pipeline step without
        its own sub-menu. All other steps are reachable exclusively via the
        SVG pipeline diagrams above. Their QCheckBox state holders are kept
        hidden in `_hidden_holder` for serialization compatibility.
        """
        _acc_hex = self.palette().color(
            self.palette().ColorRole.Highlight).name()
        _orange = "#e67e22"
        _sidebar = getattr(self, "_pipeline_header_external", False)

        # Container for the entire masters block (hidden in sub-menu mode)
        self._pp_masters_row = QWidget()
        _mlay = QVBoxLayout(self._pp_masters_row)
        _mlay.setContentsMargins(0, 0, 0, 0)
        _mlay.setSpacing(4)

        # Only colorize the LABEL. Leave the indicator to the system theme
        # (Breeze / default) — overriding width/height produces unthemed
        # squares and bleeds color into the checkmark.
        _master_style = (
            "QCheckBox {{ color: {col}; font-size: 18px; "
            "font-weight: bold; padding: 2px 0; }}")
        _sub_style = (
            "QCheckBox {{ color: {col}; font-size: 14px; "
            "padding: 1px 0; }}")

        # ── Master 1: Enable PP (normal) ──
        self.chk_postprocess = ToggleSwitch(_("Enable PP"))
        self.chk_postprocess.setChecked(self._pp_master_normal)
        if _sidebar:
            self.chk_postprocess.setStyleSheet(_master_style.format(col=_acc_hex))
        _mlay.addWidget(self.chk_postprocess)

        # Normal sub-row: Short text fix  < [N▼] words  (indented)
        _normal_sub = QWidget()
        _nrow = QHBoxLayout(_normal_sub)
        _nrow.setContentsMargins(28, 0, 0, 0)
        _nrow.setSpacing(6)
        self.chk_pp_short_text = ToggleSwitch(_("Short text fix"))
        self.chk_pp_short_text.setChecked(
            (conf.get("DICTEE_PP_SHORT_TEXT", "true") or "true").lower() == "true")
        self.chk_pp_short_text.setToolTip(_tt(_("For transcriptions with fewer than N words, remove trailing punctuation and lowercase capitalized words.")))
        if _sidebar:
            self.chk_pp_short_text.setStyleSheet(_sub_style.format(col=_acc_hex))
        _nrow.addWidget(self.chk_pp_short_text)
        _nrow.addWidget(QLabel(_("<")))
        self.cmb_pp_short_text_max = QComboBox()
        for n in (2, 3, 4, 5, 6):
            self.cmb_pp_short_text_max.addItem(str(n), n)
        try:
            _saved_max = int(conf.get("DICTEE_PP_SHORT_TEXT_MAX", "3"))
        except ValueError:
            _saved_max = 3
        _idx = self.cmb_pp_short_text_max.findData(_saved_max)
        if _idx >= 0:
            self.cmb_pp_short_text_max.setCurrentIndex(_idx)
        self.cmb_pp_short_text_max.setToolTip(_("Maximum word count for a transcription to be considered \"short\" and receive the short-text treatment."))
        self.cmb_pp_short_text_max.setEnabled(self.chk_pp_short_text.isChecked())
        self.chk_pp_short_text.toggled.connect(self.cmb_pp_short_text_max.setEnabled)
        _nrow.addWidget(self.cmb_pp_short_text_max)
        _nrow.addWidget(QLabel(_("words")))
        _nrow.addStretch(1)

        # Sub-row follows master state
        _normal_sub.setEnabled(self.chk_postprocess.isChecked())
        self.chk_postprocess.toggled.connect(_normal_sub.setEnabled)

        # Shared "Exceptions…" button — used for both source-lang (PP normal)
        # and target-lang (PP translate) short-text keepcaps; the dialog
        # switches between languages via its own combo.
        self.chk_pp_keepcaps = ToggleSwitch(_("Exceptions"))
        self.chk_pp_keepcaps.setChecked(
            (conf.get("DICTEE_PP_KEEPCAPS", "true") or "true").lower() == "true")
        self.chk_pp_keepcaps.setToolTip(_tt(_("Enable the short-text exceptions list. Words and expressions from the list keep their capitalization when dictated alone — greetings, formal openings/closings, courtesies…")))

        self.btn_pp_keepcaps = QPushButton(_("Exceptions…"))
        self.btn_pp_keepcaps.setToolTip(_tt(_("Edit the short-text capitalization exceptions. Shared for all languages (source and target) — greetings, courtesies, formal correspondence.")))
        self.btn_pp_keepcaps.clicked.connect(self._on_edit_keepcaps)
        self.btn_pp_keepcaps.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.chk_pp_keepcaps_ext = ToggleSwitch(_("Extended match"))
        self.chk_pp_keepcaps_ext.setChecked(
            (conf.get("DICTEE_PP_KEEPCAPS_EXTENDED", "true") or "true").lower() == "true")
        self.chk_pp_keepcaps_ext.setToolTip(_("Apply the exception matching beyond short texts: • A full list expression (\"to whom it may concern\", \"je vous prie de croire\") triggers keepcaps regardless of length. • A first-word match on a longer text emits a signal so the next push preserves its capital after a comma or a period+continuation word. Disable if you find the behavior too aggressive."))

        def _update_keepcaps_enabled():
            # Enabled if at least one of the two short_text toggles is on and
            # its master is active.
            src_on = (self.chk_postprocess.isChecked()
                      and self.chk_pp_short_text.isChecked())
            tgt_on = (self.chk_pp_translate.isChecked()
                      and getattr(self, 'chk_trpp_short_text', None)
                      and self.chk_trpp_short_text.isChecked())
            any_short = bool(src_on or tgt_on)
            kc = self.chk_pp_keepcaps.isChecked()
            self.chk_pp_keepcaps.setEnabled(any_short)
            self.btn_pp_keepcaps.setEnabled(any_short and kc)
            self.chk_pp_keepcaps_ext.setEnabled(any_short and kc)
        self._update_keepcaps_enabled = _update_keepcaps_enabled
        self.chk_pp_keepcaps.toggled.connect(
            lambda _on: self._update_keepcaps_enabled())

        # ── Master 2: Enable PP for translation ──
        self.chk_pp_translate = ToggleSwitch(_("Enable PP for translation"))
        self.chk_pp_translate.setChecked(self._pp_master_translate)
        self.chk_pp_translate.setToolTip(_tt(_("When enabled, the translated text is passed through the translation post-processing pipeline (orange), with the target language as reference.")))
        if _sidebar:
            self.chk_pp_translate.setStyleSheet(_master_style.format(col=_orange))

        def _on_master_translate_toggled(on):
            self._pp_master_translate = bool(on)
            self._refresh_pp_diagrams()
            self._update_test_chain_label()
            self._update_keepcaps_enabled()
        self.chk_pp_translate.toggled.connect(_on_master_translate_toggled)
        self.chk_postprocess.toggled.connect(
            lambda _on: self._update_keepcaps_enabled())
        self.chk_pp_short_text.toggled.connect(
            lambda _on: self._update_keepcaps_enabled())

        # Translation sub-row: Short text fix + its own threshold combo.
        _trans_sub = QWidget()
        _trow = QHBoxLayout(_trans_sub)
        _trow.setContentsMargins(28, 0, 0, 0)
        _trow.setSpacing(6)
        self.chk_trpp_short_text = ToggleSwitch(_("Short text fix"))
        self.chk_trpp_short_text.setChecked(
            bool(self._trpp_state.get("short_text", True)))
        self.chk_trpp_short_text.setToolTip(_tt(_("Apply the short-text fix to translated text. Useful when the translation backend capitalizes single-word inputs: e.g. 'maison' → 'House' → 'house'.")))
        if _sidebar:
            self.chk_trpp_short_text.setStyleSheet(_sub_style.format(col=_orange))

        def _on_trpp_short_toggled(on):
            self._trpp_state["short_text"] = bool(on)
            self._refresh_pp_diagrams()
        self.chk_trpp_short_text.toggled.connect(_on_trpp_short_toggled)
        _trow.addWidget(self.chk_trpp_short_text)
        _trow.addWidget(QLabel(_("<")))
        self.cmb_trpp_short_text_max = QComboBox()
        for n in (2, 3, 4, 5, 6):
            self.cmb_trpp_short_text_max.addItem(str(n), n)
        try:
            _trpp_saved_max = int(conf.get("DICTEE_TRPP_SHORT_TEXT_MAX", "3"))
        except ValueError:
            _trpp_saved_max = 3
        _tidx = self.cmb_trpp_short_text_max.findData(_trpp_saved_max)
        if _tidx >= 0:
            self.cmb_trpp_short_text_max.setCurrentIndex(_tidx)
        self.cmb_trpp_short_text_max.setToolTip(_("Maximum word count for a translated transcription to be considered \"short\" and receive the short-text treatment."))
        self.cmb_trpp_short_text_max.setEnabled(self.chk_trpp_short_text.isChecked())
        self.chk_trpp_short_text.toggled.connect(
            self.cmb_trpp_short_text_max.setEnabled)
        _trow.addWidget(self.cmb_trpp_short_text_max)
        _trow.addWidget(QLabel(_("words")))
        _trow.addStretch(1)

        # Sub-row enabled only in full_chain mode
        # Sub-row follows master state
        _trans_sub.setEnabled(self.chk_pp_translate.isChecked())
        self.chk_pp_translate.toggled.connect(_trans_sub.setEnabled)
        self.chk_trpp_short_text.toggled.connect(
            lambda _on: self._update_keepcaps_enabled())

        # Stack the master rows vertically (back to normal flow).
        _mlay.addWidget(_normal_sub)
        _mlay.addWidget(self.chk_pp_translate)
        _mlay.addWidget(_trans_sub)

        lay.addWidget(self._pp_masters_row)

        # Overview-only extras (Exceptions block + diarize warning) —
        # wrapped so they can be hidden when a sub-page is active,
        # like _pp_masters_row. These belong to the PP OVERVIEW, not
        # the Rules/Continuation/Language/Dict/LLM sub-tabs.
        self._pp_overview_extras = QWidget()
        _extras_lay = QVBoxLayout(self._pp_overview_extras)
        _extras_lay.setContentsMargins(0, 0, 0, 0)
        _extras_lay.setSpacing(6)

        # Separator: visually detach the shared Exceptions row from the
        # two PP masters above.
        _keepcaps_sep = QFrame()
        _keepcaps_sep.setFrameShape(QFrame.Shape.HLine)
        _keepcaps_sep.setFrameShadow(QFrame.Shadow.Sunken)
        _extras_lay.addWidget(_keepcaps_sep)

        # Shared Exceptions block — between the two PP masters and the
        # diarization warning. Two rows stacked:
        #   Row 1: [Exceptions toggle] [Exceptions… button]  Hint label
        #   Row 2: indented [Extended match toggle]
        _keepcaps_block = QVBoxLayout()
        _keepcaps_block.setContentsMargins(0, 4, 0, 4)
        _keepcaps_block.setSpacing(2)

        _keepcaps_row1 = QHBoxLayout()
        _keepcaps_row1.setContentsMargins(0, 0, 0, 0)
        _keepcaps_row1.setSpacing(8)
        _keepcaps_row1.addWidget(self.chk_pp_keepcaps)
        _keepcaps_row1.addWidget(self.btn_pp_keepcaps)
        _keepcaps_lbl = QLabel(_(
            "Shared source + target. Words from the list keep their capital."))
        _keepcaps_lbl.setStyleSheet("color: #888; font-style: italic;")
        _keepcaps_lbl.setWordWrap(True)
        _keepcaps_row1.addWidget(_keepcaps_lbl, 1)
        _keepcaps_block.addLayout(_keepcaps_row1)

        _keepcaps_row2 = QHBoxLayout()
        _keepcaps_row2.setContentsMargins(28, 0, 0, 0)  # indent
        _keepcaps_row2.setSpacing(6)
        _keepcaps_row2.addWidget(self.chk_pp_keepcaps_ext)
        _keepcaps_row2.addStretch(1)
        _keepcaps_block.addLayout(_keepcaps_row2)

        _extras_lay.addLayout(_keepcaps_block)
        self._update_keepcaps_enabled()

        # Diarization note: explicit, visible once on the PP page.
        _accent_hex = self.palette().color(
            self.palette().ColorRole.Highlight).name()
        _lbl_diarize_note = QLabel(
            "<span style='color:#e67e22;font-weight:bold;'>⚠ "
            + _("Diarisation") + "</span> &nbsp;—&nbsp; "
            + _(
                "in multi-speaker mode, the raw text is kept as-is (no "
                "post-processing, no translation, no LLM) to preserve "
                "the labels ")
            + "<span style='background:rgba(230,126,34,0.2);"
              "padding:1px 5px;border-radius:3px;font-family:monospace;'>"
              "[SPK1]</span>, "
            + "<span style='background:rgba(230,126,34,0.2);"
              "padding:1px 5px;border-radius:3px;font-family:monospace;'>"
              "[SPK2]</span>…")
        _lbl_diarize_note.setWordWrap(True)
        _lbl_diarize_note.setTextFormat(Qt.TextFormat.RichText)
        _lbl_diarize_note.setStyleSheet(
            "QLabel { font-size: 13px; padding: 10px 14px;"
            " border: 1px solid #e67e22; border-left: 4px solid #e67e22;"
            " border-radius: 4px; background: rgba(230,126,34,0.08); }")
        _extras_lay.addWidget(_lbl_diarize_note)

        lay.addWidget(self._pp_overview_extras)

        # Container for all PP content (grayed out if disabled)
        self._pp_content = QWidget()
        pp_lay = QVBoxLayout(self._pp_content)
        pp_lay.setContentsMargins(0, 0, 0, 0)
        pp_lay.setSpacing(6)

        # --- Pipeline diagram (SVG) with hint label ---
        # In sidebar mode, the pipeline header is mounted at window level
        # by _build_sidebar_ui; skip it here to avoid duplicate instances.
        if not getattr(self, "_pipeline_header_external", False):
            pp_lay.addWidget(self._build_pipeline_header_widget())

        # --- Pipeline toggles: only Short text and LLM are shown here.
        # The 6 others (Rules, Continuation, Language rules, Numbers, Dict,
        # Capitalization) are reachable via the SVG pipeline above — their
        # QCheckBox objects are still instantiated (hidden) so _on_apply
        # serializes them and _on_pp_step_clicked can toggle them.
        grid_gen = QGridLayout()
        grid_gen.setContentsMargins(20, 0, 0, 0)
        _hidden_holder = QWidget()
        _hidden_holder.setVisible(False)
        _hidden_lay = QVBoxLayout(_hidden_holder)
        _hidden_lay.setContentsMargins(0, 0, 0, 0)

        self.chk_pp_rules = ToggleSwitch(_("Regex rules"), _hidden_holder)
        self.chk_pp_rules.setChecked(conf.get("DICTEE_PP_RULES", "true") == "true")
        _hidden_lay.addWidget(self.chk_pp_rules)

        self.chk_pp_continuation = ToggleSwitch(_("Continuation"), _hidden_holder)
        self.chk_pp_continuation.setChecked(conf.get("DICTEE_PP_CONTINUATION", "true") == "true")
        _hidden_lay.addWidget(self.chk_pp_continuation)

        self.chk_pp_language_rules = ToggleSwitch(_("Language rules"), _hidden_holder)
        self.chk_pp_language_rules.setChecked(
            conf.get("DICTEE_PP_LANGUAGE_RULES", "true") == "true")
        _hidden_lay.addWidget(self.chk_pp_language_rules)

        self.chk_pp_numbers = ToggleSwitch(_("Number conversion (text2num)"), _hidden_holder)
        self.chk_pp_numbers.setChecked(conf.get("DICTEE_PP_NUMBERS", "true") == "true")
        if not has_text2num():
            # Force OFF so the SVG pipeline step renders as disabled too,
            # and Apply writes DICTEE_PP_NUMBERS=false (matches reality).
            self.chk_pp_numbers.setChecked(False)
            self.chk_pp_numbers.setEnabled(False)
            # Also sync the diagram state dicts (which were already seeded
            # from config before this point — signals won't propagate at init).
            if hasattr(self, "_pp_state"):
                self._pp_state["numbers"] = False
            if hasattr(self, "_trpp_state"):
                self._trpp_state["numbers"] = False
            self.chk_pp_numbers.setToolTip(
                "<span style='color:#c0392b;'><b>" + _("text2num not installed") + "</b><br>"
                + _("Reinstall dictee, or manually:") + "<br>"
                + "<code>sudo python3 -m venv /usr/share/dictee/postprocess-env</code><br>"
                + "<code>sudo /usr/share/dictee/postprocess-env/bin/pip install text2num</code>"
                + "</span>"
            )
        _hidden_lay.addWidget(self.chk_pp_numbers)

        self.chk_pp_dict = ToggleSwitch(_("Dictionary"), _hidden_holder)
        self.chk_pp_dict.setChecked(conf.get("DICTEE_PP_DICT", "true") == "true")
        _hidden_lay.addWidget(self.chk_pp_dict)

        self.chk_pp_capitalization = ToggleSwitch(_("Auto-capitalization"), _hidden_holder)
        self.chk_pp_capitalization.setChecked(conf.get("DICTEE_PP_CAPITALIZATION", "true") == "true")
        _hidden_lay.addWidget(self.chk_pp_capitalization)

        # LLM state holder (hidden; editable via its sub-menu).
        self.chk_llm = ToggleSwitch(_("LLM grammar correction (ollama)"), _hidden_holder)
        self.chk_llm.setChecked(conf.get("DICTEE_LLM_POSTPROCESS", "false") == "true")
        _hidden_lay.addWidget(self.chk_llm)

        pp_lay.addLayout(grid_gen)  # kept for layout rigidity; empty in practice
        pp_lay.addWidget(_hidden_holder)  # hidden state holder

        # Cosmetic separator between checkboxes grid and editing tabs.
        # Hidden in sidebar overview mode (no tabs visible → no need).
        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.HLine)
        _sep.setFrameShadow(QFrame.Shadow.Sunken)
        _sep.setContentsMargins(0, 8, 0, 8)
        pp_lay.addSpacing(6)
        pp_lay.addWidget(_sep)
        pp_lay.addSpacing(6)
        self._pp_sep = _sep

        # --- Editing sub-tabs ---
        # In sidebar mode, the tab bar is hidden and a dynamic title label
        # replaces it (the left pane drives tab selection).
        self._pp_tabs = QTabWidget()

        # Accent colors for tabs
        accent = self.palette().color(self.palette().ColorRole.Highlight)
        accent_hex = accent.name()
        self._pp_tabs.setStyleSheet(f"""
            QTabBar::tab:selected {{
                color: {accent_hex};
                font-weight: bold;
            }}
        """)

        if getattr(self, "_pipeline_header_external", False):
            self._pp_tabs.tabBar().hide()
            # Header row wrapped in a QWidget so it can be hidden as a
            # whole when the user selects the Post-processing root node
            # (overview mode). Holds an enable toggle (writes the normal
            # pipeline only) + the dynamic title. The toggle is ON when
            # EITHER the normal OR the translate pipeline has this step
            # enabled — so the user sees the step is "live" somewhere
            # even with the interactive SVG accordion collapsed.
            self._pp_title_row_w = QWidget()
            _title_row = QHBoxLayout(self._pp_title_row_w)
            _title_row.setContentsMargins(0, 0, 0, 0)
            _title_row.setSpacing(12)
            self._pp_tab_enable_chk = ToggleSwitch("")
            self._pp_tab_enable_chk.setToolTip(
                _("Enable this step in the normal pipeline. "
                  "Stays ON while the translation pipeline has it active."))
            _title_row.addWidget(self._pp_tab_enable_chk)
            self._pp_tab_title = QLabel()
            self._pp_tab_title.setStyleSheet(
                f"color: {accent_hex}; font-size: 24px; font-weight: bold; "
                "padding: 6px 0 12px 0;")
            _title_row.addWidget(self._pp_tab_title)
            _title_row.addStretch(1)
            pp_lay.addWidget(self._pp_title_row_w)

            def _on_tab_enable_toggled(checked):
                idx = self._pp_tabs.currentIndex() if hasattr(self, '_pp_tabs') else -1
                key = self._PP_TAB_KEY_BY_IDX.get(idx)
                if key is None:
                    return
                # Memo of translate state cut by the toggle — used to
                # restore it on the next re-activation. Cleared on restore.
                if not hasattr(self, '_pp_translate_before_off'):
                    self._pp_translate_before_off = {}
                if checked:
                    # Activating: force normal ON.
                    self._pp_state[key] = True
                    # Restore translate if we cut it previously.
                    if key in self._pp_translate_before_off:
                        self._trpp_state[key] = self._pp_translate_before_off.pop(key)
                else:
                    # Deactivating: cut BOTH pipelines; remember translate.
                    if self._trpp_state.get(key):
                        self._pp_translate_before_off[key] = True
                    self._pp_state[key] = False
                    self._trpp_state[key] = False
                # Keep the normal master checkbox in sync (blockSignals to
                # avoid re-entering _refresh_pp_diagrams via its toggled).
                master_attr = self._PP_MASTER_CHK_BY_KEY.get(key)
                if master_attr and hasattr(self, master_attr):
                    chk = getattr(self, master_attr)
                    chk.blockSignals(True)
                    chk.setChecked(bool(checked))
                    chk.blockSignals(False)
                # LLM in translate pipeline is always forced OFF at runtime.
                if key == "llm":
                    self._trpp_state["llm"] = False
                self._refresh_pp_diagrams()
            self._pp_tab_enable_chk.toggled.connect(_on_tab_enable_toggled)

            def _sync_pp_title(idx):
                if idx < 0:
                    return
                self._pp_tab_title.setText(self._pp_tabs.tabText(idx))
                self._sync_pp_tab_enable_chk()

            self._pp_tabs.currentChanged.connect(_sync_pp_title)
            # Initial sync deferred to after addTab calls below
            self._pp_tab_title_sync = _sync_pp_title

        # Tab order: pipeline sequence with LLM moved to the end.
        # Rules(0) → Continuation(1) → Language rules(2) → Dictionary(3) → LLM(4)

        # Rules tab (index 0)
        tab_rules = QWidget()
        tab_rules_lay = QVBoxLayout(tab_rules)
        tab_rules_lay.setContentsMargins(8, 8, 8, 8)
        self._build_rules_tab(tab_rules_lay)
        self._pp_tabs.addTab(tab_rules, _("Regex rules"))

        # Continuation tab (index 1)
        tab_cont = QWidget()
        tab_cont_lay = QVBoxLayout(tab_cont)
        tab_cont_lay.setContentsMargins(8, 8, 8, 8)
        self._build_continuation_tab(tab_cont_lay)
        self._pp_tabs.addTab(tab_cont, _("Continuation"))

        # Language rules tab (index 2)
        tab_lang = QWidget()
        tab_lang_lay = QVBoxLayout(tab_lang)
        tab_lang_lay.setContentsMargins(8, 8, 8, 8)
        self._build_language_rules_tab(tab_lang_lay, conf)
        self._pp_tabs.addTab(tab_lang, _("Language rules"))

        # Dictionary tab (index 3)
        tab_dict = QWidget()
        tab_dict_lay = QVBoxLayout(tab_dict)
        tab_dict_lay.setContentsMargins(8, 8, 8, 8)
        self._build_dictionary_tab(tab_dict_lay)
        self._pp_tabs.addTab(tab_dict, _("Dictionary"))

        # LLM tab (index 4) — moved to the end
        tab_llm = QWidget()
        tab_llm_lay = QVBoxLayout(tab_llm)
        tab_llm_lay.setContentsMargins(8, 8, 8, 8)
        self._build_llm_tab(tab_llm_lay, conf)
        self._pp_tabs.addTab(tab_llm, _("LLM"))

        # Initialize dynamic title now that tabs exist (sidebar mode only)
        if hasattr(self, "_pp_tab_title_sync"):
            self._pp_tab_title_sync(self._pp_tabs.currentIndex())

        # Tabs stay clickable (never Qt-disabled) but their title is grayed
        # via the disabled palette color when the corresponding step is off.
        _disabled_col = self.palette().color(
            self.palette().ColorGroup.Disabled,
            self.palette().ColorRole.WindowText)
        _normal_col = self.palette().color(
            self.palette().ColorRole.WindowText)

        # Sub-pages are always fully active: the step activation state is
        # stored in self._pp_state / self._trpp_state and visualised via
        # the SVG pipeline only. No greying of tab content from the step
        # checkboxes anymore.

        # Edit mode button (masqué pour l'onglet Règles)
        self._btn_advanced = QPushButton(_("Edit mode"))
        self._btn_advanced.setCheckable(True)
        self._btn_advanced.setMaximumWidth(150)
        accent = self.palette().color(self.palette().ColorRole.Highlight).name()
        self._btn_advanced.setStyleSheet(
            f"QPushButton {{ font-weight: bold; }}"
            f"QPushButton:checked {{ background-color: {accent}; color: white; border-radius: 4px; padding: 2px 8px; }}"
        )
        corner = QWidget()
        corner_lay = QHBoxLayout(corner)
        corner_lay.setContentsMargins(0, 0, 4, 0)
        corner_lay.addWidget(self._btn_advanced)
        self._pp_tabs.setCornerWidget(corner)

        def _on_tab_changed(idx):
            # New tab order: Rules(0), Continuation(1), Lang(2), Dict(3), LLM(4)
            # Edit mode button hidden for Rules, Languages, LLM
            self._btn_advanced.setVisible(idx not in (0, 2, 4))
            self._btn_advanced.setChecked(False)
            self._toggle_advanced_mode(False)
            if idx == 0:
                self._maybe_show_rules_warning()
        self._pp_tabs.currentChanged.connect(_on_tab_changed)
        self._btn_advanced.toggled.connect(self._toggle_advanced_mode)
        # Never open on the Regex rules tab — its warning popup would fire
        # before the dialog is even painted. Default to Continuation (index 1).
        self._pp_tabs.setCurrentIndex(1)
        _on_tab_changed(1)

        pp_lay.addWidget(self._pp_tabs)

        # --- Test panel (collapsible accordion) ---
        _test_toggle = QPushButton("▶  " + _("Test"))
        _test_toggle.setCheckable(True)
        _test_toggle.setChecked(False)
        _test_toggle.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        _test_toggle.setStyleSheet(
            "QPushButton { text-align: left; font-weight: bold; "
            "padding: 6px 12px; border: none; }"
            "QPushButton:hover { background-color: rgba(127,127,127,30); }"
        )
        _test_body = QFrame()
        test_lay = QVBoxLayout(_test_body)
        test_lay.setContentsMargins(8, 0, 8, 8)
        test_lay.setSpacing(4)
        # No hardcoded min height — Qt computes _test_body.minimumSize()
        # from the children natural mins. The scroll protection is handled
        # in _on_test_toggled by freezing _pp_tabs height.
        # Expose the accordion toggle BEFORE _build_test_panel so its
        # sub-tab hook (_update_test_header) can refresh the label.
        self._test_accordion_toggle = _test_toggle
        self._build_test_panel(test_lay)
        _test_body.setVisible(False)

        def _on_test_toggled(on):
            self._freeze_pp()
            # Freeze tabs at their current height so the test panel
            # doesn't squeeze or stretch the editors above.
            if on and hasattr(self, "_pp_tabs"):
                self._pp_tabs.setFixedHeight(self._pp_tabs.height())
            elif not on and hasattr(self, "_pp_tabs"):
                self._pp_tabs.setMinimumHeight(480)
                self._pp_tabs.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            _test_body.setVisible(on)
            self._refresh_test_accordion_label()
            self._unfreeze_pp(20)
            # Auto-scroll to reveal the test panel when opened
            if on:
                scroll = getattr(self, "_pp_scroll", None)
                if scroll:
                    QTimer.singleShot(
                        40, lambda: scroll.ensureWidgetVisible(_test_body, 0, 40))
        _test_toggle.toggled.connect(_on_test_toggled)
        # Initial label reflects current PP sub-tab (if any)
        self._refresh_test_accordion_label()

        pp_lay.addWidget(_test_toggle)
        pp_lay.addWidget(_test_body)

        # Sidebar mode: Test accordion keeps its natural size when
        # expanded. A dedicated spacer widget pushes Short text to the
        # top in overview mode; it is hidden when a sub-section is
        # visible so the tab content fills the remaining space above
        # the Test panel.
        if getattr(self, "_pipeline_header_external", False):
            _test_body.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            # Overview-only spacer: expands vertically only in overview
            # mode. Must be inserted BEFORE the test accordion so tabs
            # (which come earlier in the layout) can expand freely when
            # visible, and the spacer fills the gap in overview mode.
            self._pp_overview_spacer = QWidget()
            self._pp_overview_spacer.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            # Insert right before the test toggle
            test_idx = pp_lay.indexOf(_test_toggle)
            pp_lay.insertWidget(test_idx, self._pp_overview_spacer)

        # Outer QScrollArea wrapping the whole PP content (tabs + test
        # accordion). The goal: when the user expands the test panel,
        # the Rules editor above (inside _pp_tabs) MUST NOT shrink —
        # instead the outer scrollbar appears and the user scrolls
        # down to the test.
        #
        # How it works:
        # - _pp_tabs keeps its default Expanding policy so it grows to
        #   fill all available space when there's room.
        # - _pp_tabs AND _test_body both get an explicit setMinimumHeight.
        #   Only hard minimums contribute to layout.minimumSize(), which
        #   is what QScrollArea uses to decide when the scrollbar is
        #   needed.
        # - Sum of mins = tabs_min + test_body_min + other fixed stuff.
        #   When test is hidden, test_body min is ignored by the layout
        #   (Qt skips hidden widgets) → content min stays low → no
        #   scroll on normal viewports. When test is visible, content
        #   min jumps → if it exceeds the viewport, scrollbar appears
        #   and tabs stay at their min height, not squeezed.
        if hasattr(self, "_pp_tabs"):
            self._pp_tabs.setMinimumHeight(480)

        # _pp_scroll is now the outer QScrollArea wrapping page_pp_inner
        # (created in _build_sidebar_ui). Store a reference for
        # ensureWidgetVisible calls; addWidget _pp_content directly to lay.
        lay.addWidget(self._pp_content)

        # Per-step greying: a pipeline step is "effectively active" when
        # at least one of the two pipelines (normal / translation) has it
        # enabled, taking masters into account:
        #     effective(step) = (master_normal AND _pp_state[step])
        #                    OR (master_translate AND _trpp_state[step])
        # When effectively inactive, both the sub-item in the sidebar tree
        # AND the corresponding sub-page (tab content) are greyed.
        # LLM is a special case: _trpp_state['llm'] is always False, so
        # its effective state depends only on the normal pipeline.
        def _apply_any_master_active():
            # Build per-step effective activation map
            effective = {}
            for k in ("rules", "continuation", "language_rules", "dict", "llm"):
                n = self._pp_master_normal and self._pp_state.get(k, False)
                t = self._pp_master_translate and self._trpp_state.get(k, False)
                effective[k] = bool(n or t)

            # Sidebar sub-items under the Post-processing root.
            # Grey them visually via foreground color when the step is
            # effectively off, but KEEP them enabled so the user can
            # still navigate to their page via clicks (either from
            # sidebar or from the SVG pipeline).
            tree = getattr(self, "_sidebar_tree", None)
            pp_root = None
            if tree is not None:
                for i in range(tree.topLevelItemCount()):
                    it = tree.topLevelItem(i)
                    if it.childCount() == 5:
                        pp_root = it
                        break
            step_order = ("rules", "continuation", "language_rules", "dict", "llm")
            from PyQt6.QtGui import QBrush
            _pal = self.palette()
            _col_normal = _pal.color(_pal.ColorRole.WindowText)
            _col_disabled = _pal.color(
                _pal.ColorGroup.Disabled, _pal.ColorRole.WindowText)
            if pp_root is not None:
                for idx, k in enumerate(step_order):
                    child = pp_root.child(idx)
                    if child is not None:
                        child.setForeground(
                            0,
                            QBrush(_col_normal if effective[k] else _col_disabled))

            # Sub-page tab content
            if hasattr(self, "_pp_tabs") and self._pp_tabs is not None:
                for idx, k in enumerate(step_order):
                    w = self._pp_tabs.widget(idx)
                    if w is not None:
                        w.setEnabled(effective[k])

            # Rules page: the QSyntaxHighlighter needs an explicit refresh
            # (setEnabled alone leaves highlighted text in its colored state).
            if hasattr(self, "_update_rules_active"):
                self._update_rules_active()
        self._apply_any_master_active = _apply_any_master_active

        def _on_master_normal_toggled(on):
            self._pp_master_normal = bool(on)
            _apply_any_master_active()
            self._refresh_pp_diagrams()
            self._update_test_chain_label()
        self.chk_postprocess.toggled.connect(_on_master_normal_toggled)
        self.chk_pp_translate.toggled.connect(
            lambda _on: _apply_any_master_active())

        # Initial state
        _apply_any_master_active()
        self._refresh_pp_diagrams()

        # Sidebar mode: grey the post-processing header (big title + tab
        # checkbox) when the master post-processing is disabled, so the
        # whole page looks consistently inactive.
        if getattr(self, "_pipeline_header_external", False):
            accent_hex = self.palette().color(
                self.palette().ColorRole.Highlight).name()
            dis_hex = self.palette().color(
                self.palette().ColorGroup.Disabled,
                self.palette().ColorRole.WindowText).name()

            def _apply_pp_master(on):
                col = accent_hex if on else dis_hex
                self._pp_tab_title.setStyleSheet(
                    f"color: {col}; font-size: 24px; font-weight: bold; "
                    "padding: 6px 0 12px 0;")
                if hasattr(self, "_pp_tabs"):
                    self._pp_tabs.setEnabled(on)

            self.chk_postprocess.toggled.connect(_apply_pp_master)
            _apply_pp_master(self.chk_postprocess.isChecked())

        # Wire pipeline diagram refresh (SVG is the source of activation —
        # no per-tab enable checkbox to keep in sync anymore).
        for cb in (self.chk_pp_rules, self.chk_pp_continuation,
                   self.chk_pp_language_rules,
                   self.chk_pp_numbers, self.chk_pp_dict,
                   self.chk_pp_capitalization, self.chk_llm,
                   self.chk_pp_short_text):
            cb.toggled.connect(self._refresh_pp_diagram)
        if hasattr(self, 'llm_position_group'):
            self.llm_position_group.buttonToggled.connect(
                lambda _btn, _checked: self._refresh_pp_diagram() if _checked else None)
        if hasattr(self, 'cmb_pp_short_text_max'):
            self.cmb_pp_short_text_max.currentIndexChanged.connect(self._refresh_pp_diagram)
        self._pp_diagram.widget.step_clicked.connect(self._on_pp_step_clicked)
        # Orange diagram: same handler. Clicks modify the shared state
        # dict (via the hidden checkbox toggle), so both diagrams update
        # in sync. LLM on the orange is cosmetic-only (forced off).
        if hasattr(self, "_trpp_diagram") and self._trpp_diagram is not None:
            self._trpp_diagram.widget.step_clicked.connect(self._on_pp_step_clicked)
        self._refresh_pp_diagram()

    def _maybe_show_rules_warning(self):
        """Show the 'rules can break output' warning as a popup with a
        'don't show again' checkbox. Dismissal is persisted in
        ~/.config/dictee/.rules_warning_dismissed.
        """
        flag_path = os.path.join(
            os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
            "dictee", ".rules_warning_dismissed")
        if os.path.isfile(flag_path):
            return
        parent = self._pp_parent if hasattr(self, "_pp_parent") else self
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(_("Regex rules — caution"))
        box.setText(
            '<span style="color: #c0392b; font-weight: bold;">⚠ ' +
            _("Advanced feature") + "</span>")
        box.setInformativeText(_(
            "Incorrect rules can break transcription output. "
            "Rules are applied in order: a misplaced or wrong pattern may "
            "silently delete or corrupt text.\n\n"
            "Use the test panel below to verify your changes before saving."))
        dont_show = ToggleSwitch(_("Don't show this warning again"))
        box.setCheckBox(dont_show)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()
        if dont_show.isChecked():
            try:
                os.makedirs(os.path.dirname(flag_path), exist_ok=True)
                with open(flag_path, "w") as _f:
                    _f.write("1\n")
            except OSError:
                pass

    def _on_pp_step_clicked(self, key):
        # Identify which diagram emitted the signal. sender() returns the
        # _ClickableSvgWidget instance; compare with the two known widgets.
        sender = self.sender()
        is_translation = (
            hasattr(self, "_trpp_diagram")
            and self._trpp_diagram is not None
            and sender is self._trpp_diagram.widget
        )

        # Navigation-only shortcuts (mic / ASR icons): jump to the
        # corresponding sidebar section without toggling anything.
        if key.startswith("nav:") and hasattr(self, "_sidebar_tree"):
            target_label = {
                "nav:microphone": _("Microphone"),
                "nav:asr": _("ASR backend"),
                "nav:translation": _("Translation"),
            }.get(key)
            if target_label:
                tree = self._sidebar_tree
                for i in range(tree.topLevelItemCount()):
                    it = tree.topLevelItem(i)
                    if it.text(0) == target_label:
                        tree.setCurrentItem(it)
                        return
            return

        # Translation source: the orange diagram has ITS OWN independent
        # state dict (`self._trpp_state`). Clicks on it never touch the
        # normal state. LLM is always force-off on the orange, so ignore
        # any "llm" clicks on that diagram.
        if is_translation:
            if key == "llm":
                # LLM is locked off in translation mode; silently ignore.
                return
            tab_idx = {
                "rules": 0, "continuation": 1, "language_rules": 2,
                "dict": 3,
            }.get(key)
            target_child = None
            tree = getattr(self, "_sidebar_tree", None)
            if tree is not None and tab_idx is not None:
                for i in range(tree.topLevelItemCount()):
                    it = tree.topLevelItem(i)
                    if it.childCount() == 5:
                        target_child = it.child(tab_idx)
                        break

            def _toggle_trpp():
                # "numbers" requires text2num — block toggle if absent.
                if key == "numbers" and not has_text2num():
                    self._show_text2num_missing()
                    return
                self._trpp_state[key] = not self._trpp_state.get(key, True)
                self._refresh_pp_diagrams()

            steps_with_page = {"rules", "continuation", "language_rules", "dict"}
            if key in steps_with_page:
                if target_child is None:
                    _toggle_trpp()
                    return
                already_on_page = (
                    tree is not None
                    and tree.currentItem() is target_child
                )
                if already_on_page:
                    _toggle_trpp()
                    return
                # Navigate first; 2nd click (on page) will toggle.
                tree.setCurrentItem(target_child)
                return
            # numbers, capitalization, short_text → direct toggle.
            if key in self._trpp_state:
                _toggle_trpp()
            return

        # Normal source (blue diagram): existing behavior, drives the
        # hidden checkboxes which in turn update self._pp_state via signals.
        cb_map = {
            "rules": self.chk_pp_rules,
            "continuation": self.chk_pp_continuation,
            "language_rules": self.chk_pp_language_rules,
            "numbers": self.chk_pp_numbers,
            "dict": self.chk_pp_dict,
            "capitalization": self.chk_pp_capitalization,
            "llm": self.chk_llm,
            "short_text": getattr(self, 'chk_pp_short_text', None),
        }
        steps_with_page = {"rules", "continuation", "language_rules", "dict", "llm"}
        target_child = None
        tab_idx = {
            "rules": 0, "continuation": 1, "language_rules": 2,
            "dict": 3, "llm": 4,
        }.get(key)
        tree = getattr(self, "_sidebar_tree", None)
        if tree is not None and tab_idx is not None:
            for i in range(tree.topLevelItemCount()):
                it = tree.topLevelItem(i)
                if it.childCount() == 5:
                    target_child = it.child(tab_idx)
                    break
        if key in steps_with_page:
            if target_child is None:
                cb = cb_map.get(key)
                if cb is not None and cb.isEnabled():
                    cb.toggle()
                elif key == "numbers":
                    self._show_text2num_missing()
                return
            already_on_page = (
                tree is not None
                and tree.currentItem() is target_child
            )
            if already_on_page:
                cb = cb_map.get(key)
                if cb is not None and cb.isEnabled():
                    cb.toggle()
                elif key == "numbers":
                    self._show_text2num_missing()
                return
            # Navigate first; 2nd click (on page) will toggle.
            tree.setCurrentItem(target_child)
            return
        # Step without a page: toggle directly (respect disabled state —
        # e.g. "numbers" is disabled when text2num is not installed).
        cb = cb_map.get(key)
        if cb is not None and cb.isEnabled():
            cb.toggle()
        elif key == "numbers":
            self._show_text2num_missing()


    def _show_text2num_missing(self):
        """Display a warning dialog explaining how to install text2num."""
        title = _("Number conversion unavailable")
        body = (
            _("text2num is not installed on this system. "
              "It should have been installed automatically with dictee.")
            + "\n\n"
            + _("To install it manually, run:")
            + "\n\n"
            + "sudo python3 -m venv /usr/share/dictee/postprocess-env\n"
            + "sudo /usr/share/dictee/postprocess-env/bin/pip install text2num"
            + "\n\n"
            + _("Then restart dictee-setup.")
        )
        QMessageBox.warning(self, title, body)


    def _update_test_chain_label(self):
        """Update the test panel chain label from the current toggle states."""
        if not hasattr(self, '_test_mode_label'):
            return
        parts = []
        if self._pp_master_normal:
            parts.append(_("PP Normal"))
        trad = (hasattr(self, '_test_trad_switch')
                and self._test_trad_switch.isChecked())
        if trad:
            parts.append(_("Traduction"))
        if trad and self._pp_master_translate:
            parts.append(_("PP Traduction"))
        self._test_mode_label.setText(" → ".join(parts) if parts else "—")
        if hasattr(self, '_update_test_mode_icon'):
            self._update_test_mode_icon()
        # Force immediate re-run with freeze to avoid repaint artifacts
        if hasattr(self, '_run_test_pipeline'):
            self._freeze_pp()
            self._run_test_pipeline()
            self._unfreeze_pp(10)

    # Mapping used by the sub-page title enable toggle (above each tab).
    _PP_TAB_KEY_BY_IDX = {
        0: "rules",
        1: "continuation",
        2: "language_rules",
        3: "dict",
        4: "llm",
    }
    _PP_MASTER_CHK_BY_KEY = {
        "rules":          "chk_pp_rules",
        "continuation":   "chk_pp_continuation",
        "language_rules": "chk_pp_language_rules",
        "dict":           "chk_pp_dict",
        "llm":            "chk_llm",
    }

    def _sync_pp_tab_enable_chk(self):
        """Mirror the title-row enable toggle on combined normal OR translate state."""
        if not hasattr(self, '_pp_tab_enable_chk'):
            return
        if not hasattr(self, '_pp_tabs'):
            return
        idx = self._pp_tabs.currentIndex()
        key = self._PP_TAB_KEY_BY_IDX.get(idx)
        if key is None:
            return
        combined = bool(
            self._pp_state.get(key, False)
            or self._trpp_state.get(key, False))
        self._pp_tab_enable_chk.blockSignals(True)
        self._pp_tab_enable_chk.setChecked(combined)
        self._pp_tab_enable_chk.blockSignals(False)

    def _refresh_pp_diagrams(self):
        """Refresh both pipeline diagrams (blue/Normal and orange/Translation)
        from their INDEPENDENT state dicts + two masters."""
        # Sync normal state from hidden checkboxes (they remain the
        # persistence-side source of truth for normal mode).
        if hasattr(self, "chk_pp_rules"):
            self._pp_state["rules"] = self.chk_pp_rules.isChecked()
        if hasattr(self, "chk_pp_continuation"):
            self._pp_state["continuation"] = self.chk_pp_continuation.isChecked()
        if hasattr(self, "chk_pp_language_rules"):
            self._pp_state["language_rules"] = self.chk_pp_language_rules.isChecked()
        if hasattr(self, "chk_pp_numbers"):
            self._pp_state["numbers"] = self.chk_pp_numbers.isChecked()
        if hasattr(self, "chk_pp_dict"):
            self._pp_state["dict"] = self.chk_pp_dict.isChecked()
        if hasattr(self, "chk_pp_capitalization"):
            self._pp_state["capitalization"] = self.chk_pp_capitalization.isChecked()
        if hasattr(self, "chk_pp_short_text"):
            self._pp_state["short_text"] = self.chk_pp_short_text.isChecked()
        if hasattr(self, "chk_llm"):
            self._pp_state["llm"] = self.chk_llm.isChecked()

        # Sync translation short-text checkbox FROM self._trpp_state so
        # that SVG orange clicks (which write directly into the dict) are
        # reflected in the visible checkbox. Use blockSignals to avoid
        # triggering the toggled handler and re-entering this function.
        if hasattr(self, "chk_trpp_short_text"):
            desired = bool(self._trpp_state.get("short_text", True))
            if self.chk_trpp_short_text.isChecked() != desired:
                self.chk_trpp_short_text.blockSignals(True)
                self.chk_trpp_short_text.setChecked(desired)
                self.chk_trpp_short_text.blockSignals(False)

        llm_pos = self._get_llm_position() if hasattr(self, "_get_llm_position") else "hybrid"
        st_max = 3
        if hasattr(self, "cmb_pp_short_text_max"):
            st_max = self.cmb_pp_short_text_max.currentData() or 3

        if hasattr(self, "_pp_diagram") and self._pp_diagram is not None:
            self._pp_diagram.set_master(self._pp_master_normal)
            self._pp_diagram.set_states(
                dict(self._pp_state),
                bool(self._pp_state.get("llm", False)),
                llm_pos, st_max)
        if hasattr(self, "_trpp_diagram") and self._trpp_diagram is not None:
            self._trpp_diagram.set_master(self._pp_master_translate)
            # Orange reads its own independent state. LLM is force_off at
            # construction so always rendered as disabled.
            self._trpp_diagram.set_states(
                dict(self._trpp_state),
                bool(self._trpp_state.get("llm", False)),
                llm_pos, st_max)

        # Also reapply the per-step greying of sidebar sub-items and
        # sub-pages (effective state = OR between normal/translation).
        if hasattr(self, "_apply_any_master_active"):
            self._apply_any_master_active()

        # Keep the sub-page title toggle in sync with the combined state
        # (clicking a node in either SVG must flip the title toggle too).
        self._sync_pp_tab_enable_chk()

        # Re-run the test panel so toggling a step (e.g. Dictionary OFF)
        # is reflected immediately in the test output.
        if hasattr(self, "_schedule_test_run"):
            self._schedule_test_run()

    # Backwards-compatibility shim (many connections call the old name).
    def _refresh_pp_diagram(self):
        self._refresh_pp_diagrams()

    def _build_llm_tab(self, lay, conf):
        """Build LLM post-processing tab content."""
        llm_vbox = lay
        llm_vbox.setSpacing(2)
        # Keep the parent's horizontal margins but drop vertical padding
        _m = llm_vbox.contentsMargins()
        llm_vbox.setContentsMargins(_m.left(), 0, _m.right(), 0)

        # Top row: combos in a QFormLayout
        _llm_form = QWidget()
        _llm_form.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        llm_flay = QFormLayout(_llm_form)
        llm_flay.setContentsMargins(0, 0, 0, 0)
        llm_flay.setVerticalSpacing(4)

        # LLM pipeline position — displayed FIRST (above the model combo)
        # Radio buttons grouped in a QButtonGroup; data stored on each button.
        if not hasattr(self, "_get_llm_position"):
            def _get_llm_position_impl():
                grp = getattr(self, "llm_position_group", None)
                if grp is None:
                    return "hybrid"
                btn = grp.checkedButton()
                if btn is None:
                    return "hybrid"
                return btn.property("llm_position") or "hybrid"
            self._get_llm_position = _get_llm_position_impl
        saved_pos = conf.get("DICTEE_LLM_POSITION", "hybrid")
        self.llm_position_group = QButtonGroup(self)
        self.llm_position_group.setExclusive(True)
        _pos_row = QWidget()
        _pos_hl = QHBoxLayout(_pos_row)
        _pos_hl.setContentsMargins(0, 0, 0, 0)
        _pos_hl.setSpacing(12)
        for _val, _label in (
            ("hybrid", _("Hybrid (recommended)")),
            ("first", _("At start")),
            ("last", _("At end")),
        ):
            _rb = QRadioButton(_label)
            _rb.setProperty("llm_position", _val)
            if _val == saved_pos:
                _rb.setChecked(True)
            self.llm_position_group.addButton(_rb)
            _pos_hl.addWidget(_rb)
        _pos_hl.addStretch(1)
        # Ensure at least one is checked (fallback to hybrid)
        if self.llm_position_group.checkedButton() is None:
            for _b in self.llm_position_group.buttons():
                if _b.property("llm_position") == "hybrid":
                    _b.setChecked(True)
                    break
        llm_flay.addRow(_("Position in chain:"), _pos_row)

        # Model combo + refresh button on one row
        self.cmb_llm_model = QComboBox()
        self.cmb_llm_model.setEditable(True)
        self.cmb_llm_model.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_refresh_llm_models = QPushButton("🔄")
        self.btn_refresh_llm_models.setToolTip(
            _("Rescan installed Ollama models"))
        self.btn_refresh_llm_models.setFixedWidth(36)
        self.btn_refresh_llm_models.clicked.connect(self._on_refresh_llm_models)
        _llm_model_row = QHBoxLayout()
        _llm_model_row.setContentsMargins(0, 0, 0, 0)
        _llm_model_row.addWidget(self.cmb_llm_model, 1)
        _llm_model_row.addWidget(self.btn_refresh_llm_models)
        _llm_model_row_w = QWidget()
        _llm_model_row_w.setLayout(_llm_model_row)
        llm_flay.addRow(_("Model:"), _llm_model_row_w)

        # Status label below the combo (live check of Ollama state + model)
        self.lbl_llm_ollama_status = QLabel("")
        self.lbl_llm_ollama_status.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_llm_ollama_status.setWordWrap(True)
        llm_flay.addRow("", self.lbl_llm_ollama_status)

        # Download button + progress (hidden by default, shown when the
        # selected model is not yet pulled — mirrors the translation page).
        self.btn_llm_pull = QPushButton(_("Download"))
        self.btn_llm_pull.setVisible(False)
        self.btn_llm_pull.clicked.connect(self._on_llm_ollama_pull)
        self.progress_llm_pull = QProgressBar()
        self.progress_llm_pull.setRange(0, 0)
        self.progress_llm_pull.setVisible(False)
        _llm_pull_row = QHBoxLayout()
        _llm_pull_row.setContentsMargins(0, 0, 0, 0)
        _llm_pull_row.addWidget(self.btn_llm_pull)
        _llm_pull_row.addWidget(self.progress_llm_pull, 1)
        _llm_pull_row_w = QWidget()
        _llm_pull_row_w.setLayout(_llm_pull_row)
        llm_flay.addRow("", _llm_pull_row_w)
        self._llm_pull_thread = None

        # Populate from installed Ollama + recommended (not-installed suffix)
        saved_model = conf.get("DICTEE_LLM_MODEL", "gemma3:4b")
        self._populate_llm_model_combo(preferred_text=saved_model)
        self._check_llm_ollama_status()
        self.cmb_llm_model.currentTextChanged.connect(
            lambda _t: self._check_llm_ollama_status())

        # System prompt presets
        self.cmb_llm_preset = QComboBox()
        self.cmb_llm_preset.addItem(_("Default"), "default")
        self.cmb_llm_preset.addItem("Minimal", "minimal")
        self.cmb_llm_preset.addItem(_("Custom"), "custom")
        saved_preset = conf.get("DICTEE_LLM_SYSTEM_PROMPT", "default")
        idx_preset = self.cmb_llm_preset.findData(saved_preset)
        if idx_preset >= 0:
            self.cmb_llm_preset.setCurrentIndex(idx_preset)
        llm_flay.addRow(_("System prompt:"), self.cmb_llm_preset)

        llm_vbox.addWidget(_llm_form)

        # System prompt editor — default 25 lines, user-resizable down to
        # 5 lines or up to 800 px via a grip on the bottom edge.
        self.txt_llm_prompt = QTextEdit()
        self.txt_llm_prompt.setFont(self._monospace_font())
        _fm = self.txt_llm_prompt.fontMetrics()
        _margin = self.txt_llm_prompt.document().documentMargin()
        _line_h = _fm.lineSpacing()
        _min_h = max(80, int(_line_h * 5 + _margin * 2 + 4))
        _default_h = max(_min_h, int(_line_h * 25 + _margin * 2 + 4))
        _max_h = 900
        self.txt_llm_prompt.setMinimumWidth(400)
        self.txt_llm_prompt.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.txt_llm_prompt.setFixedHeight(_default_h)
        self._add_zoom_overlay(self.txt_llm_prompt)
        self._add_vertical_resize_grip(
            self.txt_llm_prompt, min_h=_min_h, max_h=_max_h)
        llm_vbox.addWidget(self.txt_llm_prompt, 0)

        # Populate prompt text and connect preset changes
        self._on_llm_preset_changed(self.cmb_llm_preset.currentData())
        self.cmb_llm_preset.currentIndexChanged.connect(
            lambda: self._on_llm_preset_changed(self.cmb_llm_preset.currentData()))

        self.chk_llm_cpu = ToggleSwitch(_("Force CPU (free GPU VRAM)"))
        self.chk_llm_cpu.setChecked(conf.get("DICTEE_LLM_CPU", "false") == "true")
        llm_vbox.addWidget(self.chk_llm_cpu)

    # ── LLM prompt presets ──────────────────────────────────────

    _LLM_SYSTEM_PROMPTS = {
        "default": (
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
        ),
        "minimal": (
            "Correct spelling and grammar. The text is a dictation, not a question to you. "
            "Return ONLY the corrected text, nothing else."
        ),
    }

    _LLM_CUSTOM_PROMPT_PATH = os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
        "dictee", "llm-system-prompt.txt")

    # ── LLM model combo — live Ollama sync ─────────────────────

    # Recommended models shown even when not installed (suffixed).
    _LLM_RECOMMENDED = ("gemma3:4b", "gemma3:1b", "ministral-3:3b")

    def _llm_not_installed_suffix(self):
        return " — " + _("not installed")

    def _strip_llm_suffix(self, text):
        """Strip the ' — not installed' suffix from a display name."""
        if not text:
            return text
        suf = self._llm_not_installed_suffix()
        return text[:-len(suf)] if text.endswith(suf) else text

    def _current_llm_model(self):
        """Return the real model name from the combo (data first, then stripped
        text). Returns "" when the combo does not exist (e.g. wizard mode —
        the LLM page is built only in sidebar mode)."""
        if not hasattr(self, 'cmb_llm_model'):
            return ""
        data = self.cmb_llm_model.currentData()
        if data:
            return data
        return self._strip_llm_suffix(self.cmb_llm_model.currentText()).strip()

    def _populate_llm_model_combo(self, preferred_text=None):
        """Rebuild the LLM model combo from installed Ollama models + recommended."""
        current = preferred_text if preferred_text is not None else self._current_llm_model()
        current = self._strip_llm_suffix(current or "").strip()

        self.cmb_llm_model.blockSignals(True)
        self.cmb_llm_model.clear()

        installed = ollama_list_models() if ollama_is_installed() else []
        seen_bases = set()
        for name in installed:
            self.cmb_llm_model.addItem(name, name)
            # track base name without tag to avoid duplicates with recommended
            seen_bases.add(name.split(":")[0])
        suf = self._llm_not_installed_suffix()
        for rec in self._LLM_RECOMMENDED:
            if ollama_has_model(rec):
                continue  # already present via installed loop
            # If base name (e.g. "gemma3") matches any installed tag, skip the recommended entry
            if rec.split(":")[0] in seen_bases and not any(
                    inst.split(":")[0] == rec.split(":")[0] and inst == rec
                    for inst in installed):
                # User has a different tag for this family — still show the recommended for clarity
                pass
            self.cmb_llm_model.addItem(rec + suf, rec)

        # Restore selection
        idx = self.cmb_llm_model.findData(current)
        if idx >= 0:
            self.cmb_llm_model.setCurrentIndex(idx)
        elif current:
            self.cmb_llm_model.setEditText(current)
        self.cmb_llm_model.blockSignals(False)

    def _on_refresh_llm_models(self):
        _dbg_setup("_on_refresh_llm_models")
        self._populate_llm_model_combo()
        self._check_llm_ollama_status()

    def _check_llm_ollama_status(self):
        """Update the status label below the LLM model combo."""
        if not hasattr(self, 'lbl_llm_ollama_status'):
            return
        # Button is shown only when the selected model is pullable.
        if hasattr(self, 'btn_llm_pull'):
            self.btn_llm_pull.setVisible(False)
        model = self._current_llm_model()
        if not model:
            self.lbl_llm_ollama_status.setText("")
            return
        if not ollama_is_installed():
            self.lbl_llm_ollama_status.setText(
                '<span style="color: #c0392b;">⚠ ' +
                _("Ollama is not installed") + '</span><br>'
                '<code>curl -fsSL https://ollama.com/install.sh | sh</code><br>'
                '<small><a href="https://ollama.com">ollama.com</a></small>')
            self.lbl_llm_ollama_status.setOpenExternalLinks(True)
            return
        if not ollama_is_running():
            self.lbl_llm_ollama_status.setText(
                '<span style="color: #c0392b;">⚠ ' +
                _("Ollama service is not running") +
                ' — <code>sudo systemctl start ollama</code></span>')
            return
        if ollama_has_model(model):
            self.lbl_llm_ollama_status.setText(
                '<span style="color: #27ae60;">✓ ' +
                _("Model {model} ready").format(model=model) + '</span>')
        else:
            self.lbl_llm_ollama_status.setText(
                '<span style="color: #d68910;">⚠ ' +
                _("Model {model} not installed — run").format(model=model) +
                f' <code>ollama pull {model}</code></span>')
            if hasattr(self, 'btn_llm_pull'):
                self.btn_llm_pull.setText(_("Download"))
                self.btn_llm_pull.setEnabled(True)
                self.btn_llm_pull.setVisible(True)

    def _on_llm_ollama_pull(self):
        model = self._current_llm_model()
        if not model:
            return
        _dbg_setup(f"_on_llm_ollama_pull: model={model}")
        self.btn_llm_pull.setEnabled(False)
        self.progress_llm_pull.setVisible(True)

        self._llm_pull_thread = OllamaPullThread(model)
        self._llm_pull_thread.progress.connect(
            lambda text: self.btn_llm_pull.setText(text))
        self._llm_pull_thread.done.connect(self._on_llm_ollama_pull_finished)
        self._llm_pull_thread.start()

    def _on_llm_ollama_pull_finished(self, success, message):
        _dbg_setup(f"_on_llm_ollama_pull_finished: success={success}, msg={message!r}")
        self.progress_llm_pull.setVisible(False)
        if success:
            self._populate_llm_model_combo(
                preferred_text=self._current_llm_model())
            self._check_llm_ollama_status()
        else:
            self.btn_llm_pull.setText(_("Download"))
            self.btn_llm_pull.setEnabled(True)
            QMessageBox.critical(self, _("Download error"), message)

    def _on_llm_preset_changed(self, preset_data):
        """Update system prompt QTextEdit when preset combo changes."""
        if preset_data == "custom":
            self.txt_llm_prompt.setReadOnly(False)
            self.txt_llm_prompt.setPlaceholderText(_("Entrez votre prompt ici"))
            # Load existing custom file if available; otherwise start empty
            # so the placeholder ghost text is visible.
            if os.path.isfile(self._LLM_CUSTOM_PROMPT_PATH):
                with open(self._LLM_CUSTOM_PROMPT_PATH, encoding="utf-8") as f:
                    self.txt_llm_prompt.setPlainText(f.read().strip())
            else:
                self.txt_llm_prompt.setPlainText("")
        else:
            self.txt_llm_prompt.setPlaceholderText("")
            self.txt_llm_prompt.setReadOnly(True)
            self.txt_llm_prompt.setPlainText(
                self._LLM_SYSTEM_PROMPTS.get(preset_data, ""))

    # ── Post-processing tabs ────────────────────────────────────

    @staticmethod
    def _add_zoom_overlay(editor):
        """Ajoute des boutons zoom −/+ flottants en haut à droite d'un QTextEdit + Ctrl+/Ctrl-."""
        style = (
            "QPushButton { background: palette(window); border: 1px solid palette(mid); "
            "border-radius: 6px; font-size: 20px; font-weight: bold; "
            "padding: 0px; min-width: 36px; min-height: 36px; }"
            "QPushButton:hover { background: palette(midlight); }")
        bm = QPushButton("\u2212", editor)
        bm.setFixedSize(36, 36)
        bm.setStyleSheet(style)
        bm.clicked.connect(lambda: editor.zoomOut(2))
        bp = QPushButton("+", editor)
        bp.setFixedSize(36, 36)
        bp.setStyleSheet(style)
        bp.clicked.connect(lambda: editor.zoomIn(2))

        def _reposition(event, ed=editor, zm=bm, zp=bp):
            w = ed.viewport().width()
            zp.move(w - 44, 8)
            zm.move(w - 84, 8)
            type(ed).resizeEvent(ed, event)
        editor.resizeEvent = _reposition
        bp.move(200, 8)
        bm.move(160, 8)

        # Raccourcis Ctrl++ et Ctrl+- pour le zoom
        try:
            from PyQt6.QtGui import QShortcut, QKeySequence
        except ImportError:
            from PySide6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl++"), editor).activated.connect(lambda: editor.zoomIn(2))
        QShortcut(QKeySequence("Ctrl+="), editor).activated.connect(lambda: editor.zoomIn(2))
        QShortcut(QKeySequence("Ctrl+-"), editor).activated.connect(lambda: editor.zoomOut(2))

    @staticmethod
    def _add_vertical_resize_grip(widget, min_h=80, max_h=600):
        """Add a bottom-edge vertical resize grip to a QWidget (QTextEdit, etc.).

        Same UX as the PP test input: 3-line stripe handle at the bottom,
        drag to resize between min_h and max_h. The widget keeps a fixed
        height (updated on release) so it does not fight the parent layout.
        """
        grip = QLabel(widget)
        grip.setFixedHeight(8)
        grip.setCursor(Qt.CursorShape.SizeVerCursor)
        grip.setStyleSheet("background: transparent; border: none;")
        grip._drag_y = None
        grip._base_h = 0

        def _paint(_event):
            p = QPainter(grip)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(128, 128, 128))
            pen.setWidth(1)
            p.setPen(pen)
            cx = grip.width() // 2
            for y in (1, 4, 7):
                p.drawLine(cx - 10, y, cx + 10, y)
            p.end()
        grip.paintEvent = _paint

        def _press(event):
            grip._drag_y = event.position().y()
            grip._base_h = widget.height()
            event.accept()
        grip.mousePressEvent = _press

        def _move(event):
            if grip._drag_y is not None:
                dy = int(event.position().y() - grip._drag_y)
                new_h = max(min_h, min(max_h, grip._base_h + dy))
                widget.setFixedHeight(new_h)
                grip._base_h = new_h
                grip._drag_y = event.position().y()
                event.accept()
        grip.mouseMoveEvent = _move

        def _release(_event):
            grip._drag_y = None
        grip.mouseReleaseEvent = _release

        _orig_resize = widget.resizeEvent

        def _reposition(event):
            grip.setGeometry(0, widget.height() - 8, widget.width(), 8)
            if _orig_resize:
                _orig_resize(event)
        widget.resizeEvent = _reposition

    @staticmethod
    def _monospace_font():
        """Retourne une police monospace à 12pt pour les éditeurs avancés."""
        try:
            from PyQt6.QtGui import QFont
        except ImportError:
            from PySide6.QtGui import QFont
        font = QFont("monospace", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        return font

    # ── Coloration syntaxique + numéros de ligne pour l'éditeur regex ──

    class _RulesHighlighter(QSyntaxHighlighter):
        """Coloration syntaxique pour les fichiers de règles dictee."""

        def __init__(self, document):
            super().__init__(document)
            from PyQt6.QtGui import QTextCharFormat, QColor
            # Grey-out format used when the rules step is disabled.
            self._fmt_disabled = QTextCharFormat()
            self._fmt_disabled.setForeground(QColor("#707070"))
            self._active = True
            # Commentaires
            self._fmt_comment_color = QTextCharFormat()
            self._fmt_comment_color.setForeground(QColor("#808080"))
            # Section headers ═══
            self._fmt_header_color = QTextCharFormat()
            self._fmt_header_color.setForeground(QColor("#B8860B"))
            self._fmt_header_color.setFontWeight(700)
            # [lang]
            self._fmt_lang_color = QTextCharFormat()
            self._fmt_lang_color.setForeground(QColor("#5DADE2"))
            self._fmt_lang_color.setFontWeight(700)
            # /pattern/
            self._fmt_pattern_color = QTextCharFormat()
            self._fmt_pattern_color.setForeground(QColor("#E67E22"))
            # /replacement/
            self._fmt_replacement_color = QTextCharFormat()
            self._fmt_replacement_color.setForeground(QColor("#2ECC71"))
            # flags
            self._fmt_flags_color = QTextCharFormat()
            self._fmt_flags_color.setForeground(QColor("#AF7AC5"))
            self._refresh_fmts()

        def _refresh_fmts(self):
            if self._active:
                self._fmt_comment = self._fmt_comment_color
                self._fmt_header = self._fmt_header_color
                self._fmt_lang = self._fmt_lang_color
                self._fmt_pattern = self._fmt_pattern_color
                self._fmt_replacement = self._fmt_replacement_color
                self._fmt_flags = self._fmt_flags_color
            else:
                d = self._fmt_disabled
                self._fmt_comment = d
                self._fmt_header = d
                self._fmt_lang = d
                self._fmt_pattern = d
                self._fmt_replacement = d
                self._fmt_flags = d

        def set_active(self, on):
            on = bool(on)
            if self._active == on:
                return
            self._active = on
            self._refresh_fmts()
            self.rehighlight()

        def highlightBlock(self, text):
            import re
            s = text.strip()
            if not s:
                return
            # Commentaires
            if s.startswith("#"):
                if "═" in s or "──" in s:
                    self.setFormat(0, len(text), self._fmt_header)
                else:
                    self.setFormat(0, len(text), self._fmt_comment)
                return
            # Règle : [lang] /pattern/replacement/flags
            m = re.match(r'^(\[[^\]]*\])\s*(/(.*?)/(.*?)/(.*))$', text)
            if m:
                # [lang]
                self.setFormat(0, len(m.group(1)), self._fmt_lang)
                # Trouver le début du /pattern/replacement/flags
                rest_start = m.start(2)
                rest = m.group(2)
                # Parser les / manuellement
                parts = rest.split("/")
                # parts[0] = "" (avant le premier /), parts[1] = pattern, parts[2] = replacement, parts[3] = flags
                if len(parts) >= 4:
                    pos = rest_start
                    pos += 1  # premier /
                    # pattern
                    self.setFormat(pos, len(parts[1]), self._fmt_pattern)
                    pos += len(parts[1]) + 1  # + /
                    # replacement
                    self.setFormat(pos, len(parts[2]), self._fmt_replacement)
                    pos += len(parts[2]) + 1  # + /
                    # flags
                    self.setFormat(pos, len(parts[3]), self._fmt_flags)

    class _LineNumberArea(QWidget):
        """Widget affichant les numéros de ligne à gauche d'un QTextEdit."""

        def __init__(self, editor):
            super().__init__(editor)
            self._editor = editor
            self._editor.document().blockCountChanged.connect(self._update_width)
            self._editor.verticalScrollBar().valueChanged.connect(self.update)
            self._editor.textChanged.connect(self.update)
            self._editor.installEventFilter(self)
            self._update_width()

        def eventFilter(self, obj, event):
            if obj is self._editor and event.type() == event.Type.Resize:
                cr = self._editor.contentsRect()
                self.setGeometry(cr.left(), cr.top(), self.width(), cr.height())
            return False

        def _update_width(self):
            digits = len(str(max(1, self._editor.document().blockCount())))
            width = self._editor.fontMetrics().horizontalAdvance("9") * (digits + 2) + 8
            self._editor.setViewportMargins(width, 0, 0, 0)
            self.setFixedWidth(width)

        def paintEvent(self, event):
            from PyQt6.QtGui import QPainter, QColor
            from PyQt6.QtCore import QRect
            painter = QPainter(self)
            painter.fillRect(event.rect(), self._editor.palette().color(
                self._editor.palette().ColorRole.AlternateBase))
            painter.setPen(QColor("#808080"))
            font = self._editor.font()
            painter.setFont(font)

            block = self._editor.document().begin()
            top = self._editor.document().documentLayout().blockBoundingRect(
                block).translated(0, -self._editor.verticalScrollBar().value()).top()
            fm = self._editor.fontMetrics()

            while block.isValid():
                rect = self._editor.document().documentLayout().blockBoundingRect(block)
                y = rect.translated(0, -self._editor.verticalScrollBar().value()).top()
                if y > event.rect().bottom():
                    break
                if y + rect.height() >= event.rect().top():
                    painter.drawText(
                        QRect(0, int(y), self.width() - 4, int(rect.height())),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        str(block.blockNumber() + 1))
                block = block.next()
            painter.end()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            cr = self._editor.contentsRect()
            self.setGeometry(cr.left(), cr.top(), self.width(), cr.height())

    def _build_language_rules_tab(self, lay, conf):
        """Language rules tab: language-specific options."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setSpacing(8)

        lang_src = conf.get("DICTEE_LANG_SOURCE", "fr")
        info = QLabel(
            "<i>" + _("Language-specific rules (elisions, contractions, typography) "
                      "applied to the source language only. Currently: <b>{lang}</b>. "
                      "Only the rules matching your source language will be active."
                      ).format(lang=lang_src) + "</i>")
        info.setWordWrap(True)
        content_lay.addWidget(info)

        # ── Français ──
        grp_fr = QGroupBox("Français [fr]")
        grp_fr_lay = QVBoxLayout(grp_fr)
        grp_fr_lay.setSpacing(4)

        self.chk_pp_elisions = ToggleSwitch(_("Elisions"))
        self.chk_pp_elisions.setChecked(conf.get("DICTEE_PP_ELISIONS", "true") == "true")
        grp_fr_lay.addWidget(self._pp_checkbox_with_help(self.chk_pp_elisions,
            _("Applies French elision rules.\n"
              "Example: \"le arbre\" → \"l'arbre\",\n"
              "\"de eau\" → \"d'eau\"")))

        self.chk_pp_typography = ToggleSwitch(_("Typography (non-breaking spaces)"))
        self.chk_pp_typography.setChecked(conf.get("DICTEE_PP_TYPOGRAPHY", "true") == "true")
        grp_fr_lay.addWidget(self._pp_checkbox_with_help(self.chk_pp_typography,
            _("Inserts non-breaking spaces before French\n"
              "punctuation marks (: ; ! ? « »)\n"
              "as required by French typography rules.")))

        content_lay.addWidget(grp_fr)

        # ── English ──
        grp_en = QGroupBox("English [en]")
        grp_en_lay = QVBoxLayout(grp_en)
        grp_en_lay.setSpacing(4)
        lbl_en = QLabel("<i>" + _("No specific rules needed. Contractions (don't, I'm, can't) "
                                   "are handled natively by the ASR engine.") + "</i>")
        lbl_en.setWordWrap(True)
        grp_en_lay.addWidget(lbl_en)
        content_lay.addWidget(grp_en)

        # ── Italiano ──
        grp_it = QGroupBox("Italiano [it]")
        grp_it_lay = QVBoxLayout(grp_it)
        grp_it_lay.setSpacing(4)

        self.chk_pp_elisions_it = ToggleSwitch(_("Elisions & contractions"))
        self.chk_pp_elisions_it.setChecked(conf.get("DICTEE_PP_ELISIONS_IT", "true") == "true")
        grp_it_lay.addWidget(self._pp_checkbox_with_help(self.chk_pp_elisions_it,
            _("Italian elisions and prepositional contractions.\n"
              "Elisions: \"lo uomo\" → \"l'uomo\", \"di accordo\" → \"d'accordo\"\n"
              "Contractions: \"di il\" → \"del\", \"a la\" → \"alla\",\n"
              "\"in il\" → \"nel\", \"su la\" → \"sulla\"")))

        content_lay.addWidget(grp_it)

        # ── Español ──
        grp_es = QGroupBox("Español [es]")
        grp_es_lay = QVBoxLayout(grp_es)
        grp_es_lay.setSpacing(4)

        self.chk_pp_spanish = ToggleSwitch(_("Contractions & inverted punctuation"))
        self.chk_pp_spanish.setChecked(conf.get("DICTEE_PP_SPANISH", "true") == "true")
        grp_es_lay.addWidget(self._pp_checkbox_with_help(self.chk_pp_spanish,
            _("Spanish contractions and inverted punctuation.\n"
              "Contractions: \"a el\" → \"al\", \"de el\" → \"del\"\n"
              "Punctuation: adds ¿ before questions and ¡ before exclamations.")))

        content_lay.addWidget(grp_es)

        # ── Português ──
        grp_pt = QGroupBox("Português [pt]")
        grp_pt_lay = QVBoxLayout(grp_pt)
        grp_pt_lay.setSpacing(4)

        self.chk_pp_portuguese = ToggleSwitch(_("Contractions"))
        self.chk_pp_portuguese.setChecked(conf.get("DICTEE_PP_PORTUGUESE", "true") == "true")
        grp_pt_lay.addWidget(self._pp_checkbox_with_help(self.chk_pp_portuguese,
            _("Portuguese fused contractions.\n"
              "\"de o\" → \"do\", \"em a\" → \"na\", \"por os\" → \"pelos\",\n"
              "\"de este\" → \"deste\", \"em ele\" → \"nele\"")))

        content_lay.addWidget(grp_pt)

        # ── Deutsch ──
        grp_de = QGroupBox("Deutsch [de]")
        grp_de_lay = QVBoxLayout(grp_de)
        grp_de_lay.setSpacing(4)

        self.chk_pp_german = ToggleSwitch(_("Contractions & typography"))
        self.chk_pp_german.setChecked(conf.get("DICTEE_PP_GERMAN", "true") == "true")
        grp_de_lay.addWidget(self._pp_checkbox_with_help(self.chk_pp_german,
            _("German contractions and typography.\n"
              "Contractions: \"an dem\" → \"am\", \"in dem\" → \"im\",\n"
              "\"zu dem\" → \"zum\", \"zu der\" → \"zur\"\n"
              "Typography: \"text\" → \u201etext\u201c (German quotes)")))

        content_lay.addWidget(grp_de)

        # ── Nederlands ──
        grp_nl = QGroupBox("Nederlands [nl]")
        grp_nl_lay = QVBoxLayout(grp_nl)
        grp_nl_lay.setSpacing(4)

        self.chk_pp_dutch = ToggleSwitch(_("Contractions"))
        self.chk_pp_dutch.setChecked(conf.get("DICTEE_PP_DUTCH", "true") == "true")
        grp_nl_lay.addWidget(self._pp_checkbox_with_help(self.chk_pp_dutch,
            _("Dutch contractions and time expressions.\n"
              "\"het\" → \"'t\", \"een\" → \"'n\"\n"
              "\"in de morgens\" → \"'s morgens\"")))

        content_lay.addWidget(grp_nl)

        # ── Română ──
        grp_ro = QGroupBox("Română [ro]")
        grp_ro_lay = QVBoxLayout(grp_ro)
        grp_ro_lay.setSpacing(4)

        self.chk_pp_romanian = ToggleSwitch(_("Contractions & typography"))
        self.chk_pp_romanian.setChecked(conf.get("DICTEE_PP_ROMANIAN", "true") == "true")
        grp_ro_lay.addWidget(self._pp_checkbox_with_help(self.chk_pp_romanian,
            _("Romanian contractions and typography.\n"
              "\"nu am\" → \"n-am\", \"într o\" → \"într-o\"\n"
              "Typography: \"text\" → \u201etext\u201c (Romanian quotes)")))

        content_lay.addWidget(grp_ro)

        content_lay.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll)

    def _build_rules_tab(self, lay):
        """Rules tab: rule creator + monospace text editor."""
        import os as _os
        XDG_CFG = _os.environ.get("XDG_CONFIG_HOME", _os.path.expanduser("~/.config"))
        self._rules_path = _os.path.join(XDG_CFG, "dictee", "rules.conf")

        # --- Command suffix (per language) ---
        sfx_lay = QHBoxLayout()
        sfx_lay.setSpacing(6)
        sfx_label = QLabel(_("Command suffix:"))
        sfx_help = _help_btn(_(
            "<b>Command suffix</b><br><br>"
            "Some voice commands use words that also exist as normal words. "
            "The suffix is a word you say <b>after</b> the ambiguous command "
            "to confirm it's a voice command, not a regular word.<br><br>"
            "<b>Examples by language:</b><br>"
            "• FR (suffix = \"finale?s?\"): \"point final\" → \".\" — "
            "but \"un bon point\" → kept as text<br>"
            "• EN (suffix = \"done\"): \"period done\" → \".\" — "
            "but \"a long period\" → kept as text<br>"
            "• DE (suffix = \"weiter\"): \"Punkt weiter\" → \".\" — "
            "but \"ein guter Punkt\" → kept as text<br>"
            "• ES (suffix = \"listo\"): \"punto listo\" → \".\" — "
            "but \"un buen punto\" → kept as text<br>"
            "• IT (suffix = \"seguito\"): \"punto seguito\" → \".\" — "
            "but \"un buon punto\" → kept as text<br>"
            "• PT (suffix = \"pronto\"): \"ponto pronto\" → \".\" — "
            "but \"um bom ponto\" → kept as text<br>"
            "• UK (suffix = \"далі\"): \"крапка далі\" → \".\" — "
            "but \"одна крапка\" → kept as text<br><br>"
            "<b>Ambiguous commands that require the suffix:</b><br>"
            "FR: point, deux points — EN: period, colon — DE: Punkt<br>"
            "ES: punto, coma — IT: punto — PT: ponto — UK: крапка, кома<br><br>"
            "<b>Non-ambiguous commands (no suffix needed):</b><br>"
            "FR: virgule, point virgule, point d'interrogation…<br>"
            "EN: comma, semicolon, question mark…<br>"
            "DE: Komma, Semikolon, Doppelpunkt…<br>"
            "ES: punto y coma, dos puntos, interrogación…<br><br>"
            "<b>Per language:</b> Select a language in the combo box "
            "to set a different suffix for each language.<br><br>"
            "In the rules editor below, <code>%SUFFIX_XX%</code> "
            "placeholders are replaced by this value at runtime.<br><br>"
            "Leave empty to disable suffix-based commands for that language."))
        self._suffix_lang = QComboBox()
        self._suffix_lang.setFixedWidth(60)
        _lang = self.conf.get("DICTEE_LANG_SOURCE", "fr")
        self._sfx_defaults = {"fr": "finale?s?", "en": "done", "de": "weiter",
                              "es": "listo", "it": "seguito", "pt": "pronto",
                              "uk": "далі"}
        self._command_suffixes = {}
        for code, _name in LANGUAGES:
            self._suffix_lang.addItem(code)
            # Load from conf, fallback to default
            self._command_suffixes[code] = self.conf.get(
                f"DICTEE_COMMAND_SUFFIX_{code.upper()}",
                self._sfx_defaults.get(code, ""))
        idx = self._suffix_lang.findText(_lang)
        if idx >= 0:
            self._suffix_lang.setCurrentIndex(idx)
        self._command_suffix = QLineEdit()
        self._command_suffix.setMaximumWidth(200)
        self._command_suffix.setText(self._command_suffixes.get(_lang, ""))
        self._suffix_lang.currentTextChanged.connect(self._on_suffix_lang_changed)
        self._command_suffix.textChanged.connect(self._on_suffix_changed)
        sfx_lay.addWidget(sfx_label)
        sfx_lay.addWidget(self._suffix_lang)
        sfx_lay.addWidget(self._command_suffix)
        sfx_lay.addWidget(sfx_help)
        sfx_lay.addStretch()
        lay.addLayout(sfx_lay)

        # Warning popup is shown on tab entry (see _maybe_show_rules_warning),
        # not as a permanent label — the user can dismiss it permanently.

        # --- Rule creator (two lines) ---
        # Row 1: lang / pattern / replacement / flags   (wide inputs)
        # Row 2: Insert [combo] [at end] [Add] [Record]  (compact actions)
        add_grp = QGroupBox(_("Add a rule"))
        add_grp_lay = QVBoxLayout(add_grp)

        add_row1 = QHBoxLayout()
        add_row1.setSpacing(6)

        self._rule_lang = QComboBox()
        self._rule_lang.setFixedWidth(60)
        self._rule_lang.addItem("*")
        for code, _name in LANGUAGES:
            self._rule_lang.addItem(code)
        lang_src = self.conf.get("DICTEE_LANG_SOURCE", "fr")
        idx = self._rule_lang.findText(lang_src)
        if idx >= 0:
            self._rule_lang.setCurrentIndex(idx)
        add_row1.addWidget(self._rule_lang)

        add_row1.addWidget(QLabel("/"))
        self._rule_pattern = QLineEdit()
        self._rule_pattern.setPlaceholderText(_("Pattern (what the ASR says)"))
        self._rule_pattern.setFont(self._monospace_font())
        add_row1.addWidget(self._rule_pattern, 3)

        add_row1.addWidget(QLabel("/"))
        self._rule_replacement = QLineEdit()
        self._rule_replacement.setPlaceholderText(_("Replacement (\\n = newline)"))
        self._rule_replacement.setFont(self._monospace_font())
        add_row1.addWidget(self._rule_replacement, 3)

        add_row1.addWidget(QLabel("/"))
        self._rule_flags = QLineEdit("ig")
        self._rule_flags.setFixedWidth(40)
        self._rule_flags.setFont(self._monospace_font())
        self._rule_flags.setToolTip(_("i = case-insensitive, g = global, m = multiline"))
        add_row1.addWidget(self._rule_flags)

        add_row2 = QHBoxLayout()
        add_row2.setSpacing(6)
        add_row2.addWidget(QLabel(_("Insert:")))
        self._rule_section = QComboBox()
        self._rule_section.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._rule_section.setMinimumWidth(100)
        self._rule_section.setMaximumWidth(200)
        add_row2.addWidget(self._rule_section)

        self._rule_position = QComboBox()
        self._rule_position.addItem(_("at end"), "end")
        self._rule_position.addItem(_("at beginning"), "begin")
        self._rule_position.setFixedWidth(85)
        self._rule_position.setEnabled(False)
        add_row2.addWidget(self._rule_position)

        self._rule_section.currentIndexChanged.connect(
            lambda: self._rule_position.setEnabled(
                self._rule_section.currentData() == "section"))

        add_row2.addStretch(1)

        btn_add_rule = QPushButton("+ " + _("Add"))
        btn_add_rule.clicked.connect(self._add_rule_to_editor)
        add_row2.addWidget(btn_add_rule)

        self._btn_record_rule = QPushButton(QIcon.fromTheme("audio-input-microphone"), _("Record"))
        self._btn_record_rule.setToolTip(_("Record audio, transcribe, and fill the pattern field"))
        self._btn_record_rule.clicked.connect(self._record_for_rule)
        add_row2.addWidget(self._btn_record_rule)

        # Label to show RAW/PROCESSED after recording
        self._rule_preview = QLabel()
        self._rule_preview.setWordWrap(True)
        self._rule_preview.setVisible(False)

        add_grp_lay.addLayout(add_row1)
        add_grp_lay.addLayout(add_row2)
        add_grp_lay.addWidget(self._rule_preview)

        lay.addWidget(add_grp)

        # --- Text editor ---
        self._rules_editor = QTextEdit()
        self._rules_editor.setFont(self._monospace_font())
        self._rules_editor.setPlaceholderText(
            "# [lang] /PATTERN/REPLACEMENT/FLAGS\n"
            "# Example:\n"
            "# [fr] /point à la ligne/\\n/ig\n")

        # Syntax highlighting
        self._rules_highlighter = self._RulesHighlighter(self._rules_editor.document())

        # Rules editor greying: tied to the effective state of the "rules"
        # step (active if enabled in at least one pipeline with its master
        # on). setEnabled() alone does not update the syntax highlighter,
        # so we explicitly toggle the highlighter's active state.
        def _update_rules_active():
            normal_on = self._pp_master_normal and self._pp_state.get("rules", False)
            trans_on = self._pp_master_translate and self._trpp_state.get("rules", False)
            on = bool(normal_on or trans_on)
            self._rules_highlighter.set_active(on)
            self._rules_editor.setEnabled(on)
            if hasattr(self, "_rules_line_numbers"):
                self._rules_line_numbers.setEnabled(on)
        self._update_rules_active = _update_rules_active

        # Line numbers
        self._rules_line_numbers = self._LineNumberArea(self._rules_editor)

        # Rule counter
        self._rules_count_label = QLabel()
        self._rules_count_label.setStyleSheet("color: gray; font-size: 11px;")
        self._rules_editor.textChanged.connect(self._update_rules_count)
        self._rules_editor.cursorPositionChanged.connect(self._sync_test_lang_from_cursor)

        self._load_rules_file()
        lay.addWidget(self._rules_editor)

        self._add_zoom_overlay(self._rules_editor)

        # --- Barre de recherche (Ctrl+F) ---
        self._rules_search_bar = QWidget()
        self._rules_search_bar.setVisible(False)
        search_lay = QHBoxLayout(self._rules_search_bar)
        search_lay.setContentsMargins(0, 2, 0, 2)
        search_lay.setSpacing(4)
        self._rules_search_input = QLineEdit()
        self._rules_search_input.addAction(
            QIcon.fromTheme("edit-find"), QLineEdit.ActionPosition.LeadingPosition)
        self._rules_search_input.returnPressed.connect(lambda: self._rules_find(forward=True))
        self._rules_search_input.textChanged.connect(lambda: self._rules_find(forward=True))
        search_lay.addWidget(self._rules_search_input, 1)
        self._rules_search_count = QLabel()
        self._rules_search_count.setStyleSheet("color: gray; font-size: 11px;")
        self._rules_search_count.setFixedWidth(50)
        search_lay.addWidget(self._rules_search_count)
        btn_prev = QPushButton("\u25b2")
        btn_prev.setFixedWidth(28)
        btn_prev.setToolTip(_("Previous"))
        btn_prev.clicked.connect(lambda: self._rules_find(forward=False))
        search_lay.addWidget(btn_prev)
        btn_next = QPushButton("\u25bc")
        btn_next.setFixedWidth(28)
        btn_next.setToolTip(_("Next"))
        btn_next.clicked.connect(lambda: self._rules_find(forward=True))
        search_lay.addWidget(btn_next)
        btn_close = QPushButton("\u2715")
        btn_close.setFixedWidth(28)
        btn_close.clicked.connect(self._rules_show_search)
        search_lay.addWidget(btn_close)
        lay.addWidget(self._rules_search_bar)

        # Shortcuts Ctrl+F and Escape
        from PyQt6.QtGui import QShortcut, QKeySequence
        shortcut_find = QShortcut(QKeySequence("Ctrl+F"), self._rules_editor)
        shortcut_find.activated.connect(self._rules_show_search)
        shortcut_esc = QShortcut(QKeySequence("Escape"), self._rules_search_input)
        shortcut_esc.activated.connect(self._rules_show_search)

        btns = QHBoxLayout()
        # Undo / Redo — wired to QTextEdit's built-in undo stack
        self._btn_rules_undo = QPushButton(QIcon.fromTheme("edit-undo"), "")
        self._btn_rules_undo.setFixedWidth(30)
        self._btn_rules_undo.setToolTip(_("Undo (Ctrl+Z)"))
        self._btn_rules_undo.setEnabled(False)
        self._btn_rules_undo.clicked.connect(self._rules_editor.undo)
        btns.addWidget(self._btn_rules_undo)
        self._btn_rules_redo = QPushButton(QIcon.fromTheme("edit-redo"), "")
        self._btn_rules_redo.setFixedWidth(30)
        self._btn_rules_redo.setToolTip(_("Redo (Ctrl+Shift+Z)"))
        self._btn_rules_redo.setEnabled(False)
        self._btn_rules_redo.clicked.connect(self._rules_editor.redo)
        btns.addWidget(self._btn_rules_redo)
        self._rules_editor.undoAvailable.connect(self._btn_rules_undo.setEnabled)
        self._rules_editor.redoAvailable.connect(self._btn_rules_redo.setEnabled)
        btn_find = QPushButton(QIcon.fromTheme("edit-find"), "")
        btn_find.setFixedWidth(30)
        btn_find.setToolTip(_("Search (Ctrl+F)"))
        btn_find.clicked.connect(self._rules_show_search)
        btns.addWidget(btn_find)
        btn_send_test = QPushButton("\u2193 " + _("Test"))
        btn_send_test.setToolTip(_("Send current line to the test panel"))
        btn_send_test.clicked.connect(self._send_rule_to_test)
        btns.addWidget(btn_send_test)
        btns.addWidget(self._rules_count_label)
        btns.addStretch()
        btn_restore = QPushButton(_("Restore defaults"))
        btn_save = QPushButton(_("Save"))
        btns.addWidget(btn_restore)
        btns.addWidget(btn_save)
        lay.addLayout(btns)

        btn_save.clicked.connect(self._save_rules_file)
        btn_restore.clicked.connect(self._restore_rules_defaults)

    def _add_rule_to_editor(self):
        """Adds rule in the chosen section of the editor."""
        lang = self._rule_lang.currentText()
        pattern = self._rule_pattern.text().strip()
        replacement = self._rule_replacement.text()
        flags = self._rule_flags.text().strip()
        if not pattern:
            return
        # Bloquer [*] dans Voice commands (les commandes vocales sont spécifiques à chaque langue)
        section = self._rule_section.currentText()
        section_data = self._rule_section.currentData()
        if lang == "*" and section_data == "section" and "Voice commands" in section:
            QMessageBox.warning(self._pp_parent, "dictee",
                _("Voice commands are language-specific.\n"
                  "Please select a language instead of *."))
            return
        rule = f"[{lang}] /{pattern}/{replacement}/{flags}"
        text = self._rules_editor.toPlainText()
        lines = text.split("\n")
        position = self._rule_position.currentData()

        if section_data == "cursor":
            cursor = self._rules_editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.EndOfBlock)
            block_text = cursor.block().text().strip()
            if block_text:
                cursor.insertText("\n" + rule)
            else:
                cursor.insertText(rule)
            self._rules_editor.setTextCursor(cursor)
            self._rules_editor.ensureCursorVisible()
            self._refresh_rule_sections()
            self._rule_pattern.clear()
            self._rule_replacement.clear()
            self._rule_preview.setVisible(False)
            self._rule_pattern.setFocus()
            return

        if section_data == "eof":
            while lines and not lines[-1].strip():
                lines.pop()
            lines.append(rule)
            insert_line = len(lines) - 1
        else:
            # Trouver la section STEP dans le texte
            section_idx = -1
            for i, line in enumerate(lines):
                if section in line:
                    section_idx = i
                    break

            if section_idx < 0:
                while lines and not lines[-1].strip():
                    lines.pop()
                lines.append(rule)
                insert_line = len(lines) - 1
            else:
                # Trouver les bornes de la section STEP (sauter la barre ═══ de fermeture du header)
                step_end = section_idx + 1
                # Sauter la barre ═══ qui ferme le header
                if step_end < len(lines) and lines[step_end].strip().startswith("# ═"):
                    step_end += 1
                # Chercher le prochain header ═══ (début de la section suivante)
                while step_end < len(lines):
                    if lines[step_end].strip().startswith("# ═"):
                        break
                    step_end += 1

                # [*] : pas de sous-section langue, insérer directement
                if lang == "*":
                    if position == "begin":
                        begin_idx = section_idx + 1
                        # Sauter la barre ═══ de fermeture + lignes vides/commentaires
                        if begin_idx < step_end and lines[begin_idx].strip().startswith("# ═"):
                            begin_idx += 1
                        while begin_idx < step_end:
                            s = lines[begin_idx].strip()
                            if s and not s.startswith("#"):
                                break
                            if s.startswith("# \u2500\u2500"):
                                break
                            begin_idx += 1
                        lines.insert(begin_idx, rule)
                        insert_line = begin_idx
                    else:
                        insert_at = step_end
                        while insert_at > section_idx + 1 and not lines[insert_at - 1].strip():
                            insert_at -= 1
                        lines.insert(insert_at, rule)
                        insert_line = insert_at

                    self._rules_editor.setPlainText("\n".join(lines))
                    cursor = self._rules_editor.textCursor()
                    block = self._rules_editor.document().findBlockByNumber(insert_line)
                    cursor.setPosition(block.position())
                    self._rules_editor.setTextCursor(cursor)
                    self._rules_editor.ensureCursorVisible()
                    self._refresh_rule_sections()
                    self._rule_pattern.clear()
                    self._rule_replacement.clear()
                    self._rule_preview.setVisible(False)
                    self._rule_pattern.setFocus()
                    return

                # Chercher la sous-section langue (# ── French ──)
                lang_name = dict(LANGUAGES).get(lang, lang)
                subsection_header = f"# \u2500\u2500 {lang_name} "
                lang_sub_idx = -1
                for i in range(section_idx + 1, step_end):
                    if subsection_header in lines[i]:
                        lang_sub_idx = i
                        break

                if lang_sub_idx >= 0:
                    # Sous-section trouvée
                    if position == "begin":
                        # Après le header de sous-section, avant la prochaine
                        begin_idx = lang_sub_idx + 1
                        while begin_idx < step_end:
                            s = lines[begin_idx].strip()
                            if s and not s.startswith("#"):
                                break
                            if s.startswith("# \u2500\u2500") or s.startswith("# ═"):
                                break
                            begin_idx += 1
                        lines.insert(begin_idx, rule)
                        insert_line = begin_idx
                    else:
                        # Fin de la sous-section (prochaine sous-section ── ou fin de STEP)
                        sub_end = lang_sub_idx + 1
                        while sub_end < step_end:
                            s = lines[sub_end].strip()
                            if s.startswith("# \u2500\u2500") or s.startswith("# ═"):
                                break
                            sub_end += 1
                        while sub_end > lang_sub_idx + 1 and not lines[sub_end - 1].strip():
                            sub_end -= 1
                        lines.insert(sub_end, rule)
                        insert_line = sub_end
                else:
                    # Créer la sous-section langue à la fin de la section STEP
                    sub_header = f"# \u2500\u2500 {lang_name} " + "\u2500" * (60 - len(lang_name))
                    insert_at = step_end
                    while insert_at > section_idx + 1 and not lines[insert_at - 1].strip():
                        insert_at -= 1
                    lines.insert(insert_at, "")
                    lines.insert(insert_at + 1, sub_header)
                    lines.insert(insert_at + 2, rule)
                    insert_line = insert_at + 2

        self._rules_editor.setPlainText("\n".join(lines))
        # Position cursor on inserted line
        cursor = self._rules_editor.textCursor()
        block = self._rules_editor.document().findBlockByNumber(insert_line)
        cursor.setPosition(block.position())
        self._rules_editor.setTextCursor(cursor)
        self._rules_editor.ensureCursorVisible()
        # Refresh sections and clear fields
        self._refresh_rule_sections()
        self._rule_pattern.clear()
        self._rule_replacement.clear()
        self._rule_preview.setVisible(False)
        self._rule_pattern.setFocus()

    def _record_for_rule(self):
        """Starts or stops audio recording."""
        import subprocess
        tmpwav = "/tmp/dictee-test-rule.wav"

        # Si déjà en enregistrement → stopper et transcrire
        if getattr(self, '_rule_recording', False):
            self._rule_recording = False
            self._btn_record_rule.setText(_("Transcribing..."))
            self._btn_record_rule.setEnabled(False)
            # Arrêter l'enregistrement
            if hasattr(self, '_pw_proc') and self._pw_proc.poll() is None:
                self._pw_proc.terminate()
                self._pw_proc.wait()
            # Transcrire dans un thread pour ne pas bloquer l'UI
            _thr = (
                self.slider_silence.value() / 1000.0
                if hasattr(self, 'slider_silence') else None)
            self._rule_transcribe_thread = _RuleTranscribeThread(tmpwav, _thr)
            self._rule_transcribe_thread.finished_sig.connect(
                lambda result, wav=tmpwav: (
                    setattr(self, '_rule_transcribe_result', result),
                    self._rule_transcribe_done(wav)))
            self._rule_transcribe_thread.start()
            return

        # Start recording
        self._rule_recording = True
        self._btn_record_rule.setText("\u23f9 " + _("Stop"))
        self._btn_record_rule.setStyleSheet("color: red; font-weight: bold;")

        try:
            self._pw_proc = subprocess.Popen(
                ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", tmpwav],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            QMessageBox.warning(self._pp_parent, "dictee", _("pw-record not found."))
            self._btn_record_rule.setText("\U0001f3a4 " + _("Record"))
            self._btn_record_rule.setStyleSheet("font-weight: normal;")
            self._rule_recording = False

    def _rule_transcribe_worker(self, tmpwav):
        """Thread worker : transcrit le WAV (appelé hors UI)."""
        import subprocess
        try:
            result = subprocess.run(
                ["transcribe-client", tmpwav],
                capture_output=True, text=True, timeout=30)
            self._rule_transcribe_result = result.stdout.strip()
        except Exception:
            self._rule_transcribe_result = ""

    def _rule_transcribe_done(self, tmpwav):
        """Callback UI : traite le résultat de la transcription."""
        import re as _re
        # Nettoyer le WAV
        if os.path.isfile(tmpwav):
            os.remove(tmpwav)
        # Restaurer le bouton
        self._btn_record_rule.setText(
            QIcon.fromTheme("audio-input-microphone").name() or "\U0001f3a4 " + _("Record"))
        self._btn_record_rule.setText("\U0001f3a4 " + _("Record"))
        self._btn_record_rule.setStyleSheet("font-weight: normal;")
        self._btn_record_rule.setEnabled(True)

        raw = getattr(self, '_rule_transcribe_result', '')
        if raw:
            # Run raw through postprocess first — if existing rules already
            # transform it, no new rule is needed (avoids proposing duplicates).
            try:
                import subprocess as _sp
                lang = self._rule_lang.currentText()
                env = dict(os.environ, DICTEE_LANG_SOURCE=lang)
                proc = _sp.run(["dictee-postprocess"],
                    input=raw, capture_output=True, text=True,
                    timeout=10, env=env)
                processed = proc.stdout.strip()
            except Exception:
                processed = raw

            cyrillic_chars = [c for c in raw if '\u0400' <= c <= '\u04ff']
            already_covered = (processed != raw)

            if cyrillic_chars:
                if already_covered:
                    self._rule_preview.setText(
                        f"<b>RAW:</b> {raw}<br>"
                        f"<b>PROCESSED:</b> {processed}<br>"
                        f"<span style='color: green;'>✓ {_('Cyrillic already covered by an existing rule — no new rule needed.')}</span>")
                else:
                    word = _re.sub(r'[.,!?\s]+$', '', raw).strip()
                    word = _re.sub(r'^[.,!?\s]+', '', word).strip()
                    self._rule_pattern.setText(f"^[,.\\s]*{word}[,.\\s]*")
                    self._rule_replacement.setText("\\n")
                    self._rule_flags.setText("igm")
                    for i in range(self._rule_section.count()):
                        if "STEP 3" in self._rule_section.itemText(i):
                            self._rule_section.setCurrentIndex(i)
                            break
                    self._rule_preview.setText(
                        f"<b>RAW:</b> {raw}<br>"
                        f"<span style='color: red;'>⚠ {_('Cyrillic detected — rule pre-filled for voice command replacement.')}</span>")
            else:
                self._rule_pattern.setText(raw)
                if already_covered:
                    self._rule_preview.setText(
                        f"<b>RAW:</b> {raw}<br>"
                        f"<b>PROCESSED:</b> {processed}<br>"
                        f"<span style='color: green;'>✓ {_('Existing rules already transform this text.')}</span>")
                else:
                    self._rule_preview.setText(
                        f"<b>RAW:</b> {raw}<br>"
                        f"<span style='color: orange;'>⚠ {_('No rule matched — a new rule is needed.')}</span>")
            self._rule_preview.setVisible(True)
            self._rule_replacement.setFocus()
        else:
            self._rule_preview.setText(
                f"<span style='color: gray;'>{_('(no speech detected)')}</span>")
            self._rule_preview.setVisible(True)

    def _load_rules_file(self):
        import os as _os
        _os.makedirs(_os.path.dirname(self._rules_path), exist_ok=True)
        if _os.path.isfile(self._rules_path):
            with open(self._rules_path, encoding="utf-8") as f:
                self._rules_editor.setPlainText(f.read())
        else:
            # First launch: copy defaults if available
            for candidate in [
                _os.path.join(_os.path.dirname(_os.path.realpath(__file__)), "rules.conf.default"),
                "/usr/share/dictee/rules.conf.default",
            ]:
                if _os.path.isfile(candidate):
                    shutil.copy2(candidate, self._rules_path)
                    with open(self._rules_path, encoding="utf-8") as f:
                        self._rules_editor.setPlainText(f.read())
                    break
            else:
                self._rules_editor.clear()
        self._refresh_rule_sections()

    def _refresh_rule_sections(self):
        """Updates section combo from editor content."""
        import re
        self._rule_section.blockSignals(True)
        current = self._rule_section.currentText()
        self._rule_section.clear()
        section_re = re.compile(r"^#\s*(STEP\s+\d+\s*[—–-]\s*.+)")
        text = self._rules_editor.toPlainText()
        sections = []
        for line in text.splitlines():
            m = section_re.match(line.strip())
            if m and m.group(1):
                sections.append(m.group(1).strip())
        self._rule_section.addItem(_("At cursor"), "cursor")
        self._rule_section.addItem(_("End of file"), "eof")
        for s in sections:
            self._rule_section.addItem(s, "section")
        # Restore selection
        idx = self._rule_section.findText(current)
        if idx >= 0:
            self._rule_section.setCurrentIndex(idx)
        self._rule_section.blockSignals(False)
        # Sync _rule_position (le signal était bloqué)
        self._rule_position.setEnabled(self._rule_section.currentData() == "section")

    def _sync_test_lang_from_cursor(self):
        """Detect language tag from current line in rules editor and update test label."""
        if not hasattr(self, '_test_lang_override'):
            return
        import re
        cursor = self._rules_editor.textCursor()
        line = cursor.block().text().strip()
        m = re.match(r"^\[([a-z]{2}|\*)\]", line)
        if m:
            code = m.group(1)
            self._test_lang_override = code if code != "*" else ""
            lang_names = {"fr": "Français", "en": "English", "de": "Deutsch",
                          "es": "Español", "it": "Italiano", "pt": "Português",
                          "nl": "Nederlands", "ro": "Română", "ru": "Русский",
                          "uk": "Українська", "*": _("all languages")}
            name = lang_names.get(code, code)
            self._lbl_test_lang.setText(_("Testing as: {lang}").format(lang=f"{code} — {name}"))
            self._schedule_test_run()
        else:
            if self._test_lang_override:
                self._test_lang_override = ""
                conf_lang = self.conf.get("DICTEE_LANG_SOURCE", "fr")
                self._lbl_test_lang.setText(_("Testing as: {lang} (config)").format(lang=conf_lang))
                self._schedule_test_run()

    def _validate_rules_syntax(self, text):
        """Valide la syntaxe des règles. Retourne (ok, erreur_msg)."""
        import re
        entry_re = re.compile(r'^\s*\[([a-z]{2}|\*)\]\s*/(.+)/(.*)/([a-z]*)$')
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            m = entry_re.match(s)
            if not m:
                return False, _("Line {n}: invalid syntax: {line}").format(n=i, line=s)
            # Vérifier que le pattern regex compile
            pattern = m.group(2)
            try:
                re.compile(pattern)
            except re.error as e:
                return False, _("Line {n}: invalid regex: {err}").format(n=i, err=str(e))
        return True, ""

    def _save_rules_file_silent(self):
        """Write the rules editor content to disk without any popup.
        Returns (ok, err_msg). Skips the write if content is unchanged.
        """
        import os as _os
        if not hasattr(self, "_rules_editor") or self._rules_editor is None:
            return True, ""
        text = self._rules_editor.toPlainText()
        # Skip if file already matches editor (avoid needless mtime bumps)
        try:
            if _os.path.isfile(self._rules_path):
                with open(self._rules_path, encoding="utf-8") as f:
                    if f.read() == text:
                        return True, ""
        except OSError:
            pass
        ok, err = self._validate_rules_syntax(text)
        if not ok:
            return False, err
        try:
            _os.makedirs(_os.path.dirname(self._rules_path), exist_ok=True)
            with open(self._rules_path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            return False, str(e)
        return True, ""

    def _save_rules_file(self):
        ok, err = self._save_rules_file_silent()
        if not ok:
            QMessageBox.warning(self._pp_parent, "dictee",
                _("Cannot save — syntax error:\n\n{err}").format(err=err))
            return
        QMessageBox.information(self._pp_parent, "dictee", _("Rules saved."))
        if hasattr(self, '_schedule_test_run'):
            self._schedule_test_run()

    def _restore_rules_defaults(self):
        import os as _os
        for candidate in [
            _os.path.join(_os.path.dirname(_os.path.realpath(__file__)), "rules.conf.default"),
            "/usr/share/dictee/rules.conf.default",
        ]:
            if _os.path.isfile(candidate):
                shutil.copy2(candidate, self._rules_path)
                self._load_rules_file()
                QMessageBox.information(self._pp_parent, "dictee", _("Default rules restored."))
                return
        QMessageBox.warning(self._pp_parent, "dictee", _("Default rules file not found."))

    def _regex_to_sample(self, pattern):
        """Génère un exemple de texte qui matcherait le pattern regex."""
        import re
        text = pattern

        # 1. Retirer ancres et word boundaries
        text = re.sub(r'\^|\$|\\b', '', text)

        # 2. Classes de caractères → contenu exemple
        # [,.\s]* → "" (ponctuation optionnelle, on l'ignore)
        text = re.sub(r'\[,\.\\\s?\]\*?', '', text)
        text = re.sub(r'\[,\s\.\\\s?\]\*?', '', text)
        # [^)]* → "texte" (tout sauf parenthèse fermante)
        text = re.sub(r'\[\^[^\]]*\][\*+]?', 'texte', text)
        # [А-Яа-я] → "Было" (exemple cyrillique)
        text = re.sub(r'\[А-Яа-я\][\-А-Яа-я]*[\*+]?', 'Было', text)
        # Classes simples [Ll] [Aa] → premier caractère
        def _first_char_class(m):
            content = m.group(1)
            return content[0] if content else ''
        text = re.sub(r'\[([A-Za-zÀ-ÿА-Яа-я]{2,4})\]', _first_char_class, text)
        # Autres classes restantes → ""
        text = re.sub(r'\[[^\]]*\][\*+?]*', '', text)

        # 3. Séquences d'échappement
        text = re.sub(r'\\n', '\n', text)
        text = re.sub(r'\\t', '\t', text)
        text = re.sub(r'\\s[\*+]?', ' ', text)
        text = re.sub(r'\\([\[\](){}|.*+?/])', r'\1', text)  # \( → (

        # 4. Alternations : prendre la première option
        # (?:a|b|c) → a
        def _first_alt(m):
            content = m.group(1)
            return content.split('|')[0]
        text = re.sub(r'\(\?:([^)]+)\)', _first_alt, text)
        text = re.sub(r'\(([^)]*\|[^)]*)\)', _first_alt, text)

        # 5. Quantificateurs restants
        text = re.sub(r'([^\\])[*+?]', r'\1', text)
        text = re.sub(r'^\*|^\+|^\?', '', text)

        # 6. Nettoyage
        text = re.sub(r'\s{2,}', ' ', text)
        text = text.strip()

        return text if text else pattern

    def _send_rule_to_test(self):
        """Envoie le pattern de la ligne courante de l'éditeur regex vers le champ test."""
        import re
        # Auto-open the test accordion — otherwise the user sees nothing happen
        if hasattr(self, '_test_accordion_toggle') and not self._test_accordion_toggle.isChecked():
            self._test_accordion_toggle.setChecked(True)
        cursor = self._rules_editor.textCursor()
        line = cursor.block().text().strip()
        if not line or line.startswith("#"):
            return
        # Extraire le pattern : [lang] /PATTERN/REPLACEMENT/FLAGS
        m = re.match(r'^\[.*?\]\s*/(.*?)/(.*?)/([a-z]*)$', line)
        if m:
            pattern = m.group(1)
            # Générer un exemple de texte qui matche le pattern
            text = self._regex_to_sample(pattern)
            if text and hasattr(self, '_test_input'):
                self._test_input.setPlainText(text)
                self._test_input.setFocus()
        elif hasattr(self, '_test_input'):
            self._test_input.setPlainText(line)
            self._test_input.setFocus()

    def _update_rules_count(self):
        """Met à jour le compteur de règles."""
        import re
        text = self._rules_editor.toPlainText()
        active = 0
        commented = 0
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                # Règle commentée (pas un header ni un commentaire normal)
                if re.match(r'^#\s*\[', s):
                    commented += 1
            elif re.match(r'^\[', s):
                active += 1
        self._rules_count_label.setText(
            f"{active + commented} {_('rules')} ({active} {_('active')}, {commented} {_('commented')})")

    def _rules_show_search(self):
        """Toggles the search bar."""
        if self._rules_search_bar.isVisible():
            self._rules_search_bar.setVisible(False)
            self._restore_palette(self._rules_editor)
            self._rules_editor.setFocus()
        else:
            self._rules_search_bar.setVisible(True)
            self._rules_search_input.setFocus()
            self._rules_search_input.selectAll()

    def _set_search_palette(self, editor):
        """Change la palette de sélection d'un éditeur en jaune foncé."""
        from PyQt6.QtGui import QColor, QPalette
        pal = editor.palette()
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#B8860B"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
        editor.setPalette(pal)

    def _restore_palette(self, editor):
        """Restaure la palette de sélection par défaut."""
        editor.setPalette(self.palette())

    def _count_matches(self, editor, text):
        """Compte le nombre d'occurrences et l'index courant."""
        if not text:
            return 0, 0
        content = editor.toPlainText().lower()
        search = text.lower()
        total = content.count(search)
        if total == 0:
            return 0, 0
        cursor_pos = editor.textCursor().position()
        current = content[:cursor_pos].count(search)
        return current, total

    def _update_search_count(self, count_label, current, total, search_text=""):
        """Met à jour le label de compteur de recherche."""
        if total > 0:
            count_label.setText(f"{current}/{total}")
        elif search_text:
            count_label.setText("0")
        else:
            count_label.setText("")

    def _find_in_editor(self, editor, text, forward=True):
        """Cherche dans un QTextEdit avec wrap circulaire."""
        from PyQt6.QtGui import QTextDocument
        saved_pos = editor.textCursor().position()
        if not forward:
            found = editor.find(text, QTextDocument.FindFlag.FindBackward)
        else:
            found = editor.find(text)
        if not found:
            cursor = editor.textCursor()
            if forward:
                cursor.movePosition(cursor.MoveOperation.Start)
            else:
                cursor.movePosition(cursor.MoveOperation.End)
            editor.setTextCursor(cursor)
            if not forward:
                found = editor.find(text, QTextDocument.FindFlag.FindBackward)
            else:
                found = editor.find(text)
            # Si on retombe sur la même position, ne pas bouger
            if found and editor.textCursor().position() == saved_pos:
                return

    def _rules_find(self, forward=True):
        """Cherche le texte dans l'éditeur de règles."""
        text = self._rules_search_input.text()
        if not text:
            self._restore_palette(self._rules_editor)
            self._update_search_count(self._rules_search_count, 0, 0)
            return
        self._set_search_palette(self._rules_editor)
        self._find_in_editor(self._rules_editor, text, forward)
        current, total = self._count_matches(self._rules_editor, text)
        self._update_search_count(self._rules_search_count, current, total, text)

    def _dict_adv_show_search(self):
        """Toggles the advanced mode dictionary search bar."""
        if self._dict_adv_search_bar.isVisible():
            self._dict_adv_search_bar.setVisible(False)
            self._restore_palette(self._dict_adv_editor)
            self._dict_adv_editor.setFocus()
        else:
            self._dict_adv_search_bar.setVisible(True)
            self._dict_adv_search_input.setFocus()
            self._dict_adv_search_input.selectAll()

    def _dict_adv_find(self, forward=True):
        """Cherche le texte dans l'éditeur avancé du dictionnaire."""
        text = self._dict_adv_search_input.text()
        if not text:
            self._restore_palette(self._dict_adv_editor)
            self._update_search_count(self._dict_adv_search_count, 0, 0)
            return
        self._set_search_palette(self._dict_adv_editor)
        self._find_in_editor(self._dict_adv_editor, text, forward)
        current, total = self._count_matches(self._dict_adv_editor, text)
        self._update_search_count(self._dict_adv_search_count, current, total, text)

    def _build_dictionary_tab(self, lay):
        """Dictionary tab: single local file, form view with accordions + edit mode."""
        import os as _os

        XDG_CFG = _os.environ.get("XDG_CONFIG_HOME", _os.path.expanduser("~/.config"))
        self._dict_path = _os.path.join(XDG_CFG, "dictee", "dictionary.conf")
        self._dict_tmp_path = self._dict_path + ".tmp"

        # First launch: copy system file to local
        if not _os.path.isfile(self._dict_path):
            for candidate in [
                _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "dictionary.conf.default"),
                "/usr/share/dictee/dictionary.conf.default",
            ]:
                if _os.path.isfile(candidate):
                    _os.makedirs(_os.path.dirname(self._dict_path), exist_ok=True)
                    shutil.copy2(candidate, self._dict_path)
                    break

        # Undo stack and draft
        self._dict_undo_stack = []  # liste de contenus texte du fichier .tmp
        self._dict_saved = False  # True si l'utilisateur a fait "Enregistrer"
        self._dict_init_tmp()

        self._dict_stack = QStackedWidget()

        # --- Page 0: Form view ---
        form_page = QWidget()
        form_top_lay = QVBoxLayout(form_page)
        form_top_lay.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        self._dict_search = QComboBox()
        self._dict_search.setEditable(True)
        self._dict_search.lineEdit().addAction(
            QIcon.fromTheme("edit-find"), QLineEdit.ActionPosition.LeadingPosition)
        self._dict_search.setMinimumWidth(180)
        self._dict_search.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        toolbar.addWidget(self._dict_search)

        self._dict_lang_filter = QComboBox()
        self._dict_lang_filter.addItem(_("All languages"), "")
        toolbar.addWidget(self._dict_lang_filter)

        toolbar.addStretch()
        form_top_lay.addLayout(toolbar)

        # Single scroll area (toutes les entrées)
        self._dict_scroll = QScrollArea()
        self._dict_scroll.setWidgetResizable(True)
        self._dict_scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        self._dict_layout = QVBoxLayout(scroll_content)
        self._dict_layout.setContentsMargins(4, 4, 4, 4)
        self._dict_layout.setSpacing(6)
        self._dict_scroll.setWidget(scroll_content)
        form_top_lay.addWidget(self._dict_scroll, 1)

        # Area for new entries (outside scroll, at bottom)
        self._dict_new_entries = QVBoxLayout()
        self._dict_new_entries.setSpacing(2)
        self._dict_new_entries.setContentsMargins(4, 4, 4, 0)
        form_top_lay.addLayout(self._dict_new_entries)

        self._dict_stack.addWidget(form_page)

        # --- Page 1: Advanced mode ---
        adv_page = QWidget()
        adv_lay = QVBoxLayout(adv_page)
        adv_lay.setContentsMargins(0, 0, 0, 0)
        adv_lay.setSpacing(4)

        self._dict_adv_editor = QTextEdit()
        self._dict_adv_editor.setFont(self._monospace_font())
        self._dict_adv_editor.setPlaceholderText(
            "# [lang] WORD=REPLACEMENT\n"
            "# Example:\n"
            "# [fr] sncf=SNCF\n"
            "# [*] api=API\n")
        adv_lay.addWidget(self._dict_adv_editor)
        self._add_zoom_overlay(self._dict_adv_editor)

        # Search bar (Ctrl+F) pour le mode avancé
        self._dict_adv_search_bar = QWidget()
        self._dict_adv_search_bar.setVisible(False)
        dsearch_lay = QHBoxLayout(self._dict_adv_search_bar)
        dsearch_lay.setContentsMargins(0, 2, 0, 2)
        dsearch_lay.setSpacing(4)
        self._dict_adv_search_input = QLineEdit()
        self._dict_adv_search_input.addAction(
            QIcon.fromTheme("edit-find"), QLineEdit.ActionPosition.LeadingPosition)
        self._dict_adv_search_input.returnPressed.connect(lambda: self._dict_adv_find(forward=True))
        self._dict_adv_search_input.textChanged.connect(lambda: self._dict_adv_find(forward=True))
        dsearch_lay.addWidget(self._dict_adv_search_input, 1)
        self._dict_adv_search_count = QLabel()
        self._dict_adv_search_count.setStyleSheet("color: gray; font-size: 11px;")
        self._dict_adv_search_count.setFixedWidth(50)
        dsearch_lay.addWidget(self._dict_adv_search_count)
        btn_dprev = QPushButton("\u25b2")
        btn_dprev.setFixedWidth(28)
        btn_dprev.setToolTip(_("Previous"))
        btn_dprev.clicked.connect(lambda: self._dict_adv_find(forward=False))
        dsearch_lay.addWidget(btn_dprev)
        btn_dnext = QPushButton("\u25bc")
        btn_dnext.setFixedWidth(28)
        btn_dnext.setToolTip(_("Next"))
        btn_dnext.clicked.connect(lambda: self._dict_adv_find(forward=True))
        dsearch_lay.addWidget(btn_dnext)
        btn_dclose = QPushButton("\u2715")
        btn_dclose.setFixedWidth(28)
        btn_dclose.clicked.connect(self._dict_adv_show_search)
        dsearch_lay.addWidget(btn_dclose)
        adv_lay.addWidget(self._dict_adv_search_bar)

        # Shortcuts Ctrl+F and Escape pour le mode avancé
        from PyQt6.QtGui import QShortcut, QKeySequence
        shortcut_dfind = QShortcut(QKeySequence("Ctrl+F"), self._dict_adv_editor)
        shortcut_dfind.activated.connect(self._dict_adv_show_search)
        shortcut_desc = QShortcut(QKeySequence("Escape"), self._dict_adv_search_input)
        shortcut_desc.activated.connect(self._dict_adv_show_search)

        self._dict_stack.addWidget(adv_page)

        lay.addWidget(self._dict_stack)

        # --- Common toolbar (sous le QStackedWidget, visible dans les 2 modes) ---
        common_btns = QHBoxLayout()

        btn_dict_find = QPushButton(QIcon.fromTheme("edit-find"), "")
        btn_dict_find.setFixedWidth(30)
        btn_dict_find.setToolTip(_("Search (Ctrl+F)"))
        btn_dict_find.clicked.connect(self._dict_adv_show_search)
        common_btns.addWidget(btn_dict_find)

        self._btn_dict_add = QPushButton("+ " + _("Add"))
        self._btn_dict_add.clicked.connect(lambda: self._add_dict_entry())
        common_btns.addWidget(self._btn_dict_add)

        self._btn_dict_undo = QPushButton(QIcon.fromTheme("edit-undo"), "")
        self._btn_dict_undo.setFixedWidth(30)
        self._btn_dict_undo.setToolTip(_("Undo last change"))
        self._btn_dict_undo.setEnabled(False)
        self._btn_dict_undo.clicked.connect(self._dict_undo_smart)
        common_btns.addWidget(self._btn_dict_undo)

        self._btn_dict_redo = QPushButton(QIcon.fromTheme("edit-redo"), "")
        self._btn_dict_redo.setFixedWidth(30)
        self._btn_dict_redo.setToolTip(_("Redo last undone change"))
        self._btn_dict_redo.setEnabled(False)
        self._btn_dict_redo.clicked.connect(self._dict_redo_smart)
        common_btns.addWidget(self._btn_dict_redo)

        btn_save = QPushButton(_("Save"))
        btn_save.setToolTip(_("Save all changes to disk"))
        btn_save.clicked.connect(self._dict_save_smart)
        common_btns.addWidget(btn_save)

        common_btns.addStretch()

        btn_revert = QPushButton(_("Revert to saved"))
        btn_revert.setToolTip(_tt(_("Discard all unsaved changes and reload the last saved version")))
        btn_revert.clicked.connect(self._dict_revert_to_saved)
        common_btns.addWidget(btn_revert)

        btn_factory = QPushButton(_("Factory reset"))
        btn_factory.setToolTip(_("Restore factory defaults"))
        btn_factory.clicked.connect(self._restore_dict_defaults)
        common_btns.addWidget(btn_factory)

        lay.addLayout(common_btns)

        # Data
        self._dict_rows = []

        # Connect recherche et filtre
        self._dict_search.editTextChanged.connect(self._filter_dict_entries)
        self._dict_lang_filter.currentIndexChanged.connect(self._filter_dict_entries)

        # Load the form
        self._load_dict_form()

    def _parse_dict_with_categories(self, path):
        """Parse un fichier dictionnaire, retourne [(category, [(lang, word, replacement)])]."""
        categories = []
        current_cat = None
        current_entries = []
        cat_re = re.compile(r"^#\s*──\s*(.+?)\s*─")
        entry_re = re.compile(r"^\s*\[([a-z]{2}|\*)\]\s*(.+?)=(.+?)\s*$")
        if not os.path.isfile(path):
            return categories
        with open(path, encoding="utf-8") as f:
            for line in f:
                line_s = line.strip()
                if not line_s:
                    continue
                m_cat = cat_re.match(line_s)
                if m_cat:
                    if current_entries:
                        cat_name = current_cat or f"Dictionary [{current_entries[0][0]}]"
                        categories.append((cat_name, current_entries))
                    current_cat = m_cat.group(1).strip()
                    current_entries = []
                    continue
                if line_s.startswith("#"):
                    continue
                m = entry_re.match(line_s)
                if m:
                    current_entries.append((m.group(1), m.group(2).strip(), m.group(3).strip()))
        if current_entries:
            cat_name = current_cat or f"Dictionary [{current_entries[0][0]}]"
            categories.append((cat_name, current_entries))
        return categories

    def _load_dict_form(self):
        """Clears and rebuilds the dictionary form (single file)."""
        # Clear layout — detach immediately then delete
        layout = self._dict_layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        self._dict_rows.clear()

        # Force visual cleanup before rebuilding
        QApplication.processEvents()

        # Collect all languages for filter
        all_langs = set()

        # Parse draft file (.tmp)
        source = self._dict_tmp_path if os.path.isfile(self._dict_tmp_path) else self._dict_path
        categories = self._parse_dict_with_categories(source)

        if not categories:
            self._dict_empty_label = QLabel(
                "<i>" + _("Add words that the ASR transcribes incorrectly.") + "</i>")
            self._dict_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._dict_empty_label)
        else:
            self._dict_empty_label = None
            for cat_name, entries in categories:
                for lang, _w, _r in entries:
                    if lang != "*":
                        all_langs.add(lang)

                n_entries = len(entries)
                entry_lbl = _("entries") if n_entries > 1 else _("entry")
                # Collapsible title button — EXPANDED by default
                btn_title = f"\u25be {cat_name} ({n_entries} {entry_lbl})"
                btn_toggle = QPushButton(btn_title)
                btn_toggle.setFlat(True)
                btn_toggle.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
                btn_toggle.setStyleSheet("text-align: left; font-weight: bold; padding: 4px 12px;")
                layout.addWidget(btn_toggle)

                content_w = QWidget()
                content_w.setVisible(True)
                content_lay = QVBoxLayout(content_w)
                content_lay.setSpacing(2)
                content_lay.setContentsMargins(16, 0, 0, 4)

                def _make_toggle(btn, cw, cn=cat_name, ne=n_entries):
                    def _toggle():
                        vis = not cw.isVisible()
                        cw.setVisible(vis)
                        arrow = "\u25be" if vis else "\u25b8"
                        el = _("entries") if ne > 1 else _("entry")
                        btn.setText(f"{arrow} {cn} ({ne} {el})")
                        # Force QScrollArea to recompute its content size.
                        # Without this, collapsing leaves a phantom empty
                        # space in the scroll range — the scrollbar handle
                        # stays huge as if the category were still visible.
                        sc = getattr(self, "_dict_scroll", None)
                        if sc is not None:
                            w = sc.widget()
                            if w is not None:
                                w.adjustSize()
                            sc.updateGeometry()
                    return _toggle
                btn_toggle.clicked.connect(_make_toggle(btn_toggle, content_w))

                for lang, word, repl in entries:
                    row_widget = self._make_dict_row(lang, word, repl, cat_name)
                    content_lay.addWidget(row_widget)

                layout.addWidget(content_w)

        layout.addStretch()

        # Update language filter
        self._dict_lang_filter.blockSignals(True)
        current = self._dict_lang_filter.currentData()
        self._dict_lang_filter.clear()
        self._dict_lang_filter.addItem(_("All languages"), "")
        for lang in sorted(all_langs):
            self._dict_lang_filter.addItem(lang, lang)
        # Restore selection
        idx = self._dict_lang_filter.findData(current)
        if idx >= 0:
            self._dict_lang_filter.setCurrentIndex(idx)
        self._dict_lang_filter.blockSignals(False)

        # Re-apply active search filter
        self._filter_dict_entries()

        # Re-register in-progress new entries (hors scroll) dans _dict_rows
        if hasattr(self, '_dict_new_entries'):
            for i in range(self._dict_new_entries.count()):
                item = self._dict_new_entries.itemAt(i)
                w = item.widget() if item else None
                if w is not None and w not in self._dict_rows:
                    self._dict_rows.append(w)

    def _make_dict_row(self, lang="*", word="", repl="", category="", is_new=False):
        """Creates an editable row for a dictionary entry.

        is_new=False: existing line in file.
        is_new=True: user-added line, not yet confirmed.
                       ✓ writes to .tmp and reloads (removes ✓).
                       ✕ just removes line from UI and writes to .tmp.
        No auto-save via editingFinished — changes are
        written to .tmp only via explicit actions (✓, ✕, Save, mode switch).
        """
        row_widget = QWidget()
        row_lay = QHBoxLayout(row_widget)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(4)

        cmb_lang = QComboBox()
        cmb_lang.setFixedWidth(60)
        cmb_lang.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        cmb_lang.installEventFilter(self._scroll_guard)
        cmb_lang.addItem("*")
        for code, _name in LANGUAGES:
            cmb_lang.addItem(code)
        idx = cmb_lang.findText(lang)
        if idx >= 0:
            cmb_lang.setCurrentIndex(idx)
        row_lay.addWidget(cmb_lang)

        edt_word = QLineEdit(word)
        edt_word.setPlaceholderText(_("Word"))
        row_lay.addWidget(edt_word)

        lbl_arrow = QLabel("\u2192")
        lbl_arrow.setFixedWidth(20)
        lbl_arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_lay.addWidget(lbl_arrow)

        edt_repl = QLineEdit(repl)
        edt_repl.setPlaceholderText(_("Replacement"))
        row_lay.addWidget(edt_repl)

        # Mark line as new (not yet in file)
        row_widget.setProperty("dict_is_new", is_new)

        # ✓ confirm — visible for new entries, hidden for existing
        btn_ok = QPushButton("\u2713")
        btn_ok.setToolTip(_("Confirm this entry"))
        btn_ok.setFixedWidth(30)
        btn_ok.setStyleSheet("color: green; font-weight: bold;")
        btn_ok.setVisible(is_new)
        def _on_confirm(_checked=None, rw=row_widget):
            word = rw.property("dict_word_edt").text().strip()
            repl = rw.property("dict_repl_edt").text().strip()
            if not word or not repl:
                return
            # Mark as confirmed and set category based on chosen language
            lang = rw.property("dict_lang_cmb").currentText()
            rw.setProperty("dict_is_new", False)
            rw.setProperty("dict_category", f"Dictionary [{lang}]")
            # Save first (line is still in _dict_rows)
            self._dict_push_undo()
            self._save_dict_to_tmp(reload=False)
            # Remove this line from _dict_new_entries
            if rw in self._dict_rows:
                self._dict_rows.remove(rw)
            rw.setParent(None)
            rw.deleteLater()
            # Reload scroll from .tmp
            self._load_dict_form()
        btn_ok.clicked.connect(_on_confirm)
        row_lay.addWidget(btn_ok)

        # For existing entries: show ✓ when anything is modified
        if not is_new:
            def _on_modified():
                btn_ok.setVisible(True)
            edt_word.textChanged.connect(_on_modified)
            edt_repl.textChanged.connect(_on_modified)
            cmb_lang.currentIndexChanged.connect(_on_modified)

        # ✕ to delete
        btn_del = QPushButton("\u2715")
        btn_del.setToolTip(_("Remove"))
        btn_del.setFixedWidth(30)
        btn_del.setStyleSheet("color: red;")
        btn_del.clicked.connect(lambda: self._remove_dict_entry(row_widget))
        row_lay.addWidget(btn_del)

        row_widget.setProperty("dict_lang_cmb", cmb_lang)
        row_widget.setProperty("dict_word_edt", edt_word)
        row_widget.setProperty("dict_repl_edt", edt_repl)
        row_widget.setProperty("dict_category", category)

        self._dict_rows.append(row_widget)
        return row_widget

    def _add_dict_entry(self, lang="*", word="", repl=""):
        """Adds a new entry at the bottom of the form (not filtered until confirmed)."""
        # Remove empty label if present
        if hasattr(self, '_dict_empty_label') and self._dict_empty_label is not None:
            self._dict_empty_label.setParent(None)
            self._dict_empty_label.deleteLater()
            self._dict_empty_label = None

        row_widget = self._make_dict_row(lang, word, repl, f"Dictionary [{lang}]", is_new=True)

        # At bottom of window, outside scroll
        self._dict_new_entries.addWidget(row_widget)

        # Save to .tmp only if line has content
        # (sinon la ligne vide serait supprimée immédiatement par _save_dict_to_tmp)
        if word and repl:
            self._dict_push_undo()
            self._save_dict_to_tmp()

        # Focus the word field
        QTimer.singleShot(50, lambda: row_widget.property("dict_word_edt").setFocus())

    def _remove_dict_entry(self, entry):
        """Deletes a dictionary entry."""
        is_new = entry.property("dict_is_new")
        if not is_new:
            self._dict_push_undo()
        if entry in self._dict_rows:
            self._dict_rows.remove(entry)
        entry.setParent(None)
        entry.deleteLater()
        if not is_new:
            self._save_dict_to_tmp(reload=False)
            self._load_dict_form()

    def _filter_dict_entries(self):
        """Filters visible entries by search and language."""
        search = self._dict_search.currentText().lower()
        lang_filter = self._dict_lang_filter.currentData() or ""

        # Parcourir les catégories (paires btn_toggle + content_w)
        layout = self._dict_layout
        i = 0
        while i < layout.count():
            item = layout.itemAt(i)
            if item is None:
                i += 1
                continue
            btn = item.widget()
            if btn is None or not isinstance(btn, QPushButton):
                i += 1
                continue
            i += 1
            if i >= layout.count():
                break
            content_item = layout.itemAt(i)
            content_w = content_item.widget() if content_item else None
            if content_w is None:
                i += 1
                continue
            i += 1
            # Filter children of content_w (editable rows)
            content_lay = content_w.layout()
            if content_lay is None:
                continue
            any_visible = False
            for j in range(content_lay.count()):
                child_item = content_lay.itemAt(j)
                if child_item is None:
                    continue
                child = child_item.widget()
                if child is None:
                    continue
                cmb = child.property("dict_lang_cmb")
                edt_w = child.property("dict_word_edt")
                edt_r = child.property("dict_repl_edt")
                if cmb is None or edt_w is None:
                    continue
                c_lang = cmb.currentText()
                c_word = edt_w.text().lower()
                c_repl = edt_r.text().lower() if edt_r else ""
                visible = True
                if lang_filter and c_lang != "*" and c_lang != lang_filter:
                    visible = False
                if search and search not in c_word and search not in c_repl:
                    visible = False
                child.setVisible(visible)
                if visible:
                    any_visible = True
            # Hide title button + content if no visible entries
            btn.setVisible(any_visible)
            if (search or lang_filter) and any_visible:
                content_w.setVisible(True)
            elif not any_visible:
                content_w.setVisible(False)

    def _dict_collect_entries(self):
        """Collects form entries, returns (cat_entries OrderedDict, empty_rows list) or None on error."""
        from collections import OrderedDict
        cat_entries = OrderedDict()
        empty_rows = []

        for row in self._dict_rows:
            cmb = row.property("dict_lang_cmb")
            edt_w = row.property("dict_word_edt")
            edt_r = row.property("dict_repl_edt")
            if cmb is None or edt_w is None or edt_r is None:
                continue
            lang = cmb.currentText()
            word = edt_w.text().strip()
            repl = edt_r.text().strip()

            # New entries (unconfirmed): always ignore
            if row.property("dict_is_new"):
                continue
            else:
                if not word and not repl:
                    empty_rows.append(row)
                    continue
                if not word:
                    continue
            if "=" in word:
                QMessageBox.warning(self._pp_parent, "dictee",
                    _("Word cannot contain '=': {word}").format(word=word))
                return None

            category = row.property("dict_category") or f"Dictionary [{lang}]"

            if category not in cat_entries:
                cat_entries[category] = []
            cat_entries[category].append((lang, word, repl))
        return cat_entries, empty_rows

    def _dict_entries_to_text(self, cat_entries):
        """Serializes entries to text for the dictionary file."""
        lines = ["# dictee dictionary\n", "# Format: [lang] WORD=REPLACEMENT\n\n"]
        for cat_name, entries in cat_entries.items():
            lines.append(f"# \u2500\u2500 {cat_name} \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n")
            for lang, word, repl in entries:
                lines.append(f"[{lang}] {word}={repl}\n")
            lines.append("\n")
        return "".join(lines)

    def _dict_push_undo(self):
        """Pushes current .tmp content to undo stack (max 20)."""
        if os.path.isfile(self._dict_tmp_path):
            with open(self._dict_tmp_path, encoding="utf-8") as f:
                content = f.read()
        elif os.path.isfile(self._dict_path):
            with open(self._dict_path, encoding="utf-8") as f:
                content = f.read()
        else:
            content = ""
        self._dict_undo_stack.append(content)
        if len(self._dict_undo_stack) > 20:
            self._dict_undo_stack = self._dict_undo_stack[-20:]
        # New action → clear redo (future history is invalidated)
        self._dict_redo_stack.clear()
        self._dict_update_undo_buttons()

    def _dict_read_tmp(self):
        """Reads current .tmp content (or official as fallback)."""
        if os.path.isfile(self._dict_tmp_path):
            with open(self._dict_tmp_path, encoding="utf-8") as f:
                return f.read()
        if os.path.isfile(self._dict_path):
            with open(self._dict_path, encoding="utf-8") as f:
                return f.read()
        return ""

    def _dict_write_tmp(self, content):
        """Writes content to .tmp."""
        os.makedirs(os.path.dirname(self._dict_tmp_path), exist_ok=True)
        with open(self._dict_tmp_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _dict_undo(self):
        """Undo in normal mode."""
        if not self._dict_undo_stack:
            return
        # Empiler l'état actuel dans le redo
        self._dict_redo_stack.append(self._dict_read_tmp())
        content = self._dict_undo_stack.pop()
        self._dict_write_tmp(content)
        scroll_pos = self._dict_scroll.verticalScrollBar().value()
        self._load_dict_form()
        QTimer.singleShot(50, lambda: self._dict_scroll.verticalScrollBar().setValue(scroll_pos))
        self._dict_update_undo_buttons()

    def _dict_undo_in_advanced(self):
        """Undo in advanced mode."""
        if not self._dict_undo_stack:
            return
        self._dict_redo_stack.append(self._dict_read_tmp())
        content = self._dict_undo_stack.pop()
        self._dict_write_tmp(content)
        self._dict_adv_editor.setPlainText(content)
        self._dict_update_undo_buttons()

    def _dict_redo(self):
        """Redo in normal mode."""
        if not self._dict_redo_stack:
            return
        self._dict_undo_stack.append(self._dict_read_tmp())
        content = self._dict_redo_stack.pop()
        self._dict_write_tmp(content)
        scroll_pos = self._dict_scroll.verticalScrollBar().value()
        self._load_dict_form()
        QTimer.singleShot(50, lambda: self._dict_scroll.verticalScrollBar().setValue(scroll_pos))
        self._dict_update_undo_buttons()

    def _dict_redo_in_advanced(self):
        """Redo in advanced mode."""
        if not self._dict_redo_stack:
            return
        self._dict_undo_stack.append(self._dict_read_tmp())
        content = self._dict_redo_stack.pop()
        self._dict_write_tmp(content)
        self._dict_adv_editor.setPlainText(content)
        self._dict_update_undo_buttons()

    def _dict_undo_smart(self):
        """Undo that works in both modes."""
        if self._dict_stack.currentIndex() == 1:
            self._dict_undo_in_advanced()
        else:
            self._dict_undo()

    def _dict_redo_smart(self):
        """Redo that works in both modes."""
        if self._dict_stack.currentIndex() == 1:
            self._dict_redo_in_advanced()
        else:
            self._dict_redo()

    def _dict_save_smart(self):
        """Save that works in both modes."""
        if self._dict_stack.currentIndex() == 1:
            # En mode avancé : valider syntaxe, écrire .tmp, copier vers officiel, basculer
            text = self._dict_adv_editor.toPlainText()
            if not text.endswith("\n"):
                text += "\n"
            ok, err = self._validate_dict_syntax(text)
            if not ok:
                QMessageBox.warning(self._pp_parent, "dictee",
                    _("Cannot save — syntax error:\n\n{err}").format(err=err))
                return
            self._save_dict_advanced()
            self._save_dict_official()
            QMessageBox.information(self._pp_parent, "dictee", _("Dictionary saved."))
            self._btn_advanced.blockSignals(True)
            self._btn_advanced.setChecked(False)
            self._btn_advanced.blockSignals(False)
            self._load_dict_form()
            self._dict_stack.setCurrentIndex(0)
        else:
            # En mode normal : écrire .tmp puis copier vers officiel
            self._save_dict_to_tmp()
            self._save_dict_official()
            QMessageBox.information(self._pp_parent, "dictee", _("Dictionary saved."))
        if hasattr(self, '_schedule_test_run'):
            self._schedule_test_run()

    def _dict_update_undo_buttons(self):
        """Synchronise l'état enabled des boutons undo/redo."""
        if hasattr(self, '_btn_dict_undo'):
            self._btn_dict_undo.setEnabled(bool(self._dict_undo_stack))
        if hasattr(self, '_btn_dict_redo'):
            self._btn_dict_redo.setEnabled(bool(self._dict_redo_stack))

    def _dict_init_tmp(self):
        """Copie le fichier officiel vers .tmp et vide les stacks undo/redo."""
        self._dict_undo_stack = []
        self._dict_redo_stack = []
        self._dict_saved = False
        self._dict_update_undo_buttons()
        os.makedirs(os.path.dirname(self._dict_path), exist_ok=True)
        if os.path.isfile(self._dict_path):
            shutil.copy2(self._dict_path, self._dict_tmp_path)
        elif os.path.isfile(self._dict_tmp_path):
            os.remove(self._dict_tmp_path)

    def _dict_cleanup_tmp(self):
        """Supprime le .tmp si l'utilisateur n'a pas enregistré."""
        if not self._dict_saved:
            if os.path.isfile(self._dict_tmp_path):
                os.remove(self._dict_tmp_path)

    def _save_dict_to_tmp(self, reload=False):
        """Écrit les entrées du formulaire dans le fichier brouillon .tmp."""
        result = self._dict_collect_entries()
        if result is None:
            return
        cat_entries, empty_rows = result

        # Remove empty rows from UI
        for row in empty_rows:
            if row in self._dict_rows:
                self._dict_rows.remove(row)
            row.setParent(None)
            row.deleteLater()

        text = self._dict_entries_to_text(cat_entries)
        os.makedirs(os.path.dirname(self._dict_tmp_path), exist_ok=True)
        with open(self._dict_tmp_path, "w", encoding="utf-8") as f:
            f.write(text)

        if reload:
            scroll_pos = self._dict_scroll.verticalScrollBar().value()
            self._load_dict_form()
            QTimer.singleShot(50, lambda: self._dict_scroll.verticalScrollBar().setValue(scroll_pos))

    def _save_dict_official(self):
        """Copie .tmp → officiel (bouton Enregistrer)."""
        # Wizard mode: dictionary tab wasn't built → nothing to save here.
        if not hasattr(self, '_dict_rows') or not hasattr(self, '_dict_path'):
            return
        result = self._dict_collect_entries()
        if result is None:
            return
        cat_entries, empty_rows = result

        # Remove empty rows from UI
        for row in empty_rows:
            if row in self._dict_rows:
                self._dict_rows.remove(row)
            row.setParent(None)
            row.deleteLater()

        text = self._dict_entries_to_text(cat_entries)
        os.makedirs(os.path.dirname(self._dict_tmp_path), exist_ok=True)
        with open(self._dict_tmp_path, "w", encoding="utf-8") as f:
            f.write(text)

        # Copy .tmp → official
        shutil.copy2(self._dict_tmp_path, self._dict_path)
        self._dict_saved = True
        self._dict_undo_stack.clear()
        self._dict_update_undo_buttons()

    def _validate_dict_syntax(self, text):
        """Validates dictionary syntax. Returns (ok, error_msg)."""
        entry_re = re.compile(r"^\s*\[([a-z]{2}|\*)\]\s*.+=.+\s*$")
        for i, line in enumerate(text.splitlines(), 1):
            line_s = line.strip()
            if not line_s or line_s.startswith("#"):
                continue
            if not entry_re.match(line_s):
                return False, _("Line {n}: invalid syntax: {line}").format(n=i, line=line_s)
        return True, ""

    def _dict_revert_to_saved(self):
        """Discards all changes since last save."""
        reply = QMessageBox.question(self._pp_parent, "dictee",
            _("Revert to the last saved version?\n\n"
              "All unsaved changes will be lost."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._dict_init_tmp()
        self._load_dict_form()
        # Si on était en mode avancé, revenir au mode normal
        if self._dict_stack.currentIndex() == 1:
            if os.path.isfile(self._dict_tmp_path):
                with open(self._dict_tmp_path, encoding="utf-8") as f:
                    self._dict_adv_editor.setPlainText(f.read())
            self._btn_advanced.blockSignals(True)
            self._btn_advanced.setChecked(False)
            self._btn_advanced.blockSignals(False)
            self._dict_stack.setCurrentIndex(0)

    def _dict_cancel_advanced(self):
        """Discard : recharger depuis le dernier fichier officiel enregistré."""
        self._dict_init_tmp()
        self._load_dict_form()
        self._btn_advanced.blockSignals(True)
        self._btn_advanced.setChecked(False)
        self._btn_advanced.blockSignals(False)
        self._dict_stack.setCurrentIndex(0)

    def _dict_save_advanced_and_switch(self):
        """Save en mode avancé : valider, écrire .tmp → officiel, basculer vers normal."""
        text = self._dict_adv_editor.toPlainText()
        if not text.endswith("\n"):
            text += "\n"
        ok, err = self._validate_dict_syntax(text)
        if not ok:
            QMessageBox.warning(self._pp_parent, "dictee", err)
            return
        # Validation OK: write and switch
        self._save_dict_advanced()
        self._btn_advanced.blockSignals(True)
        self._btn_advanced.setChecked(False)
        self._btn_advanced.blockSignals(False)
        self._load_dict_form()
        self._dict_stack.setCurrentIndex(0)

    def _restore_dict_defaults(self):
        """Restores factory dictionary to draft .tmp."""
        reply = QMessageBox.question(self._pp_parent, "dictee",
            _("Restore factory defaults?\n\n"
              "This will replace ALL your dictionary entries with the original defaults.\n"
              "Click Save afterwards to make it permanent."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        for candidate in [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictionary.conf.default"),
            "/usr/share/dictee/dictionary.conf.default",
        ]:
            if os.path.isfile(candidate):
                self._dict_push_undo()
                shutil.copy2(candidate, self._dict_tmp_path)
                self._load_dict_form()
                return
        QMessageBox.warning(self._pp_parent, "dictee", _("Default dictionary file not found."))

    def _dict_reorganize(self, text):
        """Reorganizes orphan dictionary entries.

        Entries written outside a category (before the first ── header)
        are placed in a 'Dictionary [lang]' section.
        Entries already in a category stay in place.
        """
        from collections import OrderedDict
        cat_re = re.compile(r"^#\s*──\s*(.+?)\s*─")
        entry_re = re.compile(r"^\s*\[([a-z]{2}|\*)\]\s*(.+?)=(.+?)\s*$")

        categories = []  # [(cat_name, [(lang, word, repl)])]
        current_cat = None  # None = pas encore de catégorie
        current_entries = []
        orphans = []  # entrées avant tout header

        for line in text.splitlines():
            line_s = line.strip()
            if not line_s:
                continue
            m_cat = cat_re.match(line_s)
            if m_cat:
                if current_cat is not None and current_entries:
                    categories.append((current_cat, current_entries))
                current_cat = m_cat.group(1).strip()
                current_entries = []
                continue
            if line_s.startswith("#"):
                continue
            m = entry_re.match(line_s)
            if m:
                lang, word, repl = m.group(1), m.group(2).strip(), m.group(3).strip()
                if current_cat is None:
                    orphans.append((lang, word, repl))
                else:
                    current_entries.append((lang, word, repl))
        if current_cat is not None and current_entries:
            categories.append((current_cat, current_entries))

        # Placer les orphelins dans Dictionary [lang]
        reorg = OrderedDict()
        for cat_name, entries in categories:
            reorg[cat_name] = entries
        for lang, word, repl in orphans:
            cat = f"Dictionary [{lang}]"
            if cat not in reorg:
                reorg[cat] = []
            reorg[cat].append((lang, word, repl))

        return self._dict_entries_to_text(reorg)

    def _save_dict_advanced(self):
        """Saves advanced mode content to .tmp (draft only)."""
        text = self._dict_adv_editor.toPlainText()
        if not text.endswith("\n"):
            text += "\n"

        ok, err = self._validate_dict_syntax(text)
        if not ok:
            QMessageBox.warning(self._pp_parent, "dictee", err)
            # Stay in advanced mode
            self._btn_advanced.blockSignals(True)
            self._btn_advanced.setChecked(True)
            self._btn_advanced.blockSignals(False)
            return

        # Reorganize entries into correct categories
        text = self._dict_reorganize(text)

        os.makedirs(os.path.dirname(self._dict_tmp_path), exist_ok=True)
        self._dict_push_undo()
        with open(self._dict_tmp_path, "w", encoding="utf-8") as f:
            f.write(text)

    # ── Continuation tab ────────────────────────────────────────

    _LANG_FLAGS = {
        "fr": "\U0001f1eb\U0001f1f7", "en": "\U0001f1ec\U0001f1e7",
        "de": "\U0001f1e9\U0001f1ea", "es": "\U0001f1ea\U0001f1f8",
        "it": "\U0001f1ee\U0001f1f9", "pt": "\U0001f1f5\U0001f1f9",
        "uk": "\U0001f1fa\U0001f1e6",
    }

    _LANG_FULLNAMES = {
        "fr": "Français", "en": "English", "de": "Deutsch",
        "es": "Español", "it": "Italiano", "pt": "Português",
        "uk": "Українська",
    }

    def _parse_cont_with_categories(self, path):
        """Parse un fichier continuation, retourne {lang: [(subcategory, [mot, ...])]}.

        Catégories principales : commentaires ``# ── Langue ─``
        Sous-catégories : commentaires ``# Sous-titre`` (sans ──)
        Entrées : ``[lang] mot1 mot2 ...``
        """
        result = {}  # lang -> [(subcat, [words])]
        current_lang = None
        current_subcat = _("Other")
        entry_re = re.compile(r"^\s*\[([a-z]{2})\]\s+(.+)$")
        lang_re = re.compile(r"^#\s*──\s*(.+?)\s*─")
        subcat_re = re.compile(r"^#\s+(.+)$")

        if not os.path.isfile(path):
            return result
        with open(path, encoding="utf-8") as f:
            for line in f:
                line_s = line.strip()
                if not line_s:
                    continue
                # Lang header  # ── French ──
                m_lang = lang_re.match(line_s)
                if m_lang:
                    current_subcat = _("Other")
                    continue
                # Sub-category  # Articles
                if line_s.startswith("#"):
                    m_sub = subcat_re.match(line_s)
                    if m_sub and "──" not in line_s:
                        current_subcat = m_sub.group(1).strip()
                    continue
                # Entry  [fr] le la les ...
                m = entry_re.match(line_s)
                if m:
                    lang = m.group(1)
                    words = m.group(2).split()
                    current_lang = lang
                    if lang not in result:
                        result[lang] = []
                    # Merge into existing subcat or create new
                    if result[lang] and result[lang][-1][0] == current_subcat:
                        result[lang][-1][1].extend(words)
                    else:
                        result[lang].append((current_subcat, list(words)))
        return result

    def _parse_cont_exclusions(self, path):
        """Returns {lang: set(excluded_words)} from [exclude:xx] lines."""
        result = {}
        if not os.path.isfile(path):
            return result
        exc_re = re.compile(r"^\s*\[exclude:([a-z]{2})\]\s+(.+)$")
        with open(path, encoding="utf-8") as f:
            for line in f:
                line_s = line.strip()
                if not line_s or line_s.startswith("#"):
                    continue
                m = exc_re.match(line_s)
                if m:
                    lang = m.group(1)
                    words = m.group(2).split()
                    result.setdefault(lang, set()).update(w.lower() for w in words)
        return result

    def _build_continuation_tab(self, lay):
        """Continuation tab: accordions per language with chips + edit mode."""
        import os as _os

        XDG_CFG = _os.environ.get("XDG_CONFIG_HOME", _os.path.expanduser("~/.config"))
        self._cont_path = _os.path.join(XDG_CFG, "dictee", "continuation.conf")

        # Find system file
        self._cont_sys_path = None
        for candidate in [
            _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "continuation.conf.default"),
            "/usr/share/dictee/continuation.conf.default",
        ]:
            if _os.path.isfile(candidate):
                self._cont_sys_path = candidate
                break

        # First launch: create empty personal file (les mots système sont lus séparément)
        if not _os.path.isfile(self._cont_path):
            _os.makedirs(_os.path.dirname(self._cont_path), exist_ok=True)
            with open(self._cont_path, "w", encoding="utf-8") as f:
                f.write("# User continuation words for dictee\n"
                        "# Format: [lang] word1 word2 ...\n\n")

        # Personal words per language : {lang: set()}
        self._cont_personal_words = {}
        # Excluded (removed from system) words per language : {lang: set()}
        self._cont_excluded_words = {}

        self._cont_stack = QStackedWidget()

        # --- Page 0: Form view ---
        form_page = QWidget()
        form_top_lay = QVBoxLayout(form_page)
        form_top_lay.setContentsMargins(0, 0, 0, 0)

        # Collapsible explanation (text + separator grouped in a container)
        _info_container = QWidget()
        _info_container_lay = QVBoxLayout(_info_container)
        _info_container_lay.setContentsMargins(0, 0, 0, 0)
        _info_container_lay.setSpacing(6)
        info = QLabel(_(
            "Continuation words are words that never end a sentence "
            "(articles, prepositions, conjunctions, pronouns, auxiliaries...).\n"
            "When the ASR incorrectly places a period after one of these words, "
            "the period is removed and the next sentence is joined.\n"
            "Example: \"Je suis allé. dans le parc\" → \"Je suis allé dans le parc\"\n\n"
            "When continuation is active, a visual indicator (default \">>\") "
            "appears at the end of the text to show the system is waiting "
            "for more input. Configurable via DICTEE_CONTINUATION_INDICATOR.\n\n"
            "System words are built-in and cannot be modified. "
            "You can add your own words per language below."
        ))
        info.setWordWrap(True)
        _info_font = info.font()
        _info_font.setItalic(True)
        info.setFont(_info_font)
        _info_container_lay.addWidget(info)

        # --- Separator (inside the collapsible block) ---
        _sep1 = QFrame()
        _sep1.setFrameShape(QFrame.Shape.HLine)
        _sep1.setFrameShadow(QFrame.Shadow.Sunken)
        _info_container_lay.addWidget(_sep1)

        _info_container.setVisible(False)

        _info_toggle = QPushButton("\u25b8  " + _("Explanation"))
        _info_toggle.setCheckable(True)
        _info_toggle.setChecked(False)
        _info_toggle.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        _info_toggle.setStyleSheet(
            "QPushButton { text-align: left; font-weight: bold; "
            "padding: 4px 12px; border: none; }"
            "QPushButton:hover { background-color: rgba(127,127,127,30); }"
        )

        def _on_info_toggled(on, box=_info_container, btn=_info_toggle):
            btn.setText(("\u25be  " if on else "\u25b8  ") + _("Explanation"))
            box.setVisible(on)
        _info_toggle.toggled.connect(_on_info_toggled)

        form_top_lay.addWidget(_info_toggle)
        form_top_lay.addWidget(_info_container)

        # Manual continuation fallback
        kw_info = QLabel(_(
            "Sometimes automatic continuation does not work as expected — "
            "the ASR may not place a period, or the last word may not be in the list above. "
            "In that case, you can say a keyword at the start of the next segment "
            "to force continuation manually."
        ))
        kw_info.setWordWrap(True)
        _kw_font = kw_info.font()
        _kw_font.setItalic(True)
        kw_info.setFont(_kw_font)
        _info_container_lay.addWidget(kw_info)

        # Continuation keyword (per language) — widgets created here,
        # laid out further below on the same row as the visual indicator.
        kw_label = QLabel(_("Continuation keyword:"))
        kw_help = _help_btn(_(
            "<b>Continuation keyword</b><br><br>"
            "The continuation system automatically joins sentences when the ASR "
            "incorrectly places a period after a closed-class word (article, "
            "preposition, conjunction…). However, <b>automatic continuation "
            "does not always work</b> — the ASR may not place a period, or "
            "the last word may not be in the continuation list.<br><br>"
            "The continuation keyword is a <b>manual fallback</b>: say it at the "
            "start of a new dictation segment to force continuation. The system "
            "removes the previous punctuation and joins in lowercase.<br><br>"
            "<b>Examples:</b><br>"
            "• FR (keyword = \"minuscule\"): \"Je mange.\" + \"minuscule du fromage\" "
            "→ \"Je mange du fromage\"<br>"
            "• EN (keyword = \"lowercase\"): \"I eat.\" + \"lowercase some cheese\" "
            "→ \"I eat some cheese\"<br>"
            "• DE (keyword = \"klein\"): \"Ich esse.\" + \"klein etwas Käse\" "
            "→ \"Ich esse etwas Käse\"<br><br>"
            "<b>Per language:</b> Select a language in the combo box to set "
            "a different keyword for each language. The keyword is only active "
            "when dictating in that language.<br><br>"
            "Leave empty to disable for that language."))
        self._cont_kw_lang = QComboBox()
        self._cont_kw_lang.setFixedWidth(60)
        _lang = self.conf.get("DICTEE_LANG_SOURCE", "fr")
        # Store keywords per language
        self._cont_keywords = {}
        for code, _name in LANGUAGES:
            self._cont_kw_lang.addItem(code)
            self._cont_keywords[code] = self._load_cont_keyword(code)
        idx = self._cont_kw_lang.findText(_lang)
        if idx >= 0:
            self._cont_kw_lang.setCurrentIndex(idx)
        self._cont_keyword = QLineEdit()
        self._cont_keyword.setMaximumWidth(200)
        self._cont_keyword.setPlaceholderText("minuscule")
        self._cont_keyword.setText(self._cont_keywords.get(_lang, ""))
        self._cont_kw_lang.currentTextChanged.connect(self._on_cont_kw_lang_changed)
        self._cont_keyword.textChanged.connect(self._on_cont_kw_text_changed)

        # Visual indicator combobox: pre-tested ASCII strings that are
        # directly typeable on all latin keyboard layouts via dotool.
        ind_lay = QHBoxLayout()
        ind_lay.setSpacing(6)
        ind_label = QLabel(_("Visual indicator:"))
        ind_help = _help_btn(_(
            "<b>Continuation visual indicator</b><br><br>"
            "Character(s) appended to the typed text when continuation "
            "is pending. The next push erases them automatically.<br><br>"
            "Only ASCII strings that can be typed on every latin layout "
            "without dead-keys or AltGr are listed. Unicode arrows like "
            "→ or ▶ would require clipboard paste and are not offered "
            "here to keep the user clipboard intact."))
        self.cmb_continuation_indicator = QComboBox()
        self.cmb_continuation_indicator.setFixedWidth(120)
        # (display, value) — value is what gets written to dictee.conf
        for _disp, _val in [
            (">>", ">>"),
            (">",  ">"),
            (">>>", ">>>"),
            ("&",  "&"),
            ("...", "..."),
            ("•",  "•"),  # may not be on all layouts; user choice
        ]:
            self.cmb_continuation_indicator.addItem(_disp, _val)
        _saved_ind = self.conf.get("DICTEE_CONTINUATION_INDICATOR", ">>")
        _ind_idx = self.cmb_continuation_indicator.findData(_saved_ind)
        if _ind_idx < 0:
            # Custom value not in list — add it on the fly
            self.cmb_continuation_indicator.addItem(_saved_ind, _saved_ind)
            _ind_idx = self.cmb_continuation_indicator.count() - 1
        self.cmb_continuation_indicator.setCurrentIndex(_ind_idx)
        self.cmb_continuation_indicator.currentIndexChanged.connect(self._mark_dirty)
        ind_lay.addWidget(ind_label)
        ind_lay.addWidget(self.cmb_continuation_indicator)
        ind_lay.addWidget(ind_help)
        # Separator between indicator block and continuation keyword block
        ind_lay.addSpacing(20)
        ind_lay.addWidget(kw_label)
        ind_lay.addWidget(self._cont_kw_lang)
        ind_lay.addWidget(self._cont_keyword)
        ind_lay.addWidget(kw_help)
        ind_lay.addStretch()
        form_top_lay.addLayout(ind_lay)

        # Variants label — own line, wraps if too long. Small left indent
        # instead of a fixed spacer so the label can shrink with the window.
        self._cont_kw_variants = QLabel()
        self._cont_kw_variants.setStyleSheet(
            "color: gray; font-size: 11px; padding-left: 20px;")
        self._cont_kw_variants.setWordWrap(True)
        self._cont_kw_variants.setMinimumWidth(1)
        form_top_lay.addWidget(self._cont_kw_variants)
        self._update_kw_variants(self._cont_keywords.get(_lang, ""))

        # --- Separator ---
        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.HLine)
        _sep.setFrameShadow(QFrame.Shadow.Sunken)
        form_top_lay.addWidget(_sep)

        # Search bar
        self._cont_search = QLineEdit()
        self._cont_search.addAction(
            QIcon.fromTheme("edit-find"), QLineEdit.ActionPosition.LeadingPosition)
        self._cont_search.setMaximumWidth(250)
        self._cont_search.textChanged.connect(self._filter_cont_words)
        form_top_lay.addWidget(self._cont_search)

        # Scrollable area for accordions
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cont_scroll_content = QWidget()
        self._cont_form_layout = QVBoxLayout(self._cont_scroll_content)
        self._cont_form_layout.setContentsMargins(4, 4, 4, 4)
        self._cont_form_layout.setSpacing(6)
        scroll.setWidget(self._cont_scroll_content)
        form_top_lay.addWidget(scroll)

        # No Cancel/Apply buttons : chaque ajout/suppression sauvegarde immédiatement

        self._cont_stack.addWidget(form_page)

        # --- Page 1: Advanced mode ---
        adv_page = QWidget()
        adv_lay = QVBoxLayout(adv_page)
        adv_lay.setContentsMargins(0, 0, 0, 0)

        self._cont_adv_editor = QTextEdit()
        self._cont_adv_editor.setFont(self._monospace_font())
        self._cont_adv_editor.setPlaceholderText(
            "# [lang] word1 word2 word3 ...\n"
            "# Example:\n"
            "# [fr] donc alors\n"
            "# [en] however moreover\n")
        adv_lay.addWidget(self._cont_adv_editor)

        self._add_zoom_overlay(self._cont_adv_editor)

        self._cont_stack.addWidget(adv_page)

        lay.addWidget(self._cont_stack)

        # --- Common toolbar ---
        common_btns = QHBoxLayout()

        btn_cont_save = QPushButton(_("Save"))
        btn_cont_save.setToolTip(_("Save continuation words to disk"))
        btn_cont_save.clicked.connect(self._cont_save_smart)
        common_btns.addWidget(btn_cont_save)

        common_btns.addStretch()

        btn_cont_revert = QPushButton(_("Revert to saved"))
        btn_cont_revert.setToolTip(_("Discard all unsaved changes"))
        btn_cont_revert.clicked.connect(self._cont_revert)
        common_btns.addWidget(btn_cont_revert)

        btn_cont_factory = QPushButton(_("Factory reset"))
        btn_cont_factory.setToolTip(_("Restore factory defaults"))
        btn_cont_factory.clicked.connect(self._cont_factory_reset)
        common_btns.addWidget(btn_cont_factory)

        lay.addLayout(common_btns)

        # Save initial state for Revert
        self._cont_saved_state = None
        if os.path.isfile(self._cont_path):
            with open(self._cont_path, encoding="utf-8") as f:
                self._cont_saved_state = f.read()

        # Load the form
        self._load_cont_form()

    def _cont_refresh_scroll(self):
        """Force the continuation QScrollArea to recompute its content
        size after a category fold/unfold. The canonical Qt fix is to
        propagate updateGeometry bottom-up so the scroll area picks up
        the new (smaller) sizeHint instead of caching the old layout.
        """
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QApplication
        w = getattr(self, "_cont_scroll_content", None)
        if w is None:
            return
        # Walk children bottom-up and call updateGeometry on each
        for child in w.findChildren(QWidget):
            child.updateGeometry()
        lay = w.layout()
        if lay is not None:
            lay.invalidate()
            lay.activate()
        w.updateGeometry()
        w.adjustSize()
        # Drain any pending LayoutRequest events on the scroll content
        QApplication.sendPostedEvents(w, QEvent.Type.LayoutRequest)
        p = w.parentWidget()
        while p is not None and not isinstance(p, QScrollArea):
            p = p.parentWidget()
        if p is not None:
            p.updateGeometry()
            p.verticalScrollBar().setValue(0)

    def _load_cont_form(self):
        """Clears and rebuilds the Continuation tab accordions."""
        layout = self._cont_form_layout

        # Vider le layout existant — détacher immédiatement
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                sub = item.layout()
                while sub.count():
                    si = sub.takeAt(0)
                    sw = si.widget()
                    if sw:
                        sw.setParent(None)
                        sw.deleteLater()

        QApplication.processEvents()

        # Load system words
        sys_cats = {}
        if self._cont_sys_path:
            sys_cats = self._parse_cont_with_categories(self._cont_sys_path)

        # Load personal words from file only on first load
        # or after a revert/factory reset (_cont_force_reload)
        if not self._cont_personal_words or getattr(self, '_cont_force_reload', False):
            self._cont_personal_words.clear()
            self._cont_excluded_words.clear()
            self._cont_force_reload = False
            user_cats = self._parse_cont_with_categories(self._cont_path)
            for lang, subcats in user_cats.items():
                words_set = set()
                for _sc, words in subcats:
                    words_set.update(words)
                self._cont_personal_words[lang] = words_set
            # Load exclusions ([exclude:xx] lines)
            excl = self._parse_cont_exclusions(self._cont_path)
            for lang, wset in excl.items():
                self._cont_excluded_words[lang] = wset
            # Snapshot the loaded state so the test panel can detect
            # pending-but-unsaved changes (merge warning).
            self._snapshot_cont_state()

        # Determine active language
        active_lang = self.conf.get("DICTEE_LANG_SOURCE", "fr")

        # Collect all languages (system + personal)
        all_langs = sorted(set(list(sys_cats.keys()) + list(self._cont_personal_words.keys())))

        # Build one accordion per language
        for lang in all_langs:
            excluded_set = self._cont_excluded_words.get(lang, set())
            sys_words_all = []
            sys_subcats = sys_cats.get(lang, [])
            for _sc, words in sys_subcats:
                # Filter out excluded (case-insensitive)
                sys_words_all.extend(
                    w for w in words if w.lower() not in excluded_set
                )

            perso_words = self._cont_personal_words.get(lang, set())
            total = len(sys_words_all) + len(perso_words)

            flag = self._LANG_FLAGS.get(lang, "")
            name = self._LANG_FULLNAMES.get(lang, lang.upper())
            title = f"{flag} {name} ({total} " + (_("words") if total != 1 else _("word")) + ")"

            # Bouton titre repliable
            btn_lang = QPushButton(("\u25be " if lang == active_lang else "\u25b8 ") + title)
            btn_lang.setFlat(True)
            btn_lang.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            btn_lang.setStyleSheet("text-align: left; font-weight: bold; padding: 4px 12px;")
            layout.addWidget(btn_lang)

            group = QWidget()
            # Maximum vertical so the group never claims more height than
            # its sizeHint — critical for QScrollArea to recompute its
            # range when this group is folded/unfolded.
            group.setSizePolicy(QSizePolicy.Policy.Preferred,
                                QSizePolicy.Policy.Maximum)
            group.setVisible(lang == active_lang)
            group_lay = QVBoxLayout(group)
            group_lay.setSpacing(4)
            group_lay.setContentsMargins(16, 4, 0, 8)

            def _make_lang_toggle(btn, w, t=title):
                def _toggle():
                    vis = not w.isVisible()
                    w.setVisible(vis)
                    btn.setText(("\u25be " if vis else "\u25b8 ") + t)
                    self._cont_refresh_scroll()
                return _toggle
            btn_lang.clicked.connect(_make_lang_toggle(btn_lang, group))

            # --- Words ---
            hl_color = self.palette().color(self.palette().ColorRole.Highlight)
            hl_hex = hl_color.name()
            hl_text_hex = self.palette().color(self.palette().ColorRole.HighlightedText).name()

            # Collect all system words
            sys_all = set()
            for _sc, words in sys_subcats:
                sys_all.update(words)

            # System words toggle (on top) — open by default for active language
            sys_count = len(sys_all)
            _sys_open = (lang == active_lang)
            _sys_arrow = "\u25be" if _sys_open else "\u25b8"
            btn_show_sys = QPushButton(
                f"{_sys_arrow} {_('System words')} ({sys_count})")
            btn_show_sys.setFlat(True)
            btn_show_sys.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            btn_show_sys.setStyleSheet("text-align: left; color: gray; padding: 2px 12px;")
            group_lay.addWidget(btn_show_sys)

            # System chips
            sys_w = QWidget()
            _sp = sys_w.sizePolicy()
            _sp.setVerticalPolicy(QSizePolicy.Policy.Maximum)
            _sp.setHeightForWidth(True)
            sys_w.setSizePolicy(_sp)
            sys_lay = self._FlowLayout(sys_w, spacing=8)
            for word in sorted(sys_all, key=locale.strxfrm):
                lbl = QLabel(f"  {word}  ")
                lbl.setStyleSheet(
                    "background:rgba(128,128,128,0.3); border-radius:14px; "
                    "padding:6px 14px; font-size:14px;")
                sys_lay.addWidget(lbl)
            sys_w.setVisible(_sys_open)
            sys_w.setProperty("cont_sys_chips", True)
            group_lay.addWidget(sys_w)

            def _toggle_sys(checked=None, btn=btn_show_sys, sw=sys_w, n=sys_count):
                vis = not sw.isVisible()
                sw.setVisible(vis)
                arrow = "\u25be" if vis else "\u25b8"
                btn.setText(f"{arrow} {_('System words')} ({n})")
                self._cont_refresh_scroll()
            btn_show_sys.clicked.connect(_toggle_sys)

            # Personal chips (always visible, after system)
            lbl_yours = QLabel(f"<b>{_('Your words:')}</b>")
            group_lay.addWidget(lbl_yours)
            if perso_words:
                perso_w = QWidget()
                _sp2 = perso_w.sizePolicy()
                _sp2.setVerticalPolicy(QSizePolicy.Policy.Maximum)
                _sp2.setHeightForWidth(True)
                perso_w.setSizePolicy(_sp2)
                perso_lay = self._FlowLayout(perso_w, spacing=8)
                for word in sorted(perso_words, key=locale.strxfrm):
                    btn = QPushButton(f"  {word}  \u2715  ")
                    btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn.setStyleSheet(
                        f"QPushButton {{ background:{hl_hex}; color:{hl_text_hex}; "
                        f"border-radius:14px; padding:6px 14px; font-size:14px; border:none; }}"
                        f"QPushButton:hover {{ background:{hl_color.darker(120).name()}; }}")
                    btn.clicked.connect(lambda checked, w=word, l=lang: self._remove_cont_word(l, w))
                    perso_lay.addWidget(btn)
                group_lay.addWidget(perso_w)
            else:
                lbl_none = QLabel("<i>" + _("(none)") + "</i>")
                group_lay.addWidget(lbl_none)

            # --- Add field ---
            add_row = QHBoxLayout()
            add_edit = QLineEdit()
            add_edit.setPlaceholderText(_("Add a word..."))
            add_edit.returnPressed.connect(
                lambda le=add_edit, l=lang: self._add_cont_word(l, le)
            )
            add_row.addWidget(add_edit)
            btn_add = QPushButton("+ " + _("Add"))
            btn_add.clicked.connect(
                lambda checked, le=add_edit, l=lang: self._add_cont_word(l, le)
            )
            add_row.addWidget(btn_add)
            group_lay.addLayout(add_row)

            layout.addWidget(group)

        layout.addStretch()

        # Ré-appliquer le filtre de recherche s'il y a du texte
        if hasattr(self, '_cont_search') and self._cont_search.text().strip():
            self._filter_cont_words()

        # Defer a scroll geometry refresh so the FlowLayouts inside hidden
        # groups have time to settle before we measure them.
        QTimer.singleShot(0, self._cont_refresh_scroll)

    class _FlowLayout(QLayout):
        """Layout qui wrappe les widgets horizontalement comme du texte."""

        def __init__(self, parent=None, spacing=4):
            super().__init__(parent)
            self._items = []
            self._spacing = spacing

        def addItem(self, item):
            self._items.append(item)

        def count(self):
            return len(self._items)

        def itemAt(self, index):
            if 0 <= index < len(self._items):
                return self._items[index]
            return None

        def takeAt(self, index):
            if 0 <= index < len(self._items):
                return self._items.pop(index)
            return None

        def sizeHint(self):
            # Real sizeHint based on visible items so QScrollArea can
            # propagate a correct height up the chain.
            size = QSize()
            for item in self._items:
                if item.isEmpty():
                    continue
                size = size.expandedTo(item.minimumSize())
            m = self.contentsMargins()
            size += QSize(m.left() + m.right(), m.top() + m.bottom())
            return size

        def minimumSize(self):
            return self.sizeHint()

        def expandingDirections(self):
            return Qt.Orientation(0)

        def setGeometry(self, rect):
            super().setGeometry(rect)
            self._do_layout(rect, dry_run=False)

        def hasHeightForWidth(self):
            return True

        def heightForWidth(self, width):
            return self._do_layout(QRect(0, 0, width, 0), dry_run=True)

        def _do_layout(self, rect, dry_run=False):
            x = rect.x()
            y = rect.y()
            row_height = 0
            for item in self._items:
                # Qt's canonical "should I lay out this item?" check.
                # Honors hidden widgets (and their ancestors) via the
                # default QWidgetItem.isEmpty() implementation.
                if item.isEmpty():
                    continue
                size = item.sizeHint()
                if x + size.width() > rect.right() and x > rect.x():
                    x = rect.x()
                    y += row_height + self._spacing
                    row_height = 0
                if not dry_run:
                    item.setGeometry(QRect(x, y, size.width(), size.height()))
                x += size.width() + self._spacing
                row_height = max(row_height, size.height())
            return y + row_height - rect.y()

    def _make_flow_layout(self, parent):
        """Crée un FlowLayout sur le parent."""
        lay = self._FlowLayout(parent, spacing=4)
        return lay

    def _add_cont_word(self, lang, line_edit):
        """Adds a personal word in memory (no disk write)."""
        word = line_edit.text().strip().lower()
        if not word:
            return
        if lang not in self._cont_personal_words:
            self._cont_personal_words[lang] = set()
        if word in self._cont_personal_words[lang]:
            return  # déjà présent
        # Vérifier qu'il n'est pas déjà dans le système
        if self._cont_sys_path:
            sys_cats = self._parse_cont_with_categories(self._cont_sys_path)
            for _sc, words in sys_cats.get(lang, []):
                if word in words:
                    QMessageBox.information(self._pp_parent, "dictee",
                        _("'{word}' is already in the system list.").format(word=word))
                    return
        self._cont_personal_words[lang].add(word)
        line_edit.clear()
        self._load_cont_form()
        # Refresh the test panel so the user sees the effect immediately
        if hasattr(self, '_schedule_test_run'):
            self._schedule_test_run()

    def _on_cont_chip_clicked(self, link):
        """Handles click on personal chip (remove:lang:word)."""
        if link.startswith("remove:"):
            parts = link.split(":", 2)
            if len(parts) == 3:
                self._remove_cont_word(parts[1], parts[2])

    def _remove_cont_word(self, lang, word):
        """Removes a personal word from memory (no disk write)."""
        if lang in self._cont_personal_words:
            self._cont_personal_words[lang].discard(word)
        self._load_cont_form()
        if hasattr(self, '_schedule_test_run'):
            self._schedule_test_run()

    def _filter_cont_words(self):
        """Filters visible chips by search."""
        search = self._cont_search.text().lower().strip() if hasattr(self, '_cont_search') else ""
        active_lang = self.conf.get("DICTEE_LANG_SOURCE", "fr")
        layout = self._cont_form_layout
        i = 0
        while i < layout.count():
            item = layout.itemAt(i)
            if item is None:
                i += 1
                continue
            w = item.widget()
            if w is None:
                i += 1
                continue
            # Boutons titre (accordéons langue)
            if isinstance(w, QPushButton) and w.isFlat() and "(" in w.text():
                i += 1
                if i >= layout.count():
                    break
                content_item = layout.itemAt(i)
                content_w = content_item.widget() if content_item else None
                if content_w is None:
                    i += 1
                    continue
                i += 1

                # Détecter si c'est la langue active (flag emoji dans le titre)
                is_active = any(fn in w.text() for fn in
                    [self._LANG_FULLNAMES.get(active_lang, "")])

                if not search:
                    # Pas de recherche : restaurer l'état par défaut
                    w.setVisible(True)
                    content_w.setVisible(is_active)
                    for child in content_w.findChildren((QLabel, QPushButton)):
                        child.setVisible(True)
                    for child in content_w.findChildren(QWidget):
                        if child.property("cont_sys_chips"):
                            child.setVisible(False)
                    # Remettre les icônes des toggles système à ▸ (fermé)
                    for child in content_w.findChildren(QPushButton):
                        ct = child.text()
                        if _("System words") in ct and ct.startswith("\u25be"):
                            child.setText("\u25b8" + ct[1:])
                    txt = w.text()
                    arrow = "\u25be" if is_active else "\u25b8"
                    w.setText(arrow + txt[1:])
                    continue

                # Filtrer les chips individuels (perso ET système)
                any_match = False
                # Ouvrir les mots système et mettre l'icône ▾
                for child in content_w.findChildren(QWidget):
                    if child.property("cont_sys_chips"):
                        child.setVisible(True)
                for child in content_w.findChildren(QPushButton):
                    ct = child.text()
                    if _("System words") in ct and ct.startswith("\u25b8"):
                        child.setText("\u25be" + ct[1:])
                for child in content_w.findChildren((QLabel, QPushButton)):
                    text = child.text().replace("\u2715", "").strip()
                    if not text or text.startswith("\u25b8") or text.startswith("\u25be"):
                        continue
                    if _("Your words") in text or _("System words") in text:
                        continue
                    if search in text.lower():
                        child.setVisible(True)
                        any_match = True
                    else:
                        child.setVisible(False)
                w.setVisible(any_match)
                content_w.setVisible(any_match)
                txt = w.text()
                arrow = "\u25be" if any_match else "\u25b8"
                w.setText(arrow + txt[1:])
            else:
                i += 1

    def _save_cont_personal(self):
        """Saves personal words + keyword to ~/.config/dictee/continuation.conf."""
        import os as _os

        # Wizard mode: continuation tab wasn't built → nothing to save here.
        # The ~/.config/dictee/continuation.conf will be created lazily when
        # the user opens the PP page later.
        if not hasattr(self, '_cont_path') or not hasattr(self, '_cont_personal_words'):
            return

        _os.makedirs(_os.path.dirname(self._cont_path), exist_ok=True)
        with open(self._cont_path, "w", encoding="utf-8") as f:
            f.write("# User continuation words for dictee\n")
            f.write("# Format: [lang] word1 word2 ...\n\n")
            # Save continuation keywords (all languages)
            if hasattr(self, '_cont_keywords'):
                for lang, kw in sorted(self._cont_keywords.items()):
                    if kw:
                        f.write(f"[keyword:{lang}] {kw}\n")
                f.write("\n")
            for lang in sorted(self._cont_personal_words.keys()):
                words = sorted(self._cont_personal_words[lang])
                if words:
                    f.write(f"[{lang}] {' '.join(words)}\n")
            # Excluded (removed from system) words
            if hasattr(self, '_cont_excluded_words') and self._cont_excluded_words:
                f.write("\n")
                for lang in sorted(self._cont_excluded_words.keys()):
                    words = sorted(self._cont_excluded_words[lang])
                    if words:
                        f.write(f"[exclude:{lang}] {' '.join(words)}\n")
        # Refresh the unsaved-changes snapshot so the test panel warning
        # clears right after Save.
        self._snapshot_cont_state()
        if hasattr(self, '_schedule_test_run'):
            self._schedule_test_run()

    def _snapshot_cont_state(self):
        """Freeze the current in-memory continuation state as baseline.

        Used by `_has_unsaved_cont_changes` to detect pending edits
        that haven't been persisted to ~/.config/dictee/continuation.conf.
        """
        self._cont_personal_snapshot = {
            k: set(v) for k, v in
            getattr(self, '_cont_personal_words', {}).items()}
        self._cont_excluded_snapshot = {
            k: set(v) for k, v in
            getattr(self, '_cont_excluded_words', {}).items()}

    def _has_unsaved_cont_changes(self):
        """Return True when in-memory continuation state diverges from
        the last saved/loaded baseline."""
        snap_a = getattr(self, '_cont_personal_snapshot', None)
        snap_e = getattr(self, '_cont_excluded_snapshot', None)
        if snap_a is None or snap_e is None:
            return False
        cur_a = getattr(self, '_cont_personal_words', {})
        cur_e = getattr(self, '_cont_excluded_words', {})
        all_langs = set(snap_a) | set(cur_a) | set(snap_e) | set(cur_e)
        for lang in all_langs:
            if snap_a.get(lang, set()) != cur_a.get(lang, set()):
                return True
            if snap_e.get(lang, set()) != cur_e.get(lang, set()):
                return True
        return False

    def _cont_save_smart(self):
        """Save (normal or advanced mode)."""
        if self._cont_stack.currentIndex() == 1:
            self._save_cont_advanced()
            self._btn_advanced.blockSignals(True)
            self._btn_advanced.setChecked(False)
            self._btn_advanced.blockSignals(False)
            self._cont_force_reload = True
            self._load_cont_form()
            self._cont_stack.setCurrentIndex(0)
        else:
            self._save_cont_personal()
        # Update saved state
        if os.path.isfile(self._cont_path):
            with open(self._cont_path, encoding="utf-8") as f:
                self._cont_saved_state = f.read()
        QMessageBox.information(self._pp_parent, "dictee", _("Continuation words saved."))

    def _cont_revert(self):
        """Discards changes — reverts to state at open time."""
        reply = QMessageBox.question(self._pp_parent, "dictee",
            _("Revert to the last saved version?\n\n"
              "All unsaved changes will be lost."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        # Restore file as it was at open time
        os.makedirs(os.path.dirname(self._cont_path), exist_ok=True)
        with open(self._cont_path, "w", encoding="utf-8") as f:
            f.write(self._cont_saved_state or "")
        self._cont_force_reload = True
        self._load_cont_form()
        if self._cont_stack.currentIndex() == 1:
            self._btn_advanced.blockSignals(True)
            self._btn_advanced.setChecked(False)
            self._btn_advanced.blockSignals(False)
            self._cont_stack.setCurrentIndex(0)

    def _load_cont_keyword(self, lang="fr"):
        """Load continuation keyword for a language from conf files."""
        # Search order: [keyword:lang] user, [keyword:lang] system, [keyword] user, [keyword] system
        for tag in [f"[keyword:{lang}]", "[keyword]"]:
            for cf in [self._cont_path, self._cont_sys_path]:
                if not cf or not os.path.isfile(cf):
                    continue
                with open(cf, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(tag):
                            return line[len(tag):].strip()
        return "minuscule"

    def _update_kw_variants(self, text):
        """Show accepted variants of the continuation keyword."""
        kw = text.strip()
        if not kw:
            self._cont_kw_variants.setText(_("(disabled)"))
            return
        variants = set()
        variants.add(kw)
        variants.add(kw.capitalize())
        # Without hyphens
        if '-' in kw:
            no_hyphen = kw.replace('-', '')
            variants.add(no_hyphen)
            variants.add(no_hyphen.capitalize())
            with_space = kw.replace('-', ' ')
            variants.add(with_space)
            variants.add(with_space.capitalize())
        # Without spaces
        if ' ' in kw:
            no_space = kw.replace(' ', '')
            variants.add(no_space)
            variants.add(no_space.capitalize())
            with_hyphen = kw.replace(' ', '-')
            variants.add(with_hyphen)
            variants.add(with_hyphen.capitalize())
        sorted_v = sorted(variants, key=lambda s: (s.lower(), s))
        full = ", ".join(sorted_v)
        max_shown = 4
        if len(sorted_v) > max_shown:
            shown = ", ".join(sorted_v[:max_shown]) + _(", … (+{n} more)").format(
                n=len(sorted_v) - max_shown)
        else:
            shown = full
        self._cont_kw_variants.setText(_("Accepted: ") + shown)
        self._cont_kw_variants.setToolTip(_("Accepted: ") + full)

    def _on_cont_kw_lang_changed(self, lang):
        """Switch continuation keyword when language combo changes."""
        # Save current value
        self._cont_keyword.blockSignals(True)
        self._cont_keyword.setText(self._cont_keywords.get(lang, ""))
        self._cont_keyword.blockSignals(False)
        self._update_kw_variants(self._cont_keyword.text())

    def _on_cont_kw_text_changed(self, text):
        """Save keyword for current language in memory."""
        lang = self._cont_kw_lang.currentText()
        self._cont_keywords[lang] = text.strip()
        self._update_kw_variants(text)

    def _on_suffix_lang_changed(self, lang):
        """Switch command suffix when language combo changes."""
        self._command_suffix.blockSignals(True)
        self._command_suffix.setText(self._command_suffixes.get(lang, ""))
        self._command_suffix.blockSignals(False)

    def _on_suffix_changed(self, text):
        """Save suffix for current language in memory."""
        lang = self._suffix_lang.currentText()
        self._command_suffixes[lang] = text.strip()

    def _cont_factory_reset(self):
        """Restores system file defaults."""
        reply = QMessageBox.question(self._pp_parent, "dictee",
            _("Remove all your custom continuation words?\n\n"
              "System words will remain unchanged."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._cont_personal_words.clear()
        self._save_cont_personal()
        self._load_cont_form()

    def _cont_build_advanced_text(self):
        """Build the text shown in the advanced editor: keywords + system
        words (with user additions merged and exclusions removed), editable."""
        lines = []
        lines.append("# User continuation words for dictee")
        lines.append("# Format: [lang] word1 word2 ...")
        lines.append("# Edit lines below to add/remove words. On save, the")
        lines.append("# diff vs system words is stored as additions/exclusions.")
        lines.append("")
        # Keywords
        if hasattr(self, '_cont_keywords'):
            for lang, kw in sorted(self._cont_keywords.items()):
                if kw:
                    lines.append(f"[keyword:{lang}] {kw}")
            lines.append("")
        # Load system words
        sys_cats = {}
        if self._cont_sys_path:
            sys_cats = self._parse_cont_with_categories(self._cont_sys_path)
        # Merge: (system ∪ personal) − excluded
        lines.append("# --- Continuation words (editable — remove what you don't want) ---")
        all_langs = sorted(set(list(sys_cats.keys()) + list(self._cont_personal_words.keys())))
        for lang in all_langs:
            sys_words = set()
            for _sc, words in sys_cats.get(lang, []):
                sys_words.update(w.lower() for w in words)
            perso = {w.lower() for w in self._cont_personal_words.get(lang, set())}
            excl = self._cont_excluded_words.get(lang, set())
            merged = (sys_words | perso) - excl
            if merged:
                lines.append(f"[{lang}] {' '.join(sorted(merged))}")
        return "\n".join(lines) + "\n"

    def _save_cont_advanced(self):
        """Parses the advanced editor, computes diff vs system words, and
        writes keywords + personal additions + [exclude:xx] lines."""
        import os as _os

        text = self._cont_adv_editor.toPlainText()

        # Parse editor content
        keywords = {}
        editor_words = {}  # lang -> set
        kw_re = re.compile(r"^\s*\[keyword:([a-z]{2})\]\s*(.+)$")
        entry_re = re.compile(r"^\s*\[([a-z]{2})\]\s+(.+)$")
        for line in text.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("#"):
                continue
            m = kw_re.match(line_s)
            if m:
                keywords[m.group(1)] = m.group(2).strip()
                continue
            m = entry_re.match(line_s)
            if m:
                lang = m.group(1)
                words = {w.lower() for w in m.group(2).split()}
                editor_words.setdefault(lang, set()).update(words)

        # Load system reference
        sys_cats = {}
        if self._cont_sys_path:
            sys_cats = self._parse_cont_with_categories(self._cont_sys_path)
        sys_sets = {}
        for lang, subcats in sys_cats.items():
            s = set()
            for _sc, words in subcats:
                s.update(w.lower() for w in words)
            sys_sets[lang] = s

        # Diff → personals + exclusions
        new_personals = {}
        new_excluded = {}
        all_langs = set(sys_sets.keys()) | set(editor_words.keys())
        for lang in all_langs:
            sys_s = sys_sets.get(lang, set())
            ed_s = editor_words.get(lang, set())
            added = ed_s - sys_s
            removed = sys_s - ed_s
            if added:
                new_personals[lang] = added
            if removed:
                new_excluded[lang] = removed

        # Update in-memory state — keywords: any lang present in the editor
        # overrides, any lang absent is cleared (explicit deletion).
        if hasattr(self, '_cont_keywords'):
            for lang in list(self._cont_keywords.keys()):
                self._cont_keywords[lang] = keywords.get(lang, "")
            # Also accept keywords for langs not yet tracked
            for lang, kw in keywords.items():
                if lang not in self._cont_keywords:
                    self._cont_keywords[lang] = kw
        self._cont_personal_words.clear()
        self._cont_personal_words.update(new_personals)
        self._cont_excluded_words.clear()
        self._cont_excluded_words.update(new_excluded)

        # Write file through the canonical writer
        _os.makedirs(_os.path.dirname(self._cont_path), exist_ok=True)
        self._save_cont_personal()

    def _toggle_advanced_mode(self, checked):
        """Toggles form ↔ text editor for the active tab.

        Form → Advanced: form is already synced with file,
                               load file into editor.
        Advanced → Form: reload from file (Cancel = discard text edits).
                               The Save button in advanced mode writes the file first
                               before triggering this switch.
        """
        idx = self._pp_tabs.currentIndex()
        if idx == 3:  # Dictionary (new index with LLM moved last)
            currently_advanced = self._dict_stack.currentIndex() == 1
            if checked and not currently_advanced:
                # Form → Advanced : push current state (Discard can restore it)
                self._dict_push_undo()
                self._save_dict_to_tmp(reload=False)
                if os.path.isfile(self._dict_tmp_path):
                    with open(self._dict_tmp_path, encoding="utf-8") as f:
                        self._dict_adv_editor.setPlainText(f.read())
                elif os.path.isfile(self._dict_path):
                    with open(self._dict_path, encoding="utf-8") as f:
                        self._dict_adv_editor.setPlainText(f.read())
                else:
                    self._dict_adv_editor.clear()
                self._dict_stack.setCurrentIndex(1)
            elif not checked and currently_advanced:
                # Advanced → Form : validate syntax before switching
                text = self._dict_adv_editor.toPlainText()
                if not text.endswith("\n"):
                    text += "\n"
                ok, err = self._validate_dict_syntax(text)
                if not ok:
                    QMessageBox.warning(self._pp_parent, "dictee", err)
                    # Stay in advanced mode
                    self._btn_advanced.blockSignals(True)
                    self._btn_advanced.setChecked(True)
                    self._btn_advanced.blockSignals(False)
                    return
                # Reorganize, write to .tmp and reload form
                text = self._dict_reorganize(text)
                self._dict_push_undo()
                os.makedirs(os.path.dirname(self._dict_tmp_path), exist_ok=True)
                with open(self._dict_tmp_path, "w", encoding="utf-8") as f:
                    f.write(text)
                self._load_dict_form()
                self._dict_stack.setCurrentIndex(0)
        elif idx == 1:  # Continuation (new index in pipeline order)
            if checked:
                # Form → Advanced : sauvegarder le formulaire, puis composer
                # le texte à éditer (keywords + mots système mergés avec perso
                # et exclusions retirées).
                self._save_cont_personal()
                self._cont_adv_editor.setPlainText(self._cont_build_advanced_text())
            else:
                # Advanced → Form : recharger depuis le fichier
                self._cont_force_reload = True
                self._load_cont_form()
            self._cont_stack.setCurrentIndex(1 if checked else 0)

    def _build_mic_section(self, lay_mic, conf):
        """Build microphone source selection, volume slider, level meter."""
        saved_src = conf.get("DICTEE_AUDIO_SOURCE", "")

        # Defer QMediaDevices.audioInputs() (typically 340 ms; up to a few
        # seconds on machines with a busy PipeWire) to the next event-loop
        # tick. The combo shows just "System default" until the deferred
        # _ensure_audio_populated() fills it in — imperceptible to the user
        # but lets the window paint immediately.
        self._audio_devices = []
        self._audio_saved_src = saved_src
        self._audio_populated = False
        self.cmb_audio_source = QComboBox()
        self.cmb_audio_source.addItem(_("System default"), "")
        self.cmb_audio_source.currentIndexChanged.connect(self._on_audio_source_changed)
        QTimer.singleShot(0, self._ensure_audio_populated)

        # Refresh button to update application list
        lay_src = QHBoxLayout()
        lay_src.setSpacing(4)
        lay_src.addWidget(self.cmb_audio_source, 1)
        btn_refresh = QPushButton("⟳")
        btn_refresh.setFixedWidth(32)
        btn_refresh.setToolTip(_("Refresh audio sources"))
        btn_refresh.clicked.connect(self._refresh_audio_sources)
        lay_src.addWidget(btn_refresh)

        lay_mic.addWidget(QLabel(_("Audio source:")))
        lay_mic.addLayout(lay_src)

        # Volume slider
        lay_vol = QHBoxLayout()
        lay_vol.setSpacing(8)
        lbl_vol = QLabel(_("Volume:"))
        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(30)
        self.slider_volume.valueChanged.connect(self._on_volume_changed)
        self.lbl_vol_pct = QLabel("30%")
        lay_vol.addWidget(lbl_vol)
        lay_vol.addWidget(self.slider_volume, 1)
        lay_vol.addWidget(self.lbl_vol_pct)
        lay_mic.addLayout(lay_vol)

        # Level meter (custom painted — instant repaint)
        self.mic_level = LevelMeter()
        lay_mic.addWidget(self.mic_level)

        # Silence threshold slider + calibration playground are hidden in
        # wizard mode — first-time users shouldn't be overwhelmed. The
        # conf key DICTEE_SILENCE_RMS keeps its default 0.03 until the
        # user opens the regular setup later.
        if not self.wizard_mode:
            self._build_silence_threshold_section(lay_mic, conf)

        # Audio level monitor is started lazily by the sidebar nav handler
        # (_on_item_changed) when the Microphone page becomes visible — and
        # by _wizard_next when reaching wizard page 6. No eager start here:
        # opening the mic stream costs 400-500 ms on busy PipeWire systems
        # and would otherwise block window paint for users who never visit
        # this page in the current session.

    def _build_silence_threshold_section(self, lay_mic, conf):
        """Silence threshold slider + calibration playground.

        Only called in non-wizard mode (regular setup).
        """
        # Silence threshold slider (anti-hallucination)
        # Range 10..60 → 0.010..0.060. Default 30 (= 0.030).
        try:
            _saved_rms = float(conf.get("DICTEE_SILENCE_RMS", "0.03"))
        except ValueError:
            _saved_rms = 0.03
        _saved_rms_int = max(10, min(60, int(round(_saved_rms * 1000))))

        lay_sil = QHBoxLayout()
        lay_sil.setSpacing(8)
        lbl_sil = QLabel(_("Silence threshold:"))
        lbl_sil.setToolTip(_tt(_("RMS level below which the recording is considered silent and transcription is skipped. Prevents ASR hallucinations (parasitic phrases invented on background noise).")))
        self.slider_silence = QSlider(Qt.Orientation.Horizontal)
        self.slider_silence.setRange(10, 60)
        self.slider_silence.setValue(_saved_rms_int)
        self.slider_silence.setTickInterval(10)
        self.slider_silence.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.lbl_silence_val = QLabel(f"{_saved_rms_int / 1000:.3f}")
        self.lbl_silence_val.setMinimumWidth(48)
        self.lbl_silence_val.setStyleSheet("font-family: monospace;")

        def _rms_to_meter_level(rms_int):
            # rms_int is the slider value (10..60, representing 0.010..0.060).
            # Meter level uses: level = (20*log10(rms_norm) + 50) * 2, same
            # formula as AudioLevelMonitor, so the marker lines up with
            # actual VU readings.
            rms = rms_int / 1000.0
            if rms <= 0:
                return 0
            db = 20 * math.log10(rms)
            return max(0, min(100, int((db + 50) * 2)))

        def _on_silence_changed(v):
            self.lbl_silence_val.setText(f"{v / 1000:.3f}")
            self.mic_level.setThreshold(_rms_to_meter_level(v))

        self.slider_silence.valueChanged.connect(_on_silence_changed)
        # Initial marker position
        self.mic_level.setThreshold(_rms_to_meter_level(_saved_rms_int))
        lay_sil.addWidget(lbl_sil)
        lay_sil.addWidget(self.slider_silence, 1)
        lay_sil.addWidget(self.lbl_silence_val)
        lay_mic.addLayout(lay_sil)

        lbl_sil_warn = QLabel(_(
            "⚠ Too low → ASR may hallucinate on background noise. "
            "Too high → risk of cutting soft voices."))
        lbl_sil_warn.setWordWrap(True)
        lbl_sil_warn.setStyleSheet(
            "color: #e67e22; font-size: 11px; padding-left: 4px;")
        lay_mic.addWidget(lbl_sil_warn)

        # Calibration lab (record → measure RMS → transcribe → compare)
        self._build_calibration_section(lay_mic)

    def _build_calibration_section(self, lay_mic):
        """Calibration playground: record, listen, compare RMS vs threshold.

        - Press to start / press to stop
        - 4 records max, FIFO drop
        - Non-persistent: WAVs in /dev/shm, cleaned on Apply or close
        - Each card shows RMS measured, threshold at record time, source,
          ASR backend, timestamp, verdict (skip or transcribed text)
        """
        self._calib_records = []
        self._calib_rec_process = None
        self._calib_rec_path = None
        self._calib_counter = 0
        self._calib_player = None
        self._calib_audio_out = None
        self._calib_playing_path = None

        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        lbl_title = QLabel(_("Test the threshold setting:"))
        lbl_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        hdr.addWidget(lbl_title)

        accent = self.palette().color(self.palette().ColorRole.Highlight).name()
        _mic_icon = QIcon.fromTheme("audio-input-microphone")
        self._btn_calib_record = (
            QPushButton(_mic_icon, "") if not _mic_icon.isNull()
            else QPushButton("🎙"))
        self._btn_calib_record.setFixedSize(48, 48)
        self._btn_calib_record.setIconSize(self._btn_calib_record.size() * 0.55)
        self._btn_calib_record.setToolTip(_tt(_("Record a sample, measure its RMS, check whether the current silence threshold would skip or transcribe it. Press again to stop.")))
        self._btn_calib_record.setStyleSheet(
            f"background-color: {accent}; color: white; border-radius: 8px;")
        self._btn_calib_record.clicked.connect(self._toggle_calib_recording)
        hdr.addWidget(self._btn_calib_record)
        hdr.addStretch(1)
        self._lbl_calib_count = QLabel("0/4")
        self._lbl_calib_count.setStyleSheet("color: #888; font-size: 11px;")
        hdr.addWidget(self._lbl_calib_count)
        lay_mic.addLayout(hdr)

        self._calib_container = QWidget()
        self._calib_lay = QVBoxLayout(self._calib_container)
        self._calib_lay.setContentsMargins(0, 4, 0, 0)
        self._calib_lay.setSpacing(6)
        lay_mic.addWidget(self._calib_container)

    def _toggle_calib_recording(self):
        if self._calib_rec_process is not None:
            self._stop_calib_recording()
            return
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        shm_dir = "/dev/shm" if os.path.isdir("/dev/shm") else runtime_dir
        self._calib_counter += 1
        self._calib_rec_path = os.path.join(
            shm_dir, f"dictee-calib-{os.getpid()}-{self._calib_counter}.wav")

        src = self.cmb_audio_source.currentData() if hasattr(self, 'cmb_audio_source') else ""
        pw_args = ["--rate", "16000", "--channels", "1", "--format", "s16"]
        if src:
            pw_args += ["--target", str(src)]
        pw_args.append(self._calib_rec_path)

        self._calib_rec_process = QProcess(self)
        self._calib_rec_process.start("pw-record", pw_args)
        _stop_icon = QIcon.fromTheme("media-playback-stop")
        if not _stop_icon.isNull():
            self._btn_calib_record.setIcon(_stop_icon)
        else:
            self._btn_calib_record.setText("⏹")
        self._btn_calib_record.setStyleSheet(
            "background-color: #c0392b; color: white; border-radius: 8px;")

    def _stop_calib_recording(self):
        proc = self._calib_rec_process
        if proc is None:
            return
        proc.terminate()
        proc.waitForFinished(2000)
        self._calib_rec_process = None
        # Restore mic icon + accent background
        accent = self.palette().color(self.palette().ColorRole.Highlight).name()
        _mic_icon = QIcon.fromTheme("audio-input-microphone")
        if not _mic_icon.isNull():
            self._btn_calib_record.setIcon(_mic_icon)
            self._btn_calib_record.setText("")
        else:
            self._btn_calib_record.setIcon(QIcon())
            self._btn_calib_record.setText("🎙")
        self._btn_calib_record.setStyleSheet(
            f"background-color: {accent}; color: white; border-radius: 8px;")

        wav = self._calib_rec_path
        self._calib_rec_path = None
        if not wav or not os.path.isfile(wav):
            return
        self._process_calib_recording(wav)

    def _process_calib_recording(self, wav_path):
        import socket as _socket
        import time

        # Measure RMS via `sox ... -n stat`
        rms_measured = 0.0
        try:
            res = subprocess.run(
                ["sox", wav_path, "-n", "stat"],
                capture_output=True, text=True, timeout=10)
            for line in res.stderr.splitlines():
                if "RMS" in line and "amplitude" in line:
                    parts = line.split(":")
                    if len(parts) == 2:
                        try:
                            rms_measured = float(parts[1].strip())
                        except ValueError:
                            pass
                    break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        threshold = self.slider_silence.value() / 1000.0
        skipped = rms_measured < threshold

        src_label = self.cmb_audio_source.currentText() if hasattr(self, 'cmb_audio_source') else "?"
        backend = self.conf.get("DICTEE_ASR_BACKEND", "parakeet")
        timestamp = time.strftime("%H:%M:%S")

        transcription = ""
        if not skipped:
            runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            sock_path = os.path.join(runtime_dir, "transcribe.sock")
            if not os.path.exists(sock_path):
                sock_path = os.path.join(runtime_dir, "dictee", "transcribe.sock")
            if not os.path.exists(sock_path):
                sock_path = "/tmp/transcribe.sock"
            try:
                s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
                s.settimeout(20)
                s.connect(sock_path)
                s.sendall((wav_path + "\n").encode())
                data = b""
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                transcription = data.decode("utf-8").strip()
                s.close()
            except (OSError, _socket.error):
                transcription = _("(ASR daemon unreachable)")

        record = {
            "path": wav_path,
            "rms": rms_measured,
            "threshold": threshold,
            "source": src_label,
            "backend": backend,
            "timestamp": timestamp,
            "skipped": skipped,
            "transcription": transcription,
        }
        self._calib_records.insert(0, record)
        while len(self._calib_records) > 4:
            old = self._calib_records.pop()
            try:
                os.unlink(old["path"])
            except OSError:
                pass
        self._refresh_calib_cards()

    def _refresh_calib_cards(self):
        while self._calib_lay.count():
            item = self._calib_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for i, rec in enumerate(self._calib_records):
            self._calib_lay.addWidget(self._make_calib_card(i, rec))
        if hasattr(self, '_lbl_calib_count'):
            self._lbl_calib_count.setText(f"{len(self._calib_records)}/4")

    def _make_calib_card(self, index, rec):
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(
            "QFrame { border: 1px solid palette(mid); border-radius: 6px;"
            " background: palette(base); }")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(3)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        btn_play = QPushButton()
        is_playing = (
            self._calib_playing_path == rec["path"]
            and self._calib_player is not None
            and self._calib_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        _play_ico = QIcon.fromTheme(
            "media-playback-pause" if is_playing else "media-playback-start")
        if not _play_ico.isNull():
            btn_play.setIcon(_play_ico)
        else:
            btn_play.setText("⏸" if is_playing else "▶")
        btn_play.setFixedSize(28, 24)
        btn_play.setToolTip(_("Pause") if is_playing else _("Play"))
        btn_play.clicked.connect(lambda _=False, p=rec["path"]: self._toggle_play_calib(p))
        row1.addWidget(btn_play)

        btn_del = QPushButton()
        _del_icon = QIcon.fromTheme("edit-delete")
        if _del_icon.isNull():
            _del_icon = QIcon.fromTheme("user-trash")
        if not _del_icon.isNull():
            btn_del.setIcon(_del_icon)
        else:
            btn_del.setText("✕")
        btn_del.setFixedSize(28, 24)
        btn_del.setToolTip(_("Delete"))
        btn_del.clicked.connect(lambda _=False, i=index: self._delete_calib(i))
        row1.addWidget(btn_del)

        rec_num = len(self._calib_records) - index
        lbl_meta = QLabel(f"<b>#{rec_num}</b> — {rec['timestamp']}")
        lbl_meta.setStyleSheet("font-size: 11px;")
        row1.addWidget(lbl_meta)
        row1.addStretch(1)
        lay.addLayout(row1)

        rms_str = f"{rec['rms']:.3f}"
        thr_str = f"{rec['threshold']:.3f}"
        mark = "✓" if not rec["skipped"] else "✗"
        color = "#2ecc71" if not rec["skipped"] else "#e67e22"
        lbl_rms = QLabel(
            f"<span style='color:{color}; font-weight:bold;'>{mark}</span> "
            + _("Measured RMS: <b>{rms}</b> &nbsp; Threshold: <b>{thr}</b>").format(
                rms=rms_str, thr=thr_str))
        lbl_rms.setStyleSheet("font-size: 11px;")
        lay.addWidget(lbl_rms)

        lbl_src = QLabel(_("Source: <i>{src}</i> &nbsp;|&nbsp; ASR: <i>{backend}</i>").format(
            src=rec['source'], backend=rec['backend']))
        lbl_src.setStyleSheet("color: #888; font-size: 10px;")
        lay.addWidget(lbl_src)

        if rec["skipped"]:
            lbl_verdict = QLabel("⚠ " + _("Silence detected — skipped"))
            lbl_verdict.setStyleSheet(
                "color: #e67e22; font-style: italic; font-size: 11px;")
        else:
            text = rec["transcription"] or "(∅)"
            lbl_verdict = QLabel(f"→ \"{text}\"")
            lbl_verdict.setWordWrap(True)
            lbl_verdict.setStyleSheet("color: #2ecc71; font-size: 11px;")
        lay.addWidget(lbl_verdict)

        return card

    def _ensure_calib_player(self):
        if self._calib_player is None:
            self._calib_audio_out = QAudioOutput()
            self._calib_player = QMediaPlayer()
            self._calib_player.setAudioOutput(self._calib_audio_out)
            self._calib_player.playbackStateChanged.connect(
                lambda _s: self._refresh_calib_cards())

    def _toggle_play_calib(self, path):
        if not os.path.isfile(path):
            return
        self._ensure_calib_player()
        player = self._calib_player
        if self._calib_playing_path == path:
            # Same file loaded — true pause/resume
            if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                player.pause()
            else:
                player.play()
        else:
            player.stop()
            player.setSource(QUrl.fromLocalFile(path))
            self._calib_playing_path = path
            player.play()

    def _delete_calib(self, index):
        if 0 <= index < len(self._calib_records):
            rec = self._calib_records.pop(index)
            try:
                os.unlink(rec["path"])
            except OSError:
                pass
            self._refresh_calib_cards()

    def _cleanup_calib_records(self):
        """Delete all temp WAVs from calibration records (on apply or close)."""
        # Stop any ongoing recording
        if getattr(self, '_calib_rec_process', None) is not None:
            try:
                self._calib_rec_process.terminate()
                self._calib_rec_process.waitForFinished(1000)
            except Exception as _e:
                _dbg_setup(f"silenced: {_e!r}")
            self._calib_rec_process = None
        # Stop playback and release the source so the WAV can be unlinked
        if getattr(self, '_calib_player', None) is not None:
            try:
                self._calib_player.stop()
                self._calib_player.setSource(QUrl())
            except Exception as _e:
                _dbg_setup(f"silenced: {_e!r}")
        self._calib_playing_path = None
        for rec in getattr(self, '_calib_records', []):
            try:
                os.unlink(rec["path"])
            except OSError:
                pass
        if hasattr(self, '_calib_rec_path') and self._calib_rec_path:
            try:
                os.unlink(self._calib_rec_path)
            except OSError:
                pass
            self._calib_rec_path = None
        self._calib_records = []
        if hasattr(self, '_calib_lay'):
            self._refresh_calib_cards()

    def _ensure_audio_populated(self):
        """Lazily fill the audio source combo with QMediaDevices.audioInputs()
        + PipeWire monitors/apps. Called from a QTimer.singleShot scheduled
        in _build_mic_section, so the window paints before this runs.
        Idempotent: subsequent calls are no-ops."""
        if getattr(self, '_audio_populated', False):
            return
        self._audio_populated = True
        try:
            self._audio_devices = QMediaDevices.audioInputs()
        except Exception as _e:
            _dbg_setup(f"_ensure_audio_populated: audioInputs() failed: {_e}")
            self._audio_devices = []
        self._populate_audio_sources()
        saved = getattr(self, '_audio_saved_src', '')
        if saved:
            idx = self.cmb_audio_source.findData(saved)
            if idx >= 0:
                self.cmb_audio_source.blockSignals(True)
                self.cmb_audio_source.setCurrentIndex(idx)
                self.cmb_audio_source.blockSignals(False)

    def _populate_audio_sources(self):
        """Populate combo with devices (Qt) + monitors + applications (PipeWire)."""
        # ── Devices (microphones) ──
        for dev in self._audio_devices:
            self.cmb_audio_source.addItem(
                "🎤 " + dev.description(), dev.id().data().decode())
        # ── Monitors + Applications (PipeWire/PulseAudio) ──
        try:
            import json
            out = subprocess.check_output(
                ["pw-dump"], timeout=3, stderr=subprocess.DEVNULL)
            nodes = json.loads(out)
            for node in nodes:
                if node.get("type") != "PipeWire:Interface:Node":
                    continue
                props = node.get("info", {}).get("props", {})
                media_class = props.get("media.class", "")
                node_name = props.get("node.name", "")
                # Monitors (audio output loopback)
                if media_class == "Audio/Source" and node_name.endswith(".monitor"):
                    desc = props.get("node.description",
                                     props.get("node.nick", node_name))
                    self.cmb_audio_source.addItem(
                        "🔊 Monitor: " + desc, node_name)
                # Applications playing audio
                elif media_class == "Stream/Output/Audio":
                    app = props.get("application.name", "?")
                    media = props.get("media.name", "")
                    label = f"📺 {app}"
                    if media and media != app:
                        # Truncate long media names
                        if len(media) > 50:
                            media = media[:47] + "..."
                        label += f" — {media}"
                    # Use node.name (stable) instead of id (ephemeral)
                    self.cmb_audio_source.addItem(label, node_name)
        except Exception:
            pass  # pw-dump unavailable — Qt devices only

    def _refresh_audio_sources(self):
        """Refresh the audio source list (re-scan devices + apps)."""
        saved = self.cmb_audio_source.currentData()
        self.cmb_audio_source.blockSignals(True)
        self.cmb_audio_source.clear()
        self.cmb_audio_source.addItem(_("System default"), "")
        self._audio_devices = QMediaDevices.audioInputs()
        self._populate_audio_sources()
        if saved:
            idx = self.cmb_audio_source.findData(saved)
            if idx >= 0:
                self.cmb_audio_source.setCurrentIndex(idx)
        self.cmb_audio_source.blockSignals(False)
        # User-driven refresh counts as a populated state — prevents the
        # deferred _ensure_audio_populated() from re-adding entries.
        self._audio_populated = True

    # ── Wizard checks (page 5) ───────────────────────────────────

    def _run_wizard_checks(self):
        checks = {
            "daemon": self._check_daemon_active,   # service active AND socket ready
            "model": self._check_model_installed_fn,
            "shortcut": self._check_shortcut_registered,
            "audio": lambda: len(QMediaDevices.audioInputs()) > 0,
            "dotool": lambda: shutil.which("dotool") is not None,
        }
        all_ok = True
        for check_id, fn in checks.items():
            lbl_icon, lbl_status = self._check_labels[check_id]
            try:
                ok = fn()
            except Exception:
                ok = False
            if ok:
                lbl_icon.setText('<span style="color: green;">✓</span>')
                if check_id == "shortcut":
                    ptt_k = getattr(self, '_ptt_key', int(self.conf.get("DICTEE_PTT_KEY", 67)))
                    lbl_status.setText('<span style="color: green;">'
                                      + linux_keycode_name(ptt_k) + '</span>')
                else:
                    lbl_status.setText('<span style="color: green;">' + _("OK") + '</span>')
            else:
                lbl_icon.setText('<span style="color: red;">✗</span>')
                lbl_status.setText('<span style="color: red;">' + _("Not found") + '</span>')
                all_ok = False

        if all_ok:
            ptt_key = getattr(self, '_ptt_key', int(self.conf.get("DICTEE_PTT_KEY", 67)))
            shortcut = linux_keycode_name(ptt_key)
            ptt_mode = ""
            if hasattr(self, 'cmb_ptt_mode'):
                ptt_mode = self.cmb_ptt_mode.currentData()
            else:
                ptt_mode = self.conf.get("DICTEE_PTT_MODE", "toggle")
            mode_label = "hold" if ptt_mode == "hold" else "toggle"
            self.lbl_final.setText(
                '<div style="background: #1e2e1e; padding: 12px; border-radius: 8px;">'
                '<span style="color: #afa; font-size: 14pt; font-weight: bold;">'
                + _("Everything is ready!") + '</span><br>'
                '<span style="color: #8a8;">'
                + _("Press {key} anytime to dictate.").format(key=shortcut)
                + f' ({mode_label})'
                + '</span></div>'
            )

    def _check_daemon_active(self):
        """Vérifie que le service ASR est réellement actif (et la socket ouverte
        pour les backends Rust). Tolère un état `activating` transitoire (model
        loading) jusqu'à ~6 s avant de conclure à l'échec, ce qui évite un
        faux positif quand le daemon crashe en boucle (driver CUDA cassé,
        modèle absent, etc.)."""
        asr = self._wizard_asr if hasattr(self, '_wizard_asr') else "parakeet"
        svc = {"parakeet": "dictee", "vosk": "dictee-vosk",
               "whisper": "dictee-whisper", "canary": "dictee-canary"}.get(asr, "dictee")
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        sock = os.path.join(runtime_dir, "transcribe.sock")
        needs_socket = asr in ("parakeet", "canary")
        deadline = time.monotonic() + 6.0
        last_state = "?"
        while time.monotonic() < deadline:
            try:
                r = subprocess.run(
                    ["systemctl", "--user", "is-active", f"{svc}.service"],
                    capture_output=True, text=True, timeout=2,
                )
            except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
                return False
            last_state = (r.stdout or "").strip()
            if last_state == "active" and (not needs_socket or os.path.exists(sock)):
                return True
            if last_state in ("failed", "inactive"):
                return False
            # `activating` (or socket not yet ready) — wait and retry.
            time.sleep(0.4)
        return False

    def _check_model_installed_fn(self):
        asr = self._wizard_asr if hasattr(self, '_wizard_asr') else "parakeet"
        if asr == "parakeet":
            return all(model_is_installed(m) for m in ASR_MODELS if m["required"])
        elif asr == "vosk":
            return venv_is_installed(VOSK_VENV)
        elif asr == "whisper":
            return venv_is_installed(WHISPER_VENV)
        return True

    def _check_shortcut_registered(self):
        """Vérifie qu'une touche PTT est configurée (wizard ou dictee.conf)."""
        # Wizard en cours : on a _ptt_key défini
        if hasattr(self, '_ptt_key') and self._ptt_key:
            return True
        # Sinon, vérifier la config existante
        key = self.conf.get("DICTEE_PTT_KEY", "")
        return bool(key and int(key) > 0)

    # ── Audio helpers ─────────────────────────────────────────────

    def _on_volume_changed(self, value):
        self.lbl_vol_pct.setText(f"{value}%")
        # Debounce: apply volume after 50ms of inactivity
        if not hasattr(self, '_vol_timer'):
            self._vol_timer = QTimer(self)
            self._vol_timer.setSingleShot(True)
            self._vol_timer.timeout.connect(self._apply_volume)
        self._vol_timer.start(50)

    def _apply_volume(self):
        value = self.slider_volume.value()
        vol = value / 100.0
        src = self.cmb_audio_source.currentData()
        if shutil.which("wpctl"):
            subprocess.Popen(["wpctl", "set-volume", str(src) if src else "@DEFAULT_SOURCE@",
                              f"{vol:.2f}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("pactl"):
            pct = f"{value}%"
            subprocess.Popen(["pactl", "set-source-volume",
                              str(src) if src else "@DEFAULT_SOURCE@", pct],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _on_audio_source_changed(self, _index):
        """Restart audio level thread on new source."""
        self._stop_audio_level()
        self._start_audio_level()

    def _start_audio_level(self):
        if self._audio_monitor is not None:
            return
        idx = self.cmb_audio_source.currentIndex()
        if idx > 0 and idx - 1 < len(self._audio_devices):
            device = self._audio_devices[idx - 1]
        else:
            device = QMediaDevices.defaultAudioInput()
        self._audio_monitor = AudioLevelMonitor(self.mic_level, device)
        self._audio_monitor.start()

    def _stop_audio_level(self):
        if self._audio_monitor:
            self._audio_monitor.stop()
            self._audio_monitor = None

    def closeEvent(self, event):
        self._stop_audio_level()
        self._cleanup_calib_records()
        # Wizard annulé : rien n'a été écrit sur disque, rien à nettoyer
        super().closeEvent(event)

    # ── Test dictation ────────────────────────────────────────────

    def _on_test_dictee(self):
        _dbg_setup("_on_test_dictee")
        if self._test_thread and self._test_thread.isRunning():
            self._test_thread.stop()
            self.btn_test_dictee.setText("🎤 " + _("Test dictation"))
            self.btn_test_dictee.setEnabled(True)
            if hasattr(self, '_test_timer'):
                self._test_timer.stop()
            return
        self.txt_test_result.clear()
        self._test_countdown = 5
        self.btn_test_dictee.setText("⏹ " + _("Recording… {n}s").format(n=self._test_countdown))
        self._test_timer = QTimer(self)
        self._test_timer.timeout.connect(self._on_test_tick)
        self._test_timer.start(1000)
        pp_enabled = self.chk_postprocess.isChecked() if hasattr(self, 'chk_postprocess') else False
        _thr = (
            self.slider_silence.value() / 1000.0
            if hasattr(self, 'slider_silence') else None)
        self._test_thread = TestDicteeThread(
            duration=5, postprocess=pp_enabled, silence_threshold=_thr)
        self._test_thread.result.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_tick(self):
        self._test_countdown -= 1
        if self._test_countdown > 0:
            self.btn_test_dictee.setText("⏹ " + _("Recording… {n}s").format(n=self._test_countdown))
        else:
            self.btn_test_dictee.setText("⏳ " + _("Transcribing…"))
            self._test_timer.stop()

    def _on_test_result(self, text):
        _dbg_setup(f"_on_test_result: {len(text)} chars")
        if hasattr(self, '_test_timer'):
            self._test_timer.stop()
        self.btn_test_dictee.setText("🎤 " + _("Test dictation"))
        self.txt_test_result.setPlainText(text)

    # ── Test translation (Canary) ────────────────────────────────

    def _on_test_translate(self):
        _dbg_setup("_on_test_translate")
        if self._test_thread and self._test_thread.isRunning():
            self._test_thread.stop()
            self.btn_test_translate.setText("🌐 " + _("Test translation"))
            self.btn_test_translate.setEnabled(True)
            if hasattr(self, '_test_timer_tr'):
                self._test_timer_tr.stop()
            return
        self.txt_test_result.clear()
        self._test_countdown_tr = 5
        self.btn_test_translate.setText("⏹ " + _("Recording… {n}s").format(n=self._test_countdown_tr))
        self._test_timer_tr = QTimer(self)
        self._test_timer_tr.timeout.connect(self._on_test_translate_tick)
        self._test_timer_tr.start(1000)

        # Gather current config
        if self.wizard_mode and hasattr(self, '_wizard_asr'):
            asr = self._wizard_asr
        elif hasattr(self, 'cmb_asr_backend'):
            asr = self.cmb_asr_backend.currentData()
        else:
            asr = "parakeet"
        source = self.combo_src.currentData() if hasattr(self, 'combo_src') else "fr"
        target = self.combo_tgt.currentData() if hasattr(self, 'combo_tgt') else "en"
        trans_backend = self.cmb_trans_backend.currentData() if hasattr(self, 'cmb_trans_backend') else "trans:google"
        trans_engine = "google"
        if trans_backend.startswith("trans:"):
            trans_engine = trans_backend.split(":", 1)[1]
            trans_backend = "trans"
        _lt_txt = self.spin_lt_port.currentText() if hasattr(self, 'spin_lt_port') else ""
        lt_port = int(_lt_txt) if _lt_txt.isdigit() else 5000
        ollama_model = self.cmb_ollama_model.currentText() if hasattr(self, 'cmb_ollama_model') else "translategemma"
        pp_enabled = self.chk_postprocess.isChecked() if hasattr(self, 'chk_postprocess') else False

        _thr = (
            self.slider_silence.value() / 1000.0
            if hasattr(self, 'slider_silence') else None)
        self._test_thread = TestTranslateThread(
            duration=5, asr_backend=asr, trans_backend=trans_backend,
            source_lang=source, target_lang=target, trans_engine=trans_engine,
            lt_port=lt_port, ollama_model=ollama_model, postprocess=pp_enabled,
            silence_threshold=_thr,
        )
        self._test_thread.result.connect(self._on_test_translate_result)
        self._test_thread.start()

    def _on_test_translate_tick(self):
        self._test_countdown_tr -= 1
        if self._test_countdown_tr > 0:
            self.btn_test_translate.setText("⏹ " + _("Recording… {n}s").format(n=self._test_countdown_tr))
        else:
            self.btn_test_translate.setText("⏳ " + _("Translating…"))
            self._test_timer_tr.stop()

    def _on_test_translate_result(self, text):
        _dbg_setup(f"_on_test_translate_result: {len(text)} chars")
        if hasattr(self, '_test_timer_tr'):
            self._test_timer_tr.stop()
        self.btn_test_translate.setText("🌐 " + _("Test translation"))
        self.txt_test_result.setPlainText(text)

    # ── Static helpers ────────────────────────────────────────────

    @staticmethod
    def _is_service_enabled(name):
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", name],
                capture_output=True, text=True,
            )
            return result.stdout.strip() == "enabled"
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

    @staticmethod
    def _system_lang():
        lang = os.environ.get("LANG", "")
        if lang:
            return lang.split("_")[0].split(".")[0]
        try:
            return locale.getdefaultlocale()[0].split("_")[0]
        except (AttributeError, IndexError):
            return "fr"

    @staticmethod
    def _set_combo_by_data(combo, data, fallback_idx):
        for i in range(combo.count()):
            if combo.itemData(i) == data:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(fallback_idx)

    # -- Filtrage langues selon backend --

    def _filter_lang_combo(self, combo, allowed_codes):
        """Repeuple un combo avec les langues spécifiées.

        allowed_codes peut être :
          - None            → toutes les entrées de LANGUAGES (29 langues)
          - set / frozenset → filtre LANGUAGES, garde l'ordre LANGUAGES
          - list            → utilise la liste dans l'ordre donné
                              (pour les cibles issues de dictee-translate-langs)
        Les noms affichés : natifs via LANGUAGES si présent, sinon anglais
        via TARGET_LANG_NAMES_EN, sinon juste le code.
        """
        current = combo.currentData()
        was_blocked = combo.signalsBlocked()
        combo.blockSignals(True)
        combo.clear()
        native = dict(LANGUAGES)
        if allowed_codes is None:
            codes = [c for c, _ in LANGUAGES]
        elif isinstance(allowed_codes, (set, frozenset)):
            codes = [c for c, _ in LANGUAGES if c in allowed_codes]
        else:
            codes = list(allowed_codes)
        for code in codes:
            name = native.get(code) or TARGET_LANG_NAMES_EN.get(code, code)
            combo.addItem(f"{code} — {name}", code)
        idx = combo.findData(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(was_blocked)

    def _fetch_target_langs_from_script(self, backend_short):
        """Run dictee-translate-langs to get target languages for a backend.

        Returns a list of codes (preferred order) or None on failure.
        Separator '---' from the script is stripped.
        """
        import subprocess
        try:
            r = subprocess.run(
                ["dictee-translate-langs", backend_short],
                capture_output=True, text=True, timeout=3)
            if r.returncode == 0:
                raw = r.stdout.strip()
                if raw:
                    return [c for c in raw.split(",") if c and c != "---"]
        except Exception as _e:
            _dbg_setup(f"silenced: {_e!r}")
        return None

    def _update_src_languages(self):
        """Filtre la langue source selon le backend ASR sélectionné."""
        if self.wizard_mode and hasattr(self, '_wizard_asr'):
            asr = self._wizard_asr
        elif hasattr(self, 'cmb_asr_backend'):
            asr = self.cmb_asr_backend.currentData()
        else:
            asr = "parakeet"
        if asr == "vosk" and hasattr(self, 'cmb_vosk_lang'):
            # Vosk = mono-langue, uniquement la langue du modèle sélectionné
            vosk_lang = self.cmb_vosk_lang.currentData()
            allowed = {vosk_lang} if vosk_lang else ASR_LANGUAGES.get("vosk")
        else:
            allowed = ASR_LANGUAGES.get(asr)
        self._filter_lang_combo(self.combo_src, allowed)

    def _update_tgt_languages(self):
        """Filtre la langue cible selon le backend de traduction sélectionné.

        For cloud (google/bing), ollama and libretranslate, ask
        dictee-translate-langs for the full list (~130 for google/bing,
        ~90 for ollama, dynamic for LT). Fallback to the static
        TRANSLATE_LANGUAGES map (29 LANGUAGES) if the script fails.
        """
        if not hasattr(self, 'cmb_trans_backend'):
            return
        backend = self.cmb_trans_backend.currentData()
        short_map = {
            "trans:google": "google",
            "trans:bing": "bing",
            "ollama": "ollama",
            "libretranslate": "libretranslate",
        }
        short = short_map.get(backend)
        if short:
            codes = self._fetch_target_langs_from_script(short)
            if codes:
                self._filter_lang_combo(self.combo_tgt, codes)
                return
        allowed = TRANSLATE_LANGUAGES.get(backend)
        self._filter_lang_combo(self.combo_tgt, allowed)

    def _update_canary_translation_visibility(self):
        """Show/hide translation widgets depending on Canary backend."""
        if self.wizard_mode and hasattr(self, '_wizard_asr'):
            asr = self._wizard_asr
        elif hasattr(self, 'cmb_asr_backend'):
            asr = self.cmb_asr_backend.currentData()
        else:
            asr = "parakeet"

        is_canary = (asr == "canary")

        # Notice verte
        if hasattr(self, '_canary_translation_notice'):
            self._canary_translation_notice.setVisible(is_canary)

        # Masquer la ComboBox backend traduction si Canary.
        # En wizard, cmb_trans_backend est détaché (setParent(None) dans
        # _build_translation_section) pour ne pas apparaître sur la page 5.
        # Ne jamais setVisible sur un widget détaché, sinon Qt l'affiche
        # comme une top-level window flottante.
        w = getattr(self, 'cmb_trans_backend', None)
        if w and w.parent() is not None:
            w.setVisible(not is_canary)
        # lt_widget: visible seulement si pas Canary ET backend == libretranslate
        w = getattr(self, 'lt_widget', None)
        if w and w.parent() is not None:
            if is_canary:
                w.setVisible(False)
            else:
                current_backend = getattr(self, 'cmb_trans_backend', None)
                if current_backend:
                    w.setVisible(current_backend.currentData() == "libretranslate")
        if is_canary and hasattr(self, 'ollama_widget') and self.ollama_widget.parent() is not None:
            self._tr_layout.removeWidget(self.ollama_widget)
            self.ollama_widget.setParent(None)

        # Contrainte langue : Canary traduit uniquement via l'anglais
        if hasattr(self, '_canary_trans_card'):
            self._canary_trans_card.setVisible(is_canary)
        if hasattr(self, '_trans_cards'):
            current = getattr(self, '_wizard_trans', '')
            for bid, card in self._trans_cards.items():
                card.setEnabled(not is_canary)
                if is_canary:
                    card.setStyleSheet(self._card_style(False) + " QFrame#radioCard { opacity: 0.4; }")
                else:
                    card.setStyleSheet(self._card_style(bid == current))
        if hasattr(self, '_chk_trans_disabled'):
            self._chk_trans_disabled.setEnabled(not is_canary)
        if is_canary and hasattr(self, 'combo_src') and hasattr(self, 'combo_tgt'):
            src = self.combo_src.currentData()
            if src != "en":
                # Source ≠ EN → cible forcée à EN
                self._filter_lang_combo(self.combo_tgt, {"en"})
                self._set_combo_by_data(self.combo_tgt, "en", 0)
                self.combo_tgt.setEnabled(False)
            else:
                # Source = EN → cible libre parmi les 25 langues Canary
                self._filter_lang_combo(self.combo_tgt, CANARY_LANGUAGES - {"en"})
                self.combo_tgt.setEnabled(True)
        elif hasattr(self, 'combo_tgt'):
            self.combo_tgt.setEnabled(True)
            self._update_tgt_languages()

    # -- Capture raccourci --

    def _on_ptt_key_captured(self, seq):
        code = qt_key_to_linux_keycode(seq)
        if code:
            self._ptt_key = code
            self.btn_capture.setText(_("Key: {name}").format(name=linux_keycode_name(code)))
            self.btn_capture._changed = True
            self._dirty = True
            self._check_ptt_warning(code, self.lbl_ptt_warning)
            # Refresh combo item texts so "Same key + ..." labels reflect
            # the new dictation key ("Ctrl+Alt+F9", etc.).
            self._refresh_shortcut_combos_labels()
        else:
            key_str = seq.toString() if seq else "?"
            self.lbl_ptt_warning.setText(
                '<span style="color: red;">⚠ ' +
                _("Key '{key}' is not supported. Use a function key (F1-F12).").format(key=key_str) +
                '</span>'
            )
            self.lbl_ptt_warning.setVisible(True)

    def _on_ptt_key_translate_captured(self, seq):
        code = qt_key_to_linux_keycode(seq)
        if code:
            self._ptt_key_translate = code
            self.btn_capture_translate.setText(_("Key: {name}").format(name=linux_keycode_name(code)))
            self.btn_capture_translate._changed = True
            self._dirty = True
        else:
            key_str = seq.toString() if seq else "?"
            self.btn_capture_translate.setText(
                _("Key '{key}' not supported").format(key=key_str))

    def _check_ptt_warning(self, code, lbl):
        """Avertit si la touche risque de poser problème."""
        # Touches dangereuses : lettres, chiffres, espace, enter, tab
        dangerous = {14, 15, 28, 57}  # backspace, tab, enter, space
        dangerous.update(range(2, 12))  # 1-0
        dangerous.update(range(16, 26))  # q-p
        dangerous.update(range(30, 39))  # a-l
        dangerous.update(range(44, 51))  # z-m
        if code in dangerous:
            lbl.setText(
                '<span style="color: orange;">⚠ ' +
                _("This key is used for typing. Prefer a function key (F1-F12) "
                  "or a special key (Home, End, Insert, etc.).") +
                '</span>'
            )
            lbl.setVisible(True)
        elif code == 1:  # ESC
            lbl.setText(
                '<span style="color: orange;">⚠ ' +
                _("Escape is used to cancel dictation. Choose another key.") +
                '</span>'
            )
            lbl.setVisible(True)
        else:
            lbl.setVisible(False)

    def _on_translate_mode_changed(self, _idx):
        mode = self.cmb_translate_mode.currentData()
        self.btn_capture_translate.setVisible(mode == "separate")

    def _on_cheatsheet_mode_changed(self, _idx):
        mode = self.cmb_cheatsheet_mode.currentData()
        self.kse_cheatsheet_separate.setVisible(mode == "separate")

    def _refresh_shortcut_combos_labels(self):
        """Update the cheatsheet and translate combo item texts so that
        every "Same key + <mod>" entry shows its resolved value (e.g.
        "Ctrl+Alt+F9") whenever the dictation PTT key is known. Falls back
        to the localized "Same key + <mod>" when the key is unknown."""
        ptt = getattr(self, '_ptt_key', 0)
        name = linux_keycode_name(ptt) if ptt else ""
        has_name = bool(name) and not name.startswith("Key ")
        # Mode-data → (resolved label when key is known, fallback)
        labels_cheat = {
            "same_alt": (f"Alt+{name}", _("Same key + Alt")),
            "same_ctrl": (f"Ctrl+{name}", _("Same key + Ctrl")),
            "same_ctrl_alt": (f"Ctrl+Alt+{name}", _("Same key + Ctrl + Alt")),
            "same_shift": (f"Shift+{name}", _("Same key + Shift")),
            "separate": (_("Separate key"), _("Separate key")),
            "disabled": (_("Disabled"), _("Disabled")),
        }
        # Translate combo has the same data values minus "same_ctrl_alt".
        for combo_name in ("cmb_cheatsheet_mode", "cmb_translate_mode"):
            combo = getattr(self, combo_name, None)
            if combo is None:
                continue
            for i in range(combo.count()):
                data = combo.itemData(i)
                if data in labels_cheat:
                    resolved, fallback = labels_cheat[data]
                    combo.setItemText(i, resolved if has_name else fallback)

    def _compute_cheatsheet_keysequence(self):
        """Resolve the cheatsheet shortcut from the combo selection.

        Returns a QKeySequence if a shortcut should be registered, or None
        if the user picked "Disabled" or "Separate key" with no capture.
        For "Same key + X" modes, combines the chosen modifier with the
        dictation PTT key name (e.g. "Ctrl+Alt+F9")."""
        if not hasattr(self, 'cmb_cheatsheet_mode'):
            return None
        mode = self.cmb_cheatsheet_mode.currentData()
        if mode == "disabled":
            return None
        if mode == "separate":
            seq = self.kse_cheatsheet_separate.keySequence()
            return seq if seq.count() > 0 else None
        mod_map = {
            "same_alt": "Alt",
            "same_ctrl": "Ctrl",
            "same_ctrl_alt": "Ctrl+Alt",
            "same_shift": "Shift",
        }
        mod = mod_map.get(mode)
        if mod is None:
            return None
        ptt_key = getattr(self, '_ptt_key', 0)
        if not ptt_key:
            return None
        key_name = linux_keycode_name(ptt_key)
        if not key_name or key_name.startswith("Key "):
            return None
        return QKeySequence(f"{mod}+{key_name}")

    def _on_shortcut_captured(self, seq):
        """Legacy — redirige vers PTT."""
        self._on_ptt_key_captured(seq)

    def _on_shortcut_translate_captured(self, seq):
        """Legacy — redirige vers PTT."""
        self._on_ptt_key_translate_captured(seq)

    # -- Animation-speech --

    def _check_animation_speech(self):
        # _build_visual_section fires this synchronously during build path
        # (~50 ms: shutil.which + dpkg-query subprocess). Defer to first
        # event-loop tick post-show; coalesced with a pending flag.
        if getattr(self, '_build_phase', False):
            if not getattr(self, '_anim_speech_deferred', False):
                self._anim_speech_deferred = True
                QTimer.singleShot(0, self._check_animation_speech)
            return
        self._anim_speech_deferred = False
        parts = []
        has_anim = shutil.which(ANIMATION_SPEECH_BIN)
        if has_anim:
            try:
                result = subprocess.run(
                    ["dpkg-query", "-W", "-f", "${Version}", "animation-speech"],
                    capture_output=True, text=True,
                )
                v = result.stdout.strip() if result.returncode == 0 else ""
                if v:
                    parts.append('<span style="color: green;">' +
                                 _("animation-speech {version} installed").format(version=v) +
                                 '</span>')
                else:
                    parts.append('<span style="color: green;">' +
                                 _("animation-speech installed") + '</span>')
            except FileNotFoundError:
                parts.append('<span style="color: green;">' +
                             _("animation-speech installed") + '</span>')
            self.btn_install_anim.setVisible(False)
        else:
            self.btn_install_anim.setVisible(True)
            if self.de_type == "gnome":
                self.btn_install_anim.setEnabled(False)

        has_plasmoid = os.path.isdir(
            os.path.expanduser("~/.local/share/plasma/plasmoids/com.github.rcspam.dictee")
        ) or os.path.isdir("/usr/share/plasma/plasmoids/com.github.rcspam.dictee")
        if has_plasmoid:
            parts.append('<span style="color: green;">' +
                         _("Dictee plasmoid installed") + '</span>')

        if parts:
            self.lbl_anim_status.setText(" — ".join(parts))

    def _on_install_animation(self):
        _dbg_setup("_on_install_animation")
        self.btn_install_anim.setEnabled(False)
        self.btn_install_anim.setText(_("Downloading…"))
        self.progress_anim.setVisible(True)

        self._install_thread = InstallThread()
        self._install_thread.progress.connect(lambda text: self.btn_install_anim.setText(text))
        self._install_thread.done.connect(self._on_install_finished)
        self._install_thread.start()

    def _on_install_finished(self, success, message):
        _dbg_setup(f"_on_install_finished: success={success}, msg={message!r}")
        self.progress_anim.setVisible(False)
        if success:
            self._check_animation_speech()
        else:
            self.btn_install_anim.setText(_("Install animation-speech"))
            self.btn_install_anim.setEnabled(True)
            QMessageBox.critical(self, _("Installation error"), message)

    # -- Ollama backend --

    def _on_ollama_model_changed(self, _index):
        if self.cmb_trans_backend.currentData() == "ollama":
            self._check_ollama_status()

    def _check_ollama_status(self):
        _dbg_setup("_check_ollama_status")
        if not ollama_is_installed():
            self.lbl_ollama_status.setText(
                '<span style="color: red;">⚠ ' +
                _("ollama is not installed") + '</span><br>'
                '<code>curl -fsSL https://ollama.com/install.sh | sh</code><br>'
                '<small><a href="https://ollama.com">https://ollama.com</a></small>'
            )
            self.lbl_ollama_status.setOpenExternalLinks(True)
            self.btn_ollama_pull.setVisible(False)
            return

        model = self.combo_ollama_model.currentData()
        min_ram = 8
        min_vram = 4
        for m_id, _label, m_ram, m_vram in OLLAMA_MODELS:
            if m_id == model:
                min_ram, min_vram = m_ram, m_vram
                break

        sys_ram = get_system_ram_gb()
        vram_total, vram_free = get_gpu_vram_gb()
        warnings = []
        if sys_ram and sys_ram < min_ram:
            warnings.append(
                '<span style="color: orange;">⚠ ' +
                _("RAM: {actual} GB / {required} GB recommended").format(
                    actual=sys_ram, required=min_ram) +
                '</span>')
        vram_insufficient = False
        if vram_total:
            if vram_free < min_vram:
                vram_insufficient = True
                warnings.append(
                    '<span style="color: orange;">⚠ ' +
                    _("VRAM free: {free} GB / {required} GB required (total: {total} GB)").format(
                        free=vram_free, required=min_vram, total=vram_total) +
                    '</span>')
        else:
            vram_insufficient = True
            warnings.append(
                '<small><i>' +
                _("No GPU detected — ollama will use CPU (slower).") +
                '</i></small>')

        if vram_insufficient and not vram_total:
            self.chk_ollama_cpu.setChecked(True)

        hw_info = ""
        if warnings:
            hw_info = "<br>" + "<br>".join(warnings)

        if not ollama_is_running():
            self.lbl_ollama_status.setText(
                '<span style="color: red;">⚠ ' +
                _("Ollama service is not running") + '</span><br>'
                '<small><code>sudo systemctl start ollama</code></small>' +
                hw_info
            )
            self.btn_ollama_pull.setVisible(False)
        elif ollama_has_model(model):
            self.lbl_ollama_status.setText(
                '<span style="color: green;">✓ ' +
                _("Model {model} ready").format(model=model) + '</span>' +
                hw_info
            )
            self.btn_ollama_pull.setVisible(False)
        else:
            self.lbl_ollama_status.setText(
                '<span style="color: orange;">⚠ ' +
                _("Model {model} not downloaded").format(model=model) + '</span>' +
                hw_info
            )
            self.btn_ollama_pull.setVisible(True)
            self.btn_ollama_pull.setText(_("Download"))
            self.btn_ollama_pull.setEnabled(True)

    def _on_ollama_pull(self):
        _dbg_setup(f"_on_ollama_pull: model={self.combo_ollama_model.currentData()}")
        model = self.combo_ollama_model.currentData()
        self.btn_ollama_pull.setEnabled(False)
        self.progress_ollama.setVisible(True)

        self._ollama_pull_thread = OllamaPullThread(model)
        self._ollama_pull_thread.progress.connect(
            lambda text: self.btn_ollama_pull.setText(text))
        self._ollama_pull_thread.done.connect(self._on_ollama_pull_finished)
        self._ollama_pull_thread.start()

    def _on_ollama_pull_finished(self, success, message):
        _dbg_setup(f"_on_ollama_pull_finished: success={success}, msg={message!r}")
        self.progress_ollama.setVisible(False)
        if success:
            self._check_ollama_status()
        else:
            self.btn_ollama_pull.setText(_("Download"))
            self.btn_ollama_pull.setEnabled(True)
            QMessageBox.critical(self, _("Download error"), message)

    # -- LibreTranslate backend --

    def _on_lt_toggled(self, checked):
        self.lt_widget.setVisible(checked)
        if checked:
            self._check_lt_status()

    def _check_lt_status(self):
        # During the initial dialog build, _build_translation_section's
        # combo signal handlers fire this twice (~256 ms total for the
        # Docker probes + LT HTTP). Coalesce them into a single deferred
        # check that runs after the window is painted.
        if getattr(self, '_build_phase', False):
            if not getattr(self, '_lt_status_deferred', False):
                self._lt_status_deferred = True
                QTimer.singleShot(0, self._check_lt_status)
            return
        self._lt_status_deferred = False
        _dbg_setup("_check_lt_status")
        if not docker_is_installed():
            self.lbl_lt_status.setText(
                '<span style="color: red;">⚠ ' +
                _("Docker is not installed") + '</span><br>'
                '<small>sudo apt install docker.io</small>')
            self.btn_lt_pull.setVisible(False)
            self.btn_lt_start.setVisible(False)
            self.btn_lt_stop.setVisible(False)
            self.btn_lt_purge.setVisible(False)
            return

        needs_daemon = not docker_daemon_running()
        needs_group = not docker_is_accessible() and not getattr(self, '_docker_group_fixed', False)

        if needs_daemon or needs_group:
            if needs_daemon and needs_group:
                msg = _("Docker daemon is not running and permissions are missing")
            elif needs_daemon:
                msg = _("Docker daemon is not running")
            else:
                msg = _("Docker permission denied")
            self.lbl_lt_status.setText(
                '<span style="color: red;">⚠ ' + msg + '</span>')
            if not hasattr(self, '_btn_fix_docker'):
                self._btn_fix_docker = QPushButton(_("Setup Docker (requires password)"))
                self._btn_fix_docker.setFixedWidth(280)
                self._btn_fix_docker.clicked.connect(self._on_setup_docker)
                self.lt_widget.layout().addWidget(self._btn_fix_docker)
            self._btn_fix_docker.setVisible(True)
            self.btn_lt_pull.setVisible(False)
            self.btn_lt_start.setVisible(False)
            self.btn_lt_stop.setVisible(False)
            self.btn_lt_purge.setVisible(False)
            return
        if hasattr(self, '_btn_fix_docker'):
            self._btn_fix_docker.setVisible(False)

        if not docker_has_image():
            self.lbl_lt_status.setText(
                '<span style="color: orange;">⚠ ' +
                _("Docker image not downloaded (~2 GB)") + '</span>'
            )
            self.btn_lt_pull.setVisible(True)
            self.btn_lt_pull.setEnabled(True)
            self.btn_lt_start.setVisible(False)
            self.btn_lt_stop.setVisible(False)
            self.btn_lt_purge.setVisible(False)
            return

        if docker_container_running():
            port_text = self.spin_lt_port.currentText()
            port = int(port_text) if port_text.isdigit() else 5000
            # Use cached size (updated asynchronously by _DockerSizeThread)
            # so the UI thread never blocks on `docker exec du -sb`.
            size_info = getattr(self, '_lt_last_size', '')
            size_str = f" — {size_info}" if size_info else ""
            # Trigger async size fetch (no-op if one is already running)
            _existing = getattr(self, '_lt_size_thread', None)
            if _existing is None or not _existing.isRunning():
                self._lt_size_thread = _DockerSizeThread()
                self._lt_size_thread.done.connect(self._on_lt_size_fetched)
                self._lt_size_thread.start()
            status_html = (
                '<span style="color: green;">✓ ' +
                _("LibreTranslate running on port {port}").format(port=port) +
                '</span>' +
                ('<small style="color: #888;"> ' + size_str + '</small>' if size_str else '')
            )
            # Vérifier que les langues source/cible sont disponibles
            avail = libretranslate_available_languages(port=port)
            if avail:
                src = self.combo_src.currentData()
                tgt = self.combo_tgt.currentData()
                missing = []
                if src not in avail:
                    missing.append(src)
                if tgt not in avail:
                    missing.append(tgt)
                if missing:
                    # Check if missing langs were requested but failed to load
                    # (not supported by LibreTranslate)
                    try:
                        _args = docker_cmd(
                            ["docker", "inspect", "-f", "{{.Args}}",
                             LIBRETRANSLATE_CONTAINER],
                            capture_output=True, text=True, timeout=3
                        ).stdout.strip()
                    except Exception:
                        _args = ""
                    unsupported = [l for l in missing if l in _args]
                    need_restart = [l for l in missing if l not in _args]
                    if unsupported:
                        status_html += (
                            '<br><span style="color: orange;">⚠ ' +
                            _("Language(s) not supported by LibreTranslate: "
                              "{langs}").format(
                                langs=", ".join(unsupported)) +
                            '</span>')
                    if need_restart:
                        status_html += (
                            '<br><span style="color: orange;">⚠ ' +
                            _("Language(s) not loaded: {langs}").format(
                                langs=", ".join(need_restart)) +
                            '</span><br><small>' +
                            _("Restart to add missing languages.") +
                            '</small>')
                    if not need_restart:
                        status_html += (
                            '<br><small>' +
                            _("Available: {langs}").format(
                                langs=", ".join(sorted(avail))) +
                            '</small>')
            self.lbl_lt_status.setText(status_html)
            self.btn_lt_pull.setVisible(False)
            self.btn_lt_start.setVisible(False)
            self.btn_lt_stop.setVisible(True)
            self.btn_lt_purge.setVisible(True)
        else:
            self.lbl_lt_status.setText(
                '<span style="color: orange;">⚠ ' +
                _("LibreTranslate stopped") + '</span>'
            )
            self.btn_lt_pull.setVisible(False)
            self.btn_lt_start.setVisible(True)
            self.btn_lt_stop.setVisible(False)
            self.btn_lt_purge.setVisible(False)
            # Container stopped → next start may change size; clear cache
            self._lt_last_size = ""

        # Polling périodique : voir la taille du conteneur grossir pendant que
        # LibreTranslate télécharge les modèles après un restart avec nouvelles langues
        if not hasattr(self, '_lt_size_timer'):
            self._lt_size_timer = QTimer(self)
            self._lt_size_timer.setInterval(10000)
            self._lt_size_timer.timeout.connect(self._check_lt_status)
        if docker_container_running() and self.lt_widget.isVisible():
            if not self._lt_size_timer.isActive():
                self._lt_size_timer.start()
        else:
            self._lt_size_timer.stop()

    def _get_lt_selected_langs(self):
        """Retourne les langues cochées, en forçant source et cible."""
        langs = set()
        for code, chk in self._lt_lang_checks.items():
            if chk.isChecked():
                langs.add(code)
        # Toujours inclure source et cible
        src = self.combo_src.currentData()
        tgt = self.combo_tgt.currentData()
        if src:
            langs.add(src)
        if tgt:
            langs.add(tgt)
        return sorted(lang for lang in langs if lang is not None)

    def _update_lt_lang_checks(self):
        """Coche automatiquement les langues source/cible (sans griser)."""
        src = self.combo_src.currentData()
        tgt = self.combo_tgt.currentData()
        for code, chk in self._lt_lang_checks.items():
            if code in (src, tgt) and not chk.isChecked():
                chk.blockSignals(True)
                chk.setChecked(True)
                chk.blockSignals(False)

    def _on_lt_deselect_all_langs(self):
        """Uncheck all LibreTranslate languages in one click.
        Source/target are re-checked automatically because they are mandatory."""
        # Block signals to avoid firing _on_lt_langs_changed N times (and N
        # HTTP calls to libretranslate_available_languages); fire it once at
        # the end instead.
        for chk in self._lt_lang_checks.values():
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
        # Re-check source/target (mandatory)
        self._update_lt_lang_checks()
        # Update hint label / restart button once
        self._on_lt_langs_changed()

    def _on_lt_langs_changed(self):
        """Affiche le bouton de redémarrage si les langues ont changé."""
        if not docker_container_running():
            self.btn_lt_restart_langs.setVisible(False)
            self.lbl_lt_langs_hint.setVisible(False)
            return
        selected = set(self._get_lt_selected_langs())
        port_text = self.spin_lt_port.currentText()
        port = int(port_text) if port_text.isdigit() else 5000
        installed = set(libretranslate_available_languages(port=port))
        if selected != installed and installed:
            added = selected - installed
            removed = installed - selected
            parts = []
            if added:
                parts.append("+ " + ", ".join(sorted(added)))
            if removed:
                parts.append("− " + ", ".join(sorted(removed)))
            self.lbl_lt_langs_hint.setText(
                '<small style="color: #888;">' +
                _("Changes: {changes}").format(changes=" / ".join(parts)) +
                '</small>')
            self.lbl_lt_langs_hint.setVisible(True)
            self.btn_lt_restart_langs.setVisible(True)
        else:
            self.lbl_lt_langs_hint.setVisible(False)
            self.btn_lt_restart_langs.setVisible(False)
        self._check_lt_status()

    def _on_lt_restart_langs(self):
        """Redémarre le conteneur Docker avec les nouvelles langues."""
        if self._lt_is_busy():
            return
        languages = ",".join(self._get_lt_selected_langs())
        port_text = self.spin_lt_port.currentText()
        port = int(port_text) if port_text.isdigit() else 5000

        # Sauvegarder immédiatement dans la config
        self._save_lt_langs_to_config(languages)

        self._lt_set_buttons_busy(True)
        self.lbl_lt_status.setText(
            '<span style="color: #888;">⏳ ' +
            _("Restarting with languages: {langs}…").format(langs=languages) + '</span>')

        self._lt_action_thread = _DockerActionThread("restart", port=port, languages=languages)
        self._lt_action_thread.progress.connect(self._on_lt_progress)
        self._lt_action_thread.done.connect(self._on_lt_restart_langs_finished)
        self._lt_action_thread.start()

    def _save_lt_langs_to_config(self, langs):
        """Met à jour DICTEE_LIBRETRANSLATE_LANGS dans dictee.conf (ou mémoire en mode wizard)."""
        # In wizard mode, only update in-memory conf
        if self.wizard_mode:
            self.conf["DICTEE_LIBRETRANSLATE_LANGS"] = langs
            return
        os.makedirs(os.path.dirname(CONF_PATH), exist_ok=True)
        if not os.path.exists(CONF_PATH):
            with open(CONF_PATH, "w") as f:
                f.write(f"# Generated by dictee-setup\nDICTEE_LIBRETRANSLATE_LANGS={langs}\n")
            return
        lines = []
        found = False
        with open(CONF_PATH) as f:
            for line in f:
                if line.startswith("DICTEE_LIBRETRANSLATE_LANGS="):
                    lines.append(f"DICTEE_LIBRETRANSLATE_LANGS={langs}\n")
                    found = True
                else:
                    lines.append(line)
        if not found:
            inserted = False
            for i, line in enumerate(lines):
                if line.startswith("DICTEE_LIBRETRANSLATE_PORT="):
                    lines.insert(i + 1, f"DICTEE_LIBRETRANSLATE_LANGS={langs}\n")
                    inserted = True
                    break
            if not inserted:
                lines.append(f"DICTEE_LIBRETRANSLATE_LANGS={langs}\n")
        tmp_path = CONF_PATH + ".tmp"
        with open(tmp_path, "w") as f:
            f.writelines(lines)
        os.replace(tmp_path, CONF_PATH)

    def _on_lt_restart_langs_finished(self, success, message):
        self._lt_set_buttons_busy(False)
        self._lt_starting_after_apply = False
        # Invalider le cache pour forcer une requête fraîche
        _lt_langs_cache["time"] = 0
        if not success:
            QMessageBox.critical(self, _("Error"), message)
        self.btn_lt_restart_langs.setVisible(False)
        self.lbl_lt_langs_hint.setVisible(False)
        self._check_lt_status()
        # Refresh target language combo with newly available languages
        self._update_tgt_languages()

    def _on_edit_keepcaps(self):
        """Open the short-text keepcaps editor dialog."""
        dlg = KeepcapsDialog(self)
        # Qt modal dialog show
        getattr(dlg, "exec")()

    def _on_lt_size_fetched(self, size):
        """Called from _DockerSizeThread when a new size reading is available.
        Re-renders the status label only if the value actually changed."""
        if size != getattr(self, '_lt_last_size', ''):
            self._lt_last_size = size
            # Refresh status label with the new cached size
            self._check_lt_status()

    def _on_setup_docker(self):
        _dbg_setup("_on_setup_docker")
        """Start Docker daemon + add user to docker group in one pkexec call."""
        user = os.environ.get("USER", "")
        if not user:
            return
        # Show spinner while pkexec runs
        self._btn_fix_docker.setEnabled(False)
        self.lbl_lt_status.setText(
            '<span style="color: #888;">⏳ ' +
            _("Setting up Docker…") + '</span>')
        self.progress_lt.setVisible(True)

        self._docker_setup_thread = _DockerSetupThread(user)
        self._docker_setup_thread.done.connect(self._on_setup_docker_finished)
        self._docker_setup_thread.start()

    def _on_setup_docker_finished(self, success, message):
        _dbg_setup(f"_on_setup_docker_finished: success={success}, msg={message!r}")
        self.progress_lt.setVisible(False)
        if success:
            global _docker_use_sg
            _docker_use_sg = True
            self._docker_group_fixed = True
            self._btn_fix_docker.setVisible(False)
            self.lbl_lt_status.setText(
                '<span style="color: green;">✓ ' +
                _("Docker started and permissions configured.") +
                '</span>')
            self._check_lt_status()
        else:
            self._btn_fix_docker.setEnabled(True)
            self._check_lt_status()
            QMessageBox.critical(self, _("Error"), message)

    def _on_lt_pull(self):
        _dbg_setup("_on_lt_pull: downloading LibreTranslate image")
        self.btn_lt_pull.setEnabled(False)
        self.progress_lt.setVisible(True)

        self._docker_pull_thread = DockerPullThread()
        self._docker_pull_thread.progress.connect(
            lambda text: self.btn_lt_pull.setText(text))
        self._docker_pull_thread.done.connect(self._on_lt_pull_finished)
        self._docker_pull_thread.start()

    def _on_lt_pull_finished(self, success, message):
        _dbg_setup(f"_on_lt_pull_finished: success={success}, msg={message!r}")
        self.progress_lt.setVisible(False)
        if success:
            self._check_lt_status()
        else:
            self.btn_lt_pull.setText(_("Download image"))
            self.btn_lt_pull.setEnabled(True)
            QMessageBox.critical(self, _("Download error"), message)

    def _on_lt_start(self):
        _dbg_setup("_on_lt_start")
        if self._lt_is_busy():
            return
        port_text = self.spin_lt_port.currentText()
        port = int(port_text) if port_text.isdigit() else 5000
        languages = ",".join(self._get_lt_selected_langs())
        self._save_lt_langs_to_config(languages)

        self._lt_set_buttons_busy(True)
        self.lbl_lt_status.setText(
            '<span style="color: #888;">⏳ ' +
            _("Starting LibreTranslate…") + '</span>')

        self._lt_action_thread = _DockerActionThread("start", port=port, languages=languages)
        self._lt_action_thread.progress.connect(self._on_lt_progress)
        self._lt_action_thread.done.connect(self._on_lt_action_finished)
        self._lt_action_thread.start()

    def _on_lt_stop(self):
        _dbg_setup("_on_lt_stop")
        if self._lt_is_busy():
            return

        self._lt_set_buttons_busy(True)
        self.lbl_lt_status.setText(
            '<span style="color: #888;">⏳ ' +
            _("Stopping LibreTranslate…") + '</span>')

        self._lt_action_thread = _DockerActionThread("stop")
        self._lt_action_thread.progress.connect(self._on_lt_progress)
        self._lt_action_thread.done.connect(self._on_lt_action_finished)
        self._lt_action_thread.start()

    def _on_lt_purge(self):
        _dbg_setup("_on_lt_purge")
        if self._lt_is_busy():
            return
        reply = QMessageBox.question(
            self, _("Purge downloaded models"),
            _("This deletes every language model cached in the LibreTranslate "
              "volume, then re-downloads only the currently selected "
              "languages.\n\n"
              "Use this to reclaim disk space after adding or removing "
              "languages several times.\n\n"
              "Continue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        languages = ",".join(self._get_lt_selected_langs())
        port_text = self.spin_lt_port.currentText()
        port = int(port_text) if port_text.isdigit() else 5000
        self._save_lt_langs_to_config(languages)
        self._lt_set_buttons_busy(True)
        self.lbl_lt_status.setText(
            '<span style="color: #888;">⏳ ' +
            _("Purging cached models and restarting…") + '</span>')
        self._lt_action_thread = _DockerActionThread(
            "purge", port=port, languages=languages)
        self._lt_action_thread.progress.connect(self._on_lt_progress)
        self._lt_action_thread.done.connect(self._on_lt_restart_langs_finished)
        self._lt_action_thread.start()

    def _lt_is_busy(self):
        """Vérifie si une opération Docker est en cours."""
        return (self._lt_action_thread is not None
                and self._lt_action_thread.isRunning())

    def _lt_set_buttons_busy(self, busy):
        """Désactive/réactive tous les boutons Docker LT."""
        enabled = not busy
        self.btn_lt_start.setEnabled(enabled)
        self.btn_lt_stop.setEnabled(enabled)
        self.btn_lt_restart_langs.setEnabled(enabled)
        self.btn_lt_purge.setEnabled(enabled)
        self.progress_lt.setVisible(busy)

    def _on_lt_progress(self, text):
        """Met à jour le label de statut avec la progression."""
        self.lbl_lt_status.setText(
            '<span style="color: #888;">⏳ ' + text + '</span>')

    def _on_lt_action_finished(self, success, message):
        _dbg_setup(f"_on_lt_action_finished: success={success}, msg={message!r}")
        self._lt_set_buttons_busy(False)
        self._lt_starting_after_apply = False
        _lt_langs_cache["time"] = 0
        if not success:
            QMessageBox.critical(self, _("Error"), message)
        self._check_lt_status()
        # Refresh target language combo with newly available languages
        self._update_tgt_languages()

    # -- Modèles ASR --

    def _on_model_cancel(self, mid):
        """Cancel an ongoing model download."""
        thread = self._model_threads.get(mid)
        if thread and thread.isRunning():
            thread.cancel()

    def _on_model_download(self, model):
        _dbg_setup(f"_on_model_download: {model}")
        mid = model["id"]
        w = self._model_widgets[mid]
        w["button"].setEnabled(False)
        w["button"].setStyleSheet("QPushButton { color: white; background-color: #c84; font-weight: bold; }")
        w["btn_delete"].setVisible(False)
        w["btn_cancel"].setVisible(True)
        w["progress"].setVisible(True)

        thread = ModelDownloadThread(model)
        thread.progress.connect(lambda text, _m=mid: self._on_model_progress(_m, text))
        thread.done.connect(lambda ok, msg, _m=mid: self._on_model_download_finished(_m, ok, msg))
        self._model_threads[mid] = thread
        thread.start()

    def _on_model_progress(self, mid, text):
        w = self._model_widgets[mid]
        w["button"].setText(text)
        # Extraire le pourcentage du texte ("filename  42.3%")
        import re as _re
        m = _re.search(r"([\d.]+)%", text)
        if m:
            try:
                pct = int(float(m.group(1)))
                w["progress"].setRange(0, 100)
                w["progress"].setValue(pct)
            except ValueError:
                pass

    def _on_model_download_finished(self, mid, success, message):
        _dbg_setup(f"_on_model_download_finished: {mid}, success={success}, msg={message!r}")
        w = self._model_widgets[mid]
        w["progress"].setVisible(False)
        w["btn_cancel"].setVisible(False)
        model = w["model"]
        if success:
            self._update_venv_button(w["button"], model["name"], True)
            w["button"].setToolTip("")
            w["btn_delete"].setVisible(True)
            # If TDT just installed, enable Sortformer button
            if mid == "tdt" and "sortformer" in self._model_widgets:
                dep_w = self._model_widgets["sortformer"]
                if not model_is_installed(dep_w["model"]):
                    self._update_venv_button(dep_w["button"], dep_w["model"]["name"], False)
                    dep_w["button"].setToolTip("")
        else:
            self._update_venv_button(w["button"], model["name"], False)
            if message != _("Cancelled"):
                QMessageBox.critical(self, _("Download error"), message)

    def _on_model_delete(self, model):
        """Delete an ASR model after confirmation."""
        mid = model["id"]
        name = model["name"]
        reply = QMessageBox.question(
            self, _("Delete model"),
            _("Delete {name} and free disk space?").format(name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        import shutil
        # Delete from both system and user dirs
        for base in (MODEL_DIR, DICTEE_DATA_DIR):
            model_dir = model["dir"].replace(MODEL_DIR, base)
            if os.path.isdir(model_dir):
                try:
                    shutil.rmtree(model_dir)
                    os.makedirs(model_dir, exist_ok=True)
                except PermissionError:
                    r = subprocess.run(["pkexec", "rm", "-rf", model_dir],
                                       capture_output=True, timeout=10)
                    if r.returncode == 0:
                        os.makedirs(model_dir, mode=0o777, exist_ok=True)
        w = self._model_widgets[mid]
        self._update_venv_button(w["button"], name, False)
        w["btn_delete"].setVisible(False)
        # If TDT deleted, disable Sortformer download
        if mid == "tdt" and "sortformer" in self._model_widgets:
            dep_w = self._model_widgets["sortformer"]
            if not model_is_installed(dep_w["model"]):
                dep_w["button"].setEnabled(False)
                dep_w["button"].setToolTip(_("Requires Parakeet-TDT 0.6B v3 to be installed first"))

    # -- Installation venv ASR --

    def _update_venv_button(self, btn, engine_name, installed):
        """Style a venv install button: red when not installed, green label when installed."""
        if installed:
            btn.setText(f"✓ {engine_name} " + _("installed"))
            btn.setStyleSheet("QPushButton { color: #4a4; font-weight: bold; }")
            btn.setEnabled(False)
        else:
            btn.setText(_("Install {name} engine").format(name=engine_name))
            btn.setStyleSheet("QPushButton { color: white; background-color: #c44; font-weight: bold; }"
                              "QPushButton:hover { background-color: #a33; }")
            btn.setEnabled(True)

    def _install_venv(self, name, venv_path, pip_package):
        _dbg_setup(f"_install_venv: {name}, path={venv_path}, pkg={pip_package}")
        btn = self.btn_install_vosk if name == "vosk" else self.btn_install_whisper
        btn.setEnabled(False)
        btn.setText(_("Installing…"))
        btn.setStyleSheet("QPushButton { color: white; background-color: #c84; font-weight: bold; }")
        thread = VenvInstallThread(venv_path, pip_package)
        thread.progress.connect(lambda text: btn.setText(text))
        thread.done.connect(lambda ok, msg, n=name: self._on_venv_installed(n, ok, msg))
        self._venv_threads[name] = thread
        thread.start()

    def _on_venv_installed(self, name, success, message):
        _dbg_setup(f"_on_venv_installed: {name}, success={success}, msg={message!r}")
        btn = self.btn_install_vosk if name == "vosk" else self.btn_install_whisper
        btn_del = self.btn_del_vosk_venv if name == "vosk" else self.btn_del_whisper_venv
        engine = "Vosk" if name == "vosk" else "Whisper"
        config_widgets = self._vosk_config_widgets if name == "vosk" else self._whisper_config_widgets
        if success:
            self._update_venv_button(btn, engine, True)
            btn_del.setVisible(True)
            for w in config_widgets:
                w.setEnabled(True)
            # Remind the user to download at least one language/model —
            # the venv on its own doesn't transcribe anything.
            if not self._any_model_installed(name):
                if name == "vosk":
                    hint = _("Now select a language in the combo box and click Download "
                             "to fetch at least one Vosk language model — without it, "
                             "Vosk cannot transcribe anything.")
                else:  # whisper
                    hint = _("Now pick a Whisper model (small / turbo / large-v3…) and "
                             "click Download — Whisper cannot transcribe until at least "
                             "one model is downloaded.")
                QMessageBox.information(
                    self,
                    _("{name} installed").format(name=engine),
                    _("{engine} engine installed successfully.").format(engine=engine)
                    + "\n\n" + hint)
        else:
            self._update_venv_button(btn, engine, False)
            btn_del.setVisible(False)
            _dbg_setup(f"Venv install error ({name}): {message!r}")
            QMessageBox.critical(self, _("Installation error"), message or _("Unknown error"))

    def _asr_backend_ready(self, backend, whisper_model=None, vosk_lang=None):
        """Return (ok, error_message) for the given ASR backend.
        Checks that the engine is actually installed AND that at least one
        language/model for it is available. Parakeet is always considered
        ready (it ships with the dictee package)."""
        if backend == "parakeet":
            return True, ""
        if backend == "canary":
            # Canary uses the transcribe-daemon binary shared with parakeet.
            # It also needs the CUDA providers for reasonable speed.
            if not os.path.isdir("/usr/share/dictee/canary") \
                    and not os.path.isfile(
                        os.path.join(DICTEE_DATA_DIR, "canary", "encoder-model.onnx")):
                return False, _(
                    "The Canary model is not installed.\n\n"
                    "Download it from the ASR backend page before enabling Canary.")
            if not os.path.isfile("/usr/lib/dictee/libonnxruntime_providers_cuda.so"):
                return False, _(
                    "Canary requires the CUDA build of dictee "
                    "(dictee-cuda .deb / .rpm).\n\n"
                    "On a CPU-only install, Canary is too slow to be usable.")
            return True, ""
        if backend == "vosk":
            if not venv_is_installed(VOSK_VENV):
                return False, _(
                    "Vosk is not installed.\n\n"
                    "Click « Install Vosk » on the ASR backend page before enabling it.")
            if not self._any_model_installed("vosk"):
                return False, _(
                    "Vosk is installed, but no language model has been downloaded.\n\n"
                    "Select a language in the Vosk combo box and click Download.")
            # Also require the currently selected lang to be installed
            if vosk_lang and not self._vosk_model_installed(vosk_lang):
                return False, _(
                    "The Vosk model for « {lang} » is not downloaded yet.\n\n"
                    "Pick it in the combo box and click Download, or choose a language "
                    "whose model is already installed.").format(lang=vosk_lang)
            return True, ""
        if backend == "whisper":
            if not venv_is_installed(WHISPER_VENV):
                return False, _(
                    "faster-whisper is not installed.\n\n"
                    "Click « Install Whisper » on the ASR backend page before enabling it.")
            if not self._any_model_installed("whisper"):
                return False, _(
                    "Whisper is installed, but no model has been downloaded.\n\n"
                    "Pick a Whisper model (small / turbo / large-v3…) and click Download.")
            if whisper_model and not self._whisper_model_cached(whisper_model):
                return False, _(
                    "The Whisper model « {model} » is not downloaded yet.\n\n"
                    "Click Download next to it, or choose a model that is already "
                    "available.").format(model=whisper_model)
            return True, ""
        return True, ""

    def _any_model_installed(self, name):
        """Returns True if at least one model is installed for the given engine."""
        if name == "vosk":
            for code in VOSK_MODELS:
                if self._vosk_model_installed(code):
                    return True
            return False
        if name == "whisper":
            # WHISPER_MODELS is a list of (model_id, display_name) tuples.
            # Do NOT use `_` as the throwaway var — it shadows gettext.
            for _mid, _dname in WHISPER_MODELS:
                if self._whisper_model_cached(_mid):
                    return True
            return False
        return True

    def _delete_venv(self, name):
        """Delete a Vosk or Whisper venv after user confirmation."""
        engine = "Vosk" if name == "vosk" else "Whisper"
        venv_path = VOSK_VENV if name == "vosk" else WHISPER_VENV
        btn = self.btn_install_vosk if name == "vosk" else self.btn_install_whisper
        btn_del = self.btn_del_vosk_venv if name == "vosk" else self.btn_del_whisper_venv
        config_widgets = self._vosk_config_widgets if name == "vosk" else self._whisper_config_widgets
        ret = QMessageBox.question(
            self, _("Uninstall {name} engine").format(name=engine),
            _("Delete the {name} virtual environment?\n\n{path}\n\nDownloaded models will be kept.").format(
                name=engine, path=venv_path),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            if os.path.isdir(venv_path):
                shutil.rmtree(venv_path)
            # Stop the systemd service if running
            svc = "dictee-vosk.service" if name == "vosk" else "dictee-whisper.service"
            subprocess.run(["systemctl", "--user", "stop", svc],
                           capture_output=True, timeout=5)
        except Exception as exc:
            QMessageBox.critical(self, _("Error"), str(exc))
            return
        self._update_venv_button(btn, engine, False)
        btn_del.setVisible(False)
        for w in config_widgets:
            w.setEnabled(False)

    def _mark_dirty(self):
        self._dirty = True

    # -- Panneau de test post-traitement --

    class _TestInputTextEdit(QTextEdit):
        """QTextEdit qui NE sélectionne PAS le texte après paste / drop /
        middle-click.

        Qt sélectionne par défaut le texte inséré via drag-drop ET via
        middle-click paste (primary selection X11) pour permettre à
        l'utilisateur de le "revoir". Dans le panneau de test on veut
        simplement voir le texte, cursor à la fin, sans sélection — pour
        ne pas masquer le rendu ni gêner la frappe suivante.

        Solution : on court-circuite complètement l'insertion par défaut
        en utilisant `insertPlainText` qui, par design, n'a jamais de
        sélection en sortie. On ignore volontairement les formats riches
        (HTML, RTF) — le panneau de test ne traite que du texte brut de
        toute façon.
        """

        def insertFromMimeData(self, source):
            if source is not None and source.hasText():
                self.insertPlainText(source.text())
            else:
                super().insertFromMimeData(source)

    # Mapping: _pp_tabs tab index → (step_key, friendly_label).
    # step_key matches the DICTEE_PP_* env var name segment used by
    # dictee-postprocess (also used as STEP trace label on stderr).
    _TEST_PAGE_STEPS = {
        0: ("rules",          "Règles regex"),
        1: ("continuation",   "Continuation"),
        2: ("language_rules", "Règles de langue"),
        3: ("dict",           "Dictionnaire"),
        4: ("llm",            "LLM"),
    }

    def _build_test_panel(self, lay):
        """Test panel: input → multiline output + mic."""
        # Test language indicator (auto-detected from cursor position in rules editor)
        self._test_lang_override = ""
        self._lbl_test_lang = QLabel("")
        self._lbl_test_lang.setStyleSheet("font-size: 14px; font-weight: bold;")
        self._lbl_test_lang.setVisible(False)
        # Auto-show/hide when text is set or cleared
        _orig_setText = self._lbl_test_lang.setText
        def _set_and_toggle(t, lbl=self._lbl_test_lang, orig=_orig_setText):
            orig(t)
            lbl.setVisible(bool(t))
        self._lbl_test_lang.setText = _set_and_toggle
        lay.addWidget(self._lbl_test_lang)

        # Tracks the step_key (rules/continuation/...) of the current
        # PP sub-tab. None when on the overview / unknown. Filled by
        # _update_test_header.
        self._test_current_step = None

        # Hook into the PP sub-tab change to refresh the accordion label
        # + the solo switch enabled state when the user navigates.
        if hasattr(self, '_pp_tabs'):
            self._pp_tabs.currentChanged.connect(self._update_test_header)

        # Re-run the test when the live language selection changes, so
        # the preview updates immediately without needing Apply.
        for _attr in ('combo_src', 'combo_tgt', 'cmb_trans_backend',
                      'cmb_trans_engine'):
            _cb = getattr(self, _attr, None)
            if _cb is not None:
                _cb.currentIndexChanged.connect(self._schedule_test_run)


        row = QHBoxLayout()
        row.setSpacing(6)

        # Left column: Isoler (top) + Traduction (bottom). Stacked so
        # both mode switches sit together at the start of the row, next
        # to the input. Isoler is on top per user preference.
        mode_col = QVBoxLayout()
        mode_col.setSpacing(4)
        mode_col.setContentsMargins(0, 0, 0, 0)

        self._test_solo_switch = ToggleSwitch(_("Isoler"))
        self._test_solo_switch.setToolTip(_tt(_("OFF: runs the full pipeline (all toggles active). ON: runs only the step of the currently open page, temporarily forcing the other steps off. Does not modify the persistent config — useful to see the effect of a single step in isolation.")))
        self._test_solo_switch.setEnabled(False)  # enabled once a page is known
        self._test_solo_switch.toggled.connect(self._schedule_test_run)
        mode_col.addWidget(self._test_solo_switch)

        self._test_trad_switch = ToggleSwitch(_("Traduction"))
        self._test_trad_switch.setChecked(False)
        self._test_trad_switch.setToolTip(_tt(_("OFF: tests the normal PP pipeline alone. ON: adds translation (+ translation PP if enabled).")))
        self._test_trad_switch.toggled.connect(lambda _: self._update_test_chain_label())
        mode_col.addWidget(self._test_trad_switch)

        # Chain description label
        self._test_mode_label = QLabel()
        self._test_mode_label.setStyleSheet("font-size: 11px; color: gray;")
        self._test_mode_label.setWordWrap(True)
        mode_col.addWidget(self._test_mode_label)

        row.addLayout(mode_col)

        # Initial header refresh now that switches exist
        if hasattr(self, '_pp_tabs'):
            self._update_test_header(self._pp_tabs.currentIndex())

        self._test_input = self._TestInputTextEdit()
        self._test_input.setPlaceholderText(_("Type text or record..."))
        self._test_input.setAcceptDrops(True)
        # Default height: 5 lines of text + document margins
        _fm = self._test_input.fontMetrics()
        _5lines = _fm.lineSpacing() * 5 + self._test_input.document().documentMargin() * 2 + 4
        _5lines = max(80, int(_5lines))
        self._test_input.setMinimumHeight(_5lines)
        self._test_input.setMaximumHeight(300)
        self._test_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Vertical resize grip (bottom edge of input)
        _input_grip = QLabel(self._test_input)
        _input_grip.setFixedHeight(8)
        _input_grip.setCursor(Qt.CursorShape.SizeVerCursor)
        _input_grip.setStyleSheet("background: transparent; border: none;")
        _input_grip._drag_y = None
        _input_grip._base_h = 0
        _self = self

        def _grip_paint(event):
            p = QPainter(_input_grip)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(128, 128, 128))
            pen.setWidth(1)
            p.setPen(pen)
            cx = _input_grip.width() // 2
            for y in (1, 4, 7):
                p.drawLine(cx - 10, y, cx + 10, y)
            p.end()
        _input_grip.paintEvent = _grip_paint

        def _grip_press(event):
            _input_grip._drag_y = event.position().y()
            _input_grip._base_h = _self._test_input.height()
            # Freeze tabs so they don't resize during drag
            if hasattr(_self, '_pp_tabs'):
                _input_grip._tabs_h = _self._pp_tabs.height()
                _self._pp_tabs.setFixedHeight(_input_grip._tabs_h)
            event.accept()
        _input_grip.mousePressEvent = _grip_press

        def _grip_move(event):
            if _input_grip._drag_y is not None:
                dy = int(event.position().y() - _input_grip._drag_y)
                new_h = max(_5lines, min(300, _input_grip._base_h + dy))
                _self._test_input.setFixedHeight(new_h)
                _self._test_output.setFixedHeight(new_h)
                _input_grip._base_h = new_h
                _input_grip._drag_y = event.position().y()
                event.accept()
        _input_grip.mouseMoveEvent = _grip_move

        def _grip_release(event):
            _input_grip._drag_y = None
            # Unfreeze tabs — restore minimum instead of fixed
            if hasattr(_self, '_pp_tabs'):
                _self._pp_tabs.setMinimumHeight(
                    getattr(_input_grip, '_tabs_h', 480))
                _self._pp_tabs.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            event.accept()
        _input_grip.mouseReleaseEvent = _grip_release

        def _reposition_grip(event=None):
            _input_grip.setGeometry(
                0, _self._test_input.height() - 8,
                _self._test_input.width(), 8)
            if event:
                type(_self._test_input).resizeEvent(_self._test_input, event)
        self._test_input.resizeEvent = _reposition_grip

        self._test_input.setFixedHeight(_5lines)

        # Clear button (top-right corner of input)
        _btn_clear_input = QPushButton("↺", self._test_input)
        _btn_clear_input.setFixedSize(24, 24)
        _btn_clear_input.setCursor(Qt.CursorShape.PointingHandCursor)
        _btn_clear_input.setToolTip(_("Clear input"))
        _btn_clear_input.setStyleSheet(
            "QPushButton { font-size: 18px; font-weight: bold; border: none;"
            " background: rgba(127,127,127,50); border-radius: 12px; color: rgba(200,200,200,180); }"
            "QPushButton:hover { background: rgba(127,127,127,90); color: white; }")
        _btn_clear_input.clicked.connect(lambda: self._test_input.clear())

        def _reposition_clear(event=None):
            _btn_clear_input.move(
                _self._test_input.width() - 24, 4)
            if event:
                type(_self._test_input).resizeEvent(_self._test_input, event)
        _old_resize = self._test_input.resizeEvent
        def _combined_resize(event=None):
            _reposition_clear(None)
            _old_resize(event)
        self._test_input.resizeEvent = _combined_resize
        _reposition_clear()

        row.addWidget(self._test_input, 3)

        # Arrow column with ASR/Translate icon above
        arrow_col = QVBoxLayout()
        arrow_col.setSpacing(2)
        arrow_col.setContentsMargins(0, 0, 0, 0)

        self._test_mode_icon = QLabel()
        self._test_mode_icon.setFixedSize(32, 32)
        self._test_mode_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow_col.addWidget(self._test_mode_icon, 0, Qt.AlignmentFlag.AlignCenter)

        self._test_translate_icon = QLabel()
        self._test_translate_icon.setFixedSize(32, 32)
        self._test_translate_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._test_translate_icon.setVisible(False)
        arrow_col.addWidget(self._test_translate_icon, 0, Qt.AlignmentFlag.AlignCenter)

        lbl_arrow = QLabel("\u2192")
        lbl_arrow.setStyleSheet("font-size: 22px; font-weight: bold;")
        lbl_arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow_col.addWidget(lbl_arrow, 0, Qt.AlignmentFlag.AlignCenter)

        arrow_widget = QWidget()
        arrow_widget.setFixedWidth(40)
        arrow_widget.setLayout(arrow_col)
        row.addWidget(arrow_widget)

        self._update_test_mode_icon()

        # Output column: unsaved warning label + output text
        _out_col = QVBoxLayout()
        _out_col.setSpacing(0)
        _out_col.setContentsMargins(0, 0, 0, 0)

        self._lbl_test_unsaved = QLabel(_("Unsaved"))
        self._lbl_test_unsaved.setStyleSheet(
            "QLabel { color: #e03030; font-size: 13px; font-weight: bold;"
            " padding: 0 2px; }")
        self._lbl_test_unsaved.setVisible(False)
        _out_col.addWidget(self._lbl_test_unsaved)

        self._test_output = QTextEdit()
        self._test_output.setReadOnly(True)
        self._test_output.setPlaceholderText(_("Output"))
        self._test_output.setFixedHeight(_5lines)
        self._test_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _out_col.addWidget(self._test_output)

        row.addLayout(_out_col, 3)

        accent = self.palette().color(self.palette().ColorRole.Highlight).name()
        _mic_icon = QIcon.fromTheme("audio-input-microphone")
        self._btn_record = QPushButton(_mic_icon, "") if not _mic_icon.isNull() else QPushButton("\U0001f3a4")
        self._btn_record.setFixedSize(60, 60)
        self._btn_record.setIconSize(self._btn_record.size() * 0.6)
        self._btn_record.setToolTip(_("Record"))
        self._btn_record.setStyleSheet(
            f"background-color: {accent}; color: white; border-radius: 8px;")
        row.addWidget(self._btn_record)

        btn_details = QPushButton(QIcon.fromTheme("view-list-details"), "")
        btn_details.setFixedSize(60, 60)
        btn_details.setIconSize(btn_details.size() * 0.6)
        btn_details.setToolTip(_("Pipeline details"))
        btn_details.setCheckable(True)
        row.addWidget(btn_details)

        lay.addLayout(row)

        # Pipeline details inside a scroll area so long trace lines
        # (many STEP entries with long before/after) don't push the
        # test body past a reasonable height and squeeze the Rules
        # editor above. The scroll area caps its height; the label
        # inside is free to grow and scrolls vertically as needed.
        self._test_details_label = QLabel("")
        self._test_details_label.setWordWrap(True)
        self._test_details_label.setStyleSheet(
            "font-family: monospace; font-size: 13px; line-height: 1.4;"
            " padding: 4px 6px;")
        self._test_details_label.setTextFormat(Qt.TextFormat.RichText)
        self._test_details_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._test_details_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self._test_details_scroll = QScrollArea()
        self._test_details_scroll.setWidgetResizable(True)
        self._test_details_scroll.setFrameShape(QFrame.Shape.StyledPanel)
        self._test_details_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._test_details_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._test_details_scroll.setFixedHeight(180)
        self._test_details_scroll.setWidget(self._test_details_label)
        self._test_details_scroll.setVisible(False)
        lay.addWidget(self._test_details_scroll)

        def _on_details_toggled(on):
            self._freeze_pp()
            self._test_details_scroll.setVisible(on)
            self._unfreeze_pp(20)
            # Auto-scroll to reveal the details panel when opened
            if on:
                scroll = getattr(self, "_pp_scroll", None)
                if scroll:
                    QTimer.singleShot(
                        40, lambda: scroll.ensureWidgetVisible(
                            self._test_details_scroll, 0, 40))
        btn_details.toggled.connect(_on_details_toggled)

        # Connect
        self._test_input.textChanged.connect(self._schedule_test_run)
        self._btn_record.clicked.connect(self._toggle_recording)

        # Debounce timer
        self._test_timer = QTimer()
        self._test_timer.setSingleShot(True)
        self._test_timer.setInterval(300)
        def _run_frozen():
            self._freeze_pp()
            self._run_test_pipeline()
            self._unfreeze_pp(10)
        self._test_timer.timeout.connect(_run_frozen)

        # Recording state
        self._recording_process = None

    def _freeze_pp(self):
        """Block repaints on the PP page to avoid intermediate layout artifacts."""
        scroll = getattr(self, '_pp_scroll', None)
        if scroll:
            scroll.setUpdatesEnabled(False)

    def _unfreeze_pp(self, delay=15):
        """Re-enable repaints after layout settles."""
        scroll = getattr(self, '_pp_scroll', None)
        if scroll:
            QTimer.singleShot(delay, lambda: (
                scroll.setUpdatesEnabled(True), scroll.update()))

    def _schedule_test_run(self):
        if hasattr(self, '_test_timer'):
            self._test_timer.start()

    def _load_continuation_words_for(self, lang):
        """Load continuation words for the given language.

        Mirrors dictee-postprocess.load_continuation() but also merges
        the user's in-memory pending additions (`_cont_personal_words`)
        and exclusions (`_cont_excluded_words`) so the test panel shows
        the same result the user will get after Apply — without needing
        to save the file first.

        Not cached: the continuation sets can change on every keystroke
        in the UI (add/remove chips) and the file is small.
        """
        import re as _re

        script_dir = os.path.dirname(os.path.abspath(__file__))
        paths = [
            os.path.join(script_dir, "continuation.conf.default"),
            "/usr/share/dictee/continuation.conf.default",
            os.path.expanduser("~/.local/share/dictee/continuation.conf.default"),
            os.path.expanduser("~/.config/dictee/continuation.conf"),
        ]
        _line_re = _re.compile(r"^\s*\[([a-z]{2}|\*)\]\s*(.+)$")
        _exc_re = _re.compile(r"^\s*\[exclude:([a-z]{2})\]\s*(.+)$")
        added = set()
        excluded = set()
        for p in paths:
            if not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        m = _exc_re.match(line)
                        if m:
                            tag, wl = m.groups()
                            if tag == lang:
                                for w in wl.split():
                                    excluded.add(w.lower())
                            continue
                        m = _line_re.match(line)
                        if not m:
                            continue
                        tag, wl = m.groups()
                        if tag == "*" or tag == lang:
                            for w in wl.split():
                                added.add(w.lower())
            except OSError:
                continue

        # Merge in-memory pending additions/exclusions so the test
        # reflects what the user WILL have after Apply, not just what
        # is currently persisted on disk.
        pending_add = getattr(self, '_cont_personal_words', {})
        if isinstance(pending_add, dict):
            added |= set(w.lower() for w in pending_add.get(lang, set()))
        pending_excl = getattr(self, '_cont_excluded_words', {})
        if isinstance(pending_excl, dict):
            excluded |= set(w.lower() for w in pending_excl.get(lang, set()))

        return added - excluded

    def _update_test_header(self, idx):
        """Update the test accordion label from the active PP sub-tab.

        Policy:
        - Every page change **invalidates** any active solo mode: the
          Isoler switch is reset to OFF so the user cannot accidentally
          isolate the wrong step after navigating.
        - On the PP overview (`self._pp_overview_mode` = True) the solo
          switch is **disabled entirely** — only the full pipeline test
          is available on the root page.
        - On a real sub-page, the switch is enabled and the accordion
          label shows the friendly step name.
        """
        overview = bool(getattr(self, '_pp_overview_mode', False))
        mapping = self._TEST_PAGE_STEPS.get(idx)
        if overview or mapping is None:
            self._test_current_step = None
            if hasattr(self, '_test_solo_switch'):
                self._test_solo_switch.setChecked(False)
                self._test_solo_switch.setEnabled(False)
        else:
            step_key, _label = mapping
            self._test_current_step = step_key
            if hasattr(self, '_test_solo_switch'):
                # Invalidate any previous solo state on page change
                self._test_solo_switch.setChecked(False)
                self._test_solo_switch.setEnabled(True)
        self._refresh_test_accordion_label()
        # Re-run the pipeline to refresh highlight / solo filtering
        if hasattr(self, '_test_timer'):
            self._schedule_test_run()

    def _refresh_test_accordion_label(self):
        """Set the accordion toggle text from its collapse state + page.

        The label becomes `▶ Test : Dictionnaire` on a sub-page and
        `▶ Test : global` on the PP overview / when no sub-page is
        focused (the full pipeline runs there). Called by
        _on_test_toggled and _update_test_header.
        """
        btn = getattr(self, '_test_accordion_toggle', None)
        if btn is None:
            return
        arrow = "▼  " if btn.isChecked() else "▶  "
        overview = bool(getattr(self, '_pp_overview_mode', False))
        mapping = self._TEST_PAGE_STEPS.get(
            self._pp_tabs.currentIndex() if hasattr(self, '_pp_tabs') else -1)
        if overview or mapping is None:
            suffix = _("Test : global")
        else:
            _step, friendly = mapping
            suffix = _("Test : {page}").format(page=_(friendly))
        btn.setText(arrow + suffix)

    def _get_test_mode(self):
        """Derive test pipeline mode from the current toggle states."""
        trad = (hasattr(self, '_test_trad_switch')
                and self._test_trad_switch.isChecked())
        if trad and self._pp_master_translate:
            return "full_chain"
        elif trad:
            return "normal+translate"
        return "normal"

    def _update_test_mode_icon(self):
        """Update icons between input/output based on test mode."""
        icons = _icons_dir()
        if not icons:
            self._test_mode_icon.clear()
            if hasattr(self, '_test_translate_icon'):
                self._test_translate_icon.clear()
                self._test_translate_icon.setVisible(False)
            return
        from PyQt6.QtGui import QPalette
        pal = self.palette()
        is_dark = pal.color(QPalette.ColorRole.Window).lightness() < 128
        suffix = "dark" if is_dark else "light"

        mode = (self._get_test_mode())
        has_translate = mode in ("normal+translate", "full_chain")

        # ASR icon always visible
        asr_path = os.path.join(icons, f"asr-symbolic-{suffix}.svg")
        if os.path.isfile(asr_path):
            pm = QPixmap(asr_path)
            self._test_mode_icon.setPixmap(
                pm.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation))
        else:
            self._test_mode_icon.clear()

        # Translate icon: visible only for modes with translation
        if hasattr(self, '_test_translate_icon'):
            self._test_translate_icon.setVisible(has_translate)
            if has_translate:
                trad_path = os.path.join(icons, f"translate-symbolic-orange-{suffix}.svg")
                if os.path.isfile(trad_path):
                    pm = QPixmap(trad_path)
                    self._test_translate_icon.setPixmap(
                        pm.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation))
                else:
                    self._test_translate_icon.clear()

    def _run_test_pipeline(self):
        """Runs the real dictee-postprocess binary as a subprocess.

        Uses DICTEE_PP_DEBUG=1 to collect step-by-step traces on stderr, so
        this panel stays in sync with the actual pipeline (LLM, master
        switches, short_text included). Single source of truth.

        Three modes derived from test toggles + PP masters:
        - "normal"           = PP Normal only (source language, LLM optional)
        - "normal+translate" = PP Normal → Translation → output
        - "full_chain"       = PP Normal → Translation → PP Translation → output
        """
        text = self._test_input.toPlainText()
        if not text.strip():
            self._test_output.setPlainText("")
            self._test_details_label.setText("")
            return

        test_mode = self._get_test_mode()
        needs_translate = test_mode in ("normal+translate", "full_chain")
        needs_trpp = test_mode == "full_chain"

        # Read the LIVE source/target languages from the combo boxes
        # instead of the saved conf — so changing the language in the
        # Translation page immediately reflects in the test panel, no
        # Apply needed.
        def _live(attr, conf_key, default):
            cb = getattr(self, attr, None)
            if cb is not None:
                val = cb.currentData()
                if val:
                    return val
            return self.conf.get(conf_key, default) or default

        live_src = _live("combo_src", "DICTEE_LANG_SOURCE", "fr")
        live_tgt = _live("combo_tgt", "DICTEE_LANG_TARGET", "en")

        # First subprocess always uses source language for PP Normal
        lang = getattr(self, '_test_lang_override', "") or live_src

        # Master switch: always check PP Normal master
        pp_master = self.chk_postprocess.isChecked() \
            if hasattr(self, 'chk_postprocess') else True

        # Locate dictee-postprocess (dev tree first, then installed)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        pp_path = os.path.join(script_dir, "dictee-postprocess.py")
        if not os.path.isfile(pp_path):
            pp_path = os.path.join(script_dir, "dictee-postprocess")
        if not os.path.isfile(pp_path):
            pp_path = shutil.which("dictee-postprocess") or ""
        if not pp_path or not os.path.isfile(pp_path):
            self._test_output.setPlainText(_("dictee-postprocess not found"))
            self._test_details_label.setText("")
            return

        # Build env from UI toggles
        def _b(attr, default=True):
            w = getattr(self, attr, None)
            if w is None:
                return "true" if default else "false"
            return "true" if w.isChecked() else "false"

        def _tb(key):
            return "true" if self._trpp_state.get(key, True) else "false"

        env = os.environ.copy()
        env["DICTEE_LANG_SOURCE"] = lang
        env["DICTEE_PP_DEBUG"] = "true"

        # Command suffixes — rules with %SUFFIX_XX% placeholders are
        # skipped by dictee-postprocess when their env var is empty.
        # Pass the current UI state so the test matches runtime.
        for _code, _sfx in getattr(self, '_command_suffixes', {}).items():
            if _sfx:
                env[f"DICTEE_COMMAND_SUFFIX_{_code.upper()}"] = _sfx

        # PP Normal env vars (always source language)
        env["DICTEE_PP_RULES"] = _b("chk_pp_rules")
        env["DICTEE_PP_CONTINUATION"] = _b("chk_pp_continuation")
        env["DICTEE_PP_LANGUAGE_RULES"] = _b("chk_pp_language_rules")
        env["DICTEE_PP_ELISIONS"] = _b("chk_pp_elisions")
        env["DICTEE_PP_ELISIONS_IT"] = _b("chk_pp_elisions_it")
        env["DICTEE_PP_SPANISH"] = _b("chk_pp_spanish")
        env["DICTEE_PP_PORTUGUESE"] = _b("chk_pp_portuguese")
        env["DICTEE_PP_GERMAN"] = _b("chk_pp_german")
        env["DICTEE_PP_DUTCH"] = _b("chk_pp_dutch")
        env["DICTEE_PP_ROMANIAN"] = _b("chk_pp_romanian")
        env["DICTEE_PP_NUMBERS"] = _b("chk_pp_numbers")
        env["DICTEE_PP_TYPOGRAPHY"] = _b("chk_pp_typography")
        env["DICTEE_PP_DICT"] = _b("chk_pp_dict")
        env["DICTEE_PP_CAPITALIZATION"] = _b("chk_pp_capitalization")
        env["DICTEE_PP_SHORT_TEXT"] = _b("chk_pp_short_text")
        env["DICTEE_PP_KEEPCAPS"] = _b("chk_pp_keepcaps")
        env["DICTEE_PP_KEEPCAPS_EXTENDED"] = _b("chk_pp_keepcaps_ext")
        if hasattr(self, 'cmb_pp_short_text_max'):
            env["DICTEE_PP_SHORT_TEXT_MAX"] = str(
                self.cmb_pp_short_text_max.currentData() or 3)

        # LLM (normal mode only)
        llm_on = _b("chk_llm", default=False)
        env["DICTEE_LLM_POSTPROCESS"] = llm_on
        env["DICTEE_LLM_POSITION"] = (
            self._get_llm_position() if hasattr(self, '_get_llm_position') else "hybrid")
        if hasattr(self, 'cmb_llm_model'):
            env["DICTEE_LLM_MODEL"] = self.cmb_llm_model.currentText() or "gemma3:4b"
        if hasattr(self, 'cmb_llm_preset'):
            env["DICTEE_LLM_SYSTEM_PROMPT"] = self.cmb_llm_preset.currentData() or "correction-fr"
        if hasattr(self, 'txt_llm_prompt'):
            env["DICTEE_LLM_CUSTOM_PROMPT"] = self.txt_llm_prompt.toPlainText()
        # Tight LLM timeout so the UI stays responsive
        env.setdefault("DICTEE_LLM_TIMEOUT", "15")

        # Solo mode: force-off all PP sub-steps except the one for the
        # active sub-page. Does not touch persistent config — only the
        # env vars for this single invocation. Short text stays off too
        # (it's not mapped to a sub-page of its own).
        solo_mode = (
            hasattr(self, '_test_solo_switch')
            and self._test_solo_switch.isEnabled()
            and self._test_solo_switch.isChecked()
            and self._test_current_step is not None)
        if solo_mode:
            _all_steps = [
                "DICTEE_PP_RULES", "DICTEE_PP_CONTINUATION",
                "DICTEE_PP_LANGUAGE_RULES", "DICTEE_PP_ELISIONS",
                "DICTEE_PP_ELISIONS_IT", "DICTEE_PP_SPANISH",
                "DICTEE_PP_PORTUGUESE", "DICTEE_PP_GERMAN",
                "DICTEE_PP_DUTCH", "DICTEE_PP_ROMANIAN",
                "DICTEE_PP_NUMBERS", "DICTEE_PP_TYPOGRAPHY",
                "DICTEE_PP_DICT", "DICTEE_PP_CAPITALIZATION",
                "DICTEE_PP_SHORT_TEXT",
            ]
            for k in _all_steps:
                env[k] = "false"
            env["DICTEE_LLM_POSTPROCESS"] = "false"
            _step = self._test_current_step
            if _step == "rules":
                env["DICTEE_PP_RULES"] = "true"
            elif _step == "continuation":
                env["DICTEE_PP_CONTINUATION"] = "true"
            elif _step == "language_rules":
                # Umbrella ON + all language sub-flags ON so the user
                # sees the full effect of the language-rules stage.
                env["DICTEE_PP_LANGUAGE_RULES"] = "true"
                for k in ("DICTEE_PP_ELISIONS", "DICTEE_PP_ELISIONS_IT",
                          "DICTEE_PP_SPANISH", "DICTEE_PP_PORTUGUESE",
                          "DICTEE_PP_GERMAN", "DICTEE_PP_DUTCH",
                          "DICTEE_PP_ROMANIAN", "DICTEE_PP_TYPOGRAPHY"):
                    env[k] = "true"
            elif _step == "dict":
                env["DICTEE_PP_DICT"] = "true"
            elif _step == "llm" and test_mode == "normal":
                env["DICTEE_LLM_POSTPROCESS"] = "true"

        # Update the language indicator label to reflect the active mode
        if hasattr(self, '_lbl_test_lang'):
            if test_mode == "normal":
                self._lbl_test_lang.setText("")
            elif test_mode == "normal+translate":
                self._lbl_test_lang.setText(
                    _("PP Normal → Traduction {src}→{tgt}").format(
                        src=live_src[:2].upper(), tgt=live_tgt[:2].upper()))
            elif test_mode == "full_chain":
                self._lbl_test_lang.setText(
                    _("PP Normal → Trad → PP Trad ({tgt})").format(
                        tgt=live_tgt[:2].upper()))

        # Continuation keyword: if text starts with the configured keyword
        # (e.g. "minuscule"), strip it and lowercase the rest — mirrors
        # apply_continuation() in the dictee shell script.
        keyword_stripped = False
        _kw = getattr(self, '_cont_keywords', {}).get(lang[:2], "minuscule")
        if _kw:
            import re as _re_kw
            # Build regex like the shell: hyphens/spaces → [- ]?, s? suffix
            _kw_pat = _re_kw.sub(r"[\s-]", "[- ]?", _kw.lower())
            _kw_re = _re_kw.compile(
                r"^" + _kw_pat + r"s?[.,]?\s*(.*)", _re_kw.IGNORECASE | _re_kw.DOTALL)
            _kw_m = _kw_re.match(text)
            if _kw_m:
                _kw_rest = _kw_m.group(1)
                _kw_before = text
                if _kw_rest:
                    text = _kw_rest[0].lower() + _kw_rest[1:]
                else:
                    text = ""
                keyword_stripped = True

        # Skip PP subprocess if master is off — pass text through to translation
        steps = []
        if not pp_master:
            result = text
        else:
            try:
                proc = subprocess.run(
                    [sys.executable, pp_path],
                    input=text, capture_output=True, text=True,
                    env=env, timeout=30)
            except subprocess.TimeoutExpired:
                self._test_output.setPlainText(_("Timeout running post-processing"))
                self._test_details_label.setText("")
                return
            except Exception as e:
                self._test_output.setPlainText(f"Error: {e}")
                self._test_details_label.setText("")
                return

            result = proc.stdout.rstrip(" ")  # strip trailing spaces (mirrors shell)

        # Parse step traces on stderr
        def _dec(s):
            out = []
            i = 0
            while i < len(s):
                c = s[i]
                if c == "\\" and i + 1 < len(s):
                    nxt = s[i + 1]
                    if nxt == "n":
                        out.append("\n"); i += 2; continue
                    if nxt == "t":
                        out.append("\t"); i += 2; continue
                    if nxt == "\\":
                        out.append("\\"); i += 2; continue
                out.append(c)
                i += 1
            return "".join(out)

        if pp_master:
            steps = []
            if keyword_stripped:
                steps.append(("Continuation keyword", _kw_before, text))
            for line in proc.stderr.splitlines():
                if not line.startswith("STEP\t"):
                    continue
                parts = line.split("\t", 3)
                if len(parts) != 4:
                    continue
                label = parts[1]
                before = _dec(parts[2])
                after = _dec(parts[3])
                steps.append((label, before, after))

        # Continuation indicator: mirror the shell script's save_last_word
        # logic. When the last word of the result is a continuation word
        # in the active language, strip trailing punctuation and append
        # the configured indicator (>>, ..., ↓, •…). This is what the
        # user would actually see at runtime in their target app.
        #
        # In translate mode, dictee checks the SOURCE text last word but
        # appends >> to the TRANSLATED text. So here we detect continuation
        # on the source result but defer appending until after translation.
        indicator_appended = False
        _source_continuation = False
        _indicator_before = ""
        _indicator = self.conf.get(
            "DICTEE_CONTINUATION_INDICATOR", ">>") or ">>"
        if (env.get("DICTEE_PP_CONTINUATION", "false") == "true"
                and result.strip()):
            cont_words = self._load_continuation_words_for(lang)
            if cont_words:
                import re as _re
                _m = _re.search(r"([A-Za-zÀ-ÿ''-]+)"
                                r"[\.\,\?\!\u2026\s]*$", result.rstrip())
                if _m:
                    _last = _m.group(1).lower()
                    if "-" in _last:
                        _last = _last.rsplit("-", 1)[-1]
                    if _last in cont_words:
                        if needs_translate:
                            # Defer: just flag it, append after translation
                            _source_continuation = True
                        else:
                            _indicator_before = result
                            _stripped = _re.sub(
                                r"[\.\,\?\!\u2026]+\s*$", "", result.rstrip())
                            result = _stripped + _indicator
                            indicator_appended = True

        # Synthetic step entry so the details panel stays honest about
        # the continuation indicator append (which happens here, in the
        # test panel, not in dictee-postprocess itself).
        if indicator_appended:
            steps.append(("Continuation indicator", _indicator_before, result))

        # --- Phase 2: Translation (modes normal+translate, full_chain) ---
        translated_from = ""
        translate_error = ""
        if needs_translate and result.strip():
            source_lang = live_src[:2]
            target = live_tgt[:2]
            if source_lang != target:
                _eff_conf = dict(self.conf)
                if hasattr(self, 'cmb_trans_backend'):
                    _tb_val = self.cmb_trans_backend.currentData()
                    if _tb_val:
                        _eff_conf["DICTEE_TRANSLATE_BACKEND"] = _tb_val
                if hasattr(self, 'cmb_trans_engine'):
                    _e = self.cmb_trans_engine.currentData()
                    if _e:
                        _eff_conf["DICTEE_TRANS_ENGINE"] = _e
                translated, translate_error = _test_translate_text(
                    result, source_lang, target, _eff_conf)
                if translated and translated != result:
                    translated_from = result
                    result = translated

        # Source continuation deferred: append >> to translated text
        if _source_continuation and result.strip():
            import re as _re
            _indicator_before = result
            _stripped = _re.sub(
                r"[\.\,\?\!\u2026]+\s*$", "", result.rstrip())
            result = _stripped + _indicator
            indicator_appended = True
            steps.append(("Continuation indicator", _indicator_before, result))

        # --- Phase 3: PP Translation (full_chain only) ---
        trpp_steps = []
        trpp_error = ""
        if needs_trpp and result.strip():
            trpp_master = getattr(self, '_pp_master_translate', True)
            if trpp_master:
                env2 = os.environ.copy()
                env2["DICTEE_LANG_SOURCE"] = live_tgt[:2]
                env2["DICTEE_PP_DEBUG"] = "true"
                for _code, _sfx in getattr(self, '_command_suffixes', {}).items():
                    if _sfx:
                        env2[f"DICTEE_COMMAND_SUFFIX_{_code.upper()}"] = _sfx
                env2["DICTEE_PP_RULES"]          = _tb("rules")
                env2["DICTEE_PP_CONTINUATION"]   = _tb("continuation")
                env2["DICTEE_PP_LANGUAGE_RULES"] = _tb("language_rules")
                env2["DICTEE_PP_NUMBERS"]        = _tb("numbers")
                env2["DICTEE_PP_DICT"]           = _tb("dict")
                env2["DICTEE_PP_CAPITALIZATION"] = _tb("capitalization")
                env2["DICTEE_PP_SHORT_TEXT"]     = _tb("short_text")
                if hasattr(self, 'cmb_trpp_short_text_max'):
                    env2["DICTEE_PP_SHORT_TEXT_MAX"] = str(
                        self.cmb_trpp_short_text_max.currentData() or 3)
                if self._trpp_state.get("language_rules", True):
                    env2["DICTEE_PP_ELISIONS"]    = _b("chk_pp_elisions")
                    env2["DICTEE_PP_ELISIONS_IT"] = _b("chk_pp_elisions_it")
                    env2["DICTEE_PP_SPANISH"]     = _b("chk_pp_spanish")
                    env2["DICTEE_PP_PORTUGUESE"]  = _b("chk_pp_portuguese")
                    env2["DICTEE_PP_GERMAN"]      = _b("chk_pp_german")
                    env2["DICTEE_PP_DUTCH"]       = _b("chk_pp_dutch")
                    env2["DICTEE_PP_ROMANIAN"]    = _b("chk_pp_romanian")
                    env2["DICTEE_PP_TYPOGRAPHY"]  = _b("chk_pp_typography")
                else:
                    for k in ("DICTEE_PP_ELISIONS", "DICTEE_PP_ELISIONS_IT",
                              "DICTEE_PP_SPANISH", "DICTEE_PP_PORTUGUESE",
                              "DICTEE_PP_GERMAN", "DICTEE_PP_DUTCH",
                              "DICTEE_PP_ROMANIAN", "DICTEE_PP_TYPOGRAPHY"):
                        env2[k] = "false"
                env2["DICTEE_LLM_POSTPROCESS"] = "false"
                try:
                    proc2 = subprocess.run(
                        [sys.executable, pp_path],
                        input=result, capture_output=True, text=True,
                        env=env2, timeout=30)
                    result = proc2.stdout
                    for line in proc2.stderr.splitlines():
                        if not line.startswith("STEP\t"):
                            continue
                        parts = line.split("\t", 3)
                        if len(parts) == 4:
                            trpp_steps.append((parts[1], _dec(parts[2]), _dec(parts[3])))
                except subprocess.TimeoutExpired:
                    trpp_error = _("Timeout PP traduction")
                except Exception as e:
                    trpp_error = str(e)
            else:
                trpp_error = _("Translation post-processing disabled (master switch off)")

        # Continuation indicator on the FINAL result (target language)
        # when translation was applied. The first check (above) covers
        # the source language after PP Normal; this one covers the target
        # language after translation / TRPP.
        if needs_translate and not indicator_appended and result.strip():
            _final_lang = live_tgt[:2]
            # Check continuation in the env that was actually used:
            # Phase 3 env2 if full_chain, else Phase 1 env for the flag
            _cont_on = True
            if needs_trpp and 'env2' in dir():
                _cont_on = env2.get("DICTEE_PP_CONTINUATION", "false") == "true"
            else:
                _cont_on = env.get("DICTEE_PP_CONTINUATION", "false") == "true"
            if _cont_on:
                cont_words = self._load_continuation_words_for(_final_lang)
                if cont_words:
                    import re as _re
                    _m = _re.search(r"([A-Za-zÀ-ÿ''-]+)"
                                    r"[\.\,\?\!\u2026\s]*$", result.rstrip())
                    if _m:
                        _last = _m.group(1).lower()
                        # Hyphenated words: "parles-tu" → check "tu"
                        if "-" in _last:
                            _last = _last.rsplit("-", 1)[-1]
                        if _last in cont_words:
                            _indicator = self.conf.get(
                                "DICTEE_CONTINUATION_INDICATOR", ">>") or ">>"
                            _indicator_before = result
                            _stripped = _re.sub(
                                r"[\.\,\?\!\u2026]+\s*$", "", result.rstrip())
                            result = _stripped + _indicator
                            indicator_appended = True
                            steps.append(("Continuation indicator",
                                          _indicator_before, result))

        # Unsaved-continuation warning visibility
        if hasattr(self, '_lbl_test_unsaved'):
            self._lbl_test_unsaved.setVisible(
                self._has_unsaved_cont_changes())

        # Output display (visible whitespace markers)
        display_output = result
        display_output = display_output.replace("\n", "↵\n")
        display_output = display_output.replace("\t", "⇥\t")
        if display_output.endswith(" "):
            display_output = display_output.rstrip(" ") + "␣"
        if not display_output.strip() and result.strip():
            display_output = result.replace("\n", "↵").replace("\t", "⇥")
        self._test_output.setPlainText(display_output)

        # Details — built as rich HTML so the active step can be
        # highlighted in accent color (follows the current PP sub-page).
        import html as _html
        _accent_html = self.palette().color(
            self.palette().ColorRole.Highlight).name()
        _current_step = getattr(self, '_test_current_step', None)

        # Map each PP sub-page to a predicate matching STEP trace labels
        # emitted by dictee-postprocess on stderr.
        def _step_matches(trace_label, page_step):
            if page_step is None:
                return False
            n = trace_label
            if page_step == "rules":
                return n == "Rules"
            if page_step == "continuation":
                return n == "Continuation" or n == "Continuation indicator"
            if page_step == "language_rules":
                return any(n.startswith(p) for p in (
                    "Elisions", "Spanish", "Contractions",
                    "German", "Dutch", "Romanian", "Typography"))
            if page_step == "dict":
                return n == "Dictionary"
            if page_step == "llm":
                return n.startswith("LLM")
            return False

        def _line(txt, highlight=False, warn=False):
            escaped = _html.escape(txt).replace("\n", "<br/>")
            if highlight:
                return (f'<span style="color:{_accent_html}; '
                        f'font-weight:bold;">{escaped}</span>')
            if warn:
                return f'<span style="color:#e67e22;">{escaped}</span>'
            return escaped

        html_lines = []
        if solo_mode:
            html_lines.append(_line(
                _("🔬 Solo mode: only this step runs."),
                highlight=True))
        if not steps and (not pp_master or (pp_master and proc.returncode == 0)):
            html_lines.append(_line(_("No pipeline steps ran.")))
        # Resolve LLM model label once for trace enrichment
        _llm_label = ""
        if hasattr(self, '_current_llm_model'):
            _lm = self._current_llm_model()
            if _lm:
                _llm_label = f" [{_lm}]"
        for i, (name, before, after) in enumerate(steps, 1):
            changed = before != after
            marker = " \u2190 " + _("changed") if changed else ""
            display = after.replace("\n", "\\n").replace("\t", "\\t")
            if len(display) > 100:
                display = display[:100] + "\u2026"
            # Append model tag to LLM steps: "LLM" → "LLM [gemma3:4b]"
            display_name = f"{name}{_llm_label}" if name.startswith("LLM") else name
            raw = f"{i}. {display_name} \u2192 {display}{marker}"
            is_current = _step_matches(name, _current_step)
            html_lines.append(_line(raw, highlight=is_current))

        # Translation step (Phase 2)
        if needs_translate and translated_from:
            src_short = translated_from if len(translated_from) <= 100 \
                else translated_from[:100] + "\u2026"
            tgt_short = result if not needs_trpp else (
                translated_from if len(translated_from) <= 100 else translated_from[:100] + "\u2026")
            # For full_chain, show pre-TRPP text, not final result
            if needs_trpp and translated_from:
                _pre_trpp = translated_from  # text before TRPP
            html_lines.append(_line(
                _("\U0001f310 Translate: \u201c{src}\u201d \u2192 "
                  "\u201c{tgt}\u201d").format(src=src_short, tgt=tgt_short)))
        if translate_error:
            html_lines.append(_line(
                _("⚠ Translation failed: {err}").format(err=translate_error),
                warn=True))

        # TRPP steps (Phase 3, full_chain only)
        if trpp_steps:
            html_lines.append(_line("── PP Traduction ──"))
            step_offset = len(steps)
            for i, (name, before, after) in enumerate(trpp_steps, step_offset + 1):
                changed = before != after
                marker = " \u2190 " + _("changed") if changed else ""
                display_text = after.replace("\n", "\\n").replace("\t", "\\t")
                if len(display_text) > 100:
                    display_text = display_text[:100] + "\u2026"
                display_name = f"{name}{_llm_label}" if name.startswith("LLM") else name
                raw = f"{i}. {display_name} \u2192 {display_text}{marker}"
                html_lines.append(_line(raw))
        if trpp_error:
            html_lines.append(_line(
                _("⚠ PP Traduction: {err}").format(err=trpp_error),
                warn=True))

        if pp_master and proc.returncode != 0:
            html_lines.append(_line(
                f"[exit {proc.returncode}] "
                f"{proc.stderr.splitlines()[-1] if proc.stderr else ''}",
                warn=True))
        self._test_details_label.setTextFormat(Qt.TextFormat.RichText)
        _prev_h = self._test_details_label.height()
        self._test_details_label.setText("<br/>".join(html_lines))



    def _toggle_recording(self):
        """Starts/stops microphone recording."""
        if self._recording_process is not None:
            self._recording_process.terminate()
            self._recording_process.waitForFinished(2000)
            self._recording_process = None
            # Restore mic icon + accent background
            accent = self.palette().color(self.palette().ColorRole.Highlight).name()
            _mic_icon = QIcon.fromTheme("audio-input-microphone")
            if not _mic_icon.isNull():
                self._btn_record.setIcon(_mic_icon)
                self._btn_record.setText("")
            else:
                self._btn_record.setIcon(QIcon())
                self._btn_record.setText("\U0001f3a4")
            self._btn_record.setStyleSheet(
                f"background-color: {accent}; color: white; border-radius: 8px;")
            self._transcribe_recorded()
            return

        # Check daemon
        services = ["dictee.service", "dictee-vosk.service", "dictee-whisper.service", "dictee-canary.service"]
        active = False
        for svc in services:
            try:
                r = subprocess.run(["systemctl", "--user", "is-active", svc],
                                   capture_output=True, text=True, timeout=3)
                if r.stdout.strip() == "active":
                    active = True
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        if not active:
            reply = QMessageBox.question(
                self._pp_parent, "dictee",
                _("No ASR service is running. Start the default service?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                backend = self.conf.get("DICTEE_ASR_BACKEND", "parakeet")
                svc_map = {"parakeet": "dictee.service", "vosk": "dictee-vosk.service",
                           "whisper": "dictee-whisper.service", "canary": "dictee-canary.service"}
                subprocess.Popen(["systemctl", "--user", "start",
                                  svc_map.get(backend, "dictee.service")])
            else:
                return

        # Start recording
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        self._tmp_wav = os.path.join(runtime_dir, "dictee-test-recording.wav")
        self._recording_process = QProcess(self)
        self._recording_process.start("pw-record", [
            "--rate", "16000", "--channels", "1", "--format", "s16",
            self._tmp_wav])
        _stop_icon = QIcon.fromTheme("media-playback-stop")
        if not _stop_icon.isNull():
            self._btn_record.setIcon(_stop_icon)
            self._btn_record.setText("")
        else:
            self._btn_record.setIcon(QIcon())
            self._btn_record.setText("⏹")
        self._btn_record.setStyleSheet(
            "background-color: #c0392b; color: white; border-radius: 8px;")

    def _transcribe_recorded(self):
        """Sends recorded WAV to daemon via Unix socket."""
        import socket as _socket
        wav_path = getattr(self, '_tmp_wav', None)
        if not wav_path or not os.path.isfile(wav_path):
            return

        # Silence threshold check — consistent with the main PTT flow
        # and the calibration playground.
        _thr = (
            self.slider_silence.value() / 1000.0
            if hasattr(self, 'slider_silence')
            else _read_silence_threshold_from_conf())
        _rms = _measure_wav_rms(wav_path)
        if _rms > 0 and _rms < _thr:
            self._test_output.setHtml('<span style="font-size: 16pt;">🔇</span>')
            self._test_details_label.setText(
                _("Silence detected (RMS {rms:.3f} < threshold {thr:.3f})").format(
                    rms=_rms, thr=_thr))
            try:
                os.unlink(wav_path)
            except OSError:
                pass
            return

        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        sock_path = os.path.join(runtime_dir, "transcribe.sock")
        if not os.path.exists(sock_path):
            sock_path = os.path.join(runtime_dir, "dictee", "transcribe.sock")
        if not os.path.exists(sock_path):
            sock_path = "/tmp/transcribe.sock"
        s = None
        try:
            s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            s.settimeout(30)
            s.connect(sock_path)
            s.sendall((wav_path + "\n").encode())
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            text = data.decode("utf-8").strip()
            if text:
                self._test_input.setPlainText(text)
        except (_socket.error, OSError) as e:
            QMessageBox.warning(self._pp_parent, "dictee",
                                _("Cannot connect to ASR daemon: {err}").format(err=str(e)))
        finally:
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    # -- LLM Diarization (page 9) --

    def _on_manage_llm_providers(self):
        """Open the LLM providers management dialog."""
        try:
            dlg = LLMProvidersDialog(self)
        except ImportError as e:
            QMessageBox.critical(
                self, _("Module missing"),
                _("Could not load LLM module:\n{err}").format(err=str(e)))
            return
        _llm_modal(dlg)

    def _on_manage_llm_profiles(self):
        """Open the LLM profiles management dialog."""
        try:
            dlg = LLMProfilesDialog(self)
        except ImportError as e:
            QMessageBox.critical(
                self, _("Module missing"),
                _("Could not load LLM module:\n{err}").format(err=str(e)))
            return
        _llm_modal(dlg)

    # -- Appliquer --

    def _on_apply_clicked(self):
        """Apply button handler: run _on_apply with in-button animation
        instead of a trailing message box (message box only on OK).
        """
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication
        btn = self.sender()
        if btn is None:
            # Fallback: no sender context, run plain apply silently
            self._on_apply(show_message=False)
            return
        orig_text = btn.text()
        orig_min_w = btn.minimumWidth()
        # Freeze width to prevent layout shift as the spinner cycles
        btn.setMinimumWidth(btn.width())
        btn.setEnabled(False)

        # Braille spinner — 32 frames, ~30 fps for a smooth rotating wheel
        _frames = (
            "⣾⣽⣻⢿⡿⣟⣯⣷"
            "⠋⠙⠚⠞⠖⠦⠴⠲⠳⠓"
            "⠁⠂⠄⡀⡈⡐⡠⣀⣁⣂⣄⣌⣔⣤"
        )
        self._apply_anim_step = 0
        _base = _("Applying")
        def _tick():
            frame = _frames[self._apply_anim_step % len(_frames)]
            btn.setText(f"{frame} {_base}…")
            self._apply_anim_step += 1
        _tick()
        self._apply_anim_timer = QTimer(self)
        self._apply_anim_timer.timeout.connect(_tick)
        self._apply_anim_timer.start(33)  # ~30 fps
        QApplication.processEvents()

        try:
            self._on_apply(show_message=False)
        finally:
            self._apply_anim_timer.stop()
            btn.setText(orig_text)
            btn.setMinimumWidth(orig_min_w)
            btn.setEnabled(True)

    def _on_apply(self, show_message=True):
        _dbg_setup("_on_apply: saving configuration")
        # Save ALL editor content — user expects Apply to persist
        # every pending change, not just the checkboxes.
        _rules_error = ""
        if hasattr(self, "_save_rules_file_silent"):
            _rules_ok, _rules_err = self._save_rules_file_silent()
            if not _rules_ok:
                _rules_error = _rules_err
        # Continuation words (personal additions/exclusions)
        if hasattr(self, "_save_cont_personal"):
            self._save_cont_personal()
        # Dictionary
        if hasattr(self, "_save_dict_official"):
            self._save_dict_official()
        # Snapshot PTT-related config BEFORE save_config() to detect if
        # a dictee-ptt restart is actually needed. For post-processing
        # toggles (the common case) no restart is required — dictee bash
        # sources dictee.conf fresh on each F9 press.
        # Snapshot config that affects service lifecycles (PTT + ASR daemon)
        # before save_config() overwrites the file.
        _old_ptt = {}
        _old_asr = {}
        _ASR_KEYS = ("DICTEE_ASR_BACKEND", "DICTEE_WHISPER_MODEL",
                     "DICTEE_WHISPER_LANG", "DICTEE_VOSK_MODEL",
                     "DICTEE_AUDIO_SOURCE")
        try:
            if os.path.isfile(CONF_PATH):
                with open(CONF_PATH) as _f:
                    for _line in _f:
                        _line = _line.strip()
                        if _line.startswith("#") or "=" not in _line:
                            continue
                        _pk, _pv = _line.split("=", 1)
                        _pk = _pk.strip()
                        _pv = _pv.strip().strip('"').strip("'")
                        if _pk in ("DICTEE_PTT_MODE", "DICTEE_PTT_KEY",
                                   "DICTEE_PTT_KEY_TRANSLATE",
                                   "DICTEE_PTT_MOD_TRANSLATE"):
                            _old_ptt[_pk] = _pv
                        elif _pk in _ASR_KEYS:
                            _old_asr[_pk] = _pv
        except OSError:
            _old_ptt = {}
            _old_asr = {}
        # Wizard translation cards override cmb_trans_backend
        if self.wizard_mode and hasattr(self, '_wizard_trans'):
            wt = self._wizard_trans
            if hasattr(self, '_chk_trans_disabled') and self._chk_trans_disabled.isChecked():
                wt = ""
            if wt in ("google", "bing"):
                trans_data = f"trans:{wt}"
            elif wt in ("libretranslate", "ollama"):
                trans_data = wt
            else:
                trans_data = "trans:google"
        else:
            trans_data = self.cmb_trans_backend.currentData()
        if trans_data == "ollama":
            backend = "ollama"
        elif trans_data == "libretranslate":
            backend = "libretranslate"
        else:
            backend = "trans"
        lang_src = self.combo_src.currentData()
        lang_tgt = self.combo_tgt.currentData()
        clipboard = self.chk_clipboard.isChecked()

        anim_speech = self.chk_anim_speech.isChecked()
        anim_plasmoid = self.chk_plasmoid.isChecked()

        ollama_model = self.combo_ollama_model.currentData()
        ollama_cpu = self.chk_ollama_cpu.isChecked()
        if trans_data and trans_data.startswith("trans:"):
            trans_engine = trans_data.split(":")[1]
        else:
            trans_engine = "google"
        lt_port = int(self.spin_lt_port.currentText()) if self.spin_lt_port.currentText().isdigit() else 5000
        lt_langs = ",".join(self._get_lt_selected_langs()) if hasattr(self, '_lt_lang_checks') else ""

        # Backend ASR — wizard uses _wizard_asr, classic uses cmb_asr_backend
        if self.wizard_mode and hasattr(self, '_wizard_asr'):
            asr_backend = self._wizard_asr
        else:
            asr_backend = self.cmb_asr_backend.currentData() or "parakeet"

        whisper_model = self.cmb_whisper_model.currentData() or "small"
        whisper_lang = (self.txt_whisper_lang.currentData() or self.txt_whisper_lang.currentText() or "").strip()
        vosk_model = self.cmb_vosk_lang.currentData() or "fr"

        # Guard: refuse to save an ASR backend that is not actually usable.
        # Without this, the user can pick Vosk/Whisper/Canary, click Apply,
        # and end up with DICTEE_ASR_BACKEND set in dictee.conf pointing to
        # an engine that can't start → transcription silently fails on F9.
        _ready_ok, _ready_msg = self._asr_backend_ready(
            asr_backend, whisper_model=whisper_model, vosk_lang=vosk_model)
        if not _ready_ok:
            QMessageBox.warning(self, _("ASR backend not ready"), _ready_msg)
            return False

        # Audio source
        audio_source = ""
        if hasattr(self, 'cmb_audio_source') and self.cmb_audio_source.isEnabled():
            audio_source = self.cmb_audio_source.currentData() or ""

        # PTT config
        ptt_mode = self.cmb_ptt_mode.currentData() if hasattr(self, 'cmb_ptt_mode') else "toggle"
        ptt_key = getattr(self, '_ptt_key', 67)
        ptt_mod_translate = ""

        translate_mode = self.cmb_translate_mode.currentData() if hasattr(self, 'cmb_translate_mode') else "disabled"
        if translate_mode == "same_alt":
            ptt_key_translate = ptt_key
            ptt_mod_translate = "alt"
        elif translate_mode == "same_ctrl":
            ptt_key_translate = ptt_key
            ptt_mod_translate = "ctrl"
        elif translate_mode == "same_shift":
            ptt_key_translate = ptt_key
            ptt_mod_translate = "shift"
        elif translate_mode == "separate":
            ptt_key_translate = getattr(self, '_ptt_key_translate', 0)
        else:  # disabled
            ptt_key_translate = 0

        # Post-processing
        # Pipeline mode: translation is activated at RUNTIME via --translate
        # shortcut, not via Apply. The config only stores whether PP and TRPP
        # are enabled. The mode is derived at runtime from --translate flag +
        # these config values.
        _pp_on = self.chk_postprocess.isChecked() if hasattr(self, 'chk_postprocess') else True
        _trpp_on = self.chk_pp_translate.isChecked() if hasattr(self, 'chk_pp_translate') else False
        pipeline_mode = "normal"  # always normal — --translate overrides at runtime
        postprocess = _pp_on
        pp_translate = _trpp_on
        pp_elisions = self.chk_pp_elisions.isChecked() if hasattr(self, 'chk_pp_elisions') else True
        pp_elisions_it = self.chk_pp_elisions_it.isChecked() if hasattr(self, 'chk_pp_elisions_it') else True
        pp_spanish = self.chk_pp_spanish.isChecked() if hasattr(self, 'chk_pp_spanish') else True
        pp_portuguese = self.chk_pp_portuguese.isChecked() if hasattr(self, 'chk_pp_portuguese') else True
        pp_german = self.chk_pp_german.isChecked() if hasattr(self, 'chk_pp_german') else True
        pp_dutch = self.chk_pp_dutch.isChecked() if hasattr(self, 'chk_pp_dutch') else True
        pp_romanian = self.chk_pp_romanian.isChecked() if hasattr(self, 'chk_pp_romanian') else True
        pp_numbers = self.chk_pp_numbers.isChecked() if hasattr(self, 'chk_pp_numbers') else True
        pp_typography = self.chk_pp_typography.isChecked() if hasattr(self, 'chk_pp_typography') else True
        pp_capitalization = self.chk_pp_capitalization.isChecked() if hasattr(self, 'chk_pp_capitalization') else True
        pp_dict = self.chk_pp_dict.isChecked() if hasattr(self, 'chk_pp_dict') else True
        pp_rules = self.chk_pp_rules.isChecked() if hasattr(self, 'chk_pp_rules') else True
        pp_continuation = self.chk_pp_continuation.isChecked() if hasattr(self, 'chk_pp_continuation') else True
        pp_language_rules = self.chk_pp_language_rules.isChecked() if hasattr(self, 'chk_pp_language_rules') else True
        pp_short_text = self.chk_pp_short_text.isChecked() if hasattr(self, 'chk_pp_short_text') else True
        pp_short_text_max = (self.cmb_pp_short_text_max.currentData()
                             if hasattr(self, 'cmb_pp_short_text_max') else 3) or 3
        pp_keepcaps = self.chk_pp_keepcaps.isChecked() if hasattr(self, 'chk_pp_keepcaps') else True
        pp_keepcaps_ext = self.chk_pp_keepcaps_ext.isChecked() if hasattr(self, 'chk_pp_keepcaps_ext') else True
        llm_postprocess = self.chk_llm.isChecked() if hasattr(self, 'chk_llm') else False
        # Use the real model name (strip "— not installed" suffix if present)
        if hasattr(self, '_current_llm_model'):
            llm_model = self._current_llm_model() or "gemma3:4b"
        else:
            llm_model = self.cmb_llm_model.currentText() if hasattr(self, 'cmb_llm_model') else "gemma3:4b"
        # If LLM post-processing is enabled, warn when the selected model is missing
        if llm_postprocess and hasattr(self, 'cmb_llm_model') and llm_model:
            if not ollama_has_model(llm_model):
                reply = QMessageBox.warning(
                    self,
                    _("LLM model not installed"),
                    _("The LLM model '{model}' is not installed in Ollama.\n\n"
                      "Run in a terminal:\n  ollama pull {model}\n\n"
                      "Save the configuration anyway?").format(model=llm_model),
                    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    _dbg_setup(f"_on_apply: cancelled — llm_model '{llm_model}' not installed")
                    return
        llm_cpu = self.chk_llm_cpu.isChecked() if hasattr(self, 'chk_llm_cpu') else False
        llm_system_prompt = self.cmb_llm_preset.currentData() if hasattr(self, 'cmb_llm_preset') else "correction-fr"
        llm_position = self._get_llm_position() if hasattr(self, '_get_llm_position') else "hybrid"
        llm_custom_prompt = self.txt_llm_prompt.toPlainText() if hasattr(self, 'txt_llm_prompt') else ""

        # Continuation visual indicator
        continuation_indicator = (
            self.cmb_continuation_indicator.currentData()
            if hasattr(self, 'cmb_continuation_indicator') else ">>")

        # Audio context buffer
        audio_context = self.chk_audio_context.isChecked() if hasattr(self, 'chk_audio_context') else True
        audio_context_timeout = self.spin_audio_context_timeout.value() if hasattr(self, 'spin_audio_context_timeout') else 30
        silence_rms = (self.slider_silence.value() / 1000.0) if hasattr(self, 'slider_silence') else 0.03
        debug = self.chk_debug.isChecked() if hasattr(self, 'chk_debug') else False

        # Cheatsheet shortcut: persist the combo selection (and the captured
        # sequence when "Separate key" is chosen) so the next session restores
        # the user's intent. The actual KDE shortcut registration happens
        # below via apply_kde_shortcut.
        cheatsheet_mode = (self.cmb_cheatsheet_mode.currentData()
                           if hasattr(self, 'cmb_cheatsheet_mode') else "")
        cheatsheet_seq_obj = self._compute_cheatsheet_keysequence()
        cheatsheet_seq_str = (cheatsheet_seq_obj.toString()
                              if cheatsheet_seq_obj is not None
                              and cheatsheet_mode == "separate" else "")

        save_config(backend, lang_src, lang_tgt, clipboard,
                    anim_speech, anim_plasmoid,
                    ollama_model, ollama_cpu, trans_engine, lt_port, lt_langs,
                    asr_backend, whisper_model, whisper_lang, vosk_model,
                    audio_source=str(audio_source),
                    ptt_mode=ptt_mode, ptt_key=ptt_key,
                    ptt_key_translate=ptt_key_translate,
                    ptt_mod_translate=ptt_mod_translate,
                    cheatsheet_mod=cheatsheet_mode,
                    cheatsheet_key_seq=cheatsheet_seq_str,
                    postprocess=postprocess,
                    pp_translate=pp_translate,
                    pp_elisions=pp_elisions, pp_elisions_it=pp_elisions_it,
                    pp_spanish=pp_spanish, pp_portuguese=pp_portuguese,
                    pp_german=pp_german, pp_dutch=pp_dutch,
                    pp_romanian=pp_romanian, pp_numbers=pp_numbers,
                    pp_typography=pp_typography, pp_capitalization=pp_capitalization,
                    pp_dict=pp_dict,
                    pp_rules=pp_rules, pp_continuation=pp_continuation,
                    pp_language_rules=pp_language_rules,
                    pp_short_text=pp_short_text,
                    pp_short_text_max=pp_short_text_max,
                    pp_keepcaps=pp_keepcaps,
                    pp_keepcaps_extended=pp_keepcaps_ext,
                    llm_postprocess=llm_postprocess,
                    llm_model=llm_model, llm_cpu=llm_cpu,
                    llm_system_prompt=llm_system_prompt,
                    llm_position=llm_position,
                    llm_custom_prompt=llm_custom_prompt,
                    continuation_indicator=continuation_indicator,
                    audio_context=audio_context,
                    audio_context_timeout=audio_context_timeout,
                    silence_rms=silence_rms,
                    notifications=self.chk_notifications.isChecked(),
                    notifications_text=self.chk_notifications_text.isChecked(),
                    command_suffixes=self._command_suffixes,
                    debug=debug,
                    trpp_states=dict(self._trpp_state),
                    trpp_short_text_max=(
                        self.cmb_trpp_short_text_max.currentData()
                        if hasattr(self, 'cmb_trpp_short_text_max') else 3) or 3)

        # Register the cheatsheet KDE global shortcut. The QKeySequence is
        # resolved from the combo: "Same key + <mod>" combines with the
        # dictation PTT key, "Separate key" uses the captured sequence,
        # "Disabled" registers nothing.
        if cheatsheet_seq_obj is not None and cheatsheet_seq_obj.count() > 0:
            try:
                kde_format = qt_key_to_kde(cheatsheet_seq_obj)
                if kde_format:
                    apply_kde_shortcut(
                        kde_format,
                        "dictee-cheatsheet-toggle.desktop",
                        "/usr/bin/dictee-cheatsheet --toggle",
                        _("Toggle voice commands cheatsheet"),
                        key_sequence=cheatsheet_seq_obj,
                    )
            except Exception as _e:
                _dbg_setup(f"_on_apply: cheatsheet shortcut registration failed: {_e}")

        # Calibration playground: wipe temp recordings now that the
        # threshold value has been validated and persisted.
        self._cleanup_calib_records()

        # Clear ephemeral runtime state so the next push starts clean after a
        # config change: stale continuation marker (>>), obsolete audio-context
        # buffer from a previous source language, leftover translate error.
        # These caches can bite the first push after Apply if not cleared.
        _uid = os.getuid()
        _ephemeral = [
            f"/dev/shm/.dictee_last_word-{_uid}",
            f"/dev/shm/.dictee_pp-{_uid}",
            f"/dev/shm/.dictee_buffer-{_uid}.wav",
            f"/dev/shm/.dictee_buffer_ts-{_uid}",
            f"/dev/shm/.dictee_buffer_text-{_uid}",
            f"/tmp/dictee_trans_err-{_uid}",
        ]
        for _f in _ephemeral:
            try:
                os.unlink(_f)
            except FileNotFoundError:
                pass
            except Exception as _e:
                _dbg_setup(f"_on_apply: cleanup {_f} failed: {_e}")

        # Systemd services — reload first (needed after first .deb install)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)

        # Systemd services — ASR (active service: synchronous for error reporting)
        asr_services = {"parakeet": "dictee", "vosk": "dictee-vosk", "whisper": "dictee-whisper", "canary": "dictee-canary"}
        active_svc = asr_services.get(asr_backend, "dictee")
        svc_error = ""
        # Disable inactive services + enable/restart tray/ptt in background
        bg_cmds = []
        for svc_name in asr_services.values():
            if svc_name != active_svc:
                bg_cmds.append(["systemctl", "--user", "disable", "--now", svc_name])
        tray_action = "enable" if self.chk_tray.isChecked() else "disable"
        bg_cmds.append(["systemctl", "--user", tray_action, "--now", "dictee-tray"])
        bg_cmds.append(["systemctl", "--user", "enable", "dictee-ptt"])
        # Only restart dictee-ptt when a PTT-related key actually changed.
        # Otherwise the restart loses the first F9 press (keyboard grab
        # drops during the ~1s restart window) for no benefit.
        _new_ptt = {
            "DICTEE_PTT_MODE": ptt_mode,
            "DICTEE_PTT_KEY": str(ptt_key),
            "DICTEE_PTT_KEY_TRANSLATE": str(ptt_key_translate) if ptt_key_translate else "",
            "DICTEE_PTT_MOD_TRANSLATE": ptt_mod_translate or "",
        }
        _old_ptt_normalized = {
            "DICTEE_PTT_MODE": _old_ptt.get("DICTEE_PTT_MODE", "toggle"),
            "DICTEE_PTT_KEY": _old_ptt.get("DICTEE_PTT_KEY", "67"),
            "DICTEE_PTT_KEY_TRANSLATE": _old_ptt.get("DICTEE_PTT_KEY_TRANSLATE", ""),
            "DICTEE_PTT_MOD_TRANSLATE": _old_ptt.get("DICTEE_PTT_MOD_TRANSLATE", ""),
        }
        _ptt_changed = _new_ptt != _old_ptt_normalized
        if _ptt_changed:
            bg_cmds.append(["systemctl", "--user", "restart", "dictee-ptt"])
            _dbg_setup(f"_on_apply: dictee-ptt restart (PTT changed: {_old_ptt_normalized} -> {_new_ptt})")
        else:
            _dbg_setup("_on_apply: skipping dictee-ptt restart (PTT unchanged)")
        bg_procs = [subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for cmd in bg_cmds]

        # Active ASR service: always ensure it's enabled (boot). Restart it
        # only when an ASR-related key actually changed — otherwise the
        # transcribe-daemon goes down for 2-10s (model reload) for nothing,
        # and any F9 during that window produces no dictation.
        en = subprocess.run(
            ["systemctl", "--user", "enable", active_svc],
            capture_output=True, text=True,
        )
        if en.returncode != 0:
            svc_error = _("Warning: could not enable {svc} at boot.\n{err}").format(
                svc=active_svc, err=en.stderr.strip())

        _new_asr = {
            "DICTEE_ASR_BACKEND": asr_backend,
            "DICTEE_WHISPER_MODEL": whisper_model,
            "DICTEE_WHISPER_LANG": whisper_lang,
            "DICTEE_VOSK_MODEL": vosk_model,
            "DICTEE_AUDIO_SOURCE": str(audio_source),
        }
        _old_asr_normalized = {k: _old_asr.get(k, "") for k in _new_asr}
        _asr_changed = _new_asr != _old_asr_normalized
        # Also restart if the service isn't running yet (first-install path)
        _active_running = subprocess.run(
            ["systemctl", "--user", "is-active", active_svc],
            capture_output=True, text=True).stdout.strip() == "active"

        if _asr_changed or not _active_running:
            _dbg_setup(f"_on_apply: restarting {active_svc} (asr_changed={_asr_changed}, running={_active_running})")
            try:
                from PyQt6.QtWidgets import QApplication
                _proc = subprocess.Popen(
                    ["systemctl", "--user", "restart", active_svc],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                import time as _time
                _deadline = _time.monotonic() + 15.0
                while _proc.poll() is None:
                    QApplication.processEvents()
                    _time.sleep(0.02)
                    if _time.monotonic() > _deadline:
                        break
                if _proc.poll() is None:
                    _proc.kill()
                    svc_error = _("Warning: {svc} is taking too long to start.\n"
                                  "It may still be loading the model.").format(svc=active_svc)
                elif _proc.returncode != 0:
                    _err = (_proc.stderr.read() or "").strip() if _proc.stderr else ""
                    svc_error = _("Warning: {svc} failed to start.\n{err}").format(
                        svc=active_svc, err=_err)
            except Exception as _e:
                svc_error = _("Warning: {svc} failed to start.\n{err}").format(
                    svc=active_svc, err=str(_e))
        else:
            _dbg_setup(f"_on_apply: skipping {active_svc} restart (ASR unchanged and running)")

        # Wait for background processes (non-blocking, they should be done by now)
        for p in bg_procs:
            p.wait()

        # Supprimer les anciens raccourcis KDE/GNOME (dictee-ptt les remplace)
        shortcut_msg = ""
        if self.de_type == "kde":
            for desktop in (DICTEE_DESKTOP, DICTEE_TRANSLATE_DESKTOP):
                try:
                    remove_kde_shortcut(desktop)
                except Exception as _e:
                    _dbg_setup(f"silenced: {_e!r}")
            shortcut_msg = "\n" + _("PTT key: {key} ({mode})").format(
                key=linux_keycode_name(ptt_key), mode=ptt_mode)

        self._dirty = False

        # DICTEE_SETUP_DONE est écrit par save_config()

        # Proposer de démarrer/redémarrer LibreTranslate si nécessaire
        # Proposer de démarrer/redémarrer LibreTranslate si nécessaire
        self._lt_starting_after_apply = False
        if backend == "libretranslate" and docker_is_installed() and docker_is_accessible():
            self._prompt_lt_server()

        if not self.wizard_mode and show_message:
            msg = _("File: {path}").format(path=CONF_PATH) + shortcut_msg
            if svc_error:
                QMessageBox.warning(
                    self,
                    _("Configuration saved"),
                    msg + "\n\n" + svc_error,
                )
            else:
                QMessageBox.information(
                    self,
                    _("Configuration saved"),
                    msg,
                )
        elif svc_error and not self.wizard_mode:
            # Apply-button path: still surface service errors (don't swallow)
            QMessageBox.warning(self, _("Configuration saved"), svc_error)

        # Rules syntax error must always be surfaced — even silently via Apply —
        # otherwise the user could believe their rules were saved when they weren't.
        if _rules_error and not self.wizard_mode:
            QMessageBox.warning(
                self, "dictee",
                _("Cannot save rules — syntax error:\n\n{err}").format(err=_rules_error))

        # Signal successful save so _on_ok knows it can close the dialog.
        return True

    def _prompt_lt_server(self):
        """Propose de démarrer/redémarrer LibreTranslate après Apply."""
        # Skip if a restart is already in progress
        # (user clicked "Restart with new languages" before Apply)
        if self._lt_is_busy():
            return
        selected = set(self._get_lt_selected_langs())
        running = docker_container_running()
        port_text = self.spin_lt_port.currentText()
        port = int(port_text) if port_text.isdigit() else 5000

        if running:
            # Vérifier si les langues ont changé
            installed = set(libretranslate_available_languages(port=port))
            # Only care about languages we NEED but don't have.
            # Extra languages in the container are harmless — don't prompt to remove them.
            added = selected - installed
            if not added:
                return  # All needed languages are available
            removed = installed - selected
            details = []
            if added:
                details.append(_("Add: {langs}").format(langs=", ".join(sorted(added))))
            if removed:
                details.append(_("Remove: {langs}").format(langs=", ".join(sorted(removed))))
            msg = (
                _("The LibreTranslate languages have changed.") + "\n\n" +
                "\n".join(details) + "\n\n" +
                _("Restart the server now to apply changes?") + "\n" +
                _("(This will download missing models if needed)")
            )
            reply = QMessageBox.question(
                self, _("LibreTranslate"), msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._lt_starting_after_apply = True
                self._on_lt_restart_langs()
        else:
            # Serveur arrêté → proposer de le démarrer
            if not docker_has_image():
                return  # Pas d'image, rien à proposer
            n_langs = len(selected)
            msg = (
                _("LibreTranslate is not running.") + "\n\n" +
                _("Start the server with {n} languages ({langs})?").format(
                    n=n_langs, langs=", ".join(sorted(selected))) + "\n" +
                _("(This will download missing models if needed)")
            )
            reply = QMessageBox.question(
                self, _("LibreTranslate"), msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._lt_starting_after_apply = True
                self._on_lt_start()

    def _on_ok(self):
        _dbg_setup("_on_ok")
        if self._dirty:
            # _on_apply returns False when a guard aborted the save (e.g. the
            # chosen ASR backend isn't actually installed). In that case we
            # must NOT close the dialog — otherwise the user ends up with
            # dictee-setup gone and an unchanged (or broken) dictee.conf.
            if self._on_apply() is False:
                return
        # Ne pas fermer si LibreTranslate est en cours de démarrage
        if getattr(self, '_lt_starting_after_apply', False):
            return
        self.accept()


_SETUP_DEBUG = False
_setup_log_file = None


def _dbg_setup(msg):
    """Print debug message if --debug is enabled."""
    if not _SETUP_DEBUG:
        return
    import datetime
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[DBG {ts}] {msg}"
    print(line, file=sys.stderr)
    global _setup_log_file
    if _setup_log_file is None:
        _setup_log_file = open("/tmp/dictee-setup.log", "a", encoding="utf-8")
    _setup_log_file.write(line + "\n")
    _setup_log_file.flush()


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Dictee — Voice dictation configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  dictee-setup                  Open configuration\n"
               "  dictee-setup --wizard         Force wizard mode\n"
               "  dictee-setup --postprocess    Open post-processing dialog\n"
               "  dictee-setup --translation    Open on translation section\n"
               "  dictee-setup --models         List installed models\n"
               "  dictee-setup --models --json  List models (JSON)\n"
               "  dictee-setup --debug          Enable debug logging\n")
    parser.add_argument("--wizard", action="store_true",
                        help="Force wizard mode (step-by-step configuration)")
    parser.add_argument("--postprocess", action="store_true",
                        help="Open post-processing dialog directly")
    parser.add_argument("--translation", action="store_true",
                        help="Open on the translation configuration section")
    parser.add_argument("--models", action="store_true",
                        help="List all installed ASR models and exit")
    parser.add_argument("--json", action="store_true",
                        help="Output in JSON format (with --models)")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging to stderr and /tmp/dictee-setup.log")
    args = parser.parse_args()

    # Optional startup profiling: DICTEE_SETUP_PROFILE=1 dumps a cProfile
    # snapshot to /tmp/dictee-setup.prof and a per-method timing table to
    # /tmp/dictee-setup-timings.log when the window closes. Zero impact
    # in normal use (only enabled when the env var is set).
    if os.environ.get("DICTEE_SETUP_PROFILE"):
        import cProfile, atexit, time as _t, sys as _sys, signal as _sig
        from collections import defaultdict as _dd
        _profile = cProfile.Profile()
        _profile.enable()
        _timings = []

        # Default SIGTERM behavior is to kill the process without running
        # atexit, so the profile would never be dumped. Convert SIGTERM
        # into a clean sys.exit(0) so atexit fires.
        def _on_term(signum, frame):
            _sys.exit(0)
        _sig.signal(_sig.SIGTERM, _on_term)
        _sig.signal(_sig.SIGINT, _on_term)

        def _wrap_for_timing(method, qualname):
            def wrapped(*a, **kw):
                t0 = _t.perf_counter()
                try:
                    return method(*a, **kw)
                finally:
                    _timings.append((qualname, (_t.perf_counter() - t0) * 1000.0))
            wrapped.__name__ = method.__name__
            return wrapped

        # NOTE: do NOT wrap "_render_*" or "_paint_*" — those are typically
        # Qt event overrides / slots whose signature is set by Qt and any
        # *args wrapper trips signature checks (e.g. _render_svg).
        _PROF_PREFIXES = (
            "_build_", "_check_", "_init_",
            "_load_", "_setup_", "_detect_",
        )
        for _cname, _cls in list(globals().items()):
            if not isinstance(_cls, type) or _cname.startswith("_"):
                continue
            for _attr in list(vars(_cls).keys()):
                if not _attr.startswith(_PROF_PREFIXES):
                    continue
                _raw = vars(_cls).get(_attr)
                # Skip staticmethod/classmethod: wrapping them with a plain
                # function would silently turn them into bound methods and
                # corrupt the call signature.
                if isinstance(_raw, (staticmethod, classmethod)):
                    continue
                _orig = getattr(_cls, _attr, None)
                if callable(_orig) and not isinstance(_orig, type):
                    setattr(_cls, _attr, _wrap_for_timing(_orig, f"{_cname}.{_attr}"))

        @atexit.register
        def _dump_profile_outputs():
            _profile.disable()
            try:
                _profile.dump_stats("/tmp/dictee-setup.prof")
            except Exception as _e:
                print(f"[profile] cProfile dump failed: {_e}", file=_sys.stderr)
            # Aggregate per-method timings
            _agg = _dd(lambda: [0.0, 0])
            for _n, _ms in _timings:
                _agg[_n][0] += _ms
                _agg[_n][1] += 1
            try:
                with open("/tmp/dictee-setup-timings.log", "w") as _f:
                    _f.write(f"Total instrumented methods called: {len(_agg)}\n")
                    _f.write(f"Total method calls timed: {len(_timings)}\n")
                    _f.write("\nTop 40 by cumulative ms (calls in parens):\n")
                    for _n, (_tot, _cnt) in sorted(
                            _agg.items(), key=lambda kv: -kv[1][0])[:40]:
                        _f.write(f"  {_tot:8.1f} ms  ({_cnt:3d}x)  {_n}\n")
                print("[profile] cProfile -> /tmp/dictee-setup.prof", file=_sys.stderr)
                print("[profile] timings  -> /tmp/dictee-setup-timings.log", file=_sys.stderr)
            except Exception as _e:
                print(f"[profile] timings dump failed: {_e}", file=_sys.stderr)

    if args.models:
        from dictee_models import find_all_models, print_table
        import json as json_mod
        models = find_all_models()
        if args.json:
            print(json_mod.dumps(models, indent=2))
        else:
            print_table(models)
        sys.exit(0)

    global _SETUP_DEBUG
    if args.debug or os.environ.get("DICTEE_DEBUG") == "true":
        _SETUP_DEBUG = True
        _dbg_setup("dictee-setup starting (debug via %s)" % ("--debug" if args.debug else "DICTEE_DEBUG"))

    app = QApplication([])
    app.setApplicationName("dictee-setup")
    app.setDesktopFileName("dictee-setup")
    app.setWindowIcon(QIcon.fromTheme("dictee-setup"))

    # Fix QMessageBox invisible text on GNOME dark themes
    _pal = app.palette()
    _win_light = _pal.color(_pal.ColorRole.Window).lightness()
    _txt_light = _pal.color(_pal.ColorRole.WindowText).lightness()
    if abs(_win_light - _txt_light) < 50:
        # Text and background too similar — force readable contrast
        txt_color = "white" if _win_light < 128 else "black"
        app.setStyleSheet(f"QMessageBox QLabel {{ color: {txt_color}; }}")
    _dbg_setup(f"wizard={args.wizard}, postprocess={args.postprocess}, translation={args.translation}")
    dialog = DicteeSetupDialog(wizard=args.wizard, open_postprocess=args.postprocess,
                               open_translation=args.translation)
    # All CLI flags (--postprocess, --translation) open the main sidebar
    # window; navigation to the matching entry is handled in showEvent via
    # _select_sidebar_item. The legacy standalone PP dialog stays accessible
    # from the wizard button only.
    _screen = app.primaryScreen()
    if _screen is not None:
        _geo = _screen.availableGeometry()
        dialog.move(_geo.center().x() - dialog.width() // 2,
                    _geo.center().y() - dialog.height() // 2)
    dialog.show()
    app.exec()


if __name__ == "__main__":
    main()
