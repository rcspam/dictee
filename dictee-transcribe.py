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

try:
    from PyQt6.QtCore import Qt, QProcess, QByteArray
    from PyQt6.QtGui import QIcon, QShortcut, QKeySequence, QTextDocument
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QComboBox, QProgressBar, QCheckBox,
        QPlainTextEdit, QFileDialog, QLineEdit, QWidget,
    )
except ImportError:
    from PySide6.QtCore import Qt, QProcess, QByteArray
    from PySide6.QtGui import QIcon, QShortcut, QKeySequence, QTextDocument
    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QComboBox, QProgressBar, QCheckBox,
        QPlainTextEdit, QFileDialog, QLineEdit, QWidget,
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

# === Constants ===

AUDIO_FILTER = _("Audio files") + " (*.wav *.mp3 *.flac *.ogg *.m4a *.webm *.opus);;All files (*)"

DIARIZE_RE = re.compile(
    r"\[(\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]\s*(Speaker\s+\d+|UNKNOWN):\s*(.*)"
)


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
    """Format diarized segments as plain text."""
    return "\n".join(f"{seg['speaker']}: {seg['text']}" for seg in segments)


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
    """Ephemeral search bar for QPlainTextEdit."""

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


# === Main Window ===

class TranscribeWindow(QDialog):
    """Main transcription/diarization window."""

    def __init__(self, file_path=None, auto_diarize=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Dictee - Transcribe file"))
        self.setMinimumSize(600, 500)
        self.resize(700, 550)

        self._process = None
        self._stdout_buf = QByteArray()
        self._segments = []

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

        # -- Transcribe button --
        lay_action = QHBoxLayout()
        lay_action.addStretch()
        self._btn_transcribe = QPushButton(_("Transcribe"))
        self._btn_transcribe.setEnabled(False)
        self._btn_transcribe.setToolTip(_("Start transcription of the selected file"))
        self._btn_transcribe.clicked.connect(self._on_transcribe)
        lay_action.addWidget(self._btn_transcribe)
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

        # -- Text editor --
        self._text_edit = QPlainTextEdit()
        self._text_edit.setReadOnly(False)
        self._text_edit.setPlaceholderText(_("Transcription results will appear here..."))
        self._text_edit.setToolTip(_("Editable transcription text. Ctrl+F to search, Ctrl+Z to undo."))
        layout.addWidget(self._text_edit, 1)

        # -- Search bar --
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

    def _connect_signals(self):
        self._file_input.textChanged.connect(self._update_transcribe_btn)

        # Ctrl+F -> search bar
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self._search_bar.activate)

        # Escape -> close search bar if visible, else close window
        esc = QShortcut(QKeySequence("Escape"), self)
        esc.activated.connect(self._on_escape)

    def _update_transcribe_btn(self):
        has_file = bool(self._file_input.text().strip())
        not_running = self._process is None
        self._btn_transcribe.setEnabled(has_file and not_running)

    def _on_escape(self):
        if self._search_bar.isVisible():
            self._search_bar.hide()
        else:
            self.close()

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _("Select audio file"), "", AUDIO_FILTER)
        if path:
            self._file_input.setText(path)

    def _on_transcribe(self):
        audio_path = self._file_input.text().strip()
        if not audio_path or not os.path.isfile(audio_path):
            self._lbl_status.setText(_("File not found."))
            self._lbl_status.setVisible(True)
            return

        diarize = self._chk_diarize.isChecked()

        self._text_edit.clear()
        self._segments = []
        self._stdout_buf = QByteArray()
        self._progress.setVisible(True)
        self._lbl_status.setText(_("Transcribing..."))
        self._lbl_status.setVisible(True)
        self._btn_transcribe.setEnabled(False)

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.finished.connect(self._on_finished)

        if diarize:
            self._process.start("transcribe-diarize", [audio_path])
        else:
            self._process.start("transcribe", [audio_path])

    def _on_stdout(self):
        data = self._process.readAllStandardOutput()
        self._stdout_buf.append(data)

    def _on_finished(self, exit_code, _exit_status):
        self._progress.setVisible(False)
        self._process = None
        self._update_transcribe_btn()

        raw_output = bytes(self._stdout_buf).decode("utf-8", errors="replace").strip()

        if exit_code != 0:
            self._lbl_status.setText(
                _("Transcription failed (exit code {code}).").format(code=exit_code))
            if raw_output:
                self._text_edit.setPlainText(raw_output)
            return

        if not raw_output:
            self._lbl_status.setText(_("No transcription result."))
            return

        diarize = self._chk_diarize.isChecked()
        fmt = self._cmb_format.currentData()

        if diarize:
            self._segments = _parse_diarize_output(raw_output)
            if not self._segments:
                # Fallback: show raw output
                self._text_edit.setPlainText(raw_output)
            elif fmt == "srt":
                self._text_edit.setPlainText(_format_srt(self._segments))
            elif fmt == "json":
                self._text_edit.setPlainText(_format_json(self._segments))
            else:
                self._text_edit.setPlainText(_format_text(self._segments))
        else:
            if fmt == "json":
                self._text_edit.setPlainText(json.dumps(
                    [{"text": raw_output}], ensure_ascii=False, indent=2))
            elif fmt == "srt":
                self._text_edit.setPlainText(
                    f"1\n00:00:00,000 --> 99:59:59,999\n{raw_output}\n")
            else:
                self._text_edit.setPlainText(raw_output)

        n_speakers = len(set(s["speaker"] for s in self._segments)) if self._segments else 0
        if diarize and self._segments:
            self._lbl_status.setText(
                _("Transcription complete - {n} speaker(s) identified.").format(n=n_speakers))
        else:
            self._lbl_status.setText(_("Transcription complete."))

    def _on_copy(self):
        text = self._text_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._lbl_status.setText(_("Copied to clipboard."))
            self._lbl_status.setVisible(True)

    def _on_export(self):
        fmt = self._cmb_format.currentData()
        ext_map = {"text": ".txt", "srt": ".srt", "json": ".json"}
        filter_map = {
            "text": _("Text files") + " (*.txt)",
            "srt": _("SRT subtitles") + " (*.srt)",
            "json": _("JSON files") + " (*.json)",
        }
        default_ext = ext_map.get(fmt, ".txt")
        file_filter = filter_map.get(fmt, _("All files") + " (*)")

        # Suggest filename based on input
        base = os.path.splitext(os.path.basename(self._file_input.text()))[0]
        suggested = f"{base}-transcription{default_ext}" if base else f"transcription{default_ext}"

        path, _ = QFileDialog.getSaveFileName(
            self, _("Export transcription"), suggested, file_filter)
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._text_edit.toPlainText())
                self._lbl_status.setText(_("Exported to {path}").format(path=path))
                self._lbl_status.setVisible(True)
            except OSError as e:
                self._lbl_status.setText(_("Export failed: {error}").format(error=str(e)))
                self._lbl_status.setVisible(True)


# === Main ===

def main():
    parser = argparse.ArgumentParser(description="Dictee - Transcribe audio files")
    parser.add_argument("--file", "-f", help="Audio file to transcribe")
    parser.add_argument("--diarize", "-d", action="store_true",
                        help="Enable speaker diarization")
    args = parser.parse_args()

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
