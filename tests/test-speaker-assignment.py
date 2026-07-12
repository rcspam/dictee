#!/usr/bin/env python3
"""_assign_speakers: sequence-aware word->speaker fusion.

Regression test for the mid-clause speaker-flip bug: diarization engines
emit spurious overlapping islands and shifted boundaries in fast exchanges
(verified on community-1, Sortformer AND diarizen — the defect is
engine-agnostic), and the previous per-word nearest-segment rule faithfully
copied them onto the words. The fixture geometry below (word timings and
segment boundaries) is taken verbatim from a real 5-min interview run
(diarize-multi --threshold 0.60 + whisper large-v3 word tokens); word texts
are anonymized, punctuation kept (it is functional: clause boundaries).

Run: python3 tests/test-speaker-assignment.py
"""
import os

SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "dictee-transcribe.py",
)


def _load_func(name, source_path=SCRIPT):
    """Extract a top-level def by name and exec it into a fresh ns
    (same pattern as test-transcribe-routing.py: no PyQt6 import)."""
    with open(source_path, encoding="utf-8") as f:
        lines = f.readlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"def {name}("):
            start = i
            break
    if start is None:
        raise RuntimeError(f"Function {name}() not found in {source_path}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("def ") or lines[j].startswith("class "):
            end = j
            break
    src = "".join(lines[start:end])
    ns = {}
    exec(src, ns)
    return ns[name]


_assign_speakers = _load_func("_assign_speakers")


def W(start, end, text="w"):
    return {"start": start, "end": end, "text": text}


def S(start, end, speaker):
    return {"start": start, "end": end, "speaker": speaker}


# ---------------------------------------------------------------------------
# Test 1: real-geometry regression — spurious island + early boundary.
# Segments (real diarize-multi output): speaker 1 talks continuously
# 25.80-38.8; a spurious 1.48 s speaker-2 island (35.03-36.51) OVERLAPS the
# first speaker-1 segment and captures two mid-clause words; the next
# speaker-2 segment starts 0.5 s early (38.07 vs the real turn at 38.84)
# and captures the clause tail "en France.".
# Expected: the whole first clause stays speaker 1; the true answer
# ("Oui, ..." — zero-pause turn at a clause boundary) stays speaker 2;
# the clause "Ça a beaucoup changé." straddling the 41.56 boundary is not
# split mid-clause.
# ---------------------------------------------------------------------------
segments = [
    S(25.80, 35.84, 1),
    S(35.03, 36.51, 2),   # spurious island (overlaps previous)
    S(36.51, 38.07, 1),
    S(38.07, 41.56, 2),   # real segment, boundary ~0.5 s early
    S(41.56, 45.42, 1),
]
words = [
    W(34.38, 34.66), W(34.66, 34.87), W(34.87, 34.99), W(35.09, 35.70, "w."),
    W(35.70, 35.76),
    W(35.84, 36.26),                  # "passes" — captured by the island
    W(36.26, 36.34),                  # "de"     — captured by the island
    W(36.41, 36.75), W(36.75, 36.89), W(36.89, 37.24), W(37.24, 37.52),
    W(37.60, 37.73), W(37.73, 37.78),
    W(38.20, 38.22),                  # "en"     — captured by early boundary
    W(38.24, 38.84, "w."),            # "France." (0.42 s pause before "en",
                                      #  clause end here)
    W(38.84, 39.18, "w,"),            # "Oui," — REAL turn, zero pause
    W(39.18, 39.59, "w,"), W(39.59, 39.92), W(40.02, 40.35, "w,"),
    W(40.35, 40.49), W(40.49, 40.76), W(40.86, 41.36, "w."),
    W(41.44, 41.60),                  # "Ça" — clause straddles 41.56 boundary
    W(41.60, 41.67), W(41.67, 41.98), W(42.30, 42.91, "w."),
]
out = _assign_speakers(words, segments)
assert out[:15] == [1] * 15, f"Test 1 FAIL (first clause): {out[:15]}"
assert out[15:22] == [2] * 7, f"Test 1 FAIL (true answer lost): {out[15:22]}"
assert out[22:26] == [1] * 4, f"Test 1 FAIL (clause split at boundary): {out[22:26]}"
print("PASS: test 1 — island + early boundary absorbed, true zero-pause turn kept")

# ---------------------------------------------------------------------------
# Test 2: a genuine turn with strong segment support switches even
# mid-clause (no punctuation, no pause): the switch cost is paid once and
# the growing per-word distances make staying on the old speaker costlier.
# ---------------------------------------------------------------------------
segments = [S(0.0, 2.0, 0), S(2.0, 10.0, 1)]
words = [W(0.5, 1.0), W(1.2, 1.8),
         W(2.5, 3.0), W(3.2, 4.0), W(4.2, 5.0), W(5.2, 6.0)]
out = _assign_speakers(words, segments)
assert out[:2] == [0, 0], f"Test 2 FAIL: {out}"
assert out[-2:] == [1, 1], f"Test 2 FAIL (real turn glued): {out}"
print("PASS: test 2 — genuine mid-clause turn still switches")

# ---------------------------------------------------------------------------
# Test 3: a long silence (>= free_gap) is a free boundary even without
# punctuation: the isolated word after the gap follows its own segment.
# ---------------------------------------------------------------------------
segments = [S(0.0, 1.0, 0), S(5.0, 6.0, 1)]
words = [W(0.2, 0.9), W(5.2, 5.9)]
out = _assign_speakers(words, segments)
assert out == [0, 1], f"Test 3 FAIL: {out}"
print("PASS: test 3 — long silence is a free boundary")

# ---------------------------------------------------------------------------
# Test 4: single speaker, words drifting into gaps — every word still gets
# the (only) speaker, never UNKNOWN (same guarantee as nearest-segment).
# ---------------------------------------------------------------------------
segments = [S(1.0, 2.0, 3), S(4.0, 5.0, 3)]
words = [W(0.0, 0.5), W(2.5, 3.5), W(5.5, 6.0)]
out = _assign_speakers(words, segments)
assert out == [3, 3, 3], f"Test 4 FAIL: {out}"
print("PASS: test 4 — no UNKNOWN when segments exist")

# ---------------------------------------------------------------------------
# Test 5: degenerate inputs.
# ---------------------------------------------------------------------------
assert _assign_speakers([], [S(0, 1, 0)]) == []
assert _assign_speakers([W(0, 1)], []) == [-1]
print("PASS: test 5 — degenerate inputs")

# ---------------------------------------------------------------------------
# Test 6: a real short answer forming its own clause, backed by its own
# segment, is preserved (guard against any future "absorb enclosed
# segments" attempt: the mirrored-configuration trap, see the NOTE in
# _assign_speakers and project memory 2026-07-09/12).
# ---------------------------------------------------------------------------
segments = [S(0.0, 2.0, 1), S(2.05, 2.95, 2), S(3.0, 5.0, 1)]
words = [
    W(0.3, 0.9), W(1.0, 1.9, "w."),        # speaker-1 clause
    W(2.1, 2.4), W(2.5, 2.9, "w."),        # short answer = its own clause
    W(3.2, 3.8), W(3.9, 4.8, "w."),        # speaker-1 again
]
out = _assign_speakers(words, segments)
assert out == [1, 1, 2, 2, 1, 1], f"Test 6 FAIL: {out}"
print("PASS: test 6 — real short answer segment kept")

print("\nALL TESTS PASS")
