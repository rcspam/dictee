"""Parakeet Ultra is listed by dictee_models next to v3 (tdt-ultra directory)."""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "dm", pathlib.Path(__file__).resolve().parent.parent / "dictee_models.py")
dm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dm)


def _layout(tmp_path, monkeypatch, files):
    sys_dir = tmp_path / "sys"
    user_dir = tmp_path / "user"
    for rel in files:
        p = sys_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    user_dir.mkdir()
    monkeypatch.setattr(dm, "SYS_DIR", str(sys_dir))
    monkeypatch.setattr(dm, "DICTEE_DATA", str(user_dir))


def test_ultra_only_is_listed(tmp_path, monkeypatch):
    _layout(tmp_path, monkeypatch, ["tdt-ultra/encoder-model.int8.onnx"])
    names = [m["name"] for m in dm.find_parakeet_models()]
    assert names == ["parakeet-tdt-0.6b-ultra"]


def test_v3_and_ultra_both_listed(tmp_path, monkeypatch):
    _layout(tmp_path, monkeypatch,
            ["tdt/encoder-model.onnx", "tdt-ultra/encoder-model.onnx"])
    names = sorted(m["name"] for m in dm.find_parakeet_models())
    assert names == ["parakeet-tdt-0.6b-ultra", "parakeet-tdt-0.6b-v3"]


def test_empty_ultra_dir_is_ignored(tmp_path, monkeypatch):
    _layout(tmp_path, monkeypatch, ["tdt/encoder-model.onnx", "tdt-ultra/vocab.txt"])
    names = [m["name"] for m in dm.find_parakeet_models()]
    assert names == ["parakeet-tdt-0.6b-v3"]
