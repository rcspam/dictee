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

# ---------------------------------------------------------------------------
# Task 3.2 — Typist tests
# ---------------------------------------------------------------------------

def test_typist_sanitize_strips_unsupported():
    t = ds.Typist(dry_run=True)
    # String contains NBSP (U+00A0) and narrow NBSP (U+202F) alongside ASCII.
    out = t.sanitize("a b …—")  # NBSP, narrow NBSP, …, em-dash
    assert " " not in out and " " not in out
    assert "…" not in out and "—" not in out

def test_typist_tracks_typed_length_for_rewrite():
    t = ds.Typist(dry_run=True)
    t.type_text("Bonjour")
    assert t.typed_len == len("Bonjour")
    t.backspace(3)
    assert t.typed_len == len("Bonjour") - 3

def test_typist_control_chars_become_key_segments():
    t = ds.Typist(dry_run=True)
    cmds = t.build_commands(t.sanitize("a\nb\tc\x01d"))
    assert cmds == ["type a", "key enter", "type b", "key tab", "type c", "key ctrl+j", "type d"]

# ---------------------------------------------------------------------------
# Task 3.3 — StreamClient frame test
# ---------------------------------------------------------------------------

def test_frame_length_prefix_matches_rust():
    payload = b"\x01\x00\x02\x00"
    framed = ds.frame(payload)
    assert framed[:4] == (len(payload)).to_bytes(4, "big")
    assert framed[4:] == payload
    assert ds.frame(b"") == (0).to_bytes(4, "big")

# ---------------------------------------------------------------------------
# Fix B — Segmenter + _current_sentence_raw_len tests (write BEFORE fix)
# ---------------------------------------------------------------------------

def test_sentence_segmenter_multiple_terminators_in_one_fragment():
    seg = ds.Segmenter(granularity="sentence")
    assert seg.feed("Oui. Non. Et") == ["Oui.", "Non."]

def test_sentence_segmenter_ellipsis_terminator():
    seg = ds.Segmenter(granularity="sentence")
    assert seg.feed("Bon… alors") == ["Bon…"]

def test_current_sentence_raw_len_trailing_terminator():
    t = ds.Typist(dry_run=True)
    t.type_text("Bonjour. il fait beau.")
    # trailing '.' closes the sentence to rewrite: " il fait beau."
    assert ds._current_sentence_raw_len(t) == len(" il fait beau.")

def test_current_sentence_raw_len_no_terminator():
    t = ds.Typist(dry_run=True)
    t.type_text("il fait beau")
    assert ds._current_sentence_raw_len(t) == len("il fait beau")

def test_typist_backspace_more_than_typed():
    t = ds.Typist(dry_run=True)
    t.type_text("abc")
    t.backspace(10)
    assert t.typed == ""

def test_typist_sanitize_strips_batch_markers():
    t = ds.Typist(dry_run=True)
    assert t.sanitize("a\x02b\x03c\x04d") == "abcd"
