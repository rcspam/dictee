#!/usr/bin/env python3
"""Voie A via a socket daemon (canary or whisper), with the SAME Sortformer
cleaning as the Nemotron POC, so the 3 backends share identical segments.
Sortformer + the daemon are forced to CPU (GPU is held by dictee.service).
Usage: voie-a-segment.py <audio.wav> <canary|whisper>"""
import os, sys, socket, subprocess, tempfile, time

AUDIO = os.path.abspath(sys.argv[1])
BACKEND = sys.argv[2]
SORTFORMER_DIR = "/usr/share/dictee/sortformer"
SOCK = f"/tmp/poc-{BACKEND}-cmp-{os.getpid()}.sock"
MIN_DUR, MERGE_GAP = 1.0, 0.6


def clean(segs, min_dur, merge_gap):
    segs = [(a, b, s) for (a, b, s) in segs if b - a >= min_dur]
    segs.sort()
    out = []
    for (a, b, s) in segs:
        if out:
            pa, pb, ps = out[-1]
            if a < pb:
                if s == ps:
                    out[-1] = (pa, max(pb, b), ps); continue
                a = pb
                if b - a < min_dur:
                    continue
            if s == ps and a - pb <= merge_gap:
                out[-1] = (pa, b, ps); continue
        out.append((a, b, s))
    return out


env = dict(os.environ, DICTEE_FORCE_CPU="1")
r = subprocess.run(["diarize-only", AUDIO, SORTFORMER_DIR], capture_output=True, text=True, env=env)
raw = []
for ln in r.stdout.splitlines():
    p = ln.split()
    if len(p) >= 3:
        try:
            raw.append((float(p[0]), float(p[1]), int(p[2])))
        except ValueError:
            pass
segs = clean(raw, MIN_DUR, MERGE_GAP)
print(f"Sortformer: {len(raw)} raw -> {len(segs)} clean segments")

if BACKEND == "canary":
    denv = dict(os.environ, DICTEE_ASR_BACKEND="canary", DICTEE_LANG_SOURCE="fr",
                DICTEE_TRANSCRIBE_SOCKET=SOCK, DICTEE_FORCE_CPU="1", DICTEE_DAEMON_NO_PROVIDER="1")
    cmd = ["transcribe-daemon", "--canary", "/usr/share/dictee/canary", "--socket", SOCK]
elif BACKEND == "whisper":
    venv_py = os.path.expanduser("~/.local/share/dictee/whisper-env/bin/python")
    denv = dict(os.environ, DICTEE_TRANSCRIBE_SOCKET=SOCK, DICTEE_FORCE_CPU="1",
                DICTEE_LANG_SOURCE="fr",
                DICTEE_WHISPER_MODEL=os.environ.get("DICTEE_WHISPER_MODEL", "medium"),
                DICTEE_DAEMON_NO_PROVIDER="1")
    cmd = [venv_py, "/usr/bin/transcribe-daemon-whisper"]
else:
    sys.exit("backend must be canary|whisper")

log = open(f"/tmp/poc-{BACKEND}-cmp.log", "w")
daemon = subprocess.Popen(cmd, env=denv, stdout=log, stderr=log)
try:
    for _ in range(240):
        if os.path.exists(SOCK):
            break
        if daemon.poll() is not None:
            sys.exit(f"{BACKEND} daemon died (see /tmp/poc-{BACKEND}-cmp.log)")
        time.sleep(1)
    else:
        sys.exit("daemon socket timeout")

    def ask(wav):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(180); s.connect(SOCK)
        s.sendall((wav + "\n").encode())
        buf = b""
        while True:
            try:
                c = s.recv(65536)
            except socket.timeout:
                break
            if not c:
                break
            buf += c
        s.close()
        return buf.decode(errors="replace").strip()

    tmp = tempfile.mkdtemp()
    print(f"\n=== VOIE A — {BACKEND} (fr) per Sortformer segment ===")
    for i, (a, b, spk) in enumerate(segs):
        w = f"{tmp}/seg_{i}.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", AUDIO,
                        "-ss", f"{a}", "-t", f"{b - a}", "-ar", "16000", "-ac", "1", w],
                       stdin=subprocess.DEVNULL)
        print(f"[{a:7.2f} - {b:7.2f}] SPK{spk}: {ask(os.path.abspath(w))}")
    subprocess.run(["rm", "-rf", tmp])
finally:
    daemon.terminate()
    try:
        daemon.wait(5)
    except Exception:
        daemon.kill()
    if os.path.exists(SOCK):
        os.remove(SOCK)
