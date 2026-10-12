"""The Whisper install of dictee-setup must keep PyAV below 19.

faster-whisper 1.2.1 opens audio with av.open(..., metadata_errors="ignore")
and only asks for av>=11. PyAV 19.0.0 (2026-09-29) removed that argument, so
a Whisper environment installed after that date answered every request with
"TypeError: open() got an unexpected keyword argument 'metadata_errors'":
dictation and the live meeting preview both came back empty (kubuntu-2604,
2026-10-02). The install now carries the pin as a second requirement.

subprocess.run is captured: nothing is installed, no network.

Usage: python3 tests/offscreen-check_whisper_install_pin.py
"""
import importlib.util
import os
import re
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="dictee-whisper-pin-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ["XDG_RUNTIME_DIR"] = _HOME
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LANGUAGE"] = "C"
os.environ["LC_ALL"] = "C.UTF-8"
os.environ["LANG"] = "C.UTF-8"

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dictee-setup.py")
spec = importlib.util.spec_from_file_location("dictee_setup", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_setup"] = mod
spec.loader.exec_module(mod)

failures = []


def check(label, got, want):
    if got == want:
        print(f"PASS {label}")
    else:
        failures.append(label)
        print(f"FAIL {label}: got {got!r}, expected {want!r}")


class Done:
    returncode = 0
    stdout = ""
    stderr = ""


commands = []


def fake_run(cmd, **_kwargs):
    commands.append(list(cmd))
    return Done()


pip_spec = getattr(mod, "WHISPER_PIP_SPEC", "")
check("the Whisper requirement set names faster-whisper", "faster-whisper" in pip_spec.split(), True)
check("the Whisper requirement set keeps PyAV below 19", "av<19" in pip_spec.split(), True)

real_run = mod.subprocess.run
mod.subprocess.run = fake_run
try:
    mod.VenvInstallThread(os.path.join(_HOME, "whisper-env"), pip_spec or "faster-whisper").run()
finally:
    mod.subprocess.run = real_run

install = [c for c in commands if "install" in c and "pip" in c and "--upgrade" in c and "pip" != c[-1]]
check("one package install command was run", len(install), 1)
args = install[0] if install else []
check("faster-whisper is its own pip argument", "faster-whisper" in args, True)
check("the PyAV pin is its own pip argument", "av<19" in args, True)

src = open(SRC, encoding="utf-8").read()
check("the Install Whisper button installs that requirement set",
      bool(re.search(r'_install_venv\("whisper", WHISPER_VENV, WHISPER_PIP_SPEC\)', src)), True)

print()
if failures:
    print(f"{len(failures)} FAILED: " + ", ".join(failures))
    sys.exit(1)
print("OK")
