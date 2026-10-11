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


def test_analysis_opens_the_live_preview_when_it_covers_the_meeting(tmp_path):
    audio = tmp_path / "audio.wav"
    preview = tmp_path / "transcript-live.md"
    preview.write_text("# Réunion\n\n[0.500s - 3.200s] Speaker 0: Bonjour.\n",
                       encoding="utf-8")
    # with the meeting's threshold, for an analysis the user runs again there
    assert ml.analysis_command(audio, preview, "nemotron3", "whisper-rust", True, 70) == [
        "dictee-transcribe", "--file", str(audio), "--transcript", str(preview),
        "--asr-model", "whisper-rust", "--sensitivity", "70"]


def test_analysis_runs_again_for_moss_or_a_preview_with_holes(tmp_path):
    audio = tmp_path / "audio.wav"
    preview = tmp_path / "transcript-live.md"
    preview.write_text("[0.500s - 3.200s] Speaker 0: Bonjour.\n", encoding="utf-8")
    empty = tmp_path / "empty.md"
    empty.write_text("# Réunion\n\n", encoding="utf-8")
    for transcript, engine, whole in ((preview, "moss", True),
                                      (preview, "nemotron3", False),
                                      (empty, "nemotron3", True),
                                      (tmp_path / "missing.md", "nemotron3", True)):
        assert ml.analysis_command(audio, transcript, engine, "canary", whole, 35) == [
            "dictee-transcribe", "--file", str(audio), "--diarize",
            "--diar-engine", engine, "--asr-model", "canary",
            "--sensitivity", "35"], (transcript, engine, whole)


def test_analysis_runs_again_for_nemotron_3_5(tmp_path):
    # its preview goes piece by piece, its analysis transcribes the whole file
    audio = tmp_path / "audio.wav"
    preview = tmp_path / "transcript-live.md"
    preview.write_text("[0.500s - 3.200s] Speaker 0: Bonjour.\n", encoding="utf-8")
    assert ml.analysis_command(audio, preview, "nemotron3", "nemotron", True, 50) == [
        "dictee-transcribe", "--file", str(audio), "--diarize",
        "--diar-engine", "nemotron3", "--asr-model", "nemotron", "--sensitivity", "50"]


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



def _window(value, preview_value, whole=True):
    """What MeetingWindow._preview_holds_meeting reads: the threshold slider,
    the value the live preview started with, and whether it got every turn."""
    from types import SimpleNamespace
    return SimpleNamespace(_diar_slider=SimpleNamespace(value=lambda: value),
                           _live_sensitivity=preview_value, _live_whole=whole)


def test_the_preview_is_the_result_when_the_threshold_did_not_move():
    assert ml.MeetingWindow._preview_holds_meeting(_window(50, 50)) is True
    assert ml.MeetingWindow._preview_holds_meeting(_window(50, 50, whole=False)) is False


def test_a_threshold_moved_after_the_start_has_the_meeting_analysed_again():
    # the preview kept its starting threshold: the slider's is another result
    assert ml.MeetingWindow._preview_holds_meeting(_window(70, 50)) is False


class _Widget:
    def __init__(self):
        self.enabled, self.tip = True, ""

    def setEnabled(self, on):
        self.enabled = on

    def setToolTip(self, tip):
        self.tip = tip


def _threshold_row(engine):
    from types import SimpleNamespace
    return SimpleNamespace(_diar_combo=SimpleNamespace(currentData=lambda: engine),
                           _diar_slider=_Widget(), _diar_slider_val=_Widget())


def test_the_threshold_is_greyed_with_moss_which_has_none():
    win = _threshold_row("moss")
    ml.MeetingWindow._sync_diar_slider(win)
    assert not win._diar_slider.enabled and not win._diar_slider_val.enabled
    assert "MOSS" in win._diar_slider.tip


def test_the_threshold_is_live_with_nemotron_3():
    win = _threshold_row("nemotron3")
    win._diar_slider.enabled = False      # MOSS was chosen before
    ml.MeetingWindow._sync_diar_slider(win)
    assert win._diar_slider.enabled and win._diar_slider_val.enabled
    assert "MOSS" not in win._diar_slider.tip


def test_only_a_meeting_folder_right_under_the_meetings_root_may_be_deleted(tmp_path, monkeypatch):
    root = tmp_path / "meetings"
    monkeypatch.setenv("DICTEE_MEETING_DIR", str(root))
    meeting = ml.meeting_dir(title="essai")
    assert ml.deletable_meeting_dir(meeting) == meeting.resolve()
    assert ml.deletable_meeting_dir(None) is None
    assert ml.deletable_meeting_dir(root) is None
    nested = meeting / "sous-dossier"
    nested.mkdir()
    assert ml.deletable_meeting_dir(nested) is None
    elsewhere = tmp_path / "ailleurs"
    elsewhere.mkdir()
    assert ml.deletable_meeting_dir(elsewhere) is None
    assert ml.deletable_meeting_dir(root / ".." / "ailleurs") is None
    (root / "lien").symlink_to(elsewhere)
    assert ml.deletable_meeting_dir(root / "lien") is None
    assert ml.deletable_meeting_dir(root / "absent") is None

