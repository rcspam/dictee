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
        "env": {"DICTEE_PARAKEET_QUANT": "fp32", "DICTEE_FORCE_CPU": "0"},
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


def test_chunked_env_override():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    w = dt._ChunkedPipelineWorker("/tmp/x.wav", 0.5, diarize=True,
                                   env_override={"DICTEE_PARAKEET_QUANT": "int8",
                                                 "DICTEE_FORCE_CPU": "1"})
    assert w._subprocess_env["DICTEE_PARAKEET_QUANT"] == "int8"
    assert w._subprocess_env["DICTEE_FORCE_CPU"] == "1"
    # No override → conf-derived/default behavior, key may be absent or conf value
    w2 = dt._ChunkedPipelineWorker("/tmp/x.wav", 0.5, diarize=True)
    assert getattr(w2, "_subprocess_env", None) is not None
