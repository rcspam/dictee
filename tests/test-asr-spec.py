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


def test_whisper_rust_turbo():
    assert dt.asr_spec_to_daemon("whisper-rust-large-v3-turbo") == {
        "backend": "whisper-rust",
        "env": {"DICTEE_WHISPER_RUST_MODEL": "large-v3-turbo"},
    }


def test_whisper_rust_small():
    assert dt.asr_spec_to_daemon("whisper-rust-small")["backend"] == "whisper-rust"


def test_unknown_raises():
    import pytest
    with pytest.raises(ValueError):
        dt.asr_spec_to_daemon("whisper-large")   # large intentionally excluded
    with pytest.raises(ValueError):
        dt.asr_spec_to_daemon("whisper-rust-large")  # not a shipped GGML size


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


def test_isolated_daemon_whisper_cmd_env():
    d = dt.IsolatedAsrDaemon({"backend": "whisper", "env": {"DICTEE_WHISPER_MODEL": "medium"}})
    cmd, env = d._build_cmd_env()
    assert cmd == ["transcribe-daemon-whisper"]
    assert env["DICTEE_WHISPER_MODEL"] == "medium"
    assert env["DICTEE_TRANSCRIBE_SOCKET"] == d.sock
    assert env["DICTEE_DAEMON_NO_PROVIDER"] == "1"


def test_isolated_daemon_parakeet_cmd_env():
    d = dt.IsolatedAsrDaemon({"backend": "parakeet", "env": {"DICTEE_PARAKEET_QUANT": "int8", "DICTEE_FORCE_CPU": "1"}})
    cmd, env = d._build_cmd_env()
    assert cmd[0] == "transcribe-daemon" and "--socket" in cmd
    assert env["DICTEE_PARAKEET_QUANT"] == "int8"
    assert env["DICTEE_DAEMON_NO_PROVIDER"] == "1"


def test_list_past_meetings(tmp_path):
    import json, os
    m = tmp_path / "2026-06-08-1430_reunion"
    (m).mkdir(parents=True)
    (m / "audio.wav").write_bytes(b"\x00" * 100)
    (m / "meeting.meta.json").write_text(json.dumps({"title": "Réunion équipe"}))
    res = dt.list_past_meetings(str(tmp_path))
    assert res == [("2026-06-08-1430_reunion — Réunion équipe",
                    str(m / "audio.wav"))]
