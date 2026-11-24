"""Parakeet variant helpers of dictee-setup (v3 / Ultra x FP32 / INT8)."""
import importlib.util
import os
import pathlib
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="dictee-ultra-setup-test-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

spec = importlib.util.spec_from_file_location(
    "dictee_setup", pathlib.Path(__file__).resolve().parent.parent / "dictee-setup.py")
ds = importlib.util.module_from_spec(spec)
sys.modules["dictee_setup"] = ds
spec.loader.exec_module(ds)

ALL = ["ultra:fp32", "ultra:int8", "v3:fp32", "v3:int8"]


def test_tdt_models_ultra_first():
    keys = [ds.parakeet_variant_key(m) for m in ds.PARAKEET_TDT_MODELS]
    assert keys == ALL


def test_titles():
    titles = [ds.parakeet_variant_title(m) for m in ds.PARAKEET_TDT_MODELS]
    assert titles == ["Ultra FP32", "Ultra INT8", "v3 FP32", "v3 INT8"]


def test_ultra_dirs_shared():
    dirs = {m["dir"] for m in ds.PARAKEET_TDT_MODELS if m["variant"] == "ultra"}
    assert len(dirs) == 1 and next(iter(dirs)).endswith("/tdt-ultra")


def test_existing_install_without_model_key_stays_v3():
    assert ds.resolve_parakeet_variant("", "int8", ALL, "ultra:fp32") == "v3:int8"


def test_fresh_conf_takes_recommendation():
    assert ds.resolve_parakeet_variant("", "", ALL, "ultra:int8") == "ultra:int8"


def test_conf_ultra():
    assert ds.resolve_parakeet_variant("ultra", "fp32", ALL, "v3:int8") == "ultra:fp32"


def test_model_without_quant_takes_recommended_quant():
    assert ds.resolve_parakeet_variant("ultra", "", ALL, "ultra:int8") == "ultra:int8"


def test_conf_variant_not_installed_falls_back_to_first_installed():
    assert ds.resolve_parakeet_variant("v3", "fp32", ["ultra:int8"], "ultra:fp32") == "ultra:int8"


def test_nothing_installed_keeps_conf_choice():
    assert ds.resolve_parakeet_variant("ultra", "int8", [], "v3:fp32") == "ultra:int8"


def test_garbage_conf_values():
    assert ds.resolve_parakeet_variant("v9", "fp16", ALL, "ultra:fp32") == "ultra:fp32"


def test_save_config_writes_model(tmp_path, monkeypatch):
    conf = tmp_path / "dictee.conf"
    monkeypatch.setattr(ds, "CONF_PATH", str(conf))
    ds.save_config("trans", "fr", "en", asr_backend="parakeet", parakeet_model="ultra",
                   parakeet_quant="int8", mark_setup_done=False)
    text = conf.read_text()
    assert "DICTEE_PARAKEET_MODEL=ultra" in text
    assert "DICTEE_PARAKEET_QUANT=int8" in text
