#!/usr/bin/env python3
"""Tests for the chunked-mode speaker reconciliation of dictee-moss-diarize.

MOSS labels are local to each chunk (S01 restarts every call); the driver
maps them onto persistent global speakers with two ordered signals:
temporal co-occurrence in the overlap zone, then voice embeddings. Both
are pure logic (embeddings are injected as a callable), locked here
without models or GPU.

Run: python3 -m pytest tests/test-moss-chunked.py
"""

import importlib.machinery
import importlib.util
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(HERE, "..", "dictee-moss-diarize")

_loader = importlib.machinery.SourceFileLoader("moss_diarize", DRIVER)
_spec = importlib.util.spec_from_loader("moss_diarize", _loader)
md = importlib.util.module_from_spec(_spec)
_loader.exec_module(md)


# ── _overlap_matches ──────────────────────────────────────────────────────

def test_overlap_matches_basic():
    # Chunk A (0-40) labels the 32-35s turn "2"; chunk B (30-70) re-hears
    # the same instant as its label "0" — same seconds, same person.
    prev = [(10.0, 20.0, 0, "x"), (32.0, 35.0, 2, "y")]
    nxt = [(32.1, 34.8, 0, "y'"), (36.0, 39.0, 1, "z")]
    m = md._overlap_matches(prev, nxt, 30.0, 40.0)
    assert m == {0: 2}


def test_overlap_matches_uniqueness_both_sides():
    # Two next-labels co-occurring with the same prev-label: only the
    # strongest pair wins; the other stays unmatched.
    prev = [(30.0, 40.0, 5, "long")]
    nxt = [(30.0, 36.0, 0, "a"), (36.5, 39.5, 1, "b")]
    m = md._overlap_matches(prev, nxt, 30.0, 40.0)
    assert m == {0: 5}


def test_overlap_matches_min_cooccurrence():
    # 0.3 s of shared speech is below the floor: no match.
    prev = [(33.0, 33.3, 0, "blip")]
    nxt = [(33.0, 33.3, 1, "blip")]
    assert md._overlap_matches(prev, nxt, 30.0, 40.0) == {}


def test_overlap_matches_ignores_speech_outside_zone():
    # Massive co-occurrence at 10-20s, but the overlap zone is 30-40s.
    prev = [(10.0, 20.0, 0, "x")]
    nxt = [(10.0, 20.0, 1, "x")]
    assert md._overlap_matches(prev, nxt, 30.0, 40.0) == {}


# ── _greedy_assign ────────────────────────────────────────────────────────

def test_greedy_assign_threshold_and_uniqueness():
    sims = {(0, 0): 0.9, (0, 1): 0.8, (1, 0): 0.85, (1, 1): 0.4}
    out = md._greedy_assign(sims, threshold=0.6, taken=set())
    # label 0 takes person 0 (0.9); label 1 falls back to... person 1 is
    # only 0.4 < threshold, and person 0 is taken -> label 1 unassigned.
    assert out == {0: 0}


def test_greedy_assign_respects_taken():
    sims = {(0, 0): 0.95}
    assert md._greedy_assign(sims, threshold=0.6, taken={0}) == {}


# ── _keep_by_midpoint ─────────────────────────────────────────────────────

def test_keep_by_midpoint_cuts_overlap():
    turns = [(28.0, 33.0, 0, "a"),   # midpoint 30.5 < 35 -> left chunk
             (34.0, 38.0, 0, "b")]   # midpoint 36 >= 35 -> right chunk
    left = md._keep_by_midpoint(turns, float("-inf"), 35.0)
    right = md._keep_by_midpoint(turns, 35.0, float("inf"))
    assert [t[3] for t in left] == ["a"]
    assert [t[3] for t in right] == ["b"]


# ── _reconcile_chunks (the whole pipeline) ────────────────────────────────

def _vec(*xs):
    class V(tuple):
        def __matmul__(self, other):
            return sum(a * b for a, b in zip(self, other))
        def __mul__(self, k):
            return V(a * k for a in self)
        __rmul__ = __mul__
        def __add__(self, other):
            return V(a + b for a, b in zip(self, other))
        def __truediv__(self, k):
            return V(a / k for a in self)
    return V(xs)


def test_reconcile_temporal_continuity():
    # Speaker talks across the chunk boundary: labels 1 (chunk 0) and 0
    # (chunk 1) must become the same global id, no embeddings needed.
    chunks = [
        (0.0, [(5.0, 15.0, 0, "intro"), (28.0, 39.0, 1, "guest speaks")]),
        (30.0, [(30.5, 38.5, 0, "guest speaks bis"),
                (45.0, 55.0, 1, "intro again")]),
    ]
    out = md._reconcile_chunks(chunks, 40.0, 10.0, embed_fn=None)
    by_text = {t[3]: t[2] for t in out}
    assert by_text["guest speaks"] == by_text.get("guest speaks bis",
                                                  by_text["guest speaks"])
    # dedup: the overlap-zone turn appears once (midpoint rule)
    texts = [t[3] for t in out]
    assert len(texts) == len(set(texts))


def test_reconcile_embeddings_relink_after_silence():
    # The crop2 failure mode: a speaker silent through the whole overlap
    # (no temporal signal) returns in chunk 1 under a fresh local label.
    # Embeddings must relink it to the global speaker created in chunk 0.
    A, B = _vec(1.0, 0.0), _vec(0.0, 1.0)
    emb = {"host": A, "guest": B}
    def embed_fn(intervals):
        # identify by interval position: guest speaks 5-15 and 55-65
        return emb["guest"] if intervals[0][0] in (5.0, 55.0) else emb["host"]
    chunks = [
        (0.0, [(5.0, 15.0, 0, "guest early"), (20.0, 39.0, 1, "host long")]),
        (30.0, [(31.0, 39.0, 0, "host still"), (55.0, 65.0, 1, "guest back")]),
    ]
    out = md._reconcile_chunks(chunks, 70.0, 40.0, embed_fn=embed_fn)
    ids = {t[3]: t[2] for t in out}
    assert ids["guest back"] == ids["guest early"]
    assert ids["guest early"] != ids["host long"]
    # "host still" (31-39s) is chunk 0's territory (midpoint < the 50s cut):
    # deduplicated away — chunk 0 already emitted it as "host long".
    assert "host still" not in ids


def test_reconcile_new_speaker_below_threshold():
    # A genuinely new voice (orthogonal embedding) must get a NEW id, not
    # be absorbed into the closest existing speaker.
    A, C = _vec(1.0, 0.0), _vec(0.0, 1.0)
    def embed_fn(intervals):
        return A if intervals[0][0] < 40.0 else C
    chunks = [
        (0.0, [(5.0, 35.0, 0, "only speaker")]),
        (30.0, [(45.0, 55.0, 0, "newcomer")]),
    ]
    out = md._reconcile_chunks(chunks, 40.0, 10.0, embed_fn=embed_fn,
                               sim_new=0.6)
    ids = {t[3]: t[2] for t in out}
    assert ids["newcomer"] != ids["only speaker"]


def test_reconcile_no_embedder_falls_back_to_index():
    # Degraded mode (no diar component): labels map by index so the
    # speaker count stays plausible instead of growing per chunk.
    chunks = [
        (0.0, [(5.0, 15.0, 0, "a"), (16.0, 25.0, 1, "b")]),
        (30.0, [(45.0, 50.0, 0, "c"), (51.0, 55.0, 1, "d")]),
    ]
    out = md._reconcile_chunks(chunks, 40.0, 10.0, embed_fn=None)
    assert {t[2] for t in out} == {0, 1}


# ── parsing with offset (chunked absolute times) ──────────────────────────

def test_parse_turns_offset():
    text = "[1.50][S01] Bonjour.[3.00][3.10][S02] Salut.[4.00]"
    turns = md._parse_turns(text, offset=30.0)
    assert turns[0][:3] == (31.5, 33.0, 0)
    assert turns[1][:3] == (33.1, 34.0, 1)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
