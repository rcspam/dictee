#!/usr/bin/env python3
"""Prove ShortcutButton reads real keycodes, including keys with no symbol.

A fake keyboard is created through uinput, exposing F9 and the mic key
(KEY_VOICECOMMAND) that issue #30 is about. The button is then asked to
capture, the fake keyboard presses a key, and the emitted keycode is checked.

The mic key is the whole point: it has no Qt keysym, so the old capture path
resolved it to 0 and silently kept the previous key. Its evdev code is also
582, past the 255 an X11 keycode can hold — another reason no symbol-based
path could ever carry it.

Needs write access to /dev/uinput (group 'input'). Skips cleanly otherwise, so
CI without the device does not fail.

Run: python3 tests/test-key-capture.py
"""
import importlib.util
import os
import sys
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CONFIG_HOME", "/tmp/dictee-test-noconfig")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import evdev
    from evdev import UInput, ecodes as e
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False

from PyQt6.QtWidgets import QApplication


def load_setup():
    spec = importlib.util.spec_from_file_location(
        "dictee_setup", os.path.join(ROOT, "dictee-setup.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dictee_setup"] = mod
    spec.loader.exec_module(mod)
    return mod


app = QApplication.instance() or QApplication([])
setup = load_setup()


def pump(seconds=0.5):
    """Spin the Qt event loop so QSocketNotifier callbacks actually run."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


class FakeKeyboard:
    """A keyboard with a mic key, like the NuPhy of issue #30."""

    NAME = "dictee test keyboard"

    def __enter__(self):
        caps = {e.EV_KEY: [e.KEY_F9, e.KEY_A, e.KEY_LEFTSHIFT, e.KEY_ESC,
                           e.KEY_VOICECOMMAND]}
        self.ui = UInput(caps, name=self.NAME)
        time.sleep(0.4)  # let the node show up in /dev/input
        return self

    def press(self, code):
        self.ui.write(e.EV_KEY, code, 1)
        self.ui.write(e.EV_KEY, code, 0)
        self.ui.syn()

    def __exit__(self, *a):
        self.ui.close()


@unittest.skipUnless(HAS_EVDEV, "python3-evdev not installed")
class TestDirectCapture(unittest.TestCase):

    def setUp(self):
        try:
            UInput().close()
        except Exception as ex:  # noqa: BLE001 - any failure means no /dev/uinput
            self.skipTest(f"/dev/uinput not usable: {ex}")
        self.btn = setup.ShortcutButton()
        self.seen = []
        self.btn.keyCaptured.connect(
            lambda code, dev: self.seen.append((code, dev)))

    def tearDown(self):
        self.btn._close_devices()
        self.btn.deleteLater()

    def test_mic_key_is_captured(self):
        """The key issue #30 is about: no Qt symbol, evdev code 582."""
        with FakeKeyboard() as kbd:
            self.btn._start_capture()
            self.assertTrue(self.btn._devices,
                            "no input device opened; direct capture unavailable")
            kbd.press(e.KEY_VOICECOMMAND)
            pump()
        self.assertEqual([c for c, _ in self.seen], [e.KEY_VOICECOMMAND])
        self.assertEqual(self.seen[0][1], FakeKeyboard.NAME)

    def test_function_key_still_works(self):
        """F9 is what everyone uses; it must come out unchanged."""
        with FakeKeyboard() as kbd:
            self.btn._start_capture()
            kbd.press(e.KEY_F9)
            pump()
        self.assertEqual([c for c, _ in self.seen], [e.KEY_F9])

    def test_modifier_alone_is_ignored(self):
        with FakeKeyboard() as kbd:
            self.btn._start_capture()
            kbd.press(e.KEY_LEFTSHIFT)
            pump(0.3)
            self.assertEqual(self.seen, [], "a lone modifier was captured")
            kbd.press(e.KEY_F9)
            pump()
        self.assertEqual([c for c, _ in self.seen], [e.KEY_F9])

    def test_escape_cancels_and_restores_label(self):
        with FakeKeyboard() as kbd:
            before = self.btn.text()
            self.btn._start_capture()
            self.assertNotEqual(self.btn.text(), before)
            kbd.press(e.KEY_ESC)
            pump()
        self.assertEqual(self.seen, [], "Escape was captured as a key")
        self.assertEqual(self.btn.text(), before)
        self.assertFalse(self.btn._capturing)
        self.assertFalse(self.btn._devices, "devices left open after cancel")

    def test_devices_are_released_after_capture(self):
        """A capture must not leave input devices open behind it."""
        with FakeKeyboard() as kbd:
            self.btn._start_capture()
            kbd.press(e.KEY_F9)
            pump()
        self.assertFalse(self.btn._devices)
        self.assertFalse(self.btn._notifiers)

    def test_our_own_virtual_keyboards_are_skipped(self):
        """Listening to dotool would capture dictee typing, not the user."""
        self.btn._start_capture()
        names = [d.name.lower() for d in self.btn._devices]
        self.btn._cancel_capture()
        for own in ("dotool", "dictee-ptt"):
            self.assertFalse([n for n in names if own in n],
                             f"{own} device opened for capture")


class TestQtFallback(unittest.TestCase):
    """With no readable device, capture must still resolve the listed keys."""

    def test_table_still_resolves_f9(self):
        seq = setup.QKeySequence(0x01000038)  # Qt.Key_F9
        self.assertEqual(setup.qt_key_to_linux_keycode(seq), 67)

    def test_table_no_longer_offers_editing_keys(self):
        for qt_key in (0x01000010, 0x01000011, 0x01000016, 0x01000015):
            seq = setup.QKeySequence(qt_key)
            self.assertEqual(setup.qt_key_to_linux_keycode(seq), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
