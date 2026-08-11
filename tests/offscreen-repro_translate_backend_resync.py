"""Changing the translation backend from the plasmoid does not reach an open
dictee-setup window.

The plasmoid runs `dictee-switch-backend translate <backend>`, which rewrites
DICTEE_TRANSLATE_BACKEND (and DICTEE_TRANS_ENGINE for google/bing) in
dictee.conf. dictee-setup already watches that file, but _resync_external_toggles
only reconciles four checkboxes -- audio context, LLM post-process and the two
short-text ones -- so the backend combo keeps showing the old value until the
window is closed and reopened.

The full chain is exercised: the real dictee-switch-backend writes the real
conf (inside a throwaway HOME), the real QFileSystemWatcher fires, and the Qt
event loop runs long enough for the debounce timer to resync.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

REPO = "/home/rapha/SOURCES/RAPHA_STT/dictee"
_HOME = tempfile.mkdtemp(prefix="dictee-resync-test-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ["XDG_RUNTIME_DIR"] = _HOME
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Start from the user's own conf so the window opens in settings mode with a
# realistic state. Only the sandbox copy is ever written to.
_REAL_CONF = os.path.expanduser("~/.config/dictee.conf")  # already sandboxed HOME
_SRC_CONF = "/home/rapha/.config/dictee.conf"
SANDBOX_CONF = os.path.join(os.environ["XDG_CONFIG_HOME"], "dictee.conf")
if os.path.isfile(_SRC_CONF):
    shutil.copy(_SRC_CONF, SANDBOX_CONF)
else:
    with open(SANDBOX_CONF, "w") as f:
        f.write('DICTEE_TRANSLATE_BACKEND="trans"\nDICTEE_TRANS_ENGINE="google"\n')

spec = importlib.util.spec_from_file_location("dictee_setup", f"{REPO}/dictee-setup.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_setup"] = mod
spec.loader.exec_module(mod)

assert mod.CONF_PATH == SANDBOX_CONF, f"CONF_PATH escaped the sandbox: {mod.CONF_PATH}"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer


def conf_backend():
    out = subprocess.run(
        ["bash", "-c", f'source "{SANDBOX_CONF}"; echo "$DICTEE_TRANSLATE_BACKEND|$DICTEE_TRANS_ENGINE"'],
        capture_output=True, text=True).stdout.strip()
    return out


def switch(backend):
    """Exactly what the plasmoid runs (FullRepresentation.qml:783)."""
    r = subprocess.run([f"{REPO}/dictee-switch-backend", "translate", backend],
                       capture_output=True, text=True, env={**os.environ})
    assert r.returncode == 0, f"switch-backend failed: {r.stderr}"


# Start from a known backend so the change is unambiguous
switch("google")
assert conf_backend().startswith("trans|google"), conf_backend()

app = QApplication([])
dlg = mod.DicteeSetupDialog()
dlg.show()          # a hidden window may skip deferred wiring
app.processEvents()

assert dlg._dirty is False, "settings mode should open clean"
start = dlg.cmb_trans_backend.currentData()
assert start == "trans:google", f"combo did not load the conf backend: {start}"
print(f"open with: {start}")

# The plasmoid changes it while the window stays open
switch("libretranslate")
assert conf_backend().startswith("libretranslate"), conf_backend()

# Let the watcher fire and the 200 ms debounce elapse
QTimer.singleShot(1500, app.quit)
app.exec()

now = dlg.cmb_trans_backend.currentData()
print(f"after plasmoid switch: conf={conf_backend()} combo={now}")
assert now == "libretranslate", \
    f"combo still shows {now}: an open window ignores the plasmoid change"

# Reconciling from disk is not a user edit: OK must not re-run Apply for it
assert dlg._dirty is False, "the resync marked the window dirty"

# The panels that depend on the backend must follow, not just the combo text.
# isHidden(), not isVisible(): the translation page is not the one on screen,
# so every widget it holds is invisible regardless of the backend. What we
# check is the explicit show/hide the index handler performs.
assert not dlg.lt_widget.isHidden(), "LibreTranslate panel did not appear with the backend"

# And back the other way, including the engine sub-choice
switch("bing")
QTimer.singleShot(1500, app.quit)
app.exec()
now = dlg.cmb_trans_backend.currentData()
assert now == "trans:bing", f"combo shows {now} after switching to bing"
assert dlg.lt_widget.isHidden(), "LibreTranslate panel stayed shown after switching away"

# Non-regression: the four checkboxes this resync already handled must keep
# following the conf. Audio context is the cheapest of them to flip.
before_ctx = dlg.chk_audio_context.isChecked()
subprocess.run([f"{REPO}/dictee-switch-backend", "context",
                "false" if before_ctx else "true"],
               capture_output=True, text=True, check=True)
QTimer.singleShot(1500, app.quit)
app.exec()
assert dlg.chk_audio_context.isChecked() is (not before_ctx), \
    "audio context checkbox stopped following the conf"
print(f"PASS audio context still resyncs ({before_ctx} -> {not before_ctx})")

# The sandbox holds a copy of the user's own conf: do not leave it in /tmp.
# Kept on failure, since the assertions above exit before this point.
shutil.rmtree(_HOME, ignore_errors=True)
print("OK")
