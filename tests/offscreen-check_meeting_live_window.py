"""The live meeting window on release/1.3: builds, refuses without engines, speaks French.

Loads dictee-meeting-live (no .py extension, hence SourceFileLoader) with a
throwaway HOME so no real dictee.conf or meetings folder is touched. Nothing
here ever starts a capture: start_meeting is only called when the engine
capability check is guaranteed to fail.

Building the window writes "meeting-ui-open" to the shared state file, which
on a developer machine makes dictee-ptt forward every key. The script exposes
that path as STATE_FILE; the test points it into the throwaway HOME and
refuses to build anything if the constant is missing. The real file is read
at start and compared at the end.

Run: QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_meeting_live_window.py
"""
import importlib.machinery
import importlib.util
import os
import pathlib
import shutil
import stat
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="dictee-meeting-ui-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ["XDG_RUNTIME_DIR"] = _HOME
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LANGUAGE"] = "C"
os.environ["LC_ALL"] = "C"
os.environ["LANG"] = "C"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "dictee-meeting-live")

REAL_STATE = "/dev/shm/.dictee_state"


def read_real_state():
    try:
        with open(REAL_STATE) as f:
            return f.read()
    except OSError:
        return None


_real_state_before = read_real_state()

# The script looks for its catalog in ~/.local/share/locale first (its own
# LOCALE_DIRS order), so the tracked po/fr.mo dropped there is what the
# French rendering check below reads: no msgfmt, no system install involved.
_MO_DIR = os.path.join(_HOME, ".local", "share", "locale", "fr", "LC_MESSAGES")
os.makedirs(_MO_DIR)
shutil.copy(os.path.join(ROOT, "po", "fr.mo"), os.path.join(_MO_DIR, "dictee.mo"))


def load():
    loader = importlib.machinery.SourceFileLoader("meeting_live", SCRIPT)
    spec = importlib.util.spec_from_loader("meeting_live", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["meeting_live"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = load()
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
failures = []


def check(label, got, want):
    if got == want:
        print(f"PASS {label}")
    else:
        failures.append(label)
        print(f"FAIL {label}: got {got!r}, expected {want!r}")


def finish():
    check("real /dev/shm/.dictee_state untouched", read_real_state(), _real_state_before)
    print()
    if failures:
        print(f"{len(failures)} FAILED: " + ", ".join(failures))
        sys.exit(1)
    print("OK")
    sys.exit(0)


# --- 1. construction ---------------------------------------------------------

check("module has a gettext _()", callable(getattr(mod, "_", None)), True)
check("script exposes STATE_FILE", hasattr(mod, "STATE_FILE"), True)
if not hasattr(mod, "STATE_FILE"):
    print("refusing to build the window: it would write the real state file")
    finish()
mod.STATE_FILE = pathlib.Path(_HOME) / "dictee_state"

win = mod.MeetingWindow()
check("window starts idle", win._state, "idle")
check("state went to the sandbox file", mod.STATE_FILE.read_text(), "meeting-ui-open\n")
check("no capture worker at rest", win.audio_worker, None)
for name in ("status_label", "cmb_source", "btn_start", "btn_stop", "btn_analyze",
             "btn_sound_test", "chk_include_mic", "_title_edit"):
    check(f"widget {name} exists", hasattr(win, name), True)
check("start button enabled at rest", win.btn_start.isEnabled(), True)
check("stop button disabled at rest", win.btn_stop.isEnabled(), False)
check("title is prefilled", bool(win._title_edit.text().strip()), True)

# --- 2. engine capability gate -----------------------------------------------

def fake_bin_dir(with_markers):
    """A PATH entry holding transcribe-client and diarize-only stand-ins whose
    --help either documents the streaming flags (master build) or not (1.3)."""
    d = tempfile.mkdtemp(prefix="dictee-fake-engines-")
    help_client = "transcribe-client <file> --json-timestamps  JSON output" if with_markers \
        else "transcribe-client <file>  plain output"
    help_diar = "diarize-only --stream [OPTIONS]" if with_markers \
        else "diarize-only <file> [OPTIONS]"
    for name, text in (("transcribe-client", help_client), ("diarize-only", help_diar)):
        p = os.path.join(d, name)
        with open(p, "w") as f:
            f.write("#!/bin/sh\nprintf '%s\\n' \"" + text + "\" >&2\nexit 1\n")
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return d


class _Msg:
    """Stand-in for QMessageBox: records instead of blocking on a dialog."""
    calls = []

    @staticmethod
    def critical(*a, **k):
        _Msg.calls.append(a)


saved_path = os.environ["PATH"]
saved_box = mod.QMessageBox
mod.QMessageBox = _Msg

os.environ["PATH"] = fake_bin_dir(with_markers=False)
missing = mod.missing_live_engine_features()
check("1.3 engines: both features reported missing", len(missing), 2)

win.start_meeting()
check("start refused: state still idle", win._state, "idle")
check("start refused: no capture worker spawned", win.audio_worker, None)
check("start refused: one error box", len(_Msg.calls), 1)
check("start refused: status names the missing engine",
      "not available" in win.status_label.text(), True)
check("start refused: sandbox state untouched", mod.STATE_FILE.read_text(), "meeting-ui-open\n")

os.environ["PATH"] = fake_bin_dir(with_markers=True)
check("master engines: nothing missing", mod.missing_live_engine_features(), [])

os.environ["PATH"] = tempfile.mkdtemp(prefix="dictee-no-engines-")
check("no engines at all: both reported as not installed",
      all("not installed" in m for m in mod.missing_live_engine_features()), True)

os.environ["PATH"] = saved_path
mod.QMessageBox = saved_box

finish()
