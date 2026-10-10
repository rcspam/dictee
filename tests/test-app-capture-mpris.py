#!/usr/bin/env python3
"""Recording an application must never pause it.

WirePlumber 0.5.11+ (scripts/linking/mpris-pause.lua) pauses every MPRIS
player linked, even indirectly, to a sink that goes away. dictee-app-capture
used to record an application through a private Audio/Sink, and the meeting
window stopped one at Play (the meter's capture) and another at Stop: the
player paused each time (Decibels, 2026-10-10). It now records through a
virtual source, which WirePlumber never treats as a player's output.

Bench: a stand-in MPRIS player on the session bus counts the Pause calls it
gets; its child gst-launch plays a sine into a muted null sink, so nothing
reaches the speakers and WirePlumber finds that player (by pid) and no other.
The meeting window runs offscreen with its own HOME, its live preview, Do Not
Disturb and loudness normalization switched off, and its state file moved
out of /dev/shm.

Local only: skips without PipeWire, WirePlumber's mpris-pause enabled or a
session bus. The microphone cases record the default mic into a temporary
folder, deleted at the end.

Run: python3 tests/test-app-capture-mpris.py [-v]
"""

import importlib.util
import math
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.environ.get("DICTEE_APP_CAPTURE",
                     os.path.join(ROOT, "target", "release", "dictee-app-capture"))
SCRIPT = os.path.join(ROOT, "dictee-meeting-live")

KEY = "dicteetestplayer"              # application.name of the stand-in player
TEST_SINK = f"dictee_test_out_{os.getpid()}"
SETTLE = 1.5                          # WirePlumber pauses within milliseconds

PLAYER = r'''
import signal, subprocess, sys
from gi.repository import Gio, GLib

suffix, sink, app = sys.argv[1:4]
XML = """<node>
 <interface name="org.mpris.MediaPlayer2">
  <method name="Raise"/><method name="Quit"/>
  <property name="Identity" type="s" access="read"/>
  <property name="CanQuit" type="b" access="read"/>
  <property name="CanRaise" type="b" access="read"/>
  <property name="HasTrackList" type="b" access="read"/>
 </interface>
 <interface name="org.mpris.MediaPlayer2.Player">
  <method name="Play"/><method name="Pause"/><method name="PlayPause"/>
  <method name="Stop"/><method name="Next"/><method name="Previous"/>
  <property name="PlaybackStatus" type="s" access="read"/>
  <property name="CanControl" type="b" access="read"/>
  <property name="CanPlay" type="b" access="read"/>
  <property name="CanPause" type="b" access="read"/>
 </interface>
</node>"""
PROPS = {"Identity": GLib.Variant("s", app), "CanQuit": GLib.Variant("b", False),
         "CanRaise": GLib.Variant("b", False), "HasTrackList": GLib.Variant("b", False),
         "PlaybackStatus": GLib.Variant("s", "Playing"),
         "CanControl": GLib.Variant("b", True), "CanPlay": GLib.Variant("b", True),
         "CanPause": GLib.Variant("b", True)}
loop = GLib.MainLoop()
gst = None

def call(conn, sender, path, iface, method, params, inv):
    print("CALL " + method, flush=True)
    inv.return_value(None)

def prop(conn, sender, path, iface, name):
    return PROPS[name]

def acquired(conn, name):
    for iface in Gio.DBusNodeInfo.new_for_xml(XML).interfaces:
        conn.register_object("/org/mpris/MediaPlayer2", iface, call, prop, None)

def owned(conn, name):
    global gst
    gst = subprocess.Popen(
        ["gst-launch-1.0", "-q", "audiotestsrc", "is-live=true", "volume=0.5",
         "freq=440", "!", "audioconvert", "!", "pulsesink", "device=" + sink,
         "client-name=" + app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("READY", flush=True)

def quit_():
    if gst is not None:
        gst.terminate()
        gst.wait()
    loop.quit()
    return False

Gio.bus_own_name(Gio.BusType.SESSION, "org.mpris.MediaPlayer2." + suffix,
                 Gio.BusNameOwnerFlags.NONE, acquired, owned, lambda c, n: quit_())
GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, quit_)
loop.run()
'''


def _run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10)


def _why_skip():
    for tool in ("pactl", "pw-record", "pw-dump", "wpctl", "gst-launch-1.0"):
        if shutil.which(tool) is None:
            return f"{tool} missing"
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return "no session bus"
    if not any(os.path.isfile(os.path.join(d, "wireplumber/scripts/linking/mpris-pause.lua"))
               for d in ("/usr/share", "/usr/local/share", "/etc")):
        return "WirePlumber without mpris-pause.lua (< 0.5.11)"
    try:
        if "true" not in _run("wpctl", "settings", "linking.pause-playback").stdout:
            return "linking.pause-playback is off"
    except (OSError, subprocess.SubprocessError):
        return "wpctl settings failed"
    if not os.access(BIN, os.X_OK):
        return f"{BIN} not built"
    return None


def _stream_linked(app):
    """True once a stream of `app` is linked to something."""
    import json
    nodes = json.loads(_run("pw-dump").stdout or "[]")
    ids = {n["id"] for n in nodes if n.get("type") == "PipeWire:Interface:Node"
           and n.get("info", {}).get("props", {}).get("application.name") == app}
    return any(n.get("type") == "PipeWire:Interface:Link"
               and n.get("info", {}).get("output-node-id") in ids for n in nodes)


def _wav_rms(path, skip=0.5, tail=0.2):
    """RMS (0-1) of a 16 kHz mono s16 WAV, without its first and last moments."""
    with open(path, "rb") as f:
        data = f.read()
    at = data.find(b"data")
    pcm = data[at + 8:] if at >= 0 else b""
    n = len(pcm) // 2
    samples = struct.unpack(f"<{n}h", pcm[:n * 2])
    samples = samples[int(skip * 16000):max(0, n - int(tail * 16000))]
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768


class Player:
    """The stand-in MPRIS player and the calls it receives."""

    def __init__(self):
        self.calls = []
        self.proc = subprocess.Popen(
            [sys.executable, "-c", PLAYER, f"dicteetest{os.getpid()}",
             TEST_SINK, KEY], stdout=subprocess.PIPE, text=True)
        ready = threading.Event()

        def read():
            for line in self.proc.stdout:
                line = line.strip()
                if line == "READY":
                    ready.set()
                elif line.startswith("CALL "):
                    self.calls.append(line[5:])
        threading.Thread(target=read, daemon=True).start()
        if not ready.wait(5):
            raise RuntimeError("stand-in player did not start")
        deadline = time.time() + 5
        while not _stream_linked(KEY):
            if time.time() > deadline:
                raise RuntimeError("stand-in player stream never linked")
            time.sleep(0.1)

    def stops_since(self, mark):
        return [c for c in self.calls[mark:] if c in ("Pause", "PlayPause", "Stop")]

    def close(self):
        self.proc.terminate()
        self.proc.wait(5)


def setUpModule():
    global MODULE_SINK, PLAYER_PROC
    why = _why_skip()
    if why:
        raise unittest.SkipTest(why)
    MODULE_SINK = _run("pactl", "load-module", "module-null-sink",
                       f"sink_name={TEST_SINK}").stdout.strip()
    PLAYER_PROC = Player()


def tearDownModule():
    PLAYER_PROC.close()
    _run("pactl", "unload-module", MODULE_SINK)


class AppCaptureBinary(unittest.TestCase):

    def test_stopping_the_capture_does_not_pause_the_player(self):
        name = f"dictee_meeting_{os.getpid()}_{KEY}"
        mark = len(PLAYER_PROC.calls)
        cap = subprocess.Popen(
            [BIN, "--source-name", name, "--description",
             "Dictée réunion : test", "--match", KEY],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            self.assertTrue(cap.stdout.readline().startswith("READY"))
            time.sleep(0.5)
            sources = _run("pactl", "list", "sources", "short").stdout
            sinks = _run("pactl", "list", "sinks", "short").stdout
            wav = os.path.join(TMP, "binary.wav")
            subprocess.run(["timeout", "2", "pw-record", "--format=s16",
                            "--rate=16000", "--channels=1", f"--target={name}", wav])
        finally:
            cap.terminate()
            cap.wait(5)
        time.sleep(SETTLE)
        self.assertEqual(PLAYER_PROC.stops_since(mark), [],
                         "WirePlumber paused the player when the capture stopped")
        self.assertIn(name, sources, "no virtual source of that name")
        self.assertNotIn(name, sinks, "the capture is still a sink")
        self.assertGreater(_wav_rms(wav), 0.2, "the source does not carry the player")


class MeetingWindowCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            from PyQt6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PyQt6 missing")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])
        loader = SourceFileLoader("dictee_meeting_live", SCRIPT)
        mod = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(mod)
        state = os.path.join(TMP, "dictee_state")

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
        real = subprocess.check_output

        def check_output(cmd, *a, **kw):
            # The 'default sink' the window sees is the muted test sink, so the
            # Mix case plays nothing on the speakers.
            if list(cmd) == ["pactl", "get-default-sink"]:
                return TEST_SINK + "\n"
            return real(cmd, *a, **kw)

        mod.subprocess = type(sys)("subprocess_shim")
        mod.subprocess.__dict__.update(subprocess.__dict__)
        mod.subprocess.check_output = check_output
        cls.mod = mod

    def spin(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.app.processEvents()
            time.sleep(0.02)

    def meeting(self, source, include_mic=False, level=None, seconds=3):
        """Open the window on `source`, record `seconds`, stop, close.
        Returns (pauses after Stop, pauses at close, recording path)."""
        conf = os.path.join(os.environ["HOME"], ".config", "dictee.conf")
        os.makedirs(os.path.dirname(conf), exist_ok=True)
        with open(conf, "w") as f:
            f.write(f"DICTEE_MEETING_AUDIO_SOURCE={source}\n"
                    f"DICTEE_MEETING_INCLUDE_MIC={'true' if include_mic else 'false'}\n"
                    "DICTEE_MEETING_ALWAYS_ON_TOP=false\n")
        # each case starts from the default level, not the last case's
        levels = os.path.join(os.path.dirname(conf), "dictee", "meeting-levels.json")
        if os.path.exists(levels):
            os.unlink(levels)
        win = self.mod.MeetingWindow()
        self.assertEqual(win.cmb_source.currentData(), source,
                         "source not offered by the window")
        win.show()
        self.spin(2.5)                         # the meter's capture settles
        if level is not None:
            win.slider_sys["slider"].setValue(level)
            self.spin(0.5)
        mark = len(PLAYER_PROC.calls)
        win.btn_start.click()
        self.spin(seconds)
        win.btn_stop.click()
        self.spin(SETTLE)
        at_stop = PLAYER_PROC.stops_since(mark)
        wav = str(win.audio_wav)
        mark = len(PLAYER_PROC.calls)
        win.close()
        self.spin(SETTLE)
        return at_stop, PLAYER_PROC.stops_since(mark), wav

    def test_app_source_play_stop_close(self):
        at_stop, at_close, wav = self.meeting(f"app:{KEY}")
        self.assertEqual(at_stop, [], "the player was paused by Play or Stop")
        self.assertEqual(at_close, [], "the player was paused by closing the window")
        self.assertGreater(_wav_rms(wav), 0.05, "the recording misses the player")

    def test_app_source_with_mic(self):
        at_stop, at_close, _ = self.meeting(f"app:{KEY}", include_mic=True)
        self.assertEqual(at_stop, [], "the player was paused by Play or Stop")
        self.assertEqual(at_close, [], "the player was paused by closing the window")

    def test_mix_source(self):
        at_stop, at_close, _ = self.meeting("mix")
        self.assertEqual(at_stop, [], "the player was paused by Play or Stop")
        self.assertEqual(at_close, [], "the player was paused by closing the window")

    def test_app_level_slider(self):
        full = _wav_rms(self.meeting(f"app:{KEY}", level=100)[2])
        half = _wav_rms(self.meeting(f"app:{KEY}", level=50)[2])
        self.assertGreater(full, 0.05, "the recording misses the player")
        # pactl volumes are cubic: 50 % is 0.5 ** 3 in amplitude
        self.assertAlmostEqual(half / full, 0.125, delta=0.0125,
                               msg=f"50 % gave {half:.4f} against {full:.4f} at 100 %")


if __name__ == "__main__":
    TMP = tempfile.mkdtemp(prefix="dictee-app-capture-mpris-")
    os.environ["HOME"] = TMP
    os.environ["DICTEE_MEETING_DIR"] = os.path.join(TMP, "meetings")
    # the window runs dictee-app-capture from PATH: the one under test
    os.makedirs(os.path.join(TMP, "bin"))
    os.symlink(BIN, os.path.join(TMP, "bin", "dictee-app-capture"))
    os.environ["PATH"] = os.pathsep.join(
        [os.path.join(TMP, "bin"), ROOT, os.environ["PATH"]])
    try:
        unittest.main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
