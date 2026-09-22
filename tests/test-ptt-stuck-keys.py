#!/usr/bin/env python3
"""No key may stay pressed on dictee-ptt's virtual keyboard.

The daemon grabs the physical keyboards and re-emits their keys on a uinput
device, the only keyboard the compositor sees. A key whose KEY_DOWN went
through that device and whose KEY_UP never does stays pressed for the
compositor until the session ends: Shift stuck (accents typed as digits,
every click a Shift+click), the dictation key leaking into applications
because _any_mod_held() never turns false again, autorepeat on a key nobody
holds. Measured on a KDE Wayland session: xinput showed Shift down on the
Xwayland keyboard after a key capture in dictee-setup.

Four ways to lose a KEY_UP, each replayed here against the real loop
(tests/ptt_sandbox_driver.py runs it on fake uinput keyboards only):

1. the devices are let go for a key capture while a key is held: its
   release lands on the physical keyboard, not on us;
2. the daemon takes the keyboards back while a key is physically held: the
   compositor saw that press on the physical keyboard and the grab now
   steals its release, so the daemon must wait;
3. a keyboard vanishes while a key is held (unplugged, input-remapper churn);
4. the passthrough is replaced by a wider one for a hotplugged keyboard.

Needs /dev/uinput and readable /dev/input nodes (group input). Skips cleanly
otherwise.

Run: python3 tests/test-ptt-stuck-keys.py [-v]
"""
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.path.join(ROOT, "tests", "ptt_sandbox_driver.py")

try:
    import evdev
    from evdev import UInput, ecodes as e
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False

# "dictee-ptt" in the name: the real daemon on the host skips such devices
# (its own virtual keyboards carry it), so only the sandbox grabs them.
PREFIX = f"dictee-ptt sandbox {os.getpid()}"
PASSTHROUGH = f"{PREFIX} passthrough"
# 60 keys so the daemon treats it as a keyboard, plus F9 (dictation key) and
# F24 as the "plain key" nobody binds, so a leak types nothing visible.
FULL_KEYS = (list(range(e.KEY_ESC, e.KEY_ESC + 60)) + [e.KEY_F9, e.KEY_F24]) if HAS_EVDEV else []


class FakeKeyboard:
    """A grabbable fake keyboard (more than 30 keys, no pointer axes)."""

    def __init__(self, tag, caps=None):
        self.name = f"{PREFIX} {tag}"
        self.caps = caps or {e.EV_KEY: FULL_KEYS}
        self.ui = None

    def __enter__(self):
        self.ui = UInput(self.caps, name=self.name)
        time.sleep(0.4)
        return self

    def key(self, code, value):
        self.ui.write(e.EV_KEY, code, value)
        self.ui.syn()

    def down(self, code):
        self.key(code, 1)

    def up(self, code):
        self.key(code, 0)

    def close(self):
        if self.ui is not None:
            self.ui.close()
            self.ui = None

    def __exit__(self, *a):
        self.close()


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


def virtual_keys_down():
    dev = find_node(PASSTHROUGH)
    if dev is None:
        return None
    try:
        return sorted(dev.active_keys())
    finally:
        dev.close()


def wait_until(predicate, timeout, step=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


class Daemon:
    """The sandboxed dictee-ptt loop, with its log readable line by line."""

    def __init__(self):
        self.sandbox = tempfile.mkdtemp(prefix="dictee-ptt-sandbox-")
        self.proc = subprocess.Popen(
            [sys.executable, "-u", DRIVER, self.sandbox, PREFIX, PASSTHROUGH],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.lines = []
        self.q = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            self.lines.append(line.rstrip("\n"))
            self.q.put(line.rstrip("\n"))

    def wait_log(self, needle, timeout=8, since=0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(needle in ln for ln in self.lines[since:]):
                return True
            time.sleep(0.05)
        return any(needle in ln for ln in self.lines[since:])

    def mark(self):
        return len(self.lines)

    def pause(self, on):
        p = os.path.join(self.sandbox, "pause")
        if on:
            with open(p, "w") as f:
                f.write("test\n")
        else:
            try:
                os.remove(p)
            except FileNotFoundError:
                pass

    def stop(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        try:
            self.proc.stdout.close()
        except OSError:
            pass
        shutil.rmtree(self.sandbox, ignore_errors=True)


@unittest.skipUnless(HAS_EVDEV, "python3-evdev not installed")
@unittest.skipUnless(os.environ.get("GITHUB_ACTIONS") or os.environ.get("DICTEE_PTT_SANDBOX_TESTS"),
                     "injects keys into the running session: set DICTEE_PTT_SANDBOX_TESTS=1 "
                     "on a VM or in CI, never on a live desktop")
class StuckKeysTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            UInput().close()
        except Exception as ex:  # noqa: BLE001
            raise unittest.SkipTest(f"/dev/uinput not usable: {ex}")

    def setUp(self):
        self.kbd = FakeKeyboard("A").__enter__()
        self.daemon = Daemon()
        self.assertTrue(self.daemon.wait_log("en écoute", timeout=10),
                        "sandboxed daemon did not start:\n" + "\n".join(self.daemon.lines))
        self.assertTrue(wait_until(lambda: is_grabbed(self.kbd.name) is True, 5),
                        "daemon did not grab the fake keyboard")
        self.assertTrue(wait_until(lambda: virtual_keys_down() is not None, 5),
                        "passthrough device did not appear")
        time.sleep(0.6)   # startup grace: keys are dropped during the first 500 ms

    def tearDown(self):
        self.daemon.stop()
        self.kbd.close()

    def _hold_and_check_reemitted(self, code):
        self.kbd.down(code)
        self.assertTrue(wait_until(lambda: code in (virtual_keys_down() or []), 3),
                        f"key {code} was not re-emitted on the passthrough; test is void")

    # 1. release for key capture -------------------------------------------

    def test_pause_releases_the_keys_held_on_the_passthrough(self):
        self._hold_and_check_reemitted(e.KEY_LEFTSHIFT)
        mark = self.daemon.mark()
        self.daemon.pause(True)
        self.assertTrue(self.daemon.wait_log("pause: devices released", since=mark))
        self.assertEqual(virtual_keys_down(), [],
                         "Shift stayed pressed on the passthrough after the devices were let go")
        self.kbd.up(e.KEY_LEFTSHIFT)   # lands on the physical keyboard, never on us
        self.daemon.pause(False)

    def test_dictation_key_works_after_a_modifier_released_during_capture(self):
        """The user's symptom: Shift held at capture time, released during it,
        and afterwards the dictation key leaks into applications on every
        press because keys_held still says Shift is down."""
        self._hold_and_check_reemitted(e.KEY_LEFTSHIFT)
        mark = self.daemon.mark()
        self.daemon.pause(True)
        self.assertTrue(self.daemon.wait_log("pause: devices released", since=mark))
        self.kbd.up(e.KEY_LEFTSHIFT)
        time.sleep(0.5)                # released DURING the capture, as a user does
        self.daemon.pause(False)
        self.assertTrue(self.daemon.wait_log("resume: devices grabbed again", since=mark),
                        "daemon never took the keyboard back")
        # Watch the passthrough: F9 must not come out of it.
        watcher = find_node(PASSTHROUGH)
        mark = self.daemon.mark()
        self.kbd.down(e.KEY_F9)
        time.sleep(0.3)
        self.kbd.up(e.KEY_F9)
        self.assertTrue(self.daemon.wait_log("hold: start", since=mark),
                        "F9 did not start a dictation: the daemon still believes a modifier is held")
        time.sleep(0.5)
        leaked = []
        try:
            while True:
                ev = watcher.read_one()
                if ev is None:
                    break
                if ev.type == e.EV_KEY and ev.code == e.KEY_F9:
                    leaked.append(ev.value)
        except BlockingIOError:
            pass
        finally:
            watcher.close()
        self.assertEqual(leaked, [], "F9 leaked to the applications through the passthrough")

    # 2. regrab waits for the physical keys --------------------------------

    def test_regrab_waits_until_no_key_is_physically_held(self):
        mark = self.daemon.mark()
        self.daemon.pause(True)
        self.assertTrue(self.daemon.wait_log("pause: devices released", since=mark))
        self.assertTrue(wait_until(lambda: is_grabbed(self.kbd.name) is False, 3))
        self.kbd.down(e.KEY_F24)       # pressed while the compositor owns the keyboard
        self.daemon.pause(False)
        time.sleep(2.5)                # two select timeouts
        self.assertFalse(is_grabbed(self.kbd.name),
                         "daemon grabbed the keyboard while a key was held: the compositor "
                         "will never see that key released")
        self.assertTrue(self.daemon.wait_log("resume deferred", since=mark))
        self.kbd.up(e.KEY_F24)
        self.assertTrue(wait_until(lambda: is_grabbed(self.kbd.name) is True, 4),
                        "daemon did not take the keyboard back once the key was released")
        self.assertTrue(self.daemon.wait_log("resume: devices grabbed again", since=mark))

    # 3. a keyboard vanishes while a key is held -------------------------------

    def test_unplugging_a_keyboard_releases_its_keys(self):
        with FakeKeyboard("B") as kbd_b:
            self.assertTrue(wait_until(lambda: is_grabbed(kbd_b.name) is True, 6),
                            "second keyboard not grabbed by the rescan")
            time.sleep(0.6)
            kbd_b.down(e.KEY_LEFTALT)
            self.assertTrue(wait_until(lambda: e.KEY_LEFTALT in (virtual_keys_down() or []), 3))
            mark = self.daemon.mark()
        # kbd_b is gone, its KEY_UP will never come.
        self.assertTrue(self.daemon.wait_log("clavier", since=mark, timeout=6),
                        "daemon did not notice the keyboard leaving")
        self.assertTrue(wait_until(lambda: virtual_keys_down() == [], 3),
                        f"Alt stayed pressed after its keyboard vanished: {virtual_keys_down()}")

    def test_a_key_held_on_another_keyboard_survives_the_unplug(self):
        self._hold_and_check_reemitted(e.KEY_LEFTCTRL)   # on A, which stays
        with FakeKeyboard("B") as kbd_b:
            self.assertTrue(wait_until(lambda: is_grabbed(kbd_b.name) is True, 6))
            time.sleep(0.6)
            kbd_b.down(e.KEY_LEFTALT)
            self.assertTrue(wait_until(lambda: e.KEY_LEFTALT in (virtual_keys_down() or []), 3))
            mark = self.daemon.mark()
        self.assertTrue(self.daemon.wait_log("clavier", since=mark, timeout=6))
        self.assertTrue(wait_until(lambda: virtual_keys_down() == [e.KEY_LEFTCTRL], 3),
                        f"expected only Ctrl (still held on A) down, got {virtual_keys_down()}")
        self.kbd.up(e.KEY_LEFTCTRL)
        self.assertTrue(wait_until(lambda: virtual_keys_down() == [], 3))

    # 4. the passthrough is replaced ----------------------------------------

    def test_replacing_the_passthrough_releases_the_old_one(self):
        self._hold_and_check_reemitted(e.KEY_LEFTSHIFT)
        mark = self.daemon.mark()
        # A keyboard with pointer axes needs a wider passthrough: the loop
        # creates a new one and closes the old one, keys and all.
        with FakeKeyboard("C", caps={e.EV_KEY: FULL_KEYS, e.EV_REL: [e.REL_X, e.REL_Y]}) as kbd_c:
            self.assertTrue(self.daemon.wait_log("passthrough recreated", since=mark, timeout=8),
                            "the rescan did not replace the passthrough; test is void")
            self.assertTrue(self.daemon.wait_log("released 1 virtual key", since=mark),
                            "Shift was not released on the old passthrough before it was closed")
            self.assertTrue(wait_until(lambda: virtual_keys_down() == [], 3),
                            f"new passthrough not clean: {virtual_keys_down()}")
            self.kbd.up(e.KEY_LEFTSHIFT)
            time.sleep(0.3)
            self.assertEqual(virtual_keys_down(), [])
            del kbd_c

    # 5. grabbing while a key is physically held ------------------------------------

    def test_startup_waits_until_no_key_is_physically_held(self):
        """A restart while Alt+PTT is held: the compositor saw the press on the
        physical keyboard during the ungrabbed window and the fresh grab would
        steal the release. Measured as an endless burst of the PTT character."""
        self.daemon.stop()          # the one setUp started, on a keyboard at rest
        self.kbd.down(e.KEY_F24)    # held BEFORE the daemon comes up
        self.daemon = Daemon()
        self.assertTrue(self.daemon.wait_log("grab deferred", timeout=10),
                        "daemon did not notice the key held at startup")
        time.sleep(1.0)
        self.assertFalse(is_grabbed(self.kbd.name),
                         "daemon grabbed the keyboard while a key was held at startup")
        self.kbd.up(e.KEY_F24)
        self.assertTrue(wait_until(lambda: is_grabbed(self.kbd.name) is True, 5),
                        "daemon did not grab once the key was released")
        self.assertTrue(self.daemon.wait_log("en écoute", timeout=5))

    def test_hotplug_waits_until_no_key_is_physically_held(self):
        with FakeKeyboard("B") as kbd_b:
            kbd_b.down(e.KEY_F24)   # held when the rescan finds it
            mark = self.daemon.mark()
            self.assertTrue(self.daemon.wait_log("hotplug grab deferred", since=mark, timeout=8),
                            "the rescan grabbed a keyboard with a key held, or never saw it")
            self.assertFalse(is_grabbed(kbd_b.name))
            kbd_b.up(e.KEY_F24)
            self.assertTrue(wait_until(lambda: is_grabbed(kbd_b.name) is True, 8),
                            "hotplugged keyboard never grabbed after the key was released")

    # 6. the dictation key under a modifier the daemon does not own -----------------

    def test_dictation_key_release_follows_its_press_through(self):
        """Ctrl+F9 is none of the daemon's chords (Alt selects translation
        here), so the press is passed to the applications; the release must
        follow it, or the compositor keeps F9 down and autorepeats it without
        end (measured on the host with Alt+PTT: a burst of the PTT character
        until another key was pressed)."""
        watcher = find_node(PASSTHROUGH)
        self.kbd.down(e.KEY_LEFTCTRL)
        time.sleep(0.2)
        self.kbd.down(e.KEY_F9)
        time.sleep(0.2)
        self.kbd.up(e.KEY_F9)
        time.sleep(0.2)
        self.kbd.up(e.KEY_LEFTCTRL)
        time.sleep(0.5)
        seen = []
        try:
            while True:
                ev = watcher.read_one()
                if ev is None:
                    break
                if ev.type == e.EV_KEY and ev.code == e.KEY_F9:
                    seen.append(ev.value)
        except BlockingIOError:
            pass
        finally:
            watcher.close()
        self.assertEqual(seen, [1, 0],
                         "the press of the dictation key was passed through but not its release")
        self.assertEqual(virtual_keys_down(), [],
                         f"keys left pressed on the passthrough: {virtual_keys_down()}")

    # 7. stopping the daemon -----------------------------------------------------

    def test_shutdown_releases_the_keys(self):
        self._hold_and_check_reemitted(e.KEY_LEFTSHIFT)
        mark = self.daemon.mark()
        self.daemon.proc.send_signal(signal.SIGTERM)
        self.daemon.proc.wait(timeout=8)
        self.assertTrue(self.daemon.wait_log("released 1 virtual key", since=mark, timeout=2),
                        "Shift was not released before the passthrough was closed at shutdown")


if __name__ == "__main__":
    unittest.main()
