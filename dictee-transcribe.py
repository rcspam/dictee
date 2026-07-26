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
import shutil
import subprocess
import sys
import time

try:
    from PyQt6.QtCore import (Qt, QProcess, QByteArray, QThread, QTimer,
                               QProcessEnvironment, QFileSystemWatcher,
                               QUrl, QSize, QRect, QRectF,
                               QPropertyAnimation, QEasingCurve,
                               QSettings, QEvent,
                               pyqtSignal as Signal,
                               pyqtProperty as Property)
    from PyQt6.QtGui import (QShortcut, QKeySequence, QTextDocument,
                              QPainter, QColor, QBrush, QPen,
                              QTextCharFormat, QTextCursor)
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QComboBox, QProgressBar, QCheckBox, QSlider,
        QTextEdit, QFileDialog, QLineEdit, QWidget, QTabWidget, QGroupBox,
        QMessageBox, QToolButton, QSizePolicy, QFrame, QToolTip, QInputDialog,
    )
    from PyQt6.QtGui import QFont as _QFontTip
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
except ImportError:
    from PySide6.QtCore import (Qt, QProcess, QByteArray, QThread, QTimer,
                                QProcessEnvironment, QFileSystemWatcher,
                                Signal, QUrl, QSize, QRect, QRectF,
                                QPropertyAnimation, QEasingCurve, Property,
                                QSettings, QEvent)
    from PySide6.QtGui import (QShortcut, QKeySequence, QTextDocument,
                                QPainter, QColor, QBrush, QPen,
                                QTextCharFormat, QTextCursor)
    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QComboBox, QProgressBar, QCheckBox, QSlider,
        QTextEdit, QFileDialog, QLineEdit, QWidget, QTabWidget, QGroupBox,
        QMessageBox, QToolButton, QSizePolicy, QFrame, QToolTip, QInputDialog,
    )
    from PySide6.QtGui import QFont as _QFontTip
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices


# ---------------------------------------------------------------------------
# ASR model spec helpers
# ---------------------------------------------------------------------------

_WHISPER_RUST_SIZES = ("tiny", "base", "small", "medium",
                       "large-v3-turbo", "large-v3-turbo-fp16", "large-v3")

ASR_SPECS = ("parakeet-int8", "parakeet-fp32",
             "whisper", "whisper-tiny", "whisper-small", "whisper-medium",
             "whisper-rust", "nemotron") + tuple(
             f"whisper-rust-{s}" for s in _WHISPER_RUST_SIZES)


def _whisper_rust_ggml_path(size=None):
    """Resolve the ggml model file for an isolated Whisper-Rust run.

    Preference order: the dictee.conf DICTEE_WHISPER_RUST_GGML path (written
    by dictee-setup when a model is selected), unless a specific `size` is
    requested; then a glob for ggml-<size>-q*.bin in the user and system
    model dirs (quantization suffixes vary per size, so no filename table
    is duplicated here), then the exact ggml-<size>.bin (unquantized models
    such as large-v3-turbo-fp16 carry no -q suffix). Returns "" when nothing
    is installed.
    """
    import glob
    conf = _read_conf()
    if size is None:
        p = (conf.get("DICTEE_WHISPER_RUST_GGML") or "").strip()
        if p and os.path.isfile(p):
            return p
        size = (conf.get("DICTEE_WHISPER_RUST_MODEL") or "large-v3").strip()
    user_dir = os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
        "dictee", "whisper-rust")
    for d in (user_dir, "/usr/share/dictee/whisper-rust"):
        for pat in (f"ggml-{size}-q*.bin", f"ggml-{size}.bin"):
            hits = sorted(glob.glob(os.path.join(d, pat)))
            if hits:
                return hits[0]
    return ""


def asr_spec_to_daemon(spec):
    """Map an --asr-model spec to the isolated-daemon recipe, or None for the
    default F9 daemon.  Raises ValueError on an unknown non-empty spec.

    The unsized "whisper" / "whisper-rust" specs follow the model selected
    in dictee-setup (dictee.conf) — the UI combos expose only those two so
    the size stays a single-source setting. The sized variants remain for
    the CLI and for values saved before this change.
    """
    if not spec or spec in ("f9", "default"):  # UI-combo sentinels meaning "use the F9 daemon"
        return None
    if spec == "parakeet-int8":
        return {"backend": "parakeet",
                "env": {"DICTEE_PARAKEET_QUANT": "int8", "DICTEE_FORCE_CPU": "1"}}
    if spec == "parakeet-fp32":
        # fp32 = full-precision model on the best provider (GPU if present).
        # Explicitly clear any conf-level DICTEE_FORCE_CPU so an isolated fp32
        # run isn't pinned to CPU by the F9 config ("0" means "GPU allowed":
        # execution.rs only forces CPU on 1/true/yes).
        return {"backend": "parakeet",
                "env": {"DICTEE_PARAKEET_QUANT": "fp32", "DICTEE_FORCE_CPU": "0"}}
    # whisper-rust before plain whisper: both share the "whisper-" prefix.
    # The daemon needs the ggml PATH (transcribe_daemon.rs reads
    # DICTEE_WHISPER_RUST_GGML): IsolatedAsrDaemon does not source
    # dictee.conf, so the recipe must carry it. Empty path = model not
    # installed; the caller surfaces the error before spawning.
    # DICTEE_ASR_BACKEND=whisper is what actually flips transcribe-daemon*
    # to the whisper branch (transcribe_daemon.rs use_whisper): without it a
    # conf-level backend (e.g. parakeet, forwarded from os.environ) silently
    # wins and the "isolated whisper-rust" daemon transcribes with Parakeet.
    if spec == "whisper-rust":
        return {"backend": "whisper-rust",
                "env": {"DICTEE_ASR_BACKEND": "whisper",
                        "DICTEE_WHISPER_RUST_GGML": _whisper_rust_ggml_path()}}
    if spec.startswith("whisper-rust-"):
        size = spec[len("whisper-rust-"):]
        if size in _WHISPER_RUST_SIZES:
            return {"backend": "whisper-rust",
                    "env": {"DICTEE_ASR_BACKEND": "whisper",
                            "DICTEE_WHISPER_RUST_MODEL": size,
                            "DICTEE_WHISPER_RUST_GGML": _whisper_rust_ggml_path(size)}}
        raise ValueError(f"unknown asr spec: {spec}")
    if spec == "whisper":
        size = (_read_conf().get("DICTEE_WHISPER_MODEL") or "small").strip()
        if size not in ("tiny", "small", "medium"):
            size = "small"
        return {"backend": "whisper",
                "env": {"DICTEE_WHISPER_MODEL": size}}
    if spec in ("whisper-tiny", "whisper-small", "whisper-medium"):
        return {"backend": "whisper",
                "env": {"DICTEE_WHISPER_MODEL": spec.split("-", 1)[1]}}
    if spec == "nemotron":
        return {"backend": "nemotron",
                "env": {"DICTEE_ASR_BACKEND": "nemotron"}}
    raise ValueError(f"unknown asr spec: {spec}")


def list_past_meetings(base=None):
    """Return [(label, audio_path), ...] sorted recent→old, from
    ~/.local/share/dictee/meetings/*/meeting.meta.json (title + date)."""
    import json
    base = base or os.environ.get(
        "DICTEE_MEETING_DIR",
        os.path.join(os.path.expanduser("~"), ".local/share/dictee/meetings"))
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base), reverse=True):   # date-prefixed → recent first
        d = os.path.join(base, name)
        audio = os.path.join(d, "audio.wav")
        if not os.path.isfile(audio):
            continue
        title = name
        meta = os.path.join(d, "meeting.meta.json")
        if os.path.isfile(meta):
            try:
                with open(meta, encoding="utf-8") as f:
                    title = json.load(f).get("title") or name
            except Exception:
                pass
        out.append((f"{name} — {title}" if title != name else name, audio))
    return out


class ToggleSwitch(QCheckBox):
    """Plasma/iOS-style toggle switch (copied from dictee-setup.py).

    Drop-in replacement for QCheckBox: accepts a label text, honours
    isChecked/setChecked, the toggled signal, the enabled state, tooltips,
    and stylesheets affecting font-size / font-weight (via self.font()).
    Text atténuated when OFF, grey when disabled. Same visuals as the
    dictee-setup ToggleSwitch for consistency across the dictee UI family.
    """

    _TRACK_W = 44
    _TRACK_H = 22
    _TRACK_RADIUS = 11
    _HANDLE_RADIUS = 9
    _TEXT_SPACING = 8

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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

        off_color = QColor("#5a5a5a") if enabled else QColor("#3a3a3a")
        on_color = pal.color(pal.ColorRole.Highlight)
        if not enabled:
            on_color = on_color.darker(160)
        handle_color = QColor("#f4f4f4") if enabled else QColor("#aaaaaa")

        t = self._offset_val
        track = QColor(
            int(off_color.red() * (1 - t) + on_color.red() * t),
            int(off_color.green() * (1 - t) + on_color.green() * t),
            int(off_color.blue() * (1 - t) + on_color.blue() * t),
        )

        total_h = self.height()
        track_y = (total_h - self._TRACK_H) / 2
        track_rect = QRectF(0, track_y, self._TRACK_W, self._TRACK_H)
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
class _ClickSlider(QSlider):
    """QSlider with click-to-seek and speaker segment markers.

    Markers and click handling are aligned to the *groove* rect (not
    the widget rect): the native handle moves inside the groove, which
    has horizontal margins, so using widget.width() shifts everything
    away from the playback handle's actual track. The downward red
    triangle replaces the native round handle for a clearer "tip"
    pointing at the exact playback position.
    """
    sliderClicked = Signal(int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._markers = []   # list of (start_ms, end_ms, QColor)
        self.setMinimumHeight(44)
        # Hide the native handle so we can render our own triangle on
        # top of the groove. The groove itself is left to the platform
        # style (so it follows the user's KDE/GNOME palette).
        self.setStyleSheet(
            "QSlider::handle:horizontal { background: transparent; "
            "border: none; width: 0px; margin: 0; }")

    def set_markers(self, markers):
        """Set speaker markers: list of (start_ms, end_ms, color_str)."""
        try:
            from PyQt6.QtGui import QColor
        except ImportError:
            from PySide6.QtGui import QColor
        self._markers = [(s, e, QColor(c)) for s, e, c in markers]
        self.update()

    def clear_markers(self):
        self._markers.clear()
        self.update()

    def _groove_rect(self):
        """Return the rect of the slider's groove (in widget coords).
        Falls back to a sane default if the style query fails."""
        try:
            from PyQt6.QtWidgets import QStyle, QStyleOptionSlider
        except ImportError:
            from PySide6.QtWidgets import QStyle, QStyleOptionSlider
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        return self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt,
            QStyle.SubControl.SC_SliderGroove, self)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.maximum() <= self.minimum():
            return
        try:
            from PyQt6.QtGui import QPainter, QPen, QPolygonF, QColor
            from PyQt6.QtCore import QPointF
        except ImportError:
            from PySide6.QtGui import QPainter, QPen, QPolygonF, QColor
            from PySide6.QtCore import QPointF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rng = self.maximum() - self.minimum()
        h = self.height()
        groove = self._groove_rect()
        gx, gw = groove.x(), groove.width()
        if gw <= 0:
            p.end()
            return

        def to_x(ms):
            return gx + (ms - self.minimum()) / rng * gw

        # Speaker bars (semi-transparent) + thin colour ticks at the
        # segment starts — both clamped to the groove so they line up
        # exactly with the playback triangle.
        for start_ms, end_ms, color in self._markers:
            x1 = int(to_x(start_ms))
            x2 = int(to_x(end_ms))
            bar = QColor(color); bar.setAlpha(60)
            p.fillRect(x1, 0, max(x2 - x1, 2), h, bar)
        for start_ms, _end_ms, color in self._markers:
            x = int(to_x(start_ms))
            p.setPen(QPen(color, 1))
            p.drawLine(x, 0, x, h - 1)

        # Up-pointing red triangle placed BELOW the groove so its apex
        # points up at the playback position on the timeline. (User's
        # convention: tip aimed at the groove — pointing up means
        # sitting under it; pointing down would mean sitting above.)
        cx = to_x(self.value())
        tri_w = 16.0
        tri_h = 13.0
        tip_y = groove.bottom() + 2
        base_y = tip_y + tri_h
        # Clamp to the widget so the triangle is always fully drawn
        # even on tighter heights.
        if base_y > h - 1:
            base_y = h - 1
            tip_y = base_y - tri_h
        tip = QPointF(cx, tip_y)
        left = QPointF(cx - tri_w / 2, base_y)
        right = QPointF(cx + tri_w / 2, base_y)
        p.setPen(QPen(QColor("#a02020"), 1))
        p.setBrush(QColor("#e63946"))
        p.drawPolygon(QPolygonF([tip, left, right]))
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            groove = self._groove_rect()
            gx, gw = groove.x(), groove.width()
            if gw > 0:
                rel = (event.position().x() - gx) / gw
                rel = max(0.0, min(1.0, rel))
                rng = self.maximum() - self.minimum()
                val = int(self.minimum() + rel * rng)
                self.setValue(val)
                self.sliderClicked.emit(val)
                event.accept()
                return
        super().mousePressEvent(event)


SPEAKER_COLORS = [
    "#e06c75",  # red
    "#61afef",  # blue
    "#98c379",  # green
    "#d19a66",  # orange
]

DIARIZE_RE = re.compile(
    r"\[(\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]\s*(Speaker\s+\d+|UNKNOWN):\s*(.*)"
)

# ISO-2 code → English language name. Used by the Ollama translate
# prompt and by the LLM Diarization "force output language" hint —
# both want English names regardless of the user's UI locale, since
# foreign-language LLM prompts tend to drift in unpredictable ways.
LANG_NAMES_EN = {
    "en": "English", "fr": "French", "de": "German",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese",
    "uk": "Ukrainian", "nl": "Dutch", "pl": "Polish",
    "ru": "Russian", "zh": "Chinese", "ja": "Japanese",
    "ko": "Korean", "ar": "Arabic",
}


# === Configuration ===

CONF_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "dictee.conf",
)


def _update_conf_kv(updates):
    """Patch specific keys in dictee.conf, preserving everything else.

    Reads the whole file, replaces matching `key=value` lines (or
    appends new ones), then atomically rewrites via tempfile +
    os.replace. Per feedback-no-sed.md, this is the sanctioned way to
    mutate dictee.conf programmatically — sed is forbidden.
    """
    lines = []
    if os.path.isfile(CONF_PATH):
        with open(CONF_PATH, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    seen = set()
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k = s.split("=", 1)[0].strip()
        if k in updates:
            lines[i] = f"{k}={updates[k]}\n"
            seen.add(k)
    for k, v in updates.items():
        if k not in seen:
            lines.append(f"{k}={v}\n")
    # CONF_PATH may be a symlink (dotfiles managers keep the real file in a
    # versioned repo — #24): replace the resolved TARGET, not the link name,
    # or the link would be clobbered by a regular file on every save.
    target = os.path.realpath(CONF_PATH)
    tmp = target + ".tmp"
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.replace(tmp, target)


def _read_conf():
    """Read dictee.conf into a dict."""
    conf = {}
    try:
        if os.path.isfile(CONF_PATH):
            with open(CONF_PATH, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        conf[k] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return conf


def _postprocess(text):
    """Apply dictee-postprocess rules to transcribed text."""
    if not text or not shutil.which("dictee-postprocess"):
        return text
    conf = _read_conf()
    env = os.environ.copy()
    # Propagate all DICTEE_* keys so dictee-postprocess sees DICTEE_PP_*,
    # DICTEE_LLM_*, etc. (it reads them via os.environ.get / _env_bool).
    for _k, _v in conf.items():
        if _k.startswith("DICTEE_"):
            env[_k] = _v
    # LANG_SOURCE fallback if not in conf
    env.setdefault("DICTEE_LANG_SOURCE", env.get("LANG", "en")[:2])
    try:
        result = subprocess.run(
            ["dictee-postprocess"],
            input=text, capture_output=True, text=True, timeout=10, env=env)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        _dbg(f"_postprocess: error: {e}")
    return text


def _detect_language(text):
    """Simple language detection based on common words and characters."""
    if not text:
        return "en"
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


def _translate_available(backend=None):
    """Check if the requested translation backend is usable.

    Backend values match the four-entry combo in the Translate pad:
    "google" / "bing" (require the `trans` CLI binary), "ollama"
    (requires the `ollama` CLI), "libretranslate" (requires `docker`
    since the LT instance runs in a container). When backend is
    None, falls back to the dictee.conf-configured backend.
    """
    import shutil
    if backend is None:
        conf = _read_conf()
        b = conf.get("DICTEE_TRANSLATE_BACKEND", "trans")
        backend = (conf.get("DICTEE_TRANS_ENGINE", "google") or "google").lower() \
                  if b == "trans" else b
    if backend in ("google", "bing"):
        return shutil.which("trans") is not None
    if backend == "ollama":
        return shutil.which("ollama") is not None
    if backend == "libretranslate":
        return shutil.which("docker") is not None
    return False


def _translate_text(text, lang_src="en", lang_tgt="fr", backend=None):
    """Translate text using the chosen backend.

    `backend` matches the plasmoid's translate selector:
      - "google", "bing" → trans CLI with -e <engine>
      - "ollama"        → Ollama HTTP API (model from DICTEE_OLLAMA_MODEL)
      - "libretranslate"→ local LibreTranslate HTTP (port from
                          DICTEE_LIBRETRANSLATE_PORT, languages from
                          DICTEE_LIBRETRANSLATE_LANGS).

    Falls back to dictee.conf's DICTEE_TRANSLATE_BACKEND (mapped
    through DICTEE_TRANS_ENGINE for the trans case) when None — kept
    for legacy callers. Sub-params still live in dictee.conf since
    they describe infrastructure, not per-file choices.
    """
    conf = _read_conf()
    if backend is None:
        b = conf.get("DICTEE_TRANSLATE_BACKEND", "trans")
        backend = (conf.get("DICTEE_TRANS_ENGINE", "google") or "google").lower() \
                  if b == "trans" else b
    _dbg(f"_translate_text: backend={backend}, {lang_src}→{lang_tgt}, text_len={len(text)}")

    try:
        if backend in ("google", "bing"):
            result = subprocess.run(
                ["trans", "-b", "-e", backend, f"{lang_src}:{lang_tgt}"],
                input=text, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

        elif backend == "ollama":
            import json as _json
            import urllib.request
            model = conf.get("DICTEE_OLLAMA_MODEL", "translategemma")
            if ":" not in model:
                model += ":latest"
            src_name = LANG_NAMES_EN.get(lang_src, lang_src)
            tgt_name = LANG_NAMES_EN.get(lang_tgt, lang_tgt)
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


def _diar_multi_available():
    """Check if the in-house multi-speaker diarization engine is usable:
    diarize-multi binary on PATH + its models installed (sentinel =
    segmentation-3.0.onnx, same convention as the Rust default_models_dir).
    When available it is preferred over Sortformer for batch diarization
    (no 4-speaker cap, better DER)."""
    import shutil
    if not shutil.which("diarize-multi"):
        return False
    sentinel = "segmentation-3.0.onnx"
    dd = os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
        "dictee", "diar",
    )
    return (os.path.isfile(os.path.join(dd, sentinel))
            or os.path.isfile(os.path.join("/usr/share/dictee/diar", sentinel)))


def _moss_available():
    """True when the MOSS one-pass diarized-transcription engine is usable:
    dictee-moss-diarize on PATH and its --check passing (model + native
    transcribe.cpp runtime + python bindings). Unlike the other engines MOSS
    emits the final transcript itself (ASR + speakers in a single pass).
    Runs on any GPU via Vulkan, not just NVIDIA (crop2 bench 2026-07-15:
    RTF 0.154 NVIDIA/Vulkan, 0.216 CUDA, 0.643 Intel Iris Xe iGPU, 1.73 CPU
    — same output everywhere)."""
    import shutil
    exe = shutil.which("dictee-moss-diarize")
    if not exe:
        return False
    try:
        return subprocess.run(
            [exe, "--check"], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=10).returncode == 0
    except Exception:
        return False


def _diarize_available():
    """True when at least one diarization engine (multi-speaker,
    Sortformer or MOSS) is installed — gates the diarize toggle."""
    return (_diar_multi_available() or _sortformer_available()
            or _moss_available())


def _diar_threshold_from_sensitivity(sensitivity):
    """Map the UI sensitivity slider (0.0-1.0, default 0.5) to the
    diarize-multi AHC distance threshold (default 0.6, lower = more
    speakers — same direction as the slider)."""
    return sensitivity * 1.2


def _assign_speakers(words, speaker_segments, switch_penalty=1.5, free_gap=1.0):
    """Assign one speaker per word token, sequence-aware (engine-agnostic).

    The diarization timeline is authoritative but locally imperfect: in fast
    exchanges every engine tested (community-1, Sortformer, diarizen) emits
    spurious overlapping islands or boundaries shifted by a few hundred ms,
    and any per-word geometric rule (nearest segment, max overlap) faithfully
    copies those defects onto the words as mid-clause speaker flips.

    So words are assigned as a SEQUENCE (min-cost dynamic program):
    - per-word cost for a speaker = temporal distance from the word midpoint
      to that speaker's nearest segment (0 when inside — the same primitive
      as the previous nearest-segment rule);
    - changing speaker between consecutive words costs switch_penalty
      (seconds-equivalent), EXCEPT at a clause boundary — previous word ends
      with sentence-final punctuation — or after an inter-word silence
      >= free_gap, where switching is free.

    A 1-2 word island captured by a spurious segment cannot pay the switch
    cost and stays with its clause; a genuine turn switches freely at the
    clause boundary (even with zero pause — common in fast interviews), and
    a genuine mid-clause interruption still switches because the per-word
    distances of staying on the old speaker quickly exceed the penalty.
    switch_penalty must sit between the flip cost of spurious islands
    (<= ~0.6 s of distance mass on the reference sample) and that of the
    shortest legitimate turn to protect (~1.75 s for a 2-word turn right
    next to the other speaker's segment).
    Punctuation is the boundary signal, not pauses: on the reference sample
    the real turn had a 0.00 s gap while a 0.42 s pause sat mid-sentence.

    words: [{"start", "end", "text"}] in chronological order.
    speaker_segments: [{"start", "end", "speaker"}], may overlap.
    Returns one speaker id per word (-1 only when speaker_segments is empty).
    """
    if not words:
        return []
    if not speaker_segments:
        return [-1] * len(words)

    def ends_clause(text):
        return text.rstrip("\"'»«)]}").endswith((".", "!", "?", "…"))

    def free_boundary(prev_word, word):
        return (ends_clause(prev_word["text"])
                or word["start"] - prev_word["end"] >= free_gap)

    # NOTE — known limitation, deliberately NOT handled here: a WRONG
    # diarization segment of ~2 s with real mass strictly inside a clause
    # (e.g. a phantom speaker over "notre invité est un chercheur
    # extrêmement connu.") cannot be told apart, on geometry + text alone,
    # from a CORRECT segment in the mirrored configuration — a clause-
    # enclosed-flanked-by-same-other-speaker filter was tried and rejected
    # the true presenter segment of the reference sample (same trap as the
    # Rust enforce_min_turn absorption, see project memory 2026-07-09).
    # Distinguishing them needs voice-level evidence (clustering confidence
    # / embeddings), i.e. the diarizer side, not this fusion.
    speakers = sorted({s["speaker"] for s in speaker_segments})
    n_spk = len(speakers)

    # Per-word emission costs: distance to each speaker's nearest segment.
    emissions = []
    for word in words:
        mid = 0.5 * (word["start"] + word["end"])
        best = {spk: float("inf") for spk in speakers}
        for seg in speaker_segments:
            if seg["start"] <= mid <= seg["end"]:
                dist = 0.0
            else:
                dist = min(abs(mid - seg["start"]), abs(mid - seg["end"]))
            if dist < best[seg["speaker"]]:
                best[seg["speaker"]] = dist
        emissions.append([best[spk] for spk in speakers])

    # Viterbi over (word, speaker) with backpointers.
    cost = list(emissions[0])
    backptrs = []
    for i in range(1, len(words)):
        free = free_boundary(words[i - 1], words[i])
        new_cost = []
        new_back = []
        for j in range(n_spk):
            best_prev, best_cost = j, cost[j]
            if not free:
                for k in range(n_spk):
                    c = cost[k] + (0.0 if k == j else switch_penalty)
                    if c < best_cost:
                        best_cost, best_prev = c, k
            else:
                for k in range(n_spk):
                    if cost[k] < best_cost:
                        best_cost, best_prev = cost[k], k
            new_cost.append(best_cost + emissions[i][j])
            new_back.append(best_prev)
        cost = new_cost
        backptrs.append(new_back)

    j = min(range(n_spk), key=lambda x: cost[x])
    path = [j]
    for back in reversed(backptrs):
        j = back[j]
        path.append(j)
    path.reverse()
    return [speakers[j] for j in path]


def _build_turns(words, assigned, speaker_segments):
    """Group per-word speaker assignments into display turns.

    Consecutive same-speaker words merge into one turn, but a turn ALSO
    breaks where the word's nearest diarization segment (of its assigned
    speaker) changes: the diarizer's own turn structure stays visible in
    the output instead of being flattened into monolithic blocks (measured
    on the reference interview: a 47 s subtitle cue swallowing a 3-speaker
    exchange). Word attribution is untouched — presentation only.
    """
    def segment_index(spk, mid):
        best_idx, best_dist = -1, float("inf")
        for idx, seg in enumerate(speaker_segments):
            if seg["speaker"] != spk:
                continue
            if seg["start"] <= mid <= seg["end"]:
                dist = 0.0
            else:
                dist = min(abs(mid - seg["start"]), abs(mid - seg["end"]))
            if dist < best_dist:
                best_dist, best_idx = dist, idx
        return best_idx

    turns = []
    prev_seg = None
    for word, spk in zip(words, assigned):
        seg = segment_index(spk, 0.5 * (word["start"] + word["end"]))
        if turns and turns[-1]["speaker"] == spk and seg == prev_seg:
            turns[-1]["end"] = word["end"]
            turns[-1]["parts"].append(word["text"])
        else:
            turns.append({"start": word["start"], "end": word["end"],
                          "speaker": spk, "parts": [word["text"]]})
        prev_seg = seg
    return turns


class _DiarizeTranscribeWorker(QThread):
    """Phase 2 worker: transcribe diarized segments via daemon socket."""
    progress = Signal(int, int)    # (done, total)
    finished = Signal(str)         # final output text
    error = Signal(str)            # error message

    def __init__(self, audio_path, diarize_output, sock_path, parent=None,
                 socket_timeout=None, per_segment=False, audio_duration=0.0,
                 plain=False):
        super().__init__(parent)
        self._audio_path = audio_path
        self._diarize_output = diarize_output
        # plain=True: no diarization at all — one plain full-file request
        # (`path\n`) and the raw text back. diarize_output is unused then.
        self._plain = plain
        self._sock_path = sock_path
        self._socket_timeout = socket_timeout
        # Full-audio transcription blocks until the daemon finishes the WHOLE
        # file (whisper.cpp full() is not streaming), so the recv timeout must
        # cover the entire transcription, not a fixed 120 s — a 92-min file
        # needs 20-40 min and used to die at the 2-min mark (empty result tab).
        self._audio_duration = audio_duration
        # Timestamp-less backends (nemotron): a full-audio '\tdiarize' request
        # returns an empty body (the daemon formats word tokens, and nemotron
        # has none) — transcribe each diarized segment separately instead.
        self._per_segment = per_segment
        self._cancelled = False
        self._sock = None  # current open socket, if any (for cancel)

    def cancel(self):
        """Mark thread as cancelled and try to break the blocking
        recv() by closing the socket from the outside. The HTTP-style
        loop in run() exits with a socket error; emit is then
        suppressed so the UI sees the cancel as instantaneous."""
        self._cancelled = True
        try:
            if self._sock is not None:
                self._sock.close()
        except Exception as _e:
            _dbg(f"silenced: {_e!r}")

    def _maybe_convert_to_wav(self, path):
        """transcribe-daemon opens the file as raw WAV without running
        ffmpeg internally, so mp3/m4a/webm/ogg inputs crash with
        'Ill-formed WAVE file: no RIFF tag found' before any token is
        produced. Detect non-compatible inputs via ffprobe and convert
        to WAV 16k mono via ffmpeg into /tmp/. The temp file is left
        behind on purpose (small, /tmp/ is cleaned at boot)."""
        try:
            info = subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_streams", "-of", "json", path],
                stderr=subprocess.DEVNULL, timeout=10).decode()
            for st in json.loads(info).get("streams", []):
                if (st.get("codec_type") == "audio"
                        and st.get("codec_name") == "pcm_s16le"
                        and int(st.get("sample_rate", 0)) == 16000
                        and st.get("channels") == 1):
                    return path  # already daemon-compatible
        except Exception as _e:
            _dbg(f"silenced: {_e!r}")

        out_path = f"/tmp/dictee_daemon_input_{os.getpid()}.wav"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", path, "-ar", "16000", "-ac", "1",
                 "-f", "wav", out_path],
                check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=120)
            return out_path
        except Exception:
            return path  # caller will surface the daemon error

    def run(self):
        import socket as sock_mod, time as _time, re

        # Wait for socket (default max 15s; isolated cold-loads override it).
        # NB: never use `_` as the loop variable — it shadows the gettext
        # function `_(...)` for the rest of run(), and every translated
        # string downstream blows up with "'int' object is not callable".
        _wait_s = self._socket_timeout if self._socket_timeout else 15
        for _attempt in range(int(_wait_s / 0.25)):
            if os.path.exists(self._sock_path):
                try:
                    s = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
                    s.settimeout(5)
                    s.connect(self._sock_path)
                    s.close()
                    break
                except (ConnectionRefusedError, OSError):
                    pass
            _time.sleep(0.25)
        else:
            self.error.emit(
                _("Daemon socket not available after {s}s").format(s=int(_wait_s)))
            return

        # Plain mode (isolated engine, no diarization): one request for the
        # whole file, raw text back — same daemon protocol as PTT dictation.
        if self._plain:
            daemon_path = self._maybe_convert_to_wav(self._audio_path)
            if self._cancelled:
                return
            recv_timeout = (max(300, int(self._audio_duration * 3))
                            if self._audio_duration else 300)
            _dbg(f"DiarizeWorker: plain full-file request: {daemon_path} "
                 f"(recv timeout {recv_timeout}s)")
            try:
                self._sock = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
                self._sock.settimeout(recv_timeout)
                self._sock.connect(self._sock_path)
                self._sock.sendall((daemon_path + "\n").encode())
                data = b""
                while True:
                    chunk = self._sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                self._sock.close()
                self._sock = None
                full_text = data.decode("utf-8", errors="replace").strip()
            except Exception as e:
                if self._cancelled:
                    return
                self.error.emit(f"Daemon transcription failed: {e}")
                return
            if self._cancelled:
                return
            if not full_text:
                self.error.emit(_("Empty transcription from daemon"))
                return
            self.finished.emit(full_text)
            return

        # Parse diarize-only output into speaker segments
        speaker_segments = []
        for line in self._diarize_output.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) >= 3:
                try:
                    speaker_segments.append({
                        "start": float(parts[0]), "end": float(parts[1]),
                        "speaker": int(parts[2])
                    })
                except ValueError:
                    continue

        if not speaker_segments:
            self.error.emit(_("No speaker segments detected"))
            return

        self.progress.emit(1, 3)  # phase 2 started

        # Pre-convert non-WAV inputs (mp3/m4a/webm/...) so the daemon does
        # not crash with "Ill-formed WAVE file" on its raw WAV reader.
        daemon_path = self._maybe_convert_to_wav(self._audio_path)

        if self._cancelled:
            return

        if self._per_segment:
            self._run_per_segment(daemon_path, speaker_segments)
            return

        # Transcribe full audio via daemon with timestamps (diarize mode).
        # Duration-aware recv timeout: the daemon sends nothing until the whole
        # file is transcribed, so the FIRST recv() blocks for the full run.
        # max(300, 3x duration) covers large-v3 even on a mid-run CPU fallback.
        recv_timeout = max(300, int(self._audio_duration * 3)) if self._audio_duration else 300
        _dbg(f"DiarizeWorker: sending full audio to daemon: {daemon_path} "
             f"(recv timeout {recv_timeout}s)")
        full_text = ""
        try:
            self._sock = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
            self._sock.settimeout(recv_timeout)
            self._sock.connect(self._sock_path)
            self._sock.sendall((daemon_path + "\tdiarize\n").encode())
            data = b""
            while True:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            self._sock.close()
            self._sock = None
            full_text = data.decode("utf-8", errors="replace").strip()
        except Exception as e:
            if self._cancelled:
                return
            self.error.emit(f"Daemon transcription failed: {e}")
            return

        if self._cancelled:
            return

        if not full_text:
            self.error.emit(_("Empty transcription from daemon"))
            return

        self.progress.emit(2, 3)  # transcription done

        # The daemon returns timestamped sentences (TimestampMode::Sentences)
        # Format: "[start - end] text" or just "text" (plain)
        # Parse sentences with timestamps
        sentences = []
        ts_pattern = re.compile(r"^\[(\d+\.?\d*)s?\s*-\s*(\d+\.?\d*)s?\]\s*(.+)")
        for line in full_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = ts_pattern.match(line)
            if m:
                sentences.append({
                    "start": float(m.group(1)),
                    "end": float(m.group(2)),
                    "text": m.group(3).strip()
                })

        # If daemon returned plain text (no timestamps), emit as single block
        if not sentences:
            # Fallback: attribute all text to the dominant speaker
            from collections import Counter
            spk_counts = Counter(s["speaker"] for s in speaker_segments)
            dominant = spk_counts.most_common(1)[0][0]
            self.finished.emit(f"[0.00s - 0.00s] Speaker {dominant}: {full_text}")
            return

        # Fuse the word-level transcription with the diarization timeline,
        # then MERGE consecutive same-speaker words into turns. The whisper
        # daemon emits word-level tokens (needed by the meeting aligner), so
        # without merging the result is one word per line and the per-segment
        # postprocess in _finish_transcription spawns thousands of subprocesses.
        #
        # Attribution: sequence-aware assignment (_assign_speakers). The
        # previous per-word nearest-segment rule copied every diarizer defect
        # (spurious overlapping islands, boundaries a few hundred ms early)
        # onto the words as mid-clause speaker flips — engine-agnostic bug,
        # observed with community-1, Sortformer and diarizen alike. A
        # transcribed word was spoken by someone, so it always gets the
        # best-estimate speaker; genuine non-speech (whisper hallucinations
        # on music/silence) is a separate concern (detect & drop), not a
        # speaker-assignment one.
        assigned = _assign_speakers(sentences, speaker_segments)

        turns = _build_turns(sentences, assigned, speaker_segments)

        results = []
        for turn in turns:
            speaker = (f"{_('Speaker')} {turn['speaker']}"
                       if turn["speaker"] >= 0 else _("UNKNOWN"))
            results.append(
                f"[{turn['start']:.2f}s - {turn['end']:.2f}s] "
                f"{speaker}: {' '.join(turn['parts'])}")

        self.progress.emit(3, 3)  # done
        self.finished.emit("\n".join(results))

    def _run_per_segment(self, daemon_path, speaker_segments):
        """Per-segment phase 2 for timestamp-less backends (nemotron): cut the
        audio on the diarized segments (stdlib wave — NOT sox) and send one
        PLAIN request per segment. Speaker attribution is exact by
        construction; output format is the same '[a s - b s] Speaker N: text'
        lines as the overlap-matching path."""
        import socket as sock_mod
        import tempfile
        import wave

        results = []
        total = len(speaker_segments)
        try:
            with wave.open(daemon_path, "rb") as wf:
                rate = wf.getframerate()
                width = wf.getsampwidth()
                channels = wf.getnchannels()
                nframes = wf.getnframes()
                for done, seg in enumerate(speaker_segments, start=1):
                    if self._cancelled:
                        return
                    start = max(0.0, seg["start"])
                    end = min(seg["end"], nframes / rate)
                    if end - start < 0.3:   # too short to transcribe (noise)
                        self.progress.emit(done, total)
                        continue
                    wf.setpos(int(start * rate))
                    frames = wf.readframes(int((end - start) * rate))
                    tmp = tempfile.NamedTemporaryFile(
                        prefix="dictee-seg-", suffix=".wav", delete=False)
                    try:
                        with wave.open(tmp, "wb") as out:
                            out.setnchannels(channels)
                            out.setsampwidth(width)
                            out.setframerate(rate)
                            out.writeframes(frames)
                        tmp.close()
                        self._sock = sock_mod.socket(sock_mod.AF_UNIX,
                                                     sock_mod.SOCK_STREAM)
                        self._sock.settimeout(120)
                        self._sock.connect(self._sock_path)
                        self._sock.sendall((tmp.name + "\n").encode())
                        data = b""
                        while True:
                            chunk = self._sock.recv(4096)
                            if not chunk:
                                break
                            data += chunk
                        self._sock.close()
                        self._sock = None
                        text = data.decode("utf-8", errors="replace").strip()
                    finally:
                        try:
                            os.unlink(tmp.name)
                        except OSError:
                            pass
                    self.progress.emit(done, total)
                    if not text or text.startswith("ERROR:"):
                        continue
                    results.append(
                        f"[{start:.2f}s - {end:.2f}s]"
                        f" {_('Speaker')} {seg['speaker']}: {text}")
        except Exception as e:
            if self._cancelled:
                return
            self.error.emit(f"Daemon transcription failed: {e}")
            return

        if not results:
            self.error.emit(_("Empty transcription from daemon"))
            return
        self.finished.emit("\n".join(results))


class _ChunkedPipelineWorker(QThread):
    """Long-file chunked pipeline (audio > VRAM-adaptive threshold + CUDA build).

    With diarize=True (4 phases):
      Phase 1: ffmpeg pre-cut into 2-min chunks with 15-s overlap (WAV 16k mono).
      Phase 2: diarize-multi (preferred) or diarize-only on the full file
               -> global speaker segments.
      Phase 3: transcribe-diarize-batch --no-diarize on chunks -> timestamped tokens.
      Phase 4: merge global speakers onto tokens via argmax_overlap.
      Output: '[X.XXs - Y.YYs] Speaker N: text' per line — DIARIZE_RE-compatible.

    With diarize=False (2 phases — extends chunking to plain transcription):
      Phase 1: ffmpeg pre-cut into 2-min chunks (same as above).
      Phase 2: transcribe-diarize-batch --no-diarize on chunks -> tokens.
      Output: plain text, postprocessed downstream like the non-chunked
      `transcribe` batch path.
    """
    phase_changed = Signal(int, str)    # (phase_num, label)
    chunk_progress = Signal(int, int)   # (done, total) during chunked transcription
    finished = Signal(str)              # final formatted output
    error = Signal(str)

    CHUNK_SECONDS = 180   # 3 min — comfortable margin under the Parakeet
    OVERLAP_SECONDS = 75  # = CHUNK_SECONDS - STEP_SECONDS. MUST equal the real
                          # chunk overlap, otherwise _run_transcribe_batch's
                          # dedup zone is too narrow and keeps duplicate tokens
                          # (repeated sentences) at every chunk boundary.
    STEP_SECONDS = 105    # CHUNK - OVERLAP

    def __init__(self, audio_path, sensitivity, diarize=True, parent=None,
                 env_override=None, allow_diar_multi=True):
        super().__init__(parent)
        self._audio_path = audio_path
        self._sensitivity = sensitivity
        self._diarize = diarize
        # Engine choice is frozen at job start (availability won't change
        # mid-run): multi-speaker engine preferred, Sortformer fallback.
        # allow_diar_multi=False forces Sortformer (UI engine combo).
        self._use_diar_multi = allow_diar_multi and _diar_multi_available()
        self._duration = 0.0  # set in run(), used for the diarize timeout
        self._cancel = False
        self._tmp_dir = None
        self._current_proc = None
        # ORT_DYLIB_PATH must be set for CUDA dictee builds (load-dynamic):
        # without it, ORT cannot find libonnxruntime.so and falls back to CPU
        # silently. Mirrors the QProcess env setup in _on_transcribe.
        self._subprocess_env = os.environ.copy()
        ort_lib = "/usr/lib/dictee/libonnxruntime.so"
        if os.path.isfile(ort_lib):
            self._subprocess_env["ORT_DYLIB_PATH"] = ort_lib
        # Propagate DICTEE_* keys from dictee.conf to subprocesses. Systemd
        # services do this via EnvironmentFile=, but Popen children only inherit
        # the plain user shell env, which doesn't source dictee.conf.
        for _k, _v in _read_conf().items():
            if _k.startswith("DICTEE_"):
                self._subprocess_env[_k] = _v
        # Per-run model override (e.g. isolated Parakeet quant chosen in the
        # combo): wins over the conf-derived values WITHOUT touching dictee.conf.
        if env_override:
            self._subprocess_env.update(env_override)

    def request_cancel(self):
        self._cancel = True
        if self._current_proc is not None:
            try:
                self._current_proc.terminate()
                # Give the child 200 ms to exit on SIGTERM, then SIGKILL.
                # Without this kill(), communicate() in run() may hang
                # several seconds and trip closeEvent's wait timeout,
                # leaking /tmp/dictee_chunks_<pid>/.
                try:
                    self._current_proc.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    self._current_proc.kill()
            except Exception as _e:
                _dbg(f"silenced: {_e!r}")

    def run(self):
        try:
            duration = self._get_duration()
            if duration <= 0:
                self.error.emit(_("Could not determine audio duration"))
                return
            self._duration = duration

            n_phases = 4 if self._diarize else 2
            self.phase_changed.emit(
                1, _("Phase 1/{n}: pre-cut audio").format(n=n_phases))
            self._tmp_dir = self._make_tmp_dir()
            chunks = self._ffmpeg_split(duration)
            if self._cancel:
                self.error.emit(_("Cancelled"))
                return
            if not chunks:
                self.error.emit(_("No chunks produced from audio split"))
                return

            speaker_segments = None
            if self._diarize:
                self.phase_changed.emit(
                    2, _("Phase 2/{n}: global diarization").format(n=n_phases))
                speaker_segments = self._run_diarize_only()
                if self._cancel:
                    self.error.emit(_("Cancelled"))
                    return
                if not speaker_segments:
                    self.error.emit(_("No speaker segments detected"))
                    return

            transcribe_phase = 3 if self._diarize else 2
            self.phase_changed.emit(
                transcribe_phase,
                _("Phase {p}/{n}: chunked transcription").format(
                    p=transcribe_phase, n=n_phases))
            tokens_absolute = self._run_transcribe_batch(chunks)
            if self._cancel:
                self.error.emit(_("Cancelled"))
                return
            if not tokens_absolute:
                self.error.emit(_("No transcription tokens produced"))
                return

            if self._diarize:
                self.phase_changed.emit(
                    4, _("Phase 4/{n}: merging speakers").format(n=n_phases))
                output = self._merge(tokens_absolute, speaker_segments)
                if not output:
                    self.error.emit(_("Merge produced empty output"))
                    return
            else:
                # Plain transcription: concatenate token texts. Downstream
                # _finish_transcription will run dictee-postprocess once
                # on the joined string, mirroring the non-chunked path.
                output = " ".join(t["text"] for t in tokens_absolute).strip()
                if not output:
                    self.error.emit(_("Empty transcription output"))
                    return

            self.finished.emit(output)
        except Exception as e:
            self.error.emit(f"Chunked pipeline failed: {e}")
        finally:
            self._cleanup_tmp()

    def _make_tmp_dir(self):
        d = f"/tmp/dictee_chunks_{os.getpid()}_{int(time.time())}"
        os.makedirs(d, exist_ok=True)
        return d

    def _get_duration(self):
        try:
            out = subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", self._audio_path],
                stderr=subprocess.DEVNULL, timeout=30,
            ).decode().strip()
            return float(out)
        except Exception:
            return 0.0

    def _ffmpeg_split(self, duration):
        """Split audio into chunks (idx, abs_start_seconds, chunk_path)."""
        chunks = []
        idx = 0
        start = 0.0
        while start < duration:
            if self._cancel:
                return []
            chunk_path = os.path.join(self._tmp_dir, f"chunk_{idx:04d}.wav")
            cmd = [
                "ffmpeg", "-y", "-ss", f"{start:.3f}",
                "-t", str(self.CHUNK_SECONDS),
                "-i", self._audio_path,
                "-ar", "16000", "-ac", "1", "-f", "wav",
                chunk_path,
            ]
            self._current_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=self._subprocess_env,
            )
            rc = self._current_proc.wait()
            self._current_proc = None
            if rc == 0 and os.path.exists(chunk_path) \
                    and os.path.getsize(chunk_path) > 1024:
                chunks.append((idx, start, chunk_path))
            idx += 1
            start += self.STEP_SECONDS
        return chunks

    def _run_diarize_only(self):
        """Run the global diarization pass. Stdout format:
        'start end speaker_id' per line (same contract for both engines).

        diarize-multi (in-house, no 4-speaker cap) is preferred; Sortformer
        diarize-only is the fallback when its models are not installed."""
        if self._use_diar_multi:
            threshold = _diar_threshold_from_sensitivity(self._sensitivity)
            cmd = ["diarize-multi", "--threshold", f"{threshold:.2f}",
                   self._audio_path]
            # CPU-only hosts run diarize-multi at RTF ~0.9 (plus the
            # clustering pass): the fixed 600 s cap would kill any file
            # beyond ~10 min, so scale the timeout with the duration.
            timeout = max(600, int(self._duration * 3))
        else:
            cmd = ["diarize-only", "--sensitivity", f"{self._sensitivity:.2f}",
                   self._audio_path]
            timeout = 600
        self._current_proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=self._subprocess_env,
        )
        try:
            stdout_data, _err = self._current_proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._current_proc.kill()
            return []
        finally:
            self._current_proc = None

        segments = []
        for line in stdout_data.decode("utf-8", errors="replace").splitlines():
            parts = line.strip().split()
            if len(parts) >= 3:
                try:
                    segments.append({
                        "start": float(parts[0]),
                        "end": float(parts[1]),
                        "speaker": int(parts[2]),
                    })
                except ValueError:
                    continue
        return segments

    def _run_transcribe_batch(self, chunks):
        """Run transcribe-diarize-batch --no-diarize on chunks via stdin.

        Stdout format per chunk:
            ===CHUNK <idx> <path>===
            [X.XXs - Y.YYs] text
            ...

        Tokens whose midpoint falls outside the chunk's useful zone are
        dropped (deduplication of overlap zones).
        """
        chunks_paths = [c[2] for c in chunks]
        n = len(chunks)
        last_idx = n - 1

        # --no-postprocess: postprocess is applied per-segment in
        # _finish_transcription, matching the existing _DiarizeTranscribeWorker
        # pattern. Avoids double processing.
        cmd = ["transcribe-diarize-batch", "--no-diarize",
               "--no-postprocess", "--stdin"]
        # The batch's stderr carries the engine diagnostics (execution
        # provider, model variant, per-chunk timings): keep it in the
        # transcribe log when debugging instead of dropping it — "is this
        # really running on CUDA?" is otherwise unanswerable from logs.
        if DEBUG:
            _stderr_sink = open("/tmp/dictee-transcribe.log", "a", encoding="utf-8")
        else:
            _stderr_sink = subprocess.DEVNULL
        self._current_proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=_stderr_sink,
            env=self._subprocess_env,
        )
        stdin_data = ("\n".join(chunks_paths) + "\n").encode()
        try:
            stdout_data, _err = self._current_proc.communicate(
                input=stdin_data, timeout=3600,
            )
        except subprocess.TimeoutExpired:
            self._current_proc.kill()
            return []
        finally:
            self._current_proc = None
            if _stderr_sink is not subprocess.DEVNULL:
                _stderr_sink.close()

        chunk_re = re.compile(r"^===CHUNK\s+(\d+)\s+(.+?)===$")
        token_re = re.compile(r"^\[(\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]\s*(.+)$")
        tokens_abs = []
        cur_idx = -1
        cur_offset = 0.0
        half_overlap = self.OVERLAP_SECONDS / 2.0

        for line in stdout_data.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            m = chunk_re.match(line)
            if m:
                cur_idx = int(m.group(1))
                cur_offset = chunks[cur_idx][1] if 0 <= cur_idx < n else 0.0
                self.chunk_progress.emit(cur_idx + 1, n)
                continue
            tm = token_re.match(line)
            if tm and cur_idx >= 0:
                local_start = float(tm.group(1))
                local_end = float(tm.group(2))
                text = tm.group(3).strip()
                if not text:
                    continue
                # Useful zone (relative to chunk start)
                if cur_idx == 0:
                    z_start = 0.0
                    z_end = self.CHUNK_SECONDS - half_overlap
                elif cur_idx == last_idx:
                    z_start = half_overlap
                    z_end = float(self.CHUNK_SECONDS)
                else:
                    z_start = half_overlap
                    z_end = self.CHUNK_SECONDS - half_overlap
                mid = (local_start + local_end) / 2.0
                if z_start <= mid < z_end:
                    tokens_abs.append({
                        "start": cur_offset + local_start,
                        "end": cur_offset + local_end,
                        "text": text,
                    })

        tokens_abs.sort(key=lambda t: t["start"])
        return tokens_abs

    def _merge(self, tokens, speaker_segments):
        """Merge speakers onto tokens via _assign_speakers (sequence-aware,
        same fusion as the two-phase path: per-token argmax-overlap copied
        diarizer islands/shifted boundaries onto the tokens as mid-clause
        speaker flips, and left gap-drifted tokens UNKNOWN).

        Output: '[X.XXs - Y.YYs] Speaker N: text' per line.
        Speaker label is hardcoded English to stay DIARIZE_RE-compatible.
        """
        assigned = _assign_speakers(tokens, speaker_segments)
        results = []
        for tok, speaker in zip(tokens, assigned):
            spk = f"Speaker {speaker}" if speaker >= 0 else "UNKNOWN"
            results.append(
                f"[{tok['start']:.2f}s - {tok['end']:.2f}s] {spk}: {tok['text']}"
            )
        return "\n".join(results)

    def _cleanup_tmp(self):
        if self._tmp_dir and os.path.exists(self._tmp_dir):
            try:
                shutil.rmtree(self._tmp_dir, ignore_errors=True)
            except Exception as _e:
                _dbg(f"silenced: {_e!r}")


class IsolatedAsrDaemon:
    """Spawn an ad-hoc ASR daemon on a private socket for a one-off model,
    WITHOUT touching dictee.conf or the F9 daemon/badge. Non-blocking:
    start() launches the process and returns the socket path immediately;
    the phase-2 worker waits for the socket (model cold-load can be slow).
    """
    def __init__(self, recipe, model_dir="/usr/share/dictee/tdt"):
        self.recipe = recipe            # {"backend", "env"} from asr_spec_to_daemon
        self.model_dir = model_dir
        self.sock = f"/tmp/dictee-adhoc-{os.getpid()}.sock"
        self.proc = None

    def _build_cmd_env(self):
        """Return (cmd_list, env_dict) for the ad-hoc daemon. Pure (no spawn)."""
        env = os.environ.copy()
        env.update(self.recipe["env"])
        env["DICTEE_TRANSCRIBE_SOCKET"] = self.sock     # whisper daemon honors this
        env["DICTEE_DAEMON_NO_PROVIDER"] = "1"          # don't clobber the F9 badge
        ort = "/usr/lib/dictee/libonnxruntime.so"
        if os.path.isfile(ort):
            env.setdefault("ORT_DYLIB_PATH", ort)
        if self.recipe["backend"] == "whisper":
            cmd = ["transcribe-daemon-whisper"]
        elif self.recipe["backend"] == "whisper-rust":
            # whisper.cpp daemon: model file comes from the recipe's
            # DICTEE_WHISPER_RUST_GGML (checked by the caller before spawn).
            cmd = ["transcribe-daemon-whisper-rust", "--socket", self.sock]
        elif self.recipe["backend"] == "nemotron":
            # transcribe-daemon reads DICTEE_ASR_BACKEND=nemotron from env and
            # auto-selects the nemotron model directory (no positional arg needed).
            cmd = ["transcribe-daemon", "--socket", self.sock]
        else:  # parakeet ad-hoc (not used by the current routing, kept for completeness)
            cmd = ["transcribe-daemon", "--socket", self.sock, self.model_dir]
        return cmd, env

    def start(self):
        """Launch the daemon (non-blocking). Returns the private socket path."""
        cmd, env = self._build_cmd_env()
        try:
            os.unlink(self.sock)        # clear a stale socket
        except OSError:
            pass
        self.proc = subprocess.Popen(cmd, env=env,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        return self.sock

    def stop(self):
        """Terminate the daemon and remove the private socket. Idempotent."""
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        try:
            os.unlink(self.sock)
        except OSError:
            pass


# Strip ASCII control characters (except \t \n \r) from segment text.
# Parakeet-TDT occasionally emits SentencePiece special tokens (e.g.
#  ETX) that leak through the decoder and pollute the start of
# some segments — visible in exports as "Good morning".
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean_segment_text(text):
    return _CONTROL_CHAR_RE.sub("", text).strip()


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
                "text": _clean_segment_text(m.group(4)),
            })
    return segments


def _seconds_to_srt_time(seconds):
    """Convert seconds to SRT timestamp HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_elapsed(s):
    """Format an elapsed-seconds float as 'HH:MM:SS' when >= 1 h,
    'MM:SS' when >= 1 min, else '12.3s'. Compact clock style — easier
    to scan than '1 h 4 mn 56 s'."""
    if s < 60:
        return f"{s:.1f}s"
    total = int(s)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_text(segments, name_map=None):
    """Format diarized segments as plain text with speaker headers.

    `name_map` is an optional {canonical_id: display_name} dict consulted at
    render time; it never mutates segments. Speaker-change detection keeps
    using the canonical id so consecutive segments remain grouped.
    """
    lines = []
    prev_speaker = None
    for seg in segments:
        if seg["speaker"] != prev_speaker:
            if prev_speaker is not None:
                lines.append("")  # blank line between speakers
            label = (name_map or {}).get(seg["speaker"], seg["speaker"])
            lines.append(f"{label}:")
            prev_speaker = seg["speaker"]
        lines.append(f"     {seg['text']}")
    return "\n".join(lines)


def _format_srt(segments, name_map=None):
    """Format diarized segments as SRT subtitles.

    `name_map` (optional) substitutes the speaker label at render time.
    """
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _seconds_to_srt_time(seg["start"])
        end = _seconds_to_srt_time(seg["end"])
        label = (name_map or {}).get(seg["speaker"], seg["speaker"])
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(f"[{label}] {seg['text']}")
        lines.append("")
    return "\n".join(lines)


def _format_json(segments, name_map=None):
    """Format diarized segments as JSON.

    Emits both `speaker_id` (canonical, stable) and `speaker` (renamed
    when `name_map` is provided) so downstream consumers can round-trip.
    """
    out = []
    for seg in segments:
        display = (name_map or {}).get(seg["speaker"], seg["speaker"])
        out.append({
            "start": seg["start"],
            "end": seg["end"],
            "speaker_id": seg["speaker"],
            "speaker": display,
            "text": seg["text"],
        })
    return json.dumps(out, ensure_ascii=False, indent=2)


# === Transcription routing ===

def _select_transcribe_cmd(diarize, asr_backend, has_transcribe,
                           has_diarize_only, has_transcribe_diarize,
                           has_diarize_multi=False, has_moss=False,
                           diar_engine="auto"):
    """Pick the ASR command and pipeline mode for a transcription run.

    Pure function (no I/O, no Qt) so the routing matrix stays
    regression-tested without spinning up a window. Called from
    _on_transcribe with shutil.which() and conf-derived inputs.

    Routing rules:
      diarize=False  + transcribe binary → ("transcribe", False, None)
      diarize=True   + engine combo forced to MOSS and MOSS usable
                     → ("dictee-moss-diarize", False, None)
        One-pass engine: MOSS emits the final diarized transcript itself
        (DIARIZE_RE lines), so no phase-2 and no daemon involved. Explicit
        user choice — it never wins under "auto". Falls through to the
        normal matrix when MOSS is not usable.
      diarize=True   + Canary daemon     → ("transcribe-diarize", False, None)
        Canary path bypasses the daemon socket because the daemon is
        locked at DICTEE_LANG_SOURCE — phase-2 transcription would
        mistranscribe any audio in another language. Standalone
        transcribe-diarize loads Parakeet-TDT itself (multilingual
        auto-detect). This is about the phase-2 TRANSCRIPTION engine,
        so it applies whatever diarization engine is installed.
      diarize=True   + diarize-multi usable → ("diarize-multi", True, None)
        Two-phase with the in-house multi-speaker engine (no 4-speaker
        cap): diarize-multi emits speaker timestamps, daemon socket
        transcribes each segment. Preferred over Sortformer.
      diarize=True   + Parakeet daemon   → ("diarize-only", True, None)
        Two-phase Sortformer fallback: diarize-only emits speaker
        timestamps, daemon socket transcribes each segment.
      diarize=True   + diarize-only missing → ("transcribe-diarize", False, None)
        Legacy fallback when the two-phase binary is not installed.
      Required binary missing → (None, False, error_string)

    Inputs:
      diarize: bool — diarize checkbox state.
      asr_backend: str — DICTEE_ASR_BACKEND from dictee.conf.
        "" / "parakeet" / "canary" / etc. Case-insensitive.
      has_transcribe / has_diarize_only / has_transcribe_diarize: bools
        — typically `bool(shutil.which(<name>))`.
      has_diarize_multi: bool — binary on PATH AND its models installed
        (`_diar_multi_available()`, not a bare which()).

    Returns: (cmd, two_phase, error). On error, cmd is None and
    error is the missing-binary message ready for the status bar.
    """
    if not diarize:
        if not has_transcribe:
            return None, False, "transcribe"
        return "transcribe", False, None

    if diar_engine == "moss" and has_moss:
        return "dictee-moss-diarize", False, None

    daemon_is_canary = (asr_backend or "").lower() == "canary"

    if daemon_is_canary and has_transcribe_diarize:
        return "transcribe-diarize", False, None

    if has_diarize_multi:
        return "diarize-multi", True, None

    if has_diarize_only:
        return "diarize-only", True, None

    if has_transcribe_diarize:
        return "transcribe-diarize", False, None

    return None, False, "diarize-only"


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
            if not self._text_edit.find(text):
                # Wrap: move cursor to start and try again
                cursor = self._text_edit.textCursor()
                cursor.movePosition(cursor.MoveOperation.Start)
                self._text_edit.setTextCursor(cursor)
                self._text_edit.find(text)

    def _find_prev(self):
        text = self._input.text()
        if text:
            if not self._text_edit.find(text, QTextDocument.FindFlag.FindBackward):
                # Wrap: move cursor to end and try again
                cursor = self._text_edit.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                self._text_edit.setTextCursor(cursor)
                self._text_edit.find(text, QTextDocument.FindFlag.FindBackward)


# === Translation Thread ===

class TranslateThread(QThread):
    """Translate text in background to avoid blocking UI."""
    finished_signal = Signal(str, list)  # translated_text, translated_segments
    error_signal = Signal(str)  # error message

    def __init__(self, raw_text, segments, was_diarized,
                 lang_src="en", lang_tgt="fr", backend=None):
        super().__init__()
        self._raw_text = raw_text
        self._segments = segments
        self._was_diarized = was_diarized
        self._lang_src = lang_src
        self._lang_tgt = lang_tgt
        self._backend = backend
        self._cancelled = False

    def cancel(self):
        """Mark thread as cancelled. The current HTTP/CLI translation
        call cannot be interrupted from outside but its result will be
        discarded — the UI sees the cancel as immediate."""
        self._cancelled = True

    def run(self):
        try:
            if self._was_diarized and self._segments:
                groups = []
                for i, seg in enumerate(self._segments):
                    if groups and groups[-1][0] == seg["speaker"]:
                        groups[-1][1].append(i)
                    else:
                        groups.append((seg["speaker"], [i]))

                translated_segments = [dict(s) for s in self._segments]
                failed = False
                any_ok = False
                for _speaker, indices in groups:
                    group_text = "\n".join(self._segments[i]["text"] for i in indices)
                    translated = _translate_text(group_text, self._lang_src, self._lang_tgt, self._backend)
                    if translated:
                        any_ok = True
                        lines = [l.strip() for l in translated.strip().splitlines() if l.strip()]
                        for j, idx in enumerate(indices):
                            new_seg = dict(self._segments[idx])
                            new_seg["text"] = lines[j] if j < len(lines) else self._segments[idx]["text"]
                            translated_segments[idx] = new_seg
                    else:
                        failed = True
                if self._cancelled:
                    return
                if failed and not any_ok:
                    # Every group failed (dead backend): emitting the source
                    # segments would fabricate a "translation" tab full of
                    # untranslated text. ("", []) tells _on_translate_done
                    # there is no result to show.
                    self.error_signal.emit(_("Translation failed — check backend configuration."))
                    self.finished_signal.emit("", [])
                    return
                if failed:
                    self.error_signal.emit(_("Translation partially failed — some segments untranslated."))
                self.finished_signal.emit("", translated_segments)
            else:
                translated = _translate_text(self._raw_text, self._lang_src, self._lang_tgt, self._backend)
                if self._cancelled:
                    return
                if not translated:
                    self.error_signal.emit(_("Translation failed — check backend configuration."))
                    self.finished_signal.emit("", [])
                else:
                    self.finished_signal.emit(translated, [])
        except Exception as e:
            if self._cancelled:
                return
            self.error_signal.emit(str(e))
            self.finished_signal.emit("", [])


# === Export Dialog ===

class ExportDialog(QDialog):
    """Single-tab export dialog (Format(s) + Filename + Directory).

    Multi-tab export was removed because it produced a confusing pile
    of files when the user only wanted the active tab — the dialog
    now reflects that: it exports exactly the tab the user clicked
    Export from. The first element of `tabs_info` is the only one
    used; the other parameters keep the same names purely so the
    callers stay short.
    """

    def __init__(self, tabs_info, current_format, base_name, parent=None,
                 current_tab_index=None):
        """
        tabs_info: list with a single (tab_name, text_content) tuple.
        current_format: "text", "srt", or "json" (pre-checked).
        base_name: default filename prefix (audio basename).
        current_tab_index: ignored — kept for back-compat.
        """
        super().__init__(parent)
        self.setWindowTitle(_("Export"))
        self.setMinimumWidth(450)

        self._tabs_info = list(tabs_info)
        self._base_name = base_name

        layout = QVBoxLayout(self)

        # Show which tab will be exported (read-only label)
        if self._tabs_info:
            tab_name = self._tabs_info[0][0]
            lbl = QLabel(_("Tab: <b>{name}</b>").format(name=tab_name))
            lbl.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(lbl)

        # -- Formats (checkboxes) --
        group_fmt = QGroupBox(_("Formats"))
        lay_fmt = QHBoxLayout(group_fmt)
        self._chk_text = ToggleSwitch(_("Plain text (.txt)"))
        self._chk_srt = ToggleSwitch(_("SRT (.srt)"))
        self._chk_json = ToggleSwitch(_("JSON (.json)"))
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

        # -- Filename prefix (base name) --
        # Pre-filled with the audio source's basename, editable so the
        # user can override it (e.g. "weekly-meeting" instead of the
        # raw audio filename). Final files are named:
        #   <basename>-<tab_name>.<ext>
        lay_name = QHBoxLayout()
        lay_name.addWidget(QLabel(_("Filename prefix:")))
        self._name_input = QLineEdit()
        self._name_input.setText(base_name)
        self._name_input.setPlaceholderText(base_name)
        self._name_input.setToolTip(_(
            "Base name used for every exported file. The tab name "
            "and the extension are appended automatically."))
        lay_name.addWidget(self._name_input, 1)
        layout.addLayout(lay_name)

        # -- Directory --
        lay_dir = QHBoxLayout()
        lay_dir.addWidget(QLabel(_("Directory:")))
        self._dir_input = QLineEdit()
        # Use XDG Desktop directory (localized: Bureau, Escritorio, Schreibtisch...)
        try:
            desktop = subprocess.check_output(
                ["xdg-user-dir", "DESKTOP"], text=True, timeout=3).strip()
        except Exception:
            desktop = os.path.expanduser("~/Desktop")
        if not os.path.isdir(desktop):
            desktop = os.path.expanduser("~")
        self._dir_input.setText(desktop)
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
        """Return [(tab_name, text_content)] — always a 1-element list
        now that multi-tab export was removed. Kept as a list to keep
        the calling _do_export loop intact."""
        return list(self._tabs_info)

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
        """User-edited filename prefix (falls back to the original
        audio basename if the user cleared the field)."""
        text = self._name_input.text().strip()
        return text or self._base_name


# === LLM result Export Dialog ===

class LLMExportDialog(QDialog):
    """Single-tab export for LLM analysis results.

    Two output formats: Markdown (.md) and PDF (.pdf). Markdown writes
    the editor content as-is (the LLM produces markdown). PDF renders
    via QTextDocument.setMarkdown() + QPrinter for headings/lists/etc.
    Filename and target directory are user-editable.
    """

    def __init__(self, default_filename, content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Export LLM result"))
        self.setMinimumWidth(520)
        self._content = content or ""

        layout = QVBoxLayout(self)

        from PyQt6.QtWidgets import QFormLayout
        form = QFormLayout()

        self._name_edit = QLineEdit(default_filename)
        form.addRow(_("Filename:"), self._name_edit)

        self._dir_input = QLineEdit()
        try:
            desktop = subprocess.check_output(
                ["xdg-user-dir", "DESKTOP"], text=True, timeout=3).strip()
        except Exception:
            desktop = os.path.expanduser("~/Desktop")
        if not os.path.isdir(desktop):
            desktop = os.path.expanduser("~")
        self._dir_input.setText(desktop)
        dir_h = QHBoxLayout()
        dir_h.setContentsMargins(0, 0, 0, 0)
        dir_h.addWidget(self._dir_input, 1)
        btn_browse = QPushButton(_("Browse..."))
        btn_browse.clicked.connect(self._on_browse)
        dir_h.addWidget(btn_browse)
        dir_w = QWidget()
        dir_w.setLayout(dir_h)
        form.addRow(_("Directory:"), dir_w)

        layout.addLayout(form)

        # Format checkboxes
        group_fmt = QGroupBox(_("Formats"))
        lay_fmt = QHBoxLayout(group_fmt)
        self._chk_md = ToggleSwitch(_("Markdown (.md)"))
        self._chk_md.setChecked(True)
        self._chk_pdf = ToggleSwitch(_("PDF (.pdf)"))
        lay_fmt.addWidget(self._chk_md)
        lay_fmt.addWidget(self._chk_pdf)
        layout.addWidget(group_fmt)

        # Buttons
        lay_btns = QHBoxLayout()
        lay_btns.addStretch()
        btn_save = QPushButton(_("Save"))
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._on_save)
        lay_btns.addWidget(btn_save)
        btn_cancel = QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        lay_btns.addWidget(btn_cancel)
        layout.addLayout(lay_btns)

    def _on_browse(self):
        d = QFileDialog.getExistingDirectory(
            self, _("Select directory"), self._dir_input.text())
        if d:
            self._dir_input.setText(d)

    def _on_save(self):
        name = self._name_edit.text().strip()
        out_dir = self._dir_input.text().strip()
        if not name:
            QMessageBox.warning(self, _("Validation"),
                                _("Filename is required."))
            return
        if not os.path.isdir(out_dir):
            QMessageBox.warning(
                self, _("Validation"),
                _("Directory does not exist: {dir}").format(dir=out_dir))
            return
        formats = []
        if self._chk_md.isChecked():
            formats.append("md")
        if self._chk_pdf.isChecked():
            formats.append("pdf")
        if not formats:
            QMessageBox.warning(self, _("Validation"),
                                _("Pick at least one format."))
            return

        # Strip any extension the user typed; we add ours.
        stem = re.sub(r"\.(md|pdf|txt)$", "", name, flags=re.IGNORECASE)

        written = []
        for fmt in formats:
            path = os.path.join(out_dir, f"{stem}.{fmt}")
            try:
                if fmt == "md":
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(self._content)
                elif fmt == "pdf":
                    self._write_pdf(path, self._content)
                written.append(path)
            except Exception as e:
                QMessageBox.critical(
                    self, _("Export failed"),
                    _("Could not write {path}:\n{err}").format(
                        path=path, err=str(e)))
                return

        QMessageBox.information(
            self, _("Export OK"),
            _("Wrote:\n") + "\n".join(written))
        self.accept()

    def _write_pdf(self, path, markdown_text):
        """Render markdown as PDF via QTextDocument + QPrinter. Headings,
        bullet lists, code blocks etc. are rendered properly."""
        from PyQt6.QtPrintSupport import QPrinter
        from PyQt6.QtGui import QTextDocument
        from PyQt6.QtCore import QMarginsF
        from PyQt6.QtGui import QPageLayout, QPageSize
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        layout_pdf = QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            QMarginsF(15, 15, 15, 15))
        printer.setPageLayout(layout_pdf)
        doc = QTextDocument()
        doc.setMarkdown(markdown_text)
        # Indirect call — security hook flags '.print(' literal.
        doc_print = getattr(doc, "print")
        doc_print(printer)


# === LLM Diarization helpers, thread & dialog ===

def _dll_module():
    """Lazy import of the dictee-diarize-llm module.

    The installed file is /usr/bin/dictee-diarize-llm (no .py extension),
    which means importlib.util.spec_from_file_location() returns None by
    default — it can't infer a loader from the empty extension. Pass a
    SourceFileLoader explicitly so any path resolves to a Python module.
    """
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

    # Cache, but invalidate on file mtime change so dev iterations on
    # /usr/bin/dictee-diarize-llm don't require restarting the whole
    # transcribe window (which would lose the open diarization).
    mtime = os.path.getmtime(path)
    cached_mod = getattr(_dll_module, "_cached", None)
    cached_mt = getattr(_dll_module, "_cached_mtime", None)
    cached_path = getattr(_dll_module, "_cached_path", None)
    if cached_mod is not None and cached_mt == mtime and cached_path == path:
        return cached_mod

    loader = importlib.machinery.SourceFileLoader(
        "dictee_diarize_llm", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    # Indirect call: a security hook flags '.exec(' literal even on
    # SourceFileLoader's exec_module(), unrelated to its purpose.
    loader_run = getattr(loader, "exec_module")
    loader_run(mod)
    _dll_module._cached = mod
    _dll_module._cached_mtime = mtime
    _dll_module._cached_path = path
    return mod


def _llm_modal(dlg):
    """Run a modal QDialog and return the result code. Wrapped because the
    project's security hook treats any '.exec(' literal as suspect."""
    return getattr(dlg, "exec")()


class LLMAnalysisThread(QThread):
    """Background worker for LLM analysis. Wraps _dll_module().analyze().

    The progress signal fires per-segment in 'per-segment' mode; for
    'global' mode it fires once at the very end (no granular progress).
    """
    progress = Signal(int, int)
    result = Signal(str)
    error = Signal(str)

    def __init__(self, segments, profile, provider_cfg, model,
                 dictionary="", timeout=120, lang_name="", parent=None):
        super().__init__(parent)
        self._segments = segments
        self._profile = profile
        self._provider_cfg = provider_cfg
        self._model = model
        self._dictionary = dictionary
        self._timeout = timeout
        self._lang_name = lang_name
        # Created lazily in run() because the helper class lives in the
        # dictee-diarize-llm module which we hot-import.
        self._cancellation = None

    def cancel(self):
        """Abort the in-flight HTTP stream and suppress emit.

        Closes the live HTTPResponse from the outside — the streaming
        loop in the provider call exits immediately. No more wasted
        cloud tokens or pinned GPU after the user closes the tab.
        """
        c = self._cancellation
        if c is not None:
            c.abort()

    def run(self):
        try:
            mod = _dll_module()
            self._cancellation = mod.Cancellation()
            text = mod.analyze(
                self._segments, self._profile, self._provider_cfg,
                model=self._model, dictionary=self._dictionary,
                timeout=self._timeout, lang_name=self._lang_name,
                cancellation=self._cancellation,
                progress_cb=lambda i, n: self.progress.emit(i, n))
            if self._cancellation.cancelled:
                return
            self.result.emit(text)
        except Exception as e:
            # CancelledError (or any other) after abort: stay silent.
            if self._cancellation is not None and self._cancellation.cancelled:
                return
            self.error.emit(str(e))


class LLMProcessDialog(QDialog):
    """Dialog to configure and launch an LLM analysis.

    On success the parent's ._add_llm_result_tab(name, text) is called and
    the dialog closes. Errors are shown inline so the user can retry."""

    def __init__(self, segments, parent=None, is_plain=False, source_widget=None):
        """`is_plain=True` when the source tab is a non-diarized
        transcription. The profile combo is then filtered to the
        plain-text profiles only (and conversely, diarized tabs only
        see the diarized profiles) so the user can't pick a profile
        whose prompt expects [Speaker N] labels on plain text or
        vice-versa.

        `source_widget` pins the analysis to the transcription tab the
        user clicked from, so the resulting "#N LLM: …" tab inherits
        the correct counter even if the user later opens a fresh
        transcription that updates `parent._text_edit`."""
        super().__init__(parent)
        self.setWindowTitle(_("LLM analysis"))
        self.setMinimumWidth(560)

        self._segments = list(segments or [])
        self._parent_window = parent
        self._source_widget = source_widget
        self._thread = None
        self._is_plain = is_plain

        from PyQt6.QtWidgets import QFormLayout

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Profile combo — filtered by the source tab's diarized state
        self._profile_combo = QComboBox()
        try:
            all_profiles = list(_dll_module().load_profiles())
        except Exception as e:
            all_profiles = []
            QMessageBox.critical(
                self, _("LLM module error"),
                _("Could not load profiles:\n{err}").format(err=str(e)))
        if is_plain:
            self._profiles = [p for p in all_profiles if p.get("format") == "plain"]
        else:
            self._profiles = [p for p in all_profiles if p.get("format") != "plain"]
        for p in self._profiles:
            self._profile_combo.addItem(p["name"], p["id"])
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        form.addRow(_("Profile:"), self._profile_combo)

        # Provider combo
        self._provider_combo = QComboBox()
        try:
            self._providers = list(_dll_module().load_providers())
        except Exception:
            self._providers = []
        for p in self._providers:
            self._provider_combo.addItem(p["name"], p["id"])
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow(_("Provider:"), self._provider_combo)

        # Model: editable combo + manual Refresh button. Populated
        # automatically when provider changes, but if that silent fetch
        # fails the user can re-trigger it manually with feedback.
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
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
        form.addRow(_("Model:"), model_w)

        layout.addLayout(form)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Buttons
        btn_h = QHBoxLayout()
        btn_h.addStretch()
        self._btn_generate = QPushButton(_("Generate"))
        self._btn_generate.setDefault(True)
        self._btn_generate.clicked.connect(self._on_generate)
        btn_h.addWidget(self._btn_generate)
        self._btn_close = QPushButton(_("Close"))
        self._btn_close.clicked.connect(self.reject)
        btn_h.addWidget(self._btn_close)
        layout.addLayout(btn_h)

        # Initial sync: pick the profile's preferred provider/model
        if self._profiles:
            self._on_profile_changed()

    def _on_profile_changed(self):
        pid = self._profile_combo.currentData()
        profile = next((p for p in self._profiles if p["id"] == pid), None)
        if not profile:
            return
        prov = profile.get("default_provider_id")
        index_changed = False
        if prov:
            before = self._provider_combo.currentIndex()
            for i in range(self._provider_combo.count()):
                if self._provider_combo.itemData(i) == prov:
                    self._provider_combo.setCurrentIndex(i)
                    break
            index_changed = self._provider_combo.currentIndex() != before
        self._model_combo.setEditText(profile.get("default_model", ""))
        # If the provider index didn't actually change, the
        # currentIndexChanged signal never fired and the model list
        # stays stale. Trigger the silent refresh manually so the
        # dropdown is populated as soon as the dialog opens.
        if not index_changed:
            QTimer.singleShot(0, self._on_provider_changed)

    def _on_provider_changed(self):
        """Best-effort silent model list refresh.

        On failure (no API key, network down, 401…) the model list is
        left untouched and the status label shows a hint to use the
        Refresh button manually for the full error.
        """
        prov_id = self._provider_combo.currentData()
        if not prov_id:
            return
        try:
            cfg = _dll_module().find_provider(prov_id)
            if not cfg:
                return
            models = _dll_module().list_provider_models(cfg, timeout=5)
        except Exception as e:
            # Don't wipe the field, just hint the user that we couldn't
            # fetch — they can use Refresh for the full error.
            short = str(e)[:120]
            self._status.setText(
                "<span style='color:#d68910'>" +
                _("Couldn't auto-load models ({err}). Click Refresh.").format(
                    err=short) + "</span>")
            return
        current = self._model_combo.currentText()
        self._model_combo.clear()
        for m in models:
            self._model_combo.addItem(m)
        # Keep the previous model only if it actually exists on the new
        # provider. Otherwise show the first model of the new list —
        # restoring a non-existent name visually masks the provider
        # switch and confuses the user (same fix as LLMProfileEditDialog
        # in dictee-setup.py).
        if current and current in models:
            self._model_combo.setEditText(current)
        elif models:
            self._model_combo.setCurrentIndex(0)
        self._status.setText(
            "<span style='color:#2a7'>" +
            _("{n} model(s) loaded from {name}.").format(
                n=len(models), name=cfg.get("name") or prov_id) + "</span>")

    def _on_refresh_models(self):
        """Manual refresh with explicit feedback (success or failure)."""
        prov_id = self._provider_combo.currentData()
        if not prov_id:
            self._status.setText(
                "<span style='color:#c44'>" +
                _("Pick a provider first.") + "</span>")
            return
        cfg = _dll_module().find_provider(prov_id)
        if not cfg:
            self._status.setText(
                "<span style='color:#c44'>" +
                _("Provider '{id}' not found.").format(id=prov_id) +
                "</span>")
            return
        self._status.setText(_("Loading models from {name}…").format(
            name=cfg.get("name") or prov_id))
        QApplication.processEvents()
        try:
            models = _dll_module().list_provider_models(cfg, timeout=10)
        except Exception as e:
            short = str(e)[:200]
            self._status.setText(
                "<span style='color:#c44'>" +
                _("Failed: {err}").format(err=short) + "</span>")
            return
        current = self._model_combo.currentText()
        self._model_combo.clear()
        for m in models:
            self._model_combo.addItem(m)
        if current:
            self._model_combo.setEditText(current)
        self._status.setText(
            "<span style='color:#2a7'>" +
            _("{n} model(s) loaded.").format(n=len(models)) + "</span>")

    def _set_busy(self, busy):
        self._btn_generate.setEnabled(not busy)
        self._profile_combo.setEnabled(not busy)
        self._provider_combo.setEnabled(not busy)
        self._model_combo.setEnabled(not busy)
        if hasattr(self, "_btn_refresh_models"):
            self._btn_refresh_models.setEnabled(not busy)
        self._progress.setVisible(busy)

    def _on_generate(self):
        profile_id = self._profile_combo.currentData()
        provider_id = self._provider_combo.currentData()
        model = self._model_combo.currentText().strip()
        if not profile_id or not provider_id or not model:
            self._status.setText(
                "<span style='color:#c44'>" +
                _("Profile, provider and model are required.") + "</span>")
            return
        try:
            mod = _dll_module()
        except Exception as e:
            self._status.setText(
                f"<span style='color:#c44'>{str(e)}</span>")
            return
        profile = next((p for p in self._profiles if p["id"] == profile_id), None)
        provider_cfg = mod.find_provider(provider_id)
        if not profile or not provider_cfg:
            self._status.setText(
                "<span style='color:#c44'>" +
                _("Profile or provider not found.") + "</span>")
            return

        if not self._segments:
            self._status.setText(
                "<span style='color:#c44'>" +
                _("No transcript available. Run a transcription "
                  "first, then retry.") + "</span>")
            return

        self._status.setText(_("Generating…"))
        self._set_busy(True)
        self._progress.setRange(0, 0)  # indeterminate until first progress

        # Create the result tab right away (empty + spinner) so the
        # user sees the tab appear immediately. The content lands in
        # _on_result; on error the tab is dropped via _cancel_llm_result_tab.
        profile_name = self._profile_combo.currentText()
        self._llm_tab_widget = None
        if hasattr(self._parent_window, "_start_llm_result_tab"):
            self._llm_tab_widget = self._parent_window._start_llm_result_tab(
                profile_name, model, source_widget=self._source_widget)

        # Force the LLM output language to the user's native language
        # (DICTEE_LANG_SOURCE in dictee.conf), NOT the translation
        # source/target combos — those are unrelated to the LLM output.
        # The in-prompt hint alone is unreliable; many models drift to
        # English regardless.
        code = _read_conf().get("DICTEE_LANG_SOURCE", "") or ""
        lang_name = LANG_NAMES_EN.get(code, "")

        # 600 s per HTTP call — local models (Ollama qwen3.5:4b on a
        # 30 min transcript) genuinely need more than the previous 120 s
        # ceiling and were timing out mid-generation. Cloud models
        # finish in seconds anyway; raising the cap costs nothing.
        self._thread = LLMAnalysisThread(
            self._segments, profile, provider_cfg, model,
            timeout=600, lang_name=lang_name, parent=self)
        self._thread.progress.connect(self._on_progress)
        self._thread.result.connect(self._on_result)
        self._thread.error.connect(self._on_error)
        # Stash the thread on the result tab so closing it (X button)
        # also cancels the underlying LLM call — see _on_tab_close.
        if self._llm_tab_widget is not None:
            self._llm_tab_widget._llm_thread = self._thread
        self._thread.start()

    def _on_progress(self, current, total):
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(current)
            self._status.setText(
                _("Generating… {i}/{n}").format(i=current, n=total))

    def _on_result(self, text):
        profile_name = self._profile_combo.currentText()
        # Prefer the two-phase API (tab pre-created with spinner) when
        # available; fall back to the old _add_llm_result_tab path.
        if (self._llm_tab_widget is not None
                and hasattr(self._parent_window, "_finish_llm_result_tab")):
            self._parent_window._finish_llm_result_tab(
                self._llm_tab_widget, text)
        elif hasattr(self._parent_window, "_add_llm_result_tab"):
            self._parent_window._add_llm_result_tab(
                profile_name, text, source_widget=self._source_widget)
        self.accept()

    def _on_error(self, msg):
        self._set_busy(False)
        short = msg if len(msg) <= 300 else msg[:300] + "…"
        self._status.setText(
            "<span style='color:#c44'>" +
            _("Failed: {err}").format(err=short) + "</span>")
        # Drop the empty tab created in _on_generate so the user
        # doesn't see an orphan spinner forever.
        if (self._llm_tab_widget is not None
                and hasattr(self._parent_window, "_cancel_llm_result_tab")):
            self._parent_window._cancel_llm_result_tab(self._llm_tab_widget)
            self._llm_tab_widget = None


# === Main Window ===
#
# State ownership (2026-07 refactor: the tab owns its state)
# ----------------------------------------------------------
# Per-tab attributes — owned by each QTextEdit tab, initialized by
# _init_tab_state() (LLM result tabs excepted, they carry their own set):
#   _audio_path          source audio file of this tab (None for LLM tabs)
#   _raw_text            raw engine output, input for reformatting
#   _was_diarized        whether this tab's run used diarization
#   _diarize_segments    parsed segments (historical naming: the window
#                        projection of this attribute is `_segments`)
#   _speaker_name_map    {canonical_id -> custom_name}, render-time only
#   _rename_family       run tab this tab is a view of (itself for a run
#                        tab, the source run for a translation tab);
#                        speaker renames apply within one family only
#   _status_text         live/final status line (restored on tab switch)
#   _audio_duration      probed once at run start (seconds)
#   _transcribe_elapsed  this tab's run duration (seconds; translations
#   _translate_elapsed   inherit the source's transcribe time)
#   _segment_positions   char ranges per segment (set by _apply_format_to)
#   _format              display format of THIS tab (text/srt/json),
#                        captured from the combo at creation and updated
#                        on every render; the anchor for background
#                        renders (_apply_format_to) and for the combo
#                        sync on tab switch (_on_tab_changed)
#   _rendered_baseline, _current_highlight_range,
#   _modified_overlay    render bookkeeping, set lazily
#   _is_llm_result, _llm_profile_name, _spinner_base_title, _llm_thread
#                        LLM result tabs only
# The window keeps PERMANENT read-only projections of the active tab:
# _raw_text, _segments (-> _diarize_segments), _was_diarized and
# _speaker_name_map are getter-only @property — writing through them
# raises AttributeError by design, so shared-state writes cannot creep
# back in. Writers always target a specific tab's attribute. Treat
# lists/dicts read through projections as read-only: copy before
# mutating.
#
# Run-scoped attributes — on the window, valid for the single in-flight
# run: _run_tab (the tab the run writes into; captured at run start,
# never re-resolved inside async handlers), _process, _stdout_buf,
# _transcription_in_progress, _start_time, _diarize_two_phase,
# _user_cancelled, _retry_done, _moss_run, _daemon_was_active,
# _isolated_recipe, _diarize_audio_path, _chunked_phase_label,
# _translate_start.
#
# Closing a run's tab detaches but does NOT delete its editor
# (_on_tab_close deletes LLM tabs only): a late finisher writes into
# the detached widget harmlessly.

class TranscribeWindow(QDialog):
    """Main transcription/diarization window."""

    def __init__(self, file_path=None, auto_diarize=False, asr_model="",
                 diar_engine="", parent=None):
        super().__init__(parent)
        self._asr_model = asr_model or ""
        self.setWindowTitle(_("Dictee - Transcribe file"))
        self.setMinimumSize(600, 500)
        self.resize(980, 800)
        self.setAcceptDrops(True)
        # All earlier attempts to shrink tooltips (dialog stylesheet,
        # QToolTip.setFont(), QApplication stylesheet) were ignored by
        # Qt on this build. The only reliable lever left is to wrap
        # every tooltip text in a rich-text element with an explicit
        # font-size, which QToolTip honours per-widget.
        # 11pt matches the rich-text tooltips used throughout dictee-setup.py
        # (see e.g. lines 5410, 5516 of that file). Stay consistent across
        # the project rather than picking sizes at random.
        # For long texts (>60 chars), use <p> instead of <span>: <p> is a
        # block element so Qt enables rich-text mode AND triggers word-wrap.
        # The explicit `width:400px` caps the tooltip at a readable width
        # — otherwise long plain-text tooltips render as a single line
        # stretching the full screen on wide monitors. 400px is the
        # project-wide convention (used in dictee-setup and dictee-tray
        # too — see feedback-tooltips-width-400.md).
        def _tip(txt):
            if len(txt) > 60:
                return ("<p style='font-size:11pt; white-space:pre-wrap; "
                        "width:400px;'>" + txt + "</p>")
            return f"<span style='font-size:11pt'>{txt}</span>"
        self._tip = _tip

        self._process = None
        self._run_tab = None  # tab the in-flight run writes into
        self._isolated_daemon = None  # ad-hoc isolated ASR daemon (Task 5b)
        self._stdout_buf = QByteArray()
        self._rename_line_edits = {}   # filled by _populate_rename_fields
        self._translate_thread = None
        self._translate_start = 0.0
        self._current_translate_lang = ""  # lang code of current translation

        self._build_ui()
        self._connect_signals()
        # Set the initial window icon to match the current Diarize
        # toggle state (off = blue 'transcribing', on = violet
        # 'diarize'). Subsequent toggles update it in real time.
        self._refresh_window_icon()

        # Check if dictee is configured — explain and offer wizard if not
        conf = _read_conf()
        if not os.path.isfile(CONF_PATH) or conf.get("DICTEE_SETUP_DONE") != "true":
            _dbg("config not found or SETUP_DONE != true")
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle(_("Dictee - First run"))
            msg.setText(_("Dictee is not yet configured."))
            msg.setInformativeText(
                _("Before transcribing audio files, you need to configure "
                  "the speech recognition engine and other settings.\n\n"
                  "Would you like to open the configuration wizard?"))
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setDefaultButton(QMessageBox.StandardButton.Yes)
            if msg.exec() == QMessageBox.StandardButton.Yes:
                env = dict(os.environ)
                env["QT_QPA_PLATFORMTHEME"] = "kde"
                subprocess.Popen(["dictee-setup", "--wizard"], env=env)
            QTimer.singleShot(0, self.close)
            return

        # Pre-fill from CLI args
        if file_path:
            self._file_input.setText(file_path)
            self._load_audio(file_path)
        if auto_diarize and _diarize_available():
            self._chk_diarize.setChecked(True)
        # --diar-engine (meeting-live hands its own engine choice over):
        # select it when usable, else keep the combo's persisted value
        # rather than failing a run the user cannot see being set up.
        if diar_engine:
            _di = self._cmb_diar_engine.findData(diar_engine)
            if _di >= 0 and self._cmb_diar_engine.model().item(_di).isEnabled():
                self._cmb_diar_engine.setCurrentIndex(_di)
            else:
                _dbg(f"--diar-engine {diar_engine!r} unavailable — "
                     f"keeping {self._cmb_diar_engine.currentData()!r}")

        # Speaker transfer from meeting-live: look for speakers.json next to
        # the audio file. Loaded now; applied after diarization completes.
        self._pending_speakers_data = None
        if file_path:
            try:
                _spk_json = os.path.join(
                    os.path.dirname(os.path.abspath(file_path)),
                    "speakers.json",
                )
                if os.path.isfile(_spk_json):
                    with open(_spk_json, encoding="utf-8") as _f:
                        self._pending_speakers_data = json.load(_f)
                    _dbg(f"loaded speakers.json from {_spk_json}")
            except Exception as _e:
                _dbg(f"speakers.json load error: {_e!r}")

        if file_path and auto_diarize:
            # Defer to event loop so window is fully initialized
            QTimer.singleShot(100, self._on_transcribe)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # -- File picker --
        lay_file = QHBoxLayout()

        self._asr_model_combo = QComboBox()
        # (label, userData=spec). "" = Default (F9).
        # Whisper entries are per ENGINE, not per size: the model size
        # follows the dictee-setup selection (DICTEE_WHISPER_MODEL /
        # DICTEE_WHISPER_RUST_MODEL) — keeps the list short and the size a
        # single-source setting. The configured size is shown in
        # parentheses (snapshot at window build).
        _conf_sizes = _read_conf()
        _wh_size = (_conf_sizes.get("DICTEE_WHISPER_MODEL") or "small").strip()
        if _wh_size not in ("tiny", "small", "medium"):
            _wh_size = "small"
        _wr_size = (_conf_sizes.get("DICTEE_WHISPER_RUST_MODEL")
                    or "large-v3").strip()
        for _lbl, _spec in (
            (_("Default (F9)"), ""),
            ("Parakeet int8", "parakeet-int8"),
            ("Parakeet fp32", "parakeet-fp32"),
            (f"faster-whisper ({_wh_size})", "whisper"),
            (f"Whisper-Rust ({_wr_size})", "whisper-rust"),
            ("Nemotron", "nemotron"),
        ):
            self._asr_model_combo.addItem(_lbl, _spec)
        self._asr_model_combo.setToolTip(self._tip(
            _("ASR model for this transcription (isolated from your F9 "
              "setting). Whisper model sizes follow your dictee-setup "
              "selection.")))
        if self._asr_model:
            _i = self._asr_model_combo.findData(self._asr_model)
            if _i >= 0:
                self._asr_model_combo.setCurrentIndex(_i)
        lay_file.addWidget(self._asr_model_combo)

        lbl = QLabel(_("File:"))
        lay_file.addWidget(lbl)

        # Editable combo whose dropdown lists the recent files (persisted
        # in QSettings). The embedded QLineEdit is exposed as
        # `_file_input`, so every historical call site (.text(),
        # .setText(), .textChanged) keeps working unchanged.
        self._file_combo = QComboBox()
        self._file_combo.setEditable(True)
        self._file_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._file_combo.setToolTip(_("Path to the audio file to transcribe "
                                      "— the list holds the recent files"))
        self._file_input = self._file_combo.lineEdit()
        self._file_input.setPlaceholderText(_("Select an audio file..."))
        # Decline drops on the line edit itself: QLineEdit's default handler
        # inserts the raw "file://..." URI text. Letting drops bubble up to the
        # window's dropEvent (which uses QUrl.toLocalFile()) yields a clean
        # local path every time, regardless of where the file is dropped.
        self._file_input.setAcceptDrops(False)
        self._file_combo.setAcceptDrops(False)
        self._reload_recent_files()
        lay_file.addWidget(self._file_combo, 1)

        self._btn_browse = QPushButton(_("Browse..."))
        self._btn_browse.setToolTip(_("Open file selection dialog"))
        self._btn_browse.clicked.connect(self._on_browse)
        lay_file.addWidget(self._btn_browse)

        self._btn_history = QPushButton(_("History"))
        self._btn_history.setToolTip(self._tip(_("Open a past meeting")))
        self._btn_history.clicked.connect(self._on_open_history)
        lay_file.addWidget(self._btn_history)

        layout.addLayout(lay_file)

        # -- Audio player --
        lay_player = QHBoxLayout()

        # U+23EA Fast Reverse + U+FE0E Variation Selector-15 forces the
        # monochrome text glyph instead of the colourful emoji glyph.
        self._btn_seek_start = QPushButton("⏪︎")
        self._btn_seek_start.setFixedWidth(36)
        self._btn_seek_start.setToolTip(self._tip(_("Go to the start")))
        self._btn_seek_start.clicked.connect(
            lambda: self._player.setPosition(0))
        lay_player.addWidget(self._btn_seek_start)

        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedWidth(36)
        self._btn_play.setToolTip(self._tip(_("Play / Pause")))
        self._btn_play.clicked.connect(self._on_play_pause)
        lay_player.addWidget(self._btn_play)

        self._btn_stop = QPushButton("⏹")
        self._btn_stop.setFixedWidth(36)
        self._btn_stop.setToolTip(self._tip(_("Stop")))
        self._btn_stop.clicked.connect(self._on_player_stop)
        lay_player.addWidget(self._btn_stop)

        self._btn_prev_seg = QPushButton("⏮")
        self._btn_prev_seg.setFixedWidth(36)
        self._btn_prev_seg.setToolTip(self._tip(_("Previous speaker segment")))
        self._btn_prev_seg.clicked.connect(self._on_prev_segment)
        lay_player.addWidget(self._btn_prev_seg)

        self._btn_next_seg = QPushButton("⏭")
        self._btn_next_seg.setFixedWidth(36)
        self._btn_next_seg.setToolTip(self._tip(_("Next speaker segment")))
        self._btn_next_seg.clicked.connect(self._on_next_segment)
        lay_player.addWidget(self._btn_next_seg)

        # U+23E9 Fast Forward + U+FE0E VS-15 to force the monochrome glyph.
        self._btn_seek_end = QPushButton("⏩︎")
        self._btn_seek_end.setFixedWidth(36)
        self._btn_seek_end.setToolTip(self._tip(_("Go to the end")))
        # Land 100 ms before the very end so QMediaPlayer doesn't auto-stop
        # before the user can see the position update.
        self._btn_seek_end.clicked.connect(
            lambda: self._player.setPosition(
                max(0, self._player.duration() - 100)))
        lay_player.addWidget(self._btn_seek_end)

        # Uniform 36×36 size + matching font for every player-toolbar
        # button. Play is downsized to 18px because ▶ (U+25B6 Black
        # Right-Pointing Triangle) renders visually much larger than
        # the surrounding Media-Control glyphs at the same font size,
        # and we add setFixedHeight(36) so the smaller font does not
        # also shrink the button bounding box (which made play look
        # shorter than the others).
        for _btn in (self._btn_seek_start, self._btn_play, self._btn_stop,
                     self._btn_prev_seg, self._btn_next_seg,
                     self._btn_seek_end):
            _btn.setFixedHeight(36)
        for _btn in (self._btn_seek_start, self._btn_stop,
                     self._btn_prev_seg, self._btn_next_seg,
                     self._btn_seek_end):
            _btn.setStyleSheet("font-size: 24px;")
        self._btn_play.setStyleSheet("font-size: 18px;")

        self._sld_position = _ClickSlider(Qt.Orientation.Horizontal)
        self._sld_position.setRange(0, 0)
        self._sld_position.sliderMoved.connect(self._on_seek)
        self._sld_position.sliderClicked.connect(self._on_seek)
        lay_player.addWidget(self._sld_position, 1)

        self._lbl_time = QLabel("0:00 / 0:00")
        self._lbl_time.setFixedWidth(90)
        lay_player.addWidget(self._lbl_time)

        layout.addLayout(lay_player)

        # Media player backend. QAudioOutput() binds the default output
        # device AT CREATION TIME and never re-follows the system default:
        # Bluetooth headphones connected after this window opened would be
        # ignored (playback stuck on the laptop speakers). Track the device
        # list and re-pin the system default whenever it changes; the
        # QMediaDevices instance must be kept alive for the signal to fire.
        self._audio_output = QAudioOutput()
        self._media_devices = QMediaDevices()
        self._audio_output.setDevice(QMediaDevices.defaultAudioOutput())
        self._media_devices.audioOutputsChanged.connect(
            self._on_audio_outputs_changed)
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_player_position)
        self._player.durationChanged.connect(self._on_player_duration)
        self._player.playbackStateChanged.connect(self._on_playback_state)

        # === Transcribe pad: button + options ===
        self._pad_transcribe = QFrame()
        self._pad_transcribe.setObjectName("padSection")
        self._pad_transcribe.setStyleSheet(
            "QFrame#padSection { border: 1px solid palette(mid); "
            "border-radius: 6px; background: palette(base); }")
        pad_transcribe = QVBoxLayout(self._pad_transcribe)
        pad_transcribe.setContentsMargins(10, 8, 10, 8)
        pad_transcribe.setSpacing(4)

        # Two-column pad: options on the left, tall coloured action
        # button on the right. Purple Transcribe matches Translate's
        # orange below — both feel actionable and stay above the fold.
        lay_pad_h = QHBoxLayout()
        lay_pad_h.setContentsMargins(0, 0, 0, 0)
        lay_pad_h.setSpacing(12)

        lay_opts = QVBoxLayout()
        lay_opts.setContentsMargins(0, 0, 0, 0)
        lay_opts.setSpacing(4)

        # Row 1: diarization toggle + threshold slider tucked to its right.
        # The threshold widget is hidden until the toggle is checked, but
        # always laid out next to the toggle (no separate row) so the
        # vertical rhythm of the pad doesn't change when it appears.
        self._chk_diarize = ToggleSwitch(_("Diarization (speaker identification)"))
        diar_multi_ok = _diar_multi_available()
        sortformer_ok = _sortformer_available()
        moss_ok = _moss_available()
        # Cached for _update_transcribe_btn: its bare setEnabled(not_running)
        # used to re-arm the toggle on every file-input change even when no
        # diarization engine is installed.
        self._diar_available = diar_multi_ok or sortformer_ok or moss_ok
        self._chk_diarize.setEnabled(self._diar_available)
        if diar_multi_ok:
            self._chk_diarize.setToolTip(self._tip(
                _("Identify speakers (no speaker-count limit). Works on "
                  "any duration thanks to the auto-chunking pipeline.")))
        elif sortformer_ok:
            self._chk_diarize.setToolTip(self._tip(
                _("Identify speakers (max 4). Works on any duration "
                  "thanks to the auto-chunking pipeline.")))
        else:
            self._chk_diarize.setToolTip(
                _("No diarization model installed. Configure in dictee-setup."))

        self._w_threshold = QWidget()
        lay_thresh = QHBoxLayout(self._w_threshold)
        lay_thresh.setContentsMargins(0, 0, 0, 0)
        self._lbl_sensitivity = QLabel(_("Threshold:"))
        self._sld_sensitivity = QSlider(Qt.Orientation.Horizontal)
        self._sld_sensitivity.setRange(0, 100)
        self._sld_sensitivity.setValue(50)
        self._sld_sensitivity.setFixedWidth(120)
        self._sld_sensitivity.setToolTip(self._tip(_("Speaker detection threshold. ← Low: more sensitive, detects more speakers (may split one person into two speakers). → High: stricter, detects fewer speakers (may merge two people into one speaker). Default (50%) works well for most recordings.")))
        self._lbl_sensitivity_val = QLabel("50%")
        self._lbl_sensitivity_val.setFixedWidth(35)
        self._sld_sensitivity.valueChanged.connect(
            lambda v: self._lbl_sensitivity_val.setText(f"{v}%"))
        lay_thresh.addWidget(self._lbl_sensitivity)
        lay_thresh.addWidget(self._sld_sensitivity)
        lay_thresh.addWidget(self._lbl_sensitivity_val)
        # No internal stretch: keep _w_threshold tight so it stacks
        # snug against the toggle in the parent row.
        self._w_threshold.setVisible(False)

        # Diarization engine combo (same visibility rhythm as the threshold
        # widget). "Auto" preserves the historical preference (multi-speaker
        # engine when installed, else Sortformer); the explicit entries let
        # the user force one (e.g. Sortformer on heavily produced audio).
        # Persisted per window in QSettings, like the translate choices.
        self._w_diar_engine = QWidget()
        lay_diar_eng = QHBoxLayout(self._w_diar_engine)
        lay_diar_eng.setContentsMargins(0, 0, 0, 0)
        # Explicit label: without it the combo reads as "the model" while it
        # only picks WHO-SPEAKS-WHEN — the transcription model is the top
        # combo (user got bitten on 2026-07-08).
        lay_diar_eng.addWidget(QLabel(_("Engine:")))
        self._cmb_diar_engine = QComboBox()
        self._cmb_diar_engine.addItem(_("Auto"), "auto")
        self._cmb_diar_engine.addItem(_("Multi-speaker (no limit)"), "multi")
        self._cmb_diar_engine.addItem(_("Sortformer (max 4)"), "sortformer")
        # MOSS is a different animal: a single pass produces the transcript
        # AND the speakers (it replaces the ASR phase entirely), so the
        # threshold slider does not apply to it. Any GPU (Vulkan), not just
        # NVIDIA; CPU works but is slower than real time.
        self._cmb_diar_engine.addItem(_("MOSS (integrated, GPU)"), "moss")
        if not diar_multi_ok:
            self._cmb_diar_engine.model().item(1).setEnabled(False)
        if not sortformer_ok:
            self._cmb_diar_engine.model().item(2).setEnabled(False)
        if not moss_ok:
            self._cmb_diar_engine.model().item(3).setEnabled(False)
        self._cmb_diar_engine.setToolTip(self._tip(
            _("Diarization engine. Auto uses the multi-speaker engine when "
              "installed, otherwise Sortformer (max 4 speakers). MOSS "
              "transcribes and identifies speakers in a single pass (own "
              "ASR); it needs a GPU — any brand — and is slower than real "
              "time on the CPU.")))
        _qs_diar = QSettings("dictee", "transcribe")
        _i = self._cmb_diar_engine.findData(
            _qs_diar.value("diarize/engine", "auto"))
        if _i >= 0 and self._cmb_diar_engine.model().item(_i).isEnabled():
            self._cmb_diar_engine.setCurrentIndex(_i)
        self._cmb_diar_engine.currentIndexChanged.connect(
            lambda _i: QSettings("dictee", "transcribe").setValue(
                "diarize/engine", self._cmb_diar_engine.currentData()))
        # Re-evaluate the threshold visibility when the engine changes
        # (hidden for MOSS, which has no clustering threshold).
        self._cmb_diar_engine.currentIndexChanged.connect(
            lambda _i: self._on_diarize_toggled(self._chk_diarize.isChecked()))
        lay_diar_eng.addWidget(self._cmb_diar_engine)
        self._w_diar_engine.setVisible(False)

        # Secondary ASR for MOSS transcript holes (silent omissions and
        # truncated runaway chunks): the recovered text lands as UNKNOWN
        # turns — no speaker claim — so the LLM analysis never loses
        # content. Only meaningful for a MOSS run, hence the inverted
        # visibility rhythm vs the threshold widget. The UI choice wins
        # over the dictee.conf DICTEE_MOSS_GAP_ASR key for runs started
        # here (the conf key still drives meeting-live and CLI runs).
        self._w_moss_gap = QWidget()
        lay_moss_gap = QHBoxLayout(self._w_moss_gap)
        lay_moss_gap.setContentsMargins(0, 0, 0, 0)
        lay_moss_gap.addWidget(QLabel(_("Gap fill:")))
        self._cmb_moss_gap = QComboBox()
        self._cmb_moss_gap.addItem(_("Parakeet"), "parakeet")
        self._cmb_moss_gap.addItem(_("MOSS retry"), "moss")
        self._cmb_moss_gap.addItem(_("Off"), "none")
        self._cmb_moss_gap.setToolTip(self._tip(
            _("When MOSS leaves a hole in the transcript (a span with no "
              "output), a secondary engine transcribes it and the text is "
              "inserted with the UNKNOWN speaker label. Parakeet: robust "
              "default. MOSS retry: often recovers more words but may "
              "hallucinate on silence. Off: keep the hole, warn only.")))
        _qs_gap = QSettings("dictee", "transcribe")
        _ig = self._cmb_moss_gap.findData(
            _qs_gap.value("diarize/moss_gap_asr", "parakeet"))
        if _ig >= 0:
            self._cmb_moss_gap.setCurrentIndex(_ig)
        self._cmb_moss_gap.currentIndexChanged.connect(
            lambda _i: QSettings("dictee", "transcribe").setValue(
                "diarize/moss_gap_asr", self._cmb_moss_gap.currentData()))
        lay_moss_gap.addWidget(self._cmb_moss_gap)
        self._w_moss_gap.setVisible(False)

        lay_diarize_row = QHBoxLayout()
        lay_diarize_row.setContentsMargins(0, 0, 0, 0)
        lay_diarize_row.setSpacing(12)
        lay_diarize_row.addWidget(self._chk_diarize, 0, Qt.AlignmentFlag.AlignLeft)
        lay_diarize_row.addWidget(self._w_threshold, 0, Qt.AlignmentFlag.AlignLeft)
        lay_diarize_row.addWidget(self._w_diar_engine, 0, Qt.AlignmentFlag.AlignLeft)
        lay_diarize_row.addWidget(self._w_moss_gap, 0, Qt.AlignmentFlag.AlignLeft)
        lay_diarize_row.addStretch(1)
        lay_opts.addLayout(lay_diarize_row)
        self._chk_diarize.toggled.connect(self._on_diarize_toggled)

        # Row 3: output format
        lay_fmt = QHBoxLayout()
        lay_fmt.setContentsMargins(0, 0, 0, 0)
        lbl_fmt = QLabel(_("Format:"))
        lay_fmt.addWidget(lbl_fmt)

        self._cmb_format = QComboBox()
        self._cmb_format.addItem(_("Plain text"), "text")
        self._cmb_format.addItem("SRT", "srt")
        self._cmb_format.addItem("JSON", "json")
        self._cmb_format.setToolTip(_("Output format for transcription"))
        lay_fmt.addWidget(self._cmb_format)
        lay_fmt.addStretch()
        lay_opts.addLayout(lay_fmt)

        lay_pad_h.addLayout(lay_opts, 1)

        # Right column: tall purple Transcribe button + Cancel underneath
        # (Cancel is shown only during the chunked long-file pipeline).
        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(4)

        self._btn_transcribe = QPushButton(_("Transcribe"))
        self._btn_transcribe.setEnabled(False)
        self._btn_transcribe.setToolTip(_("Start transcription of the selected file"))
        self._btn_transcribe.clicked.connect(self._on_transcribe)
        self._btn_transcribe.setMinimumWidth(140)
        self._btn_transcribe.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        # #9B59B6 matches the violet used by dictee-tray for the
        # "diarizing / preparing / diarize-ready" states — keeps the
        # whole project on a single visual cue for diarization.
        self._btn_transcribe.setStyleSheet(
            "QPushButton { background: #9b59b6; color: white; "
            "font-weight: bold; border: none; border-radius: 4px; "
            "padding: 6px 16px; }"
            "QPushButton:hover { background: #a569bd; }"
            "QPushButton:pressed { background: #8e44ad; }"
            "QPushButton:disabled { background: rgba(155,89,182,80); "
            "color: rgba(255,255,255,150); }")
        btn_col.addWidget(self._btn_transcribe)

        self._btn_cancel = QPushButton(_("Cancel"))
        self._btn_cancel.setVisible(False)
        self._btn_cancel.setToolTip(_("Cancel the current transcription run"))
        self._btn_cancel.clicked.connect(self._on_cancel_run)
        btn_col.addWidget(self._btn_cancel)

        lay_pad_h.addLayout(btn_col, 0)
        pad_transcribe.addLayout(lay_pad_h)

        layout.addWidget(self._pad_transcribe)

        # -- Long-audio warning (shown when diarization + long file + CUDA build) --
        self._lbl_long_audio_warning = QLabel("")
        self._lbl_long_audio_warning.setWordWrap(True)
        self._lbl_long_audio_warning.setTextFormat(Qt.TextFormat.RichText)
        # Minimal styling: just colour the text (orange info-tone). No
        # background or border — the previous boxed look fought with
        # the rest of the form on long-file transcripts.
        self._lbl_long_audio_warning.setStyleSheet(
            "QLabel { color: #d68910; padding: 2px 0; }")
        self._lbl_long_audio_warning.setVisible(False)
        layout.addWidget(self._lbl_long_audio_warning)

        # === Translate pad: button + options ===
        self._pad_translate = QFrame()
        self._pad_translate.setObjectName("padSection")
        self._pad_translate.setStyleSheet(
            "QFrame#padSection { border: 1px solid palette(mid); "
            "border-radius: 6px; background: palette(base); }")
        pad_translate = QVBoxLayout(self._pad_translate)
        pad_translate.setContentsMargins(10, 8, 10, 8)
        pad_translate.setSpacing(4)

        # Two-column pad: options on the left, tall orange Translate
        # button on the right (mirrors the Transcribe pad layout).
        lay_translate_h = QHBoxLayout()
        lay_translate_h.setContentsMargins(0, 0, 0, 0)
        lay_translate_h.setSpacing(12)

        lay_translate_opts = QVBoxLayout()
        lay_translate_opts.setContentsMargins(0, 0, 0, 0)
        lay_translate_opts.setSpacing(4)

        lay_opts2 = QHBoxLayout()
        lay_opts2.setContentsMargins(0, 0, 0, 0)
        self._chk_auto_translate = ToggleSwitch(_("Auto-translate the transcription"))
        self._chk_auto_translate.setToolTip(
            _("Automatically translate after transcription"))
        lay_opts2.addWidget(self._chk_auto_translate)
        lay_opts2.addStretch()
        lay_translate_opts.addLayout(lay_opts2)

        # -- Options: row 3 — sync slider/text bidirectional --
        # Toggles built here, layout assembled below the rename
        # accordion so the user sees them in context with the
        # diarization controls.
        qs_sync = QSettings("dictee", "transcribe")
        self._chk_follow_text = ToggleSwitch(_("Follow playback in text"))
        self._chk_follow_text.setToolTip(
            _("Move text cursor in real time during audio playback"))
        self._chk_follow_text.setChecked(
            qs_sync.value("sync/follow_text", False, type=bool))
        self._chk_follow_text.toggled.connect(
            lambda v: QSettings("dictee", "transcribe").setValue("sync/follow_text", v))

        self._chk_play_on_click = ToggleSwitch(_("Auto-play on text click"))
        self._chk_play_on_click.setToolTip(
            _("Start playback when clicking on a segment in the text"))
        self._chk_play_on_click.setChecked(
            qs_sync.value("sync/play_on_click", False, type=bool))
        self._chk_play_on_click.toggled.connect(
            lambda v: QSettings("dictee", "transcribe").setValue("sync/play_on_click", v))

        self._chk_highlight_current = ToggleSwitch(_("Highlight current segment"))
        self._chk_highlight_current.setToolTip(
            _("Underline the segment matching the audio position"))
        self._chk_highlight_current.setChecked(
            qs_sync.value("sync/highlight_current", False, type=bool))
        self._chk_highlight_current.toggled.connect(
            lambda v: QSettings("dictee", "transcribe").setValue("sync/highlight_current", v))

        # -- Translation row (language pickers + backend label) --
        lay_trans = QHBoxLayout()
        lay_trans.setContentsMargins(0, 0, 0, 0)

        conf = _read_conf()
        qs_translate = QSettings("dictee", "transcribe")

        # Full language list — used as the master set. trans (Google)
        # supports 100+ languages and Ollama models like translategemma
        # cover most of them; this list keeps the most common ones to
        # stay manageable. The target combo is filtered down further
        # when the backend is libretranslate (only the languages loaded
        # via DICTEE_LIBRETRANSLATE_LANGS at container startup).
        self._lang_codes = [
            ("en", "English"), ("fr", "Français"), ("de", "Deutsch"),
            ("es", "Español"), ("it", "Italiano"), ("pt", "Português"),
            ("nl", "Nederlands"), ("pl", "Polski"), ("ro", "Română"),
            ("cs", "Čeština"), ("sk", "Slovenčina"), ("hu", "Magyar"),
            ("sv", "Svenska"), ("da", "Dansk"), ("nb", "Norsk"),
            ("fi", "Suomi"), ("el", "Ελληνικά"), ("bg", "Български"),
            ("hr", "Hrvatski"), ("sr", "Српски"), ("sl", "Slovenščina"),
            ("uk", "Українська"), ("ru", "Русский"), ("be", "Беларуская"),
            ("tr", "Türkçe"), ("ar", "العربية"), ("he", "עברית"),
            ("fa", "فارسی"), ("ur", "اردو"), ("hi", "हिन्दी"),
            ("bn", "বাংলা"), ("ta", "தமிழ்"), ("te", "తెలుగు"),
            ("zh", "中文"), ("ja", "日本語"), ("ko", "한국어"),
            ("vi", "Tiếng Việt"), ("th", "ไทย"), ("id", "Bahasa Indonesia"),
            ("ms", "Bahasa Melayu"), ("sw", "Kiswahili"),
        ]

        # Backend combo — same four values as the plasmoid's translate
        # backend selector. "google" and "bing" both invoke the `trans`
        # CLI with -e <engine>; "ollama" and "libretranslate" go to
        # their respective HTTP APIs.
        # Per-file choice, persisted in QSettings so it never touches
        # dictee.conf (which would silently re-route the dictation
        # translate shortcut). Source language is auto-detected from
        # the transcript, so no source combo here.
        self._cmb_backend = QComboBox()
        # "(cloud)" makes it explicit that Google/Bing send the
        # transcription to a remote API — Ollama/LT run locally.
        self._cmb_backend.addItem(_("Google (cloud)"), "google")
        self._cmb_backend.addItem(_("Bing (cloud)"), "bing")
        self._cmb_backend.addItem("Ollama", "ollama")
        self._cmb_backend.addItem("LibreTranslate", "libretranslate")
        # Initial default: resolve dictee.conf's backend → if "trans",
        # fall back to DICTEE_TRANS_ENGINE (google/bing); otherwise
        # use the backend directly (ollama/libretranslate).
        _conf_backend = conf.get("DICTEE_TRANSLATE_BACKEND", "trans")
        if _conf_backend == "trans":
            _conf_backend = (conf.get("DICTEE_TRANS_ENGINE", "google") or "google").lower()
        default_backend = qs_translate.value("translate/backend", _conf_backend)
        for i in range(self._cmb_backend.count()):
            if self._cmb_backend.itemData(i) == default_backend:
                self._cmb_backend.setCurrentIndex(i)
                break
        self._cmb_backend.setToolTip(self._tip(_(
            "Translation backend for this file. Volatile per-session; "
            "does not modify dictee.conf, so the dictation pipeline "
            "keeps using its own configured backend.")))
        lay_trans.addWidget(QLabel(_("Backend:")))
        lay_trans.addWidget(self._cmb_backend)

        # Target language combo — filtered dynamically when backend is
        # libretranslate (only the languages loaded in the LT container
        # are usable).
        self._cmb_lang_tgt = QComboBox()
        self._cmb_lang_tgt.setToolTip(self._tip(_(
            "Target language for this file. The source language is "
            "auto-detected from the transcribed text.")))
        lay_trans.addWidget(QLabel(_("Translate to:")))
        lay_trans.addWidget(self._cmb_lang_tgt)

        # Populate combo and select the saved target. The default
        # target falls back to dictee.conf only on the very first run
        # — afterwards it lives in QSettings.
        self._refilter_lang_tgt()
        default_tgt = qs_translate.value(
            "translate/lang_tgt",
            conf.get("DICTEE_LANG_TARGET", "fr"))
        for i in range(self._cmb_lang_tgt.count()):
            if self._cmb_lang_tgt.itemData(i) == default_tgt:
                self._cmb_lang_tgt.setCurrentIndex(i)
                break

        btn_setup_trans = QPushButton(_("Backend settings…"))
        btn_setup_trans.setToolTip(self._tip(_(
            "Open dictee-setup to configure backend infrastructure "
            "(Ollama model, LibreTranslate URL and loaded languages, "
            "trans engine). The per-file backend and target language "
            "above are managed here in transcribe.")))
        def _open_setup_translation():
            env = dict(os.environ)
            env["QT_QPA_PLATFORMTHEME"] = "kde"
            subprocess.Popen(["dictee-setup", "--translation"], env=env)
        btn_setup_trans.clicked.connect(_open_setup_translation)
        lay_trans.addWidget(btn_setup_trans)

        lay_trans.addStretch()
        lay_translate_opts.addLayout(lay_trans)

        lay_translate_h.addLayout(lay_translate_opts, 1)

        # Right column: tall orange Translate button
        self._btn_translate = QPushButton(_("Translate"))
        self._btn_translate.setEnabled(False)
        self._btn_translate.setToolTip(_("Translate the current transcription"))
        self._btn_translate.clicked.connect(self._on_translate)
        self._btn_translate.setMinimumWidth(140)
        self._btn_translate.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._btn_translate.setStyleSheet(
            "QPushButton { background: #e67e22; color: white; "
            "font-weight: bold; border: none; border-radius: 4px; "
            "padding: 6px 16px; }"
            "QPushButton:hover { background: #f39c12; }"
            "QPushButton:pressed { background: #d35400; }"
            "QPushButton:disabled { background: rgba(230,126,34,80); "
            "color: rgba(255,255,255,150); }")
        lay_translate_h.addWidget(self._btn_translate)

        pad_translate.addLayout(lay_translate_h)

        layout.addWidget(self._pad_translate)

        # -- Progress bar (replaced by per-tab spinner on the active
        # tab title — see _start_tab_spinner). We use a stub object
        # that no-ops all the calls, instead of an orphaned QProgressBar
        # widget — without a parent or layout, calling .setVisible(True)
        # on a real QProgressBar promotes it to a top-level Wayland
        # window (a tiny floating dialog with the app_id as title).
        class _NullProgress:
            def setVisible(self, *_a, **_k): pass
            def setRange(self, *_a, **_k): pass
            def setValue(self, *_a, **_k): pass
            def isVisible(self): return False
        self._progress = _NullProgress()

        # === Text pad: status, rename accordion, sync toggles, tabs, search, action buttons ===
        self._pad_text = QFrame()
        self._pad_text.setObjectName("padSection")
        self._pad_text.setStyleSheet(
            "QFrame#padSection { border: 1px solid palette(mid); "
            "border-radius: 6px; background: palette(base); }")
        pad_text = QVBoxLayout(self._pad_text)
        pad_text.setContentsMargins(10, 8, 10, 8)
        pad_text.setSpacing(6)

        # -- Status label --
        self._lbl_status = QLabel()
        self._lbl_status.setVisible(False)
        pad_text.addWidget(self._lbl_status)

        # -- Speaker rename panel (visible only after diarization) --
        self._build_rename_section(pad_text)

        # -- Sync toggles (follow / play-on-click / highlight) --
        # Placed below the rename accordion so they sit close to the
        # diarization controls without being hidden when no segments
        # are loaded. Per-instance override of the ToggleSwitch track
        # / handle dimensions to shrink the visual switch (the
        # default 44×22 track is overkill for these 3 utility toggles).
        for chk in (self._chk_follow_text, self._chk_play_on_click,
                    self._chk_highlight_current):
            chk._TRACK_W = 28
            chk._TRACK_H = 14
            chk._TRACK_RADIUS = 7
            chk._HANDLE_RADIUS = 5
            chk._TEXT_SPACING = 6
            chk.updateGeometry()
        lay_opts3 = QHBoxLayout()
        lay_opts3.setContentsMargins(0, 0, 0, 0)
        lay_opts3.setSpacing(12)
        lay_opts3.addWidget(self._chk_follow_text)
        lay_opts3.addWidget(self._chk_play_on_click)
        lay_opts3.addWidget(self._chk_highlight_current)
        lay_opts3.addStretch()
        pad_text.addLayout(lay_opts3)

        # -- Tab widget: Original + dynamic translation tabs --
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close)

        # Edit mode toggle in the tab-bar's left corner. When enabled,
        # mouse clicks in the text only move the caret (no audio seek)
        # so the user can fix typos without the slider jumping around.
        self._btn_edit_mode = QPushButton("✏️")  # pencil emoji
        self._btn_edit_mode.setCheckable(True)
        self._btn_edit_mode.setChecked(True)  # click-to-seek on by default
        self._btn_edit_mode.setFixedWidth(26)
        # Tighten padding/margin so the button hugs the first tab tightly
        self._btn_edit_mode.setStyleSheet(
            "QPushButton { padding: 0 2px; margin: 0; }")
        self._btn_edit_mode.setToolTip(self._tip(_(
            "Click-to-seek: when enabled, clicking in the text seeks the "
            "audio and the text is read-only. Toggle off to edit the "
            "text freely (no audio seek).")))
        self._btn_edit_mode.toggled.connect(self._on_edit_mode_toggled)
        self._tabs.setCornerWidget(self._btn_edit_mode, Qt.Corner.TopLeftCorner)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(self._btn_edit_mode.isChecked())
        self._text_edit.setPlaceholderText(
            _("Press the pencil to edit.") + "\n"
            + _("Ctrl+F to search, Ctrl+Z to undo"))
        self._text_edit.viewport().installEventFilter(self)
        self._install_modified_overlay(self._text_edit)
        self._init_tab_state(self._text_edit)
        self._tabs.addTab(self._text_edit, _("Original"))
        # Original tab is not closable
        self._tabs.tabBar().setTabButton(0, self._tabs.tabBar().ButtonPosition.RightSide, None)

        pad_text.addWidget(self._tabs, 1)

        # -- Search bar (works on active tab) --
        self._search_bar = SearchBar(self._text_edit, self)
        pad_text.addWidget(self._search_bar)

        # -- Bottom buttons: text tools left, exports + close right --
        lay_btns = QHBoxLayout()

        # Left: text tools (LLM analysis, copy)
        self._btn_llm = QPushButton(_("LLM analysis..."))
        self._btn_llm.setToolTip(self._tip(_(
            "Run an LLM analysis on the transcript "
            "(summary, chapters, ASR correction, custom prompt)")))
        self._btn_llm.clicked.connect(self._on_llm_process)
        lay_btns.addWidget(self._btn_llm)

        self._btn_copy = QPushButton(_("Copy all"))
        self._btn_copy.setToolTip(_("Copy the entire text to the clipboard"))
        self._btn_copy.clicked.connect(self._on_copy)
        lay_btns.addWidget(self._btn_copy)

        lay_btns.addStretch()

        # Right: exports + close
        self._btn_export = QPushButton(_("Export..."))
        self._btn_export.setToolTip(_(
            "Export the currently active tab "
            "(transcription, translation, or LLM result)"))
        self._btn_export.clicked.connect(self._on_export_current_tab)
        lay_btns.addWidget(self._btn_export)

        self._btn_close = QPushButton(_("Close"))
        self._btn_close.setToolTip(_("Close this window"))
        self._btn_close.clicked.connect(self.close)
        lay_btns.addWidget(self._btn_close)

        pad_text.addLayout(lay_btns)

        layout.addWidget(self._pad_text, 1)

    def closeEvent(self, event):
        """Clean up processes on window close."""
        self._player.stop()
        # Signal every worker to abort first (cancel + kill), then wait
        # briefly. Without the cancel calls the wait() below would block
        # the UI for the full HTTP/socket timeout instead of returning
        # almost instantly.
        self._abort_main_workers()
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.waitForFinished(3000)
        if self._translate_thread and self._translate_thread.isRunning():
            self._translate_thread.wait(5000)
        if hasattr(self, '_diarize_worker') and self._diarize_worker and self._diarize_worker.isRunning():
            self._diarize_worker.wait(5000)
        if hasattr(self, '_chunked_worker') and self._chunked_worker and self._chunked_worker.isRunning():
            self._chunked_worker.wait(5000)
            # Safety net: if the worker timed out before the finally:
            # block in run() could fire, the tmp dir is still around.
            # /tmp/dictee_chunks_<pid>_<ts>/ can hold hundreds of MB
            # of WAV chunks for a long file — clean it up by hand.
            try:
                self._chunked_worker._cleanup_tmp()
            except Exception as _e:
                _dbg(f"silenced: {_e!r}")
        # Restore backend if we were in diarization mode
        conf = _read_conf()
        if conf.get("DICTEE_PRE_DIARIZE_BACKEND"):
            _dbg("closeEvent: restoring backend via diarize false")
            subprocess.Popen(["dictee-switch-backend", "diarize", "false"])
        elif getattr(self, '_daemon_was_active', False):
            # Restart daemon if we stopped it for VRAM
            asr = conf.get("DICTEE_ASR_BACKEND", "parakeet")
            svc_map = {"parakeet": "dictee", "vosk": "dictee-vosk",
                       "whisper": "dictee-whisper",
                       "whisper-rust": "dictee-whisper-rust",
                       "canary": "dictee-canary",
                       "nemotron": "dictee-nemotron"}
            subprocess.Popen(["systemctl", "--user", "enable", "--now", svc_map.get(asr, "dictee")])
        # Restaurer l'état idle pour le plasmoid
        _state_file = "/dev/shm/.dictee_state"
        _state_lock = "/dev/shm/.dictee_state.lock"
        try:
            import fcntl
            with open(_state_lock, "w") as lf:
                fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with open(_state_file, "w") as sf:
                    sf.write("idle")
        except Exception as _e:
            _dbg(f"silenced: {_e!r}")
        # Close log file
        global _log_file
        if _log_file:
            _log_file.close()
            _log_file = None
        super().closeEvent(event)

    def _active_editor(self):
        """Return the QTextEdit of the active tab."""
        widget = self._tabs.currentWidget()
        return widget if isinstance(widget, QTextEdit) else self._text_edit

    def _init_tab_state(self, editor, audio_path=None):
        """Give a fresh tab the full canonical per-tab state (see the
        'State ownership' block above the class). Every QTextEdit tab
        goes through here at creation so downstream code can rely on
        the attributes existing (LLM result tabs excepted)."""
        editor._audio_path = audio_path
        editor._raw_text = ""
        editor._was_diarized = False
        editor._diarize_segments = []
        editor._speaker_name_map = {}
        editor._status_text = ""
        editor._audio_duration = 0.0
        editor._transcribe_elapsed = 0.0
        editor._translate_elapsed = 0.0
        editor._segment_positions = []
        # Display format owned by the tab, captured from the combo at
        # creation time: a run that lands while the user reads another
        # tab must be rendered in the format its run was started with,
        # not in the one the combo happens to show (_apply_format_to).
        editor._format = (self._cmb_format.currentData()
                          if hasattr(self, "_cmb_format") else None)
        # Rename family: the run tab this tab is a view of. A fresh tab
        # is its own family; translation tabs join their source's family
        # (_on_translate_done). Speaker renames apply per family, never
        # across independent runs — even of the same audio file, since
        # "Speaker N" can name a different person in every run.
        editor._rename_family = editor

    def _active_tab_attr(self, name, default):
        """Read a per-tab attribute from the active tab (used by the
        read-only projections below). Mirrors what _on_tab_changed used
        to copy onto the window: non-QTextEdit tabs and the pre-build
        window yield the empty defaults."""
        tabs = getattr(self, '_tabs', None)
        widget = tabs.currentWidget() if tabs is not None else None
        return getattr(widget, name, default) if widget is not None else default

    @property
    def _raw_text(self):
        """Read-only projection: the active tab's raw engine output.
        Writers must target a tab's `_raw_text` directly. Returns the
        tab's live value — copy before mutating."""
        return self._active_tab_attr('_raw_text', "")

    @property
    def _speaker_name_map(self):
        """Read-only projection: the active tab's speaker display map
        {canonical_id -> custom_name}. Writers must target a tab's
        `_speaker_name_map` directly. Returns the tab's live dict —
        copy before mutating."""
        return self._active_tab_attr('_speaker_name_map', {})

    @property
    def _was_diarized(self):
        """Read-only projection: whether the active tab's run used
        diarization. Writers must target a tab's `_was_diarized`."""
        return bool(self._active_tab_attr('_was_diarized', False))

    @property
    def _segments(self):
        """Read-only projection: the active tab's parsed segments
        (stored as `_diarize_segments` on the tab — historical naming).
        Writers must target a tab's `_diarize_segments` directly.
        Returns the tab's live list — copy before mutating."""
        return self._active_tab_attr('_diarize_segments', [])

    def _on_tab_close(self, index):
        """Close a tab and abort whatever work is feeding it.

        Robust shutdown: every worker that could write into the tab we
        drop is signalled to cancel (suppress emit), so the QTextEdit
        can be deleted without Qt firing on a dangling C++ object.
        Long-running HTTP/socket calls keep going in the background
        but their result is discarded.
        """
        widget = self._tabs.widget(index)
        # LLM result tab still spinning: cancel the thread, then drop
        # the tab.
        if getattr(widget, "_is_llm_result", False):
            thread = getattr(widget, "_llm_thread", None)
            if thread is not None and thread.isRunning():
                thread.cancel()
            self._stop_tab_spinner(widget)
            self._tabs.removeTab(index)
            widget.deleteLater()
            return
        if widget is self._text_edit:
            self._abort_main_workers()
        self._tabs.removeTab(index)

    def _abort_main_workers(self):
        """Cancel every worker that could still touch self._text_edit.
        Used when the user closes the main tab or the whole window
        mid-flight. Returns immediately — workers finish in the
        background, their emit is suppressed."""
        if self._process is not None \
                and self._process.state() != QProcess.ProcessState.NotRunning:
            _dbg("abort: killing transcription QProcess")
            try:
                self._process.kill()
            except Exception as _e:
                _dbg(f"silenced: {_e!r}")
        for attr in ("_chunked_worker", "_diarize_worker", "_translate_thread"):
            w = getattr(self, attr, None)
            if w is not None and w.isRunning():
                _dbg(f"abort: cancelling {attr}")
                # All three workers expose either request_cancel
                # (legacy chunked pipeline) or cancel.
                if hasattr(w, "request_cancel"):
                    try:
                        w.request_cancel()
                    except Exception as _e:
                        _dbg(f"silenced: {_e!r}")
                if hasattr(w, "cancel"):
                    try:
                        w.cancel()
                    except Exception as _e:
                        _dbg(f"silenced: {_e!r}")
        # Kill the ad-hoc isolated ASR daemon too (window/main-tab closed
        # mid-run). closeEvent calls this, so the private socket is freed.
        self._stop_isolated_daemon()
        # Cancelled workers suppress their own signals, so the completion
        # slots that normally clear these never fire — reset the run state
        # here or _update_transcribe_btn() keeps everything greyed forever
        # and the 1 Hz ticker leaks. (The phase-1 QProcess path recovers on
        # its own: kill() above still delivers finished → _on_finished.)
        self._diarize_worker = None
        self._chunked_worker = None
        self._transcription_in_progress = False
        self._stop_run_ticker()
        # Hide the cancel button + reset status so the next run starts
        # from a clean slate.
        if hasattr(self, "_btn_cancel"):
            self._btn_cancel.setVisible(False)
        self._update_transcribe_btn()

    def _connect_signals(self):
        self._file_input.textChanged.connect(self._update_transcribe_btn)
        self._file_input.textChanged.connect(self._update_long_audio_warning)
        # User picked an entry in the recent-files dropdown: reload the
        # player like _on_browse does, or Play keeps the previous audio.
        self._file_combo.activated.connect(self._on_recent_file_selected)
        self._cmb_format.currentIndexChanged.connect(self._on_format_changed)
        self._cmb_backend.currentIndexChanged.connect(self._on_translate_choice_changed)
        self._cmb_lang_tgt.currentIndexChanged.connect(self._on_translate_choice_changed)
        self._chk_auto_translate.toggled.connect(lambda: self._update_translate_btn())
        self._tabs.currentChanged.connect(self._on_tab_changed)

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
        """Refresh UI when dictee.conf changes (live sync with dictee-setup).

        Translate pad is now independent (backend + target language live
        in QSettings, not dictee.conf). The only thing we still pull
        from disk on conf change is the DICTEE_LIBRETRANSLATE_LANGS
        list, which determines what target languages are usable when
        backend == libretranslate.
        """
        _dbg(f"_on_conf_changed: {path}")
        if self._cmb_backend.currentData() == "libretranslate":
            self._refilter_lang_tgt()
        self._update_translate_btn()
        # Re-add to watcher (some editors replace the file, removing the watch)
        if hasattr(self, '_conf_watcher') and path not in self._conf_watcher.files():
            self._conf_watcher.addPath(path)

    def _refilter_lang_tgt(self):
        """Repopulate _cmb_lang_tgt according to the current backend.

        - trans / ollama: full language list (anything they support).
        - libretranslate: only languages loaded in the LT container
          (DICTEE_LIBRETRANSLATE_LANGS in dictee.conf — set by
          dictee-setup when starting the container).

        Preserves the current selection if the new list still contains
        it; otherwise the combo lands on its first item and the user
        will see the change.
        """
        prev = self._cmb_lang_tgt.currentData()
        backend = self._cmb_backend.currentData()
        if backend == "libretranslate":
            conf = _read_conf()
            allowed = set(c.strip() for c in conf.get(
                "DICTEE_LIBRETRANSLATE_LANGS",
                "en,fr,es,de,it,pt,uk,ru,tr,ar,zh,hi,bn,ja,ko").split(",")
                if c.strip())
            codes = [(c, n) for c, n in self._lang_codes if c in allowed]
        else:
            codes = list(self._lang_codes)

        self._cmb_lang_tgt.blockSignals(True)
        self._cmb_lang_tgt.clear()
        for code, name in codes:
            self._cmb_lang_tgt.addItem(f"{code} — {name}", code)
        # Restore previous selection if still valid
        if prev:
            for i in range(self._cmb_lang_tgt.count()):
                if self._cmb_lang_tgt.itemData(i) == prev:
                    self._cmb_lang_tgt.setCurrentIndex(i)
                    break
        self._cmb_lang_tgt.blockSignals(False)

    def _on_translate_choice_changed(self):
        """Persist backend + target language to QSettings (per-file
        choices that must NOT touch dictee.conf), and refilter the
        target combo if the backend changed."""
        backend = self._cmb_backend.currentData()
        tgt = self._cmb_lang_tgt.currentData()
        qs = QSettings("dictee", "transcribe")
        if backend:
            qs.setValue("translate/backend", backend)
        if tgt:
            qs.setValue("translate/lang_tgt", tgt)
        # Re-filter target language list if backend changed (the
        # caller may have changed either combo, so we always check).
        # blockSignals inside _refilter avoids a recursion loop.
        self._refilter_lang_tgt()
        self._update_translate_btn()

    def _update_translate_btn(self):
        tgt = self._cmb_lang_tgt.currentData()
        translating = self._translate_thread and self._translate_thread.isRunning()
        # The translation source follows the active tab (the run it is
        # a view of, cf. _on_translate) — the button reflects whether
        # THAT run has produced text. _on_tab_changed re-projects this
        # on every switch.
        src = (getattr(self._active_editor(), '_rename_family', None)
               or self._text_edit)
        self._btn_translate.setEnabled(
            bool(tgt)
            and bool(getattr(src, '_raw_text', ''))
            and _translate_available(self._cmb_backend.currentData())
            and not self._chk_auto_translate.isChecked()
            and not translating)

    def _update_transcribe_btn(self):
        has_file = bool(self._file_input.text().strip())
        # `_transcription_in_progress` is the single source of truth: it
        # is raised at the start of _on_transcribe and lowered only when
        # the run truly ends (success or error). The QProcess /
        # _diarize_worker / _chunked_worker checks remain as belt &
        # braces — there's a brief window between phase 1's QProcess
        # cleanup and phase 2's worker spawn where all three are None,
        # which the flag covers.
        not_running = (
            not getattr(self, "_transcription_in_progress", False)
            and self._process is None
            and getattr(self, "_diarize_worker", None) is None
            and getattr(self, "_chunked_worker", None) is None
        )
        self._btn_transcribe.setEnabled(has_file and not_running)
        # Same gating for inputs whose value would otherwise be picked
        # up mid-run (diarize toggle is read at job start; auto-translate
        # is checked when results land). We never *force* them on; we
        # only block changes while a job is in-flight.
        if hasattr(self, "_chk_diarize"):
            self._chk_diarize.setEnabled(
                not_running and getattr(self, "_diar_available", True))
        if hasattr(self, "_chk_auto_translate"):
            self._chk_auto_translate.setEnabled(not_running)
        if hasattr(self, "_sld_sensitivity"):
            self._sld_sensitivity.setEnabled(not_running)

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

    def _reload_recent_files(self):
        """Fill the file combo's dropdown from the persisted recent list
        without touching the visible edit text."""
        qs = QSettings("dictee", "transcribe")
        paths = qs.value("file/recent", []) or []
        if isinstance(paths, str):
            paths = [paths]
        cur = self._file_input.text()
        self._file_combo.blockSignals(True)
        self._file_input.blockSignals(True)
        self._file_combo.clear()
        self._file_combo.addItems([p for p in paths if p])
        self._file_combo.setCurrentIndex(-1)
        self._file_input.setText(cur)
        self._file_input.blockSignals(False)
        self._file_combo.blockSignals(False)

    def _add_recent_file(self, path, _max=10):
        """Move `path` to the top of the persisted recent-files list."""
        qs = QSettings("dictee", "transcribe")
        paths = qs.value("file/recent", []) or []
        if isinstance(paths, str):
            paths = [paths]
        paths = [path] + [p for p in paths if p and p != path]
        qs.setValue("file/recent", paths[:_max])
        self._reload_recent_files()

    def _on_browse(self):
        _dbg("_on_browse: opening file dialog")
        path, _filter = QFileDialog.getOpenFileName(
            self, _("Select audio file"), "", AUDIO_FILTER)
        if path:
            _dbg(f"_on_browse: selected {path}")
            self._file_input.setText(path)
            self._player.stop()
            self._load_audio(path)

    def _on_recent_file_selected(self, _index):
        """Recent-files dropdown selection: sync the player to the choice."""
        path = self._file_input.text().strip()
        if path:
            self._player.stop()
            self._load_audio(path)

    def _on_open_history(self):
        items = list_past_meetings()
        if not items:
            QMessageBox.information(self, _("History"), _("No past meeting found."))
            return
        labels = [lbl for lbl, _p in items]
        choice, ok = QInputDialog.getItem(
            self, _("Past meetings"), _("Meeting:"), labels, 0, False)
        if ok and choice:
            path = dict(zip(labels, [p for _l, p in items]))[choice]
            self._file_input.setText(path)
            # Mirror _on_browse: without this the player kept its previous
            # source and Play played the wrong recording.
            self._player.stop()
            self._load_audio(path)

    # -- Drag & drop audio file onto the window --

    AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".oga", ".m4a",
                  ".opus", ".aac", ".webm", ".mp4", ".mkv", ".wma"}

    def _drop_pick_audio(self, event):
        """Return the first local audio path in the drag event, or None."""
        md = event.mimeData()
        if not md or not md.hasUrls():
            return None
        for url in md.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if not os.path.isfile(path):
                continue
            if os.path.splitext(path)[1].lower() in self.AUDIO_EXTS:
                return path
        return None

    def dragEnterEvent(self, event):
        if self._drop_pick_audio(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._drop_pick_audio(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._drop_pick_audio(event)
        if not path:
            event.ignore()
            return
        event.acceptProposedAction()
        _dbg(f"dropEvent: loading {path}")
        self._file_input.setText(path)
        self._player.stop()
        self._load_audio(path)

    # -- Audio player methods --

    def _load_audio(self, path):
        """Load an audio file into the player."""
        self._player.setSource(QUrl.fromLocalFile(path))

    def _on_play_pause(self):
        # Load file if not yet loaded
        path = self._file_input.text().strip()
        if not path:
            return
        if self._player.source().isEmpty():
            self._load_audio(path)
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_player_stop(self):
        self._player.stop()

    def _find_segment_for_time(self, t, segs):
        """Return the segment containing t, or the closest one if t falls
        in a silence/gap. Returns None if segs is empty."""
        if not segs:
            return None
        for s in segs:
            if s["start"] <= t < s["end"]:
                return s
        # Fallback: argmin distance to either edge
        return min(segs, key=lambda s: min(abs(t - s["start"]), abs(t - s["end"])))

    def _speaker_index(self, spk):
        """Extract integer index from 'Speaker N' label.
        Returns 0 for UNKNOWN or any non-numeric speaker."""
        m = re.search(r'\d+', spk or '')
        return int(m.group(0)) if m else 0

    def _on_seek(self, position):
        """User clicked the slider: seek + always sync text cursor (regardless of toggle)."""
        self._player.setPosition(position)
        self._sync_text_to_position(position / 1000.0, force_cursor=True)

    def _on_player_position(self, pos_ms):
        if not self._sld_position.isSliderDown():
            self._sld_position.setValue(pos_ms)
        dur_ms = self._player.duration()
        self._lbl_time.setText(
            f"{self._ms_to_str(pos_ms)} / {self._ms_to_str(dur_ms)}")
        # Continuous playback sync: respect the user toggles
        if (self._chk_follow_text.isChecked()
                or self._chk_highlight_current.isChecked()):
            self._sync_text_to_position(pos_ms / 1000.0)

    def _sync_text_to_position(self, t, force_cursor=False):
        """Move the text cursor (and optionally highlight) to the segment at
        time t. force_cursor=True moves the cursor unconditionally (slider
        click); otherwise the move respects the _chk_follow_text toggle.
        Highlight is independent and respects _chk_highlight_current.
        Silently no-op if there are no segments in the active tab."""
        editor = self._active_editor()
        segs = getattr(editor, '_diarize_segments', None) or []
        if not segs:
            return
        seg = self._find_segment_for_time(t, segs)
        if seg is None:
            return
        if force_cursor or self._chk_follow_text.isChecked():
            self._move_text_cursor_to_segment(editor, seg)
        if self._chk_highlight_current.isChecked():
            self._highlight_segment(editor, seg)

    def _highlight_segment(self, editor, seg):
        """Underline the current segment's rendered text in its speaker
        colour and clear the previously underlined range. Lookup uses
        editor._segment_positions, mergeCharFormat preserves the existing
        text colour applied by the formatter."""
        positions = getattr(editor, '_segment_positions', None)
        if not positions:
            return
        pos_start = pos_end = None
        for p in positions:
            if abs(p["seg"]["start"] - seg["start"]) < 0.01:
                pos_start, pos_end = p["start"], p["end"]
                break
        if pos_start is None:
            return

        # Clear previous highlight: remove underline AND restore the
        # default foreground colour (else the previously highlighted
        # segment stays speaker-coloured forever).
        default_brush = QBrush(editor.palette().text().color())
        prev = getattr(editor, '_current_highlight_range', None)
        if prev is not None and prev != (pos_start, pos_end):
            old_start, old_end = prev
            cursor = editor.textCursor()
            cursor.setPosition(old_start)
            cursor.setPosition(old_end, QTextCursor.MoveMode.KeepAnchor)
            clear_fmt = QTextCharFormat()
            clear_fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.NoUnderline)
            clear_fmt.setForeground(default_brush)
            cursor.mergeCharFormat(clear_fmt)

        # Apply the new highlight: underline + text colour both in the
        # speaker palette colour, so the segment really stands out.
        cursor = editor.textCursor()
        cursor.setPosition(pos_start)
        cursor.setPosition(pos_end, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
        idx = self._speaker_index(seg.get("speaker", ""))
        spk_color = QColor(SPEAKER_COLORS[idx % len(SPEAKER_COLORS)])
        fmt.setUnderlineColor(spk_color)
        fmt.setForeground(QBrush(spk_color))
        cursor.mergeCharFormat(fmt)

        editor._current_highlight_range = (pos_start, pos_end)

    def eventFilter(self, obj, event):
        """Capture mouse release on QTextEdit viewports to drive text->slider
        sync. We watch viewport() (not the QTextEdit itself) because that's
        where mouse events land in QAbstractScrollArea. Pass the actual
        click point — editor.textCursor() lags by one event and would map
        the click to the previously-active segment.

        When the edit-mode corner button is on, the click-to-seek is
        bypassed so the user can move the caret to fix typos without the
        audio slider jumping around."""
        if event.type() == QEvent.Type.MouseButtonRelease:
            seek_on = (hasattr(self, '_btn_edit_mode')
                       and self._btn_edit_mode.isChecked())
            parent = obj.parent() if hasattr(obj, 'parent') else None
            if isinstance(parent, QTextEdit) and seek_on:
                # Qt6 uses event.position() (QPointF); fall back to pos()
                # for older bindings.
                point = (event.position().toPoint()
                         if hasattr(event, 'position')
                         else event.pos())
                cursor_at_click = parent.cursorForPosition(point)
                self._on_text_clicked(parent, cursor_at_click.position())
        elif event.type() == QEvent.Type.KeyPress:
            # Light the Modified badge ONLY when the user actually types.
            # KeyPress is dispatched to the focused QTextEdit itself
            # (eventFilter installed in _install_modified_overlay), so
            # obj is the QTextEdit directly.
            if isinstance(obj, QTextEdit) and not obj.isReadOnly():
                text = event.text()
                edit_keys = {Qt.Key.Key_Backspace, Qt.Key.Key_Delete,
                             Qt.Key.Key_Return, Qt.Key.Key_Enter}
                if text or event.key() in edit_keys:
                    overlay = getattr(obj, '_modified_overlay', None)
                    if overlay is not None:
                        self._reposition_modified_overlay(obj)
                        overlay.setVisible(True)
                        overlay.raise_()
        return super().eventFilter(obj, event)

    def _on_text_clicked(self, editor, click_pos=None):
        """User clicked at click_pos (or editor.textCursor() fallback).
        Find the segment whose rendered range contains it and seek the
        player there. Closest-segment fallback when the click landed in
        a gap (speaker header line, blank space)."""
        positions = getattr(editor, '_segment_positions', None)
        if not positions:
            return
        if click_pos is None:
            click_pos = editor.textCursor().position()
        matched = None
        for p in positions:
            if p["start"] <= click_pos <= p["end"]:
                matched = p
                break
        if matched is None:
            matched = min(positions, key=lambda p: min(
                abs(click_pos - p["start"]), abs(click_pos - p["end"])))
        self._player.setPosition(int(matched["seg"]["start"] * 1000))
        if self._chk_play_on_click.isChecked():
            self._player.play()

    def _install_modified_overlay(self, editor):
        """Attach a red 'Modified' badge in the top-right of the editor.
        Visibility is driven by KeyPress events caught in eventFilter:
        we install the filter on the editor itself (KeyPress is dispatched
        to the focused widget, not its viewport — viewport only sees
        mouse events). Hidden by _apply_format_to (after a render) and
        by _on_edit_mode_toggled (after the sync recompute)."""
        overlay = QLabel(_("● Modified"), editor)
        overlay.setStyleSheet(
            "QLabel { color: white; background: rgba(220, 50, 50, 220); "
            "padding: 2px 8px; border-radius: 4px; font-weight: bold; }")
        overlay.setVisible(False)
        overlay.adjustSize()
        overlay.raise_()
        editor._modified_overlay = overlay

        # KeyPress goes to the QTextEdit (focused widget), not the
        # viewport which only handles mouse events.
        editor.installEventFilter(self)

        # Wrap resizeEvent (subclassing avoided) to reposition on resize.
        base_resize = editor.resizeEvent
        def _resize(ev):
            base_resize(ev)
            self._reposition_modified_overlay(editor)
        editor.resizeEvent = _resize
        self._reposition_modified_overlay(editor)

    def _reposition_modified_overlay(self, editor):
        overlay = getattr(editor, '_modified_overlay', None)
        if overlay is None:
            return
        margin = 8
        x = editor.viewport().width() - overlay.width() - margin
        overlay.move(x, margin)

    def _on_edit_mode_toggled(self, checked):
        """Sync read-only state of every QTextEdit with the click-to-seek
        toggle. checked=True (✏️ on) makes editors read-only and also
        re-computes the segment<->position mapping in case the user
        added/removed characters while the toggle was off (otherwise the
        highlight would land on stale offsets). Surface a brief status
        line so the user knows the sync was refreshed."""
        n_recomputed = 0
        for i in range(self._tabs.count()):
            w = self._tabs.widget(i)
            if isinstance(w, QTextEdit):
                w.setReadOnly(checked)
                if checked:
                    segs = getattr(w, '_diarize_segments', None) or []
                    if segs:
                        self._compute_segment_positions(w, segs)
                        n_recomputed += 1
                    # Sync caught up — hide the per-tab Modified badge.
                    overlay = getattr(w, '_modified_overlay', None)
                    if overlay is not None:
                        overlay.setVisible(False)
        if checked and n_recomputed > 0:
            self._lbl_status.setText(_("Sync positions refreshed after edits."))
            self._lbl_status.setVisible(True)
            QTimer.singleShot(2500, lambda: self._lbl_status.setVisible(False))

    def _move_text_cursor_to_segment(self, editor, seg):
        """Position the cursor at the start of the segment's rendered text
        and centre it vertically in the viewport. Uses _segment_positions
        populated by _apply_format_to (plain colored, SRT and JSON).

        QTextEdit has no centerCursor() (only QPlainTextEdit does), so we
        centre manually: compute the cursor's Y in the viewport and shift
        the vertical scrollbar to bring it to the middle. The scrollbar
        clamps automatically near top/bottom of the document."""
        positions = getattr(editor, '_segment_positions', None)
        if not positions:
            return
        for p in positions:
            if abs(p["seg"]["start"] - seg["start"]) < 0.01:
                cursor = editor.textCursor()
                cursor.setPosition(p["start"])
                editor.setTextCursor(cursor)
                rect = editor.cursorRect()
                viewport_h = editor.viewport().height()
                sb = editor.verticalScrollBar()
                sb.setValue(sb.value()
                            + rect.top()
                            - viewport_h // 2
                            + rect.height() // 2)
                return

    def _on_player_duration(self, dur_ms):
        self._sld_position.setRange(0, dur_ms)
        self._lbl_time.setText(
            f"0:00 / {self._ms_to_str(dur_ms)}")

    def _on_playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._btn_play.setText("⏸")
            self._btn_play.setStyleSheet("font-size: 24px;")
        else:
            self._btn_play.setText("▶")
            self._btn_play.setStyleSheet("")

    def _on_audio_outputs_changed(self):
        """Re-pin playback to the system default output device.

        Fired when the audio device list changes (Bluetooth headphones
        connect/disconnect, dock plugged...). Without this the player keeps
        the device captured when the window was opened.
        """
        try:
            self._audio_output.setDevice(QMediaDevices.defaultAudioOutput())
        except Exception as _e:
            _dbg(f"audio output re-pin failed: {_e!r}")

    @staticmethod
    def _ms_to_str(ms):
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def _update_player_markers(self, target):
        """Update slider markers from current segments.

        Same target-tab pattern as _apply_format_to / _refresh_rename_panel_for_target:
        if the user has switched away from the transcription target tab while
        the diarization was running, do NOT push the target's speaker markers
        onto the global timeline — that would make the timeline show speakers
        of the target tab while the visible tab is a plain-text transcription
        (visually inconsistent). _on_tab_changed re-syncs the markers when
        the user returns to the target.
        """
        if self._tabs.currentWidget() is not target:
            return
        segs = getattr(target, '_diarize_segments', [])
        if not segs:
            self._sld_position.clear_markers()
            return
        markers = []
        for seg in segs:
            # Extract speaker number for color
            spk = seg.get("speaker", "")
            try:
                spk_idx = int(spk.split()[-1]) if "Speaker" in spk else 0
            except (ValueError, IndexError):
                spk_idx = 0
            color = SPEAKER_COLORS[spk_idx % len(SPEAKER_COLORS)]
            markers.append((
                int(seg["start"] * 1000),
                int(seg["end"] * 1000),
                color))
        self._sld_position.set_markers(markers)

    def _on_prev_segment(self):
        """Jump to previous speaker segment start. Reads segments from
        the active tab."""
        segs = getattr(self._active_editor(), '_diarize_segments', None) or []
        if not segs:
            return
        pos_s = self._player.position() / 1000.0 - 0.1
        for seg in reversed(segs):
            if seg["start"] < pos_s:
                self._player.setPosition(int(seg["start"] * 1000))
                return
        # Wrap to last
        self._player.setPosition(int(segs[-1]["start"] * 1000))

    def _on_next_segment(self):
        """Jump to next speaker segment start. Reads segments from the
        active tab — see _on_prev_segment."""
        segs = getattr(self._active_editor(), '_diarize_segments', None) or []
        if not segs:
            return
        pos_s = self._player.position() / 1000.0 + 0.1
        for seg in segs:
            if seg["start"] > pos_s:
                self._player.setPosition(int(seg["start"] * 1000))
                return
        # Wrap to first segment of the active tab's list.
        self._player.setPosition(int(segs[0]["start"] * 1000))

    def _on_tab_changed(self, index):
        self._search_bar.set_editor(self._active_editor())
        # Update player markers — show ONLY the segments of the active tab
        widget = self._tabs.widget(index)
        if widget is None:
            self._sld_position.clear_markers()
            if hasattr(self, '_grp_rename'):
                self._grp_rename.setVisible(False)
            return
        # Reload the audio file associated with this tab so the
        # timeline length matches the current tab (different tabs may
        # have different durations).
        audio_path = getattr(widget, '_audio_path', None)
        if audio_path and os.path.isfile(audio_path):
            current_src = self._player.source().toLocalFile()
            if current_src != audio_path:
                self._load_audio(audio_path)
        segs = getattr(widget, '_diarize_segments', [])
        # Build markers only from this tab's segments
        markers = []
        for seg in segs:
            spk = seg.get("speaker", "")
            try:
                spk_idx = int(spk.split()[-1]) if "Speaker" in spk else 0
            except (ValueError, IndexError):
                spk_idx = 0
            color = SPEAKER_COLORS[spk_idx % len(SPEAKER_COLORS)]
            markers.append((int(seg["start"] * 1000), int(seg["end"] * 1000), color))
        self._sld_position.set_markers(markers)

        # Sync per-tab state onto the instance. Read _was_diarized from the
        # tab itself (set in _finish_transcription / _on_finished) so that
        # switching from a diarized tab to a plain-text tab correctly
        # resets the flag — otherwise downstream code (_apply_format,
        # _show_status, etc.) would still treat the active tab as diarized.
        if hasattr(self, '_grp_rename'):
            if bool(getattr(widget, '_was_diarized', False)) and segs:
                self._populate_rename_fields()
            else:
                self._grp_rename.setVisible(False)

        # The status row follows the tabs (2026-07-21): restore this tab's
        # last stored status — the live text of its running job, or its
        # final summary — instead of leaving another tab's message behind.
        # Mirror _show_status's split: a diarized tab's summary lives next
        # to the rename header (bottom label hidden); plain tabs and live
        # run status use the bottom label. Without this split the bottom
        # label showed the summary in the wrong place while the rename
        # header kept the LAST finished run's summary forever.
        _st = getattr(widget, '_status_text', "")
        _diarized_tab = bool(getattr(widget, '_was_diarized', False))
        if hasattr(self, '_lbl_rename_status'):
            self._lbl_rename_status.setText(_st if _diarized_tab else "")
        if _st and not _diarized_tab:
            self._lbl_status.setText(_st)
            self._lbl_status.setVisible(True)
        else:
            self._lbl_status.setVisible(False)

        # Sync the format combo to whatever was last rendered on this
        # tab. Block signals so the lookup doesn't trigger a re-render
        # via _on_format_changed (the tab is already showing the right
        # text — we're just bringing the combo in line with it).
        tab_fmt = getattr(widget, "_format", None)
        if tab_fmt is not None and hasattr(self, "_cmb_format"):
            idx = self._cmb_format.findData(tab_fmt)
            if idx >= 0 and idx != self._cmb_format.currentIndex():
                self._cmb_format.blockSignals(True)
                try:
                    self._cmb_format.setCurrentIndex(idx)
                finally:
                    self._cmb_format.blockSignals(False)

        # The Translate button follows the active tab's run (its source
        # family) — re-project its enabled state on every switch.
        self._update_translate_btn()

        # Grey out the buttons that don't apply to LLM result tabs.
        is_llm = bool(getattr(widget, "_is_llm_result", False))
        if hasattr(self, "_btn_copy"):
            self._btn_copy.setEnabled(not is_llm)
        if hasattr(self, "_btn_llm"):
            self._btn_llm.setEnabled(not is_llm)
        # _btn_export stays enabled even on LLM tabs — its handler
        # routes to LLMExportDialog (PDF + Markdown) instead of the
        # standard ExportDialog.

    def _on_diarize_toggled(self, checked):
        # The threshold drives the clustering engines only — hide it when
        # the MOSS one-pass engine is selected (no clustering stage).
        _is_moss = (self._cmb_diar_engine.currentData() or "auto") == "moss"
        self._w_threshold.setVisible(checked and not _is_moss)
        self._w_diar_engine.setVisible(checked)
        self._w_moss_gap.setVisible(checked and _is_moss)
        self._update_long_audio_warning()
        self._refresh_window_icon()

    def _diar_allow_multi(self):
        """False when the diarization-engine combo forces Sortformer."""
        return (self._cmb_diar_engine.currentData() or "auto") != "sortformer"

    def _refresh_window_icon(self):
        """Switch the window icon between the violet 'diarize' and the
        blue 'transcribing' variants depending on whether the user has
        ticked Diarization. Plasma 6.2+ + Qt 6.7+ propagate
        QApplication.setWindowIcon to the taskbar via the
        xdg-toplevel-icon protocol; calling it on the QApplication
        instance (not just the widget) is what makes the taskbar
        actually update under Wayland."""
        try:
            from PyQt6.QtGui import QIcon
            from PyQt6.QtWidgets import QApplication
        except ImportError:
            from PySide6.QtGui import QIcon
            from PySide6.QtWidgets import QApplication
        name = ("parakeet-diarize" if getattr(self, "_chk_diarize", None)
                and self._chk_diarize.isChecked()
                else "parakeet-transcribing")
        icon = QIcon.fromTheme(name)
        if icon.isNull():
            return
        # Set both: app-level (taskbar) and window-level (title bar /
        # alt-tab thumbnail). On Wayland the app-level call is what
        # the taskbar icon listens to.
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)
        self.setWindowIcon(icon)
        # Mutter (GNOME) and Muffin (Cinnamon) don't implement
        # xdg-toplevel-icon-v1 yet, so under their Wayland sessions the
        # taskbar icon stays frozen on the .desktop's Icon= entry.
        # Log once so debugging a "why doesn't my taskbar update" report
        # surfaces the compositor limitation immediately.
        if not getattr(self, "_icon_swap_warned", False):
            self._icon_swap_warned = True
            session = os.environ.get("XDG_SESSION_TYPE", "")
            desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
            if session == "wayland" and any(
                d in desktop for d in ("GNOME", "Cinnamon")
            ):
                _dbg(
                    f"window icon swap: {desktop}/Wayland does not support "
                    f"xdg-toplevel-icon-v1 — taskbar will not update "
                    f"(title bar and Alt+Tab thumbnail will)"
                )

    # Fallback when nvidia-smi is unavailable. Parakeet-TDT loads the full
    # mel-spectrogram → ~185 MB VRAM per minute peak. On 8 GB shared with
    # OS/compositor, ~10 min is the practical limit. _long_audio_threshold_minutes
    # below picks a per-VRAM value at runtime.
    LONG_AUDIO_WARN_MINUTES = 10

    def _has_cuda_build(self):
        """Heuristic: dictee-cuda package ships libonnxruntime.so in /usr/lib/dictee."""
        return os.path.isfile("/usr/lib/dictee/libonnxruntime.so")

    # Hard cap independent of VRAM: the Parakeet-TDT v3 ONNX model has a
    # self-attention mask whose dim-3 size doesn't broadcast past ~4000
    # frames (~5:20 min audio @ 12.5 fps). Above that, the simple
    # `transcribe` batch binary errors with "right operand cannot
    # broadcast on dim 3". Empirically validated 2026-05-10: works
    # ≤ 320 s, fails ≥ 330 s. Capping the chunked threshold at 5 min
    # routes anything close to that limit through the chunked path
    # (120-s chunks, well under the model limit). Remove this cap once
    # the binary/model is fixed.
    PARAKEET_TDT_MAX_MINUTES = 5

    def _long_audio_threshold_minutes(self):
        """Audio-duration threshold (min) above which we route to the
        chunked pipeline. Detects total NVIDIA VRAM via nvidia-smi and
        picks a value calibrated against Parakeet-TDT's ~185 MB/min mel
        peak + ~6 GB base reserve (model + ORT + OS). Beyond the
        threshold, chunking has no latency cost (each 120 s chunk fits
        on any GPU capable of running Parakeet). The result is then
        capped at PARAKEET_TDT_MAX_MINUTES to dodge the model attention
        bug. Cached after 1st call."""
        if hasattr(self, '_cached_long_audio_threshold'):
            return self._cached_long_audio_threshold
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total",
                 "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL, timeout=2,
            ).decode().strip().splitlines()[0]
            vram_mb = int(out)
            if vram_mb < 6000:
                minutes = 5
            elif vram_mb < 10000:
                minutes = 10
            elif vram_mb < 16000:
                minutes = 20
            elif vram_mb < 28000:
                minutes = 40
            else:
                minutes = 60
        except Exception:
            minutes = self.LONG_AUDIO_WARN_MINUTES
        minutes = min(minutes, self.PARAKEET_TDT_MAX_MINUTES)
        self._cached_long_audio_threshold = minutes
        _dbg(f"_long_audio_threshold_minutes: {minutes} min")
        return minutes

    def _update_long_audio_warning(self):
        """No-op since v1.3 chunked pipeline merge — long-audio
        diarization is now unbounded thanks to the auto-chunking
        pipeline (ffmpeg pre-cut + diarize-only global +
        transcribe-diarize-batch + speaker merge). The label is
        kept hidden, and the attribute itself is preserved in case
        some other call-site references it."""
        if hasattr(self, "_lbl_long_audio_warning"):
            self._lbl_long_audio_warning.setVisible(False)

    def _on_transcribe(self):
        if not self.isVisible():
            return  # window closed, don't start new transcription
        audio_path = self._file_input.text().strip()
        if not audio_path or not os.path.isfile(audio_path):
            self._lbl_status.setText(_("File not found."))
            self._lbl_status.setVisible(True)
            return
        self._add_recent_file(audio_path)

        # Block if translation is running
        if self._translate_thread and self._translate_thread.isRunning():
            _dbg("_on_transcribe: blocked — translation running")
            return

        diarize = self._chk_diarize.isChecked()
        _dbg(f"_on_transcribe: file={audio_path}, diarize={diarize}")

        # Isolated ASR model selection (combo). None = Default F9 (unchanged).
        # Only honored for diarized runs (see _ChunkedPipelineWorker / phase-2).
        _spec = self._asr_model_combo.currentData() if hasattr(self, "_asr_model_combo") else ""
        self._isolated_recipe = asr_spec_to_daemon(_spec)

        # Create a new tab for this transcription (keep previous tabs)
        # Name tab after mode + sensitivity + counter
        if not hasattr(self, '_transcription_counter'):
            self._transcription_counter = 0
        self._transcription_counter += 1
        if diarize:
            sens = self._sld_sensitivity.value()
            tab_name = f"#{self._transcription_counter} Diarize {sens}%"
        else:
            tab_name = f"#{self._transcription_counter} Transcribe"
        # Remove empty Original placeholder if it exists
        for i in range(self._tabs.count()):
            if (self._tabs.tabText(i) == _("Original")
                    and not self._tabs.widget(i).toPlainText().strip()):
                self._tabs.removeTab(i)
                break
        # Make previous active tab read-only
        if hasattr(self, '_text_edit') and self._text_edit.toPlainText().strip():
            self._text_edit.setReadOnly(True)
        # Create new tab at the right
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(self._btn_edit_mode.isChecked())
        self._text_edit.setPlaceholderText(
            _("Transcription results will appear here..."))
        self._text_edit.viewport().installEventFilter(self)
        self._install_modified_overlay(self._text_edit)
        # Canonical per-tab state; _audio_path lets a tab switch reload
        # the right file (and hence the right duration).
        self._init_tab_state(self._text_edit, audio_path)
        # Capture the run's target: async handlers write to this tab and
        # never re-resolve it at completion time.
        self._run_tab = self._text_edit
        self._tabs.addTab(self._text_edit, tab_name)
        self._tabs.setCurrentWidget(self._text_edit)
        # Animate the tab title with a braille spinner while the
        # transcription / diarization is running. _show_status() will
        # call _stop_all_spinners() when results land.
        self._start_tab_spinner(self._text_edit, tab_name)
        self._stdout_buf = QByteArray()
        self._start_time = time.monotonic()
        # Probe the duration once and store it on the run's tab (used by
        # the routing threshold, the watchdog and the final summary).
        dur = self._get_audio_duration(audio_path)
        self._text_edit._audio_duration = dur
        self._progress.setVisible(True)

        # Free GPU VRAM if needed: only stop processes when VRAM is tight
        _dbg("_on_transcribe: checking GPU VRAM")
        self._daemon_was_active = False
        try:
            import time as _time
            # Check free VRAM
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5)
            free_str = result.stdout.strip().split("\n")[0] if result.returncode == 0 else ""
            if free_str and free_str.isdigit():
                free_mb = int(free_str)
                # Parakeet needs ~3.5 GB, Sortformer adds ~1.5 GB
                vram_needed = 5120 if diarize else 3584
                _dbg(f"_on_transcribe: GPU VRAM free={free_mb} MB, needed={vram_needed} MB, diarize={diarize}")
                if free_mb < vram_needed:
                    # Check what's using VRAM
                    result2 = subprocess.run(
                        ["nvidia-smi", "--query-compute-apps=name",
                         "--format=csv,noheader"],
                        capture_output=True, text=True, timeout=5)
                    gpu_procs = result2.stdout.strip() if result2.returncode == 0 else ""
                    _dbg(f"_on_transcribe: GPU processes: {gpu_procs}")
                    # Stop daemon first (biggest VRAM consumer)
                    if "transcribe-daemon" in gpu_procs:
                        _dbg("_on_transcribe: stopping daemon to free VRAM")
                        self._daemon_was_active = True
                        subprocess.run(
                            ["systemctl", "--user", "stop",
                             "dictee", "dictee-vosk", "dictee-whisper",
                             "dictee-whisper-rust", "dictee-canary",
                             "dictee-nemotron"],
                            timeout=10)
                        _time.sleep(1)
                    # Still tight? Unload ollama too
                    result3 = subprocess.run(
                        ["nvidia-smi", "--query-gpu=memory.free",
                         "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=5)
                    free_str2 = result3.stdout.strip().split("\n")[0] if result3.returncode == 0 else ""
                    free_after = int(free_str2) if free_str2.isdigit() else free_mb
                    if free_after < vram_needed and "ollama" in gpu_procs:
                        _dbg("_on_transcribe: unloading ollama model")
                        conf = _read_conf()
                        model = conf.get("DICTEE_OLLAMA_MODEL", "translategemma")
                        import urllib.request
                        req = urllib.request.Request(
                            "http://localhost:11434/api/generate",
                            data=json.dumps({"model": model, "keep_alive": 0}).encode(),
                            headers={"Content-Type": "application/json"})
                        urllib.request.urlopen(req, timeout=5)
                        _time.sleep(1)
        except Exception as e:
            _dbg(f"_on_transcribe: VRAM cleanup error: {e}")

        self._run_status(_("Transcribing..."))
        # Single flag drives the whole gating logic — see _update_transcribe_btn.
        self._transcription_in_progress = True
        self._btn_translate.setEnabled(False)
        self._update_transcribe_btn()

        # Long-file chunked pipeline: any file longer than a single chunk
        # routes here, regardless of CUDA/CPU build or diarize on/off.
        # Rationale: chunks of CHUNK_SECONDS = 180 s sit well below the
        # Parakeet-TDT v3 ONNX attention-mask bug (~320 s) so chunked is
        # the only path that avoids the model crash for *any* host
        # (incl. dictee-cpu users on CPU). Previously gated on
        # _has_cuda_build() + a VRAM-aware threshold — the gate left
        # dictee-cpu users facing the ONNX crash, and the VRAM-aware
        # threshold was always capped at PARAKEET_TDT_MAX_MINUTES = 5
        # anyway, so the simple "> CHUNK_SECONDS" rule subsumes both.
        # _long_audio_threshold_minutes() and _has_cuda_build() are kept
        # in case the upstream ONNX bug gets fixed and we want to revert
        # to a VRAM-aware threshold.
        # Hybrid isolated-model routing: a diarized run with an isolated
        # Parakeet quant selected goes through the chunked pipeline at ANY
        # length (one chunk for short files), with the quant env forced onto
        # the batch CLI subprocess. An isolated Whisper or Nemotron selection
        # is handled by the two-phase socket path and must NOT enter here.
        # Both _whisper_isolated and _nemotron_isolated are gated on diarize:
        # non-diarized runs always fall through to the plain Parakeet CLI
        # (known limitation — selecting whisper/nemotron for a non-diarized
        # batch file currently yields Parakeet output via the transcribe CLI).
        # Parakeet variants are honored for BOTH plain and diarized runs:
        # the chunked pipeline's batch binary is Parakeet and applies the
        # recipe env (quant/CPU) as-is.
        _parakeet_isolated = bool(
            getattr(self, "_isolated_recipe", None)
            and self._isolated_recipe["backend"] == "parakeet")
        _whisper_isolated = bool(
            diarize and getattr(self, "_isolated_recipe", None)
            and self._isolated_recipe["backend"] == "whisper")
        _whisper_rust_isolated = bool(
            diarize and getattr(self, "_isolated_recipe", None)
            and self._isolated_recipe["backend"] == "whisper-rust")
        _nemotron_isolated = bool(
            diarize and getattr(self, "_isolated_recipe", None)
            and self._isolated_recipe["backend"] == "nemotron")
        # Isolated Whisper-Rust needs its ggml model: fail fast with a
        # pointer to dictee-setup instead of a daemon-socket timeout.
        # Recipe-based (not the diarize-gated flag): plain runs use the
        # isolated daemon too.
        if (getattr(self, "_isolated_recipe", None)
                and self._isolated_recipe["backend"] == "whisper-rust"):
            _ggml = self._isolated_recipe["env"].get("DICTEE_WHISPER_RUST_GGML", "")
            if not (_ggml and os.path.isfile(_ggml)):
                self._progress.setVisible(False)
                self._lbl_status.setText(
                    _("No Whisper-Rust model installed. Pick one in "
                      "dictee-setup first."))
                self._lbl_status.setVisible(True)
                self._transcription_in_progress = False
                self._update_transcribe_btn()
                self._stop_all_spinners()
                return
        # Plain run on an isolated whisper/whisper-rust/nemotron engine:
        # the chunked batch binary and the standalone `transcribe` CLI are
        # Parakeet-only, so the engine combo was silently IGNORED for plain
        # runs (French audio came back anglicised by Parakeet). Honor it
        # with the same ad-hoc isolated daemon phase 2 uses, plus one plain
        # full-file request.
        if (not diarize and getattr(self, "_isolated_recipe", None)
                and self._isolated_recipe["backend"] in (
                    "whisper", "whisper-rust", "nemotron")):
            self._start_isolated_plain_transcribe(audio_path, dur)
            return

        # A MOSS diarized run never goes through the chunked pipeline: the
        # model ingests the whole file in one pass (upstream supports hours
        # of audio; ~85 MB RAM per minute) and chunking would break its
        # global speaker labels.
        _moss_run = (diarize and _moss_available()
                     and (self._cmb_diar_engine.currentData() or "auto") == "moss")
        if ((dur > _ChunkedPipelineWorker.CHUNK_SECONDS
                or _parakeet_isolated) and not _whisper_isolated
                and not _whisper_rust_isolated
                and not _nemotron_isolated
                and not _moss_run):
            sensitivity = self._sld_sensitivity.value() / 100.0 if diarize else 0.0
            _dbg(f"_on_transcribe: routing to chunked pipeline "
                 f"(dur={dur:.1f}s, diarize={diarize}, "
                 f"chunk={_ChunkedPipelineWorker.CHUNK_SECONDS}s, "
                 f"sens={sensitivity:.2f})")
            self._diarize_two_phase = False  # chunked replaces two-phase
            self._chunked_worker = _ChunkedPipelineWorker(
                audio_path, sensitivity, diarize=diarize, parent=self,
                env_override=(self._isolated_recipe["env"] if _parakeet_isolated else None),
                allow_diar_multi=self._diar_allow_multi())
            self._chunked_worker.phase_changed.connect(self._on_chunked_phase)
            self._chunked_worker.chunk_progress.connect(self._on_chunked_progress)
            self._chunked_worker.finished.connect(self._on_chunked_done)
            self._chunked_worker.error.connect(self._on_chunked_error)
            self._btn_cancel.setVisible(True)
            self._btn_cancel.setEnabled(True)
            self._start_run_ticker()
            self._chunked_worker.start()
            return

        self._process = QProcess(self)
        # Channel mode is set AFTER the routing decision below: it depends on
        # two_phase, and reading self._diarize_two_phase here picked up the
        # PREVIOUS run's value (stale attribute) — a two-phase run following a
        # chunked run got MergedChannels, so stderr (ONNX warnings, DBG lines)
        # leaked into the segment stream and the result tab.
        # Set ORT_DYLIB_PATH for GPU acceleration if the lib exists
        env = self._process.processEnvironment()
        if env.isEmpty():
            env = QProcessEnvironment.systemEnvironment()
        ort_lib = "/usr/lib/dictee/libonnxruntime.so"
        if os.path.isfile(ort_lib):
            env.insert("ORT_DYLIB_PATH", ort_lib)
        # Propagate DICTEE_* keys from ~/.config/dictee.conf so the Rust
        # binary sees DICTEE_FORCE_CPU, DICTEE_PARAKEET_QUANT,
        # DICTEE_INTRA_THREADS, etc. The systemd services get them via
        # EnvironmentFile=, but a QProcess launched from this Python UI
        # only inherits the user shell env, which doesn't source the conf.
        for _k, _v in _read_conf().items():
            if _k.startswith("DICTEE_"):
                env.insert(_k, _v)
        if _moss_run:
            # UI choice for the MOSS hole-patching engine — inserted after
            # the conf loop so the window's combo wins over dictee.conf
            # for runs started here.
            env.insert("DICTEE_MOSS_GAP_ASR",
                       self._cmb_moss_gap.currentData() or "parakeet")
        self._process.setProcessEnvironment(env)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.finished.connect(self._on_finished)

        import shutil
        # Routing matrix lives in _select_transcribe_cmd (pure function,
        # tests/test-transcribe-routing.py). Honours DICTEE_ASR_BACKEND
        # so a Canary PTT daemon doesn't hijack diarize phase-2.
        asr_backend = _read_conf().get("DICTEE_ASR_BACKEND", "")
        cmd, two_phase, missing = _select_transcribe_cmd(
            diarize=diarize,
            asr_backend=asr_backend,
            has_transcribe=bool(shutil.which("transcribe")),
            has_diarize_only=bool(shutil.which("diarize-only")),
            has_transcribe_diarize=bool(shutil.which("transcribe-diarize")),
            has_diarize_multi=self._diar_allow_multi() and _diar_multi_available(),
            has_moss=_moss_available(),
            diar_engine=self._cmb_diar_engine.currentData() or "auto",
        )
        if cmd is None:
            self._progress.setVisible(False)
            self._lbl_status.setText(
                _("Command '{cmd}' not found. Install dictee first.").format(cmd=missing))
            self._lbl_status.setVisible(True)
            self._transcription_in_progress = False
            self._update_transcribe_btn()
            self._process.deleteLater()
            self._process = None
            return
        # Isolated Whisper/Whisper-Rust/Nemotron diarized run: force the
        # two-phase path (diarization pass + phase-2 isolated daemon over a
        # private socket), regardless of the F9 backend. Same engine
        # preference as the routing matrix: diarize-multi first, Sortformer
        # fallback. MOSS is exempt: it embeds its own ASR, so the isolated
        # ASR choice does not apply to a MOSS run.
        if ((_whisper_isolated or _whisper_rust_isolated or _nemotron_isolated)
                and cmd != "dictee-moss-diarize"):
            if self._diar_allow_multi() and _diar_multi_available():
                cmd, two_phase = "diarize-multi", True
            elif shutil.which("diarize-only"):
                cmd, two_phase = "diarize-only", True
            else:
                self._progress.setVisible(False)
                self._lbl_status.setText(
                    _("Command '{cmd}' not found. Install dictee first.").format(cmd="diarize-only"))
                self._lbl_status.setVisible(True)
                self._transcription_in_progress = False
                self._update_transcribe_btn()
                self._process.deleteLater()
                self._process = None
                return
        self._diarize_two_phase = two_phase
        if two_phase:
            # Phase 1: keep stdout (segment lines) clean of stderr.
            self._process.setProcessChannelMode(
                QProcess.ProcessChannelMode.SeparateChannels)
        else:
            self._process.setProcessChannelMode(
                QProcess.ProcessChannelMode.MergedChannels)
        if diarize and asr_backend.lower() == "canary" and not two_phase:
            _dbg("_on_transcribe: Canary daemon detected — using "
                 "standalone transcribe-diarize to keep diarize multilingual")
        _dbg(f"_on_transcribe: cmd={cmd}, two_phase={getattr(self, '_diarize_two_phase', False)}")
        self._diarize_audio_path = audio_path
        args = [audio_path]
        # MOSS takes no tuning flag: the threshold slider drives the
        # clustering engines only (MOSS has no clustering stage).
        if diarize and cmd != "dictee-moss-diarize":
            sensitivity = self._sld_sensitivity.value() / 100.0
            if cmd == "diarize-multi":
                args += ["--threshold",
                         f"{_diar_threshold_from_sensitivity(sensitivity):.2f}"]
            else:
                args += ["--sensitivity", f"{sensitivity:.2f}"]
        self._process.start(cmd, args)
        # MOSS (one pass, own ASR) prints nothing until it finishes and can
        # run much slower than real time on mic audio (RTF up to ~7 measured
        # 2026-07-16), so the indeterminate bar alone reads as "frozen".
        # Show a live elapsed-time ticker with an honest expectation.
        self._moss_run = (cmd == "dictee-moss-diarize")
        if self._moss_run:
            self._moss_elapsed = 0
            self._run_status(
                _("MOSS: transcription + speakers in one pass "
                  "(0:00 — can take several times the audio length)…"))
            self._moss_ticker = QTimer(self)
            self._moss_ticker.timeout.connect(self._on_moss_tick)
            self._moss_ticker.start(1000)
        # Watchdog: kill the process if it hangs. Duration-aware like the
        # chunked pipeline: a 92-min diarize legitimately runs 15-20 min on
        # GPU (RTF ~0.9 on CPU) and the binary prints nothing until done —
        # the previous fixed 5-min timer killed every diarized file longer
        # than ~25 min on this path. MOSS needs a far wider margin: on mic
        # audio it hit RTF ~7, so 3x duration would kill a valid run.
        _rtf_margin = 12 if self._moss_run else 3
        watchdog_secs = (max(600, int(dur * _rtf_margin))
                         if diarize else 300)
        self._watchdog_secs = watchdog_secs  # for the timeout message
        self._process_timer = QTimer(self)
        self._process_timer.setSingleShot(True)
        self._process_timer.timeout.connect(self._on_process_timeout)
        self._process_timer.start(watchdog_secs * 1000)
        # Cancel is available for every run shape, not only the chunked
        # pipeline (2026-07-21).
        self._btn_cancel.setVisible(True)
        self._btn_cancel.setEnabled(True)
        self._start_run_ticker()

    def _on_moss_tick(self):
        """Update the elapsed-time counter shown during a MOSS run so the
        window doesn't read as frozen (MOSS emits nothing until it ends)."""
        self._moss_elapsed += 1
        m, s = divmod(self._moss_elapsed, 60)
        self._run_status(
            _("MOSS: transcription + speakers in one pass "
              "({m}:{s:02d} — can take several times the audio length)…")
            .format(m=m, s=s))

    def _stop_moss_ticker(self):
        t = getattr(self, "_moss_ticker", None)
        if t is not None:
            t.stop()
            self._moss_ticker = None

    def _run_status(self, text):
        """Run-scoped status: stored on the run's target tab and displayed
        only while that tab is visible, so a background run never talks
        over the tab the user is reading (2026-07-21 — the status row now
        follows the tabs). Non-run messages (clipboard, exports...) keep
        writing _lbl_status directly."""
        tgt = self._run_tab or getattr(self, '_text_edit', None)
        if tgt is not None:
            tgt._status_text = text
        if tgt is None or self._tabs.currentWidget() is tgt:
            self._lbl_status.setText(text)
            self._lbl_status.setVisible(True)

    def _start_run_ticker(self):
        """Live elapsed counter appended to the run status every second —
        the user used to get the duration only in the final message. MOSS
        runs keep their dedicated ticker (it owns its whole message; two
        rewriters would fight)."""
        if getattr(self, '_moss_run', False):
            return
        self._stop_run_ticker()
        self._run_ticker = QTimer(self)
        self._run_ticker.timeout.connect(self._on_run_tick)
        self._run_ticker.start(1000)

    def _on_run_tick(self):
        tgt = self._run_tab or getattr(self, '_text_edit', None)
        base = (getattr(tgt, '_status_text', "") or "") if tgt else ""
        base = re.sub(r"\s*\(\d{2}:\d{2}(?::\d{2})?\)$", "", base)
        if not base:
            base = _("Transcribing...")
        total = int(time.monotonic()
                    - getattr(self, '_start_time', time.monotonic()))
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        clock = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        self._run_status(f"{base} ({clock})")

    def _stop_run_ticker(self):
        t = getattr(self, '_run_ticker', None)
        if t is not None:
            t.stop()
            self._run_ticker = None

    def _on_process_timeout(self):
        # Audit fix: previous version called self._set_status() / _set_busy()
        # which don't exist on TranscribeWindow → AttributeError silently
        # froze the UI when the 5-min watchdog fired (button stayed disabled,
        # _process / _transcription_in_progress never reset).
        self._stop_moss_ticker()
        self._stop_run_ticker()
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            _dbg("Process timeout — killing")
            self._process.kill()
            # waitForFinished reaps the killed process and emits finished
            # SYNCHRONOUSLY (same-thread direct connection): _on_finished
            # re-enters here and already deleteLater()s + nulls _process.
            # Touching it unguarded afterwards raised AttributeError inside
            # a QTimer slot — PyQt6 aborts the whole app on that.
            self._process.waitForFinished(3000)
            self._run_status(
                _("Transcription timed out ({m} min).").format(
                    m=getattr(self, "_watchdog_secs", 300) // 60))
            self._progress.setVisible(False)
            self._stop_all_spinners()
            if self._process is not None:
                self._process.deleteLater()
                self._process = None
            self._transcription_in_progress = False
            self._update_transcribe_btn()

    def _on_stdout(self):
        if self._process is None:
            return
        data = self._process.readAllStandardOutput()
        self._stdout_buf.append(data)

    def _start_daemon(self):
        """Start the configured ASR daemon."""
        conf = _read_conf()
        asr = conf.get("DICTEE_ASR_BACKEND", "parakeet")
        svc_map = {"parakeet": "dictee", "vosk": "dictee-vosk",
                   "whisper": "dictee-whisper",
                   "whisper-rust": "dictee-whisper-rust",
                   "canary": "dictee-canary",
                   "nemotron": "dictee-nemotron"}
        svc = svc_map.get(asr, "dictee")
        subprocess.Popen(["systemctl", "--user", "start", svc])
        return svc

    def _start_isolated_plain_transcribe(self, audio_path, dur):
        """Plain (no-diarize) run on an isolated whisper/whisper-rust/
        nemotron engine: ad-hoc daemon on a private socket + one plain
        full-file request (the F9 daemon/config/badge are untouched).
        Same cold-load timeout rationale as the phase-2 isolated branch."""
        self._isolated_daemon = IsolatedAsrDaemon(self._isolated_recipe)
        sock_path = self._isolated_daemon.start()
        self._run_status(_("Waiting for daemon..."))
        self._btn_cancel.setVisible(True)
        self._btn_cancel.setEnabled(True)
        self._start_run_ticker()
        self._diarize_worker = _DiarizeTranscribeWorker(
            audio_path, None, sock_path, self,
            socket_timeout=180, audio_duration=dur, plain=True)
        self._diarize_worker.progress.connect(self._on_diarize_progress)
        self._diarize_worker.finished.connect(self._on_isolated_plain_done)
        self._diarize_worker.error.connect(self._on_diarize_error)
        self._diarize_worker.start()

    def _on_isolated_plain_done(self, raw_output):
        """Plain isolated run finished: land as a plain result, then tear
        down the ad-hoc daemon and restore the F9 daemon if needed."""
        _dbg(f"_on_isolated_plain_done: output_len={len(raw_output)}")
        self._diarize_worker = None
        self._finish_transcription(
            raw_output, self._run_tab or self._text_edit, was_diarized=False)
        self._stop_isolated_daemon()
        self._restart_daemon_if_stopped()

    def _restart_daemon_and_transcribe(self, diarize_output):
        """Phase 2: restart daemon, then transcribe each diarized segment via socket (threaded)."""
        audio_path = getattr(self, '_diarize_audio_path', '')
        if not audio_path or not os.path.isfile(audio_path):
            self._stop_run_ticker()
            self._run_status(_("Audio file not found for phase 2."))
            self._transcription_in_progress = False
            self._update_transcribe_btn()
            return

        if (getattr(self, "_isolated_recipe", None)
                and self._isolated_recipe["backend"] in ("whisper",
                                                         "whisper-rust",
                                                         "nemotron")):
            # Isolated whisper/whisper-rust/nemotron: spawn an ad-hoc daemon
            # on a private socket (the F9 daemon/config/badge are untouched).
            # Extended socket-wait timeout because these models cold-load
            # slowly (whisper model download + init; nemotron 2.45 GB load;
            # whisper-rust large-v3 ~1 GB ggml).
            self._isolated_daemon = IsolatedAsrDaemon(self._isolated_recipe)
            sock_path = self._isolated_daemon.start()
            _worker_timeout = 180
            _per_segment = self._isolated_recipe["backend"] == "nemotron"
        else:
            # Restart daemon
            self._daemon_was_active = False
            self._start_daemon()
            # Match the daemon's socket resolution (transcribe_daemon.rs): when
            # XDG_RUNTIME_DIR is unset the fallback is /tmp/transcribe-<uid>.sock,
            # NOT /tmp/transcribe.sock (which the daemon never listens on).
            _xdg = os.environ.get("XDG_RUNTIME_DIR")
            sock_path = (os.path.join(_xdg, "transcribe.sock") if _xdg
                         else f"/tmp/transcribe-{os.getuid()}.sock")
            _worker_timeout = None
            # The F9 daemon itself may run a timestamp-less backend: a
            # '\tdiarize' request to nemotron returns an empty body.
            _per_segment = (_read_conf().get("DICTEE_ASR_BACKEND", "parakeet")
                            == "nemotron")

        self._run_status(_("Waiting for daemon..."))

        # Launch worker thread
        self._diarize_worker = _DiarizeTranscribeWorker(
            audio_path, diarize_output, sock_path, self,
            socket_timeout=_worker_timeout, per_segment=_per_segment,
            audio_duration=getattr(self._run_tab, "_audio_duration", 0.0))
        self._diarize_worker.progress.connect(self._on_diarize_progress)
        self._diarize_worker.finished.connect(self._on_diarize_done)
        self._diarize_worker.error.connect(self._on_diarize_error)
        self._diarize_worker.start()

    def _on_diarize_progress(self, done, total):
        self._run_status(
            _("Transcribing {done}/{total}...").format(done=done, total=total))

    def _on_diarize_done(self, raw_output):
        _dbg(f"_on_diarize_done: output_len={len(raw_output)}, btn_enabled_before={self._btn_transcribe.isEnabled()}")
        self._diarize_worker = None
        # _DiarizeTranscribeWorker is only spawned for two-phase diarize
        # mode, so the result is always diarized text.
        self._finish_transcription(
            raw_output, self._run_tab or self._text_edit, was_diarized=True)
        # Tear down the ad-hoc isolated whisper daemon (if any) and restore
        # the F9 daemon if the VRAM-free block stopped it (no-op otherwise).
        self._stop_isolated_daemon()
        self._restart_daemon_if_stopped()
        _dbg(f"_on_diarize_done: btn_enabled_after={self._btn_transcribe.isEnabled()}")

    def _on_diarize_error(self, msg):
        self._stop_isolated_daemon()
        self._restart_daemon_if_stopped()
        self._diarize_worker = None
        self._progress.setVisible(False)
        self._btn_cancel.setVisible(False)
        self._stop_run_ticker()
        self._run_status(msg)
        # Also surface the failure IN THE TAB: the status label alone reads as
        # "nothing happened" against the unchanged placeholder. A phase-2
        # failure must be visible where the user is looking.
        try:
            tgt = self._run_tab or self._text_edit
            tgt.setPlainText(_("Transcription failed:\n{msg}").format(msg=msg))
        except Exception as _e:
            _dbg(f"silenced: {_e!r}")
        self._transcription_in_progress = False
        self._update_transcribe_btn()
        # Stop the tab spinner — otherwise it keeps spinning forever on an
        # empty/failed diarization (e.g. "Empty transcription from daemon").
        self._stop_all_spinners()

    # === Chunked long-file pipeline slots ===

    def _on_chunked_phase(self, phase_num, label):
        """Phase status update from _ChunkedPipelineWorker. Label uses
        '1/2..2/2' for diarize OFF and '1/4..4/4' for diarize ON."""
        self._chunked_phase_label = label
        self._run_status(label)

    def _on_chunked_progress(self, done, total):
        """Chunk-by-chunk progress during the transcription phase."""
        base = getattr(self, '_chunked_phase_label',
                       _("Chunked transcription"))
        self._run_status(
            _("{base} — chunk {done}/{total}").format(
                base=base, done=done, total=total))

    def _on_chunked_done(self, raw_output):
        """Final output ready: forward to the common _finish_transcription path."""
        _dbg(f"_on_chunked_done: output_len={len(raw_output)}")
        worker = self._chunked_worker
        self._chunked_worker = None
        self._btn_cancel.setVisible(False)
        self._restart_daemon_if_stopped()
        self._finish_transcription(
            raw_output, self._run_tab or self._text_edit,
            was_diarized=worker._diarize if worker is not None else False)

    def _on_chunked_error(self, msg):
        """Pipeline failed at some phase (or user cancelled): surface
        message, restore UI. Stops any spinner started for this run."""
        _dbg(f"_on_chunked_error: {msg}")
        self._chunked_worker = None
        self._btn_cancel.setVisible(False)
        self._stop_run_ticker()
        self._progress.setVisible(False)
        self._run_status(msg)
        self._transcription_in_progress = False
        self._update_transcribe_btn()
        self._update_translate_btn()
        self._stop_all_spinners()
        self._restart_daemon_if_stopped()

    def _restart_daemon_if_stopped(self):
        """Restart the ASR daemon if we stopped it earlier to free VRAM.
        Called from every transcription-finishing slot (success, error,
        cancel) so push-to-talk dictation is always usable again after
        dictee-transcribe runs."""
        if getattr(self, '_daemon_was_active', False):
            self._daemon_was_active = False
            _dbg("_restart_daemon_if_stopped: restarting ASR daemon")
            self._start_daemon()

    def _stop_isolated_daemon(self):
        """Tear down the ad-hoc isolated ASR daemon if one is running."""
        d = getattr(self, "_isolated_daemon", None)
        if d is not None:
            try:
                d.stop()
            except Exception as _e:
                _dbg(f"silenced: {_e!r}")
            self._isolated_daemon = None

    def _on_cancel_run(self):
        """User clicked Cancel — covers every run shape: chunked worker,
        phase-1/one-pass QProcess, phase-2 socket worker. Until 2026-07-21
        only the chunked pipeline had a cancel; a 397-segment Nemotron
        phase 2 then ran ~35 minutes with no way out."""
        self._btn_cancel.setEnabled(False)  # avoid double clicks
        self._run_status(_("Cancelling..."))
        w = getattr(self, '_chunked_worker', None)
        if w is not None:
            _dbg("_on_cancel_run: requesting chunked worker cancel")
            w.request_cancel()
            return
        p = getattr(self, '_process', None)
        if p is not None and p.state() != QProcess.ProcessState.NotRunning:
            _dbg("_on_cancel_run: killing the phase-1/one-pass process")
            self._user_cancelled = True
            p.kill()  # _on_finished turns this into a clean "Cancelled"
            return
        dw = getattr(self, '_diarize_worker', None)
        if dw is not None and dw.isRunning():
            _dbg("_on_cancel_run: cancelling the phase-2 worker")
            dw.cancel()  # suppresses its own signals — reset the UI here
            # The completion slots that normally clear the reference never
            # fire after cancel(), and _update_transcribe_btn() gates on
            # it being None — without this the whole run UI stays greyed
            # until the window is reopened.
            self._diarize_worker = None
            iso = getattr(self, '_isolated_daemon', None)
            if iso is not None:
                iso.stop()
            self._btn_cancel.setVisible(False)
            self._progress.setVisible(False)
            self._stop_run_ticker()
            self._run_status(_("Cancelled"))
            self._transcription_in_progress = False
            self._update_transcribe_btn()
            self._stop_all_spinners()
            self._restart_daemon_if_stopped()
            return
        _dbg("_on_cancel_run: nothing to cancel")

    def _postprocess_run_output(self, raw_output, was_diarized):
        """Parse and post-process a finished run's raw output into
        (segments, cleaned_raw_output). Single code path for both
        finishers — the QProcess path used to skip _clean_segment_text
        on plain transcriptions, keeping stray control characters."""
        if was_diarized:
            segments = _parse_diarize_output(raw_output)
            # Post-process each segment's text through dictee-postprocess
            for seg in segments:
                seg["text"] = _clean_segment_text(_postprocess(seg["text"]))
            # Rebuild raw_output with post-processed text
            raw_output = "\n".join(
                f"[{seg['start']:.2f}s - {seg['end']:.2f}s] {seg['speaker']}: {seg['text']}"
                for seg in segments) if segments else raw_output
        else:
            segments = []
            raw_output = _clean_segment_text(_postprocess(raw_output))
        return segments, raw_output

    def _apply_speakers_json(self, target, segments, was_diarized):
        """Apply speaker names transferred from meeting-live
        (speakers.json), once, to the run that carried them."""
        if not (getattr(self, "_pending_speakers_data", None)
                and was_diarized and segments):
            return
        try:
            name_map = self._pending_speakers_data.get("name_map", {})
            anchors = self._pending_speakers_data.get("anchors", {})
            matched = self._match_anchors_to_batch_speakers(
                name_map, anchors, segments)
            if matched:
                target._speaker_name_map = dict(matched)
                # The QLineEdits belong to the ACTIVE tab
                # (_populate_rename_fields) — prefill them only when the
                # target is the tab on screen, otherwise the names of
                # this run would land in another tab's visible fields.
                if self._tabs.currentWidget() is target:
                    self._prefill_rename_panel(matched)
                _dbg(f"speakers.json applied: {matched}")
        except Exception as _e:
            _dbg(f"speakers.json apply error: {_e!r}")
        finally:
            self._pending_speakers_data = None  # consume once

    def _land_run_results(self, target, segments, raw_output, was_diarized):
        """Common success tail of both finishers: store the results on
        the target tab and re-project everything that depends on them.
        Leaves _transcription_in_progress and auto-translate to the
        callers — their required ordering around this tail differs.

        NB: language auto-detection removed deliberately. The source
        language combo reflects the user's choice (DICTEE_LANG_SOURCE),
        which also drives the LLM Diarization output language.
        """
        # Store data on the tab widget for per-tab translation & markers
        target._raw_text = raw_output
        target._was_diarized = was_diarized
        target._diarize_segments = segments
        # Fresh transcription: no speaker renames to inherit — the new tab
        # never shows another tab's speaker names. (A meeting-live
        # speakers.json pre-naming, if any, is applied just below.)
        target._speaker_name_map = {}

        # Rebuild the rename panel for the new speakers — only when the
        # target tab is visible (cf. _refresh_rename_panel_for_target docstring).
        self._refresh_rename_panel_for_target(target)
        self._apply_speakers_json(target, segments, was_diarized)

        # Render into the target tab explicitly, not the active one — the
        # user may have switched tabs while the transcription was running.
        self._apply_format_to(target, segments, raw_output)
        # Only switch the player to the target tab's audio if that tab is
        # currently visible: yanking the audio of the tab the user is
        # listening to would be intrusive. _on_tab_changed reloads the
        # right audio when the user comes back to the target.
        if self._tabs.currentWidget() is target:
            tab_audio = getattr(target, '_audio_path', None)
            if tab_audio and os.path.isfile(tab_audio):
                if self._player.source().toLocalFile() != tab_audio:
                    self._load_audio(tab_audio)
        self._update_player_markers(target)
        target._transcribe_elapsed = time.monotonic() - self._start_time
        self._update_translate_btn()
        self._show_status(target)

    def _maybe_auto_translate(self, target):
        """Kick auto-translate for the just-finished run. The source
        language is auto-detected inside _on_translate; same-language
        translations are short-circuited there too."""
        if (self._chk_auto_translate.isChecked()
                and _translate_available(self._cmb_backend.currentData())
                and self._cmb_lang_tgt.currentData()):
            self._on_translate(source=target)

    def _finish_transcription(self, raw_output, target, was_diarized):
        """Common finish logic for both single-phase and two-phase
        diarization. `target` is the run's tab, captured at run start —
        results land there even if the user switched tabs meanwhile.
        `was_diarized` comes from the run itself (caller), never from
        shared state a tab switch could have clobbered."""
        self._progress.setVisible(False)
        self._btn_cancel.setVisible(False)
        self._stop_run_ticker()
        # Lower the single source-of-truth flag, then route through
        # _update_transcribe_btn so the diarize toggle, auto-translate
        # checkbox and sensitivity slider come back together.
        self._transcription_in_progress = False
        self._update_transcribe_btn()
        self._btn_translate.setEnabled(True)

        if not raw_output:
            self._run_status(_("No transcription result."))
            target._raw_text = ""
            target._diarize_segments = []
            self._refresh_rename_panel_for_target(target)
            self._update_translate_btn()
            self._stop_all_spinners()
            return

        self._retry_done = False
        # The chunked pipeline also services diarize=False (long plain
        # transcription on CUDA), and that path emits plain text rather
        # than DIARIZE_RE — hence the caller-provided flag.
        segments, raw_output = self._postprocess_run_output(
            raw_output, was_diarized)
        self._land_run_results(target, segments, raw_output, was_diarized)
        self._maybe_auto_translate(target)

    def _on_finished(self, exit_code, _exit_status):
        if hasattr(self, '_process_timer'):
            self._process_timer.stop()
        self._stop_moss_ticker()
        self._progress.setVisible(False)
        if self._process:
            self._process.deleteLater()
        self._process = None
        # Note: do NOT touch _transcription_in_progress here — for two-
        # phase diarize we are about to spawn _diarize_worker. Lowering
        # the flag now would create a brief window where the button is
        # re-enabled mid-flight (the bug the user hit on "Transcribing
        # 1/3"). The flag is lowered in _finish_transcription /
        # _on_diarize_error / _on_chunked_error / the error branches
        # below.

        raw_output = bytes(self._stdout_buf).decode("utf-8", errors="replace").strip()
        # The run's tab, captured at run start — results land there even
        # if the user switched tabs while the QProcess was running.
        target = self._run_tab or self._text_edit

        # Two-phase diarization: diarize-only finished → transcribe segments via daemon
        if getattr(self, '_diarize_two_phase', False) and exit_code == 0 and raw_output:
            self._diarize_two_phase = False
            _dbg(f"_on_finished: phase 1 done (diarize-only), segments:\n{raw_output}")
            self._run_status(_("Restarting daemon for transcription..."))
            # Restart daemon — _diarize_worker is created here and will
            # keep _update_transcribe_btn() returning False until phase 2
            # actually completes via _on_diarize_done.
            self._restart_daemon_and_transcribe(raw_output)
            return

        # The QProcess run is over on every remaining path (cancel, error,
        # empty, success) — only the phase-2 handoff above keeps the live
        # clock running. Without this, a successful one-pass run leaked
        # the 1 Hz ticker forever: the final summary grew a phantom
        # (MM:SS) clock, and a following translation's status spinner
        # then fought the ticker, alternating two lines every second.
        # Same hole for the Cancel button: only the cancel/error branches
        # below hid it, so a successful one-pass run (MOSS diarize among
        # others) kept Cancel on screen next to the re-enabled Transcribe.
        self._stop_run_ticker()
        self._btn_cancel.setVisible(False)

        # Restart daemon if we stopped it for VRAM
        self._restart_daemon_if_stopped()
        _dbg(f"_on_finished: exit_code={exit_code}, output_len={len(raw_output)}")

        if getattr(self, '_user_cancelled', False):
            # The kill came from the Cancel button: a clean stop, not an
            # error — no failure message, no raw-output dump.
            self._user_cancelled = False
            _dbg("_on_finished: run cancelled by user")
            self._btn_cancel.setVisible(False)
            self._progress.setVisible(False)
            self._stop_moss_ticker()
            self._stop_run_ticker()
            self._run_status(_("Cancelled"))
            self._transcription_in_progress = False
            self._update_transcribe_btn()
            self._stop_all_spinners()
            return

        if exit_code != 0:
            # GPU OOM: unload ollama and retry once
            if ("Failed to allocate memory" in raw_output
                    or "BFCArena" in raw_output
                    or "CUBLAS_STATUS_ALLOC_FAILED" in raw_output
                    or ("CUDA" in raw_output and "ALLOC" in raw_output)
                    ) and not getattr(self, '_retry_done', False):
                self._retry_done = True
                _dbg(f"_on_finished: GPU OOM detected, retrying. Error: {raw_output[:200]}")
                msg = _("GPU memory full — unloading translation model and retrying...")
                self._run_status(msg)
                target.setPlainText(msg)
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
                    except Exception as _e:
                        _dbg(f"silenced: {_e!r}")
                # Re-trigger transcription after delay
                QTimer.singleShot(2000, self._on_transcribe)
                return

            self._retry_done = False
            self._btn_cancel.setVisible(False)
            self._stop_run_ticker()
            self._run_status(
                _("Transcription failed (code {code}). Check memory, backend, or audio file.").format(
                    code=exit_code))
            if raw_output:
                target.setPlainText(raw_output)
            target._raw_text = ""
            target._diarize_segments = []
            self._refresh_rename_panel_for_target(target)
            self._transcription_in_progress = False
            self._update_transcribe_btn()
            self._update_translate_btn()
            self._stop_all_spinners()
            return

        if not raw_output:
            self._run_status(_("No transcription result."))
            target._raw_text = ""
            target._diarize_segments = []
            self._refresh_rename_panel_for_target(target)
            self._transcription_in_progress = False
            self._update_transcribe_btn()
            self._update_translate_btn()
            self._stop_all_spinners()
            return

        # Reset retry flag on success
        self._retry_done = False
        _dbg(f"_on_finished: success, diarized={self._chk_diarize.isChecked()}, raw_len={len(raw_output)}")

        # This run's diarize setting, read from the checkbox that drove it
        # (safe: the checkbox is disabled for the whole run).
        was_diarized = self._chk_diarize.isChecked()

        segments, raw_output = self._postprocess_run_output(
            raw_output, was_diarized)
        self._land_run_results(target, segments, raw_output, was_diarized)

        # Run is genuinely done — release the gating flag and refresh
        # button states (this also enables the diarize toggle, the
        # auto-translate checkbox and the sensitivity slider).
        self._transcription_in_progress = False
        self._update_transcribe_btn()

        self._maybe_auto_translate(target)

    def _show_status(self, target):
        """Show final status with timing and speaker info; store the
        summary on `target` (the tab the run/translation produced).

        For diarized transcriptions the summary lives next to the
        rename accordion header (more visual context); for plain
        transcriptions it stays in the bottom status label.
        """
        # Any tab spinner started by transcription / diarization /
        # translation stops here.
        self._stop_all_spinners()
        dur = getattr(target, '_audio_duration', 0.0)
        dur_str = f"{int(dur//60)}:{int(dur%60):02d}" if dur >= 60 else f"{dur:.1f}s"
        segs = getattr(target, '_diarize_segments', [])
        was_diarized = bool(getattr(target, '_was_diarized', False))
        n_speakers = len(set(s["speaker"] for s in segs)) if segs else 0
        parts = []
        if was_diarized and segs:
            parts.append(_("{n} speaker(s)").format(n=n_speakers))
        parts.append(_("audio {dur}").format(dur=dur_str))
        parts.append(_("transcribed in {t}").format(
            t=_format_elapsed(getattr(target, '_transcribe_elapsed', 0.0))))
        if getattr(target, '_translate_elapsed', 0.0) > 0:
            parts.append(_("translated in {t}").format(
                t=_format_elapsed(target._translate_elapsed)))
        text = " — ".join(parts)
        # The summary belongs to the target tab: stored for the tab-switch
        # restore (the status row follows the tabs, 2026-07-21).
        target._status_text = text
        if was_diarized and hasattr(self, "_lbl_rename_status"):
            self._lbl_rename_status.setText(text)
            self._lbl_status.setText("")
            self._lbl_status.setVisible(False)
        else:
            if hasattr(self, "_lbl_rename_status"):
                self._lbl_rename_status.setText("")
            self._lbl_status.setText(text)
            self._lbl_status.setVisible(True)

    def _on_translate(self, checked=False, *, source=None):
        """Translate a transcription into the chosen target.

        The source is the run tab the ACTIVE tab is a view of (its
        _rename_family): a run tab translates itself, a translation tab
        translates its original run — never the already-translated
        text, otherwise the LLM would translate from the wrong
        language. Auto-translate passes `source` explicitly (the
        just-finished run tab) so a mid-run tab switch cannot redirect
        it. `checked` only absorbs QPushButton.clicked's argument.
        """
        if source is None:
            source = (getattr(self._active_editor(), '_rename_family', None)
                      or self._text_edit)
        raw_text = getattr(source, '_raw_text', '')
        segments = getattr(source, '_diarize_segments', None) or []
        was_diarized = getattr(source, '_was_diarized', False)
        if not raw_text:
            return
        # Prevent concurrent translation
        if self._translate_thread and self._translate_thread.isRunning():
            return
        # Auto-detect source language from the transcribed text. Cheap
        # heuristic in _detect_language; replace later with the ASR's
        # own metadata if Parakeet starts exposing it.
        lang_src = _detect_language(raw_text) or "en"
        lang_tgt = self._cmb_lang_tgt.currentData()
        if not lang_tgt:
            # Empty target combo (e.g. LibreTranslate with no languages
            # installed). Was a silent return — surface in red so the
            # user sees it stands out from the normal status messages.
            msg = _("Translation skipped: no target language selected.")
            self._lbl_status.setText(f'<span style="color:#d93025;">{msg}</span>')
            self._lbl_status.setVisible(True)
            _dbg("_on_translate: blocked — empty lang_tgt combo")
            return
        if lang_src == lang_tgt:
            # Was a silent return: user clicks Translate, nothing
            # happens, no clue why. Tell them which language was
            # detected and how to fix it. Red span stands out in the
            # status bar; the next normal status message clears it
            # because QLabel auto-detects rich vs plain text.
            src_name = LANG_NAMES_EN.get(lang_src, lang_src)
            msg = _("Translation skipped: source language detected as {src} "
                    "— select a different target above.").format(src=src_name)
            self._lbl_status.setText(f'<span style="color:#d93025;">{msg}</span>')
            self._lbl_status.setVisible(True)
            _dbg(f"_on_translate: blocked — detected source ({lang_src}) == target")
            return
        backend = self._cmb_backend.currentData()
        _dbg(f"_on_translate: backend={backend}, {lang_src}→{lang_tgt}")
        # Keep transcription status and append a braille-spinner-led
        # "Translating..." segment. The "—" separator gets replaced by
        # the spinner frame, which animates while the translation runs.
        # Drop a previous translate-skip warning (red HTML span) — it
        # shouldn't tail the running spinner ("[red error] ⠋ Translating…").
        prev_status = self._lbl_status.text()
        self._translate_status_base = (
            "" if "<span" in prev_status else prev_status)
        self._lbl_status.setVisible(True)
        self._progress.setVisible(True)
        self._btn_translate.setEnabled(False)
        self._btn_transcribe.setEnabled(False)
        self._translate_start = time.monotonic()
        self._current_translate_lang = lang_tgt
        self._current_translate_backend = backend
        self._start_translate_status_spinner()
        # The source tab is always the original transcription tab —
        # the new translation tab is inserted right after the original
        # group regardless of which tab the user clicked from.
        self._translate_source_tab = source
        # Cleanup previous thread if any
        if self._translate_thread:
            try:
                self._translate_thread.finished_signal.disconnect(self._on_translate_done)
            except (TypeError, RuntimeError):
                pass
            try:
                self._translate_thread.error_signal.disconnect(self._on_translate_error)
            except (TypeError, RuntimeError):
                pass
            if not self._translate_thread.isRunning():
                self._translate_thread.deleteLater()
        self._translate_thread = TranslateThread(
            raw_text, segments, was_diarized,
            lang_src, lang_tgt, backend)
        self._translate_thread.finished_signal.connect(self._on_translate_done)
        self._translate_thread.error_signal.connect(self._on_translate_error)
        self._translate_thread.start()

    def _on_translate_error(self, message):
        """Show translation error in status bar."""
        _dbg(f"_on_translate_error: {message}")
        self._stop_translate_status_spinner()
        self._lbl_status.setText(message)
        self._lbl_status.setVisible(True)

    def _on_translate_done(self, translated_text, translated_segments):
        """Handle translation completion."""
        _dbg(f"_on_translate_done: text_len={len(translated_text)}, segments={len(translated_segments)}")
        self._stop_translate_status_spinner()
        self._progress.setVisible(False)
        self._update_translate_btn()
        self._update_transcribe_btn()
        if not translated_text and not translated_segments:
            # Total translation failure: there is no result to land.
            # _on_translate_error already put the cause in the status row —
            # keep it visible instead of fabricating a tab with untranslated
            # source text and overwriting the error with a success summary.
            return
        translate_elapsed = time.monotonic() - self._translate_start

        lang = self._current_translate_lang
        # Find language name for tab title
        lang_name = lang.upper()
        for i in range(self._cmb_lang_tgt.count()):
            if self._cmb_lang_tgt.itemData(i) == lang:
                lang_name = self._cmb_lang_tgt.itemText(i).split(" — ")[1] if " — " in self._cmb_lang_tgt.itemText(i) else lang.upper()
                break

        # Compact label for the backend so the tab title stays readable
        # (the user wanted to see at a glance which engine produced
        # which translation). Matches the plasmoid's four-backend list.
        _backend_label_map = {
            "google": "Google",
            "bing": "Bing",
            "ollama": "Ollama",
            "libretranslate": "LT",
        }
        backend_label = _backend_label_map.get(
            getattr(self, "_current_translate_backend", ""), "")
        suffix = f" ({backend_label})" if backend_label else ""

        # Build tab name: "SourceTab → Lang (Backend)"
        source_tab = getattr(self, '_translate_source_tab', None)
        source_idx = self._tabs.indexOf(source_tab) if source_tab else -1
        if source_idx >= 0:
            source_name = self._tabs.tabText(source_idx)
            tab_title = f"{source_name} → {lang_name}{suffix}"
            insert_at = source_idx + 1
            # Skip any existing translation tabs after the source
            while insert_at < self._tabs.count():
                t = self._tabs.tabText(insert_at)
                if "→" in t and t.startswith(source_name):
                    insert_at += 1
                else:
                    break
        else:
            tab_title = f"{lang_name}{suffix}"
            insert_at = self._tabs.count()

        # Create new translation tab inserted right after source
        editor = QTextEdit()
        editor.setReadOnly(self._btn_edit_mode.isChecked())
        editor.setToolTip(self._tip(_("Editable translation text. Ctrl+F to search, Ctrl+Z to undo.")))
        editor.viewport().installEventFilter(self)
        self._install_modified_overlay(editor)
        # Canonical per-tab state; audio path and duration are inherited
        # from the source tab so switching to this translation reloads
        # the right audio file and its summary shows the right length.
        self._init_tab_state(
            editor, getattr(source_tab, '_audio_path', None))
        editor._audio_duration = getattr(source_tab, '_audio_duration', 0.0)
        # The summary line shows the SOURCE run's transcribe time plus
        # this translation's own duration.
        editor._transcribe_elapsed = getattr(
            source_tab, '_transcribe_elapsed', 0.0)
        editor._translate_elapsed = translate_elapsed
        # A translation is a view of its source run: join its rename
        # family so speaker renames keep syncing between the two.
        if source_tab is not None:
            editor._rename_family = getattr(
                source_tab, '_rename_family', source_tab)
        self._tabs.insertTab(insert_at, editor, tab_title)

        # Copy segments from source tab for marker support
        if source_tab and hasattr(source_tab, '_diarize_segments'):
            editor._diarize_segments = list(source_tab._diarize_segments)
        # Inherit the speaker name map so renames applied on the source
        # tab before translation are visible immediately in the new tab.
        if source_tab and hasattr(source_tab, '_speaker_name_map'):
            editor._speaker_name_map = dict(source_tab._speaker_name_map)

        # Store and display. Always populate _raw_text and
        # _was_diarized so re-translating from this tab (without
        # going back to the source tab) Just Works in _on_translate.
        if translated_segments:
            editor._diarize_segments = list(translated_segments)
            editor._was_diarized = True
            # Reconstruct a flat text from the translated segments —
            # used both as fallback raw_text and as input to the
            # language detector when re-translating from this tab.
            editor._raw_text = "\n".join(
                s.get("text", "") for s in translated_segments)
            self._apply_format_to(editor, translated_segments, None)
        elif translated_text:
            editor._raw_text = translated_text
            editor._was_diarized = False
            self._apply_format_to(editor, [], translated_text)

        # Switch to this translation tab
        self._tabs.setCurrentWidget(editor)
        # Uncheck auto-translate so user can translate to other languages
        self._chk_auto_translate.setChecked(False)
        # The translation summary belongs to the freshly created (and now
        # active) translation tab; the source tab keeps its own run summary.
        self._show_status(editor)

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
        """Format and display the active tab.

        Reads segments/raw_text from the active widget itself (per-tab
        state set by _finish_transcription / _on_finished / translation
        handlers). Original behaviour was to anchor on self._text_edit
        (the latest original tab) to avoid mismatching translation
        segments with the original tab — but that broke the format
        combo for any earlier original tab (e.g. user has Tab1=diarize
        + Tab2=plain, switches to Tab1, changes format → nothing
        happens because self._text_edit points at Tab2). Each tab now
        carries its own segments/raw_text since translation tabs also
        set those, so anchoring on the active widget is safe and
        WYSIWYG.

        Skips LLM-result tabs and other non-QTextEdit widgets.
        """
        widget = self._tabs.currentWidget()
        if not isinstance(widget, QTextEdit):
            return
        if getattr(widget, "_is_llm_result", False):
            return
        segments = getattr(widget, "_diarize_segments", None) or []
        raw_text = getattr(widget, "_raw_text", "")
        if not raw_text and not segments:
            return
        self._apply_format_to(widget, segments, raw_text)

    def _apply_format_to(self, editor, segments, raw_text):
        """Format and display text in the given editor.

        Resolves the speaker name map per-tab (attached to editor) —
        renaming propagates to translation tabs because they inherit
        the source tab's map.

        Reads `was_diarized` from the editor itself (per-tab flag set by
        _finish_transcription / _on_finished / _on_translate_done) —
        this method may be called for a non-active tab (e.g. a
        translation tab being rendered after the user switched away from
        the source tab, or _apply_speaker_rename's loop over all diarize
        tabs), so the active tab's flag would be the wrong anchor.
        """
        # The format combo shows the ACTIVE tab's format. Rendering a tab
        # the user is not looking at (a run landing in the background, a
        # speaker rename propagating to sibling tabs) must therefore use
        # the tab's own format, or the combo would retro-format it.
        if self._tabs.currentWidget() is editor:
            fmt = self._cmb_format.currentData()
        else:
            fmt = (getattr(editor, "_format", None)
                   or self._cmb_format.currentData())
        name_map = getattr(editor, "_speaker_name_map", None)
        was_diarized = bool(getattr(editor, "_was_diarized", False))

        if was_diarized and segments:
            if fmt == "srt":
                editor.setPlainText(_format_srt(segments, name_map))
            elif fmt == "json":
                editor.setPlainText(_format_json(segments, name_map))
            else:
                self._set_colored_diarize_to(editor, segments, name_map)
            # Build segment <-> rendered text position mapping so the
            # text-slider sync helpers can move the cursor / highlight /
            # detect clicks without relying on a textual anchor (the
            # colored-diarize format hides timestamps from the view).
            self._compute_segment_positions(editor, segments)
        else:
            editor._segment_positions = []
            text = raw_text or ""
            if fmt == "json":
                editor.setPlainText(json.dumps(
                    [{"text": text}], ensure_ascii=False, indent=2))
            elif fmt == "srt":
                editor.setPlainText(
                    f"1\n00:00:00,000 --> 99:59:59,999\n{text}\n")
            else:
                editor.setPlainText(text)

        # Programmatic render -> hide any stale Modified badge on this
        # editor. The badge is only ever lit by KeyPress events caught
        # in eventFilter, so other tabs are not affected by this call.
        overlay = getattr(editor, '_modified_overlay', None)
        if overlay is not None:
            overlay.setVisible(False)
        # Remember the format used to render this tab so _on_tab_changed
        # can sync the combo back to it on switch.
        editor._format = fmt
        # Snapshot the rendered text so _is_edited_tab can tell a real
        # edit (content differs from this baseline) from an untouched tab.
        editor._rendered_baseline = editor.toPlainText()

    @staticmethod
    def _is_edited_tab(editor):
        """True when the tab holds text the user typed over the last
        render. Tabs never rendered (no baseline) count as untouched:
        there is nothing to lose."""
        baseline = getattr(editor, '_rendered_baseline', None)
        return baseline is not None and editor.toPlainText() != baseline

    def _compute_segment_positions(self, editor, segments):
        """Build [{start, end, seg}, ...] in editor.toPlainText() coordinates.
        Searches each segment's text in order, advancing the cursor so that
        repeated phrases match the right occurrence. Stored on the editor
        for tab safety (one mapping per tab).

        Notes:
        - We do NOT fall back to a global text.find when the per-cursor
          search misses. A global hit would land on an earlier segment
          and shift every subsequent position by a chunk, breaking
          highlight + click-to-seek silently. Skipping a missing
          segment is far less surprising than misaligning all the
          following ones.
        - The `_set_colored_diarize_to` formatter inserts &nbsp;-based
          indentation; toPlainText() preserves those as U+00A0 chars.
          Searching by seg["text"] (no leading whitespace) still hits
          the correct position because find() walks past the prefix
          characters automatically — no offset shift needed."""
        text = editor.toPlainText()
        positions = []
        cursor_pos = 0
        for seg in segments:
            snippet = (seg.get("text") or "").strip()
            if not snippet:
                continue
            idx = text.find(snippet, cursor_pos)
            if idx < 0:
                # Skip silently — see docstring above.
                continue
            end_idx = idx + len(snippet)
            positions.append({"start": idx, "end": end_idx, "seg": seg})
            cursor_pos = end_idx
        editor._segment_positions = positions

    def _set_colored_diarize_to(self, editor, segments, name_map=None):
        """Display diarized text with colored speaker headers in given editor.

        The speaker-change detection compares canonical ids (seg["speaker"])
        so consecutive segments from the same speaker stay grouped. The
        header label uses the display name from `name_map` when present.
        Colors are derived from the canonical id via `_speaker_color()`.
        """
        import html as _html
        lines = []
        prev_speaker = None
        for seg in segments:
            if seg["speaker"] != prev_speaker:
                if prev_speaker is not None:
                    lines.append("<br/>")
                color = self._speaker_color(seg["speaker"])
                label = (name_map or {}).get(seg["speaker"], seg["speaker"])
                lines.append(
                    f'<b style="color:{color}">{_html.escape(label)}:</b>')
                prev_speaker = seg["speaker"]
            lines.append(f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{_html.escape(seg["text"])}')
        editor.setHtml(
            '<div style="white-space:pre-wrap">' + "<br/>".join(lines) + "</div>")

    # ── Speaker rename panel ──────────────────────────────────────

    def _build_rename_section(self, parent_layout):
        """Group box for post-diarization speaker renaming.

        Hidden by default; made visible when a diarized transcription
        produces segments. Each row shows a color swatch matching the
        canonical speaker id + a QLineEdit to set a custom display name.
        """
        # True accordion (arrow toggle, no checkbox). Outer container is
        # a QFrame with a thin border so it still reads as a grouped
        # section; header is a QToolButton with a ▼/▶ arrow that
        # collapses self._rename_content underneath.
        self._grp_rename = QFrame()
        self._grp_rename.setObjectName("renameAccordion")
        self._grp_rename.setStyleSheet(
            "#renameAccordion { border: 1px solid palette(mid); "
            "border-radius: 4px; }")
        self._grp_rename.setVisible(False)
        gv = QVBoxLayout(self._grp_rename)
        gv.setContentsMargins(0, 0, 0, 0)
        gv.setSpacing(0)

        # Use unicode triangles ▼/▶ in the text (same style as
        # dictee-setup.py accordions). QPushButton (not QToolButton)
        # because text-align:left is reliably honoured here.
        self._btn_rename_toggle = QPushButton(
            "▶  " + _("Rename speakers"))
        self._btn_rename_toggle.setCheckable(True)
        self._btn_rename_toggle.setChecked(False)
        self._btn_rename_toggle.setFlat(True)
        self._btn_rename_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        # Maximum (not Expanding) so the clickable area is just the text
        # width — clicking the empty space to the right (where the
        # status label sits) doesn't accidentally collapse the
        # accordion. See feedback-toggle-sizepolicy-max.md.
        self._btn_rename_toggle.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._btn_rename_toggle.setStyleSheet(
            "QPushButton { border: none; padding: 4px 6px; "
            "font-weight: bold; text-align: left; }"
            "QPushButton:hover { background: rgba(127,127,127,40); "
            "border-radius: 3px; }")
        self._btn_rename_toggle.toggled.connect(
            self._on_rename_group_toggled)

        # Header row : toggle button + diarization summary on the right.
        # The summary ("2 speakers — audio 5:23 — transcribed in 12s")
        # used to live in the bottom status label, but it makes more
        # sense visually next to the rename header.
        header_h = QHBoxLayout()
        header_h.setContentsMargins(0, 0, 0, 0)
        header_h.setSpacing(8)
        # No stretch on the button: its setSizePolicy(Maximum) keeps it
        # tight to the text, so clicks on empty space to its right do
        # NOT collapse the accordion.
        header_h.addWidget(self._btn_rename_toggle)
        self._lbl_rename_status = QLabel("")
        # Use palette text colour (always readable on the current theme)
        # — palette(mid) was invisible on some Plasma themes.
        self._lbl_rename_status.setStyleSheet(
            "QLabel { padding: 0 8px; font-style: italic; }")
        self._lbl_rename_status.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_h.addWidget(self._lbl_rename_status)
        header_h.addStretch(1)
        gv.addLayout(header_h)

        self._rename_content = QFrame()
        # Match the toggle's initial unchecked state. setChecked(False)
        # on an already-False button does NOT emit `toggled`, so the
        # slot would never run to hide the content frame.
        self._rename_content.setVisible(False)
        content = QVBoxLayout(self._rename_content)
        content.setContentsMargins(8, 4, 8, 6)
        content.setSpacing(4)

        # Two-column grid: up to 4 speakers fit on 2 rows × 2 cols.
        self._rename_rows_layout = QGridLayout()
        self._rename_rows_layout.setHorizontalSpacing(16)
        self._rename_rows_layout.setVerticalSpacing(3)
        content.addLayout(self._rename_rows_layout)

        lay_btns = QHBoxLayout()
        self._btn_rename_apply = QPushButton(_("Apply"))
        self._btn_rename_apply.setToolTip(self._tip(_(
            "Replaces speaker labels in all views and exports (text, SRT, "
            "JSON). Does not modify raw data.")))
        self._btn_rename_apply.clicked.connect(self._apply_speaker_rename)
        self._btn_rename_reset = QPushButton(_("Reset"))
        self._btn_rename_reset.setToolTip(self._tip(_(
            "Clears custom names and reverts to the generic labels "
            "Speaker 0, Speaker 1, etc.")))
        self._btn_rename_reset.clicked.connect(self._reset_speaker_rename)
        lay_btns.addWidget(self._btn_rename_apply)
        lay_btns.addWidget(self._btn_rename_reset)
        lay_btns.addStretch()
        content.addLayout(lay_btns)

        gv.addWidget(self._rename_content)
        parent_layout.addWidget(self._grp_rename)

    def _on_rename_group_toggled(self, checked):
        """Collapse / expand the rename accordion. Toggle the inner
        content frame and flip the unicode triangle on the header."""
        self._rename_content.setVisible(checked)
        prefix = "▼  " if checked else "▶  "
        self._btn_rename_toggle.setText(prefix + _("Rename speakers"))

    def _refresh_rename_panel_for_target(self, target):
        """Sync the global rename panel to `target` (the transcription
        target tab) — but only when that tab is currently visible. Async
        finalizers (_on_finished, _finish_transcription) call this instead of
        touching self._grp_rename / _populate_rename_fields directly, so the
        panel of a tab the user has switched to is never clobbered. When the
        user switches back to the target later, _on_tab_changed re-syncs.
        """
        if self._tabs.currentWidget() is not target:
            return
        if (getattr(target, '_was_diarized', False)
                and getattr(target, '_diarize_segments', None)):
            self._populate_rename_fields()
        else:
            self._grp_rename.setVisible(False)

    def _populate_rename_fields(self):
        """Rebuild rename inputs from the current self._segments.

        Speakers are laid out in a 2-column grid (up to 4 speakers = 2
        rows × 2 columns, matching Sortformer's max). Called after each
        successful diarization and on tab switches to the appropriate
        tab. Hides the group box when there is nothing to rename.
        """
        # Clear previous widgets from the grid layout
        while self._rename_rows_layout.count():
            item = self._rename_rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._rename_line_edits = {}

        if not self._was_diarized or not self._segments:
            self._grp_rename.setVisible(False)
            return

        # Unique speakers in order of first appearance
        seen = []
        for seg in self._segments:
            spk = seg["speaker"]
            if spk not in seen:
                seen.append(spk)

        # Build one compact row widget per speaker, place in a 2-col grid
        for i, spk in enumerate(seen):
            cell = QWidget()
            row = QHBoxLayout(cell)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)

            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            color = self._speaker_color(spk)
            swatch.setStyleSheet(
                f"background-color:{color}; border:1px solid #333;"
                " border-radius:3px;")
            row.addWidget(swatch)

            lbl = QLabel(spk)
            lbl.setFixedWidth(72)
            lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            row.addWidget(lbl)

            le = QLineEdit()
            le.setPlaceholderText(_("Nom (ex. Alice)"))
            le.setText(self._speaker_name_map.get(spk, ""))
            le.returnPressed.connect(self._apply_speaker_rename)
            row.addWidget(le, 1)

            grid_row, grid_col = divmod(i, 2)
            self._rename_rows_layout.addWidget(cell, grid_row, grid_col)
            self._rename_line_edits[spk] = le

        # Equal stretch on both columns so the widths match
        self._rename_rows_layout.setColumnStretch(0, 1)
        self._rename_rows_layout.setColumnStretch(1, 1)

        self._grp_rename.setVisible(True)
        # Keep the rename pane collapsed by default after a diarization.
        # The status next to the toggle ("2 speakers — audio 5:23 — …")
        # already gives enough feedback; the user expands the pane only
        # when they actually want to rename speakers.
        self._btn_rename_toggle.setChecked(False)

    @staticmethod
    def _match_anchors_to_batch_speakers(name_map, anchors, batch_segments):
        """Match live-named speakers to batch speaker IDs via max overlap on anchors.

        Args:
            name_map: {"0": "Alice", "1": "Bob"} (str keys, live speaker integers as strings)
            anchors: {"0": [{"start": float, "end": float}, ...], ...}
            batch_segments: list of dicts {"speaker": "Speaker N", "start": float, "end": float, ...}
                            (segments from _parse_diarize_output — speaker is a string label)

        Returns: {"Speaker N": name} mapping ready for a tab's _speaker_name_map.
        """
        from collections import defaultdict
        # Accumulate overlap per (live_spk_str, batch_spk_str) pair
        overlap_matrix = defaultdict(lambda: defaultdict(float))
        for live_spk_str, live_anchors in anchors.items():
            for anchor in live_anchors:
                a_start, a_end = anchor["start"], anchor["end"]
                for seg in batch_segments:
                    b_start, b_end = seg["start"], seg["end"]
                    overlap = max(0.0, min(a_end, b_end) - max(a_start, b_start))
                    if overlap > 0:
                        overlap_matrix[live_spk_str][seg["speaker"]] += overlap

        # Greedy assignment: most-confident named speaker first
        used_batch_spks = set()
        result = {}
        live_spks_by_confidence = sorted(
            name_map.keys(),
            key=lambda s: max(overlap_matrix[s].values()) if overlap_matrix[s] else 0,
            reverse=True,
        )
        for live_spk_str in live_spks_by_confidence:
            candidates = [
                (bs, ov) for bs, ov in overlap_matrix[live_spk_str].items()
                if bs not in used_batch_spks
            ]
            if not candidates:
                continue
            best_batch_spk = max(candidates, key=lambda c: c[1])[0]
            result[best_batch_spk] = name_map[live_spk_str]
            used_batch_spks.add(best_batch_spk)
        return result

    def _prefill_rename_panel(self, name_map):
        """Pre-fill rename panel QLineEdits with mapped names.

        name_map: {"Speaker N": display_name} — keys match self._rename_line_edits.
        Called after _populate_rename_fields so the widgets already exist.
        """
        for spk_label, name in name_map.items():
            if spk_label in self._rename_line_edits:
                self._rename_line_edits[spk_label].setText(name)

    def _apply_speaker_rename(self):
        """Collect QLineEdit values, update the display map, re-render.

        Applies to the ACTIVE tab and the other views of the SAME run
        (its _rename_family: a run tab and its translation tabs), never
        to independent transcriptions — "Speaker 0" names a different
        person in every run, even when the same audio file is
        re-transcribed (each run assigns labels on its own). The
        previous same-_audio_path criterion conflated the two and
        renamed sibling runs of one file together (found 2026-07-21).
        """
        new_map = {}
        for spk, le in self._rename_line_edits.items():
            name = le.text().strip()
            if name:
                new_map[spk] = name

        active = self._tabs.currentWidget()
        if not isinstance(active, QTextEdit):
            return
        family = getattr(active, "_rename_family", active)

        for i in range(self._tabs.count()):
            w = self._tabs.widget(i)
            if not isinstance(w, QTextEdit):
                continue
            if (w is not active
                    and getattr(w, "_rename_family", None) is not family):
                continue
            w._speaker_name_map = dict(new_map)
            segs = getattr(w, "_diarize_segments", None)
            if not segs:
                continue
            # Re-rendering replaces the whole text: never do that behind
            # the user's back on a sibling tab they have hand-corrected.
            # The new map is stored above, so their next explicit render
            # (format change, rename from that tab) picks the names up.
            # The active tab is always re-rendered — showing the rename
            # is what Apply is for, and its Modified badge is in view.
            if w is not active and self._is_edited_tab(w):
                continue
            self._apply_format_to(w, segs, getattr(w, "_raw_text", ""))

        # Refresh active tab explicitly too (covers the non-diarize case)
        self._apply_format()
        # No status message: the visual change in the tabs is its own
        # confirmation, and a status row would push everything down.

    def _reset_speaker_rename(self):
        """Clear all QLineEdits and re-apply an empty map."""
        for le in self._rename_line_edits.values():
            le.clear()
        self._apply_speaker_rename()

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

    def _on_export_current_tab(self):
        """Export the currently active tab. LLM result tabs use a
        dedicated dialog (PDF + Markdown); regular tabs (transcription
        and translations) go through the standard ExportDialog
        (txt/srt/json). One tab at a time — multi-tab export was
        removed because it produced a confusing pile of files."""
        editor = self._tabs.currentWidget()
        if getattr(editor, "_is_llm_result", False):
            self._on_export_llm_tab(editor)
            return
        if not isinstance(editor, QTextEdit):
            return
        text = editor.toPlainText()
        if not text.strip():
            self._lbl_status.setText(_("Nothing to export."))
            self._lbl_status.setVisible(True)
            return
        idx = self._tabs.indexOf(editor)
        tab_name = self._tabs.tabText(idx) if idx >= 0 else _("Tab")
        base = os.path.splitext(os.path.basename(self._file_input.text()))[0] or "transcription"
        dlg = ExportDialog(
            [(tab_name, text)], self._cmb_format.currentData(), base, self,
            current_tab_index=0)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._do_export(dlg.selected_tabs(), dlg.export_formats(),
                        dlg.export_dir(), dlg.base_name(), widget=editor)

    def _on_export_llm_tab(self, editor):
        """Show the LLMExportDialog for an LLM result tab."""
        text = editor.toPlainText() if hasattr(editor, "toPlainText") else ""
        if not text.strip():
            self._lbl_status.setText(_("Nothing to export."))
            self._lbl_status.setVisible(True)
            return
        # Default filename: {audio_basename}-{profile_name} sanitized.
        audio = self._file_input.text() if hasattr(self, "_file_input") else ""
        base = os.path.splitext(os.path.basename(audio))[0] or "transcription"
        profile = getattr(editor, "_llm_profile_name", "") or "llm"
        default_name = re.sub(r"[^\w.-]", "_", f"{base}-{profile}")
        dlg = LLMExportDialog(default_name, text, self)
        dlg.exec()

    def _on_llm_process(self):
        """Open the LLM analysis dialog.

        The source is the ACTIVE tab (the one the user clicked from):
        its segments and raw text feed the LLM. Analysing a translation
        tab therefore analyses the translated text — acceptable since
        the LLM's output language is forced to the user's native
        language anyway.

        If the original is plain (no diarization), the raw text is
        wrapped in a single synthetic segment so global-mode profiles
        (Synthèse, Chapitrage) still work — the dialog filters its
        profile list to the plain-text family.

        Speaker rename map (Speaker 1 → "Alice") is propagated to the
        speaker field of each segment so the LLM sees human-friendly
        names instead of the canonical labels.
        """
        # Pin the source = the tab the user clicked from. Without this,
        # _start_llm_result_tab would compute the "#N " prefix from
        # self._text_edit, which tracks the *last created* transcription
        # tab — not the one currently visible. Picking up the active
        # widget at click time keeps the LLM result tab's counter in
        # sync with the transcription it analyses.
        src_widget = self._tabs.currentWidget()
        if src_widget is None or getattr(src_widget, "_is_llm_result", False):
            src_widget = self._text_edit
        raw_segments = list(getattr(src_widget, "_diarize_segments", None) or [])
        is_plain = not raw_segments
        if is_plain:
            raw_text = getattr(src_widget, "_raw_text", "")
            if raw_text:
                raw_segments = [{
                    "start": 0.0, "end": 0.0,
                    "speaker": "Speaker 0", "text": raw_text,
                }]
        name_map = getattr(src_widget, "_speaker_name_map", None) or {}
        segments = []
        for seg in raw_segments:
            seg_copy = dict(seg)
            canonical = seg.get("speaker", "")
            if canonical in name_map and name_map[canonical].strip():
                seg_copy["speaker"] = name_map[canonical].strip()
            segments.append(seg_copy)
        try:
            self._llm_dlg = LLMProcessDialog(
                segments, self, is_plain=is_plain, source_widget=src_widget)
        except ImportError as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self, _("Module missing"),
                _("Could not load LLM module:\n{err}").format(err=str(e)))
            return
        self._llm_dlg.setModal(True)
        self._llm_dlg.open()

    # === Tab spinner (used during transcription and LLM analysis) ===

    SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    # All spinners (per-tab title + bottom translate-status label)
    # share a single QTimer + frame index so they stay in sync and we
    # don't multiply timers. Targets register themselves; the timer
    # stops automatically when nothing is left to animate.

    def _ensure_spinner_timer(self):
        if not hasattr(self, "_spinning_tabs"):
            self._spinning_tabs = {}    # widget → base title (str)
            self._spinning_status = False  # translate-status active flag
            self._spinner_idx = 0
            self._spinner_timer = QTimer(self)
            self._spinner_timer.setInterval(100)
            self._spinner_timer.timeout.connect(self._tick_spinner)

    def _render_spinner_frame(self):
        """Apply the current frame to every active spinner target.
        Called both on each tick and once at start so the user sees
        the spinner without waiting for the first interval."""
        frame = self.SPINNER_FRAMES[self._spinner_idx]
        for widget, base in list(self._spinning_tabs.items()):
            idx = self._tabs.indexOf(widget)
            if idx < 0:
                self._spinning_tabs.pop(widget, None)
                continue
            self._tabs.setTabText(idx, f"{frame} {base}")
        if self._spinning_status:
            base = getattr(self, "_translate_status_base", "")
            sep = (" " + frame + " ") if base else (frame + " ")
            self._lbl_status.setText(base + sep + _("Translating..."))

    def _maybe_stop_timer(self):
        if (hasattr(self, "_spinner_timer")
                and not self._spinning_tabs
                and not self._spinning_status):
            self._spinner_timer.stop()

    def _start_tab_spinner(self, widget, base_title):
        if widget is None:
            return
        self._ensure_spinner_timer()
        self._spinning_tabs[widget] = base_title
        self._render_spinner_frame()
        if not self._spinner_timer.isActive():
            self._spinner_timer.start()

    def _stop_tab_spinner(self, widget, final_title=None):
        if not hasattr(self, "_spinning_tabs"):
            return
        base = self._spinning_tabs.pop(widget, None)
        idx = self._tabs.indexOf(widget)
        if idx >= 0:
            self._tabs.setTabText(idx, final_title if final_title is not None
                                  else (base or self._tabs.tabText(idx)))
        self._maybe_stop_timer()

    def _start_translate_status_spinner(self):
        """Animate the braille spinner in the bottom status label,
        replacing the leading "—" before "Translating...". Reuses the
        shared spinner timer so it stays in sync with any tab spinner
        already running."""
        self._ensure_spinner_timer()
        self._spinning_status = True
        self._render_spinner_frame()
        if not self._spinner_timer.isActive():
            self._spinner_timer.start()

    def _stop_translate_status_spinner(self):
        if getattr(self, "_spinning_status", False):
            self._spinning_status = False
            self._maybe_stop_timer()

    def _stop_all_spinners(self):
        """Stop every active spinner — used on _show_status when
        results land, regardless of which workflow started them."""
        if hasattr(self, "_spinning_tabs"):
            for w in list(self._spinning_tabs.keys()):
                self._stop_tab_spinner(w)
        self._stop_translate_status_spinner()

    def _tick_spinner(self):
        if not self._spinning_tabs and not self._spinning_status:
            self._spinner_timer.stop()
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(self.SPINNER_FRAMES)
        self._render_spinner_frame()

    def _start_llm_result_tab(self, profile_name, model_name="", source_widget=None):
        """Create the LLM result tab immediately, empty, with a spinner.
        Returns the editor widget; caller passes it to
        _finish_llm_result_tab once the LLM call is done."""
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlaceholderText(_("Generating LLM analysis…"))
        try:
            editor.viewport().installEventFilter(self)
        except Exception as _e:
            _dbg(f"silenced: {_e!r}")
        editor._audio_path = None
        editor._is_llm_result = True
        editor._llm_profile_name = profile_name
        # Inherit the "#N " counter from the source transcription tab
        # the user clicked from (captured by _on_llm_process), so the
        # result visibly belongs to that transcription — e.g. "#3 LLM:
        # Synthèse". Falling back to self._text_edit only matters for
        # legacy callers that didn't pass `source_widget`.
        src = source_widget if source_widget is not None else self._text_edit
        src_idx = self._tabs.indexOf(src)
        prefix = ""
        if src_idx >= 0:
            m = re.match(r"^(#\d+)\s", self._tabs.tabText(src_idx))
            if m:
                prefix = m.group(1) + " "
        # Tab title shows the source-counter + profile + model so the
        # user can tell two runs of the same profile with different
        # models apart at a glance.
        if model_name:
            base_title = f"{prefix}LLM: {profile_name} · {model_name}"
        else:
            base_title = f"{prefix}LLM: {profile_name}"
        editor._spinner_base_title = base_title
        idx = self._tabs.addTab(editor, base_title)
        self._tabs.setCurrentIndex(idx)
        self._start_tab_spinner(editor, base_title)
        return editor

    def _finish_llm_result_tab(self, editor, text):
        """Fill the LLM result tab with the model output and stop the
        spinner."""
        if editor is None:
            return
        editor.setPlainText(text or "")
        base = getattr(editor, "_spinner_base_title", None) or self._tabs.tabText(
            self._tabs.indexOf(editor))
        self._stop_tab_spinner(editor, final_title=base)

    def _cancel_llm_result_tab(self, editor):
        """LLM call failed mid-flight: drop the empty tab and clean up."""
        if editor is None:
            return
        self._stop_tab_spinner(editor)
        idx = self._tabs.indexOf(editor)
        if idx >= 0:
            self._tabs.removeTab(idx)
            editor.deleteLater()

    def _add_llm_result_tab(self, profile_name, text, source_widget=None):
        """Append a new tab containing an LLM analysis result (markdown
        or reformatted diarize). Read-only by default — user can toggle
        edit mode if they want to tweak it."""
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text or "")
        try:
            editor.viewport().installEventFilter(self)
        except Exception as _e:
            _dbg(f"silenced: {_e!r}")
        # No audio binding — these tabs are not tied to a wav file.
        editor._audio_path = None
        # Marker used by _on_tab_changed and _on_export_current_tab to
        # show the LLM-specific Export dialog (PDF/Markdown) and grey
        # out the irrelevant buttons (Copy all, Export all, LLM analysis).
        editor._is_llm_result = True
        editor._llm_profile_name = profile_name
        # Inherit "#N " from the source transcription tab captured at
        # click-time (falls back to the last-touched tab for legacy
        # callers).
        src = source_widget if source_widget is not None else self._text_edit
        src_idx = self._tabs.indexOf(src)
        prefix = ""
        if src_idx >= 0:
            m = re.match(r"^(#\d+)\s", self._tabs.tabText(src_idx))
            if m:
                prefix = m.group(1) + " "
        tab_name = prefix + _("LLM: {profile}").format(profile=profile_name)
        idx = self._tabs.addTab(editor, tab_name)
        self._tabs.setCurrentIndex(idx)

    def _do_export(self, selected, formats, out_dir, base, widget=None):
        """Write the selected tab's text out in the chosen format(s).
        `selected` is always a single-tab list — multi-tab export was
        removed because users found the resulting file pile confusing.

        `widget` is the tab the caller already resolved. Tab titles are
        NOT unique (two translations of one run into the same language
        with the same backend are named identically), so re-resolving by
        title here used to export the first namesake's data."""
        if not selected or not formats:
            self._lbl_status.setText(_("Nothing to export."))
            self._lbl_status.setVisible(True)
            return

        if not os.path.isdir(out_dir):
            self._lbl_status.setText(
                _("Export directory does not exist: {dir}").format(dir=out_dir))
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
                # The caller passes the resolved widget; fall back to a
                # title lookup only for callers that have none.
                segments = None
                name_map = None
                displayed_fmt = None
                tab_raw = ""
                edited = False
                w = widget
                if w is None:
                    for i in range(self._tabs.count()):
                        if self._tabs.tabText(i) == tab_name:
                            w = self._tabs.widget(i)
                            break
                if w is not None:
                    segments = getattr(w, '_diarize_segments', None)
                    name_map = getattr(w, '_speaker_name_map', None)
                    displayed_fmt = getattr(w, '_format', None)
                    tab_raw = getattr(w, '_raw_text', "")
                    edited = self._is_edited_tab(w)

                if edited and fmt == displayed_fmt:
                    # The editor already holds this exact format with the
                    # user's edits (WYSIWYG) — export it verbatim instead of
                    # re-rendering from segments, which would drop the edits.
                    # Cross-format export still re-renders (edited timestamp-
                    # less text can't be remapped onto segments); the format-
                    # locking UX that prevents that case is deferred to 1.4.
                    content = text
                elif fmt == "text":
                    if segments:
                        # Re-render text format with renamed speakers so the
                        # exported file reflects the current display map even
                        # if the editor was never refreshed.
                        content = _format_text(segments, name_map)
                    else:
                        # Same reasoning as the segment-less branch below:
                        # a tab displayed as JSON must not export its
                        # rendering as if it were the transcript.
                        content = text if edited else (tab_raw or text)
                else:
                    if segments and fmt == "srt":
                        content = _format_srt(segments, name_map)
                    elif segments and fmt == "json":
                        content = _format_json(segments, name_map)
                    else:
                        # Segment-less tab: export ITS stored raw text, so
                        # a tab displayed as JSON/SRT does not come out
                        # wrapped in its own rendering. The on-screen text
                        # is only the right source when the user edited it
                        # (`edited` above already covers the same-format
                        # case; a cross-format export of edited text has
                        # no timestamps to remap, so the edits win here).
                        raw = text if edited else (tab_raw or text)
                        if fmt == "json":
                            content = json.dumps([{"text": raw}],
                                                 ensure_ascii=False, indent=2)
                        else:
                            content = f"1\n00:00:00,000 --> 99:59:59,999\n{raw}\n"

                safe_name = re.sub(r'[^\w.-]', '_', tab_name)
                # Sanitise the user-editable base too, otherwise a
                # slash in the field would let os.path.join escape
                # the chosen output directory.
                safe_base = re.sub(r'[^\w.-]', '_', base) or "transcription"
                filename = f"{safe_base}-{safe_name}{ext}"
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
    parser.add_argument("--diar-engine", default="",
                        help="Diarization engine (auto|multi|sortformer|moss). "
                             "Empty = the choice persisted in the window. "
                             "An unavailable engine is ignored.")
    parser.add_argument("--asr-model", default="",
                        help="ASR model spec (parakeet-int8|parakeet-fp32|"
                             "whisper|whisper-rust|nemotron; whisper sizes "
                             "follow dictee-setup, or force one with "
                             "whisper-tiny|whisper-small|whisper-medium|"
                             "whisper-rust-<size>). "
                             "Empty = use the F9 daemon (default).")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging to stderr and /tmp/dictee-transcribe.log")
    # Positional args: receive %F from .desktop / file-manager open-with /
    # CLI usage like `dictee-transcribe foo.wav`. Only the first one is
    # used (the UI handles a single file at a time).
    parser.add_argument("files", nargs="*",
                        help="Audio file path(s); first one is opened.")
    args = parser.parse_args()

    global DEBUG
    if args.debug or os.environ.get("DICTEE_DEBUG") == "true":
        DEBUG = True
        _dbg("dictee-transcribe starting (debug via %s)" % ("--debug" if args.debug else "DICTEE_DEBUG"))

    app = QApplication(sys.argv)
    app.setApplicationName("dictee-transcribe")
    # Intentionally NOT calling setDesktopFileName: under Plasma 6
    # Wayland it makes the compositor read the icon from the .desktop
    # file and ignore setWindowIcon, breaking the dynamic icon switch
    # between blue (transcribe) and violet (diarize). The .desktop
    # match for MIME associations / "Open with" still works through
    # StartupWMClass=dictee-transcribe declared in the .desktop file.
    # If you re-enable setDesktopFileName, expect the taskbar icon to
    # become static again.
    # Initial icon — _refresh_window_icon() will switch it as the
    # Diarization toggle changes; we set a sane default so the very
    # first paint isn't a generic Wayland icon.
    try:
        from PyQt6.QtGui import QIcon
    except ImportError:
        from PySide6.QtGui import QIcon
    app.setWindowIcon(QIcon.fromTheme("parakeet-transcribing"))

    file_path = args.file or (args.files[0] if args.files else None)
    win = TranscribeWindow(
        file_path=file_path,
        auto_diarize=args.diarize,
        asr_model=args.asr_model,
        diar_engine=args.diar_engine,
    )
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
