"""Nemotron 3 Diarization in the engine combo of dictee-transcribe.

With the availability probes stubbed, checks that:
  - the "Nemotron 3 (max 8)" entry is greyed out when Nemotron 3 is not
    usable and enabled when it is, the other entries keeping their own
    state (looked up by data, the entry shifts MOSS down by one);
  - choosing it keeps diarize-multi out of the run (_diar_allow_multi), and
    the chunked worker then runs diarize-only with its model directory;
  - --diar-engine nemotron3 selects it;
  - the toggle is enabled when Nemotron 3 is the only engine installed;
  - eight distinct speaker colors, the first four unchanged.

QSettings and dictee.conf are read from a throwaway XDG_CONFIG_HOME.
Run: python3 tests/offscreen-check_nemotron3_engine.py
"""
import importlib.util
import os
import sys
import tempfile

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


def stub(nemotron3=True, multi=True, sortformer=True, moss=False):
    mod._nemotron3_dir = (lambda: MODEL_DIR) if nemotron3 else (lambda: None)
    mod._diar_multi_available = lambda: multi
    mod._sortformer_available = lambda: sortformer
    mod._moss_available = lambda: moss


def entry(win, data):
    combo = win._cmb_diar_engine
    index = combo.findData(data)
    assert index >= 0, f"no {data!r} entry in the engine combo"
    return combo.model().item(index)


# ── availability drives each entry, by data ───────────────────────────
stub(nemotron3=False, multi=True, sortformer=True, moss=True)
win = mod.TranscribeWindow()
assert entry(win, "nemotron3").text() == "Nemotron 3 (max 8)", entry(win, "nemotron3").text()
assert not entry(win, "nemotron3").isEnabled(), "Nemotron 3 not usable: entry greyed out"
assert entry(win, "multi").isEnabled() and entry(win, "sortformer").isEnabled()
assert entry(win, "moss").isEnabled(), "MOSS moved down one row and must keep its state"
win.close()

stub(nemotron3=True, multi=False, sortformer=True, moss=False)
win = mod.TranscribeWindow()
assert entry(win, "nemotron3").isEnabled(), "Nemotron 3 usable: entry enabled"
assert not entry(win, "multi").isEnabled() and not entry(win, "moss").isEnabled()

# ── choosing it keeps diarize-multi out ───────────────────────────────
win._cmb_diar_engine.setCurrentIndex(win._cmb_diar_engine.findData("nemotron3"))
assert win._diar_allow_multi() is False
for data in ("auto", "multi", "moss"):
    win._cmb_diar_engine.setCurrentIndex(win._cmb_diar_engine.findData(data))
    assert win._diar_allow_multi() is True, data
win._cmb_diar_engine.setCurrentIndex(win._cmb_diar_engine.findData("sortformer"))
assert win._diar_allow_multi() is False
win.close()

# ── the chunked worker hands the model directory to diarize-only ──────
stub(nemotron3=True, multi=True, sortformer=True)
worker = mod._ChunkedPipelineWorker(
    "/tmp/a.wav", 0.5, diarize=True, allow_diar_multi=False, diar_engine="nemotron3")
assert worker._use_diar_multi is False
assert worker._diar_engine_args == [MODEL_DIR, "--engine", "nemotron3"], worker._diar_engine_args
worker = mod._ChunkedPipelineWorker(
    "/tmp/a.wav", 0.5, diarize=True, allow_diar_multi=False, diar_engine="sortformer")
assert worker._diar_engine_args == [], "Sortformer runs diarize-only without engine arguments"
worker = mod._ChunkedPipelineWorker("/tmp/a.wav", 0.0, diarize=False, diar_engine="nemotron3")
assert worker._diar_engine_args == [], "no diarization, no engine arguments"

# ── --diar-engine nemotron3 selects it ────────────────────────────────
stub(nemotron3=True)
win = mod.TranscribeWindow(diar_engine="nemotron3")
assert win._cmb_diar_engine.currentData() == "nemotron3", win._cmb_diar_engine.currentData()
win.close()

# ── Nemotron 3 alone is enough to diarize ─────────────────────────────
stub(nemotron3=True, multi=False, sortformer=False, moss=False)
win = mod.TranscribeWindow()
assert win._diar_available, "the diarize toggle needs at least one engine"
assert win._chk_diarize.isEnabled()
assert "8" in win._chk_diarize.toolTip(), win._chk_diarize.toolTip()
win.close()

# ── eight distinct colors, the first four as before ───────────────────
assert mod.SPEAKER_COLORS[:4] == ["#e06c75", "#61afef", "#98c379", "#d19a66"]
assert len(mod.SPEAKER_COLORS) == 8 and len(set(mod.SPEAKER_COLORS)) == 8

print("OK")
