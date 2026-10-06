"""The elapsed clock of a run stays on the status line between ticks.

The run ticker appends "(mm:ss)" once a second, but every progress update
rewrote the line without it: with pieces transcribed several times a second
(Kyutai, 2026-10-06) the clock blinked on and off. Checks that a progress
update, a phase change or a chunk update keeps the clock at once, that a tick
does not add a second one, and that a message written once the run is over
gets none.

Run: python3 tests/offscreen-check_run_clock.py
"""
import importlib.util
import os
import re
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="dictee-clock-check-")
# a configured install, or the window opens the first-run dialog and waits
with open(os.path.join(os.environ["XDG_CONFIG_HOME"], "dictee.conf"), "w") as f:
    f.write("DICTEE_SETUP_DONE=true\n")
# the assertions read the msgids
os.environ["LANGUAGE"] = "C"
os.environ["LC_ALL"] = "C"
os.environ["LANG"] = "C"

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "dictee_transcribe", os.path.join(HERE, "..", "dictee-transcribe.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_transcribe"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

CLOCK = re.compile(r" \(01:0[23]\)$")   # 62 s in, a second may pass meanwhile

win = mod.TranscribeWindow()
win.show()


def line():
    return win._lbl_status.text()


# a run started 62 s ago, its ticker running
win._start_time = time.monotonic() - 62
win._start_run_ticker()
win._on_run_tick()
assert CLOCK.search(line()), line()

win._on_diarize_progress(5, 120)
assert line().startswith("Transcribing 5/120..."), line()
assert CLOCK.search(line()), f"progress dropped the clock: {line()!r}"

win._on_chunked_phase(2, "Phase 2/3: chunked transcription")
assert CLOCK.search(line()), f"phase change dropped the clock: {line()!r}"
win._on_chunked_progress(1, 5)
assert "chunk 1/5" in line() and CLOCK.search(line()), line()

# a tick on top of a clocked line keeps a single clock
win._on_run_tick()
assert line().count("(01:0") == 1, line()

# the run is over: an error is written without a clock
win._stop_run_ticker()
win._run_status("Transcription failed (code 1).")
assert line() == "Transcription failed (code 1).", line()

win.close()
print("OK")
