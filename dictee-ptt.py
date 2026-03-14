#!/usr/bin/env python3
"""dictee-ptt — daemon push-to-talk / toggle pour dictee.

Écoute les claviers physiques via /dev/input/event* et déclenche dictee
selon le mode configuré (toggle ou hold).

En mode hold : key-down = start (synchrone, attend PIDFILE),
               key-up = stop+transcribe (asynchrone).

Usage:
    dictee-ptt [--mode=toggle|hold] [--key=67] [--key-translate=0]
    dictee-ptt --help

Nécessite : groupe 'input' pour lire /dev/input/event*.

Keycodes Linux courants :
    F1=59  F2=60  F3=61  F4=62  F5=63  F6=64  F7=65  F8=66
    F9=67  F10=68 F11=87 F12=88 ESC=1
"""

import struct
import subprocess
import signal
import select
import os
import sys
import re
import time
import fcntl

# --- Config ---

CONF_PATH = os.path.expanduser("~/.config/dictee.conf")
DICTEE_BIN = None  # auto-detect
PIDFILE = "/tmp/recording_dictee_pid"
OWN_PIDFILE = "/tmp/dictee-ptt.pid"

# Constantes input_event
KEY_ESC = 1
EV_KEY = 1
KEY_DOWN = 1
KEY_UP = 0
KEY_REPEAT = 2
EVENT_SIZE = struct.calcsize("llHHi")
EVENT_FMT = "llHHi"

DEBOUNCE = 0.15       # 150ms anti-rebond
STOP_COOLDOWN = 0.5   # 500ms — ignore KEY_DOWN parasites après stop
PIDFILE_TIMEOUT = 3.0 # attente max PIDFILE au key-up
RESCAN_INTERVAL = 10  # secondes entre rescans claviers (hotplug)


def load_config():
    """Charge dictee.conf et retourne un dict."""
    conf = {}
    if os.path.isfile(CONF_PATH):
        with open(CONF_PATH) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    conf[k.strip()] = v.strip().strip('"').strip("'")
    return conf


def find_keyboards():
    """Trouve les claviers physiques via /proc/bus/input/devices.

    Cherche les devices avec handler 'kbd' (couvre USB, Bluetooth, PS/2).
    Exclut les claviers virtuels (uinput, dotool, etc.).
    """
    devs = []
    try:
        with open("/proc/bus/input/devices") as f:
            content = f.read()
    except (PermissionError, FileNotFoundError):
        return devs

    for block in content.split("\n\n"):
        lines = block.strip().splitlines()
        name_line = handlers_line = ""
        for line in lines:
            if line.startswith("N:"):
                name_line = line
            elif line.startswith("H:"):
                handlers_line = line
        # kbd suffit — sysrq n'est pas présent sur tous les claviers (Bluetooth, certains USB)
        if "kbd" in handlers_line:
            if not re.search(r"virtual|Virtual|uinput|dotool", name_line, re.IGNORECASE):
                m = re.search(r"event\d+", handlers_line)
                if m:
                    devs.append(f"/dev/input/{m.group()}")
    return devs


def find_dictee_bin():
    """Trouve le script dictee."""
    for p in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictee"),
        os.path.expanduser("~/.local/bin/dictee"),
        "/usr/bin/dictee",
    ]:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return "dictee"


def run_dictee_async(*args, no_animation=False):
    """Lance dictee en subprocess non-bloquant."""
    cmd = [DICTEE_BIN] + list(args)
    env = None
    if no_animation:
        env = os.environ.copy()
        env["DICTEE_ANIMATION"] = "none"
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    except Exception as e:
        print(f"[ptt] erreur {cmd}: {e}", file=sys.stderr)


def wait_pidfile():
    """Attend que le PIDFILE apparaisse (dictee a démarré pw-record)."""
    deadline = time.monotonic() + PIDFILE_TIMEOUT
    while time.monotonic() < deadline:
        if os.path.isfile(PIDFILE):
            return True
        time.sleep(0.02)
    return False



def acquire_lock():
    """Empêche les instances multiples via flock."""
    try:
        lf = open(OWN_PIDFILE, "w")
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lf.write(str(os.getpid()))
        lf.flush()
        return lf
    except OSError:
        print("[ptt] une autre instance est déjà active!", file=sys.stderr)
        sys.exit(1)


def open_keyboards(existing_paths):
    """Ouvre les nouveaux claviers détectés (hotplug)."""
    new_fds = []
    for dev in find_keyboards():
        if dev not in existing_paths:
            try:
                new_fds.append(open(dev, "rb", buffering=0))
                print(f"[ptt] clavier ajouté: {dev}")
            except (PermissionError, FileNotFoundError) as e:
                print(f"[ptt] impossible d'ouvrir {dev}: {e}", file=sys.stderr)
    return new_fds


def sync_state():
    """Resynchronise l'état interne avec l'état réel (PIDFILE)."""
    return os.path.isfile(PIDFILE)


def main():
    global DICTEE_BIN

    mode = "toggle"
    key_dictee = 67   # F9
    key_translate = 0  # désactivé par défaut
    conf = load_config()

    mode = conf.get("DICTEE_PTT_MODE", mode)
    if "DICTEE_PTT_KEY" in conf:
        key_dictee = int(conf["DICTEE_PTT_KEY"])
    if "DICTEE_PTT_KEY_TRANSLATE" in conf:
        key_translate = int(conf["DICTEE_PTT_KEY_TRANSLATE"])

    for arg in sys.argv[1:]:
        if arg.startswith("--mode="):
            mode = arg.split("=", 1)[1]
        elif arg.startswith("--key="):
            key_dictee = int(arg.split("=", 1)[1])
        elif arg.startswith("--key-translate="):
            key_translate = int(arg.split("=", 1)[1])
        elif arg == "--help":
            print(__doc__)
            sys.exit(0)

    lock_file = acquire_lock()
    DICTEE_BIN = find_dictee_bin()

    print(f"[ptt] mode={mode} key={key_dictee} key_translate={key_translate}")
    print(f"[ptt] dictee={DICTEE_BIN}")

    kbd_devs = find_keyboards()
    if not kbd_devs:
        print("[ptt] aucun clavier détecté!", file=sys.stderr)
        sys.exit(1)

    print(f"[ptt] claviers: {kbd_devs}")

    fds = []
    for dev in kbd_devs:
        try:
            fds.append(open(dev, "rb", buffering=0))
        except (PermissionError, FileNotFoundError) as e:
            print(f"[ptt] impossible d'ouvrir {dev}: {e}", file=sys.stderr)

    if not fds:
        print("[ptt] aucun clavier accessible! (groupe 'input' requis)", file=sys.stderr)
        sys.exit(1)

    running = True

    def on_signal(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    recording = False
    recording_translate = False
    last_down_time = 0
    last_stop_time = 0
    keys_held = set()
    last_rescan = time.monotonic()

    print("[ptt] en écoute...")

    while running:
        # Nettoyer les fd morts (clavier débranché)
        dead = [f for f in fds if f.closed]
        if dead:
            for f in dead:
                fds.remove(f)
                print(f"[ptt] clavier retiré: {f.name}")

        # Hotplug : rescanner les claviers périodiquement
        now_mono = time.monotonic()
        if now_mono - last_rescan > RESCAN_INTERVAL:
            last_rescan = now_mono
            existing = {f.name for f in fds}
            new_fds = open_keyboards(existing)
            fds.extend(new_fds)

        if not fds:
            # Plus de clavier — attendre le rescan
            time.sleep(1)
            last_rescan = 0  # forcer rescan immédiat
            continue

        try:
            ready, _, _ = select.select(fds, [], [], 1.0)
        except (ValueError, OSError):
            # fd invalide — nettoyer au prochain tour
            bad = []
            for f in fds:
                try:
                    select.select([f], [], [], 0)
                except (ValueError, OSError):
                    bad.append(f)
            for f in bad:
                print(f"[ptt] clavier perdu: {f.name}")
                try:
                    f.close()
                except OSError:
                    pass
                fds.remove(f)
            continue

        for f in ready:
            try:
                data = f.read(EVENT_SIZE)
            except OSError:
                try:
                    f.close()
                except OSError:
                    pass
                continue
            if len(data) < EVENT_SIZE:
                continue

            _sec, _usec, ev_type, code, value = struct.unpack(EVENT_FMT, data)

            if ev_type != EV_KEY or value == KEY_REPEAT:
                continue

            # Déduplique multi-claviers
            if value == KEY_DOWN:
                if code in keys_held:
                    continue
                keys_held.add(code)
            elif value == KEY_UP:
                keys_held.discard(code)

            now = time.monotonic()

            # Resync : si recording=True mais PIDFILE absent depuis longtemps → reset
            if (recording or recording_translate) and now - last_down_time > PIDFILE_TIMEOUT + 2:
                if not sync_state():
                    print("[ptt] resync: enregistrement terminé extérieurement")
                    recording = False
                    recording_translate = False
                    last_stop_time = now

            # --- ESC : annuler ---
            if code == KEY_ESC and value == KEY_DOWN:
                if recording or recording_translate:
                    print("[ptt] ESC → cancel")
                    run_dictee_async("--cancel")
                    recording = False
                    recording_translate = False
                    last_stop_time = now
                continue

            # Empêcher dictée + traduction simultanées
            if recording_translate and code == key_dictee:
                continue
            if recording and key_translate and code == key_translate:
                continue

            # --- Touche dictée ---
            if code == key_dictee:
                if mode == "hold":
                    if value == KEY_DOWN and not recording:
                        if now - last_down_time < DEBOUNCE:
                            continue
                        if now - last_stop_time < STOP_COOLDOWN:
                            continue
                        last_down_time = now
                        print("[ptt] hold: start")
                        run_dictee_async("--no-esc-listener", no_animation=True)
                        recording = True
                    elif value == KEY_UP and recording:
                        if not os.path.isfile(PIDFILE):
                            wait_pidfile()
                        print("[ptt] hold: stop")
                        run_dictee_async("--no-esc-listener")
                        recording = False
                        last_stop_time = now
                else:  # toggle
                    if value == KEY_DOWN:
                        if now - last_down_time < DEBOUNCE:
                            continue
                        if now - last_stop_time < STOP_COOLDOWN:
                            continue
                        last_down_time = now
                        if not recording:
                            print("[ptt] toggle: start")
                            run_dictee_async("--no-esc-listener")
                            recording = True
                        else:
                            print("[ptt] toggle: stop")
                            run_dictee_async("--no-esc-listener")
                            recording = False
                            last_stop_time = now
                continue

            # --- Touche traduction ---
            if key_translate and code == key_translate:
                if mode == "hold":
                    if value == KEY_DOWN and not recording_translate:
                        if now - last_down_time < DEBOUNCE:
                            continue
                        if now - last_stop_time < STOP_COOLDOWN:
                            continue
                        last_down_time = now
                        print("[ptt] hold: start+translate")
                        run_dictee_async("--no-esc-listener", "--translate", no_animation=True)
                        recording_translate = True
                    elif value == KEY_UP and recording_translate:
                        if not os.path.isfile(PIDFILE):
                            wait_pidfile()
                        print("[ptt] hold: stop+translate")
                        run_dictee_async("--no-esc-listener", "--translate")
                        recording_translate = False
                        last_stop_time = now
                else:  # toggle
                    if value == KEY_DOWN:
                        if now - last_down_time < DEBOUNCE:
                            continue
                        if now - last_stop_time < STOP_COOLDOWN:
                            continue
                        last_down_time = now
                        if not recording_translate:
                            print("[ptt] toggle: start+translate")
                            run_dictee_async("--no-esc-listener", "--translate")
                            recording_translate = True
                        else:
                            print("[ptt] toggle: stop+translate")
                            run_dictee_async("--no-esc-listener", "--translate")
                            recording_translate = False
                            last_stop_time = now

    for f in fds:
        try:
            f.close()
        except OSError:
            pass
    try:
        os.unlink(OWN_PIDFILE)
    except OSError:
        pass
    lock_file.close()
    print("[ptt] arrêt.")


if __name__ == "__main__":
    main()
