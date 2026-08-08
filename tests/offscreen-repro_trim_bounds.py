"""Trim bounds before transcription: start/end offsets set on the loaded file.

Measured 2026-08-04 on a 92-min podcast: the 1 min 49 s of jingle and ads at
the head makes the diarizer report SIX speakers in the window that contains it
(three real voices), against THREE for the same window without it. Those ghost
labels then enter the cross-window reconciliation. Cutting the head is the
cheap fix, and it also lets one transcribe an excerpt of a long file.

The user-facing contract this locks:
  - HH:MM:SS (or M:SS) parsing/formatting, matching the player's own clock;
  - the ffmpeg cut is built ONCE, before any engine runs;
  - timestamps are rebased onto the ORIGINAL file, so the transcript, the SRT
    export and the player all keep speaking the user's timeline. Without this
    a bound set at 1:49 would produce a transcript starting at 0:00.

Run: python3 tests/offscreen-repro_trim_bounds.py
"""
import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

spec = importlib.util.spec_from_file_location(
    "dictee_transcribe", "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-transcribe.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

# ── time parsing: accept what the player displays, and plain seconds ──
cases = [
    ("1:49", 109.0),
    ("01:49", 109.0),
    ("1:23:45", 5025.0),
    ("0:00", 0.0),
    ("109", 109.0),
    ("", None),
    ("   ", None),
    ("abc", None),
    ("1:60", None),        # 60 s is not a valid seconds field
    ("-5", None),
]
for text, expected in cases:
    got = mod._parse_hms(text)
    assert got == expected, f"_parse_hms({text!r}) = {got!r}, attendu {expected!r}"

# Round-trip with the player's own format (M:SS, no leading hour under 1 h).
for secs, expected in ((0.0, "0:00"), (109.0, "1:49"), (5025.0, "1:23:45")):
    assert mod._format_hms(secs) == expected, (
        f"_format_hms({secs}) = {mod._format_hms(secs)!r}, attendu {expected!r}")
    assert mod._parse_hms(mod._format_hms(secs)) == secs, "aller-retour instable"

# ── the ffmpeg cut is built once, with both bounds ────────────────────
cmd = mod._build_trim_cmd("/in.webm", "/out.wav", 109.44, 900.0)
assert cmd[0] == "ffmpeg", cmd
joined = " ".join(cmd)
assert "-ss 109.440" in joined, joined
assert "-to 900.000" in joined, joined
assert "/in.webm" in cmd and "/out.wav" in cmd
# 16 kHz mono PCM, like every other path feeding the daemons
assert "-ar" in cmd and "16000" in cmd and "-ac" in cmd and "1" in cmd, joined

# An open end (only a start bound) must not emit -to at all.
open_end = " ".join(mod._build_trim_cmd("/in.webm", "/out.wav", 109.44, None))
assert "-ss 109.440" in open_end and "-to" not in open_end, open_end

# ── timestamps are rebased onto the original timeline ─────────────────
raw = ("[0.00s - 12.34s] Speaker 0: Bonjour à tous.\n"
       "[12.34s - 20.00s] Speaker 1: Merci de m'inviter.\n")
segs = mod._parse_diarize_output(raw, offset=109.44)
assert [round(s["start"], 2) for s in segs] == [109.44, 121.78], segs
assert [round(s["end"], 2) for s in segs] == [121.78, 129.44], segs
assert segs[0]["speaker"] == "Speaker 0" and segs[1]["text"] == "Merci de m'inviter."

# Default stays 0: every existing caller keeps its behaviour.
assert [s["start"] for s in mod._parse_diarize_output(raw)] == [0.0, 12.34]

print("OK")

# ── UI: the two fields live between the player and the diarize switch ──
from PyQt6.QtWidgets import QApplication          # noqa: E402

app = QApplication.instance() or QApplication([])
win = mod.TranscribeWindow()

assert hasattr(win, "_ed_trim_start") and hasattr(win, "_ed_trim_end"), (
    "les deux champs de bornes doivent exister dans la fenetre")
assert win._ed_trim_start.text() == "" and win._ed_trim_end.text() == "", (
    "sans bornes saisies, les champs sont vides (= fichier entier)")
assert win._trim_bounds() is None, "aucune borne = pas de decoupe du tout"

# Typing a bound feeds the slider so the excluded zone is visible.
win._ed_trim_start.setText("1:49")
win._on_trim_edited()
assert win._trim_bounds() == (109.0, None), win._trim_bounds()
assert win._sld_position._trim_start_ms == 109000, (
    "la borne saisie doit se voir sur la barre de lecture")

win._ed_trim_end.setText("15:00")
win._on_trim_edited()
assert win._trim_bounds() == (109.0, 900.0), win._trim_bounds()

# An end before the start is refused rather than silently swapped: a cut is
# destructive for the run, the user must see their mistake.
win._ed_trim_end.setText("0:30")
win._on_trim_edited()
assert win._trim_bounds() == (109.0, None), (
    f"fin < debut doit etre ignoree, obtenu {win._trim_bounds()}")

# Loading another file clears the bounds — they belong to the old audio.
win._reset_trim()
assert win._ed_trim_start.text() == "" and win._ed_trim_end.text() == ""
assert win._trim_bounds() is None
assert win._sld_position._trim_start_ms is None

# Dragging on the slider updates the fields, both directions stay in sync.
win._sld_position.setRange(0, 900000)
win._sld_position.set_trim(120000, 600000)
win._on_trim_slider_changed(120000, 600000)
assert win._ed_trim_start.text() == "2:00", win._ed_trim_start.text()
assert win._ed_trim_end.text() == "10:00", win._ed_trim_end.text()

print("OK UI")

# ── the cut actually runs (catches missing imports / bad ffmpeg args) ──
import subprocess as _sp                          # noqa: E402
import wave                                       # noqa: E402

_src = "/tmp/dictee-trim-test-src.wav"
_sp.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", _src],
        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, check=True)

out = win._make_trimmed_audio(_src, 5.0, 12.0)
assert out and os.path.isfile(out), "la decoupe doit produire un fichier"
with wave.open(out) as w:
    secs = w.getnframes() / w.getframerate()
    assert w.getframerate() == 16000 and w.getnchannels() == 1, "16 kHz mono attendu"
assert 6.5 <= secs <= 7.5, f"extrait de ~7 s attendu, obtenu {secs:.2f} s"

# Open end: from 20 s to the end of a 30 s file = ~10 s.
out2 = win._make_trimmed_audio(_src, 20.0, None)
with wave.open(out2) as w:
    secs2 = w.getnframes() / w.getframerate()
assert 9.0 <= secs2 <= 11.0, f"~10 s attendu, obtenu {secs2:.2f} s"

# A missing source fails cleanly (None), it must not raise.
assert win._make_trimmed_audio("/nonexistent.wav", 0.0, 5.0) is None

for _f in (_src, out, out2):
    try:
        os.unlink(_f)
    except OSError:
        pass
print("OK cut")

# ── no bounds => the slider behaves exactly as before ─────────────────
sld = mod._ClickSlider()
sld.setRange(0, 600000)
assert sld._trim_handle_at(50) is None, (
    "sans bornes, aucun point du slider ne doit capturer le clic: "
    "le clic-pour-naviguer doit rester intact")
# With bounds, only the immediate neighbourhood of a handle grabs.
sld.set_trim(300000, None)
sld.resize(400, 44)
_g = sld._groove_rect()
_hx = _g.x() + _g.width() * 0.5
assert sld._trim_handle_at(_hx) == "start", "la poignee doit se saisir"
assert sld._trim_handle_at(_hx + 40) is None, (
    "loin de la poignee, le clic reste un deplacement de lecture")
print("OK slider")

# ── the tab keeps the ORIGINAL file, engines get the trimmed one ───────
# Regression guard (user-reported 2026-08-04): reassigning audio_path to the
# trimmed temp file leaked it into _init_tab_state, so the player reloaded
# the EXCERPT on tab switch while timestamps were rebased on the original —
# follow-playback, click-to-play and highlight-current-segment were all off
# by the start bound — and exports were named dictee-trim-XXXX.
_orig_wav = "/tmp/dictee-trim-test-orig.wav"
_sp.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", _orig_wav],
        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, check=True)

seen = {}
_real_init = win._init_tab_state
win._init_tab_state = lambda ed, ap=None: (seen.update(tab_audio=ap),
                                           _real_init(ed, ap))[1]
_real_trim = win._make_trimmed_audio
win._make_trimmed_audio = lambda src, s, e: (seen.update(engine_src=src),
                                             _real_trim(src, s, e))[1]
# Stop right after the tab is created: we only care about which path landed
# where, not about running an engine.
win._get_audio_duration = lambda p: (seen.update(dur_of=p), 30.0)[1]
win._select_cmd_boom = RuntimeError("stop here")

# _on_transcribe returns immediately on an invisible window (line ~4921),
# so the offscreen window has to be shown for the run to start at all.
win.show()
win._file_input.setText(_orig_wav)
win._ed_trim_start.setText("0:05")
win._ed_trim_end.setText("0:12")
win._on_trim_edited()
try:
    win._on_transcribe()
except Exception:
    pass          # whatever fails downstream, the assignment already happened

assert seen.get("tab_audio") == _orig_wav, (
    f"l'onglet doit memoriser le fichier ORIGINAL, il a recu "
    f"{seen.get('tab_audio')!r}")
assert seen.get("engine_src") == _orig_wav, "la decoupe part du fichier original"
assert seen.get("dur_of") and seen["dur_of"] != _orig_wav, (
    "la duree qui pilote le routage doit etre celle de l'EXTRAIT")
assert abs(win._trim_offset - 5.0) < 0.01, win._trim_offset
# And the export name comes from the original, not from the temp file.
assert win._export_base_for(win._text_edit) == "dictee-trim-test-orig", (
    win._export_base_for(win._text_edit))

# The run actually spawned an engine on the excerpt: kill it, otherwise
# the test leaves a transcribe process behind.
if getattr(win, "_process", None) is not None:
    win._process.kill()
    win._process.waitForFinished(3000)
print("OK separation source/traitement")

# ── a retry reuses the bounds ITS run was started with ────────────────
# The retry fires on GPU OOM and is meant to redo the SAME run. Dropping the
# bounds would transcribe the WHOLE file instead of the excerpt — making the
# very cause of the failure worse — and re-reading the fields would pick up
# whatever the user typed during the 2 s delay.
assert getattr(win._text_edit, "_trim_bounds_used", "missing") == (5.0, 12.0), (
    f"le run doit memoriser ses bornes sur l'onglet, obtenu "
    f"{getattr(win._text_edit, '_trim_bounds_used', 'missing')!r}")

_tab = win._text_edit
win._ed_trim_start.setText("9:99")      # user meddles during the retry delay
win._ed_trim_end.clear()
seen.clear()
try:
    win._on_transcribe(retry_of=_tab)
except Exception:
    pass
assert seen.get("engine_src") == _orig_wav, "le retry repart du fichier original"
assert abs(win._trim_offset - 5.0) < 0.01, (
    f"le retry doit RE-appliquer les bornes du run initial (offset 5.0), "
    f"obtenu {win._trim_offset}")
if getattr(win, "_process", None) is not None:
    win._process.kill()
    win._process.waitForFinished(3000)
print("OK retry")

win._init_tab_state = _real_init
win._make_trimmed_audio = _real_trim
try:
    os.unlink(_orig_wav)
except OSError:
    pass
