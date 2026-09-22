#!/usr/bin/env python3
"""While the live meeting window is open, dictee-ptt must not interpret keys.

The window writes "meeting-ui-open" then "meeting-recording" to the shared
state file. In those two states every key, the dictation key included, has to
reach the applications untouched: otherwise F9 would start a dictation on top
of the meeting capture. The decision is a pure function so it can be pinned
here without a keyboard; a text check makes sure the evdev loop consults it
before handing the event to the PTT state machine.

Run: python3 tests/test-ptt-meeting-passthrough.py
"""
import importlib.util
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PTT = os.path.join(ROOT, "dictee-ptt.py")


def load_ptt():
    spec = importlib.util.spec_from_file_location("ptt_meeting_under_test", PTT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPassThrough(unittest.TestCase):

    def setUp(self):
        self.ptt = load_ptt()

    def test_meeting_states_pass_keys_through(self):
        self.assertTrue(self.ptt.keys_pass_through("meeting-ui-open"))
        self.assertTrue(self.ptt.keys_pass_through("meeting-recording"))

    def test_every_other_state_keeps_the_ptt_key(self):
        for state in ("idle", "recording", "transcribing", "offline", "switching",
                      "preparing", "diarize-ready", "diarizing", "", "garbage"):
            self.assertFalse(self.ptt.keys_pass_through(state), state)

    def test_the_evdev_loop_asks_before_handling_the_key(self):
        """The check must sit between the EV_KEY filter and ptt.handle_event."""
        src = open(PTT, encoding="utf-8").read()
        loop = src[src.index("def run_evdev("):src.index("def run_raw(")]
        # The per-key section only: the idle branch above it consults the
        # same function for the stale-state cleanup, which is not this gate.
        per_key = loop.find("for event in dev.read()")
        self.assertNotEqual(per_key, -1)
        gate = loop.find("keys_pass_through(read_state())", per_key)
        handle = loop.find("ptt.handle_event(event.code, event.value)", per_key)
        self.assertNotEqual(gate, -1, "run_evdev never consults keys_pass_through")
        self.assertLess(gate, handle, "the pass-through check comes after handle_event")
        self.assertIn("ui.write_event(event)", loop[gate:gate + 200],
                      "a passed-through key must still be re-emitted")


class TestStaleMeetingState(unittest.TestCase):
    """A meeting state must not outlive the window that wrote it.

    PyQt6 aborts the process on an unhandled exception in a slot, and
    closeEvent never runs then: the state file keeps saying the window is
    open. Nothing else writes it, so every key would pass through, the
    dictation key included, until the next reboot, with no message. The
    daemon has to notice the window is gone and put the state back to idle.
    """

    def setUp(self):
        self.ptt = load_ptt()
        self.ptt.STATE_FILE = os.path.join(tempfile.mkdtemp(), "state")

    def _state(self, value):
        with open(self.ptt.STATE_FILE, "w", encoding="utf-8") as f:
            f.write(value + "\n")

    def test_a_meeting_state_with_no_window_alive_is_reset(self):
        for state in ("meeting-ui-open", "meeting-recording"):
            self._state(state)
            self.ptt._meeting_live_running = lambda: False
            self.assertEqual(self.ptt.read_state_with_cleanup(), "idle", state)
            with open(self.ptt.STATE_FILE, encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "idle", state)

    def test_a_meeting_state_with_the_window_alive_is_kept(self):
        for state in ("meeting-ui-open", "meeting-recording"):
            self._state(state)
            self.ptt._meeting_live_running = lambda: True
            self.assertEqual(self.ptt.read_state_with_cleanup(), state)

    def test_the_idle_loop_runs_the_cleanup(self):
        """Once a second, at the select timeout, never on every key.

        The per-key check stays the cheap read_state(): a pgrep per
        keystroke is not acceptable. The timeout branch is the place, next to
        the pause handling that already lives there.
        """
        src = open(PTT, encoding="utf-8").read()
        loop = src[src.index("def run_evdev("):src.index("def run_raw(")]
        timeout_branch = loop.find("now_paused = pause_requested()")
        self.assertNotEqual(timeout_branch, -1)
        window = loop[max(0, timeout_branch - 800):timeout_branch]
        self.assertIn("read_state_with_cleanup()", window,
                      "the select timeout branch does not heal a stale meeting state")
        per_key = loop[loop.find("for event in dev.read()"):]
        self.assertNotIn("read_state_with_cleanup()", per_key,
                         "the cleanup (a pgrep) must not run on every key")


if __name__ == "__main__":
    unittest.main(verbosity=2)
