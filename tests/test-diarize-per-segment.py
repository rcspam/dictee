"""_DiarizeTranscribeWorker per-segment mode (timestamp-less backends).

Nemotron returns no word/sentence timestamps: a full-audio '\tdiarize'
request yields an empty body ("Empty transcription from daemon"). In
per-segment mode the worker must cut the audio on the diarized segments
and send one PLAIN request per segment instead.
"""
import importlib.machinery
import pathlib
import socket
import threading
import wave

dt = importlib.machinery.SourceFileLoader(
    "dt", str(pathlib.Path(__file__).resolve().parent.parent / "dictee-transcribe.py")
).load_module()


def _make_wav(path, seconds=2.0):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * int(16000 * seconds))


class _FakeDaemon(threading.Thread):
    """Stand-in for transcribe-daemon with the nemotron backend: a plain
    'path\\n' request gets a fixed text, a '\\tdiarize'/'\\ttimestamps'
    request gets an EMPTY body (nemotron has no timestamp tokens)."""

    def __init__(self, sock_path):
        super().__init__(daemon=True)
        self.requests = []
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(sock_path)
        self._srv.listen(8)

    def run(self):
        while True:
            try:
                conn, _addr = self._srv.accept()
            except OSError:
                return
            req = b""
            while not req.endswith(b"\n"):
                buf = conn.recv(4096)
                if not buf:
                    break
                req += buf
            line = req.decode("utf-8").rstrip("\n")
            if not line:        # socket-availability probe (connect+close)
                conn.close()
                continue
            self.requests.append(line)
            try:
                if "\t" not in line:
                    conn.sendall("texte du segment".encode("utf-8"))
                # else: empty body, like the nemotron backend in diarize mode
            except OSError:
                pass
            conn.close()

    def stop(self):
        self._srv.close()


def test_per_segment_two_phase(tmp_path):
    wav = tmp_path / "audio.wav"
    _make_wav(wav)
    sock_path = str(tmp_path / "fake.sock")
    daemon = _FakeDaemon(sock_path)
    daemon.start()

    diarize_output = "0.0 0.8 0\n1.0 1.8 1\n"
    worker = dt._DiarizeTranscribeWorker(
        str(wav), diarize_output, sock_path, per_segment=True)
    out, errs = [], []
    worker.finished.connect(out.append)
    worker.error.connect(errs.append)
    worker.run()        # synchronous: QThread.run called directly
    daemon.stop()

    assert errs == []
    assert out == ["[0.00s - 0.80s] Speaker 0: texte du segment\n"
                   "[1.00s - 1.80s] Speaker 1: texte du segment"]
    # Per-segment mode must never use the diarize/timestamps wire mode.
    assert daemon.requests and all("\t" not in r for r in daemon.requests)


def test_per_segment_skips_sub300ms(tmp_path):
    wav = tmp_path / "audio.wav"
    _make_wav(wav)
    sock_path = str(tmp_path / "fake.sock")
    daemon = _FakeDaemon(sock_path)
    daemon.start()

    diarize_output = "0.0 0.1 0\n0.5 1.5 1\n"   # first segment is < 0.3 s
    worker = dt._DiarizeTranscribeWorker(
        str(wav), diarize_output, sock_path, per_segment=True)
    out, errs = [], []
    worker.finished.connect(out.append)
    worker.error.connect(errs.append)
    worker.run()
    daemon.stop()

    assert errs == []
    assert out == ["[0.50s - 1.50s] Speaker 1: texte du segment"]
