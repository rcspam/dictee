import importlib.machinery

ml = importlib.machinery.SourceFileLoader(
    "ml", str(__import__("pathlib").Path(__file__).resolve().parent.parent / "dictee-meeting-live")
).load_module()


def test_slug():
    assert ml.slug_title("Réunion équipe !") == "r-union-quipe"
    assert ml.slug_title("  A  B  ") == "a-b"
    assert ml.slug_title("") == ""
