"""Retired diarization models on the Diarization page of dictee-setup.

Sortformer and the multi-speaker model (diarize-multi) left dictee in 1.4;
their models stay on disk after an upgrade. Checks that:
  - nothing is shown when neither is left, nor for an empty directory;
  - each one left gets a row with its size, system and user dirs added up;
  - Delete asks first, and No keeps everything;
  - Yes deletes the model's directories and hides its row, then the box once
    the last row is gone;
  - a directory that cannot be deleted goes through pkexec, and if it is
    still there the row stays and a warning names the model.

The two methods are called on a bare widget: no setup dialog is built. The
system and user model dirs are throwaway ones, never /usr/share/dictee.
Run: python3 tests/offscreen-check_retired_models.py
"""
import importlib.util
import os
import sys
import tempfile
from unittest import mock

_HOME = tempfile.mkdtemp(prefix="dictee-retired-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ["XDG_RUNTIME_DIR"] = _HOME
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# the assertions read the msgids
os.environ["LANGUAGE"] = "C"
os.environ["LC_ALL"] = "C"
os.environ["LANG"] = "C"

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dictee-setup.py")
spec = importlib.util.spec_from_file_location("dictee_setup", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_setup"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import (QApplication, QGroupBox, QLabel,  # noqa: E402
                             QMessageBox, QPushButton, QVBoxLayout, QWidget)

app = QApplication.instance() or QApplication([])

SYS = os.path.join(_HOME, "usr-share-dictee")
assert mod.DICTEE_DATA_DIR.startswith(_HOME), mod.DICTEE_DATA_DIR
for model in mod.RETIRED_MODELS:
    model["dir"] = model["dir"].replace(mod.MODEL_DIR, SYS)
mod.MODEL_DIR = SYS
SORTFORMER, DIAR = mod.RETIRED_MODELS


def put(path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.truncate(size)


class Host(QWidget):
    _build_retired_models_box = mod.DicteeSetupDialog._build_retired_models_box
    _on_retired_model_delete = mod.DicteeSetupDialog._on_retired_model_delete


def page():
    host = Host()
    lay = QVBoxLayout(host)
    host._build_retired_models_box(lay)
    boxes = host.findChildren(QGroupBox)
    assert len(boxes) <= 1, boxes
    return host, (boxes[0] if boxes else None)


def rows(box):
    """Label text and Delete button of each row, in order."""
    out = []
    for btn in box.findChildren(QPushButton):
        row = btn.parentWidget()
        label = [w for w in row.findChildren(QLabel)][0]
        out.append((label.text(), btn, row))
    return out


def answer(reply):
    return mock.patch.object(mod.QMessageBox, "question", return_value=reply)


# ── nothing left: no box, an empty directory does not count ──
host, box = page()
assert box is None, "no retired model on disk: no box"
os.makedirs(os.path.join(mod.DICTEE_DATA_DIR, "sortformer"))
host, box = page()
assert box is None, "an empty directory is not a model left behind"

# ── Sortformer in both dirs, the multi-speaker model in the user one ──
put(os.path.join(SYS, "sortformer", "model.onnx"), 2_000_000)
put(os.path.join(mod.DICTEE_DATA_DIR, "sortformer", "model.onnx"), 1_000_000)
put(os.path.join(mod.DICTEE_DATA_DIR, "diar", "seg", "model.onnx"), 1_000_000)
host, box = page()
assert box is not None and box.title() == "Retired models", box
r = rows(box)
assert [t for t, _b, _r in r] == ["Sortformer: 3 MB", "Multi-speaker diarization: 1 MB"], r
assert all(b.text() == "Delete" for _t, b, _r in r)
host.show()

# ── No keeps everything ──
with answer(QMessageBox.StandardButton.No) as q:
    r[0][1].click()
assert q.call_count == 1
assert "Sortformer" in q.call_args.args[2], q.call_args
assert mod.retired_model_dirs(SORTFORMER), "No must not delete"
assert not r[0][2].isHidden()

# ── Yes deletes both Sortformer dirs and hides its row, the box stays ──
with answer(QMessageBox.StandardButton.Yes):
    r[0][1].click()
assert not os.path.exists(os.path.join(SYS, "sortformer"))
assert not os.path.exists(os.path.join(mod.DICTEE_DATA_DIR, "sortformer"))
assert r[0][2].isHidden() and not box.isHidden()

# ── a directory that resists: pkexec is tried, the row stays, a warning ──
calls = []
with answer(QMessageBox.StandardButton.Yes), \
        mock.patch.object(mod.shutil, "rmtree", side_effect=PermissionError), \
        mock.patch.object(mod.subprocess, "run", lambda cmd, **kw: calls.append(cmd)), \
        mock.patch.object(mod.QMessageBox, "warning") as warn:
    r[1][1].click()
diar_dir = os.path.join(mod.DICTEE_DATA_DIR, "diar")
assert calls == [["pkexec", "rm", "-rf", diar_dir]], calls
assert warn.call_count == 1 and warn.call_args.args[2] == \
    "Could not delete Multi-speaker diarization.", warn.call_args
assert not r[1][2].isHidden() and not box.isHidden()

# ── the last one deleted: the box goes ──
with answer(QMessageBox.StandardButton.Yes):
    r[1][1].click()
assert not os.path.exists(diar_dir)
assert r[1][2].isHidden() and box.isHidden()

# ── a page never shown: only the rows deleted count as gone ──
put(os.path.join(SYS, "sortformer", "model.onnx"), 1_000_000)
put(os.path.join(SYS, "diar", "model.onnx"), 1_000_000)
host, box = page()
r = rows(box)
with answer(QMessageBox.StandardButton.Yes):
    r[0][1].click()
assert r[0][2].isHidden() and not box.isHidden(), "one model left: the box stays"
with answer(QMessageBox.StandardButton.Yes):
    r[1][1].click()
assert box.isHidden()

print("OK")
