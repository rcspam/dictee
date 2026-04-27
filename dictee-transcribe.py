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
        QMessageBox,
    )
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
        QMessageBox,
    )
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
class _ClickSlider(QSlider):
    """QSlider with click-to-seek and speaker segment markers."""
    sliderClicked = Signal(int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._markers = []   # list of (start_ms, end_ms, QColor)
        self._setMinimumHeight(28)

    def _setMinimumHeight(self, h):
        self.setMinimumHeight(h)

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

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._markers or self.maximum() <= self.minimum():
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
        # Draw colored bars for each segment (semi-transparent)
        for start_ms, end_ms, color in self._markers:
            x1 = int((start_ms - self.minimum()) / rng * self.width())
            x2 = int((end_ms - self.minimum()) / rng * self.width())
            bar_color = QColor(color)
            bar_color.setAlpha(60)
            p.fillRect(x1, 0, max(x2 - x1, 2), h, bar_color)
        # Draw triangle markers at segment starts
        for start_ms, _end_ms, color in self._markers:
            x = int((start_ms - self.minimum()) / rng * self.width())
            tri = QPolygonF([
                QPointF(x - 4, 0), QPointF(x + 4, 0), QPointF(x, 7)])
            p.setPen(QPen(color, 1))
            p.setBrush(color)
            p.drawPolygon(tri)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            val = QSlider.minimum(self) + (
                (QSlider.maximum(self) - QSlider.minimum(self))
                * event.position().x() / self.width())
            self.setValue(int(val))
            self.sliderClicked.emit(int(val))
            event.accept()
        else:
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

        # Wait for socket (max 15s)
        for _ in range(60):
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

        # Transcribe full audio via daemon with timestamps (diarize mode)
        _dbg(f"DiarizeWorker: sending full audio to daemon: {daemon_path}")
        full_text = ""
        try:
            s = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
            s.settimeout(120)
            s.connect(self._sock_path)
            s.sendall((daemon_path + "\tdiarize\n").encode())
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            s.close()
            full_text = data.decode("utf-8", errors="replace").strip()
        except Exception as e:
            self.error.emit(f"Daemon transcription failed: {e}")
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

                translated_segments = [dict(s) for s in self._segments]
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

        _big = "font-size: 24px;"

        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedWidth(36)
        self._btn_play.setToolTip(_("Play / Pause"))
        self._btn_play.clicked.connect(self._on_play_pause)
        lay_player.addWidget(self._btn_play)

        self._btn_stop = QPushButton("⏹")
        self._btn_stop.setFixedWidth(36)
        self._btn_stop.setStyleSheet(_big)
        self._btn_stop.setToolTip(_("Stop"))
        self._btn_stop.clicked.connect(self._on_player_stop)
        lay_player.addWidget(self._btn_stop)

        self._btn_prev_seg = QPushButton("⏮")
        self._btn_prev_seg.setFixedWidth(36)
        self._btn_prev_seg.setStyleSheet(_big)
        self._btn_prev_seg.setToolTip(_("Previous speaker segment"))
        self._btn_prev_seg.clicked.connect(self._on_prev_segment)
        lay_player.addWidget(self._btn_prev_seg)

        self._btn_next_seg = QPushButton("⏭")
        self._btn_next_seg.setFixedWidth(36)
        self._btn_next_seg.setStyleSheet(_big)
        self._btn_next_seg.setToolTip(_("Next speaker segment"))
        self._btn_next_seg.clicked.connect(self._on_next_segment)
        lay_player.addWidget(self._btn_next_seg)

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

        # -- Options: row 1 — diarization + sensitivity + format --
        lay_opts = QHBoxLayout()

        self._chk_diarize = ToggleSwitch(_("Speaker identification (diarization)"))
        sortformer_ok = _sortformer_available()
        self._chk_diarize.setEnabled(sortformer_ok)
        if sortformer_ok:
            self._chk_diarize.setToolTip(
                _("Identify speakers (max 4). Recommended for recordings under 5 minutes."))
        else:
            self._chk_diarize.setToolTip(
                _("Sortformer model not installed. Configure in dictee-setup."))
        lay_opts.addWidget(self._chk_diarize)

        # Sensitivity slider (visible only when diarization is checked)
        self._lbl_sensitivity = QLabel(_("Threshold:"))
        self._sld_sensitivity = QSlider(Qt.Orientation.Horizontal)
        self._sld_sensitivity.setRange(0, 100)
        self._sld_sensitivity.setValue(50)
        self._sld_sensitivity.setFixedWidth(120)
        self._sld_sensitivity.setToolTip(
            _("Speaker detection threshold.\n"
              "← Low: more sensitive, detects more speakers\n"
              "     (may split one person into two speakers).\n"
              "→ High: stricter, detects fewer speakers\n"
              "     (may merge two people into one speaker).\n"
              "Default (50%) works well for most recordings."))
        self._lbl_sensitivity_val = QLabel("50%")
        self._lbl_sensitivity_val.setFixedWidth(35)
        self._sld_sensitivity.valueChanged.connect(
            lambda v: self._lbl_sensitivity_val.setText(f"{v}%"))
        lay_opts.addWidget(self._lbl_sensitivity)
        lay_opts.addWidget(self._sld_sensitivity)
        lay_opts.addWidget(self._lbl_sensitivity_val)
        # Initially hidden
        self._lbl_sensitivity.setVisible(False)
        self._sld_sensitivity.setVisible(False)
        self._lbl_sensitivity_val.setVisible(False)
        self._chk_diarize.toggled.connect(self._on_diarize_toggled)

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

        # -- Long-audio warning (shown when diarization + long file + CUDA build) --
        self._lbl_long_audio_warning = QLabel("")
        self._lbl_long_audio_warning.setWordWrap(True)
        self._lbl_long_audio_warning.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_long_audio_warning.setStyleSheet(
            "QLabel { color: #d68910; background: #fef5e7; "
            "border: 1px solid #f39c12; border-radius: 4px; padding: 6px; }")
        self._lbl_long_audio_warning.setVisible(False)
        layout.addWidget(self._lbl_long_audio_warning)

        # -- Options: row 2 — auto-translate --
        lay_opts2 = QHBoxLayout()
        self._chk_auto_translate = ToggleSwitch(_("Auto-translate the transcription"))
        self._chk_auto_translate.setToolTip(
            _("Automatically translate after transcription"))
        lay_opts2.addWidget(self._chk_auto_translate)
        lay_opts2.addStretch()
        layout.addLayout(lay_opts2)

        # -- Options: row 3 — sync slider/text bidirectional --
        lay_opts3 = QHBoxLayout()
        qs_sync = QSettings("dictee", "transcribe")
        self._chk_follow_text = ToggleSwitch(_("Follow playback in text"))
        self._chk_follow_text.setToolTip(
            _("Move text cursor in real time during audio playback"))
        self._chk_follow_text.setChecked(
            qs_sync.value("sync/follow_text", False, type=bool))
        self._chk_follow_text.toggled.connect(
            lambda v: QSettings("dictee", "transcribe").setValue("sync/follow_text", v))
        lay_opts3.addWidget(self._chk_follow_text)

        self._chk_play_on_click = ToggleSwitch(_("Auto-play on text click"))
        self._chk_play_on_click.setToolTip(
            _("Start playback when clicking on a segment in the text"))
        self._chk_play_on_click.setChecked(
            qs_sync.value("sync/play_on_click", False, type=bool))
        self._chk_play_on_click.toggled.connect(
            lambda v: QSettings("dictee", "transcribe").setValue("sync/play_on_click", v))
        lay_opts3.addWidget(self._chk_play_on_click)

        self._chk_highlight_current = ToggleSwitch(_("Highlight current segment"))
        self._chk_highlight_current.setToolTip(
            _("Underline the segment matching the audio position"))
        self._chk_highlight_current.setChecked(
            qs_sync.value("sync/highlight_current", False, type=bool))
        self._chk_highlight_current.toggled.connect(
            lambda v: QSettings("dictee", "transcribe").setValue("sync/highlight_current", v))
        lay_opts3.addWidget(self._chk_highlight_current)

        lay_opts3.addStretch()
        layout.addLayout(lay_opts3)

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
        def _open_setup_translation():
            env = dict(os.environ)
            env["QT_QPA_PLATFORMTHEME"] = "kde"
            subprocess.Popen(["dictee-setup", "--translation"], env=env)
        btn_setup_trans.clicked.connect(_open_setup_translation)
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

        # Cancel button — only visible during the chunked long-file pipeline
        self._btn_cancel = QPushButton(_("Cancel"))
        self._btn_cancel.setVisible(False)
        self._btn_cancel.setToolTip(_("Cancel the long-file chunked pipeline"))
        self._btn_cancel.clicked.connect(self._on_cancel_chunked)
        lay_action.addWidget(self._btn_cancel)

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

        # -- Speaker rename panel (visible only after diarization) --
        self._build_rename_section(layout)

        # -- Tab widget: Original + dynamic translation tabs --
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(False)
        self._text_edit.setPlaceholderText(_("Transcription results will appear here..."))
        self._text_edit.setToolTip(_("Editable transcription text. Ctrl+F to search, Ctrl+Z to undo."))
        self._text_edit.viewport().installEventFilter(self)
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

        self._btn_export = QPushButton(_("Export all..."))
        self._btn_export.setToolTip(_("Export all tabs to files"))
        self._btn_export.clicked.connect(self._on_export)
        lay_btns.addWidget(self._btn_export)

        self._btn_export_tab = QPushButton(_("Export tab..."))
        self._btn_export_tab.setToolTip(_("Export only the current tab"))
        self._btn_export_tab.clicked.connect(self._on_export_current_tab)
        lay_btns.addWidget(self._btn_export_tab)

        lay_btns.addStretch()

        self._btn_close = QPushButton(_("Close"))
        self._btn_close.setToolTip(_("Close this window"))
        self._btn_close.clicked.connect(self.close)
        lay_btns.addWidget(self._btn_close)

        layout.addLayout(lay_btns)

    def closeEvent(self, event):
        """Clean up processes on window close."""
        self._player.stop()
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            _dbg("closeEvent: killing transcription process")
            self._process.kill()
            self._process.waitForFinished(3000)
        if self._translate_thread and self._translate_thread.isRunning():
            _dbg("closeEvent: waiting for translation thread")
            self._translate_thread.wait(5000)
        if hasattr(self, '_diarize_worker') and self._diarize_worker and self._diarize_worker.isRunning():
            _dbg("closeEvent: waiting for diarize worker")
            self._diarize_worker.wait(5000)
        if hasattr(self, '_chunked_worker') and self._chunked_worker and self._chunked_worker.isRunning():
            _dbg("closeEvent: cancelling chunked worker")
            self._chunked_worker.request_cancel()
            self._chunked_worker.wait(5000)
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
        """Close a tab (all tabs are closable)."""
        self._tabs.removeTab(index)

    def _connect_signals(self):
        self._file_input.textChanged.connect(self._update_transcribe_btn)
        self._file_input.textChanged.connect(self._update_long_audio_warning)
        self._cmb_format.currentIndexChanged.connect(self._on_format_changed)
        self._cmb_lang_src.currentIndexChanged.connect(self._on_lang_changed)
        self._cmb_lang_tgt.currentIndexChanged.connect(self._on_lang_changed)
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
        the click to the previously-active segment."""
        if event.type() == QEvent.Type.MouseButtonRelease:
            parent = obj.parent() if hasattr(obj, 'parent') else None
            if isinstance(parent, QTextEdit):
                # Qt6 uses event.position() (QPointF); fall back to pos()
                # for older bindings.
                point = (event.position().toPoint()
                         if hasattr(event, 'position')
                         else event.pos())
                cursor_at_click = parent.cursorForPosition(point)
                self._on_text_clicked(parent, cursor_at_click.position())
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

    def _move_text_cursor_to_segment(self, editor, seg):
        """Position the cursor at the start of the segment's rendered text
        and centre it vertically in the viewport. Uses _segment_positions
        populated by _apply_format_to (plain colored, SRT and JSON)."""
        positions = getattr(editor, '_segment_positions', None)
        if not positions:
            return
        for p in positions:
            if abs(p["seg"]["start"] - seg["start"]) < 0.01:
                cursor = editor.textCursor()
                cursor.setPosition(p["start"])
                editor.setTextCursor(cursor)
                # centerCursor() centres the cursor line vertically; falls
                # back to a no-op if the document is shorter than the
                # viewport. ensureCursorVisible() merely scrolled the
                # minimum amount, leaving the segment at the top or bottom.
                editor.centerCursor()
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
        """Jump to previous speaker segment start."""
        if not self._segments:
            return
        pos_s = self._player.position() / 1000.0 - 0.1
        for seg in reversed(self._segments):
            if seg["start"] < pos_s:
                self._player.setPosition(int(seg["start"] * 1000))
                return
        # Wrap to last
        self._player.setPosition(int(self._segments[-1]["start"] * 1000))

    def _on_next_segment(self):
        """Jump to next speaker segment start."""
        if not self._segments:
            return
        pos_s = self._player.position() / 1000.0 + 0.1
        for seg in self._segments:
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

    def _on_diarize_toggled(self, checked):
        self._lbl_sensitivity.setVisible(checked)
        self._sld_sensitivity.setVisible(checked)
        self._lbl_sensitivity_val.setVisible(checked)
        self._update_long_audio_warning()

    # Threshold (minutes) above which we warn about VRAM for diarize+transcribe.
    # Parakeet-TDT loads the full mel-spectrogram → ~185 MB VRAM per minute peak.
    # On an 8 GB GPU shared with OS/compositor, ~10-15 min is the practical limit.
    LONG_AUDIO_WARN_MINUTES = 10

    def _has_cuda_build(self):
        """Heuristic: dictee-cuda package ships libonnxruntime.so in /usr/lib/dictee."""
        return os.path.isfile("/usr/lib/dictee/libonnxruntime.so")

    def _update_long_audio_warning(self):
        """Show a warning when file duration + diarization + CUDA may cause OOM."""
        try:
            path = self._file_input.text().strip()
        except AttributeError:
            return
        if not path or not os.path.isfile(path):
            self._lbl_long_audio_warning.setVisible(False)
            return
        if not self._chk_diarize.isChecked() or not self._has_cuda_build():
            self._lbl_long_audio_warning.setVisible(False)
            return
        dur_s = self._get_audio_duration(path)
        if dur_s < self.LONG_AUDIO_WARN_MINUTES * 60:
            self._lbl_long_audio_warning.setVisible(False)
            return
        minutes = int(dur_s // 60)
        self._lbl_long_audio_warning.setText(
            _("ℹ Long file detected ({min} min). The chunked pipeline will be "
              "used automatically: ffmpeg pre-cut into 2-min chunks with 15-s "
              "overlap, global diarization on the full file, then chunked "
              "transcription. This avoids out-of-memory errors on GPUs with "
              "less than 10 GB of VRAM.").format(min=minutes))
        self._lbl_long_audio_warning.setVisible(True)

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
        self._text_edit.setReadOnly(False)
        self._text_edit.setPlaceholderText(
            _("Transcription results will appear here..."))
        self._text_edit.viewport().installEventFilter(self)
        self._tabs.addTab(self._text_edit, tab_name)
        self._tabs.setCurrentWidget(self._text_edit)
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
            seg["text"] = _postprocess(seg["text"])
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

        # Auto-detect language
        detect_text = " ".join(seg["text"] for seg in self._segments) if self._segments else raw_output
        detected = _detect_language(detect_text)
        _dbg(f"_finish_transcription: detected language={detected}")
        for i in range(self._cmb_lang_src.count()):
            if self._cmb_lang_src.itemData(i) == detected:
                self._cmb_lang_src.setCurrentIndex(i)
                break
        if self._cmb_lang_tgt.currentData() == detected:
            import locale as _locale
            conf = _read_conf()
            fallback = conf.get("DICTEE_LANG_TARGET", "")
            if not fallback or fallback == detected:
                sys_lang = _locale.getlocale()[0]
                if sys_lang:
                    fallback = sys_lang.split("_")[0]
            if fallback and fallback != detected:
                for i in range(self._cmb_lang_tgt.count()):
                    if self._cmb_lang_tgt.itemData(i) == fallback:
                        self._cmb_lang_tgt.setCurrentIndex(i)
                        break

        self._apply_format()
        self._update_player_markers()
        self._transcribe_elapsed = time.monotonic() - self._start_time
        self._translate_elapsed = 0.0
        self._update_translate_btn()
        self._show_status()

        # Auto-translate if checked and languages differ
        if (self._chk_auto_translate.isChecked()
                and _translate_available()
                and self._cmb_lang_src.currentData() != self._cmb_lang_tgt.currentData()):
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
                seg["text"] = _postprocess(seg["text"])
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
        self._update_player_markers()
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
        """Translate the currently active tab."""
        # Get data from current tab widget
        widget = self._tabs.currentWidget()
        raw_text = getattr(widget, '_raw_text', '') if widget else ''
        segments = getattr(widget, '_diarize_segments', []) if widget else []
        was_diarized = getattr(widget, '_was_diarized', False) if widget else False
        if not raw_text and not segments:
            # Fallback to instance state
            raw_text = self._raw_text
            segments = self._segments
            was_diarized = self._was_diarized
        if not raw_text:
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
        # Remember which tab we're translating from
        self._translate_source_tab = widget
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

        # Build tab name: "SourceTab → Lang"
        source_tab = getattr(self, '_translate_source_tab', None)
        source_idx = self._tabs.indexOf(source_tab) if source_tab else -1
        if source_idx >= 0:
            source_name = self._tabs.tabText(source_idx)
            tab_title = f"{source_name} → {lang_name}"
            insert_at = source_idx + 1
            # Skip any existing translation tabs after the source
            while insert_at < self._tabs.count():
                t = self._tabs.tabText(insert_at)
                if "→" in t and t.startswith(source_name):
                    insert_at += 1
                else:
                    break
        else:
            tab_title = lang_name
            insert_at = self._tabs.count()

        # Create new translation tab inserted right after source
        editor = QTextEdit()
        editor.setReadOnly(False)
        editor.setToolTip(_("Editable translation text. Ctrl+F to search, Ctrl+Z to undo."))
        editor.viewport().installEventFilter(self)
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

        # Store and display
        if translated_segments:
            editor._diarize_segments = list(translated_segments)
            self._apply_format_to(editor, translated_segments, None)
        elif translated_text:
            editor._raw_text = translated_text
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

    def _compute_segment_positions(self, editor, segments):
        """Build [{start, end, seg}, ...] in editor.toPlainText() coordinates.
        Searches each segment's text in order, advancing the cursor so that
        repeated phrases match the right occurrence. Stored on the editor
        for tab safety (one mapping per tab)."""
        text = editor.toPlainText()
        positions = []
        cursor_pos = 0
        for seg in segments:
            snippet = (seg.get("text") or "").strip()
            if not snippet:
                continue
            idx = text.find(snippet, cursor_pos)
            if idx < 0:
                # Defensive: the formatter may have reordered or escaped;
                # try a global search from the start.
                idx = text.find(snippet)
                if idx < 0:
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
        self._grp_rename = QGroupBox(_("Renommer les locuteurs"))
        self._grp_rename.setVisible(False)
        gv = QVBoxLayout(self._grp_rename)
        gv.setSpacing(4)
        gv.setContentsMargins(8, 6, 8, 6)

        # Two-column grid: up to 4 speakers fit on 2 rows × 2 cols.
        self._rename_rows_layout = QGridLayout()
        self._rename_rows_layout.setHorizontalSpacing(16)
        self._rename_rows_layout.setVerticalSpacing(3)
        gv.addLayout(self._rename_rows_layout)

        lay_btns = QHBoxLayout()
        self._btn_rename_apply = QPushButton(_("Appliquer"))
        self._btn_rename_apply.setToolTip(_(
            "Remplace les libellés des locuteurs dans toutes les vues et "
            "exports (texte, SRT, JSON). Ne modifie pas les données brutes."))
        self._btn_rename_apply.clicked.connect(self._apply_speaker_rename)
        self._btn_rename_reset = QPushButton(_("Réinitialiser"))
        self._btn_rename_reset.setToolTip(_(
            "Efface les noms personnalisés et revient aux libellés "
            "génériques Speaker 0, Speaker 1, etc."))
        self._btn_rename_reset.clicked.connect(self._reset_speaker_rename)
        lay_btns.addWidget(self._btn_rename_apply)
        lay_btns.addWidget(self._btn_rename_reset)
        lay_btns.addStretch()
        gv.addLayout(lay_btns)

        parent_layout.addWidget(self._grp_rename)

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

        if new_map:
            self._lbl_status.setText(_("Noms des locuteurs appliqués."))
        else:
            self._lbl_status.setText(_("Libellés par défaut restaurés."))
        self._lbl_status.setVisible(True)

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
        """Export only the currently active tab."""
        self._on_export(current_only=True)

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
    args = parser.parse_args()

    global DEBUG
    if args.debug or os.environ.get("DICTEE_DEBUG") == "true":
        DEBUG = True
        _dbg("dictee-transcribe starting (debug via %s)" % ("--debug" if args.debug else "DICTEE_DEBUG"))

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
