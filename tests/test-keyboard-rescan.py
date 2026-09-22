#!/usr/bin/env python3
"""What the hotplug rescan costs, in number of /dev/input nodes opened.

Issue #33: the rescan runs every RESCAN_INTERVAL seconds and used to open and
close every /dev/input/event* node each time, keyboards and everything else.
Closing an evdev node waits for an RCU grace period in the kernel, ~10 to 20 ms
per node, so a machine with a couple of dozen input devices stalled the push-to
-talk loop for a full second, every ten seconds (reported: 1.0 to 1.7 s).

The capabilities of a given node never change, so a node examined once does not
need to be opened again. Only nodes that appeared since the last scan do.

Everything here is faked: no /dev/input, no /dev/uinput, no evdev needed.

Run: python3 tests/test-keyboard-rescan.py
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FULL_KEYBOARD = list(range(1, 62))


class FakeDevice:
    """The slice of evdev.InputDevice that the detection code touches."""

    opened = 0
    held_on = {}          # path -> keys physically down on that node
    grab_refused = set()  # paths whose grab fails (EBUSY: someone else holds it)

    def __init__(self, path, name, caps):
        self.path = path
        self.name = name
        self._caps = caps
        self.closed = False
        self.grabbed = False
        FakeDevice.opened += 1

    def capabilities(self, verbose=False):
        return self._caps

    def active_keys(self, verbose=False):
        # The rescan reads this before grabbing: a keyboard with a key held
        # is left for the next pass, so its release is not stolen from the
        # compositor.
        return list(FakeDevice.held_on.get(self.path, []))

    def grab(self):
        if self.path in FakeDevice.grab_refused:
            raise OSError(16, "Device or resource busy")
        self.grabbed = True

    def close(self):
        self.closed = True


class FakeInput:
    """A node present under /dev/input, not yet opened."""

    def __init__(self, path, name, caps):
        self.path = path
        self.name = name
        self.caps = caps


def load_ptt(nodes):
    """dictee-ptt.py with its evdev access redirected to `nodes`."""
    spec = importlib.util.spec_from_file_location(
        "ptt_rescan_under_test", os.path.join(ROOT, "dictee-ptt.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.EXTRA_KEYBOARDS = []
    mod.EXCLUDE_KEYBOARDS = []

    class FakeEvdev:
        @staticmethod
        def list_devices():
            return [n.path for n in nodes]

    def fake_open(path):
        for n in nodes:
            if n.path == path:
                return FakeDevice(n.path, n.name, n.caps)
        raise OSError(f"no such node: {path}")

    mod.evdev = FakeEvdev
    mod.InputDevice = fake_open
    return mod


def a_keyboard(path, name="fake keyboard"):
    return FakeInput(path, name, {1: FULL_KEYBOARD})


def not_a_keyboard(path, name="fake headphone jack"):
    return FakeInput(path, name, {1: [113]})


class TestRescanCost(unittest.TestCase):

    def setUp(self):
        # One keyboard among the two dozen nodes a laptop exposes: audio jacks,
        # lid switch, power button, webcam, touchpad... the shape of #33.
        self.nodes = [a_keyboard("/dev/input/event3")]
        self.nodes += [not_a_keyboard(f"/dev/input/event{i}")
                       for i in range(4, 28)]
        self.ptt = load_ptt(self.nodes)
        FakeDevice.opened = 0
        FakeDevice.held_on = {}
        FakeDevice.grab_refused = set()

    def test_first_scan_opens_every_node(self):
        """Nothing is known yet, so everything has to be looked at."""
        devices = self.ptt.find_keyboards_evdev()
        self.assertEqual(len(devices), 1, "the keyboard was not detected")
        self.assertEqual(FakeDevice.opened, len(self.nodes))

    def test_rescan_without_hotplug_opens_nothing(self):
        """#33: a quiet rescan must not touch a single node."""
        devices = self.ptt.find_keyboards_evdev()
        FakeDevice.opened = 0
        self.ptt._rescan_keyboards(devices)
        self.assertEqual(FakeDevice.opened, 0,
                         "the rescan re-opened nodes it had already examined")
        self.assertEqual(len(devices), 1, "the known keyboard was lost")

    def test_rescan_still_picks_up_a_new_keyboard(self):
        """The whole point of the rescan: hotplug still works."""
        devices = self.ptt.find_keyboards_evdev()
        self.nodes.append(a_keyboard("/dev/input/event28", "hotplugged board"))
        FakeDevice.opened = 0
        self.ptt._rescan_keyboards(devices)
        self.assertEqual(FakeDevice.opened, 1,
                         "only the new node should have been opened")
        self.assertEqual([d.name for d in devices],
                         ["fake keyboard", "hotplugged board"])
        self.assertTrue(devices[1].grabbed, "the new keyboard was not grabbed")

    def test_unplugged_node_is_examined_again_when_it_comes_back(self):
        """A path freed then reused must not be mistaken for an old node."""
        devices = self.ptt.find_keyboards_evdev()
        gone = self.nodes.pop()                       # last jack disappears
        self.ptt._rescan_keyboards(devices)           # notices it is gone
        self.nodes.append(a_keyboard(gone.path, "replugged board"))
        FakeDevice.opened = 0
        self.ptt._rescan_keyboards(devices)
        self.assertEqual(FakeDevice.opened, 1)
        self.assertEqual(len(devices), 2,
                         "a keyboard on a recycled path was ignored")

    def test_a_lost_keyboard_whose_node_survives_is_taken_back(self):
        """The three sites that drop a keyboard must all make it new again.

        A read error does not always mean the device is gone. When the node
        is still there, forgetting to clear it from the scanned set would
        leave the keyboard dead until the daemon restarts, since a rescan
        only looks at nodes it has never seen.
        """
        devices = self.ptt.find_keyboards_evdev()
        lost = devices.pop()                     # what the run loop does...
        self.ptt._scanned_paths.discard(lost.path)   # ...and must also do
        FakeDevice.opened = 0
        self.ptt._rescan_keyboards(devices)
        self.assertEqual(FakeDevice.opened, 1,
                         "the lost keyboard's node was not examined again")
        self.assertEqual(len(devices), 1, "the keyboard was not grabbed back")

    def test_a_keyboard_plugged_with_a_key_held_is_grabbed_once_released(self):
        """Deferring the grab must not mean forgetting the keyboard.

        The rescan leaves a hotplugged keyboard alone while a key is down on
        it (grabbing then would steal the release from the compositor), but
        find_keyboards_evdev(new_only=True) has already filed the node as
        examined by then. Without clearing it, the next rescan skips the
        node and the keyboard is never grabbed at all.
        """
        devices = self.ptt.find_keyboards_evdev()
        self.nodes.append(a_keyboard("/dev/input/event28", "hotplugged board"))
        FakeDevice.held_on["/dev/input/event28"] = [30]
        self.ptt._rescan_keyboards(devices)
        self.assertEqual(len(devices), 1,
                         "grabbed with a key held: its release would be stolen")
        FakeDevice.held_on.clear()                    # the hand comes off
        FakeDevice.opened = 0
        self.ptt._rescan_keyboards(devices)
        self.assertEqual(FakeDevice.opened, 1,
                         "the deferred keyboard was never looked at again")
        self.assertEqual(len(devices), 2, "the deferred keyboard was never grabbed")
        self.assertTrue(devices[1].grabbed)

    def test_a_keyboard_whose_grab_fails_is_tried_again(self):
        """EBUSY is transient (another program held the node): stay new."""
        devices = self.ptt.find_keyboards_evdev()
        self.nodes.append(a_keyboard("/dev/input/event28", "busy board"))
        FakeDevice.grab_refused.add("/dev/input/event28")
        self.ptt._rescan_keyboards(devices)
        self.assertEqual(len(devices), 1, "a refused grab must not add the device")
        FakeDevice.grab_refused.clear()               # the other program lets go
        FakeDevice.opened = 0
        self.ptt._rescan_keyboards(devices)
        self.assertEqual(FakeDevice.opened, 1,
                         "the busy keyboard was never looked at again")
        self.assertEqual(len(devices), 2, "the busy keyboard was never grabbed")

    def test_a_rejected_node_is_never_reopened(self):
        """Non-keyboards are the bulk of the cost and never change."""
        self.ptt.find_keyboards_evdev()
        FakeDevice.opened = 0
        for _ in range(5):
            self.ptt._rescan_keyboards([])
        self.assertEqual(FakeDevice.opened, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
