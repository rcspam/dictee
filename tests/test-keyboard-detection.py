#!/usr/bin/env python3
"""Which devices dictee-ptt agrees to listen to, against the reported hardware.

Each case below is a real device from an issue, rebuilt with uinput. The kernel
cannot tell a uinput device from a physical one, so what matters is reproducing
the characteristic the detection keys on — not owning the keyboard.

  #23  Logitech Craft: 295 keys AND REL_X/REL_Y (Crown dial). A genuine pointer,
       rightly refused by default; the whitelist must be able to force it in.
  #30  NuPhy media block: >30 keys and a volume axis, no pointer at all. Was
       refused because the guard rejected any axis instead of X/Y motion only.
  #10  Remapper output (logiops, keyd): a virtual keyboard the user must be able
       to whitelist by name.

Needs /dev/uinput (group 'input'); skips cleanly otherwise.

Run: python3 tests/test-keyboard-detection.py
"""
import importlib.util
import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import evdev
    from evdev import UInput, ecodes as e
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False

FULL_KEYBOARD = list(range(e.KEY_ESC, e.KEY_ESC + 60)) if HAS_EVDEV else []


def load_ptt():
    spec = importlib.util.spec_from_file_location(
        "ptt_under_test", os.path.join(ROOT, "dictee-ptt.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.EXTRA_KEYBOARDS = []
    mod.EXCLUDE_KEYBOARDS = []
    return mod


class FakeDevice:
    def __init__(self, name, caps):
        self.name = name
        self.caps = caps

    def __enter__(self):
        self.ui = UInput(self.caps, name=self.name)
        time.sleep(0.4)
        return self

    def __exit__(self, *a):
        self.ui.close()


def detected(mod, name):
    """Is this device picked up, by both detection paths?"""
    devs = mod.find_keyboards_evdev()
    by_evdev = name in [d.name for d in devs]
    for d in devs:
        d.close()
    by_raw = False
    for path in mod.find_keyboards_raw():
        try:
            if evdev.InputDevice(path).name == name:
                by_raw = True
        except OSError:
            pass
    return by_evdev, by_raw


@unittest.skipUnless(HAS_EVDEV, "python3-evdev not installed")
class TestDetection(unittest.TestCase):

    def setUp(self):
        try:
            UInput().close()
        except Exception as ex:  # noqa: BLE001
            self.skipTest(f"/dev/uinput not usable: {ex}")
        self.ptt = load_ptt()

    def test_media_block_is_accepted(self):
        """#30: a volume axis is not a pointer."""
        caps = {e.EV_KEY: FULL_KEYBOARD + [e.KEY_VOICECOMMAND],
                e.EV_ABS: [(e.ABS_VOLUME, (0, 0, 100, 0, 0, 0))],
                e.EV_REL: [e.REL_HWHEEL]}
        with FakeDevice("dictee test media block", caps) as d:
            by_evdev, by_raw = detected(self.ptt, d.name)
        self.assertTrue(by_evdev, "media block refused by find_keyboards_evdev")
        self.assertTrue(by_raw, "media block refused by find_keyboards_raw")

    def test_real_pointer_is_still_refused(self):
        """#23 and the 1.3.4 forum report: X/Y motion means a pointer."""
        caps = {e.EV_KEY: FULL_KEYBOARD,
                e.EV_REL: [e.REL_X, e.REL_Y, e.REL_HWHEEL]}
        with FakeDevice("dictee test craft", caps) as d:
            by_evdev, by_raw = detected(self.ptt, d.name)
        self.assertFalse(by_evdev, "a pointer device was accepted: grabbing it "
                                   "would freeze the mouse")
        self.assertFalse(by_raw, "a pointer device was accepted by the fallback")

    def test_whitelist_still_forces_a_pointer_device_in(self):
        """#23: the user explicitly opted in, that decision wins."""
        caps = {e.EV_KEY: FULL_KEYBOARD,
                e.EV_REL: [e.REL_X, e.REL_Y],
                e.EV_ABS: [(e.ABS_X, (0, 0, 100, 0, 0, 0))]}
        with FakeDevice("dictee test craft wl", caps) as d:
            self.ptt.EXTRA_KEYBOARDS = ["dictee test craft wl"]
            by_evdev, by_raw = detected(self.ptt, d.name)
        self.assertTrue(by_evdev, "whitelist did not override the guard")
        self.assertTrue(by_raw, "whitelist did not override the guard (fallback)")

    def test_touchpad_is_refused(self):
        """A touchpad reports ABS_X/ABS_Y and a handful of buttons."""
        caps = {e.EV_KEY: [e.BTN_TOUCH, e.BTN_TOOL_FINGER],
                e.EV_ABS: [(e.ABS_X, (0, 0, 100, 0, 0, 0)),
                           (e.ABS_Y, (0, 0, 100, 0, 0, 0))]}
        with FakeDevice("dictee test touchpad", caps) as d:
            by_evdev, _ = detected(self.ptt, d.name)
        self.assertFalse(by_evdev)

    def test_our_own_injection_device_is_refused(self):
        """Listening to dotool would feed dictee its own typing back."""
        caps = {e.EV_KEY: FULL_KEYBOARD}
        with FakeDevice("dotool test keyboard", caps) as d:
            by_evdev, _ = detected(self.ptt, d.name)
        self.assertFalse(by_evdev, "dotool device accepted: feedback loop")

    def test_remapper_keyboard_can_be_whitelisted(self):
        """#10: a virtual keyboard is refused by name, unless whitelisted."""
        caps = {e.EV_KEY: FULL_KEYBOARD}
        with FakeDevice("dictee test virtual input", caps) as d:
            refused, _ = detected(self.ptt, d.name)
            self.ptt.EXTRA_KEYBOARDS = ["dictee test virtual input"]
            accepted, _ = detected(self.ptt, d.name)
        self.assertFalse(refused, "a virtual keyboard was taken by default")
        self.assertTrue(accepted, "whitelist did not bring the virtual keyboard in")


if __name__ == "__main__":
    unittest.main(verbosity=2)
