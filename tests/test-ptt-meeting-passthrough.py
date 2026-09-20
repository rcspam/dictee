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
        gate = loop.find("keys_pass_through(read_state())")
        handle = loop.find("ptt.handle_event(event.code, event.value)")
        self.assertNotEqual(gate, -1, "run_evdev never consults keys_pass_through")
        self.assertLess(gate, handle, "the pass-through check comes after handle_event")
        self.assertIn("ui.write_event(event)", loop[gate:gate + 200],
                      "a passed-through key must still be re-emitted")


if __name__ == "__main__":
    unittest.main(verbosity=2)
