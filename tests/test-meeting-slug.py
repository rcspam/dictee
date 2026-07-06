import importlib.machinery

ml = importlib.machinery.SourceFileLoader(
    "ml", str(__import__("pathlib").Path(__file__).resolve().parent.parent / "dictee-meeting-live")
).load_module()


def test_slug():
    assert ml.slug_title("Réunion équipe !") == "r-union-quipe"
    assert ml.slug_title("  A  B  ") == "a-b"
    assert ml.slug_title("") == ""


def test_current_f9_spec():
    assert ml.current_f9_spec({"DICTEE_ASR_BACKEND": "whisper", "DICTEE_WHISPER_MODEL": "medium"}) == "whisper-medium"
    assert ml.current_f9_spec({"DICTEE_ASR_BACKEND": "parakeet", "DICTEE_PARAKEET_QUANT": "int8"}) == "parakeet-int8"
    assert ml.current_f9_spec({}) == "parakeet-fp32"
    assert ml.current_f9_spec({"DICTEE_ASR_BACKEND": "whisper"}) == "whisper-small"
    assert ml.current_f9_spec({"DICTEE_ASR_BACKEND": "canary"}) == "parakeet-fp32"


def test_parse_whisper_tokens():
    text = "[0.00s - 0.50s] Bonjour\n[0.50s - 1.20s] le\n[1.20s - 2.00s] monde\n"
    assert ml._parse_whisper_tokens(text) == [
        {"text": "Bonjour", "start_s": 0.0, "end_s": 0.5},
        {"text": "le", "start_s": 0.5, "end_s": 1.2},
        {"text": "monde", "start_s": 1.2, "end_s": 2.0},
    ]
    # sentence-level lines (no 's' suffix variations) and blanks/garbage are robust
    assert ml._parse_whisper_tokens("[1 - 2] hi") == [{"text": "hi", "start_s": 1.0, "end_s": 2.0}]
    assert ml._parse_whisper_tokens("") == []
    assert ml._parse_whisper_tokens("garbage no brackets") == []
