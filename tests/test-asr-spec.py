import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "dt", pathlib.Path(__file__).resolve().parent.parent / "dictee-transcribe.py")
# Import only the function without launching the UI: the module's UI code must be
# guarded under `if __name__ == "__main__":` for this import to work cleanly.
dt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dt)


def test_parakeet_int8():
    assert dt.asr_spec_to_daemon("parakeet-int8") == {
        "backend": "parakeet",
        "env": {"DICTEE_PARAKEET_QUANT": "int8", "DICTEE_FORCE_CPU": "1"},
    }


def test_parakeet_fp32():
    assert dt.asr_spec_to_daemon("parakeet-fp32") == {
        "backend": "parakeet",
        "env": {"DICTEE_PARAKEET_QUANT": "fp32"},
    }


def test_whisper_medium():
    assert dt.asr_spec_to_daemon("whisper-medium") == {
        "backend": "whisper",
        "env": {"DICTEE_WHISPER_MODEL": "medium"},
    }


def test_whisper_tiny():
    assert dt.asr_spec_to_daemon("whisper-tiny")["env"]["DICTEE_WHISPER_MODEL"] == "tiny"


def test_whisper_small():
    assert dt.asr_spec_to_daemon("whisper-small")["env"]["DICTEE_WHISPER_MODEL"] == "small"


def test_default_returns_none():
    assert dt.asr_spec_to_daemon("") is None
    assert dt.asr_spec_to_daemon(None) is None
    assert dt.asr_spec_to_daemon("f9") is None


def test_unknown_raises():
    import pytest
    with pytest.raises(ValueError):
        dt.asr_spec_to_daemon("whisper-large")   # large intentionally excluded
