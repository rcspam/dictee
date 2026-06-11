"""Tests for the streaming Segmenter (sentence/word boundary detection)."""
import importlib.util, importlib.machinery, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
# dictee-stream has no .py extension; SourceFileLoader lets us load it anyway.
_loader = importlib.machinery.SourceFileLoader("dictee_stream",
                                               str(ROOT / "dictee-stream"))
spec = importlib.util.spec_from_loader("dictee_stream", _loader)
ds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds)

def test_word_segmenter_emits_complete_words():
    seg = ds.Segmenter(granularity="word")
    # SentencePiece-style fragments already carry leading spaces.
    assert seg.feed(" Bon") == []          # incomplete trailing word, hold
    assert seg.feed("jour le") == ["Bonjour"]  # "Bonjour" complete, "le" pending
    assert seg.feed(" monde") == ["le"]

def test_sentence_segmenter_emits_on_terminal_punct():
    seg = ds.Segmenter(granularity="sentence")
    assert seg.feed("Bonjour le monde") == []
    assert seg.feed(". Et la suite") == ["Bonjour le monde."]

def test_flush_returns_remainder():
    seg = ds.Segmenter(granularity="sentence")
    seg.feed("texte sans ponctuation")
    assert seg.flush() == ["texte sans ponctuation"]
