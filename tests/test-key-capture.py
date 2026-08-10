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
import subprocess
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
    """A keyboard with a mic key, like the NuPhy of issue #30.

    Five keys only, so dictee-ptt never grabs it (its detection wants more than
    30). Good enough for the unit-level checks below, and NOT representative of
    a real keyboard — see TestUnderRunningDaemon for why that distinction cost
    an evening.
    """

    NAME = "dictee test keyboard"
    KEYS = [e.KEY_F9, e.KEY_A, e.KEY_LEFTSHIFT, e.KEY_ESC, e.KEY_VOICECOMMAND,
            e.KEY_GRAVE]

    def __enter__(self):
        self.ui = UInput({e.EV_KEY: self.KEYS}, name=self.NAME)
        time.sleep(0.4)  # let the node show up in /dev/input
        return self

    def press(self, code):
        self.ui.write(e.EV_KEY, code, 1)
        self.ui.write(e.EV_KEY, code, 0)
        self.ui.syn()

    def __exit__(self, *a):
        self.ui.close()


class GrabbableFakeKeyboard(FakeKeyboard):
    """Same, but with enough keys that dictee-ptt actually grabs it.

    find_keyboards_evdev keeps a device with more than 30 keys and no pointer
    axes (dictee-ptt.py:193). Anything smaller is ignored by the daemon, which
    is exactly what made the five-key keyboard above useless as a proof.
    """

    NAME = "dictee test keyboard full"
    KEYS = list(range(e.KEY_ESC, e.KEY_ESC + 60)) + [e.KEY_VOICECOMMAND]


class FakeKeyboardWithPointer:
    """A keyboard whose node ALSO reports pointer motion.

    Two real products land here: the Logitech Craft, whose Crown dial reports
    X/Y (#23), and the unified receivers that expose keyboard and mouse on one
    node — the hardware behind the 1.3.4 frozen-pointer report. Capture must
    keep reading their keys whatever it decides to grab.
    """

    NAME = "dictee test keyboard with pointer"
    KEYS = list(range(e.KEY_ESC, e.KEY_ESC + 60)) + [e.KEY_F9]

    def __enter__(self):
        self.ui = UInput({e.EV_KEY: self.KEYS,
                          e.EV_REL: [e.REL_X, e.REL_Y]}, name=self.NAME)
        time.sleep(0.4)
        return self

    def press(self, code):
        self.ui.write(e.EV_KEY, code, 1)
        self.ui.write(e.EV_KEY, code, 0)
        self.ui.syn()

    def __exit__(self, *a):
        self.ui.close()


class FakeMediaOnlyBlock:
    """A Consumer Control node whose only key sits ABOVE the button range.

    KEY_VOICECOMMAND is 582, higher than BTN_MISC (256), while a mouse button
    is 272. So "is the code below BTN_MISC" separates neither, and a device
    exposing only this key would be dropped by such a test — the very device
    issue #30 is about.
    """

    NAME = "dictee test media only"
    KEYS = [e.KEY_VOICECOMMAND]

    def __enter__(self):
        self.ui = UInput({e.EV_KEY: self.KEYS}, name=self.NAME)
        time.sleep(0.4)
        return self

    def press(self, code):
        self.ui.write(e.EV_KEY, code, 1)
        self.ui.write(e.EV_KEY, code, 0)
        self.ui.syn()

    def __exit__(self, *a):
        self.ui.close()


class FakePointer:
    """A pointer with buttons and no keyboard key at all.

    BTN_* codes live in EV_KEY, so a mouse or a touchpad satisfies any "does
    this device have keys" test; only the code VALUE tells them apart, real
    keys sitting below BTN_MISC. This is the device the capture must leave
    alone.
    """

    NAME = "dictee test mouse"

    def __enter__(self):
        self.ui = UInput(
            {e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
             e.EV_REL: [e.REL_X, e.REL_Y]},
            name=self.NAME)
        time.sleep(0.4)  # let the node show up in /dev/input
        return self

    def __exit__(self, *a):
        self.ui.close()


def daemon_is_running():
    out = subprocess.run(["systemctl", "--user", "is-active", "dictee-ptt"],
                         capture_output=True, text=True).stdout.strip()
    return out == "active"


def find_node(name):
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
        except OSError:
            continue
        if d.name == name:
            return d
        d.close()
    return None


def is_grabbed(name):
    """True when someone else holds the device exclusively.

    Probing means trying to grab it ourselves and immediately letting go; an
    EVIOCGRAB fails with EBUSY when another process already holds one.
    """
    dev = find_node(name)
    if dev is None:
        return None
    try:
        dev.grab()
        dev.ungrab()
        return False
    except OSError:
        return True
    finally:
        dev.close()


def wait_until(predicate, timeout, step=0.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        app.processEvents()
        time.sleep(step)
    return predicate()


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

    def test_the_top_left_key_is_captured(self):
        """#22: the ² / ` key, keycode 41, must be choosable."""
        with FakeKeyboard() as kbd:
            self.btn._start_capture()
            kbd.press(e.KEY_GRAVE)
            pump()
        self.assertEqual([c for c, _ in self.seen], [e.KEY_GRAVE])

    def test_a_key_from_a_keyboard_with_pointer_is_captured(self):
        """#23: the Craft's keys stay reachable though its dial reports X/Y.

        Whatever the grab policy becomes, reading must not depend on it: this
        is the keyboard a user opts into through the extra-devices list.
        """
        with FakeKeyboardWithPointer() as kbd:
            self.btn._start_capture()
            self.assertTrue(
                any(d.name == kbd.NAME for d in self.btn._devices),
                "a keyboard carrying pointer axes was not opened — #23 lost")
            kbd.press(e.KEY_F9)
            pump()
        self.assertEqual([c for c, _ in self.seen], [e.KEY_F9])

    def test_a_keyboard_that_moves_a_pointer_is_not_grabbed(self):
        """A unified receiver must not cost the user their cursor.

        Keyboard and mouse on one node: grabbing it to stop the key from
        acting also takes the pointer, and whoever then wants to close this
        dialog has nothing to click with. Reading its keys does not need the
        grab, so the grab is what gives way.
        """
        with FakeKeyboardWithPointer() as kbd:
            self.btn._start_capture()
            pump(0.6)
            grabbed = is_grabbed(kbd.NAME)
            self.btn._cancel_capture()
        self.assertIs(grabbed, False,
                      "a keyboard+pointer node was grabbed — the cursor "
                      "freezes and the dialog cannot be closed")

    def test_a_media_only_block_is_still_captured(self):
        """Excluding pointers must not exclude high-coded keys with them.

        The guard that keeps mice out cannot be an upper bound on the code:
        a block whose single key is KEY_VOICECOMMAND (582) would fall on the
        same side as a mouse button (272). That block IS the hardware of #30.
        """
        with FakeMediaOnlyBlock() as blk:
            self.btn._start_capture()
            self.assertTrue(
                any(d.name == blk.NAME for d in self.btn._devices),
                "a media-only block was not even opened — #30 hardware lost")
            blk.press(e.KEY_VOICECOMMAND)
            pump()
        self.assertEqual([c for c, _ in self.seen], [e.KEY_VOICECOMMAND])

    def test_a_pointer_is_never_grabbed(self):
        """The mouse must keep working while the user picks a key.

        Capture grabs what it opens, so the chosen key does not also act while
        it is being chosen. Opening everything that has EV_KEY sweeps in mice
        and touchpads, whose buttons ARE keys to the kernel: the pointer then
        freezes for the whole capture, and stays frozen if the dialog is left
        open. Reported on a laptop touchpad, 2026-08-10.
        """
        with FakePointer() as ptr:
            self.btn._start_capture()
            pump(0.6)          # the first grab happens inside _open_devices
            grabbed = is_grabbed(ptr.NAME)
            self.btn._cancel_capture()
        self.assertIs(grabbed, False,
                      "the pointer was grabbed during capture — the mouse "
                      "freezes until the dialog closes")

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


@unittest.skipUnless(HAS_EVDEV, "python3-evdev not installed")
class TestQtPathStaysAliveWhileDevicesAreOpen(unittest.TestCase):
    """Regression: the Qt path must keep working with devices open.

    dictee-ptt holds an EVIOCGRAB on the real keyboard. A grabbed device is
    exclusive, so our direct read sees nothing from it. The first version of
    this feature also swallowed the Qt event whenever devices were open, which
    left the button dead for every key as long as the daemon ran — exactly the
    case a fake, ungrabbed keyboard does not reproduce.

    dictee-ptt now releases its grab while the pause marker exists, but a daemon
    too old to do that must not brick the button either.
    """

    def setUp(self):
        try:
            UInput().close()
        except Exception as ex:  # noqa: BLE001
            self.skipTest(f"/dev/uinput not usable: {ex}")
        self.btn = setup.ShortcutButton()
        self.seen = []
        self.btn.keyCaptured.connect(lambda c, d: self.seen.append((c, d)))

    def tearDown(self):
        self.btn._close_devices()
        self.btn.deleteLater()

    def test_qt_event_still_resolves_with_devices_open(self):
        from PyQt6.QtCore import Qt as _Qt
        from PyQt6.QtGui import QKeyEvent
        with FakeKeyboard():
            self.btn._start_capture()
            self.assertTrue(self.btn._devices, "no device opened; test is void")
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, _Qt.Key.Key_F9,
                           _Qt.KeyboardModifier.NoModifier)
            self.btn.keyPressEvent(ev)
        self.assertEqual([c for c, _ in self.seen], [67],
                         "Qt path did not resolve F9 while devices were open")
        self.assertFalse(self.btn._devices, "devices left open by the Qt path")


@unittest.skipUnless(HAS_EVDEV, "python3-evdev not installed")
class TestUnderRunningDaemon(unittest.TestCase):
    """The only conditions that matter: dictee-ptt running and holding the keyboard.

    THIS is the case the rest of this file does not reproduce. dictee-ptt holds
    an EVIOCGRAB on every keyboard it listens to, and a grabbed device is
    exclusive: nothing else receives its events. A capture reading /dev/input
    therefore sees nothing at all from the user's real keyboard, however well it
    works against a fake one the daemon ignores.

    The first version of this feature passed every other test in this file and
    was dead on the user's machine. Whatever else changes, this class must keep
    running the daemon and using a keyboard the daemon has actually grabbed.
    """

    @classmethod
    def setUpClass(cls):
        if not daemon_is_running():
            raise unittest.SkipTest("dictee-ptt is not running")
        try:
            UInput().close()
        except Exception as ex:  # noqa: BLE001
            raise unittest.SkipTest(f"/dev/uinput not usable: {ex}")
        cls.kbd = GrabbableFakeKeyboard()
        cls.kbd.__enter__()
        # The daemon rescans on a timer (RESCAN_INTERVAL = 10 s), so give it
        # room. If it never grabs, the test would prove nothing — skip loudly.
        if not wait_until(lambda: is_grabbed(cls.kbd.NAME) is True, timeout=25):
            cls.kbd.__exit__()
            raise unittest.SkipTest(
                "dictee-ptt did not grab the test keyboard within 25 s; "
                "cannot reproduce production conditions")

    @classmethod
    def tearDownClass(cls):
        kbd = getattr(cls, "kbd", None)
        if kbd is not None:
            kbd.__exit__()

    def setUp(self):
        self.btn = setup.ShortcutButton()
        self.seen = []
        self.btn.keyCaptured.connect(lambda c, d: self.seen.append((c, d)))

    def tearDown(self):
        self.btn._close_devices()
        self.btn._set_ptt_pause(False)
        self.btn.deleteLater()
        # Let the daemon take the devices back before the next test.
        wait_until(lambda: is_grabbed(self.kbd.NAME) is True, timeout=6)

    def test_daemon_releases_the_keyboard_during_capture(self):
        self.assertTrue(is_grabbed(self.kbd.NAME),
                        "keyboard not grabbed before capture; test is void")
        self.btn._start_capture()
        released = wait_until(lambda: is_grabbed(self.kbd.NAME) is False,
                              timeout=8)
        self.btn._cancel_capture()
        self.assertTrue(released,
                        "dictee-ptt kept its grab during capture: the capture "
                        "can never see a key from a real keyboard")

    def test_daemon_takes_the_keyboard_back_afterwards(self):
        self.btn._start_capture()
        wait_until(lambda: is_grabbed(self.kbd.NAME) is False, timeout=8)
        self.btn._cancel_capture()
        self.assertTrue(
            wait_until(lambda: is_grabbed(self.kbd.NAME) is True, timeout=8),
            "dictee-ptt did not grab the keyboard again: dictation is dead "
            "until the daemon is restarted")

    def test_key_is_captured_from_a_grabbed_keyboard(self):
        """The end-to-end case, and the one that was broken."""
        self.btn._start_capture()
        self.assertTrue(
            wait_until(lambda: is_grabbed(self.kbd.NAME) is False, timeout=8),
            "keyboard never released; cannot press a key into the capture")
        self.kbd.press(e.KEY_VOICECOMMAND)
        wait_until(lambda: bool(self.seen), timeout=4)
        self.assertEqual([c for c, _ in self.seen], [e.KEY_VOICECOMMAND],
                         "no key reached the capture while dictee-ptt was "
                         "running")
        self.assertEqual(self.seen[0][1], GrabbableFakeKeyboard.NAME,
                         "the key was reported from the wrong device")


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
