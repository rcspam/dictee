#!/usr/bin/env python3
"""Run dictee-ptt's evdev loop in a sandbox, for tests.

The real daemon grabs every keyboard on the machine and launches `dictee`;
a test cannot let it. This driver loads dictee-ptt.py as a module and, before
starting the loop, swaps out what must not touch the host:

- find_keyboards_evdev() only returns devices whose name starts with the
  prefix given on the command line (the test's fake uinput keyboards);
- the passthrough device gets the name given on the command line, so a real
  dictee-ptt running on the host is never mistaken for the sandbox;
- run_dictee_async() prints instead of launching dictee;
- the pause marker, the state file and the recording pid file live under the
  sandbox directory;
- RESCAN_INTERVAL is shortened so hotplug cases do not wait 10 s.

Everything else (grab, re-emission, key handling) is the real code.

Usage: ptt_sandbox_driver.py <sandbox dir> <keyboard name prefix> <passthrough name>
"""
import importlib.util
import os
import sys

sandbox, prefix, passthrough = sys.argv[1:4]
os.makedirs(sandbox, exist_ok=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("ptt_sandbox", os.path.join(ROOT, "dictee-ptt.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

import evdev  # noqa: E402
from evdev import UInput  # noqa: E402


def sandbox_keyboards(*_a, **_k):
    devs = []
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
        except OSError:
            continue
        # Never our own passthrough: the real finder skips every device whose
        # name carries "dictee-ptt" for the same reason (a grabbed passthrough
        # feeds the daemon its own output).
        if d.name.startswith(prefix) and d.name != passthrough:
            devs.append(d)
        else:
            d.close()
    return devs


def sandbox_passthrough(devices):
    return UInput.from_device(*devices, name=passthrough)


def fake_dictee(*args, **kwargs):
    print(f"[sandbox] dictee {' '.join(args)}", flush=True)


mod.find_keyboards_evdev = sandbox_keyboards
mod._make_passthrough = sandbox_passthrough
mod.run_dictee_async = fake_dictee
mod.PAUSE_PATH = os.path.join(sandbox, "pause")
mod.STATE_FILE = os.path.join(sandbox, "state")
mod.PIDFILE = os.path.join(sandbox, "pid")
mod.RESCAN_INTERVAL = 2
with open(mod.STATE_FILE, "w") as f:
    f.write("idle\n")

# Same key for dictation and translation, Alt selecting translation: the
# common setup, and the one where a modifier wrongly believed held makes
# handle_event let the dictation key through (_any_mod_held branch).
ptt = mod.PttState("hold", evdev.ecodes.KEY_F9, evdev.ecodes.KEY_F9, "alt", "")
mod.run_evdev(ptt)
