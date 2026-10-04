import importlib.machinery

ml = importlib.machinery.SourceFileLoader(
    "ml", str(__import__("pathlib").Path(__file__).resolve().parent.parent / "dictee-meeting-live")
).load_module()


def test_slug():
    assert ml.slug_title("Réunion équipe !") == "r-union-quipe"
    assert ml.slug_title("  A  B  ") == "a-b"
    assert ml.slug_title("") == ""


def test_default_meeting_asr():
    # the F9 engine when the meeting offers it
    for backend in ("whisper-rust", "canary", "nemotron", "kyutai"):
        assert ml.default_meeting_asr({"DICTEE_ASR_BACKEND": backend}) == backend
    # Parakeet and faster-whisper left meetings: Whisper-Rust instead
    assert ml.default_meeting_asr({"DICTEE_ASR_BACKEND": "parakeet"}) == "whisper-rust"
    assert ml.default_meeting_asr({"DICTEE_ASR_BACKEND": "whisper"}) == "whisper-rust"
    assert ml.default_meeting_asr({}) == "whisper-rust"


def test_live_asr_daemon_recipes(monkeypatch, tmp_path):
    monkeypatch.setattr(ml.shutil, "which", lambda name: f"/usr/bin/{name}")
    ggml = tmp_path / "ggml-large-v3-q5_0.bin"
    ggml.write_bytes(b"")
    conf = {"DICTEE_WHISPER_RUST_GGML": str(ggml)}
    cmd, env = ml.live_asr_daemon("whisper-rust", conf, "/tmp/s.sock")
    assert cmd == ["transcribe-daemon-whisper-rust", "--socket", "/tmp/s.sock"]
    # the whisper branch of the daemon, whatever the F9 backend in the conf
    assert env["DICTEE_ASR_BACKEND"] == "whisper"
    assert env["DICTEE_WHISPER_RUST_GGML"] == str(ggml)
    assert env["DICTEE_DAEMON_NO_PROVIDER"] == "1"
    cmd, env = ml.live_asr_daemon("nemotron", conf, "/tmp/s.sock")
    assert cmd == ["transcribe-daemon", "--socket", "/tmp/s.sock"]
    assert env["DICTEE_ASR_BACKEND"] == "nemotron"
    cmd, env = ml.live_asr_daemon("kyutai", conf, "/tmp/s.sock")
    assert cmd == ["transcribe-daemon-kyutai", "--socket", "/tmp/s.sock"]
    monkeypatch.setattr(ml, "_canary_installed", lambda: True)
    cmd, env = ml.live_asr_daemon("canary", conf, "/tmp/s.sock")
    assert cmd == ["transcribe-daemon", "--canary", "--socket", "/tmp/s.sock"]
    assert env["DICTEE_ASR_BACKEND"] == "canary"


def test_live_asr_daemon_says_what_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ml, "_data_dirs", lambda name: (str(tmp_path / name),))
    monkeypatch.setattr(ml.shutil, "which", lambda name: None)
    cmd, why = ml.live_asr_daemon("whisper-rust", {}, "/tmp/s.sock")
    assert cmd is None and "Whisper-Rust" in why
    cmd, why = ml.live_asr_daemon("canary", {}, "/tmp/s.sock")
    assert cmd is None and "Canary" in why
    cmd, why = ml.live_asr_daemon("nemotron", {}, "/tmp/s.sock")
    assert cmd is None and "transcribe-daemon" in why
    cmd, why = ml.live_asr_daemon("parakeet-fp32", {}, "/tmp/s.sock")
    assert cmd is None
    # a model of the configured size, found without the conf's path
    (tmp_path / "whisper-rust").mkdir()
    (tmp_path / "whisper-rust" / "ggml-large-v3-turbo.bin").write_bytes(b"")
    monkeypatch.setattr(ml.shutil, "which", lambda name: f"/usr/bin/{name}")
    cmd, env = ml.live_asr_daemon(
        "whisper-rust", {"DICTEE_WHISPER_RUST_MODEL": "large-v3-turbo"}, "/tmp/s.sock")
    assert env["DICTEE_WHISPER_RUST_GGML"].endswith("ggml-large-v3-turbo.bin")
