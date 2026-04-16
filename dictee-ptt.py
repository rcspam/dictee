#!/usr/bin/env -S python3 -u
"""dictee-ptt — daemon push-to-talk / toggle pour dictee.

Écoute les claviers physiques via evdev, capture exclusivement la touche
configurée (grab + re-émission uinput), et déclenche dictee selon le mode.

En mode hold : key-down = start, key-up = stop+transcribe.
En mode toggle : key-down = start/stop alternés.

Usage:
    dictee-ptt [--mode=toggle|hold] [--key=67] [--key-translate=67] [--mod-translate=alt]
    dictee-ptt --help

Exemples :
    dictee-ptt --mode=hold --key=67                        # F9 hold
    dictee-ptt --mode=hold --key=67 --key-translate=67 --mod-translate=alt  # F9 + Alt+F9
    dictee-ptt --mode=toggle --key=67 --key-translate=68   # F9 / F10 séparés

Nécessite : groupe 'input' pour /dev/input/* et /dev/uinput.

Keycodes Linux courants :
    F1=59  F2=60  F3=61  F4=62  F5=63  F6=64  F7=65  F8=66
    F9=67  F10=68 F11=87 F12=88 ESC=1
"""

import subprocess
import signal
import select
import os
import sys
import time
import fcntl
import re

try:
    import evdev
    from evdev import InputDevice, UInput, ecodes
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False

# --- Config ---

CONF_PATH = os.path.expanduser("~/.config/dictee.conf")
STATE_FILE = "/dev/shm/.dictee_state"


def _daemon_socket_exists():
    """Vérifie si le socket du daemon ASR existe (daemon actif sans fichier d'état)."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.path.exists(os.path.join(runtime_dir, "transcribe.sock"))


def read_state():
    """Lit l'état courant de dictee depuis le fichier d'état."""
    try:
        return open(STATE_FILE).read().strip()
    except FileNotFoundError:
        # Après reboot, /dev/shm est vide mais le daemon peut être actif.
        # Vérifier la socket avant de déclarer offline.
        if _daemon_socket_exists():
            try:
                with open(STATE_FILE, "w") as f:
                    f.write("idle\n")
            except OSError:
                pass
            return "idle"
        return "offline"
    except PermissionError:
        return "offline"


DICTEE_BIN = None  # auto-detect
_UID_SUFFIX = f"-{os.getuid()}"
PIDFILE = f"/tmp/recording_dictee_pid{_UID_SUFFIX}"
OWN_PIDFILE = f"/tmp/dictee-ptt{_UID_SUFFIX}.pid"


EV_KEY = 1
KEY_DOWN = 1
KEY_UP = 0
KEY_REPEAT = 2
KEY_ESC = 1
KEY_LEFTALT = 56
KEY_RIGHTALT = 100
KEY_LEFTCTRL = 29
KEY_RIGHTCTRL = 97
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54

# Modificateurs supportés : nom → (keycode gauche, keycode droit)
MODIFIERS = {
    "alt": (KEY_LEFTALT, KEY_RIGHTALT),
    "ctrl": (KEY_LEFTCTRL, KEY_RIGHTCTRL),
    "shift": (KEY_LEFTSHIFT, KEY_RIGHTSHIFT),
}

DEBOUNCE = 0.15       # 150ms anti-rebond
STOP_COOLDOWN = 0.5   # 500ms — ignore KEY_DOWN parasites après stop
PIDFILE_TIMEOUT = 3.0  # attente max PIDFILE au key-up
MIN_HOLD_DURATION = 0.3  # 300ms — en dessous, cancel au lieu de transcrire
RESCAN_INTERVAL = 10   # secondes entre rescans claviers (hotplug)


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


def find_keyboards_evdev():
    """Trouve les claviers physiques via evdev."""
    devs = []
    for path in evdev.list_devices():
        try:
            dev = InputDevice(path)
        except (PermissionError, OSError):
            continue
        caps = dev.capabilities(verbose=False)
        # EV_KEY présent et au moins les touches alphanumériques
        if EV_KEY in caps and len(caps.get(EV_KEY, [])) > 30:
            name = dev.name.lower()
            if not any(x in name for x in ("virtual", "uinput", "dotool", "dictee-ptt")):
                devs.append(dev)
            else:
                dev.close()
        else:
            dev.close()
    return devs


def find_keyboards_raw():
    """Trouve les claviers physiques via /proc/bus/input/devices (fallback)."""
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
        if "kbd" in handlers_line:
            if not re.search(r"virtual|uinput|dotool|dictee-ptt", name_line, re.IGNORECASE):
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


def _ensure_wayland_env(env):
    """Inject Wayland env vars if missing (sg/systemd may strip them)."""
    if "WAYLAND_DISPLAY" not in env:
        runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        if os.path.exists(os.path.join(runtime, "wayland-0")):
            env["WAYLAND_DISPLAY"] = "wayland-0"
    return env


def run_dictee_async(*args, no_animation=False):
    """Lance dictee en subprocess non-bloquant."""
    cmd = [DICTEE_BIN] + list(args)
    env = _ensure_wayland_env(os.environ.copy())
    if no_animation:
        env["DICTEE_ANIM_SPEECH"] = "false"
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


def sync_state():
    """Resynchronise l'état interne avec l'état réel (PIDFILE)."""
    return os.path.isfile(PIDFILE)


# ─── Logique PTT commune ───────────────────────────────────────────

class PttState:
    def __init__(self, mode, key_dictee, key_translate, mod_translate=""):
        self.mode = mode
        self.key_dictee = key_dictee
        self.key_translate = key_translate
        # Modificateur pour traduction (ex: "alt" → Alt+F9)
        self.mod_translate = mod_translate
        self.recording = False
        self.recording_translate = False
        self.last_down_time = 0
        self.last_stop_time = 0
        self.keys_held = set()

    def _mod_held(self, mod_name):
        """Vérifie si un modificateur est maintenu."""
        if not mod_name or mod_name not in MODIFIERS:
            return False
        left, right = MODIFIERS[mod_name]
        return left in self.keys_held or right in self.keys_held

    def _any_mod_held(self):
        """Vérifie si un modificateur quelconque est maintenu."""
        for left, right in MODIFIERS.values():
            if left in self.keys_held or right in self.keys_held:
                return True
        return False

    def handle_event(self, code, value):
        """Traite un événement clavier. Retourne True si l'événement est consommé."""
        if value == KEY_REPEAT:
            return code in (self.key_dictee, self.key_translate, KEY_ESC)

        # Déduplique multi-claviers
        if value == KEY_DOWN:
            if code in self.keys_held:
                return code in (self.key_dictee, self.key_translate)
            self.keys_held.add(code)
        elif value == KEY_UP:
            self.keys_held.discard(code)

        now = time.monotonic()

        # Resync si dictee a crashé
        if (self.recording or self.recording_translate) and now - self.last_down_time > PIDFILE_TIMEOUT + 2:
            if not sync_state():
                print("[ptt] resync: enregistrement terminé extérieurement")
                self.recording = False
                self.recording_translate = False
                self.last_stop_time = now

        # ESC : annuler
        if code == KEY_ESC and value == KEY_DOWN:
            state = read_state()
            if self.recording or self.recording_translate or state in ("recording", "preparing", "diarize-ready", "diarizing"):
                print(f"[ptt] ESC: state={state}, recording={self.recording} — sending cancel")
                run_dictee_async("--cancel")
                self.recording = False
                self.recording_translate = False
                self.last_stop_time = now
            return False  # laisser ESC passer aux applications

        # Empêcher dictée + traduction simultanées (seulement si touches différentes)
        if self.key_translate != self.key_dictee:
            if self.recording_translate and code == self.key_dictee:
                return True
            if self.recording and code == self.key_translate:
                return True

        # Déterminer si c'est dictée ou traduction
        if code == self.key_dictee:
            if self.key_translate and self.key_translate == self.key_dictee:
                # Même touche pour dictée et traduction — router selon l'état
                if value == KEY_UP:
                    # KEY_UP : router vers le handler actif, PAS selon le modificateur
                    # (l'utilisateur peut relâcher Alt avant F9)
                    if self.recording_translate:
                        self._handle_translate(value, now)
                    elif self.recording:
                        self._handle_dictee(value, now)
                elif value == KEY_DOWN:
                    # KEY_DOWN : le modificateur détermine le mode
                    if self.recording_translate:
                        # Toggle : déjà en traduction → stopper
                        self._handle_translate(value, now)
                    elif self.recording:
                        # Toggle : déjà en dictée → stopper
                        self._handle_dictee(value, now)
                    elif self.mod_translate and self._mod_held(self.mod_translate):
                        self._handle_translate(value, now)
                    elif not self._any_mod_held():
                        self._handle_dictee(value, now)
                    else:
                        return False  # modificateur inconnu, laisser passer
            else:
                # Touches séparées — route directe
                if self.mod_translate and self._mod_held(self.mod_translate):
                    self._handle_translate(value, now)
                else:
                    self._handle_dictee(value, now)
            return True  # consommer

        # Touche traduction séparée (différente de key_dictee)
        if self.key_translate and code == self.key_translate:
            self._handle_translate(value, now)
            return True  # consommer

        return False  # laisser passer

    def _check_debounce(self, now):
        if now - self.last_down_time < DEBOUNCE:
            return False
        if now - self.last_stop_time < STOP_COOLDOWN:
            return False
        return True

    def _handle_dictee(self, value, now):
        if self.mode == "hold":
            if value == KEY_DOWN and not self.recording:
                if not self._check_debounce(now):
                    return
                _st = read_state()
                if _st == "offline":
                    pass  # let dictee handle the error notification
                elif _st == "transcribing":
                    print("[ptt] hold: BLOCKED (transcribing)")
                    return
                self.last_down_time = now
                print("[ptt] hold: start")
                run_dictee_async(no_animation=True)
                self.recording = True
            elif value == KEY_UP and self.recording:
                # Toujours attendre le PIDFILE avant d'agir
                for _ in range(50):  # 1s max
                    if os.path.isfile(PIDFILE):
                        break
                    time.sleep(0.02)
                hold_duration = now - self.last_down_time
                if hold_duration < MIN_HOLD_DURATION:
                    print("[ptt] hold: cancel (trop court)")
                    run_dictee_async("--cancel")
                else:
                    # Écrire "transcribing" immédiatement pour stopper l'animation
                    # (sauf si offline — l'utilisateur a explicitement arrêté le daemon)
                    try:
                        cur = open(STATE_FILE).read().strip() if os.path.isfile(STATE_FILE) else ""
                        if cur != "offline":
                            with open(STATE_FILE, "w") as f:
                                f.write("transcribing\n")
                    except OSError:
                        pass
                    print("[ptt] hold: stop")
                    run_dictee_async()
                self.recording = False
                self.last_stop_time = now
        else:  # toggle
            if value == KEY_DOWN:
                if not self._check_debounce(now):
                    return
                # Block if daemon offline or still transcribing
                if not self.recording:
                    _st = read_state()
                    if _st == "offline":
                        pass  # let dictee handle the error notification
                    elif _st == "transcribing":
                        print("[ptt] toggle: BLOCKED (transcribing)")
                        return
                self.last_down_time = now
                if not self.recording:
                    print("[ptt] toggle: start")
                    run_dictee_async()
                    self.recording = True
                else:
                    print("[ptt] toggle: stop")
                    run_dictee_async()
                    self.recording = False
                    self.last_stop_time = now

    def _handle_translate(self, value, now):
        if self.mode == "hold":
            if value == KEY_DOWN and not self.recording_translate:
                if not self._check_debounce(now):
                    return
                _st = read_state()
                if _st == "offline":
                    pass  # let dictee handle the error notification
                elif _st == "transcribing":
                    print("[ptt] hold: BLOCKED translate (transcribing)")
                    return
                self.last_down_time = now
                print("[ptt] hold: start+translate")
                run_dictee_async("--translate", no_animation=True)
                self.recording_translate = True
            elif value == KEY_UP and self.recording_translate:
                # Toujours attendre le PIDFILE avant d'agir
                for _ in range(50):  # 1s max
                    if os.path.isfile(PIDFILE):
                        break
                    time.sleep(0.02)
                hold_duration = now - self.last_down_time
                if hold_duration < MIN_HOLD_DURATION:
                    print("[ptt] hold: cancel+translate (trop court)")
                    run_dictee_async("--cancel")
                else:
                    # Écrire "transcribing" immédiatement pour stopper l'animation
                    try:
                        cur = open(STATE_FILE).read().strip() if os.path.isfile(STATE_FILE) else ""
                        if cur != "offline":
                            with open(STATE_FILE, "w") as f:
                                f.write("transcribing\n")
                    except OSError:
                        pass
                    print("[ptt] hold: stop+translate")
                    run_dictee_async("--translate")
                self.recording_translate = False
                self.last_stop_time = now
        else:  # toggle
            if value == KEY_DOWN:
                if not self._check_debounce(now):
                    return
                # Block if daemon offline or still transcribing
                if not self.recording_translate:
                    _st = read_state()
                    if _st == "offline":
                        pass  # let dictee handle the error notification
                    elif _st == "transcribing":
                        print("[ptt] toggle: BLOCKED translate (transcribing)")
                        return
                self.last_down_time = now
                if not self.recording_translate:
                    print("[ptt] toggle: start+translate")
                    run_dictee_async("--translate")
                    self.recording_translate = True
                else:
                    print("[ptt] toggle: stop+translate")
                    run_dictee_async("--translate")
                    self.recording_translate = False
                    self.last_stop_time = now


# ─── Backend evdev (grab + uinput) ─────────────────────────────────

def run_evdev(ptt):
    """Boucle principale avec evdev : grab claviers, filtre la touche PTT, ré-émet le reste."""
    devices = find_keyboards_evdev()
    if not devices:
        print("[ptt] aucun clavier détecté!", file=sys.stderr)
        sys.exit(1)

    print(f"[ptt] claviers: {[d.path for d in devices]}")

    # Créer le clavier virtuel pour ré-émettre les événements non-PTT
    ui = UInput(name="dictee-ptt-passthrough")
    print(f"[ptt] uinput: {ui.device.path}")

    # Grab tous les claviers
    for dev in devices:
        try:
            dev.grab()
            print(f"[ptt] grab: {dev.name}")
        except OSError as e:
            print(f"[ptt] grab échoué {dev.name}: {e}", file=sys.stderr)

    # Vider les événements en buffer (évite de traiter des KEY_DOWN périmés au démarrage)
    for dev in devices:
        try:
            while dev.read_one() is not None:
                pass
        except (OSError, BlockingIOError):
            pass

    running = True
    last_rescan = time.monotonic()

    def on_signal(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    print("[ptt] en écoute (evdev grab)...")

    # Grace period : ignorer les événements pendant 500ms après le démarrage
    # pour éviter de traiter des KEY_DOWN empilés dans le noyau
    startup_time = time.monotonic()
    STARTUP_GRACE = 0.5

    try:
        while running:
            # Hotplug : rescanner périodiquement
            now_mono = time.monotonic()
            if now_mono - last_rescan > RESCAN_INTERVAL:
                last_rescan = now_mono
                known_paths = {d.path for d in devices}
                for new_dev in find_keyboards_evdev():
                    if new_dev.path not in known_paths:
                        try:
                            new_dev.grab()
                            devices.append(new_dev)
                            print(f"[ptt] hotplug grab: {new_dev.name}")
                        except OSError:
                            new_dev.close()
                    else:
                        new_dev.close()

            # Nettoyer les devices morts
            dead = []
            for dev in devices:
                try:
                    dev.fd  # accès fd pour vérifier
                except Exception:
                    dead.append(dev)
            for dev in dead:
                print(f"[ptt] clavier perdu: {dev.path}")
                devices.remove(dev)

            if not devices:
                time.sleep(1)
                last_rescan = 0
                continue

            # select sur les fd evdev
            try:
                r, _, _ = select.select(devices, [], [], 1.0)
            except (ValueError, OSError):
                # Nettoyer les fd invalides
                bad = []
                for dev in devices:
                    try:
                        select.select([dev], [], [], 0)
                    except (ValueError, OSError):
                        bad.append(dev)
                for dev in bad:
                    print(f"[ptt] clavier perdu: {dev.path}")
                    try:
                        dev.close()
                    except OSError:
                        pass
                    devices.remove(dev)
                continue

            for dev in r:
                try:
                    for event in dev.read():
                        # Grace period : ré-émettre tout sans traiter pendant le démarrage
                        if time.monotonic() - startup_time < STARTUP_GRACE:
                            if event.type == EV_KEY:
                                pass  # ignorer les KEY périmés
                            else:
                                ui.write_event(event)
                            continue

                        if event.type != EV_KEY:
                            # Ré-émettre les événements non-clavier (SYN, MSC, etc.)
                            ui.write_event(event)
                            continue

                        consumed = ptt.handle_event(event.code, event.value)
                        if not consumed:
                            ui.write_event(event)

                    ui.syn()
                except OSError:
                    # Device déconnecté
                    print(f"[ptt] clavier déconnecté: {dev.path}")
                    try:
                        dev.close()
                    except OSError:
                        pass
                    devices.remove(dev)
    finally:
        # Ungrab + fermer proprement
        for dev in devices:
            try:
                dev.ungrab()
            except OSError:
                pass
            try:
                dev.close()
            except OSError:
                pass
        ui.close()


# ─── Backend raw (fallback sans evdev) ──────────────────────────────

def run_raw(ptt):
    """Boucle principale raw /dev/input (fallback). La touche PTT fuit vers les apps."""
    import struct
    EVENT_SIZE = struct.calcsize("llHHi")
    EVENT_FMT = "llHHi"

    kbd_paths = find_keyboards_raw()
    if not kbd_paths:
        print("[ptt] aucun clavier détecté!", file=sys.stderr)
        sys.exit(1)

    print(f"[ptt] claviers: {kbd_paths}")
    print("[ptt] ATTENTION: mode raw — la touche PTT fuit vers les applications", file=sys.stderr)

    fds = []
    for dev in kbd_paths:
        try:
            fds.append(open(dev, "rb", buffering=0))
        except (PermissionError, FileNotFoundError) as e:
            print(f"[ptt] impossible d'ouvrir {dev}: {e}", file=sys.stderr)

    if not fds:
        print("[ptt] aucun clavier accessible! (groupe 'input' requis)", file=sys.stderr)
        sys.exit(1)

    # Vider les événements en buffer (évite de traiter des KEY_DOWN périmés au démarrage)
    for f in fds:
        try:
            os.read(f.fileno(), 65536)
        except (OSError, BlockingIOError):
            pass

    running = True
    last_rescan = time.monotonic()

    def on_signal(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    print("[ptt] en écoute (raw)...")

    while running:
        # Nettoyer fd morts
        dead = [f for f in fds if f.closed]
        for f in dead:
            fds.remove(f)

        # Hotplug
        now_mono = time.monotonic()
        if now_mono - last_rescan > RESCAN_INTERVAL:
            last_rescan = now_mono
            existing = {f.name for f in fds}
            for dev in find_keyboards_raw():
                if dev not in existing:
                    try:
                        fds.append(open(dev, "rb", buffering=0))
                        print(f"[ptt] clavier ajouté: {dev}")
                    except (PermissionError, FileNotFoundError):
                        pass

        if not fds:
            time.sleep(1)
            last_rescan = 0
            continue

        try:
            ready, _, _ = select.select(fds, [], [], 1.0)
        except (ValueError, OSError):
            bad = []
            for f in fds:
                try:
                    select.select([f], [], [], 0)
                except (ValueError, OSError):
                    bad.append(f)
            for f in bad:
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
            if ev_type != EV_KEY:
                continue

            ptt.handle_event(code, value)

    for f in fds:
        try:
            f.close()
        except OSError:
            pass


# ─── Main ───────────────────────────────────────────────────────────

def main():
    global DICTEE_BIN

    mode = "toggle"
    key_dictee = 67   # F9
    key_translate = 0  # désactivé par défaut
    mod_translate = ""  # modificateur traduction (alt, ctrl, shift)
    conf = load_config()

    mode = conf.get("DICTEE_PTT_MODE", mode)

    def _parse_key(raw, label):
        """Parse a key code, keeping the default silently on malformed input.
        dictee.conf can be edited by hand ("F9" instead of "67"); crashing
        the daemon on startup would leave PTT silently dead."""
        try:
            return int(raw)
        except (ValueError, TypeError):
            print(f"[ptt] WARNING: {label}={raw!r} is not a valid keycode, keeping default")
            return None

    if "DICTEE_PTT_KEY" in conf:
        _parsed = _parse_key(conf["DICTEE_PTT_KEY"], "DICTEE_PTT_KEY")
        if _parsed is not None:
            key_dictee = _parsed
    if "DICTEE_PTT_KEY_TRANSLATE" in conf:
        _parsed = _parse_key(conf["DICTEE_PTT_KEY_TRANSLATE"], "DICTEE_PTT_KEY_TRANSLATE")
        if _parsed is not None:
            key_translate = _parsed
    mod_translate = conf.get("DICTEE_PTT_MOD_TRANSLATE", mod_translate)

    for arg in sys.argv[1:]:
        if arg.startswith("--mode="):
            mode = arg.split("=", 1)[1]
        elif arg.startswith("--key="):
            _parsed = _parse_key(arg.split("=", 1)[1], "--key")
            if _parsed is not None:
                key_dictee = _parsed
        elif arg.startswith("--key-translate="):
            _parsed = _parse_key(arg.split("=", 1)[1], "--key-translate")
            if _parsed is not None:
                key_translate = _parsed
        elif arg.startswith("--mod-translate="):
            mod_translate = arg.split("=", 1)[1]
        elif arg == "--help":
            print(__doc__)
            sys.exit(0)

    lock_file = acquire_lock()
    DICTEE_BIN = find_dictee_bin()

    mod_info = f" mod_translate={mod_translate}" if mod_translate else ""
    print(f"[ptt] mode={mode} key={key_dictee} key_translate={key_translate}{mod_info}")
    print(f"[ptt] dictee={DICTEE_BIN}")

    ptt = PttState(mode, key_dictee, key_translate, mod_translate)

    if HAS_EVDEV:
        print("[ptt] backend: evdev (grab + uinput)")
        run_evdev(ptt)
    else:
        print("[ptt] backend: raw (evdev non disponible)", file=sys.stderr)
        run_raw(ptt)

    try:
        os.unlink(OWN_PIDFILE)
    except OSError:
        pass
    lock_file.close()
    print("[ptt] arrêt.")


if __name__ == "__main__":
    main()
