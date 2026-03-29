#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dictee-transcribe — Audio file transcription & diarization UI
PyQt6 window to transcribe audio files with optional speaker identification.
Supports PyQt6 (preferred) and PySide6 (fallback).
"""

import argparse
import gettext
import json
import os
import re
import subprocess
import sys
import time

try:
    from PyQt6.QtCore import (Qt, QProcess, QByteArray, QThread, QTimer,
                               QProcessEnvironment, QFileSystemWatcher,
                               pyqtSignal as Signal)
    from PyQt6.QtGui import QIcon, QShortcut, QKeySequence, QTextDocument
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QComboBox, QProgressBar, QCheckBox,
        QTextEdit, QFileDialog, QLineEdit, QWidget, QTabWidget, QGroupBox,
    )
except ImportError:
    from PySide6.QtCore import (Qt, QProcess, QByteArray, QThread, QTimer,
                                QProcessEnvironment, QFileSystemWatcher,
                                Signal)
    from PySide6.QtGui import QIcon, QShortcut, QKeySequence, QTextDocument
    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QComboBox, QProgressBar, QCheckBox,
        QTextEdit, QFileDialog, QLineEdit, QWidget, QTabWidget, QGroupBox,
    )

# === i18n ===

LOCALE_DIRS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "share", "locale"),
    os.path.expanduser("~/.local/share/locale"),
    "/usr/local/share/locale",
    "/usr/share/locale",
]

for _d in LOCALE_DIRS:
    if os.path.isfile(os.path.join(_d, "fr", "LC_MESSAGES", "dictee.mo")):
        gettext.bindtextdomain("dictee", _d)
        break

gettext.textdomain("dictee")
_ = gettext.gettext

# === Debug ===

DEBUG = False
_log_file = None


def _dbg(msg):
    """Print debug message if --debug is enabled."""
    if not DEBUG:
        return
    import datetime
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[DBG {ts}] {msg}"
    print(line, file=sys.stderr)
    global _log_file
    if _log_file is None:
        _log_file = open("/tmp/dictee-transcribe.log", "a", encoding="utf-8")
    _log_file.write(line + "\n")
    _log_file.flush()


# === Constants ===

AUDIO_FILTER = _("Audio files") + " (*.wav *.mp3 *.flac *.ogg *.m4a *.webm *.opus);;All files (*)"

# Colors that contrast well on both light and dark backgrounds
SPEAKER_COLORS = [
    "#e06c75",  # red
    "#61afef",  # blue
    "#98c379",  # green
    "#d19a66",  # orange
]

DIARIZE_RE = re.compile(
    r"\[(\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]\s*(Speaker\s+\d+|UNKNOWN):\s*(.*)"
)


# === Configuration ===

CONF_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "dictee.conf",
)


def _read_conf():
    """Read dictee.conf into a dict."""
    conf = {}
    if os.path.isfile(CONF_PATH):
        with open(CONF_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    conf[k] = v.strip().strip('"').strip("'")
    return conf


def _detect_language(text):
    """Simple language detection based on common words and characters."""
    text_lower = text.lower()
    scores = {
        "en": 0, "fr": 0, "de": 0, "es": 0, "it": 0, "pt": 0,
        "uk": 0, "ru": 0, "nl": 0, "pl": 0, "zh": 0, "ja": 0,
        "ko": 0, "ar": 0,
    }
    # Common words per language
    markers = {
        "en": ["the ", " is ", " are ", " was ", " have ", " that ", " with ", " this "],
        "fr": [" le ", " la ", " les ", " des ", " est ", " que ", " dans ", " une ", " qui "],
        "de": [" der ", " die ", " das ", " und ", " ist ", " ein ", " nicht ", " den "],
        "es": [" el ", " los ", " las ", " que ", " por ", " una ", " con ", " del "],
        "it": [" il ", " che ", " di ", " una ", " per ", " con ", " sono ", " della "],
        "pt": [" que ", " uma ", " com ", " para ", " dos ", " das ", " não "],
        "nl": [" het ", " een ", " van ", " dat ", " niet ", " zijn "],
        "pl": [" nie ", " jest ", " się ", " że ", " jak "],
        "ru": [" не ", " что ", " это ", " как ", " для "],
        "uk": [" не ", " що ", " це ", " як ", " для ", " або "],
    }
    # Character-based detection for non-Latin scripts
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            scores["zh"] += 5
        elif "\u3040" <= ch <= "\u30ff":
            scores["ja"] += 5
        elif "\uac00" <= ch <= "\ud7af":
            scores["ko"] += 5
        elif "\u0600" <= ch <= "\u06ff":
            scores["ar"] += 5
        elif "\u0400" <= ch <= "\u04ff":
            # Cyrillic — differentiate Ukrainian vs Russian
            scores["ru"] += 1
            scores["uk"] += 1
    # Ukrainian-specific characters
    for uk_ch in "іїєґ":
        if uk_ch in text_lower:
            scores["uk"] += 10
    # Word-based detection for Latin scripts
    for lang, words in markers.items():
        for w in words:
            scores[lang] += text_lower.count(w)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "en"


def _translate_available():
    """Check if any translation backend is configured and usable."""
    import shutil
    conf = _read_conf()
    backend = conf.get("DICTEE_TRANSLATE_BACKEND", "trans")
    if backend == "trans":
        return shutil.which("trans") is not None
    if backend == "ollama":
        return shutil.which("ollama") is not None
    if backend == "libretranslate":
        return shutil.which("docker") is not None
    return False


def _translate_text(text, lang_src="en", lang_tgt="fr"):
    """Translate text using the configured backend. Returns translated text or None."""
    conf = _read_conf()
    backend = conf.get("DICTEE_TRANSLATE_BACKEND", "trans")
    _dbg(f"_translate_text: backend={backend}, {lang_src}→{lang_tgt}, text_len={len(text)}")

    try:
        if backend == "trans":
            engine = conf.get("DICTEE_TRANS_ENGINE", "google")
            result = subprocess.run(
                ["trans", "-b", "-e", engine, f"{lang_src}:{lang_tgt}"],
                input=text, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

        elif backend == "ollama":
            import json as _json
            import urllib.request
            _LANG_NAMES = {
                "en": "English", "fr": "French", "de": "German",
                "es": "Spanish", "it": "Italian", "pt": "Portuguese",
                "uk": "Ukrainian", "nl": "Dutch", "pl": "Polish",
                "ru": "Russian", "zh": "Chinese", "ja": "Japanese",
                "ko": "Korean", "ar": "Arabic",
            }
            model = conf.get("DICTEE_OLLAMA_MODEL", "translategemma")
            if ":" not in model:
                model += ":latest"
            src_name = _LANG_NAMES.get(lang_src, lang_src)
            tgt_name = _LANG_NAMES.get(lang_tgt, lang_tgt)
            prompt = (
                f"You are a professional {src_name} to {tgt_name} translator. "
                f"Produce only the {tgt_name} translation, without any additional "
                f"explanations or commentary. Please translate the following text:\n\n{text}"
            )
            payload = _json.dumps({
                "model": model,
                "prompt": prompt,
                "stream": False,
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=120)
            data = _json.loads(resp.read().decode("utf-8"))
            response = data.get("response", "").strip()
            if response:
                return response

        elif backend == "libretranslate":
            import json as _json
            import urllib.request
            port = conf.get("DICTEE_LIBRETRANSLATE_PORT", "5000")
            payload = _json.dumps({
                "q": text, "source": lang_src, "target": lang_tgt,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"http://localhost:{port}/translate",
                data=payload,
                headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=15)
            data = _json.loads(resp.read().decode("utf-8"))
            return data.get("translatedText", "")
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        _dbg(f"_translate_text: exception {type(e).__name__}: {e}")
    return None


# === Helpers ===

def _sortformer_available():
    """Check if the Sortformer diarization model is installed."""
    dd = os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
        "dictee", "sortformer",
    )
    return os.path.isdir("/usr/share/dictee/sortformer") or os.path.isdir(dd)


def _parse_diarize_output(text):
    """Parse transcribe-diarize output into segments."""
    segments = []
    for line in text.splitlines():
        m = DIARIZE_RE.match(line.strip())
        if m:
            segments.append({
                "start": float(m.group(1)),
                "end": float(m.group(2)),
                "speaker": m.group(3),
                "text": m.group(4).strip(),
            })
    return segments


def _seconds_to_srt_time(seconds):
    """Convert seconds to SRT timestamp HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_text(segments):
    """Format diarized segments as plain text with speaker headers."""
    lines = []
    prev_speaker = None
    for seg in segments:
        if seg["speaker"] != prev_speaker:
            if prev_speaker is not None:
                lines.append("")  # blank line between speakers
            lines.append(f"{seg['speaker']}:")
            prev_speaker = seg["speaker"]
        lines.append(f"     {seg['text']}")
    return "\n".join(lines)


def _format_srt(segments):
    """Format diarized segments as SRT subtitles."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _seconds_to_srt_time(seg["start"])
        end = _seconds_to_srt_time(seg["end"])
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(f"[{seg['speaker']}] {seg['text']}")
        lines.append("")
    return "\n".join(lines)


def _format_json(segments):
    """Format diarized segments as JSON."""
    out = []
    for seg in segments:
        out.append({
            "start": seg["start"],
            "end": seg["end"],
            "speaker": seg["speaker"],
            "text": seg["text"],
        })
    return json.dumps(out, ensure_ascii=False, indent=2)


# === Search Bar ===

class SearchBar(QWidget):
    """Ephemeral search bar for QTextEdit."""

    def __init__(self, text_edit, parent=None):
        super().__init__(parent)
        self._text_edit = text_edit
        self.setVisible(False)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)

        self._input = QLineEdit()
        self._input.setPlaceholderText(_("Search..."))
        self._input.returnPressed.connect(self._find_next)
        lay.addWidget(self._input, 1)

        btn_next = QPushButton(_("Next"))
        btn_next.clicked.connect(self._find_next)
        lay.addWidget(btn_next)

        btn_prev = QPushButton(_("Previous"))
        btn_prev.clicked.connect(self._find_prev)
        lay.addWidget(btn_prev)

        btn_close = QPushButton("\u2715")
        btn_close.setFixedWidth(28)
        btn_close.clicked.connect(self.hide)
        lay.addWidget(btn_close)

    def set_editor(self, text_edit):
        self._text_edit = text_edit

    def activate(self):
        self.setVisible(True)
        self._input.setFocus()
        self._input.selectAll()

    def _find_next(self):
        text = self._input.text()
        if text:
            self._text_edit.find(text)

    def _find_prev(self):
        text = self._input.text()
        if text:
            self._text_edit.find(text, QTextDocument.FindFlag.FindBackward)


# === Translation Thread ===

class TranslateThread(QThread):
    """Translate text in background to avoid blocking UI."""
    finished_signal = Signal(str, list)  # translated_text, translated_segments
    error_signal = Signal(str)  # error message

    def __init__(self, raw_text, segments, was_diarized, lang_src="en", lang_tgt="fr"):
        super().__init__()
        self._raw_text = raw_text
        self._segments = segments
        self._was_diarized = was_diarized
        self._lang_src = lang_src
        self._lang_tgt = lang_tgt

    def run(self):
        try:
            if self._was_diarized and self._segments:
                groups = []
                for i, seg in enumerate(self._segments):
                    if groups and groups[-1][0] == seg["speaker"]:
                        groups[-1][1].append(i)
                    else:
                        groups.append((seg["speaker"], [i]))

                translated_segments = list(self._segments)
                failed = False
                for _speaker, indices in groups:
                    group_text = "\n".join(self._segments[i]["text"] for i in indices)
                    translated = _translate_text(group_text, self._lang_src, self._lang_tgt)
                    if translated:
                        lines = [l.strip() for l in translated.strip().splitlines() if l.strip()]
                        for j, idx in enumerate(indices):
                            new_seg = dict(self._segments[idx])
                            new_seg["text"] = lines[j] if j < len(lines) else self._segments[idx]["text"]
                            translated_segments[idx] = new_seg
                    else:
                        failed = True
                if failed:
                    self.error_signal.emit(_("Translation partially failed — some segments untranslated."))
                self.finished_signal.emit("", translated_segments)
            else:
                translated = _translate_text(self._raw_text, self._lang_src, self._lang_tgt)
                if not translated:
                    self.error_signal.emit(_("Translation failed — check backend configuration."))
                    self.finished_signal.emit(self._raw_text, [])
                else:
                    self.finished_signal.emit(translated, [])
        except Exception as e:
            self.error_signal.emit(str(e))
            self.finished_signal.emit(self._raw_text, self._segments)


# === Export Dialog ===

class ExportDialog(QDialog):
    """Dialog to export one or more tabs in chosen format and directory."""

    def __init__(self, tabs_info, current_format, base_name, parent=None):
        """
        tabs_info: list of (tab_name, text_content)
        current_format: "text", "srt", or "json"
        base_name: base filename from audio file
        """
        super().__init__(parent)
        self.setWindowTitle(_("Export"))
        self.setMinimumWidth(450)

        self._tabs_info = tabs_info
        self._base_name = base_name

        layout = QVBoxLayout(self)

        # -- Tabs to export --
        group = QGroupBox(_("Tabs to export"))
        lay_tabs = QVBoxLayout(group)
        self._tab_checks = []
        for i, (name, _text) in enumerate(tabs_info):
            chk = QCheckBox(name)
            chk.setChecked(True)
            lay_tabs.addWidget(chk)
            self._tab_checks.append(chk)
        layout.addWidget(group)

        # -- Formats (checkboxes) --
        group_fmt = QGroupBox(_("Formats"))
        lay_fmt = QHBoxLayout(group_fmt)
        self._chk_text = QCheckBox(_("Plain text (.txt)"))
        self._chk_srt = QCheckBox(_("SRT (.srt)"))
        self._chk_json = QCheckBox(_("JSON (.json)"))
        # Pre-check current format
        if current_format == "text":
            self._chk_text.setChecked(True)
        elif current_format == "srt":
            self._chk_srt.setChecked(True)
        elif current_format == "json":
            self._chk_json.setChecked(True)
        lay_fmt.addWidget(self._chk_text)
        lay_fmt.addWidget(self._chk_srt)
        lay_fmt.addWidget(self._chk_json)
        layout.addWidget(group_fmt)

        # -- Directory --
        lay_dir = QHBoxLayout()
        lay_dir.addWidget(QLabel(_("Directory:")))
        self._dir_input = QLineEdit()
        self._dir_input.setText(os.path.expanduser("~"))
        lay_dir.addWidget(self._dir_input, 1)
        btn_dir = QPushButton(_("Browse..."))
        btn_dir.clicked.connect(self._on_browse_dir)
        lay_dir.addWidget(btn_dir)
        layout.addLayout(lay_dir)

        # -- Buttons --
        lay_btns = QHBoxLayout()
        lay_btns.addStretch()
        btn_export = QPushButton(_("Export"))
        btn_export.clicked.connect(self.accept)
        lay_btns.addWidget(btn_export)
        btn_cancel = QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        lay_btns.addWidget(btn_cancel)
        layout.addLayout(lay_btns)

    def _on_browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, _("Select directory"), self._dir_input.text())
        if d:
            self._dir_input.setText(d)

    def selected_tabs(self):
        """Return list of (tab_name, text_content) for checked tabs."""
        return [(name, text) for (name, text), chk
                in zip(self._tabs_info, self._tab_checks) if chk.isChecked()]

    def export_formats(self):
        """Return list of selected format codes."""
        fmts = []
        if self._chk_text.isChecked():
            fmts.append("text")
        if self._chk_srt.isChecked():
            fmts.append("srt")
        if self._chk_json.isChecked():
            fmts.append("json")
        return fmts

    def export_dir(self):
        return self._dir_input.text()

    def base_name(self):
        return self._base_name


# === Main Window ===

class TranscribeWindow(QDialog):
    """Main transcription/diarization window."""

    def __init__(self, file_path=None, auto_diarize=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Dictee - Transcribe file"))
        self.setMinimumSize(600, 500)
        self.resize(980, 800)

        self._process = None
        self._stdout_buf = QByteArray()
        self._segments = []
        self._raw_text = ""  # raw transcription output (stored for reformat)
        self._was_diarized = False  # whether last transcription used diarization
        self._translate_thread = None
        self._audio_duration = 0.0
        self._transcribe_elapsed = 0.0
        self._translate_elapsed = 0.0
        self._translate_start = 0.0
        self._current_translate_lang = ""  # lang code of current translation

        self._build_ui()
        self._connect_signals()

        # Pre-fill from CLI args
        if file_path:
            self._file_input.setText(file_path)
        if auto_diarize and _sortformer_available():
            self._chk_diarize.setChecked(True)
        if file_path and auto_diarize:
            self._on_transcribe()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # -- File picker --
        lay_file = QHBoxLayout()
        lbl = QLabel(_("File:"))
        lay_file.addWidget(lbl)

        self._file_input = QLineEdit()
        self._file_input.setPlaceholderText(_("Select an audio file..."))
        self._file_input.setToolTip(_("Path to the audio file to transcribe"))
        lay_file.addWidget(self._file_input, 1)

        self._btn_browse = QPushButton(_("Browse..."))
        self._btn_browse.setToolTip(_("Open file selection dialog"))
        self._btn_browse.clicked.connect(self._on_browse)
        lay_file.addWidget(self._btn_browse)

        layout.addLayout(lay_file)

        # -- Options row --
        lay_opts = QHBoxLayout()

        self._chk_diarize = QCheckBox(_("Speaker identification (diarization)"))
        sortformer_ok = _sortformer_available()
        self._chk_diarize.setEnabled(sortformer_ok)
        if sortformer_ok:
            self._chk_diarize.setToolTip(
                _("Identify speakers (max 4). Recommended for recordings under 5 minutes."))
        else:
            self._chk_diarize.setToolTip(
                _("Sortformer model not installed. Configure in dictee-setup."))
        lay_opts.addWidget(self._chk_diarize)

        self._chk_auto_translate = QCheckBox(_("Auto-translate the transcription"))
        self._chk_auto_translate.setToolTip(
            _("Automatically translate after transcription"))
        lay_opts.addWidget(self._chk_auto_translate)

        lay_opts.addStretch()

        lbl_fmt = QLabel(_("Format:"))
        lay_opts.addWidget(lbl_fmt)

        self._cmb_format = QComboBox()
        self._cmb_format.addItem(_("Plain text"), "text")
        self._cmb_format.addItem("SRT", "srt")
        self._cmb_format.addItem("JSON", "json")
        self._cmb_format.setToolTip(_("Output format for transcription"))
        lay_opts.addWidget(self._cmb_format)

        layout.addLayout(lay_opts)

        # -- Translation row --
        lay_trans = QHBoxLayout()

        conf = _read_conf()

        LANG_CODES = [
            ("en", "English"), ("fr", "Français"), ("de", "Deutsch"),
            ("es", "Español"), ("it", "Italiano"), ("pt", "Português"),
            ("uk", "Українська"), ("nl", "Nederlands"), ("pl", "Polski"),
            ("ru", "Русский"), ("zh", "中文"), ("ja", "日本語"),
            ("ko", "한국어"), ("ar", "العربية"),
        ]

        self._cmb_lang_src = QComboBox()
        for code, name in LANG_CODES:
            self._cmb_lang_src.addItem(f"{code} — {name}", code)
        lang_src = conf.get("DICTEE_LANG_SOURCE", "en")
        for i in range(self._cmb_lang_src.count()):
            if self._cmb_lang_src.itemData(i) == lang_src:
                self._cmb_lang_src.setCurrentIndex(i)
                break
        self._cmb_lang_src.setToolTip(_("Source language"))
        lay_trans.addWidget(self._cmb_lang_src)

        lay_trans.addWidget(QLabel("→"))

        self._cmb_lang_tgt = QComboBox()
        for code, name in LANG_CODES:
            self._cmb_lang_tgt.addItem(f"{code} — {name}", code)
        lang_tgt = conf.get("DICTEE_LANG_TARGET", "fr")
        for i in range(self._cmb_lang_tgt.count()):
            if self._cmb_lang_tgt.itemData(i) == lang_tgt:
                self._cmb_lang_tgt.setCurrentIndex(i)
                break
        self._cmb_lang_tgt.setToolTip(_("Target language"))
        lay_trans.addWidget(self._cmb_lang_tgt)

        backend_name = conf.get("DICTEE_TRANSLATE_BACKEND", "trans")
        if backend_name == "trans":
            backend_name = conf.get("DICTEE_TRANS_ENGINE", "google").capitalize()
        elif backend_name == "ollama":
            backend_name = "Ollama"
        elif backend_name == "libretranslate":
            backend_name = "LibreTranslate"
        self._lbl_backend = QLabel(f'<small style="color: #98c379;"><b>{backend_name}</b></small>')
        self._lbl_backend.setToolTip(_("Current translation backend"))
        lay_trans.addWidget(self._lbl_backend)

        btn_setup_trans = QPushButton(_("Configure..."))
        btn_setup_trans.setToolTip(_("Open translation settings in dictee-setup"))
        btn_setup_trans.clicked.connect(
            lambda: subprocess.Popen(["env", "QT_QPA_PLATFORMTHEME=kde",
                                      "dictee-setup", "--translation"]))
        lay_trans.addWidget(btn_setup_trans)

        lay_trans.addStretch()
        layout.addLayout(lay_trans)

        # -- Action buttons (Transcribe + Translate on same line) --
        lay_action = QHBoxLayout()
        lay_action.addStretch()

        self._btn_transcribe = QPushButton(_("Transcribe"))
        self._btn_transcribe.setEnabled(False)
        self._btn_transcribe.setToolTip(_("Start transcription of the selected file"))
        self._btn_transcribe.clicked.connect(self._on_transcribe)
        lay_action.addWidget(self._btn_transcribe)

        self._btn_translate = QPushButton(_("Translate"))
        self._btn_translate.setEnabled(False)
        self._btn_translate.setToolTip(_("Translate the current transcription"))
        self._btn_translate.clicked.connect(self._on_translate)
        lay_action.addWidget(self._btn_translate)

        lay_action.addStretch()
        layout.addLayout(lay_action)

        # -- Progress bar --
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # -- Status label --
        self._lbl_status = QLabel()
        self._lbl_status.setVisible(False)
        layout.addWidget(self._lbl_status)

        # -- Tab widget: Original + dynamic translation tabs --
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(False)
        self._text_edit.setPlaceholderText(_("Transcription results will appear here..."))
        self._text_edit.setToolTip(_("Editable transcription text. Ctrl+F to search, Ctrl+Z to undo."))
        self._tabs.addTab(self._text_edit, _("Original"))
        # Original tab is not closable
        self._tabs.tabBar().setTabButton(0, self._tabs.tabBar().ButtonPosition.RightSide, None)

        # Dict of translation tabs: lang_code -> {editor, segments, text}
        self._translation_tabs = {}

        layout.addWidget(self._tabs, 1)

        # -- Search bar (works on active tab) --
        self._search_bar = SearchBar(self._text_edit, self)
        layout.addWidget(self._search_bar)

        # -- Bottom buttons --
        lay_btns = QHBoxLayout()

        self._btn_copy = QPushButton(_("Copy all"))
        self._btn_copy.setToolTip(_("Copy the entire text to the clipboard"))
        self._btn_copy.clicked.connect(self._on_copy)
        lay_btns.addWidget(self._btn_copy)

        self._btn_export = QPushButton(_("Export..."))
        self._btn_export.setToolTip(_("Save the transcription to a file"))
        self._btn_export.clicked.connect(self._on_export)
        lay_btns.addWidget(self._btn_export)

        lay_btns.addStretch()

        self._btn_close = QPushButton(_("Close"))
        self._btn_close.setToolTip(_("Close this window"))
        self._btn_close.clicked.connect(self.close)
        lay_btns.addWidget(self._btn_close)

        layout.addLayout(lay_btns)

    def _active_editor(self):
        """Return the QTextEdit of the active tab."""
        widget = self._tabs.currentWidget()
        return widget if isinstance(widget, QTextEdit) else self._text_edit

    def _on_tab_close(self, index):
        """Close a translation tab (but never the Original tab)."""
        if index == 0:
            return  # never close Original
        widget = self._tabs.widget(index)
        # Remove from translation_tabs dict
        for lang, data in list(self._translation_tabs.items()):
            if data["editor"] is widget:
                del self._translation_tabs[lang]
                break
        self._tabs.removeTab(index)

    def _connect_signals(self):
        self._file_input.textChanged.connect(self._update_transcribe_btn)
        self._cmb_format.currentIndexChanged.connect(self._on_format_changed)
        self._cmb_lang_src.currentIndexChanged.connect(self._on_lang_changed)
        self._cmb_lang_tgt.currentIndexChanged.connect(self._on_lang_changed)
        self._chk_auto_translate.toggled.connect(lambda: self._update_translate_btn())
        self._tabs.currentChanged.connect(
            lambda: self._search_bar.set_editor(self._active_editor()))

        # Watch dictee.conf for changes (e.g. after dictee-setup modifies it)
        if os.path.isfile(CONF_PATH):
            self._conf_watcher = QFileSystemWatcher([CONF_PATH], self)
            self._conf_watcher.fileChanged.connect(self._on_conf_changed)

        # Ctrl+F -> search bar
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self._search_bar.activate)

        # Escape -> close search bar if visible, else close window
        esc = QShortcut(QKeySequence("Escape"), self)
        esc.activated.connect(self._on_escape)

    def _on_conf_changed(self, path):
        """Refresh UI when dictee.conf changes."""
        _dbg(f"_on_conf_changed: {path}")
        self._refresh_backend_label()
        self._update_translate_btn()
        # Re-add to watcher (some editors replace the file, removing the watch)
        if hasattr(self, '_conf_watcher') and path not in self._conf_watcher.files():
            self._conf_watcher.addPath(path)

    def _refresh_backend_label(self):
        """Update the backend label from current config."""
        conf = _read_conf()
        backend = conf.get("DICTEE_TRANSLATE_BACKEND", "trans")
        if backend == "trans":
            name = conf.get("DICTEE_TRANS_ENGINE", "google").capitalize()
        elif backend == "ollama":
            name = "Ollama"
        elif backend == "libretranslate":
            name = "LibreTranslate"
        else:
            name = backend
        self._lbl_backend.setText(f'<small style="color: #98c379;"><b>{name}</b></small>')

    def _on_lang_changed(self):
        """Disable same language in the other ComboBox."""
        src = self._cmb_lang_src.currentData()
        tgt = self._cmb_lang_tgt.currentData()
        # Grey out source lang in target ComboBox
        model_tgt = self._cmb_lang_tgt.model()
        for i in range(self._cmb_lang_tgt.count()):
            item = model_tgt.item(i)
            if item:
                item.setEnabled(self._cmb_lang_tgt.itemData(i) != src)
        # Grey out target lang in source ComboBox
        model_src = self._cmb_lang_src.model()
        for i in range(self._cmb_lang_src.count()):
            item = model_src.item(i)
            if item:
                item.setEnabled(self._cmb_lang_src.itemData(i) != tgt)
        self._update_translate_btn()

    def _update_translate_btn(self):
        src = self._cmb_lang_src.currentData()
        tgt = self._cmb_lang_tgt.currentData()
        translating = self._translate_thread and self._translate_thread.isRunning()
        self._btn_translate.setEnabled(
            src != tgt
            and bool(self._raw_text)
            and _translate_available()
            and not self._chk_auto_translate.isChecked()
            and not translating)

    def _update_transcribe_btn(self):
        has_file = bool(self._file_input.text().strip())
        not_running = self._process is None
        self._btn_transcribe.setEnabled(has_file and not_running)

    @staticmethod
    def _get_audio_duration(path):
        """Get audio duration in seconds via ffprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", path],
                capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass
        return 0.0

    def _on_escape(self):
        if self._search_bar.isVisible():
            self._search_bar.hide()
        else:
            self.close()

    def _on_browse(self):
        _dbg("_on_browse: opening file dialog")
        path, _filter = QFileDialog.getOpenFileName(
            self, _("Select audio file"), "", AUDIO_FILTER)
        if path:
            _dbg(f"_on_browse: selected {path}")
            self._file_input.setText(path)

    def _on_transcribe(self):
        audio_path = self._file_input.text().strip()
        if not audio_path or not os.path.isfile(audio_path):
            self._lbl_status.setText(_("File not found."))
            self._lbl_status.setVisible(True)
            return

        # Block if translation is running
        if self._translate_thread and self._translate_thread.isRunning():
            _dbg("_on_transcribe: blocked — translation running")
            return

        diarize = self._chk_diarize.isChecked()
        _dbg(f"_on_transcribe: file={audio_path}, diarize={diarize}")

        # Reset all state for new transcription
        self._was_diarized = False
        self._text_edit.clear()
        # Remove all translation tabs
        while self._tabs.count() > 1:
            self._tabs.removeTab(1)
        self._translation_tabs.clear()
        self._segments = []
        self._raw_text = ""
        self._stdout_buf = QByteArray()
        self._start_time = time.monotonic()
        self._translate_elapsed = 0.0
        self._audio_duration = self._get_audio_duration(audio_path)
        self._tabs.setCurrentIndex(0)  # show Original tab
        self._progress.setVisible(True)

        # Free GPU VRAM only if needed: unload ollama model before transcription
        _dbg("_on_transcribe: checking GPU VRAM")
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                free_mb = int(result.stdout.strip().split("\n")[0])
                _dbg(f"_on_transcribe: GPU VRAM free={free_mb} MB")
                if free_mb < 1024:  # less than 1 GB free
                    conf = _read_conf()
                    if conf.get("DICTEE_TRANSLATE_BACKEND") == "ollama":
                        model = conf.get("DICTEE_OLLAMA_MODEL", "translategemma")
                        import urllib.request
                        req = urllib.request.Request(
                            "http://localhost:11434/api/generate",
                            data=json.dumps({"model": model, "keep_alive": 0}).encode(),
                            headers={"Content-Type": "application/json"})
                        urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

        self._lbl_status.setText(_("Transcribing..."))
        self._lbl_status.setVisible(True)
        self._btn_transcribe.setEnabled(False)
        self._btn_translate.setEnabled(False)

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        # Set ORT_DYLIB_PATH for GPU acceleration if the lib exists
        env = self._process.processEnvironment()
        if env.isEmpty():
            env = QProcessEnvironment.systemEnvironment()
        ort_lib = "/usr/lib/dictee/libonnxruntime.so"
        if os.path.isfile(ort_lib):
            env.insert("ORT_DYLIB_PATH", ort_lib)
            self._process.setProcessEnvironment(env)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.finished.connect(self._on_finished)

        import shutil
        cmd = "transcribe-diarize" if diarize else "transcribe"
        _dbg(f"_on_transcribe: cmd={cmd}, ort_lib={os.path.isfile('/usr/lib/dictee/libonnxruntime.so')}")
        if not shutil.which(cmd):
            self._progress.setVisible(False)
            self._lbl_status.setText(
                _("Command '{cmd}' not found. Install dictee first.").format(cmd=cmd))
            self._lbl_status.setVisible(True)
            self._update_transcribe_btn()
            self._process = None
            return
        self._process.start(cmd, [audio_path])

    def _on_stdout(self):
        data = self._process.readAllStandardOutput()
        self._stdout_buf.append(data)

    def _on_finished(self, exit_code, _exit_status):
        self._progress.setVisible(False)
        self._process = None
        self._update_transcribe_btn()

        raw_output = bytes(self._stdout_buf).decode("utf-8", errors="replace").strip()
        _dbg(f"_on_finished: exit_code={exit_code}, output_len={len(raw_output)}")

        if exit_code != 0:
            # GPU OOM: unload ollama and retry once
            if ("Failed to allocate memory" in raw_output
                    or "BFCArena" in raw_output
                    or "CUBLAS_STATUS_ALLOC_FAILED" in raw_output
                    or "CUDA" in raw_output and "ALLOC" in raw_output
                    ) and not getattr(self, '_retry_done', False):
                self._retry_done = True
                _dbg(f"_on_finished: GPU OOM detected, retrying. Error: {raw_output[:200]}")
                msg = _("GPU memory full — unloading translation model and retrying...")
                self._lbl_status.setText(msg)
                self._lbl_status.setVisible(True)
                self._text_edit.setPlainText(msg)
                self._progress.setVisible(True)
                conf = _read_conf()
                if conf.get("DICTEE_TRANSLATE_BACKEND") == "ollama":
                    model = conf.get("DICTEE_OLLAMA_MODEL", "translategemma")
                    try:
                        import urllib.request
                        req = urllib.request.Request(
                            "http://localhost:11434/api/generate",
                            data=json.dumps({"model": model, "keep_alive": 0}).encode(),
                            headers={"Content-Type": "application/json"})
                        urllib.request.urlopen(req, timeout=5)
                    except Exception:
                        pass
                # Re-trigger transcription after delay
                QTimer.singleShot(2000, self._on_transcribe)
                return

            self._retry_done = False
            self._lbl_status.setText(
                _("Transcription failed (code {code}). Check memory, backend, or audio file.").format(
                    code=exit_code))
            self._lbl_status.setVisible(True)
            if raw_output:
                self._text_edit.setPlainText(raw_output)
            self._raw_text = ""
            self._segments = []
            self._update_translate_btn()
            return

        if not raw_output:
            self._lbl_status.setText(_("No transcription result."))
            self._lbl_status.setVisible(True)
            self._raw_text = ""
            self._segments = []
            self._update_translate_btn()
            return

        # Reset retry flag on success
        self._retry_done = False
        _dbg(f"_on_finished: success, diarized={self._chk_diarize.isChecked()}, raw_len={len(raw_output)}")

        # Store raw result for reformatting
        self._raw_text = raw_output
        self._was_diarized = self._chk_diarize.isChecked()

        if self._was_diarized:
            self._segments = _parse_diarize_output(raw_output)

        # Auto-detect language and update source/target ComboBoxes
        detect_text = raw_output
        if self._segments:
            detect_text = " ".join(seg["text"] for seg in self._segments)
        detected = _detect_language(detect_text)
        _dbg(f"_on_finished: detected language={detected}")
        for i in range(self._cmb_lang_src.count()):
            if self._cmb_lang_src.itemData(i) == detected:
                self._cmb_lang_src.setCurrentIndex(i)
                break
        # If target is same as detected source, switch target to user's language
        if self._cmb_lang_tgt.currentData() == detected:
            import locale as _locale
            conf = _read_conf()
            # Prefer dictee.conf target, then system locale
            fallback = conf.get("DICTEE_LANG_TARGET", "")
            if not fallback or fallback == detected:
                sys_lang = _locale.getlocale()[0] or ""
                fallback = sys_lang.split("_")[0] if sys_lang else ""
            if fallback and fallback != detected:
                for i in range(self._cmb_lang_tgt.count()):
                    if self._cmb_lang_tgt.itemData(i) == fallback:
                        self._cmb_lang_tgt.setCurrentIndex(i)
                        break

        # Display in current format
        self._apply_format()
        self._transcribe_elapsed = time.monotonic() - self._start_time
        self._translate_elapsed = 0.0
        self._update_translate_btn()

        self._show_status()

        # Auto-translate if checked and languages differ
        if (self._chk_auto_translate.isChecked()
                and _translate_available()
                and self._cmb_lang_src.currentData() != self._cmb_lang_tgt.currentData()):
            self._on_translate()

    def _show_status(self):
        """Show final status with timing and speaker info."""
        dur = self._audio_duration
        dur_str = f"{int(dur//60)}:{int(dur%60):02d}" if dur >= 60 else f"{dur:.1f}s"
        n_speakers = len(set(s["speaker"] for s in self._segments)) if self._segments else 0
        parts = []
        if self._was_diarized and self._segments:
            parts.append(_("{n} speaker(s)").format(n=n_speakers))
        parts.append(_("audio {dur}").format(dur=dur_str))
        parts.append(_("transcribed in {t:.1f}s").format(t=self._transcribe_elapsed))
        if self._translate_elapsed > 0:
            parts.append(_("translated in {t:.1f}s").format(t=self._translate_elapsed))
        self._lbl_status.setText(" — ".join(parts))

    def _on_translate(self):
        """Translate current transcription result."""
        if not self._raw_text:
            return
        # Prevent concurrent translation
        if self._translate_thread and self._translate_thread.isRunning():
            return
        # Prevent same-language translation
        if self._cmb_lang_src.currentData() == self._cmb_lang_tgt.currentData():
            _dbg("_on_translate: blocked — same language")
            return
        _dbg(f"_on_translate: {self._cmb_lang_src.currentData()} → {self._cmb_lang_tgt.currentData()}")
        # Keep transcription status and append translating
        current = self._lbl_status.text()
        self._lbl_status.setText(current + " — " + _("Translating..."))
        self._lbl_status.setVisible(True)
        self._progress.setVisible(True)
        self._btn_translate.setEnabled(False)
        self._btn_transcribe.setEnabled(False)
        self._translate_start = time.monotonic()
        lang_src = self._cmb_lang_src.currentData()
        lang_tgt = self._cmb_lang_tgt.currentData()
        self._current_translate_lang = lang_tgt
        # Disconnect previous thread signal if any
        if self._translate_thread:
            try:
                self._translate_thread.finished_signal.disconnect(self._on_translate_done)
            except (TypeError, RuntimeError):
                pass
        self._translate_thread = TranslateThread(
            self._raw_text, self._segments, self._was_diarized,
            lang_src, lang_tgt)
        self._translate_thread.finished_signal.connect(self._on_translate_done)
        self._translate_thread.error_signal.connect(self._on_translate_error)
        self._translate_thread.start()

    def _on_translate_error(self, message):
        """Show translation error in status bar."""
        _dbg(f"_on_translate_error: {message}")
        self._lbl_status.setText(message)
        self._lbl_status.setVisible(True)

    def _on_translate_done(self, translated_text, translated_segments):
        """Handle translation completion."""
        _dbg(f"_on_translate_done: text_len={len(translated_text)}, segments={len(translated_segments)}")
        self._progress.setVisible(False)
        self._update_translate_btn()
        self._update_transcribe_btn()
        self._translate_elapsed = time.monotonic() - self._translate_start

        lang = self._current_translate_lang
        # Find language name for tab title
        lang_name = lang.upper()
        for i in range(self._cmb_lang_tgt.count()):
            if self._cmb_lang_tgt.itemData(i) == lang:
                lang_name = self._cmb_lang_tgt.itemText(i).split(" — ")[1] if " — " in self._cmb_lang_tgt.itemText(i) else lang.upper()
                break

        # Create or reuse tab for this language
        if lang in self._translation_tabs:
            tab_data = self._translation_tabs[lang]
            editor = tab_data["editor"]
        else:
            editor = QTextEdit()
            editor.setReadOnly(False)
            editor.setToolTip(_("Editable translation text. Ctrl+F to search, Ctrl+Z to undo."))
            tab_idx = self._tabs.addTab(editor, lang_name)
            self._translation_tabs[lang] = {"editor": editor, "segments": [], "text": ""}

        # Store and display
        if translated_segments:
            self._translation_tabs[lang]["segments"] = translated_segments
            self._translation_tabs[lang]["text"] = ""
            self._apply_format_to(editor, translated_segments, None)
        elif translated_text:
            self._translation_tabs[lang]["segments"] = []
            self._translation_tabs[lang]["text"] = translated_text
            self._apply_format_to(editor, [], translated_text)

        # Switch to this translation tab
        self._tabs.setCurrentWidget(editor)
        # Uncheck auto-translate so user can translate to other languages
        self._chk_auto_translate.setChecked(False)
        self._show_status()

    def _on_format_changed(self):
        """Reformat display when user changes the format ComboBox."""
        if self._raw_text:
            self._apply_format()

    def _speaker_color(self, speaker):
        """Get color for a speaker label."""
        # Extract speaker index from 'Speaker N'
        try:
            idx = int(speaker.split()[-1])
        except (ValueError, IndexError):
            idx = 0
        return SPEAKER_COLORS[idx % len(SPEAKER_COLORS)]

    def _apply_format(self):
        """Format and display original transcription + all translation tabs."""
        self._apply_format_to(self._text_edit, self._segments, self._raw_text)
        # Reformat all translation tabs
        for lang, data in self._translation_tabs.items():
            if data["segments"] or data["text"]:
                self._apply_format_to(data["editor"], data["segments"], data["text"])

    def _apply_format_to(self, editor, segments, raw_text):
        """Format and display text in the given editor."""
        fmt = self._cmb_format.currentData()

        if self._was_diarized and segments:
            if fmt == "srt":
                editor.setPlainText(_format_srt(segments))
            elif fmt == "json":
                editor.setPlainText(_format_json(segments))
            else:
                self._set_colored_diarize_to(editor, segments)
        else:
            text = raw_text or ""
            if fmt == "json":
                editor.setPlainText(json.dumps(
                    [{"text": text}], ensure_ascii=False, indent=2))
            elif fmt == "srt":
                editor.setPlainText(
                    f"1\n00:00:00,000 --> 99:59:59,999\n{text}\n")
            else:
                editor.setPlainText(text)

    def _set_colored_diarize_to(self, editor, segments):
        """Display diarized text with colored speaker headers in given editor."""
        import html as _html
        lines = []
        prev_speaker = None
        for seg in segments:
            if seg["speaker"] != prev_speaker:
                if prev_speaker is not None:
                    lines.append("<br/>")
                color = self._speaker_color(seg["speaker"])
                lines.append(
                    f'<b style="color:{color}">{_html.escape(seg["speaker"])}:</b>')
                prev_speaker = seg["speaker"]
            lines.append(f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{_html.escape(seg["text"])}')
        editor.setHtml(
            '<div style="white-space:pre-wrap">' + "<br/>".join(lines) + "</div>")

    def _on_copy(self):
        editor = self._active_editor()
        text = editor.toPlainText()
        _dbg(f"_on_copy: tab={self._tabs.currentIndex()}, editor={type(editor).__name__}, text_len={len(text)}")
        if text:
            QApplication.clipboard().setText(text)
            tab_name = self._tabs.tabText(self._tabs.currentIndex())
            self._lbl_status.setText(_("Copied {tab} to clipboard.").format(tab=tab_name))
            self._lbl_status.setVisible(True)
        else:
            self._lbl_status.setText(_("Nothing to copy."))
            self._lbl_status.setVisible(True)

    def _on_export(self):
        _dbg(f"_on_export: {self._tabs.count()} tabs")
        # Collect all tabs with content
        tabs_info = []
        for i in range(self._tabs.count()):
            editor = self._tabs.widget(i)
            if isinstance(editor, QTextEdit):
                text = editor.toPlainText()
                if text.strip():
                    tabs_info.append((self._tabs.tabText(i), text))

        if not tabs_info:
            self._lbl_status.setText(_("Nothing to export."))
            self._lbl_status.setVisible(True)
            return

        base = os.path.splitext(os.path.basename(self._file_input.text()))[0] or "transcription"
        dlg = ExportDialog(tabs_info, self._cmb_format.currentData(), base, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        selected = dlg.selected_tabs()
        formats = dlg.export_formats()
        out_dir = dlg.export_dir()

        if not selected or not formats:
            self._lbl_status.setText(_("Nothing to export."))
            self._lbl_status.setVisible(True)
            return

        ext_map = {"text": ".txt", "srt": ".srt", "json": ".json"}

        # For SRT/JSON we need segments, not plain text — reformat from stored data
        exported = []
        for fmt in formats:
            ext = ext_map.get(fmt, ".txt")
            for tab_name, text in selected:
                # Find segments for this tab to reformat
                content = text  # default: plain text from editor
                if fmt != "text":
                    # Try to find segments for this tab
                    segments = None
                    if tab_name == self._tabs.tabText(0):
                        segments = self._segments if self._was_diarized else None
                    else:
                        for lang, data in self._translation_tabs.items():
                            if data["segments"]:
                                # Match by checking tab widget text
                                for i in range(self._tabs.count()):
                                    if (self._tabs.tabText(i) == tab_name
                                            and self._tabs.widget(i) is data["editor"]):
                                        segments = data["segments"]
                                        break

                    if segments and fmt == "srt":
                        content = _format_srt(segments)
                    elif segments and fmt == "json":
                        content = _format_json(segments)
                    elif fmt == "json":
                        raw = self._raw_text if tab_name == self._tabs.tabText(0) else text
                        content = json.dumps([{"text": raw}], ensure_ascii=False, indent=2)
                    elif fmt == "srt":
                        raw = self._raw_text if tab_name == self._tabs.tabText(0) else text
                        content = f"1\n00:00:00,000 --> 99:59:59,999\n{raw}\n"

                safe_name = tab_name.replace(" ", "_").replace("/", "-")
                filename = f"{base}-{safe_name}{ext}"
                path = os.path.join(out_dir, filename)
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                    exported.append(filename)
                except OSError as e:
                    self._lbl_status.setText(
                        _("Export failed: {error}").format(error=str(e)))
                    self._lbl_status.setVisible(True)
                    return

        self._lbl_status.setText(
            _("Exported {n} file(s) to {dir}").format(n=len(exported), dir=out_dir))
        self._lbl_status.setVisible(True)


# === Main ===

def main():
    parser = argparse.ArgumentParser(description="Dictee - Transcribe audio files")
    parser.add_argument("--file", "-f", help="Audio file to transcribe")
    parser.add_argument("--diarize", "-d", action="store_true",
                        help="Enable speaker diarization")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging to stderr and /tmp/dictee-transcribe.log")
    args = parser.parse_args()

    global DEBUG
    if args.debug:
        DEBUG = True
        _dbg("dictee-transcribe starting with --debug")

    app = QApplication(sys.argv)
    app.setApplicationName("dictee-transcribe")
    app.setDesktopFileName("dictee-transcribe")

    win = TranscribeWindow(
        file_path=args.file,
        auto_diarize=args.diarize,
    )
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
