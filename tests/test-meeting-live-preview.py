#!/usr/bin/env python3
"""Tests for the live preview of dictee-meeting-live, cut by voices.

LivePreview feeds the recording pw-record is still writing to a streaming
diarizer (diarize-only --stream --engine nemotron3 --pieces), then sends each
piece it settles to an ASR daemon. Here both engines are stand-ins: a script
that hears a speaker per sample value and answers like diarize-only, and a
socket server that answers with the speakers and length of the audio it got,
so a piece cut at the wrong place shows in its text.

The code under test is read out of dictee-meeting-live without importing the
script, which needs PyQt6 (absent from CI).

Run: python3 tests/test-meeting-live-preview.py [-v]
"""

import collections
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import wave

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "dictee-meeting-live")


def _load(*names):
    """Top-level defs and classes of dictee-meeting-live, run in one
    namespace with the standard modules they use."""
    with open(SCRIPT, encoding="utf-8") as f:
        lines = f.readlines()
    ns = {m.__name__: m for m in (os, shutil, socket, struct, subprocess,
                                  tempfile, threading, time, wave)}
    ns["collections"] = collections
    for name in names:
        start = next(i for i, line in enumerate(lines)
                     if line.startswith((f"def {name}(", f"class {name}:",
                                         f"class {name}(")))
        end = next((j for j in range(start + 1, len(lines))
                    if lines[j].startswith(("def ", "class "))), len(lines))
        exec("".join(lines[start:end]), ns)
    return ns


NS = _load("wav_data_offset", "write_wav", "LivePreview")
wav_data_offset = NS["wav_data_offset"]
LivePreview = NS["LivePreview"]

RATE = 16000

# Stand-in for diarize-only --stream: a speaker per sample value (1000 for
# speaker 0, 2000 for speaker 1, 0 for silence). A piece is settled once a
# different value follows it; FLUSH gives the open one. Same answers as the
# real one: "start end speaker" lines, then an empty line. FAKE_FAIL=1 in its
# environment: every file is unreadable.
FAKE_DIARIZER = r'''
import os, sys, wave, array
fail = os.environ.get("FAKE_FAIL") == "1"
print("[diarize-only --stream] ready", file=sys.stderr, flush=True)
samples = array.array("h")
done = 0          # samples up to here are in settled pieces
def pieces(final):
    global done
    out, i = [], done
    while i < len(samples):
        j = i
        while j < len(samples) and samples[j] == samples[i]:
            j += 1
        if j == len(samples) and not final:
            break
        if samples[i]:
            out.append((i, j, samples[i] // 1000 - 1))
        i = done = j
    return out
for line in sys.stdin:
    cmd = line.strip()
    if cmd.startswith("FILE: "):
        if fail:
            print("ERROR: cannot read", flush=True)
            continue
        with wave.open(cmd[6:]) as w:
            samples.frombytes(w.readframes(w.getnframes()))
        found = pieces(False)
    elif cmd == "FLUSH":
        found = pieces(True)
    else:
        continue
    for a, b, s in found:
        print(f"{a / 16000:.2f} {b / 16000:.2f} {s}")
    print(flush=True)
'''


class FakeAsr:
    """Unix socket daemon answering 'voice A+B 1.25s': the speakers heard in
    the file it is sent and its length."""

    def __init__(self, path):
        self.path = path
        self.requests = 0
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(path)
        self.server.listen(4)
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                request = b""
                while not request.endswith(b"\n"):
                    request += conn.recv(4096)
                with wave.open(request.decode().strip()) as w:
                    n = w.getnframes()
                    data = w.readframes(n)
                values = set(struct.unpack(f"<{n}h", data))
                voices = "+".join(str(v // 1000 - 1) for v in sorted(values) if v)
                self.requests += 1
                conn.sendall(f"voice {voices} {n / RATE:.2f}s\n".encode())

    def close(self):
        self.server.close()


def grow_recording(path, parts, burst=0.25, pause=0.01):
    """Write a 16 kHz mono WAV the way pw-record does: a 44-byte header whose
    sizes stay 0, then the samples in bursts. parts = [(seconds, value)]."""
    samples = b"".join(struct.pack("<h", value) * int(seconds * RATE)
                       for seconds, value in parts)
    header = (b"RIFF" + struct.pack("<I", 0) + b"WAVE"
              + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16)
              + b"data" + struct.pack("<I", 0))
    step = int(burst * RATE) * 2
    with open(path, "wb") as f:
        f.write(header[:20])    # pw-record may be caught mid-header
        f.flush()
        time.sleep(pause)
        f.write(header[20:])
        for i in range(0, len(samples), step):
            f.write(samples[i:i + step])
            f.flush()
            time.sleep(pause)


class WavDataOffsetTest(unittest.TestCase):
    def test_pw_record_header_is_44_bytes(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "a.wav")
        grow_recording(path, [(0.1, 1000)], pause=0)
        with open(path, "rb") as f:
            self.assertEqual(wav_data_offset(f.read(4096)), 44)

    def test_chunks_before_the_samples_are_skipped(self):
        # ffmpeg (the normalized file) puts a LIST chunk before 'data'
        head = (b"RIFF" + struct.pack("<I", 1000) + b"WAVE"
                + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16)
                + b"LIST" + struct.pack("<I", 26) + b"INFO" + b"\0" * 22
                + b"data" + struct.pack("<I", 0))
        self.assertEqual(wav_data_offset(head), 78)

    def test_an_incomplete_header_is_not_read_yet(self):
        self.assertIsNone(wav_data_offset(b""))
        self.assertIsNone(wav_data_offset(b"RIFF\0\0\0\0WAVEfmt "))
        self.assertIsNone(wav_data_offset(b"not a wav file at all, really"))


class LivePreviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dictee-test-live-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.recording = os.path.join(self.tmp, "audio.wav")
        self.sock = os.path.join(self.tmp, "asr.sock")
        self.lines, self.errors, self.ready = [], [], []

    def preview(self, diar_cmd=None, **kw):
        return LivePreview(
            self.recording, diar_cmd or [sys.executable, "-c", FAKE_DIARIZER],
            self.sock, on_ready=lambda: self.ready.append(True),
            on_line=self.lines.append, on_error=self.errors.append,
            poll=0.05, **kw)

    def run_preview(self, preview):
        thread = threading.Thread(target=preview.run)
        thread.start()
        return thread

    def test_each_turn_comes_out_with_its_voice_and_its_own_audio(self):
        asr = FakeAsr(self.sock)
        self.addCleanup(asr.close)
        preview = self.preview()
        thread = self.run_preview(preview)
        # the window starts the preview before pw-record has written anything
        grow_recording(self.recording, [(2.0, 1000), (0.5, 0), (2.5, 2000),
                                        (1.0, 1000)])
        # turns that are over come out while the recording goes on
        deadline = time.monotonic() + 10
        while len(self.lines) < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(len(self.lines), 2, self.errors)
        preview.finish()
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.ready, [True])
        self.assertEqual(self.errors, [])
        self.assertEqual(
            [(ln["speaker"], ln["text"], ln["start_s"], ln["end_s"])
             for ln in self.lines],
            [(0, "voice 0 2.00s", 0.0, 2.0),
             (1, "voice 1 2.50s", 2.5, 5.0),
             (0, "voice 0 1.00s", 5.0, 6.0)])

    def test_pieces_wait_for_an_asr_daemon_still_loading(self):
        preview = self.preview()
        thread = self.run_preview(preview)
        grow_recording(self.recording, [(1.0, 1000), (0.5, 0)])
        time.sleep(0.3)
        asr = FakeAsr(self.sock)    # its model took a while to load
        self.addCleanup(asr.close)
        preview.finish()
        thread.join(10)
        self.assertEqual([ln["text"] for ln in self.lines], ["voice 0 1.00s"])
        self.assertEqual(self.errors, [])

    def test_without_an_asr_daemon_the_preview_says_so_once(self):
        preview = self.preview(asr_wait=0.2)
        thread = self.run_preview(preview)
        grow_recording(self.recording, [(1.0, 1000), (0.5, 0), (1.0, 2000)])
        preview.finish()
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.lines, [])
        self.assertEqual(len(self.errors), 1, self.errors)

    def test_a_diarizer_error_stops_the_preview_with_its_message(self):
        asr = FakeAsr(self.sock)
        self.addCleanup(asr.close)
        preview = self.preview(env=dict(os.environ, FAKE_FAIL="1"))
        thread = self.run_preview(preview)
        grow_recording(self.recording, [(1.0, 1000)])
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(self.errors), 1, self.errors)
        self.assertIn("cannot read", self.errors[0])

    def test_a_diarizer_that_dies_is_reported(self):
        preview = self.preview(diar_cmd=[sys.executable, "-c", "import sys; sys.exit(3)"])
        thread = self.run_preview(preview)
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.ready, [])
        self.assertEqual(len(self.errors), 1, self.errors)

    def test_abort_stops_at_once_and_quietly(self):
        asr = FakeAsr(self.sock)
        self.addCleanup(asr.close)
        preview = self.preview()
        thread = self.run_preview(preview)
        grow_recording(self.recording, [(1.0, 1000)])
        preview.abort()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.errors, [])

    def test_feed_and_piece_files_do_not_outlive_the_preview(self):
        asr = FakeAsr(self.sock)
        self.addCleanup(asr.close)
        before = set(os.listdir(tempfile.gettempdir()))
        preview = self.preview()
        thread = self.run_preview(preview)
        grow_recording(self.recording, [(1.0, 1000), (0.5, 0)])
        preview.finish()
        thread.join(10)
        self.assertEqual(len(self.lines), 1)
        leftover = {n for n in set(os.listdir(tempfile.gettempdir())) - before
                    if n.startswith("dictee-meeting-live-")}
        self.assertEqual(leftover, set())


if __name__ == "__main__":
    unittest.main()
