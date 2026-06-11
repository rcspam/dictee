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


def test_live_composer_freezes_on_trailing_newline():
    # "à la ligne" emits \n: the tail must freeze on it
    c = ds.LiveComposer(lambda t: t + "\n" if "ligne" in t else t)
    c.feed(" texte à la ligne")
    assert c.stable != ""


def test_rewrite_never_overrides_key_pacing():
    # zero-delay bursts proved unreliable (scrambled accents, dropped
    # backspaces): rewrites must never override dotool's default pacing
    t = ds.Typist(dry_run=True)
    t.type_text("Bonjour le monde entier")
    t.rewrite("Bonjour le monde contrôlé")
    assert "keydelay" not in t._last_cmds
    assert "typedelay" not in t._last_cmds
    assert t._last_cmds.count("key backspace") == len("entier")


def test_read_continuation_period_closed_class_word():
    # ".1:le" — previous push ended ". " after a closed-class word: the next
    # push erases the period (1 backspace) and continues lowercase
    pre, lead, lower = ds._parse_continuation_marker(".1:le", {"le", "la", "de"})
    assert (pre, lead, lower) == (1, " ", True)


def test_read_continuation_period_normal_word():
    pre, lead, lower = ds._parse_continuation_marker(".1:fonctionne", {"le"})
    assert (pre, lead, lower) == (0, " ", False)


def test_read_continuation_no_punct():
    pre, lead, lower = ds._parse_continuation_marker("_:pourquoi", set())
    assert (pre, lead, lower) == (0, " ", True)


def test_read_continuation_hourglass():
    # H2_ = indicator of 2 chars appended by the batch path: erase it
    pre, lead, lower = ds._parse_continuation_marker("H2_:le", set())
    assert (pre, lead, lower) == (2, " ", True)


def test_save_continuation_marker_format():
    assert ds._continuation_marker_for("Bonjour tout le monde.", "fr") == ".1:monde"
    assert ds._continuation_marker_for("on continue comme ça", "fr") == "_:ça"
    assert ds._continuation_marker_for("vraiment ?", "fr") == ".2:vraiment"
    assert ds._continuation_marker_for("c'est parles-tu.", "fr") == ".1:tu"
    assert ds._continuation_marker_for("avec un retour\nligne", "fr") is None


def test_live_composer_lead_and_continuation_init():
    c = ds.LiveComposer(lambda t: t[:1].upper() + t[1:] if t else t,
                        lead=" ", continuation=True)
    out = c.feed(" la suite")
    # cross-push continuation: leading space, first letter NOT capitalized
    assert out == " la suite"


def _kw():
    return ds._build_keyword_matchers("minuscule, miniscule")


def test_keyword_full_match_consumed():
    full, prefix = _kw()
    m = full.match("minuscule et la suite")
    assert m and m.end() == len("minuscule ")
    m2 = full.match("minuscules, et la suite")  # plural + comma tolerated
    assert m2


def test_keyword_prefix_hold():
    full, prefix = _kw()
    assert prefix("minus") is True       # could still become the keyword
    assert prefix("minuscule") is True   # complete but may grow (s, punct)
    assert prefix("minute") is False     # diverged
    assert prefix("bonjour") is False


def test_live_composer_keyword_forces_continuation():
    seen = []
    c = ds.LiveComposer(lambda t: t[:1].upper() + t[1:] if t else t,
                        lead=" ", keyword="minuscule",
                        on_keyword=lambda: seen.append(True))
    out1 = c.feed(" minus")          # possible keyword prefix: hold
    assert out1 == ""
    out2 = c.feed("cule et la suite")
    assert seen == [True]            # callback fired (marker backspaces)
    assert out2 == " et la suite"    # prefix consumed, lowercase, lead kept


def test_live_composer_keyword_divergence_types_normally():
    c = ds.LiveComposer(lambda t: t[:1].upper() + t[1:] if t else t,
                        keyword="minuscule")
    assert c.feed(" minu") == ""             # held
    out = c.feed("te de silence")            # diverged: "minute..."
    assert out == "Minute de silence"


def test_indicator_decision_closed_class():
    # ".1:le" -> erase 1 keystroke, type the indicator, marker H<len>_
    d = ds._indicator_decision(".1:le", {"le", "de"}, ">>")
    assert d == (1, ">>", "H2_:le")
    # normal word: no indicator
    assert ds._indicator_decision(".1:monde", {"le"}, ">>") is None
    # mid-sentence closed-class: indicator, nothing to erase
    assert ds._indicator_decision("_:le", {"le"}, ">>") == (0, ">>", "H2_:le")


def test_with_lead_of_preserves_cross_push_space():
    # the short-text fixup strips the leading separator space: the final
    # rewrite must put it back or the short push glues to the previous text
    assert ds._with_lead_of(" Une cuisine", "une cuisine") == " une cuisine"
    # no lead typed: nothing to preserve
    assert ds._with_lead_of("Une cuisine", "une cuisine") == "une cuisine"
    # new text already carries a lead: keep as-is
    assert ds._with_lead_of(" Une cuisine", " une cuisine") == " une cuisine"


def test_join_no_space_after_newline_tab_ctrlj():
    c = ds.LiveComposer(lambda t: t)
    c.stable = "Premier.\n"
    assert c._join(c.stable, "Deuxième") == "Premier.\nDeuxième"
    c.stable = "avant\x01"
    assert c._join(c.stable, "après") == "avant\x01après"
    c.stable = "colonne\t"
    assert c._join(c.stable, "valeur") == "colonne\tvaleur"


def test_no_freeze_on_period_after_closed_class_word():
    # "je vais le." must stay volatile: fix_continuation removes the spurious
    # period once the continuation arrives ("je vais le faire")
    def pp_fn(t):
        out = t[:1].upper() + t[1:]
        return out.replace("le. f", "le f")  # mimic fix_continuation
    c = ds.LiveComposer(pp_fn, closed_words={"le", "la", "de"})
    c.feed(" je vais le.")
    assert c.stable == ""          # NOT frozen (closed-class before period)
    out = c.feed(" faire demain")
    assert out == "Je vais le faire demain"
    # but a normal word before the period freezes as usual
    c2 = ds.LiveComposer(pp_fn, closed_words={"le"})
    c2.feed(" je vais souvent.")
    assert c2.stable != ""


def test_casing_preserves_acronyms_after_pause():
    c = ds.LiveComposer(lambda t: t)
    c.open_continuation = True
    assert c._casing("API de ce site") == "API de ce site"  # sigle intact
    assert c._casing("Bonjour") == "bonjour"


def test_join_no_space_after_reset_marker():
    c = ds.LiveComposer(lambda t: t)
    assert c._join("\x04", "on repart") == "\x04on repart"


def test_join_french_typography_before_high_punctuation():
    c = ds.LiveComposer(lambda t: t, fr_typography=True)
    assert c._join("magnifique", "!") == "magnifique !"
    assert c._join("vraiment", "?") == "vraiment ?"
    assert c._join("la liste", ":") == "la liste :"
    # sans le flag : collage simple (comportement antérieur)
    c2 = ds.LiveComposer(lambda t: t)
    assert c2._join("magnifique", "!") == "magnifique!"
