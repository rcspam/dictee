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

def test_live_composer_mid_block_terminator_stays_volatile():
    c = ds.LiveComposer(_pp_cap)
    out = c.feed(" oui. non. et")
    # internal terminators do not freeze (raw<->pp mapping is unknowable);
    # the block stays volatile until a clean end or a pause
    assert c.stable == ""
    assert out == "Oui. non. et"

def test_typist_backspace_more_than_typed():
    t = ds.Typist(dry_run=True)
    t.type_text("abc")
    t.backspace(10)
    assert t.typed == ""

def test_typist_sanitize_strips_batch_markers():
    t = ds.Typist(dry_run=True)
    assert t.sanitize("a\x02b\x03c\x04d") == "abcd"


def test_rewrite_keeps_common_prefix():
    t = ds.Typist(dry_run=True)
    t.type_text("Bonjour le monde entier")
    t.rewrite("Bonjour le monde corrigé")
    assert t.typed == "Bonjour le monde corrigé"
    # only the differing tail is erased: "entier" -> 6 backspaces
    assert t._last_cmds.count("key backspace") == len("entier")
    # the burst is bracketed by zero-delay then default-delay restore
    assert "keydelay 0" in t._last_cmds and "keydelay 2" in t._last_cmds


def test_rewrite_noop_when_identical():
    t = ds.Typist(dry_run=True)
    t.type_text("Texte.")
    t._last_cmds = None
    t.rewrite("Texte.")
    assert t._last_cmds is None
    assert t.typed == "Texte."


def _pp_cap(t):
    """Test PP: capitalize first letter (stands in for run_pipeline local)."""
    return t[:1].upper() + t[1:] if t else t


def test_live_composer_volatile_tail_renders_partial():
    c = ds.LiveComposer(_pp_cap)
    assert c.feed(" bonjour le") == "Bonjour le"
    assert c.feed(" monde") == "Bonjour le monde"


def test_live_composer_freezes_on_clean_sentence_end():
    c = ds.LiveComposer(_pp_cap)
    c.feed(" bonjour le monde")
    assert c.stable == ""
    out = c.feed(".")
    # the PP'd tail ends with a terminator -> the whole tail freezes
    assert out == "Bonjour le monde."
    assert c.stable == "Bonjour le monde."


def test_live_composer_voice_command_punctuation_no_space():
    # PP mock: the voice command "point final" becomes "." (rules.conf:89)
    c = ds.LiveComposer(lambda t: "." if t == "point final" else t)
    c.feed(" ceci est la fin")
    c.promote()  # pause froze the tail mid-sentence
    out = c.feed(" point final")
    # no space between the last word and the dot; sentence freezes
    assert out == "ceci est la fin."
    assert c.stable == "ceci est la fin."
    assert c.open_continuation is False


def test_live_composer_marker_bytes_dont_block_freeze():
    # rules emit ".\x02 " (end-of-sentence marker): freeze must still fire
    c = ds.LiveComposer(lambda t: "la fin.\x02 " if "point" in t else t)
    out = c.feed(" la fin point finale")
    assert c.stable != ""


def test_live_composer_pause_promotion_continues_sentence():
    c = ds.LiveComposer(_pp_cap)
    c.feed(" il fait")
    c.promote()  # pause boundary: freeze tail, sentence stays open
    out = c.feed(" beau aujourd'hui.")
    # the continuation is NOT re-capitalized
    assert out == "Il fait beau aujourd'hui."
    assert c.stable == "Il fait beau aujourd'hui."


def test_live_composer_target_stable_only_when_no_tail():
    c = ds.LiveComposer(_pp_cap)
    c.feed(" une phrase.")
    assert c.target() == "Une phrase."
    assert c.feed("") == "Une phrase."


def test_live_composer_no_double_space_after_rule_trailing_space():
    # rules emit ". " (trailing space): joining the next sentence must not
    # produce a double space
    c = ds.LiveComposer(lambda t: "la fin.\x02 " if "point" in t else t)
    c.feed(" la fin point finale")
    out = c.feed(" et ensuite")
    assert "  " not in out.replace("\x02", "")
