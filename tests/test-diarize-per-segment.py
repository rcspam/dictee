"""_DiarizeTranscribeWorker on the Nemotron 3 pieces, against a stand-in
daemon.

"pieces" mode cuts the audio on the pieces and sends one PLAIN request per
piece. "words" mode (Nemotron 3.5) sends one '\ttimestamps' request for the
whole file and gives each timed word to the piece around its middle.
"""
import importlib.machinery
import pathlib
import socket
import threading
import wave

dt = importlib.machinery.SourceFileLoader(
    "dt", str(pathlib.Path(__file__).resolve().parent.parent / "dictee-transcribe.py")
).load_module()

# What the stand-in answers a '\ttimestamps' request: timed words, the way
# transcribe-daemon formats them, dated like Nemotron 3.5 about 0.3 s after
# they are said.
TIMED_WORDS = ("[0.40s - 0.48s] Bonjour\n[0.72s - 0.80s] Alice.\n"
               "[1.36s - 1.44s] Salut\n[1.80s - 1.88s] Bob.\n"
               "[2.10s - 2.18s] Ça\n[2.30s - 2.38s] va ?")


def _make_wav(path, seconds=2.0):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * int(16000 * seconds))


class _FakeDaemon(threading.Thread):
    """Stand-in for transcribe-daemon: a plain 'path\\n' request gets a
    fixed text, a '\\ttimestamps' request TIMED_WORDS, a '\\tdiarize' one
    an empty body."""

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
                elif line.endswith("\ttimestamps"):
                    conn.sendall(TIMED_WORDS.encode("utf-8"))
            except OSError:
                pass
            conn.close()

    def stop(self):
        self._srv.close()


def _run(tmp_path, diarize_output, mode):
    wav = tmp_path / "audio.wav"
    _make_wav(wav, seconds=3.0)
    sock_path = str(tmp_path / "fake.sock")
    daemon = _FakeDaemon(sock_path)
    daemon.start()
    worker = dt._DiarizeTranscribeWorker(str(wav), diarize_output, sock_path, mode=mode)
    out, errs = [], []
    worker.finished.connect(out.append)
    worker.error.connect(errs.append)
    worker.run()        # synchronous: QThread.run called directly
    daemon.stop()
    return out, errs, daemon.requests


def test_per_segment_two_phase(tmp_path):
    out, errs, requests = _run(tmp_path, "0.0 0.8 0\n1.0 1.8 1\n", "pieces")
    assert errs == []
    assert out == ["[0.00s - 0.80s] Speaker 0: texte du segment\n"
                   "[1.00s - 1.80s] Speaker 1: texte du segment"]
    # Per-segment mode must never use the diarize/timestamps wire mode.
    assert requests and all("\t" not in r for r in requests)


def test_per_segment_skips_sub300ms(tmp_path):
    out, errs, _requests = _run(tmp_path, "0.0 0.1 0\n0.5 1.5 1\n", "pieces")
    assert errs == []
    assert out == ["[0.50s - 1.50s] Speaker 1: texte du segment"]


def test_words_mode_gives_each_timed_word_to_its_piece(tmp_path):
    # Alice's piece, Bob's, Alice's again: "Bob.", dated in Alice's second
    # piece, was said in his; each line is timed with its piece
    out, errs, requests = _run(tmp_path, "0.0 0.8 0\n1.0 1.72 1\n1.72 2.6 0\n", "words")
    assert errs == []
    assert len(requests) == 1 and requests[0].endswith("\ttimestamps")
    assert out == ["[0.00s - 0.80s] Speaker 0: Bonjour Alice.\n"
                   "[1.00s - 1.72s] Speaker 1: Salut Bob.\n"
                   "[1.72s - 2.60s] Speaker 0: Ça va ?"]
