#!/usr/bin/env python3
"""The silence threshold slider must reach the values a quiet input needs.

The slider was clamped to 0.010..0.060. On an audio interface with the gain
knob low, speech measures well under that: 0.013 to 0.018 on the setup of
issue #37, where calibration had written 0.023, so every recording was
dropped as silence and dictation appeared to do nothing. A hand-written
0.008 in dictee.conf worked but opening setup clamped it back to 0.010.

Builds the real Microphone page offscreen against a throwaway config.

Run: QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_silence_floor.py
"""
import importlib.util
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_cfg = tempfile.mkdtemp(prefix="dictee-silence-cfg-")
os.environ["XDG_CONFIG_HOME"] = _cfg
os.environ["HOME"] = tempfile.mkdtemp(prefix="dictee-silence-home-")
with open(os.path.join(_cfg, "dictee.conf"), "w", encoding="utf-8") as f:
    f.write("DICTEE_SETUP_DONE=true\n")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("ds", os.path.join(ROOT, "dictee-setup.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["ds"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QWidget  # noqa: E402

app = QApplication([])
root = QWidget()
QVBoxLayout(root)

failures = []


def check(label, got, expected):
    if got == expected:
        print(f"PASS {label}")
    else:
        print(f"FAIL {label}: got {got!r}, expected {expected!r}")
        failures.append(label)


def page(saved_rms="0.03", **conf):
    dlg = mod.DicteeSetupDialog.__new__(mod.DicteeSetupDialog)
    QDialog.__init__(dlg)
    dlg.wizard_mode = False
    host = QWidget()
    root.layout().addWidget(host)
    dlg._build_mic_section(QVBoxLayout(host), dict({"DICTEE_SILENCE_RMS": saved_rms}, **conf))
    return dlg


d = page("0.008")
check("a hand-written 0.008 survives the slider", d.slider_silence.value(), 8)
check("and is shown as typed", d.lbl_silence_val.text(), "0.008")

check("the floor reaches 0.003", page("0.003").slider_silence.value(), 3)
check("below the floor is clamped, not zeroed", page("0.0001").slider_silence.value(), 3)
check("the default is untouched", page("0.03").slider_silence.value(), 30)
check("the ceiling is untouched", page("0.060").slider_silence.value(), 60)
check("above the ceiling still clamps", page("0.2").slider_silence.value(), 60)
check("garbage falls back to the default", page("abc").slider_silence.value(), 30)

d = page("0.008")
check("slider range starts at the floor", d.slider_silence.minimum(), 3)
check("slider range still ends at 60", d.slider_silence.maximum(), 60)

# The threshold marker on the level meter must follow a low value instead of
# collapsing to the bottom of the meter.
d.slider_silence.setValue(5)
check("label follows a low value", d.lbl_silence_val.text(), "0.005")

# --- what happens to the playback, one row per kind of output ----------------
# Left is muted, right is untouched. Speakers default to a mute, a headset to
# untouched: nothing it plays reaches the microphone.

d = page(DICTEE_DUCK_LEVEL="10", DICTEE_DUCK_LEVEL_HEADSET="30")
check("the speakers have a slider", hasattr(d, "slider_duck"), True)
check("the headset has a slider", hasattr(d, "slider_duck_headset"), True)
check("the speaker level is read back", d.slider_duck.value(), 10)
check("the headset level is read back", d.slider_duck_headset.value(), 30)

d = page()
check("speakers default to muted", d.slider_duck.value(), 0)
check("and say so", d.lbl_duck_val.text(), "Muted")
check("a headset defaults to untouched", d.slider_duck_headset.value(), 100)
check("and says so", d.lbl_duck_headset_val.text(), "Untouched")

check("both sliders start at 0", d.slider_duck.minimum(), 0)
check("both sliders end at 100", d.slider_duck.maximum(), 100)
check("a level out of range falls back to the default",
      page(DICTEE_DUCK_LEVEL="900").slider_duck.value(), 0)
check("garbage falls back to the default",
      page(DICTEE_DUCK_LEVEL_HEADSET="abc").slider_duck_headset.value(), 100)

d.slider_duck.setValue(25)
check("the label follows the slider", d.lbl_duck_val.text(), "25 %")
d.slider_duck_headset.setValue(0)
check("a headset can be muted from here too", d.lbl_duck_headset_val.text(), "Muted")

check("the mute combo is gone", hasattr(d, "cmb_mute_output"), False)

if failures:
    print(f"\n{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("\nOK")
