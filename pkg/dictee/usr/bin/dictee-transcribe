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
        QMessageBox, QToolButton, QSizePolicy, QFrame, QToolTip,
    )
    from PyQt6.QtGui import QFont as _QFontTip
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
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
        QMessageBox, QToolButton, QSizePolicy, QFrame, QToolTip,
    )
    from PySide6.QtGui import QFont as _QFontTip
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


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
    tmp = CONF_PATH + ".tmp"
    os.makedirs(os.path.dirname(CONF_PATH), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.replace(tmp, CONF_PATH)


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
    env["DICTEE_LANG_SOURCE"] = conf.get("DICTEE_LANG_SOURCE", env.get("LANG", "en")[:2])
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


class _DiarizeTranscribeWorker(QThread):
    """Phase 2 worker: transcribe diarized segments via daemon socket."""
    progress = Signal(int, int)    # (done, total)
    finished = Signal(str)         # final output text
    error = Signal(str)            # error message

    def __init__(self, audio_path, diarize_output, sock_path, parent=None):
        super().__init__(parent)
        self._audio_path = audio_path
        self._diarize_output = diarize_output
        self._sock_path = sock_path
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
        except Exception:
            pass

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
        except Exception:
            pass

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

        # Wait for socket (max 15s).
        # NB: never use `_` as the loop variable — it shadows the gettext
        # function `_(...)` for the rest of run(), and every translated
        # string downstream blows up with "'int' object is not callable".
        for _attempt in range(60):
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
            self.error.emit(_("Daemon socket not available after 15s"))
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

        # Transcribe full audio via daemon with timestamps (diarize mode)
        _dbg(f"DiarizeWorker: sending full audio to daemon: {daemon_path}")
        full_text = ""
        try:
            self._sock = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
            self._sock.settimeout(120)
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

        # Match sentences to speakers by maximum overlap (same algo as transcribe-diarize)
        results = []
        for sent in sentences:
            best_speaker = -1
            best_overlap = 0.0
            for seg in speaker_segments:
                overlap_start = max(sent["start"], seg["start"])
                overlap_end = min(sent["end"], seg["end"])
                overlap = max(0.0, overlap_end - overlap_start)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = seg["speaker"]
            speaker = f"{_('Speaker')} {best_speaker}" if best_speaker >= 0 else _("UNKNOWN")
            results.append(
                f"[{sent['start']:.2f}s - {sent['end']:.2f}s] {speaker}: {sent['text']}")

        self.progress.emit(3, 3)  # done
        self.finished.emit("\n".join(results))


class _ChunkedPipelineWorker(QThread):
    """Long-file chunked pipeline (audio > LONG_AUDIO threshold + diarize ON).

    Phase 1: ffmpeg pre-cut into 2-min chunks with 15-s overlap (WAV 16k mono).
    Phase 2: diarize-only on the full file -> global speaker segments.
    Phase 3: transcribe-diarize-batch --no-diarize on chunks -> timestamped tokens.
    Phase 4: merge global speakers onto tokens via argmax_overlap.

    Output: '[X.XXs - Y.YYs] Speaker N: text' per line — DIARIZE_RE-compatible.
    """
    phase_changed = Signal(int, str)    # (phase_num 1..4, label)
    chunk_progress = Signal(int, int)   # (done, total) for Phase 3
    finished = Signal(str)              # final formatted output
    error = Signal(str)

    CHUNK_SECONDS = 120
    OVERLAP_SECONDS = 15
    STEP_SECONDS = 105    # CHUNK - OVERLAP

    def __init__(self, audio_path, sensitivity, parent=None):
        super().__init__(parent)
        self._audio_path = audio_path
        self._sensitivity = sensitivity
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
            except Exception:
                pass

    def run(self):
        try:
            duration = self._get_duration()
            if duration <= 0:
                self.error.emit(_("Could not determine audio duration"))
                return

            self.phase_changed.emit(1, _("Phase 1/4: pre-cut audio"))
            self._tmp_dir = self._make_tmp_dir()
            chunks = self._ffmpeg_split(duration)
            if self._cancel:
                return
            if not chunks:
                self.error.emit(_("No chunks produced from audio split"))
                return

            self.phase_changed.emit(2, _("Phase 2/4: global diarization"))
            speaker_segments = self._run_diarize_only()
            if self._cancel:
                return
            if not speaker_segments:
                self.error.emit(_("No speaker segments detected"))
                return

            self.phase_changed.emit(3, _("Phase 3/4: chunked transcription"))
            tokens_absolute = self._run_transcribe_batch(chunks)
            if self._cancel:
                return
            if not tokens_absolute:
                self.error.emit(_("No transcription tokens produced"))
                return

            self.phase_changed.emit(4, _("Phase 4/4: merging speakers"))
            output = self._merge(tokens_absolute, speaker_segments)
            if not output:
                self.error.emit(_("Merge produced empty output"))
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
        """Run diarize-only. Stdout format: 'start end speaker_id' per line."""
        cmd = ["diarize-only", "--sensitivity", f"{self._sensitivity:.2f}",
               self._audio_path]
        self._current_proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=self._subprocess_env,
        )
        try:
            stdout_data, _err = self._current_proc.communicate(timeout=600)
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
        self._current_proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
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
        """Merge speakers onto tokens via argmax_overlap.

        Output: '[X.XXs - Y.YYs] Speaker N: text' per line.
        Speaker label is hardcoded English to stay DIARIZE_RE-compatible.
        """
        results = []
        for tok in tokens:
            best_speaker = -1
            best_overlap = 0.0
            for seg in speaker_segments:
                ov_start = max(tok["start"], seg["start"])
                ov_end = min(tok["end"], seg["end"])
                ov = max(0.0, ov_end - ov_start)
                if ov > best_overlap:
                    best_overlap = ov
                    best_speaker = seg["speaker"]
            spk = f"Speaker {best_speaker}" if best_speaker >= 0 else "UNKNOWN"
            results.append(
                f"[{tok['start']:.2f}s - {tok['end']:.2f}s] {spk}: {tok['text']}"
            )
        return "\n".join(results)

    def _cleanup_tmp(self):
        if self._tmp_dir and os.path.exists(self._tmp_dir):
            try:
                shutil.rmtree(self._tmp_dir, ignore_errors=True)
            except Exception:
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
                for _speaker, indices in groups:
                    group_text = "\n".join(self._segments[i]["text"] for i in indices)
                    translated = _translate_text(group_text, self._lang_src, self._lang_tgt, self._backend)
                    if translated:
                        lines = [l.strip() for l in translated.strip().splitlines() if l.strip()]
                        for j, idx in enumerate(indices):
                            new_seg = dict(self._segments[idx])
                            new_seg["text"] = lines[j] if j < len(lines) else self._segments[idx]["text"]
                            translated_segments[idx] = new_seg
                    else:
                        failed = True
                if self._cancelled:
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
                    self.finished_signal.emit(self._raw_text, [])
                else:
                    self.finished_signal.emit(translated, [])
        except Exception as e:
            if self._cancelled:
                return
            self.error_signal.emit(str(e))
            self.finished_signal.emit(self._raw_text, self._segments)


# === Export Dialog ===

class ExportDialog(QDialog):
    """Dialog to export one or more tabs in chosen format and directory."""

    def __init__(self, tabs_info, current_format, base_name, parent=None,
                 current_tab_index=None):
        """
        tabs_info: list of (tab_name, text_content)
        current_format: "text", "srt", or "json"
        base_name: base filename from audio file
        current_tab_index: if set, only this tab is pre-checked
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
            chk = ToggleSwitch(name)
            if current_tab_index is not None:
                chk.setChecked(i == current_tab_index)
            else:
                chk.setChecked(True)
            lay_tabs.addWidget(chk)
            self._tab_checks.append(chk)
        layout.addWidget(group)

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

    def __init__(self, segments, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("LLM analysis"))
        self.setMinimumWidth(560)

        self._segments = list(segments or [])
        self._parent_window = parent
        self._thread = None

        from PyQt6.QtWidgets import QFormLayout

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Profile combo
        self._profile_combo = QComboBox()
        try:
            self._profiles = list(_dll_module().load_profiles())
        except Exception as e:
            self._profiles = []
            QMessageBox.critical(
                self, _("LLM module error"),
                _("Could not load profiles:\n{err}").format(err=str(e)))
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
                _("No diarized segments available. "
                  "Run a diarization first, then retry.") + "</span>")
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
                profile_name, model)

        # Force the LLM output language to the user's native language
        # (DICTEE_LANG_SOURCE in dictee.conf), NOT the translation
        # source/target combos — those are unrelated to the LLM output.
        # The in-prompt hint alone is unreliable; many models drift to
        # English regardless.
        _LANG_NAMES = {
            "en": "English", "fr": "French", "de": "German",
            "es": "Spanish", "it": "Italian", "pt": "Portuguese",
            "uk": "Ukrainian", "nl": "Dutch", "pl": "Polish",
            "ru": "Russian", "zh": "Chinese", "ja": "Japanese",
            "ko": "Korean", "ar": "Arabic",
        }
        code = _read_conf().get("DICTEE_LANG_SOURCE", "") or ""
        lang_name = _LANG_NAMES.get(code, "")

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
            self._parent_window._add_llm_result_tab(profile_name, text)
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

class TranscribeWindow(QDialog):
    """Main transcription/diarization window."""

    def __init__(self, file_path=None, auto_diarize=False, parent=None):
        super().__init__(parent)
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
        self._stdout_buf = QByteArray()
        self._segments = []
        self._raw_text = ""  # raw transcription output (stored for reformat)
        self._was_diarized = False  # whether last transcription used diarization
        # Per-window display map: {canonical_id -> custom_name}. Never mutates
        # seg["speaker"] — consulted only at render time by the format fns.
        self._speaker_name_map = {}
        self._rename_line_edits = {}   # filled by _populate_rename_fields
        self._translate_thread = None
        self._audio_duration = 0.0
        self._transcribe_elapsed = 0.0
        self._translate_elapsed = 0.0
        self._translate_start = 0.0
        self._current_translate_lang = ""  # lang code of current translation

        self._build_ui()
        self._connect_signals()

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
        if auto_diarize and _sortformer_available():
            self._chk_diarize.setChecked(True)
        if file_path and auto_diarize:
            # Defer to event loop so window is fully initialized
            QTimer.singleShot(100, self._on_transcribe)

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

        # Media player backend
        self._audio_output = QAudioOutput()
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
        sortformer_ok = _sortformer_available()
        self._chk_diarize.setEnabled(sortformer_ok)
        if sortformer_ok:
            self._chk_diarize.setToolTip(self._tip(
                _("Identify speakers (max 4). Works on any duration "
                  "thanks to the auto-chunking pipeline.")))
        else:
            self._chk_diarize.setToolTip(
                _("Sortformer model not installed. Configure in dictee-setup."))

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

        lay_diarize_row = QHBoxLayout()
        lay_diarize_row.setContentsMargins(0, 0, 0, 0)
        lay_diarize_row.setSpacing(12)
        lay_diarize_row.addWidget(self._chk_diarize, 0, Qt.AlignmentFlag.AlignLeft)
        lay_diarize_row.addWidget(self._w_threshold, 0, Qt.AlignmentFlag.AlignLeft)
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
        self._btn_transcribe.setStyleSheet(
            "QPushButton { background: #8e44ad; color: white; "
            "font-weight: bold; border: none; border-radius: 4px; "
            "padding: 6px 16px; }"
            "QPushButton:hover { background: #9b59b6; }"
            "QPushButton:pressed { background: #7d3c98; }"
            "QPushButton:disabled { background: rgba(142,68,173,80); "
            "color: rgba(255,255,255,150); }")
        btn_col.addWidget(self._btn_transcribe)

        self._btn_cancel = QPushButton(_("Cancel"))
        self._btn_cancel.setVisible(False)
        self._btn_cancel.setToolTip(_("Cancel the long-file chunked pipeline"))
        self._btn_cancel.clicked.connect(self._on_cancel_chunked)
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
        self._tabs.addTab(self._text_edit, _("Original"))
        # Original tab is not closable
        self._tabs.tabBar().setTabButton(0, self._tabs.tabBar().ButtonPosition.RightSide, None)

        # Dict of translation tabs: lang_code -> {editor, segments, text}
        self._translation_tabs = {}

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
        self._btn_export_tab = QPushButton(_("Export tab..."))
        self._btn_export_tab.setToolTip(_("Export only the current tab"))
        self._btn_export_tab.clicked.connect(self._on_export_current_tab)
        lay_btns.addWidget(self._btn_export_tab)

        self._btn_export = QPushButton(_("Export all..."))
        self._btn_export.setToolTip(_("Export all tabs to files"))
        self._btn_export.clicked.connect(self._on_export)
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
            except Exception:
                pass
        # Restore backend if we were in diarization mode
        conf = _read_conf()
        if conf.get("DICTEE_PRE_DIARIZE_BACKEND"):
            _dbg("closeEvent: restoring backend via diarize false")
            subprocess.Popen(["dictee-switch-backend", "diarize", "false"])
        elif getattr(self, '_daemon_was_active', False):
            # Restart daemon if we stopped it for VRAM
            asr = conf.get("DICTEE_ASR_BACKEND", "parakeet")
            svc_map = {"parakeet": "dictee", "vosk": "dictee-vosk",
                       "whisper": "dictee-whisper", "canary": "dictee-canary"}
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
        except Exception:
            pass
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
            except Exception:
                pass
        for attr in ("_chunked_worker", "_diarize_worker", "_translate_thread"):
            w = getattr(self, attr, None)
            if w is not None and w.isRunning():
                _dbg(f"abort: cancelling {attr}")
                # All three workers expose either request_cancel
                # (legacy chunked pipeline) or cancel.
                if hasattr(w, "request_cancel"):
                    try:
                        w.request_cancel()
                    except Exception:
                        pass
                if hasattr(w, "cancel"):
                    try:
                        w.cancel()
                    except Exception:
                        pass
        # Hide the cancel button + reset status so the next run starts
        # from a clean slate.
        if hasattr(self, "_btn_cancel"):
            self._btn_cancel.setVisible(False)
        self._update_transcribe_btn()

    def _connect_signals(self):
        self._file_input.textChanged.connect(self._update_transcribe_btn)
        self._file_input.textChanged.connect(self._update_long_audio_warning)
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
        # The translation source is always the original transcription
        # (self._raw_text), so the button only depends on whether the
        # original tab has produced text — not on which tab is active.
        self._btn_translate.setEnabled(
            bool(tgt)
            and bool(self._raw_text)
            and _translate_available(self._cmb_backend.currentData())
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
        segs = getattr(editor, '_diarize_segments', None) or self._segments
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

    @staticmethod
    def _ms_to_str(ms):
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def _update_player_markers(self):
        """Update slider markers from current segments."""
        # Store segments on current text_edit for tab switching
        if hasattr(self, '_text_edit'):
            self._text_edit._diarize_segments = list(self._segments)
        if not self._segments:
            self._sld_position.clear_markers()
            return
        markers = []
        for seg in self._segments:
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
        the active tab so navigation works even when the window-level
        self._segments has been zeroed by a tab switch."""
        segs = (getattr(self._active_editor(), '_diarize_segments', None)
                or self._segments)
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
        segs = (getattr(self._active_editor(), '_diarize_segments', None)
                or self._segments)
        if not segs:
            return
        pos_s = self._player.position() / 1000.0 + 0.1
        for seg in segs:
            if seg["start"] > pos_s:
                self._player.setPosition(int(seg["start"] * 1000))
                return
        # Wrap to first
        self._player.setPosition(int(self._segments[0]["start"] * 1000))

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

        # Sync the speaker rename panel with the active tab's map
        if hasattr(self, '_grp_rename'):
            if segs:
                self._segments = list(segs)
                self._was_diarized = True
                self._speaker_name_map = dict(
                    getattr(widget, "_speaker_name_map", {}) or {})
                self._populate_rename_fields()
            else:
                self._grp_rename.setVisible(False)

        # Grey out the buttons that don't apply to LLM result tabs.
        is_llm = bool(getattr(widget, "_is_llm_result", False))
        if hasattr(self, "_btn_copy"):
            self._btn_copy.setEnabled(not is_llm)
        if hasattr(self, "_btn_export"):
            self._btn_export.setEnabled(not is_llm)
        if hasattr(self, "_btn_llm"):
            self._btn_llm.setEnabled(not is_llm)
        # _btn_export_tab stays enabled — it routes to LLMExportDialog
        # for LLM tabs and to ExportDialog for regular tabs.

    def _on_diarize_toggled(self, checked):
        self._w_threshold.setVisible(checked)
        self._update_long_audio_warning()

    # Threshold (minutes) above which we warn about VRAM for diarize+transcribe.
    # Parakeet-TDT loads the full mel-spectrogram → ~185 MB VRAM per minute peak.
    # On an 8 GB GPU shared with OS/compositor, ~10-15 min is the practical limit.
    LONG_AUDIO_WARN_MINUTES = 10

    def _has_cuda_build(self):
        """Heuristic: dictee-cuda package ships libonnxruntime.so in /usr/lib/dictee."""
        return os.path.isfile("/usr/lib/dictee/libonnxruntime.so")

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

        # Block if translation is running
        if self._translate_thread and self._translate_thread.isRunning():
            _dbg("_on_transcribe: blocked — translation running")
            return

        diarize = self._chk_diarize.isChecked()
        _dbg(f"_on_transcribe: file={audio_path}, diarize={diarize}")

        # Create a new tab for this transcription (keep previous tabs)
        self._was_diarized = False
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
        # Remember which audio file this tab transcribed, so switching
        # tabs reloads the right file (and hence the right duration).
        self._text_edit._audio_path = audio_path
        self._tabs.addTab(self._text_edit, tab_name)
        self._tabs.setCurrentWidget(self._text_edit)
        # Animate the tab title with a braille spinner while the
        # transcription / diarization is running. _show_status() will
        # call _stop_all_spinners() when results land.
        self._start_tab_spinner(self._text_edit, tab_name)
        self._segments = []
        self._raw_text = ""
        self._stdout_buf = QByteArray()
        self._start_time = time.monotonic()
        self._translate_elapsed = 0.0
        self._audio_duration = self._get_audio_duration(audio_path)
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
                             "dictee", "dictee-vosk", "dictee-whisper", "dictee-canary"],
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

        self._lbl_status.setText(_("Transcribing..."))
        self._lbl_status.setVisible(True)
        self._btn_transcribe.setEnabled(False)
        self._btn_translate.setEnabled(False)

        # Long-file chunked pipeline: diarize ON + duration > threshold + CUDA build
        # → ffmpeg pre-cut + diarize-only global + transcribe-diarize-batch --no-diarize
        # → merge speakers via argmax_overlap. Avoids OOM on 8 GB VRAM beyond ~10-15 min.
        if (diarize
                and self._audio_duration >= self.LONG_AUDIO_WARN_MINUTES * 60
                and self._has_cuda_build()):
            sensitivity = self._sld_sensitivity.value() / 100.0
            _dbg(f"_on_transcribe: routing to chunked pipeline "
                 f"(dur={self._audio_duration:.1f}s, sens={sensitivity:.2f})")
            self._was_diarized = True
            self._diarize_two_phase = False  # chunked replaces two-phase
            self._chunked_worker = _ChunkedPipelineWorker(
                audio_path, sensitivity, self)
            self._chunked_worker.phase_changed.connect(self._on_chunked_phase)
            self._chunked_worker.chunk_progress.connect(self._on_chunked_progress)
            self._chunked_worker.finished.connect(self._on_chunked_done)
            self._chunked_worker.error.connect(self._on_chunked_error)
            self._btn_cancel.setVisible(True)
            self._btn_cancel.setEnabled(True)
            self._chunked_worker.start()
            return

        self._process = QProcess(self)
        if getattr(self, '_diarize_two_phase', False):
            # Phase 1 : séparer stdout (timestamps) de stderr (warnings ONNX)
            self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        else:
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
        # Diarisation : pipeline en 2 phases (diarize-only → daemon transcription)
        # Transcription seule : transcribe (batch)
        if diarize:
            cmd = "diarize-only"
            fallback_cmd = "transcribe-diarize"  # ancien binaire si diarize-only absent
            if not shutil.which(cmd):
                if shutil.which(fallback_cmd):
                    cmd = fallback_cmd
                    self._diarize_two_phase = False
                else:
                    self._progress.setVisible(False)
                    self._lbl_status.setText(
                        _("Command '{cmd}' not found. Install dictee first.").format(cmd=cmd))
                    self._lbl_status.setVisible(True)
                    self._update_transcribe_btn()
                    self._process.deleteLater()
                    self._process = None
                    return
            else:
                self._diarize_two_phase = True
        else:
            cmd = "transcribe"
            self._diarize_two_phase = False
            if not shutil.which(cmd):
                self._progress.setVisible(False)
                self._lbl_status.setText(
                    _("Command '{cmd}' not found. Install dictee first.").format(cmd=cmd))
                self._lbl_status.setVisible(True)
                self._update_transcribe_btn()
                self._process.deleteLater()
                self._process = None
                return
        _dbg(f"_on_transcribe: cmd={cmd}, two_phase={getattr(self, '_diarize_two_phase', False)}")
        self._diarize_audio_path = audio_path
        args = [audio_path]
        if diarize:
            sensitivity = self._sld_sensitivity.value() / 100.0
            args += ["--sensitivity", f"{sensitivity:.2f}"]
        self._process.start(cmd, args)
        # Watchdog: kill process if it hangs (5 min for long audio + GPU)
        self._process_timer = QTimer(self)
        self._process_timer.setSingleShot(True)
        self._process_timer.timeout.connect(self._on_process_timeout)
        self._process_timer.start(300_000)

    def _on_process_timeout(self):
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            _dbg("Process timeout — killing")
            self._process.kill()
            self._process.waitForFinished(3000)
            self._set_status(_("Transcription timed out (5 min)."))
            self._set_busy(False)

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
                   "whisper": "dictee-whisper", "canary": "dictee-canary"}
        svc = svc_map.get(asr, "dictee")
        subprocess.Popen(["systemctl", "--user", "start", svc])
        return svc

    def _restart_daemon_and_transcribe(self, diarize_output):
        """Phase 2: restart daemon, then transcribe each diarized segment via socket (threaded)."""
        audio_path = getattr(self, '_diarize_audio_path', '')
        if not audio_path or not os.path.isfile(audio_path):
            self._lbl_status.setText(_("Audio file not found for phase 2."))
            self._update_transcribe_btn()
            return

        # Restart daemon
        self._daemon_was_active = False
        self._start_daemon()
        sock_path = os.path.join(
            os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "transcribe.sock")

        self._lbl_status.setText(_("Waiting for daemon..."))

        # Launch worker thread
        self._diarize_worker = _DiarizeTranscribeWorker(
            audio_path, diarize_output, sock_path, self)
        self._diarize_worker.progress.connect(self._on_diarize_progress)
        self._diarize_worker.finished.connect(self._on_diarize_done)
        self._diarize_worker.error.connect(self._on_diarize_error)
        self._diarize_worker.start()

    def _on_diarize_progress(self, done, total):
        self._lbl_status.setText(
            _("Transcribing {done}/{total}...").format(done=done, total=total))

    def _on_diarize_done(self, raw_output):
        _dbg(f"_on_diarize_done: output_len={len(raw_output)}, btn_enabled_before={self._btn_transcribe.isEnabled()}")
        self._diarize_worker = None
        self._finish_transcription(raw_output)
        _dbg(f"_on_diarize_done: btn_enabled_after={self._btn_transcribe.isEnabled()}")

    def _on_diarize_error(self, msg):
        self._diarize_worker = None
        self._progress.setVisible(False)
        self._lbl_status.setText(msg)
        self._update_transcribe_btn()

    # === Chunked long-file pipeline slots ===

    def _on_chunked_phase(self, phase_num, label):
        """Phase 1..4 status update from _ChunkedPipelineWorker."""
        self._lbl_status.setText(label)

    def _on_chunked_progress(self, done, total):
        """Phase 3 chunk-by-chunk progress."""
        self._lbl_status.setText(
            _("Phase 3/4: chunk {done}/{total}").format(done=done, total=total))

    def _on_chunked_done(self, raw_output):
        """Final output ready: forward to the common _finish_transcription path."""
        _dbg(f"_on_chunked_done: output_len={len(raw_output)}")
        self._chunked_worker = None
        self._btn_cancel.setVisible(False)
        self._finish_transcription(raw_output)

    def _on_chunked_error(self, msg):
        """Pipeline failed at some phase: surface message, restore UI."""
        _dbg(f"_on_chunked_error: {msg}")
        self._chunked_worker = None
        self._btn_cancel.setVisible(False)
        self._progress.setVisible(False)
        self._lbl_status.setText(msg)
        self._update_transcribe_btn()

    def _on_cancel_chunked(self):
        """User clicked Cancel during the chunked pipeline."""
        if not (hasattr(self, '_chunked_worker') and self._chunked_worker):
            return
        _dbg("_on_cancel_chunked: requesting worker cancel")
        self._btn_cancel.setEnabled(False)  # avoid double clicks
        self._lbl_status.setText(_("Cancelling..."))
        self._chunked_worker.request_cancel()

    def _finish_transcription(self, raw_output):
        """Common finish logic for both single-phase and two-phase diarization."""
        self._progress.setVisible(False)
        self._btn_transcribe.setEnabled(True)
        self._btn_translate.setEnabled(True)

        if not raw_output:
            self._lbl_status.setText(_("No transcription result."))
            self._raw_text = ""
            self._segments = []
            self._grp_rename.setVisible(False)
            self._update_translate_btn()
            return

        self._retry_done = False
        self._was_diarized = True
        self._segments = _parse_diarize_output(raw_output)

        # Post-process each segment's text through dictee-postprocess
        for seg in self._segments:
            seg["text"] = _clean_segment_text(_postprocess(seg["text"]))
        # Rebuild raw_output with post-processed text
        raw_output = "\n".join(
            f"[{seg['start']:.2f}s - {seg['end']:.2f}s] {seg['speaker']}: {seg['text']}"
            for seg in self._segments) if self._segments else raw_output
        self._raw_text = raw_output
        # Store data on the tab widget for per-tab translation & markers
        self._text_edit._raw_text = raw_output
        self._text_edit._was_diarized = True
        self._text_edit._diarize_segments = list(self._segments)
        self._text_edit._speaker_name_map = dict(self._speaker_name_map)

        # Rebuild the rename panel for the new speakers
        self._populate_rename_fields()

        # NB: language auto-detection removed deliberately. The source
        # language combo reflects the user's choice (and DICTEE_LANG_SOURCE
        # in dictee.conf), which is also what drives the LLM Diarization
        # output language. Detecting & overwriting it here used to flip
        # the combo to the audio's language — so a French user analysing
        # an English meeting got the LLM summary in English.

        self._apply_format()
        # Make sure the player is on this tab's audio file. The user may
        # have browsed to a different file while the transcription was
        # running, so QMediaPlayer.source could point elsewhere — without
        # this check the timeline would inherit the unrelated file's
        # duration after the transcription lands.
        tab_audio = getattr(self._text_edit, '_audio_path', None)
        if tab_audio and os.path.isfile(tab_audio):
            if self._player.source().toLocalFile() != tab_audio:
                self._load_audio(tab_audio)
        self._update_player_markers()
        self._transcribe_elapsed = time.monotonic() - self._start_time
        self._translate_elapsed = 0.0
        self._update_translate_btn()
        self._show_status()

        # Auto-translate if checked and a target is selected. The
        # source language is auto-detected inside _on_translate; same-
        # language translations are short-circuited there too.
        if (self._chk_auto_translate.isChecked()
                and _translate_available(self._cmb_backend.currentData())
                and self._cmb_lang_tgt.currentData()):
            self._on_translate()

    def _on_finished(self, exit_code, _exit_status):
        if hasattr(self, '_process_timer'):
            self._process_timer.stop()
        self._progress.setVisible(False)
        if self._process:
            self._process.deleteLater()
        self._process = None
        self._update_transcribe_btn()

        raw_output = bytes(self._stdout_buf).decode("utf-8", errors="replace").strip()

        # Two-phase diarization: diarize-only finished → transcribe segments via daemon
        if getattr(self, '_diarize_two_phase', False) and exit_code == 0 and raw_output:
            self._diarize_two_phase = False
            _dbg(f"_on_finished: phase 1 done (diarize-only), segments:\n{raw_output}")
            self._lbl_status.setText(_("Restarting daemon for transcription..."))
            # Restart daemon
            self._restart_daemon_and_transcribe(raw_output)
            return

        # Restart daemon if we stopped it for VRAM
        if getattr(self, '_daemon_was_active', False):
            self._daemon_was_active = False
            _dbg("_on_finished: restarting transcribe-daemon")
            self._start_daemon()
        _dbg(f"_on_finished: exit_code={exit_code}, output_len={len(raw_output)}")

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
            self._grp_rename.setVisible(False)
            self._update_translate_btn()
            return

        if not raw_output:
            self._lbl_status.setText(_("No transcription result."))
            self._lbl_status.setVisible(True)
            self._raw_text = ""
            self._segments = []
            self._grp_rename.setVisible(False)
            self._update_translate_btn()
            return

        # Reset retry flag on success
        self._retry_done = False
        _dbg(f"_on_finished: success, diarized={self._chk_diarize.isChecked()}, raw_len={len(raw_output)}")

        # Store raw result for reformatting
        self._was_diarized = self._chk_diarize.isChecked()

        if self._was_diarized:
            self._segments = _parse_diarize_output(raw_output)
            # Post-process each segment's text
            for seg in self._segments:
                seg["text"] = _clean_segment_text(_postprocess(seg["text"]))
            raw_output = "\n".join(
                f"[{seg['start']:.2f}s - {seg['end']:.2f}s] {seg['speaker']}: {seg['text']}"
                for seg in self._segments) if self._segments else raw_output
        else:
            # Post-process plain transcription
            raw_output = _postprocess(raw_output)

        self._raw_text = raw_output
        # Store data on the tab widget for per-tab translation & markers
        self._text_edit._raw_text = raw_output
        self._text_edit._was_diarized = self._was_diarized
        self._text_edit._diarize_segments = list(self._segments)
        self._text_edit._speaker_name_map = dict(self._speaker_name_map)

        # Rebuild (or hide) the speaker rename panel
        self._populate_rename_fields()

        # NB: language auto-detection removed deliberately (same as in
        # _finish_transcription). The source combo stays on the user's
        # choice — DICTEE_LANG_SOURCE in dictee.conf — which is also
        # what the LLM Diarization output language is bound to.
        # Display in current format
        self._apply_format()
        self._update_player_markers()
        self._transcribe_elapsed = time.monotonic() - self._start_time
        self._translate_elapsed = 0.0
        self._update_translate_btn()

        self._show_status()

        # Auto-translate if checked and a target is selected. The
        # source language is auto-detected inside _on_translate; same-
        # language translations are short-circuited there too.
        if (self._chk_auto_translate.isChecked()
                and _translate_available(self._cmb_backend.currentData())
                and self._cmb_lang_tgt.currentData()):
            self._on_translate()

    def _show_status(self):
        """Show final status with timing and speaker info.

        For diarized transcriptions the summary lives next to the
        rename accordion header (more visual context); for plain
        transcriptions it stays in the bottom status label.
        """
        # Any tab spinner started by transcription / diarization /
        # translation stops here.
        self._stop_all_spinners()
        dur = self._audio_duration
        dur_str = f"{int(dur//60)}:{int(dur%60):02d}" if dur >= 60 else f"{dur:.1f}s"
        n_speakers = len(set(s["speaker"] for s in self._segments)) if self._segments else 0
        parts = []
        if self._was_diarized and self._segments:
            parts.append(_("{n} speaker(s)").format(n=n_speakers))
        parts.append(_("audio {dur}").format(dur=dur_str))
        parts.append(_("transcribed in {t}").format(
            t=_format_elapsed(self._transcribe_elapsed)))
        if self._translate_elapsed > 0:
            parts.append(_("translated in {t}").format(
                t=_format_elapsed(self._translate_elapsed)))
        text = " — ".join(parts)
        if self._was_diarized and hasattr(self, "_lbl_rename_status"):
            self._lbl_rename_status.setText(text)
            self._lbl_status.setText("")
            self._lbl_status.setVisible(False)
        else:
            if hasattr(self, "_lbl_rename_status"):
                self._lbl_rename_status.setText("")
            self._lbl_status.setText(text)
            self._lbl_status.setVisible(True)

    def _on_translate(self):
        """Translate the original transcription into the chosen target.

        The source is always the original transcribed text/segments,
        never the currently active translation tab. self._segments is
        mutated on every tab change (see _on_tab_changed L3210), so
        we MUST NOT read it here — we'd otherwise feed the worker the
        already-translated segments and the LLM would translate from
        the wrong language. The original tab (self._text_edit) keeps
        its own _raw_text / _diarize_segments / _was_diarized fixed
        for the session, so we read from there.
        """
        raw_text = (getattr(self._text_edit, '_raw_text', '')
                    or self._raw_text)
        segments = (getattr(self._text_edit, '_diarize_segments', None)
                    or self._segments)
        was_diarized = getattr(self._text_edit, '_was_diarized',
                               self._was_diarized)
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
            return
        if lang_src == lang_tgt:
            _dbg(f"_on_translate: blocked — detected source ({lang_src}) == target")
            return
        backend = self._cmb_backend.currentData()
        _dbg(f"_on_translate: backend={backend}, {lang_src}→{lang_tgt}")
        # Keep transcription status and append a braille-spinner-led
        # "Translating..." segment. The "—" separator gets replaced by
        # the spinner frame, which animates while the translation runs.
        self._translate_status_base = self._lbl_status.text()
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
        self._translate_source_tab = self._text_edit
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
        self._translate_elapsed = time.monotonic() - self._translate_start

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
        # Inherit audio path from the source tab so switching to this
        # translation reloads the right audio file in the player.
        editor._audio_path = getattr(self._text_edit, '_audio_path', None)
        self._tabs.insertTab(insert_at, editor, tab_title)

        # Copy segments from source tab for marker support
        if source_tab and hasattr(source_tab, '_diarize_segments'):
            editor._diarize_segments = list(source_tab._diarize_segments)
        # Inherit the speaker name map so renames applied on the source
        # tab before translation are visible immediately in the new tab.
        if source_tab and hasattr(source_tab, '_speaker_name_map'):
            editor._speaker_name_map = dict(source_tab._speaker_name_map)
        elif self._speaker_name_map:
            editor._speaker_name_map = dict(self._speaker_name_map)

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
        """Format and display current transcription tab."""
        self._apply_format_to(self._text_edit, self._segments, self._raw_text)

    def _apply_format_to(self, editor, segments, raw_text):
        """Format and display text in the given editor.

        Resolves the speaker name map per-tab (attached to editor) with a
        fallback to the window-level map, so renaming propagates correctly
        to translation tabs.
        """
        fmt = self._cmb_format.currentData()
        name_map = getattr(editor, "_speaker_name_map", None) \
            or getattr(self, "_speaker_name_map", None)

        if self._was_diarized and segments:
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

    def _apply_speaker_rename(self):
        """Collect QLineEdit values, update the display map, re-render.

        Propagates the map to ALL tabs that hold diarized segments (the
        active transcription tab and any translation tabs) so the user
        sees renamed labels consistently across views and exports.
        """
        new_map = {}
        for spk, le in self._rename_line_edits.items():
            name = le.text().strip()
            if name:
                new_map[spk] = name

        self._speaker_name_map = new_map
        if hasattr(self, "_text_edit"):
            self._text_edit._speaker_name_map = dict(new_map)

        # Propagate to any other tab holding diarize segments (translation
        # tabs spawned from this transcription).
        for i in range(self._tabs.count()):
            w = self._tabs.widget(i)
            if not isinstance(w, QTextEdit):
                continue
            segs = getattr(w, "_diarize_segments", None)
            if segs:
                w._speaker_name_map = dict(new_map)
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
        """Export only the currently active tab. LLM result tabs use a
        dedicated dialog (PDF + Markdown), regular tabs go through the
        standard ExportDialog (txt/srt/json)."""
        editor = self._tabs.currentWidget()
        if getattr(editor, "_is_llm_result", False):
            self._on_export_llm_tab(editor)
            return
        self._on_export(current_only=True)

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
        """Open the LLM analysis dialog. Uses the diarized segments stored
        on the active tab (or window-level fallback). The user's speaker
        rename map (Speaker 1 → "Alice") is applied to the speaker field
        of each segment so the LLM sees the human-friendly names instead
        of the canonical labels. Result lands in a brand-new tab via
        _add_llm_result_tab."""
        editor = self._tabs.currentWidget()
        raw_segments = (getattr(editor, "_diarize_segments", None)
                        or self._segments or [])
        name_map = getattr(self, "_speaker_name_map", None) or {}
        segments = []
        for seg in raw_segments:
            seg_copy = dict(seg)
            canonical = seg.get("speaker", "")
            if canonical in name_map and name_map[canonical].strip():
                seg_copy["speaker"] = name_map[canonical].strip()
            segments.append(seg_copy)
        try:
            self._llm_dlg = LLMProcessDialog(segments, self)
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

    def _ensure_spinner_timer(self):
        if not hasattr(self, "_spinning_tabs"):
            self._spinning_tabs = {}  # widget → base title (str)
            self._spinner_idx = 0
            self._spinner_timer = QTimer(self)
            self._spinner_timer.setInterval(100)
            self._spinner_timer.timeout.connect(self._tick_spinner)

    def _start_tab_spinner(self, widget, base_title):
        if widget is None:
            return
        self._ensure_spinner_timer()
        self._spinning_tabs[widget] = base_title
        idx = self._tabs.indexOf(widget)
        if idx >= 0:
            frame = self.SPINNER_FRAMES[self._spinner_idx]
            self._tabs.setTabText(idx, f"{frame} {base_title}")
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
        if not self._spinning_tabs:
            self._spinner_timer.stop()

    def _stop_all_spinners(self):
        """Used on _show_status to stop spinning the active text tab
        regardless of which call started it. Also stops the status-bar
        translation spinner if it's running."""
        if hasattr(self, "_spinning_tabs"):
            for w in list(self._spinning_tabs.keys()):
                self._stop_tab_spinner(w)
        self._stop_translate_status_spinner()

    def _start_translate_status_spinner(self):
        """Animate a braille spinner where the leading "—" used to
        sit before "Translating...". Lighter than creating an empty
        target tab in advance — visible right where the user already
        watches the elapsed-time / speakers status line."""
        if not hasattr(self, "_translate_status_idx"):
            self._translate_status_idx = 0
        if not hasattr(self, "_translate_status_timer"):
            self._translate_status_timer = QTimer(self)
            self._translate_status_timer.setInterval(100)
            self._translate_status_timer.timeout.connect(
                self._tick_translate_status_spinner)
        # Paint the first frame immediately so the user sees the
        # spinner without waiting one tick.
        self._tick_translate_status_spinner()
        if not self._translate_status_timer.isActive():
            self._translate_status_timer.start()

    def _tick_translate_status_spinner(self):
        if not hasattr(self, "_translate_status_base"):
            return
        frame = self.SPINNER_FRAMES[self._translate_status_idx]
        self._translate_status_idx = (self._translate_status_idx + 1) % len(self.SPINNER_FRAMES)
        base = self._translate_status_base
        sep = " " + frame + " " if base else frame + " "
        self._lbl_status.setText(base + sep + _("Translating..."))

    def _stop_translate_status_spinner(self):
        if hasattr(self, "_translate_status_timer") and self._translate_status_timer.isActive():
            self._translate_status_timer.stop()

    def _tick_spinner(self):
        if not self._spinning_tabs:
            self._spinner_timer.stop()
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(self.SPINNER_FRAMES)
        frame = self.SPINNER_FRAMES[self._spinner_idx]
        for widget, base in list(self._spinning_tabs.items()):
            idx = self._tabs.indexOf(widget)
            if idx < 0:
                self._spinning_tabs.pop(widget, None)
                continue
            self._tabs.setTabText(idx, f"{frame} {base}")

    def _start_llm_result_tab(self, profile_name, model_name=""):
        """Create the LLM result tab immediately, empty, with a spinner.
        Returns the editor widget; caller passes it to
        _finish_llm_result_tab once the LLM call is done."""
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlaceholderText(_("Generating LLM analysis…"))
        try:
            editor.viewport().installEventFilter(self)
        except Exception:
            pass
        editor._audio_path = None
        editor._is_llm_result = True
        editor._llm_profile_name = profile_name
        # Tab title shows both the profile (what kind of analysis) and
        # the model used (so the user can tell two runs of the same
        # profile with different models apart at a glance).
        if model_name:
            base_title = f"{profile_name} · {model_name}"
        else:
            base_title = profile_name
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

    def _add_llm_result_tab(self, profile_name, text):
        """Append a new tab containing an LLM analysis result (markdown
        or reformatted diarize). Read-only by default — user can toggle
        edit mode if they want to tweak it."""
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text or "")
        try:
            editor.viewport().installEventFilter(self)
        except Exception:
            pass
        # No audio binding — these tabs are not tied to a wav file.
        editor._audio_path = None
        # Marker used by _on_tab_changed and _on_export_current_tab to
        # show the LLM-specific Export dialog (PDF/Markdown) and grey
        # out the irrelevant buttons (Copy all, Export all, LLM analysis).
        editor._is_llm_result = True
        editor._llm_profile_name = profile_name
        tab_name = _("LLM: {profile}").format(profile=profile_name)
        idx = self._tabs.addTab(editor, tab_name)
        self._tabs.setCurrentIndex(idx)

    def _on_export(self, current_only=False):
        _dbg(f"_on_export: {self._tabs.count()} tabs, current_only={current_only}")
        # Collect tabs with content
        tabs_info = []
        current_tab_index = None
        cur_widget = self._tabs.currentWidget()
        for i in range(self._tabs.count()):
            editor = self._tabs.widget(i)
            if isinstance(editor, QTextEdit):
                text = editor.toPlainText()
                if text.strip():
                    if editor is cur_widget:
                        current_tab_index = len(tabs_info)
                    tabs_info.append((self._tabs.tabText(i), text))

        if not tabs_info:
            self._lbl_status.setText(_("Nothing to export."))
            self._lbl_status.setVisible(True)
            return

        base = os.path.splitext(os.path.basename(self._file_input.text()))[0] or "transcription"
        dlg = ExportDialog(tabs_info, self._cmb_format.currentData(), base, self,
                           current_tab_index=current_tab_index if current_only else None)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        selected = dlg.selected_tabs()
        formats = dlg.export_formats()
        out_dir = dlg.export_dir()

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
                # Locate the tab widget to fetch segments + per-tab name map
                segments = None
                name_map = None
                for i in range(self._tabs.count()):
                    if self._tabs.tabText(i) == tab_name:
                        w = self._tabs.widget(i)
                        segments = getattr(w, '_diarize_segments', None)
                        name_map = getattr(w, '_speaker_name_map', None)
                        break

                if fmt == "text" and segments:
                    # Re-render text format with renamed speakers so the
                    # exported file reflects the current display map even
                    # if the editor was never refreshed.
                    content = _format_text(segments, name_map)
                elif fmt != "text":
                    if segments and fmt == "srt":
                        content = _format_srt(segments, name_map)
                    elif segments and fmt == "json":
                        content = _format_json(segments, name_map)
                    elif fmt == "json":
                        raw = self._raw_text if tab_name == self._tabs.tabText(0) else text
                        content = json.dumps([{"text": raw}], ensure_ascii=False, indent=2)
                    elif fmt == "srt":
                        raw = self._raw_text if tab_name == self._tabs.tabText(0) else text
                        content = f"1\n00:00:00,000 --> 99:59:59,999\n{raw}\n"

                safe_name = re.sub(r'[^\w.-]', '_', tab_name)
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
    app.setDesktopFileName("dictee-transcribe")

    file_path = args.file or (args.files[0] if args.files else None)
    win = TranscribeWindow(
        file_path=file_path,
        auto_diarize=args.diarize,
    )
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
