"""An open dictee-setup ignores the ASR backend, the Parakeet variant and the
Force CPU preference when the plasmoid or the tray changes them.

Same hole as the translation backend (fixed earlier): _resync_external_toggles
reconciled only a handful of widgets, so these three kept showing the previous
value until the window was closed and reopened. The plasmoid reaches them via
`dictee-switch-backend asr|quant|force_cpu`, the tray via asr and quant.

Unlike the translation test, this one writes the conf keys itself instead of
running dictee-switch-backend: `asr` stops and disables every ASR daemon on the
machine (dictee-switch-backend:142-156) and quant/force_cpu restart theirs. A
test must never touch the user's running services. The script -> conf half of
the chain is already covered by offscreen-repro_translate_backend_resync.py;
what is exercised here is conf -> watcher -> UI.

Force CPU has a wrinkle worth pinning: _on_apply writes _force_cpu_pref
(dictee-setup.py:20028), not the toggle state, and _on_force_cpu_toggled only
records the preference while the toggle is interactive. Reconciling the toggle
alone would leave Apply writing back the stale preference.
"""
import importlib.util
import os
import re
import shutil
import sys
import tempfile

REPO = "/home/rapha/SOURCES/RAPHA_STT/dictee"
_HOME = tempfile.mkdtemp(prefix="dictee-asr-resync-test-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ["XDG_RUNTIME_DIR"] = _HOME
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

CONF = os.path.join(os.environ["XDG_CONFIG_HOME"], "dictee.conf")
_SRC_CONF = "/home/rapha/.config/dictee.conf"
if os.path.isfile(_SRC_CONF):
    shutil.copy(_SRC_CONF, CONF)
else:
    with open(CONF, "w") as f:
        f.write('DICTEE_ASR_BACKEND=parakeet\nDICTEE_PARAKEET_QUANT=fp32\n'
                'DICTEE_FORCE_CPU=0\n')


def set_conf(key, value):
    """Same effect as dictee-switch-backend's set_conf (line 34)."""
    with open(CONF) as f:
        text = f.read()
    if re.search(rf"^{key}=", text, re.M):
        text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.M)
    else:
        text += f"\n{key}={value}\n"
    with open(CONF, "w") as f:
        f.write(text)


spec = importlib.util.spec_from_file_location("dictee_setup", f"{REPO}/dictee-setup.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_setup"] = mod
spec.loader.exec_module(mod)

assert mod.CONF_PATH == CONF, f"CONF_PATH escaped the sandbox: {mod.CONF_PATH}"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Known starting point
set_conf("DICTEE_ASR_BACKEND", "parakeet")
set_conf("DICTEE_PARAKEET_QUANT", "fp32")
set_conf("DICTEE_FORCE_CPU", "0")

app = QApplication([])
dlg = mod.DicteeSetupDialog()
dlg.show()
app.processEvents()

assert dlg._dirty is False, "settings mode should open clean"
assert dlg.cmb_asr_backend.currentData() == "parakeet", \
    f"combo did not load the conf backend: {dlg.cmb_asr_backend.currentData()}"


def settle(ms=1500):
    QTimer.singleShot(ms, app.quit)
    app.exec()


# 1. ASR backend, as the plasmoid or the tray would change it
set_conf("DICTEE_ASR_BACKEND", "vosk")
settle()
got = dlg.cmb_asr_backend.currentData()
assert got == "vosk", f"combo still shows {got}: an open window ignores the change"
# the per-backend option blocks must follow, not just the combo text
assert not dlg.w_vosk_options.isHidden(), "vosk options did not appear"
assert dlg.w_parakeet_options.isHidden(), "parakeet options stayed shown"
print("PASS asr backend follows (parakeet -> vosk, option blocks swapped)")

set_conf("DICTEE_ASR_BACKEND", "parakeet")
settle()
assert dlg.cmb_asr_backend.currentData() == "parakeet", "did not switch back"
print("PASS asr backend follows back")

# 2. Parakeet variant. The toggle is greyed out when both variants are not
#    installed; in that case the value is not ours to force.
if dlg.tgl_quant.isEnabled():
    before = dlg.tgl_quant.isChecked()
    set_conf("DICTEE_PARAKEET_QUANT", "fp32" if before else "int8")
    settle()
    assert dlg.tgl_quant.isChecked() is (not before), \
        f"quant toggle still {dlg.tgl_quant.isChecked()}"
    print(f"PASS parakeet variant follows ({before} -> {not before})")
else:
    print("SKIP parakeet variant: toggle disabled (both variants not installed)")

# 3. Force CPU. What Apply writes is _force_cpu_pref, so that is what must move.
before_pref = dlg._force_cpu_pref
set_conf("DICTEE_FORCE_CPU", "0" if before_pref else "1")
settle()
assert dlg._force_cpu_pref is (not before_pref), \
    f"_force_cpu_pref still {dlg._force_cpu_pref}: Apply would write the stale value"
if dlg.tgl_force_cpu.isEnabled():
    assert dlg.tgl_force_cpu.isChecked() is (not before_pref), \
        "the toggle did not reflect the new preference"
print(f"PASS force cpu preference follows ({before_pref} -> {not before_pref})")

# Invariants shared with the translation resync
assert dlg._dirty is False, "the resync marked the window dirty"
mtime = os.path.getmtime(CONF)
settle(1200)
assert os.path.getmtime(CONF) == mtime, "the resync rewrote dictee.conf -- feedback loop"
print("PASS window still clean, conf not rewritten")

# Wizard mode is the other UI: the combo, the cards and the toggles may or
# may not exist there, and a resync must never blow up on the missing ones.
# (A first run with the plasmoid already installed is exactly that situation.)
wiz = mod.DicteeSetupDialog(wizard=True)
wiz.show()
app.processEvents()
set_conf("DICTEE_ASR_BACKEND", "vosk")
set_conf("DICTEE_FORCE_CPU", "1")
set_conf("DICTEE_PARAKEET_QUANT", "int8")
wiz._resync_external_toggles()      # what the debounce timer calls
app.processEvents()
print("PASS wizard mode survives a resync")
wiz.close()

shutil.rmtree(_HOME, ignore_errors=True)
print("OK")
