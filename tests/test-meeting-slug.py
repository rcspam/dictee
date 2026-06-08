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
