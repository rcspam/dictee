#!/usr/bin/env python3
"""The meeting window's cancel-and-restart button.

After Stop the window could only analyse or close: starting over meant
closing it and opening it again, the recording left on disk. The button
after the analysis one cancels the meeting, during the recording or after
it: once confirmed, the meeting stops, its folder is deleted and the same
window is back where it was before Play, ready for another meeting.

The window runs offscreen with its own HOME and meetings folder, its live
preview, Do Not Disturb and loudness normalization switched off, and its
state file moved out of /dev/shm. It records the default microphone for a
second or two, into that temporary folder. The confirmation dialog is a
stand-in.

Local only: skips without PipeWire (pactl, pw-record).
Run: python3 tests/offscreen-check_meeting_restart.py [-v]
"""

import importlib.util
import os
import pathlib
import shutil
import sys
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "dictee-meeting-live")
TMP = None


def setUpModule():
    global TMP
    for tool in ("pactl", "pw-record"):
        if shutil.which(tool) is None:
            raise unittest.SkipTest(f"{tool} missing")
    TMP = tempfile.mkdtemp(prefix="dictee-meeting-restart-")
    os.environ["HOME"] = TMP
    os.environ["DICTEE_MEETING_DIR"] = os.path.join(TMP, "meetings")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    conf = os.path.join(TMP, ".config", "dictee.conf")
    os.makedirs(os.path.dirname(conf))
    with open(conf, "w") as f:
        f.write("DICTEE_MEETING_AUDIO_SOURCE=\nDICTEE_MEETING_ALWAYS_ON_TOP=false\n")


def tearDownModule():
    if TMP:
        shutil.rmtree(TMP, ignore_errors=True)


class RestartButton(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        loader = SourceFileLoader("dictee_meeting_live", SCRIPT)
        mod = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(mod)
        cls.state = os.path.join(TMP, "dictee_state")
        state = cls.state

        class _Path(type(pathlib.Path())):
            def __init__(self, *args):
                if args and str(args[0]) == "/dev/shm/.dictee_state":
                    args = (state,) + args[1:]
                super().__init__(*args)

        mod.Path = _Path
        W = mod.MeetingWindow
        W._start_live_preview = lambda self: None
        W._inhibit_notifications = lambda self: None
        W._uninhibit_notifications = lambda self: None
        W._normalize_recording = lambda self: None
        cls.answer = False
        W._confirm_restart = lambda self: RestartButton.answer
        cls.mod = mod

    def spin(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.app.processEvents()
            time.sleep(0.02)

    def setUp(self):
        RestartButton.answer = False
        self.win = self.mod.MeetingWindow()
        self.win.show()
        self.spin(0.5)

    def tearDown(self):
        self.win.close()
        self.spin(0.5)

    def record(self, seconds=1.5):
        self.win.btn_start.click()
        self.spin(seconds)
        self.assertEqual(self.win._state, "recording")
        return pathlib.Path(self.win.meeting_dir)

    def test_the_analysis_button_shows_a_notepad(self):
        self.assertEqual(self.win.btn_analyze.text(), "\U0001F4DD")

    def test_nothing_to_cancel_before_a_meeting(self):
        self.assertFalse(self.win.btn_restart.isEnabled())

    def test_keep_leaves_the_meeting_recording(self):
        folder = self.record()
        self.assertTrue(self.win.btn_restart.isEnabled())
        self.win.btn_restart.click()
        self.spin(0.5)
        self.assertEqual(self.win._state, "recording")
        self.assertTrue(folder.is_dir())

    def assert_fresh(self, folder):
        """The meeting is gone and the same window is ready for another."""
        self.assertFalse(folder.exists(), "the cancelled meeting is still on disk")
        self.assertIsNone(self.win.audio_worker, "the recording was not stopped")
        self.assertEqual(self.win._state, "idle")
        self.assertTrue(self.win.btn_start.isEnabled())
        self.assertFalse(self.win.btn_restart.isEnabled())
        self.assertEqual(self.win.duration_label.text(), "00:00")
        self.assertEqual(self.win.transcript_view.toPlainText(), "")
        self.assertIsNone(self.win.meeting_dir)
        with open(self.state) as f:
            self.assertEqual(f.read().strip(), "idle")
        # and it records again (the folder name may come back: it is made
        # of the minute and the title)
        again = self.record()
        self.assertTrue(again.is_dir())

    def test_cancel_while_recording_deletes_the_meeting_and_starts_over(self):
        folder = self.record()
        RestartButton.answer = True
        self.win.btn_restart.click()
        self.spin(0.5)
        self.assert_fresh(folder)

    def test_cancel_after_stop_deletes_the_meeting_and_starts_over(self):
        folder = self.record()
        self.win.btn_stop.click()
        self.spin(2.0)
        self.assertEqual(self.win._state, "stopped")
        self.assertTrue(self.win.btn_restart.isEnabled())
        RestartButton.answer = True
        self.win.btn_restart.click()
        self.spin(0.5)
        self.assert_fresh(folder)


if __name__ == "__main__":
    unittest.main()
