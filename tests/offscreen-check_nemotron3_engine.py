"""Diarization engines of dictee-transcribe: Nemotron 3, and MOSS on demand.

With the availability probes stubbed, checks that:
  - the engine combo offers Nemotron 3 (the default) and MOSS, nothing else;
  - an engine that is not installed is greyed out and the other one is
    selected, without that fallback being saved;
  - the toggle needs one engine and points to dictee-setup without any;
  - a retired engine (auto, multi, sortformer), saved in QSettings or handed
    over by --diar-engine, falls back to Nemotron 3; --diar-engine moss
    selects MOSS;
  - eight distinct speaker colors, the first four unchanged.

QSettings and dictee.conf are read from a throwaway XDG_CONFIG_HOME.
Run: python3 tests/offscreen-check_nemotron3_engine.py
"""
import importlib.util
import os
import sys
import tempfile
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="dictee-n3-check-")
# a configured install, or the window opens the first-run dialog and waits
with open(os.path.join(os.environ["XDG_CONFIG_HOME"], "dictee.conf"), "w") as f:
    f.write("DICTEE_SETUP_DONE=true\n")

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "dictee_transcribe", os.path.join(HERE, "..", "dictee-transcribe.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

MODEL_DIR = "/models/nemotron3-diar"

# ── _nemotron3_dir: both model files, and a diarize-only that knows --engine ──
real_dir = mod._nemotron3_dir
root = tempfile.mkdtemp(prefix="dictee-n3-data-")
saved_env = {k: os.environ.get(k) for k in ("XDG_DATA_HOME", "HOME", "PATH")}
os.environ["XDG_DATA_HOME"] = os.path.join(root, "data")
os.environ["HOME"] = os.path.join(root, "home")
bin_dir = os.path.join(root, "bin")
os.makedirs(bin_dir)
fake = os.path.join(bin_dir, "diarize-only")


def fake_diarize_only(help_text):
    with open(fake, "w") as f:
        f.write(f"#!/bin/sh\necho '{help_text}' >&2\n")
    os.chmod(fake, 0o755)


os.environ["PATH"] = bin_dir + os.pathsep + "/usr/bin:/bin"
fake_diarize_only("  --engine <name>  sortformer or nemotron3")
model = os.path.join(root, "data", "dictee", "nemotron3-diar")
os.makedirs(model)
open(os.path.join(model, "model.onnx"), "w").close()
real_isfile = os.path.isfile
# the model may be installed system-wide on the machine running the check
with mock.patch("os.path.isfile", lambda p: not str(p).startswith(
        "/usr/share/dictee/nemotron3-diar") and real_isfile(p)):
    assert real_dir() is None, "weights missing (download cut short): not usable"
    open(os.path.join(model, "model.onnx_data"), "w").close()
    assert real_dir() == model, real_dir()
    fake_diarize_only("  --sensitivity <0.0-1.0>  Detection threshold")
    assert real_dir() is None, "a diarize-only without --engine cannot run Nemotron 3"
for key, value in saved_env.items():
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value


def stub(nemotron3=True, moss=False):
    mod._nemotron3_dir = (lambda: MODEL_DIR) if nemotron3 else (lambda: None)
    mod._moss_available = lambda: moss


def engines(win):
    combo = win._cmb_diar_engine
    return [combo.itemData(i) for i in range(combo.count())]


def entry(win, data):
    combo = win._cmb_diar_engine
    index = combo.findData(data)
    assert index >= 0, f"no {data!r} entry in the engine combo"
    return combo.model().item(index)


def saved_engine():
    return QSettings("dictee", "transcribe").value("diarize/engine")


# ── two engines: Nemotron 3 by default, MOSS on demand ────────────────
stub(nemotron3=True, moss=True)
win = mod.TranscribeWindow()
assert engines(win) == ["nemotron3", "moss"], engines(win)
assert entry(win, "nemotron3").text() == "Nemotron 3 (max 8)", entry(win, "nemotron3").text()
assert entry(win, "nemotron3").isEnabled() and entry(win, "moss").isEnabled()
assert win._cmb_diar_engine.currentData() == "nemotron3", win._cmb_diar_engine.currentData()
win.close()

# ── a missing engine is greyed out, the other one selected but not saved ──
stub(nemotron3=False, moss=True)
win = mod.TranscribeWindow()
assert not entry(win, "nemotron3").isEnabled(), "Nemotron 3 not usable: entry greyed out"
assert win._cmb_diar_engine.currentData() == "moss", win._cmb_diar_engine.currentData()
assert saved_engine() in (None, "nemotron3"), saved_engine()
assert win._diar_available and win._chk_diarize.isEnabled()
win.close()

stub(nemotron3=True, moss=False)
win = mod.TranscribeWindow()
assert not entry(win, "moss").isEnabled()
assert win._cmb_diar_engine.currentData() == "nemotron3"
assert win._diar_available and win._chk_diarize.isEnabled()
assert "8" in win._chk_diarize.toolTip(), win._chk_diarize.toolTip()
win.close()

# ── no engine: no diarization, and a pointer to the setup ────────────
stub(nemotron3=False, moss=False)
win = mod.TranscribeWindow()
assert not win._diar_available and not win._chk_diarize.isEnabled()
assert "dictee-setup" in win._chk_diarize.toolTip(), win._chk_diarize.toolTip()
win.close()

# ── retired engines fall back to Nemotron 3 ───────────────────────────
QSettings("dictee", "transcribe").setValue("diarize/engine", "multi")
stub(nemotron3=True, moss=True)
win = mod.TranscribeWindow()
assert win._cmb_diar_engine.currentData() == "nemotron3", win._cmb_diar_engine.currentData()
win.close()
win = mod.TranscribeWindow(diar_engine="sortformer")
assert win._cmb_diar_engine.currentData() == "nemotron3", win._cmb_diar_engine.currentData()
win.close()
win = mod.TranscribeWindow(diar_engine="moss")
assert win._cmb_diar_engine.currentData() == "moss", win._cmb_diar_engine.currentData()
win.close()

# ── the ASR list: no faster-whisper, no Parakeet while diarizing ──────
# The throwaway dictee.conf sets no backend: F9 is Parakeet.
stub(nemotron3=True, moss=False)
win = mod.TranscribeWindow()
asr = win._asr_model_combo
specs = [asr.itemData(i) for i in range(asr.count())]
assert "whisper" not in specs, specs
assert "whisper-rust" in specs and "canary" in specs, specs


def asr_item(data):
    return asr.model().item(asr.findData(data))


win._chk_diarize.setChecked(True)
for data in ("parakeet-int8", "parakeet-fp32", ""):
    assert not asr_item(data).isEnabled(), f"{data!r} usable while diarizing"
assert asr.currentData() == "whisper-rust", asr.currentData()
win._chk_diarize.setChecked(False)
for data in ("parakeet-int8", "parakeet-fp32", ""):
    assert asr_item(data).isEnabled(), f"{data!r} still greyed out without diarization"
win.close()

# ── eight distinct colors, the first four as before ───────────────────
assert mod.SPEAKER_COLORS[:4] == ["#e06c75", "#61afef", "#98c379", "#d19a66"]
assert len(mod.SPEAKER_COLORS) == 8 and len(set(mod.SPEAKER_COLORS)) == 8

print("OK")
