# Port de la fenêtre de réunion en direct dans la 1.3.7 : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer dans la 1.3.7 la fenêtre `dictee-meeting-live` de master telle qu'elle est au commit 03d3ad8, interface complète, traduite, branchée au tray et au plasmoid, packagée sur les quatre cibles, et qui refuse proprement de démarrer tant que les deux options Rust du moteur manquent.

**Architecture:** Le script de master est copié depuis un commit fixe sur `release/1.3` puis modifié en quatre points : amorce gettext, constante `STATE_FILE` pour le fichier d'état partagé (le constructeur de la fenêtre y écrit, les tests doivent pouvoir le détourner), chaînes traduisibles, test de capacité au démarrage. Les consommateurs des deux états qu'il publie (`meeting-ui-open`, `meeting-recording`) sont dictee-ptt.py, dictee-tray.py et le plasmoid. Aucun changement au script bash `dictee`, ni aux binaires Rust.

**Tech Stack:** Python 3 + PyQt6 (fenêtre, tray Qt), GTK3 via gi (tray AppIndicator), QML Plasma 6 (plasmoid), gettext, bash (packaging).

**Spec:** /home/rapha/SOURCES/RAPHA_STT/dictee-137/docs/superpowers/specs/2026-09-19-port-meeting-live-ui-1.3.7.md

## Global Constraints

- Branche : `release/1.3`, worktree /home/rapha/SOURCES/RAPHA_STT/dictee-137 ; source de référence : commit `03d3ad8` de master (dépôt /mnt/ff433a59-fbed-4db3-9e7d-aeb235009f1b/DEV/SOURCES/RAPHA_STT/dictee), fichier `dictee-meeting-live`, 3431 lignes.
- Aucun test ne déclenche une capture réelle : `start_meeting` n'est appelé que quand le test de capacité est certain d'échouer. Aucun test ne touche `/dev/input`, ni la session Wayland (mémoire `no-live-session-input-experiments`).
- Aucun test n'écrit dans le vrai `/dev/shm/.dictee_state`. Le constructeur de `MeetingWindow` y écrit `meeting-ui-open` (ligne 1529 du script de master) : le script reçoit une constante `STATE_FILE` que les tests détournent vers un fichier jetable, et le test refuse de construire la fenêtre tant que la constante n'existe pas. Sur la machine de développement, un état `meeting-ui-open` qui traîne fait passer toutes les touches à travers dictee-ptt.
- Tout test Qt tourne avec `QT_QPA_PLATFORM=offscreen`.
- Langue : msgid anglais, commentaires et messages de commit en anglais. La traduction française des chaînes déjà en français reproduit le texte actuel à l'octet près. Seule exception, voulue et listée en Task 3 : dix-sept diagnostics des workers, aujourd'hui en anglais dans l'interface française, reçoivent une traduction.
- Six msgid existent déjà dans `po/dictee.pot` avec la traduction attendue : `Start` (Démarrer), `Pause` (Pause), `Stop` (Arrêter), `Meeting` (Réunion), `Model:` (Modèle :), `Live meeting` (Réunion en direct). On ne les rajoute pas, `msgfmt --check` refuse les doublons.
- Règle d'or du packaging : le nouveau binaire est ajouté aux quatre cibles dans la même tâche.
- Périmètre exclu : `transcribe-client --json-timestamps`, `diarize-only --stream`, `dictee-stream`, l'état `streaming` du plasmoid, la page wiki.
- Le script n'a pas d'extension : il se charge avec `importlib.machinery.SourceFileLoader`, comme master le fait dans tests/test-meeting-slug.py.
- Pour remplacer une boîte de dialogue Qt dans un test, on remplace le nom de module (`mod.QMessageBox = _Msg`), convention des tests de master, jamais un attribut de la classe Qt.

---

## Structure des fichiers

- Créer : `dictee-meeting-live`
- Créer : `tests/offscreen-check_meeting_live_window.py`
- Créer : `tests/test-meeting-slug.py`
- Créer : `tests/test-ptt-meeting-passthrough.py`
- Créer : `tests/test-meeting-live-wiring.py`
- Modifier : `dictee-ptt.py` (fonction après `read_state()`, bloc lignes 909 à 914)
- Modifier : `dictee-tray.py` (ancrages : `ICON_MAP` 306-316, GTK 593, 757-761, 771, 782-784, Qt 1013, 1083-1084, 1218-1227, 1240-1244, 1258, 1270-1272)
- Modifier : `plasmoid/package/contents/ui/FullRepresentation.qml` (entre les lignes 529 et 530)
- Modifier : `plasmoid/package/contents/ui/main.qml` (lignes 22, 117, 690)
- Modifier : `plasmoid/package/contents/locale/template.pot` et les six `.po` + `.mo`
- Modifier : `po/dictee.pot`, les six `po/*.po` et `po/*.mo`
- Modifier : `build-common.sh` 98 et 120 ; `build-rpm.sh` 77 et 103 ; `build-tar.sh` 164 ; `PKGBUILD` 128 ; `PKGBUILD-cuda` 210 ; `install.sh` 814
- Modifier : `.github/workflows/rust.yml` (job `test-key-capture`)

Les numéros de lignes du script sont ceux du commit 03d3ad8 ; après la Task 1 ils sont décalés d'une vingtaine de lignes. Ceux des autres fichiers sont ceux de `release/1.3` avec le travail non commité du 2026-09-19, tous relus le 2026-09-20. Chaque tâche cite le texte d'ancrage exact, à retrouver par `grep` si un numéro a bougé.

---

### Task 1 : le script arrive sur la 1.3 et se construit hors écran

**Files:**
- Create: `dictee-meeting-live`
- Create: `tests/offscreen-check_meeting_live_window.py`

**Interfaces:**
- Produces: le module chargé expose `MeetingWindow` (QWidget) avec `_state` (str, `"idle"` après construction), `status_label` (QLabel), `cmb_source` (QComboBox), `btn_start`, `btn_stop`, `btn_analyze`, `btn_sound_test` (QPushButton), `chk_include_mic` (QCheckBox), `_title_edit` (QLineEdit), `audio_worker` (`None` au repos) ; la fonction module `_` (gettext) ; la constante module `STATE_FILE` (pathlib.Path).

- [ ] **Step 1 : copier le script depuis le commit fixe**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137
git -C /mnt/ff433a59-fbed-4db3-9e7d-aeb235009f1b/DEV/SOURCES/RAPHA_STT/dictee show 03d3ad8:dictee-meeting-live > dictee-meeting-live
chmod 755 dictee-meeting-live
wc -l dictee-meeting-live
grep -c 'Path("/dev/shm/.dictee_state")' dictee-meeting-live
```
Attendu : `3431 dictee-meeting-live` puis `5`.

- [ ] **Step 2 : écrire le test de construction**

Fichier `tests/offscreen-check_meeting_live_window.py` :

```python
"""The live meeting window on release/1.3: builds, refuses without engines, speaks French.

Loads dictee-meeting-live (no .py extension, hence SourceFileLoader) with a
throwaway HOME so no real dictee.conf or meetings folder is touched. Nothing
here ever starts a capture: start_meeting is only called when the engine
capability check is guaranteed to fail.

Building the window writes "meeting-ui-open" to the shared state file, which
on a developer machine makes dictee-ptt forward every key. The script exposes
that path as STATE_FILE; the test points it into the throwaway HOME and
refuses to build anything if the constant is missing. The real file is read
at start and compared at the end.

Run: QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_meeting_live_window.py
"""
import importlib.machinery
import importlib.util
import os
import pathlib
import shutil
import stat
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="dictee-meeting-ui-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ["XDG_RUNTIME_DIR"] = _HOME
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LANGUAGE"] = "C"
os.environ["LC_ALL"] = "C"
os.environ["LANG"] = "C"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "dictee-meeting-live")

REAL_STATE = "/dev/shm/.dictee_state"


def read_real_state():
    try:
        with open(REAL_STATE) as f:
            return f.read()
    except OSError:
        return None


_real_state_before = read_real_state()

# The script looks for its catalog in ~/.local/share/locale first (its own
# LOCALE_DIRS order), so the tracked po/fr.mo dropped there is what the
# French rendering check below reads: no msgfmt, no system install involved.
_MO_DIR = os.path.join(_HOME, ".local", "share", "locale", "fr", "LC_MESSAGES")
os.makedirs(_MO_DIR)
shutil.copy(os.path.join(ROOT, "po", "fr.mo"), os.path.join(_MO_DIR, "dictee.mo"))


def load():
    loader = importlib.machinery.SourceFileLoader("meeting_live", SCRIPT)
    spec = importlib.util.spec_from_loader("meeting_live", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["meeting_live"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = load()
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
failures = []


def check(label, got, want):
    if got == want:
        print(f"PASS {label}")
    else:
        failures.append(label)
        print(f"FAIL {label}: got {got!r}, expected {want!r}")


def finish():
    check("real /dev/shm/.dictee_state untouched", read_real_state(), _real_state_before)
    print()
    if failures:
        print(f"{len(failures)} FAILED: " + ", ".join(failures))
        sys.exit(1)
    print("OK")
    sys.exit(0)


# --- 1. construction ---------------------------------------------------------

check("module has a gettext _()", callable(getattr(mod, "_", None)), True)
check("script exposes STATE_FILE", hasattr(mod, "STATE_FILE"), True)
if not hasattr(mod, "STATE_FILE"):
    print("refusing to build the window: it would write the real state file")
    finish()
mod.STATE_FILE = pathlib.Path(_HOME) / "dictee_state"

win = mod.MeetingWindow()
check("window starts idle", win._state, "idle")
check("state went to the sandbox file", mod.STATE_FILE.read_text(), "meeting-ui-open\n")
check("no capture worker at rest", win.audio_worker, None)
for name in ("status_label", "cmb_source", "btn_start", "btn_stop", "btn_analyze",
             "btn_sound_test", "chk_include_mic", "_title_edit"):
    check(f"widget {name} exists", hasattr(win, name), True)
check("start button enabled at rest", win.btn_start.isEnabled(), True)
check("stop button disabled at rest", win.btn_stop.isEnabled(), False)
check("title is prefilled", bool(win._title_edit.text().strip()), True)

finish()
```

`win.btn_stop.isEnabled()` vaut `False` au repos parce que la table `cfg` de `_set_state` donne `"idle": ("▶", "Démarrer", True, False, False)`, lue au commit 03d3ad8. Les tâches 2 et 3 insèrent leurs sections avant l'appel final `finish()`.

- [ ] **Step 3 : lancer, vérifier que le test s'arrête avant de construire**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_meeting_live_window.py 2>&1 | grep -E '^(FAIL|OK|[0-9]+ FAILED|refusing)'
```
Attendu, dans l'ordre : `FAIL module has a gettext _()`, `FAIL script exposes STATE_FILE`, `refusing to build the window: it would write the real state file`, `2 FAILED`. Puis `cat /dev/shm/.dictee_state` montre le même contenu qu'avant.

- [ ] **Step 4 : amorce gettext et constante d'état**

Dans `dictee-meeting-live`, le bloc d'imports PyQt6 se ferme par `)` seul à la ligne 38, suivi de deux lignes vides puis, ligne 41, `# ---------------------------------------------------------------------------`. Insérer entre la ligne 38 et cette ligne 41 (les quinze premières lignes sont la copie de dictee-transcribe.py lignes 174 à 190) :

```python
import gettext

LOCALE_DIRS = [
    # User-space first so dev / hot translation updates win over the
    # stale .mo shipped by the system package — avoids needing sudo
    # to refresh translations during iteration.
    os.path.expanduser("~/.local/share/locale"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "share", "locale"),
    "/usr/local/share/locale",
    "/usr/share/locale",
]

for _d in LOCALE_DIRS:
    if os.path.isfile(os.path.join(_d, "fr", "LC_MESSAGES", "dictee.mo")):
        gettext.bindtextdomain("dictee", _d)
        break

gettext.textdomain("dictee")
_ = gettext.gettext

# Shared state file read by dictee-ptt, the tray and the plasmoid. A module
# constant so tests can point it elsewhere: building the window writes here.
STATE_FILE = Path("/dev/shm/.dictee_state")
```

`os` est importé à la ligne 14, `Path` à la ligne 25.

- [ ] **Step 5 : les cinq écritures passent par la constante**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137
sed -i 's|Path("/dev/shm/.dictee_state").write_text(|STATE_FILE.write_text(|' dictee-meeting-live
grep -c 'Path("/dev/shm/.dictee_state")' dictee-meeting-live; grep -c 'STATE_FILE.write_text(' dictee-meeting-live
```
Attendu : `0` puis `5`. Les cinq sites sont le constructeur (`meeting-ui-open`), `start_meeting` (`meeting-recording`), `stop_meeting`, `_on_capture_failed` et `closeEvent` (`idle`).

- [ ] **Step 6 : relancer**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_meeting_live_window.py 2>&1 | grep -E '^(FAIL|OK|[0-9]+ FAILED)'
```
Attendu : `OK` seul.

- [ ] **Step 7 : commit**

```bash
git add dictee-meeting-live tests/offscreen-check_meeting_live_window.py
git commit -m "feat(meeting-live): bring the live meeting window from master, UI only

Same script as master commit 03d3ad8, plus the gettext bootstrap every other
dictee window has, and the shared state path as a STATE_FILE constant so
tests can build the window without touching /dev/shm. The engine seams it
drives (transcribe-client --json-timestamps, diarize-only --stream) do not
exist on this branch yet; the next commits make it refuse to start cleanly
until they do."
```

---

### Task 2 : refuser proprement de démarrer sans moteur

**Files:**
- Modify: `dictee-meeting-live`
- Modify: `tests/offscreen-check_meeting_live_window.py`

**Interfaces:**
- Produces: `missing_live_engine_features() -> list[str]`, fonction module ; vide quand tout est là.
- Consumes: `win.status_label`, `win._state`, le nom de module `QMessageBox`, `_`.

- [ ] **Step 1 : ajouter les tests du refus et de la sonde**

Dans `tests/offscreen-check_meeting_live_window.py`, avant l'appel final `finish()` :

```python
# --- 2. engine capability gate -----------------------------------------------

def fake_bin_dir(with_markers):
    """A PATH entry holding transcribe-client and diarize-only stand-ins whose
    --help either documents the streaming flags (master build) or not (1.3)."""
    d = tempfile.mkdtemp(prefix="dictee-fake-engines-")
    help_client = "transcribe-client <file> --json-timestamps  JSON output" if with_markers \
        else "transcribe-client <file>  plain output"
    help_diar = "diarize-only --stream [OPTIONS]" if with_markers \
        else "diarize-only <file> [OPTIONS]"
    for name, text in (("transcribe-client", help_client), ("diarize-only", help_diar)):
        p = os.path.join(d, name)
        with open(p, "w") as f:
            f.write("#!/bin/sh\nprintf '%s\\n' \"" + text + "\" >&2\nexit 1\n")
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return d


class _Msg:
    """Stand-in for QMessageBox: records instead of blocking on a dialog."""
    calls = []

    @staticmethod
    def critical(*a, **k):
        _Msg.calls.append(a)


saved_path = os.environ["PATH"]
saved_box = mod.QMessageBox
mod.QMessageBox = _Msg

os.environ["PATH"] = fake_bin_dir(with_markers=False)
missing = mod.missing_live_engine_features()
check("1.3 engines: both features reported missing", len(missing), 2)

win.start_meeting()
check("start refused: state still idle", win._state, "idle")
check("start refused: no capture worker spawned", win.audio_worker, None)
check("start refused: one error box", len(_Msg.calls), 1)
check("start refused: status names the missing engine",
      "not available" in win.status_label.text(), True)
check("start refused: sandbox state untouched", mod.STATE_FILE.read_text(), "meeting-ui-open\n")

os.environ["PATH"] = fake_bin_dir(with_markers=True)
check("master engines: nothing missing", mod.missing_live_engine_features(), [])

os.environ["PATH"] = tempfile.mkdtemp(prefix="dictee-no-engines-")
check("no engines at all: both reported as not installed",
      all("not installed" in m for m in mod.missing_live_engine_features()), True)

os.environ["PATH"] = saved_path
mod.QMessageBox = saved_box
```

Aucun `start_meeting` n'est appelé avec les faux moteurs « master » : la fenêtre lancerait `pw-record`.

- [ ] **Step 2 : lancer, vérifier l'échec attendu**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_meeting_live_window.py 2>&1 | grep -E 'AttributeError' | head -1
```
Attendu : `AttributeError: module 'meeting_live' has no attribute 'missing_live_engine_features'`

- [ ] **Step 3 : écrire la sonde**

Dans `dictee-meeting-live`, juste avant la ligne `def _acquire_singleton_lock():` (elle suit une ligne `# ----…` et une ligne vide) :

```python
# The live pipeline drives `transcribe-client <chunk> --json-timestamps` and
# `diarize-only --stream`. Both flags document themselves in --help, and a
# build without them prints neither, so --help is the capability probe. On
# release/1.3 the Rust side does not have them yet: the window must say so
# instead of spawning workers that die on an unknown flag.
LIVE_ENGINE_CHECKS = (
    ("transcribe-client", "json-timestamps"),
    ("diarize-only", "--stream"),
)


def missing_live_engine_features():
    """Engine features this window needs and this install lacks, as labels.

    Empty list when everything is there. Each label names the binary and
    either the flag it does not document or why it could not be asked.
    """
    missing = []
    for binary, marker in LIVE_ENGINE_CHECKS:
        if shutil.which(binary) is None:
            missing.append(_("{bin} (not installed)").format(bin=binary))
            continue
        try:
            proc = subprocess.run([binary, "--help"], capture_output=True,
                                  text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            missing.append(_("{bin} (cannot run --help)").format(bin=binary))
            continue
        if marker not in proc.stdout + proc.stderr:
            missing.append(f"{binary} {marker}")
    return missing
```

`shutil` (ligne 17) et `subprocess` (ligne 24) sont déjà importés ; `_` vient de la Task 1 et se trouve plus haut dans le fichier.

- [ ] **Step 4 : brancher le refus au début de `start_meeting`**

Le corps de `MeetingWindow.start_meeting` (ligne 2511 au commit 03d3ad8) commence par :

```python
        # Re-entrancy guard: never start a second capture over a live one
        # (would orphan the previous worker/chunker/diarizer/executor).
        if self._state in ("recording", "paused") or self.audio_worker:
            return
```

Insérer immédiatement après ce `return`, avant le commentaire `# Guard rail: an "app:" source needs the dictee-app-capture helper.` :

```python
        # This branch ships the window ahead of its engine: refuse with the
        # reason rather than letting the workers fail on an unknown flag.
        missing = missing_live_engine_features()
        if missing:
            msg = _("Live meeting engine not available in this version: {what}").format(
                what=", ".join(missing))
            self.status_label.setText(msg)
            QMessageBox.critical(self, _("Live meeting"), msg)
            return
```

- [ ] **Step 5 : relancer**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_meeting_live_window.py 2>&1 | grep -E '^(FAIL|OK|[0-9]+ FAILED)'
```
Attendu : `OK` seul.

- [ ] **Step 6 : vérifier la sonde contre les vrais binaires de la 1.3**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137
PATH="$PWD/target/glibc236/release:$PATH" QT_QPA_PLATFORM=offscreen python3 - <<'EOF'
import importlib.machinery, importlib.util
l = importlib.machinery.SourceFileLoader("ml", "dictee-meeting-live")
s = importlib.util.spec_from_loader("ml", l); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
print(m.missing_live_engine_features())
EOF
```
Attendu : `['transcribe-client json-timestamps', 'diarize-only --stream']`. Les deux textes d'aide de la 1.3 ne contiennent ni l'un ni l'autre (vérifié le 2026-09-19 : zéro occurrence chacun), ceux de master les contiennent (transcribe_client.rs:83, diarize_only.rs:38 et 46). Ce script ne construit pas la fenêtre, donc n'écrit aucun état.

- [ ] **Step 7 : commit**

```bash
git add dictee-meeting-live tests/offscreen-check_meeting_live_window.py
git commit -m "feat(meeting-live): refuse to start until the engine grows its streaming flags

The window drives transcribe-client --json-timestamps and diarize-only
--stream, neither of which exists on release/1.3. Probe both through
--help before starting and say which one is missing, so the rest of the
window stays usable and the day the Rust side lands nothing here changes."
```

---

### Task 3 : passer l'interface en gettext

**Files:**
- Modify: `dictee-meeting-live`
- Modify: `po/dictee.pot`, `po/fr.po`, `po/de.po`, `po/es.po`, `po/it.po`, `po/pt.po`, `po/uk.po`, et les `.mo`
- Modify: `tests/offscreen-check_meeting_live_window.py`

**Interfaces:**
- Consumes: `_` et `STATE_FILE` posés en Task 1.
- Produces: plus aucune chaîne visible en dur dans le script ; le vérificateur par tokens de l'étape 1 fait foi.

Le premier inventaire, fait par motif de constructeur de widget, ne voyait que 37 chaînes. Le balayage par tokens du 2026-09-20, lancé sans aucune liste blanche, remonte 142 littéraux sur 135 lignes, et tout ce qui n'est pas dans la table de l'étape 3 a été lu un par un : feuilles de style, parsing de `pactl`, `print` vers stderr, aide argparse, noms de moteurs, en-tête HTTP, méthode D-Bus, format du fichier transcript. La liste blanche du vérificateur vient de ces lignes-là, pas d'une intuition.

Le vérificateur a un angle mort connu : un mot seul en minuscules sans accent n'est pas reconnu comme de la prose. Il en existe un dans ce script, `"diarisation"` (ligne 2784), traité explicitement dans la table et par un contrôle textuel dédié.

- [ ] **Step 1 : le vérificateur par tokens, le rendu français, les placeholders**

Dans `tests/offscreen-check_meeting_live_window.py`, avant l'appel final `finish()` :

```python
# --- 3. no user-facing string left outside _() -------------------------------

import gettext  # noqa: E402
import io  # noqa: E402
import re  # noqa: E402
import tokenize  # noqa: E402

# Literals that look like prose but are never shown to the user, listed from
# a scan of the script with no allowlist at all: stylesheet fragments, engine
# names in the model combo, an HTTP header, the D-Bus inhibit methods, a
# pactl line marker, HTML markup of the preview. Adding to this list is
# allowed only for a string nobody ever reads on screen, and the commit
# message must say which one and why.
NON_UI = re.compile(
    r"^(font-|color:|border|palette\(|stop:|qlineargradient|QGroupBox|QToolButton|QProgressBar|[;{}<]|"
    r"on source #|Content-Type$|(Un)?Inhibit$|"
    r"Parakeet (int8|fp32)$|faster-whisper \($|Whisper-Rust \($|Nemotron$|Whisper$|Kyutai \(fr/en, GPU\)$)")
# Whole lines that are not UI: stderr prints, stylesheets, argparse, file
# writes (the transcript format is parsed back later), pactl output parsing.
SKIP_LINE = re.compile(
    r"print\(|StyleSheet|add_argument\(|ArgumentParser\(|\.write\(|"
    r"re\.search\(|\.startswith\(|== '")


def bare_ui_strings(path):
    """(line, text) for every prose literal not inside a _() call."""
    src = open(path, encoding="utf-8").read()
    lines = src.splitlines()
    found, depth, gettext_depth, prev = [], 0, None, None
    fstring_middle = getattr(tokenize, "FSTRING_MIDDLE", None)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.OP:
            if tok.string == "(":
                depth += 1
                if prev is not None and prev.type == tokenize.NAME and prev.string == "_":
                    gettext_depth = depth
            elif tok.string == ")":
                if gettext_depth == depth:
                    gettext_depth = None
                depth -= 1
        elif tok.type == tokenize.STRING or (fstring_middle and tok.type == fstring_middle):
            line = lines[tok.start[0] - 1].strip()
            body = tok.string if tok.type != tokenize.STRING else tok.string.lstrip("rbfuRBFU").strip("\"'")
            body = body.strip()
            prose = (len(body) >= 4 and re.search(r"[a-zà-ÿ]", body)
                     and (" " in body or "…" in body or body[0].isupper()
                          or re.search(r"[àâéèêîôùûç]", body)))
            if (prose and gettext_depth is None
                    and not line.startswith(("#", '"""', "'''"))
                    and not SKIP_LINE.search(line) and not NON_UI.search(body)):
                found.append((tok.start[0], body[:50]))
        if tok.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT):
            prev = tok
    return found


check("no user-facing string outside _()", bare_ui_strings(SCRIPT), [])
# Blind spot of the scan above: a lone lowercase word. The loading status
# builds "diarisation + Whisper" from such a word; pin its catalog form.
check("loading status pulls 'diarization' from the catalog",
      '[_("diarization")]' in open(SCRIPT, encoding="utf-8").read(), True)

# --- 4. French rendering through the tracked catalog -------------------------

import subprocess  # noqa: E402

fr = subprocess.run(
    [sys.executable, "-c",
     "import os, sys, pathlib, importlib.machinery, importlib.util\n"
     "os.environ['LANGUAGE'] = 'fr'\n"
     "os.environ['LC_ALL'] = 'C.UTF-8'\n"
     "os.environ['LANG'] = 'C.UTF-8'\n"
     "os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
     f"l = importlib.machinery.SourceFileLoader('ml', {SCRIPT!r})\n"
     "s = importlib.util.spec_from_loader('ml', l); m = importlib.util.module_from_spec(s)\n"
     "s.loader.exec_module(m)\n"
     "m.STATE_FILE = pathlib.Path(os.environ['HOME']) / 'dictee_state_fr'\n"
     "from PyQt6.QtWidgets import QApplication; a = QApplication([])\n"
     "w = m.MeetingWindow(); print(w.status_label.text()); print(w.btn_sound_test.text())"],
    capture_output=True, text=True, timeout=60, env=os.environ)
check("status label renders in French", fr.stdout.splitlines()[:1], ["Prêt à enregistrer"])
check("sound test button renders in French", fr.stdout.splitlines()[1:2], ["Tester le son…"])

# msgfmt 0.21 does not validate python-brace-format placeholders: a French
# msgstr missing a {name} would raise KeyError at .format() time, in French
# only. The whole catalog passes this today (125 brace msgids, 0 mismatches).
catalog = gettext.GNUTranslations(open(os.path.join(ROOT, "po", "fr.mo"), "rb"))._catalog
bad = [k for k, v in catalog.items()
       if isinstance(k, str) and "{" in k and v
       and set(re.findall(r"\{\w+\}", k)) != set(re.findall(r"\{\w+\}", v))]
check("French catalog keeps every {placeholder}", bad, [])
```

Le sous-processus hérite de `HOME=_HOME`, où `po/fr.mo` a été copié au démarrage du test : c'est la première entrée de `LOCALE_DIRS` du script, donc la liaison se fait sur ce fichier et jamais sur un `.mo` installé sur la machine. Il détourne aussi `STATE_FILE` avant de construire.

- [ ] **Step 2 : lancer, vérifier les échecs**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_meeting_live_window.py 2>&1 | grep -E '^FAIL' | cut -c1-120
```
Attendu : `FAIL no user-facing string outside _(): got [(…), …]` avec 142 couples (compte obtenu le 2026-09-20 sur le script de master avec exactement ce vérificateur ; les ajouts des tâches 1 et 2 n'en introduisent aucun), `FAIL loading status pulls 'diarization' from the catalog`, puis les deux échecs de rendu français. Le contrôle des placeholders passe déjà.

- [ ] **Step 3 : envelopper chaque chaîne, la table est le contrat**

Numéros du commit 03d3ad8, texte d'ancrage à retrouver par `grep`. Le msgstr français est le texte actuel à l'octet près, sauf dans la dernière table (diagnostics des workers, en anglais aujourd'hui). Pour les concaténations, les morceaux sont joints tels quels. Les msgid marqués « existe » sont déjà dans le catalogue, avec la traduction indiquée : rien à ajouter au `.po`.

Fenêtre de test du son (`SoundTestDialog`) :

| Ligne | Aujourd'hui | Remplacement | msgstr fr |
|---|---|---|---|
| 1323 | `setWindowTitle("Test du son")` | `setWindowTitle(_("Sound test"))` | Test du son |
| 1337 | `QLabel(\n "Enregistrez un court essai, puis réécoutez-le.")` | `QLabel(_("Record a short test, then play it back."))` | Enregistrez un court essai, puis réécoutez-le. |
| 1342, 1398, 1431 | `"● Enregistrer"` | `_("● Record")` | ● Enregistrer |
| 1344 | `setToolTip(\n "Capture avec la source et les niveaux de la réunion")` | `setToolTip(_("Captures with the meeting's source and levels"))` | Capture avec la source et les niveaux de la réunion |
| 1347, 1420 | `"▶ Réécouter"` | `_("▶ Play back")` | ▶ Réécouter |
| 1438 | `self.btn_play.text() != "▶ Réécouter"` | `self.btn_play.text() != _("▶ Play back")` | (même msgid) |
| 1351 | `QPushButton("Fermer")` | `QPushButton(_("Close"))` | Fermer |
| 1370 | `"Normalisation…"` | `_("Normalising…")` | Normalisation… |
| 1391 | `"■ Arrêter"` | `_("■ Stop")` | ■ Arrêter |
| 1393 | `"Essai en cours — 0 s"` | `_("Test in progress, {s} s").format(s=0)` | Essai en cours — {s} s |
| 1427 | `f"Essai en cours — {int(self._elapsed)} s"` | `_("Test in progress, {s} s").format(s=int(self._elapsed))` | (même msgid que 1393) |
| 1399 | `f"Échec de la capture : {msg}"` | `_("Capture failed: {msg}").format(msg=msg)` | Échec de la capture : {msg} |
| 1411 | `"■ Arrêter la lecture"` | `_("■ Stop playback")` | ■ Arrêter la lecture |
| 1412 | `"Lecture de l'essai…"` | `_("Playing the test…")` | Lecture de l'essai… |
| 1414 | `"paplay introuvable."` | `_("paplay not found.")` | paplay introuvable. |
| 1435, 1441 | `"Prêt — réécoutez l'essai, ou refaites-en un."` | `_("Ready, play the test back or record another.")` | Prêt — réécoutez l'essai, ou refaites-en un. |

La ligne 1438 est la raison d'être de la Task 3 côté logique : sans elle, dans une autre langue le bouton ne repasserait jamais en état « lecture terminée ».

Fenêtre principale, état et statut :

| Ligne | Aujourd'hui | Remplacement | msgstr fr |
|---|---|---|---|
| 1484 | `setWindowTitle("Réunion live — capture")` | `setWindowTitle(_("Live meeting, capture"))` | Réunion live — capture |
| 1558, 1561 | `"Démarrer"` dans `cfg` | `_("Start")` | existe : Démarrer |
| 1559 | `"Pause"` dans `cfg` | `_("Pause")` | existe : Pause |
| 1560 | `"Reprendre"` dans `cfg` | `_("Resume")` | Reprendre |
| 1581 | `"idle": "Prêt à enregistrer"` | `"idle": _("Ready to record")` | Prêt à enregistrer |
| 1582 | `"recording": "Enregistrement en cours"` | `"recording": _("Recording")` | Enregistrement en cours |
| 1583 | `"paused": "Enregistrement en pause"` | `"paused": _("Recording paused")` | Enregistrement en pause |
| 1584 | `"stopped": "Enregistrement arrêté"` | `"stopped": _("Recording stopped")` | Enregistrement arrêté |
| 1640 | `QLabel("Prêt à enregistrer")` | `QLabel(_("Ready to record"))` | (même msgid que 1581) |
| 1656 | `QLabel("Titre :")` | `QLabel(_("Title:"))` | Titre : |
| 1658 | `"Titre de la réunion (optionnel)"` | `_("Meeting title (optional)")` | Titre de la réunion (optionnel) |
| 1659 | `"Réunion " + datetime…` | `_("Meeting") + " " + datetime…` | existe : Réunion |
| 1665 | `QLabel("Source :")` | `QLabel(_("Source:"))` | Source : |
| 1674 | `QLabel("Modèle :")` | `QLabel(_("Model:"))` | existe : Modèle : |
| 1697-1698 | infobulle du modèle | `setToolTip(_("ASR model for this meeting. Whisper sizes follow the choice made in dictee-setup."))` | Modèle ASR pour cette réunion. Les tailles Whisper suivent le choix fait dans dictee-setup. |
| 1717 | `QLabel("Diarisation :")` | `QLabel(_("Diarization:"))` | Diarisation : |
| 1722 | `("Auto", "auto")` | `(_("Auto"), "auto")` | Auto |
| 1723 | `("Multi-locuteurs (sans limite)", "multi")` | `(_("Multi-speaker (no limit)"), "multi")` | Multi-locuteurs (sans limite) |
| 1724 | `("Sortformer (4 max)", "sortformer")` | `(_("Sortformer (4 max)"), "sortformer")` | Sortformer (4 max) |
| 1725 | `("MOSS (analyse finale seule)", "moss")` | `(_("MOSS (final analysis only)"), "moss")` | MOSS (analyse finale seule) |
| 1734-1739 | infobulle diarisation | un seul `_()` multiligne, texte ci-dessous | texte ci-dessous |
| 1763-1766 | infobulle sensibilité | un seul `_()` multiligne, texte ci-dessous | texte ci-dessous |
| 1781 | `QCheckBox("Ajouter le micro")` | `QCheckBox(_("Add the microphone"))` | Ajouter le micro |
| 1788 | `setToolTip("Démarrer")` | `setToolTip(_("Start"))` | existe : Démarrer |
| 1795 | `setToolTip("Arrêter")` | `setToolTip(_("Stop"))` | existe : Arrêter |
| 1803 | `setToolTip("Démarrer l'analyse")` | `setToolTip(_("Start the analysis"))` | Démarrer l'analyse |
| 1810 | `QPushButton("Tester le son…")` | `QPushButton(_("Test the sound…"))` | Tester le son… |
| 1812-1813 | infobulle test du son | `setToolTip(_("Record a short test with the current settings and play it back, before starting the real meeting."))` | Enregistrer un court essai avec les réglages actuels et le réécouter, avant de lancer la vraie réunion. |
| 1823 | `QPushButton("Analyser un autre fichier…")` | `QPushButton(_("Analyze another file…"))` | Analyser un autre fichier… |
| 1825-1827 | infobulle analyse | un seul `_()` multiligne, texte ci-dessous | texte ci-dessous |
| 1835 | `QGroupBox("Niveaux")` | `QGroupBox(_("Levels"))` | Niveaux |
| 1881 | `setText("Aperçu en direct")` | `setText(_("Live preview"))` | Aperçu en direct |
| 1928 | `_ind_row("Chunk 1", …)` | `_ind_row(_("Chunk {n}").format(n=1), …)` | Chunk {n} |
| 1929 | `_ind_row("Contexte", …)` | `_ind_row(_("Context"), …)` | Contexte |
| 1957 | `QGroupBox("Speakers détectés")` | `QGroupBox(_("Detected speakers"))` | Speakers détectés |
| 2056 | `addItem("🎙 Mix micro + audio système", "mix")` | `addItem(_("🎙 Mic + system audio mix"), "mix")` | 🎙 Mix micro + audio système |
| 2422 | `setText("Modèle (aperçu) :" if _moss else "Modèle :")` | `setText(_("Model (preview):") if _moss else _("Model:"))` | Modèle (aperçu) : / existe : Modèle : |
| 2424-2428 | deux infobulles selon `_moss` | `_("ASR model of the LIVE PREVIEW only: MOSS transcribes the final file with its own engine.") if _moss else _("ASR model for this meeting. Whisper sizes follow the choice made in dictee-setup.")` | Modèle ASR de l'APERÇU LIVE uniquement : MOSS transcrit le fichier final avec son propre moteur. / (même msgid que 1697) |
| 2504-2505 | texte de `notify-send` | `_("All desktops option not yet supported on Wayland, window will only show on current desktop.")` | Option « tous les bureaux » pas encore prise en charge sous Wayland, la fenêtre n'apparaîtra que sur le bureau courant. |
| 2527 | `"Capture d'application indisponible"` | `_("Application capture unavailable")` | Capture d'application indisponible |
| 2528-2531 | corps de la boîte | un seul `_()` multiligne, texte ci-dessous | texte ci-dessous |
| 2542 | `"Réunion " + datetime…` | `_("Meeting") + " " + datetime…` | existe : Réunion |
| 2620-2621 | `"Aucun modèle Whisper-Rust installé " "(voir dictee-setup) — live en Parakeet"` | `_("No Whisper-Rust model installed (see dictee-setup), live falls back to Parakeet")` | Aucun modèle Whisper-Rust installé (voir dictee-setup) — live en Parakeet |
| 2628-2629, 2651-2652 | `"transcribe-daemon-whisper-rust " "introuvable — live en Parakeet"` | `_("transcribe-daemon-whisper-rust not found, live falls back to Parakeet")` | transcribe-daemon-whisper-rust introuvable — live en Parakeet |
| 2672 | `"transcribe-daemon-whisper introuvable — live en Parakeet"` | `_("transcribe-daemon-whisper not found, live falls back to Parakeet")` | transcribe-daemon-whisper introuvable — live en Parakeet |
| 2677, 2701 | `"transcribe-daemon introuvable — live en Parakeet"` | `_("transcribe-daemon not found, live falls back to Parakeet")` | transcribe-daemon introuvable — live en Parakeet |
| 2707, 2727 | `"transcribe-daemon-kyutai introuvable — live en Parakeet"` | `_("transcribe-daemon-kyutai not found, live falls back to Parakeet")` | transcribe-daemon-kyutai introuvable — live en Parakeet |
| 2784 | `_loading = ["diarisation"]` | `_loading = [_("diarization")]` | diarisation |
| 2786 | `"Nemotron" if self._nemotron_live else "Whisper"` | inchangé, noms de moteurs (liste blanche) | |
| 2787 | `"⏳ Chargement du modèle : " + " + ".join(_loading) + "…"` | `_("⏳ Loading model: {what}…").format(what=" + ".join(_loading))` | ⏳ Chargement du modèle : {what}… |
| 2792 | `"Enregistrement en cours — modèles prêts"` | `_("Recording, models ready")` | Enregistrement en cours — modèles prêts |
| 2884 | `f"⚙ Chunk {chunk_id + 1} : transcription + diarisation…"` | `_("⚙ Chunk {n}: transcription + diarization…").format(n=chunk_id + 1)` | ⚙ Chunk {n} : transcription + diarisation… |
| 2899 | `f"✓ Chunk {chunk_id + 1} ajouté à l'aperçu"` | `_("✓ Chunk {n} added to the preview").format(n=chunk_id + 1)` | ✓ Chunk {n} ajouté à l'aperçu |
| 2908 | `label_text = f"Speaker {spk_id}"` | `label_text = _("Speaker {n}").format(n=spk_id)` | Speaker {n} |
| 2910 | `"(nommer ce locuteur…)"` | `_("(name this speaker…)")` | (nommer ce locuteur…) |
| 2930 | `f"⚠ Chunk {chunk_id + 1} : {msg}"` | `_("⚠ Chunk {n}: {msg}").format(n=chunk_id + 1, msg=msg)` | ⚠ Chunk {n} : {msg} |
| 2948 | `self._speaker_name_map.get(spk_id, f"Speaker {spk_id}")` | `self._speaker_name_map.get(spk_id, _("Speaker {n}").format(n=spk_id))` | (même msgid que 2908) |
| 3088 | `"Finalisation du dernier segment…"` | `_("Finalising the last segment…")` | Finalisation du dernier segment… |
| 3183 | `f"Enregistrement trop court ({self.elapsed_seconds}s)"` | `_("Recording too short ({s}s)").format(s=self.elapsed_seconds)` | Enregistrement trop court ({s}s) |
| 3202 | `"Réunion en cours d'enregistrement"` (raison D-Bus `Inhibit`) | `_("Meeting being recorded")` | Réunion en cours d'enregistrement |
| 3229 | `"Ouverture de l'analyse…"` | `_("Opening the analysis…")` | Ouverture de l'analyse… |
| 3264, 3291 | `"Erreur : dictee-transcribe introuvable"` | `_("Error: dictee-transcribe not found")` | Erreur : dictee-transcribe introuvable |
| 3318 | `f"Chunk {ch.chunk_id + 1}"` | `_("Chunk {n}").format(n=ch.chunk_id + 1)` | (même msgid que 1928) |
| 3339, 3349 | `f"Erreur : {msg}"` | `_("Error: {msg}").format(msg=msg)` | Erreur : {msg} |

`Speaker {n}` garde « Speaker » en français : c'est ce que l'interface affiche aujourd'hui, à côté du groupe « Speakers détectés ». La ligne 2892 (`f.write(… Speaker {spk}: …)`) est le format du fichier transcript, relu plus tard : elle ne bouge pas.

Workers (le `_` du module est visible dans les classes définies après lui). Les cinq premières lignes sont en français aujourd'hui ; les dix-sept suivantes sont en anglais dans l'interface française, et reçoivent une traduction. C'est la seule entorse à « à l'octet près », décidée parce que ces messages s'affichent dans la barre d'état (`_on_error_msg`, `_on_capture_failed`, `_on_chunk_error`) et que dictee-transcribe.py traduit les siens :

| Ligne | Aujourd'hui | Remplacement | msgstr fr |
|---|---|---|---|
| 377-378 | `f"Capture de « {name} » impossible : composant " "dictee-app-capture introuvable"` | `_("Cannot capture « {name} »: dictee-app-capture component not found").format(name=name)` | Capture de « {name} » impossible : composant dictee-app-capture introuvable |
| 399-400 | `f"Capture de « {name} » impossible : la capture d'application " "n'a pas démarré"` | `_("Cannot capture « {name} »: the application capture did not start").format(name=name)` | Capture de « {name} » impossible : la capture d'application n'a pas démarré |
| 745 | `f"socket transcribe-daemon absente ({self.daemon_socket})"` | `_("transcribe-daemon socket missing ({sock})").format(sock=self.daemon_socket)` | socket transcribe-daemon absente ({sock}) |
| 786 | `"daemon Whisper live pas encore prêt (chargement du modèle)"` | `_("Whisper live daemon not ready yet (model loading)")` | daemon Whisper live pas encore prêt (chargement du modèle) |
| 822 | `"daemon Nemotron live pas encore prêt (chargement du modèle)"` | `_("Nemotron live daemon not ready yet (model loading)")` | daemon Nemotron live pas encore prêt (chargement du modèle) |
| 298 | `f"audio source setup failed: {exc}"` | `_("audio source setup failed: {err}").format(err=exc)` | échec de la configuration de la source audio : {err} |
| 327 | `f"pw-record exit {rc}: {err}"` | `_("pw-record exit {rc}: {err}").format(rc=rc, err=err)` | pw-record terminé avec le code {rc} : {err} |
| 329 | `"pw-record not found. Is PipeWire installed?"` | `_("pw-record not found. Is PipeWire installed?")` | pw-record introuvable. PipeWire est-il installé ? |
| 658 | `f"ffmpeg extract failed (chunk {self.chunk_id})"` | `_("ffmpeg extract failed (chunk {n})").format(n=self.chunk_id)` | échec de l'extraction ffmpeg (chunk {n}) |
| 759 | `f"transcribe-client exit {proc.returncode}: {proc.stderr.strip()}"` | `_("transcribe-client exit {rc}: {err}").format(rc=proc.returncode, err=proc.stderr.strip())` | transcribe-client terminé avec le code {rc} : {err} |
| 766 | `"transcribe-client timeout (>20 s)"` | `_("transcribe-client timeout (>20 s)")` | transcribe-client : délai dépassé (>20 s) |
| 768 | `f"JSON parse error: {e}"` | `_("JSON parse error: {err}").format(err=e)` | erreur d'analyse JSON : {err} |
| 803, 807 | `f"Whisper live: {text}"`, `f"Whisper live: {e}"` | `_("Whisper live: {err}").format(err=text)`, `.format(err=e)` | Whisper live : {err} |
| 866, 876 | `f"Nemotron live: {text}"`, `f"Nemotron live: {e}"` | `_("Nemotron live: {err}").format(err=text)`, `.format(err=e)` | Nemotron live : {err} |
| 969 | `f"{self.cmd[0]} binary not found. Diarization feature built?"` | `_("{bin} binary not found. Diarization feature built?").format(bin=self.cmd[0])` | binaire {bin} introuvable. Compilé avec la diarisation ? |
| 981 | `f"{self.label} stderr EOF before ready"` | `_("{what} stderr EOF before ready").format(what=self.label)` | {what} : fin de stderr avant le signal ready |
| 987 | `f"{self.label} startup timeout (30s)"` | `_("{what} startup timeout (30s)").format(what=self.label)` | {what} : délai de démarrage dépassé (30 s) |
| 997 | `"DiarizationWorker not started"` | `_("DiarizationWorker not started")` | DiarizationWorker non démarré |
| 1000 | `f"{self.cmd[0]} exited with code {self.proc.returncode}"` | `_("{bin} exited with code {rc}").format(bin=self.cmd[0], rc=self.proc.returncode)` | {bin} terminé avec le code {rc} |
| 1008 | `f"{self.cmd[0]} stdin pipe broken"` | `_("{bin} stdin pipe broken").format(bin=self.cmd[0])` | {bin} : tube stdin rompu |
| 1015 | `f"{self.cmd[0]} stdout EOF unexpected"` | `_("{bin} stdout EOF unexpected").format(bin=self.cmd[0])` | {bin} : fin de stdout inattendue |
| 1033 | `f"malformed segment line: {line}"` | `_("malformed segment line: {line}").format(line=line)` | ligne de segment malformée : {line} |
| 2756 | `f"Failed to start {self.diarizer.label}"` | `_("Failed to start {what}").format(what=self.diarizer.label)` | Impossible de démarrer {what} |

Task 2, déjà enveloppées dans le code, à ajouter aux catalogues ici : `Live meeting engine not available in this version: {what}` → `Moteur de réunion en direct indisponible dans cette version : {what}` ; `{bin} (not installed)` → `{bin} (non installé)` ; `{bin} (cannot run --help)` → `{bin} (--help impossible)`. `Live meeting` existe (Réunion en direct).

Les quatre textes longs, msgid puis msgstr, chacun en un seul `_("…")` sur plusieurs lignes physiques comme l'original :

Infobulle diarisation (1734-1739), msgid :
```
Speaker separation engine.
Auto = multi-speaker if installed, otherwise Sortformer.
MOSS transcribes and identifies speakers in one pass, with its own ASR engine: it only serves the final analysis at Stop (no streaming mode, so the live preview keeps the engine above and the chosen model is ignored).
```
msgstr fr, les `\n` conservés :
```
Moteur de séparation des locuteurs.
Auto = multi-locuteurs si installé, sinon Sortformer.
MOSS transcrit et identifie les locuteurs en une passe, avec son propre moteur ASR : il ne sert QUE l'analyse finale au Stop (pas de mode flux, donc l'aperçu live garde le moteur ci-dessus et le modèle choisi est ignoré).
```

Infobulle sensibilité (1763-1766), msgid :
```
Speaker detection threshold (applied when the meeting starts). ← more speakers detected · more speakers merged →. 50 % = default; go up to 75 % if one person is split into several speakers.
```
msgstr fr :
```
Seuil de détection des locuteurs (appliqué au démarrage de la réunion). ← plus de locuteurs détectés · plus de locuteurs fusionnés →. 50 % = défaut ; montez vers 75 % si une même personne est éclatée en plusieurs locuteurs.
```

Infobulle analyse d'un autre fichier (1825-1827), msgid :
```
Open dictee-transcribe WITHOUT the current meeting, to analyze or re-transcribe a past file (History button).
To analyze THIS meeting: the 🔎 button after stopping.
```
msgstr fr :
```
Ouvrir dictee-transcribe SANS la réunion en cours, pour analyser ou ré-transcrire un fichier passé (bouton History).
Pour analyser CETTE réunion : le bouton 🔎 après l'arrêt.
```

Corps de la boîte de capture d'application (2528-2531), msgid :
```
The « dictee-app-capture » component is not on this system.

Recording did not start, to avoid capturing the microphone instead of the application. Reinstall dictee, or pick another audio source (microphone, system audio…).
```
msgstr fr :
```
Le composant « dictee-app-capture » est introuvable sur le système.

L'enregistrement n'a pas démarré pour éviter de capter le micro à la place de l'application. Réinstallez dictee, ou choisissez une autre source audio (micro, audio système…).
```

Hors traduction, à laisser tels quels : `"00:00"` (1650), les noms de moteurs du combo (1686-1690, 1695) et de la ligne 2786, les pourcentages et durées (`f"{v}%"`, `f"{h:02d}:{m:02d}:{s:02d}"`, `f"{since}s / {period}s"`, `f"{ctx_into}s / {overlap}s"`), les feuilles de style, l'aide argparse (3411-3413, non traduite dans dictee-transcribe.py non plus), `"Inhibit"` et `"UnInhibit"` (méthodes D-Bus, 3201 et 3219), `"Content-Type"` (2857), le format du transcript (2892), les `print(…, file=sys.stderr)`.

- [ ] **Step 4 : relancer le vérificateur jusqu'à la liste vide**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_meeting_live_window.py 2>&1 | grep -E '^FAIL (no user-facing|loading status)' | cut -c1-200
```
Tant qu'une ligne s'affiche, chaque couple `(ligne, texte)` est soit une chaîne oubliée à envelopper, soit un faux positif à ajouter à `NON_UI` avec justification dans le commit. La fin attendue : plus aucune ligne.

- [ ] **Step 5 : les catalogues**

Pour `po/dictee.pot` et chacun des six `po/<lang>.po`, un bloc par msgid nouveau en fin de fichier, sur ce modèle ; les msgid contenant `{…}` portent le drapeau que le reste du catalogue utilise (154 occurrences dans `po/fr.po`) :

```
#: dictee-meeting-live
#, python-brace-format
msgid "Chunk {n}"
msgstr ""
```

Dans `po/fr.po`, `msgstr` porte le texte de la colonne « msgstr fr ». Les cinq autres langues restent vides, comme les 145 à 157 chaînes déjà en attente dans chacune. Les `\n` des textes longs s'écrivent `\n` dans le `.po`, avec les continuations habituelles entre guillemets. Les `{n}`, `{s}`, `{msg}`, `{name}`, `{what}`, `{sock}`, `{err}`, `{rc}`, `{bin}`, `{line}` sont conservés à l'identique. Pour les six msgid qui existent déjà (`Start`, `Pause`, `Stop`, `Meeting`, `Model:`, `Live meeting`), aucun nouveau bloc : on peut ajouter une ligne `#: dictee-meeting-live` sous leur `#:` existant, rien d'autre.

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137
for l in fr de es it pt uk; do msgfmt --check -o po/$l.mo po/$l.po || echo "ECHEC $l"; done
msgunfmt po/fr.mo | grep -c -E 'Prêt à enregistrer|Tester le son…|Réécouter'
```
Attendu : aucun `ECHEC`, et `3`.

- [ ] **Step 6 : relancer le test complet**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/offscreen-check_meeting_live_window.py 2>&1 | grep -E '^(FAIL|OK|[0-9]+ FAILED)'
```
Attendu : `OK` seul. Vérification à l'œil, rendu français hors écran (le script de rendu détourne `STATE_FILE` et n'écrit pas dans `/dev/shm`) :

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137 && LANGUAGE=fr python3 /tmp/claude-1000/-mnt-ff433a59-fbed-4db3-9e7d-aeb235009f1b-DEV-SOURCES-RAPHA-STT-dictee/6f8f8cd9-0e26-4690-b2fe-3d75251a6020/scratchpad/render-meeting.py "$PWD/dictee-meeting-live" /tmp/meeting-1.3-fr.png
```
Le rendu doit reproduire celui de master pris le 2026-09-19, mêmes libellés français, moteurs absents mis à part.

- [ ] **Step 7 : commit**

```bash
git add dictee-meeting-live po/dictee.pot po/*.po po/*.mo tests/offscreen-check_meeting_live_window.py
git commit -m "i18n(meeting-live): route every user-facing string through gettext

The script came with about seventy French literals baked in: widget labels,
tooltips, the state table, worker error messages, a D-Bus inhibit reason,
and one comparison against a button label that would have broken the sound
test in any other language. English msgids now, French carried by the
catalog, the other five languages get empty entries as usual. The worker
diagnostics that were English in the French UI get a French translation
too. A tokenizer pass in the test flags any prose literal left outside _()
and a catalog check keeps every {placeholder} in the French msgstr."
```

---

### Task 4 : dictee-ptt réémet tout pendant la réunion

**Files:**
- Modify: `dictee-ptt.py` (fonction module après `read_state()`, trois lignes dans `run_evdev`, ancrage lignes 909 à 914)
- Create: `tests/test-ptt-meeting-passthrough.py`

**Interfaces:**
- Produces: `keys_pass_through(state: str) -> bool`.
- Consumes: `read_state()` (ligne 77), `ui.write_event(event)`.

- [ ] **Step 1 : le test**

Fichier `tests/test-ptt-meeting-passthrough.py` :

```python
#!/usr/bin/env python3
"""While the live meeting window is open, dictee-ptt must not interpret keys.

The window writes "meeting-ui-open" then "meeting-recording" to the shared
state file. In those two states every key, the dictation key included, has to
reach the applications untouched: otherwise F9 would start a dictation on top
of the meeting capture. The decision is a pure function so it can be pinned
here without a keyboard; a text check makes sure the evdev loop consults it
before handing the event to the PTT state machine.

Run: python3 tests/test-ptt-meeting-passthrough.py
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PTT = os.path.join(ROOT, "dictee-ptt.py")


def load_ptt():
    spec = importlib.util.spec_from_file_location("ptt_meeting_under_test", PTT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPassThrough(unittest.TestCase):

    def setUp(self):
        self.ptt = load_ptt()

    def test_meeting_states_pass_keys_through(self):
        self.assertTrue(self.ptt.keys_pass_through("meeting-ui-open"))
        self.assertTrue(self.ptt.keys_pass_through("meeting-recording"))

    def test_every_other_state_keeps_the_ptt_key(self):
        for state in ("idle", "recording", "transcribing", "offline", "switching",
                      "preparing", "diarize-ready", "diarizing", "", "garbage"):
            self.assertFalse(self.ptt.keys_pass_through(state), state)

    def test_the_evdev_loop_asks_before_handling_the_key(self):
        """The check must sit between the EV_KEY filter and ptt.handle_event."""
        src = open(PTT, encoding="utf-8").read()
        loop = src[src.index("def run_evdev("):src.index("def run_raw(")]
        gate = loop.find("keys_pass_through(read_state())")
        handle = loop.find("ptt.handle_event(event.code, event.value)")
        self.assertNotEqual(gate, -1, "run_evdev never consults keys_pass_through")
        self.assertLess(gate, handle, "the pass-through check comes after handle_event")
        self.assertIn("ui.write_event(event)", loop[gate:gate + 200],
                      "a passed-through key must still be re-emitted")


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

`def run_evdev(` est à la ligne 748 et `def run_raw(` à la ligne 963 de dictee-ptt.py sur la 1.3, dans cet ordre ; `ptt.handle_event(event.code, event.value)` est à la ligne 925.

- [ ] **Step 2 : lancer, vérifier l'échec**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137 && python3 tests/test-ptt-meeting-passthrough.py 2>&1 | tail -3
```
Attendu : `FAILED (errors=2, failures=1)`, les erreurs étant `AttributeError: … 'keys_pass_through'`.

- [ ] **Step 3 : la fonction et le branchement**

Après la définition de `read_state()` (elle commence ligne 77) et avant `def read_state_with_cleanup():` (ligne 111) :

```python
def keys_pass_through(state):
    """True while the live meeting window owns the keyboard.

    dictee-meeting-live writes "meeting-ui-open" when it shows and
    "meeting-recording" while it captures. In both cases every key must
    reach the applications untouched, the dictation key included: starting a
    dictation on top of a meeting capture is never what the user meant.
    """
    return state in ("meeting-recording", "meeting-ui-open")
```

Dans `run_evdev`, le bloc d'ancrage (lignes 909 à 914) :

```python
                        if event.type != EV_KEY:
                            # Ré-émettre les événements non-clavier (SYN, MSC, etc.)
                            ui.write_event(event)
                            continue

                        # Pause marker: while dictee-setup captures a key, stay
```

Insérer entre le `continue` et le commentaire `# Pause marker` :

```python
                        # Live meeting window open or recording: forward every
                        # key, the dictation key included, and consume nothing.
                        if keys_pass_through(read_state()):
                            ui.write_event(event)
                            continue

```

- [ ] **Step 4 : relancer**

```bash
python3 tests/test-ptt-meeting-passthrough.py 2>&1 | tail -1
python3 tests/test-keyboard-rescan.py 2>&1 | tail -1
python3 -m py_compile dictee-ptt.py && echo compile OK
```
Attendu : `OK`, `OK`, `compile OK`.

- [ ] **Step 5 : commit**

```bash
git add dictee-ptt.py tests/test-ptt-meeting-passthrough.py
git commit -m "feat(ptt): forward every key while the live meeting window is open

Same rule as master: in the meeting-ui-open and meeting-recording states the
daemon re-emits keys without interpreting them, so F9 cannot start a
dictation over a meeting capture. The decision lives in keys_pass_through so
it is pinned by a test without touching a keyboard."
```

---

### Task 5 : le tray connaît les deux états et lance la fenêtre

**Files:**
- Modify: `dictee-tray.py`
- Create: `tests/test-meeting-live-wiring.py`
- Modify: `po/dictee.pot`, `po/*.po`, `po/*.mo`

**Interfaces:**
- Produces: `ICON_MAP["meeting-ui-open"]`, `ICON_MAP["meeting-recording"]` ; `self.item_meeting_live_gtk` (Gtk.MenuItem) ; `self.action_meeting_live_qt` (QAction) ; msgid `Open the live meeting window (capture, then diarization)`, `Live meeting window open`, `Live meeting recording…` (`Live meeting` existe déjà).
- Consumes: `read_state()` (dictee-tray.py:430), `subprocess` (ligne 17).

- [ ] **Step 1 : le test**

Fichier `tests/test-meeting-live-wiring.py` :

```python
#!/usr/bin/env python3
"""Everything around the live meeting window: tray, plasmoid, packaging.

The window itself is covered by offscreen-check_meeting_live_window.py. This
file checks that the rest of dictee knows it exists: the tray offers it and
recognises its two shared states, the plasmoid does the same, and every
packaging target ships the binary. Text-level checks on purpose: the tray
needs a system tray and the plasmoid needs Plasma, neither of which a CI
runner has, while a forgotten line in any of these files is exactly the kind
of drift the checks are for.

Run: QT_QPA_PLATFORM=offscreen python3 tests/test-meeting-live-wiring.py
"""
import importlib.util
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


GREYED = r'\(\s*self\.state not in \("meeting-ui-open", "meeting-recording"\)\)'


class TestTray(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "dictee_tray_under_test", os.path.join(ROOT, "dictee-tray.py"))
        cls.tray = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tray)
        cls.src = read("dictee-tray.py")

    def test_icon_map_knows_both_meeting_states(self):
        self.assertEqual(self.tray.ICON_MAP["meeting-recording"], "parakeet-recording")
        self.assertEqual(self.tray.ICON_MAP["meeting-ui-open"], self.tray.ICON_MAP["idle"])

    def test_both_menus_launch_the_window(self):
        self.assertEqual(self.src.count('subprocess.Popen(["dictee-meeting-live"])'), 2,
                         "expected one launch site per menu flavour (GTK and Qt)")

    def test_gtk_entry_is_created_and_greyed_on_refresh(self):
        self.assertIn('self.item_meeting_live_gtk = Gtk.MenuItem(label=_("Live meeting"))', self.src)
        self.assertRegex(self.src, r"item_meeting_live_gtk\.set_sensitive" + GREYED)

    def test_qt_entry_is_created_and_greyed_on_refresh(self):
        self.assertIn('self.action_meeting_live_qt = self.menu.addAction(_("Live meeting"))', self.src)
        self.assertRegex(self.src, r"action_meeting_live_qt\.setEnabled" + GREYED)

    def test_meeting_recording_counts_as_busy_in_both_flavours(self):
        hits = re.findall(r'_recording = self\.state in \(([^)]*)\)', self.src)
        self.assertEqual(len(hits), 2, "expected the GTK and Qt busy lines")
        for h in hits:
            self.assertIn('"meeting-recording"', h)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2 : lancer, vérifier les échecs**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137 && QT_QPA_PLATFORM=offscreen python3 tests/test-meeting-live-wiring.py 2>&1 | tail -3
```
Attendu : `FAILED (failures=4, errors=1)`, l'erreur étant le `KeyError` sur `ICON_MAP`.

- [ ] **Step 3 : `ICON_MAP` (lignes 306-316)**

Après `    "switching": "parakeet-active-dark" if _DARK else "parakeet-active",` (ligne 315) et avant `}` :

```python
    # Live meeting window (dictee-meeting-live): open, then capturing.
    "meeting-ui-open": "parakeet-active-dark" if _DARK else "parakeet-active",
    "meeting-recording": "parakeet-recording",
```

- [ ] **Step 4 : menu GTK (ancrage ligne 593)**

Après `        self.menu.append(self.item_diarize_lock_gtk)` (ligne 593) et avant `        # LLM post-processing toggle (above Audio context)` (ligne 595) :

```python
        # Live meeting window (dictee-meeting-live). Distinct from the
        # "Meeting" toggle above, which is the diarized F9 recording.
        self.item_meeting_live_gtk = Gtk.MenuItem(label=_("Live meeting"))
        self.item_meeting_live_gtk.set_tooltip_text(
            _("Open the live meeting window (capture, then diarization)"))
        self.item_meeting_live_gtk.connect(
            "activate", lambda _w: subprocess.Popen(["dictee-meeting-live"]))
        self.item_meeting_live_gtk.set_sensitive(
            read_state() not in ("meeting-ui-open", "meeting-recording"))
        self.menu.append(self.item_meeting_live_gtk)

```

- [ ] **Step 5 : libellés, occupé et rafraîchissement GTK**

Lignes 757-761, remplacer le dictionnaire entier :

```python
            labels = {"idle": _("Daemon active"), "recording": _("Recording…"),
                      "transcribing": _("Transcribing…"),
                      "diarizing": _("Diarization in progress…"),
                      "preparing": _("Preparing diarization…"),
                      "diarize-ready": _("Ready for diarization")}
```
par :
```python
            labels = {"idle": _("Daemon active"), "recording": _("Recording…"),
                      "transcribing": _("Transcribing…"),
                      "diarizing": _("Diarization in progress…"),
                      "preparing": _("Preparing diarization…"),
                      "diarize-ready": _("Ready for diarization"),
                      "meeting-ui-open": _("Live meeting window open"),
                      "meeting-recording": _("Live meeting recording…")}
```

Ligne 771, remplacer :
```python
        _recording = self.state in ("recording", "transcribing", "diarizing")
```
par :
```python
        _recording = self.state in ("recording", "transcribing", "diarizing",
                                    "meeting-recording")
```

Après le bloc lignes 782-784 :
```python
        self.item_diarize_gtk.set_sensitive(_sortformer_available() and not is_busy)
        self.item_diarize_lock_gtk.set_sensitive(
            _sortformer_available() and not is_busy and self.item_diarize_gtk.get_active())
```
ajouter :
```python
        self.item_meeting_live_gtk.set_sensitive(
            self.state not in ("meeting-ui-open", "meeting-recording"))
```

- [ ] **Step 6 : côté Qt**

Après `        self.action_diarize_lock_qt.toggled.connect(self._on_diarize_lock_toggled_qt)` (ligne 1013) et avant `        # LLM post-processing toggle (above Audio context)` (ligne 1015) :

```python
        # Live meeting window (dictee-meeting-live). Distinct from the
        # "Meeting" toggle above, which is the diarized F9 recording.
        self.action_meeting_live_qt = self.menu.addAction(_("Live meeting"))
        self.action_meeting_live_qt.setToolTip(
            _("Open the live meeting window (capture, then diarization)"))
        self.action_meeting_live_qt.setEnabled(
            read_state() not in ("meeting-ui-open", "meeting-recording"))

```

Dispatch, après les lignes 1083-1084 :
```python
        elif action == self.action_transcribe:
            subprocess.Popen(["dictee-transcribe"])
```
ajouter :
```python
        elif action == self.action_meeting_live_qt:
            subprocess.Popen(["dictee-meeting-live"])
```

Dictionnaire des infobulles (lignes 1218-1227), après `            "transcribing": _("Dictation — transcribing"),` (ligne 1226) et avant `        }` :
```python
            "meeting-ui-open": _("Live meeting window open"),
            "meeting-recording": _("Live meeting recording…"),
```

Dictionnaire `labels` Qt (lignes 1240-1244) : même remplacement qu'à l'étape 5, mêmes deux entrées ajoutées avant la fermeture `}`.

Ligne 1258 :
```python
        _recording = self.state in ("recording", "transcribing", "diarizing",
                                    "meeting-recording")
```

Après le bloc lignes 1270-1272 (`self.action_diarize_lock_qt.setEnabled(…)`) :
```python
        self.action_meeting_live_qt.setEnabled(
            self.state not in ("meeting-ui-open", "meeting-recording"))
```

- [ ] **Step 7 : catalogues**

Sept catalogues, même schéma qu'en Task 3 avec `#: dictee-tray.py`, trois msgid nouveaux :

| msgid | msgstr fr |
|---|---|
| Open the live meeting window (capture, then diarization) | Ouvrir la fenêtre de réunion en direct (capture, puis diarisation) |
| Live meeting window open | Fenêtre de réunion en direct ouverte |
| Live meeting recording… | Réunion en direct, enregistrement… |

`Live meeting` existe déjà (page de dictee-setup, traduit « Réunion en direct ») : ne pas l'ajouter, `msgfmt --check` refuserait le doublon.

```bash
for l in fr de es it pt uk; do msgfmt --check -o po/$l.mo po/$l.po || echo "ECHEC $l"; done
```

- [ ] **Step 8 : relancer**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/test-meeting-live-wiring.py 2>&1 | tail -1
python3 tests/test-keycode-tables.py 2>&1 | tail -1
python3 -m py_compile dictee-tray.py && echo compile OK
```
Attendu : `OK`, `OK (skipped=2)`, `compile OK`.

- [ ] **Step 9 : commit**

```bash
git add dictee-tray.py po/dictee.pot po/*.po po/*.mo tests/test-meeting-live-wiring.py
git commit -m "feat(tray): offer the live meeting window and honour its two states

A \"Live meeting\" entry in both menu flavours, greyed while the window is
open or recording, plus icons, labels and the busy rule for the
meeting-ui-open and meeting-recording states the window publishes. The
existing \"Meeting\" toggle, the diarized F9 recording shipped in 1.3.6,
is untouched."
```

---

### Task 6 : le plasmoid a son bouton et connaît les deux états

**Files:**
- Modify: `plasmoid/package/contents/ui/FullRepresentation.qml` (entre les lignes 529 et 530)
- Modify: `plasmoid/package/contents/ui/main.qml` (lignes 22, 117, 690)
- Modify: `plasmoid/package/contents/locale/template.pot` et les six `.po` + `.mo`
- Modify: `tests/test-meeting-live-wiring.py`

**Interfaces:**
- Consumes: `signal actionRequested(string action)` (FullRepresentation.qml:23), `executable.run(cmd)` (main.qml:691), `ThemedButton` avec `tooltipText` (ThemedButton.qml:20), `icon.name`, `leftPadding`, `text`, `enabled`.
- Produces: action `"meeting-live"` dans le `switch` de `main.qml`.

- [ ] **Step 1 : la section plasmoid du test**

Dans `tests/test-meeting-live-wiring.py`, avant `if __name__ == "__main__":` :

```python
class TestPlasmoid(unittest.TestCase):

    def setUp(self):
        self.full = read("plasmoid/package/contents/ui/FullRepresentation.qml")
        self.main = read("plasmoid/package/contents/ui/main.qml")

    def test_popup_keeps_the_diarize_toggle_and_adds_the_live_button(self):
        self.assertIn('id: btnDiarize', self.full, "the 1.3.6 diarize toggle must stay")
        self.assertIn('id: btnMeetingLive', self.full)
        self.assertIn('fullRep.actionRequested("meeting-live")', self.full)
        self.assertLess(self.full.index('id: btnDiarize'), self.full.index('id: btnMeetingLive'))

    def test_live_button_sits_inside_the_button_row(self):
        """The row is the RowLayout right after '// Boutons dictee'; a block
        pasted after its closing brace would render outside the row."""
        row_start = self.full.index("RowLayout {", self.full.index("// Boutons dictee"))
        live = self.full.index("id: btnMeetingLive")
        sep = self.full.index("// Separateur avant transcription")
        self.assertLess(row_start, live)
        self.assertLess(live, sep)
        self.assertNotIn("\n    }\n", self.full[row_start:live],
                         "the row closed before the live button: it is outside")
        self.assertEqual(self.full[live:sep].count("\n    }\n"), 1,
                         "exactly one 4-space closing brace (the row's) between the live button and the separator")

    def test_button_is_greyed_while_the_window_is_up(self):
        self.assertIn('enabled: fullRep.state !== "meeting-ui-open" && fullRep.state !== "meeting-recording"',
                      self.full)

    def test_red_dot_follows_the_recording_state(self):
        self.assertIn('property bool active: fullRep.state === "meeting-recording"', self.full)

    def test_main_runs_the_window_on_the_action(self):
        self.assertIn('case "meeting-live":', self.main)
        self.assertIn('executable.run("dictee-meeting-live")', self.main)

    def test_offline_poll_leaves_the_meeting_states_alone(self):
        guard = [l for l in self.main.splitlines() if 'stdout === "offline" && root.state' in l]
        self.assertEqual(len(guard), 1)
        self.assertIn('root.state !== "meeting-recording"', guard[0])
        self.assertIn('root.state !== "meeting-ui-open"', guard[0])

    def test_plasmoid_catalog_carries_the_new_strings(self):
        pot = read("plasmoid/package/contents/locale/template.pot")
        fr = read("plasmoid/package/contents/locale/fr/LC_MESSAGES/plasma_applet_com.github.rcspam.dictee.po")
        for msgid in ("Live meeting", "Meeting window is open", "Meeting recording in progress",
                      "Open live meeting capture (record, then send to diarization)"):
            self.assertIn(f'msgid "{msgid}"', pot, msgid)
            self.assertIn(f'msgid "{msgid}"', fr, msgid)
        self.assertIn('msgstr "Réunion en direct"', fr)
```

Structure lue le 2026-09-20 : `// Boutons dictee` ligne 366, `RowLayout {` ligne 367, `id: btnDiarize` 447, la seule fermeture à quatre espaces entre 367 et 530 est la ligne 530 elle-même, `// Separateur avant transcription` ligne 533. Le catalogue du plasmoid connaît déjà `Meeting`, `Start meeting`, `Meeting in progress…`, `Stop meeting`, pas `Live meeting`.

- [ ] **Step 2 : lancer, vérifier les sept échecs**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/test-meeting-live-wiring.py 2>&1 | grep -E '^(FAIL|ERROR):' | wc -l
```
Attendu : `7`.

- [ ] **Step 3 : le bouton, copié de master, avec son id et son libellé propres**

Point d'insertion, c'est le piège de cette tâche. Structure lue le 2026-09-20 :

```
529:        }        ← ferme ThemedButton btnDiarize (8 espaces)
530:    }            ← ferme le RowLayout ouvert ligne 367 (4 espaces)
531:
532:
533:    // Separateur avant transcription
```

Le nouveau bloc va entre la ligne 529 et la ligne 530, donc à l'intérieur du `RowLayout`, indenté de huit espaces. Après la ligne 530 il serait hors de la rangée. Le test `test_live_button_sits_inside_the_button_row` compte les accolades pour le garantir.

```qml
        // Live meeting window (dictee-meeting-live). Sits next to the diarize
        // toggle above, which stays: that one is the diarized F9 recording.
        Item {
            Layout.fillWidth: true
            Layout.preferredWidth: 0
            implicitHeight: btnMeetingLive.implicitHeight

            ThemedButton {
                id: btnMeetingLive
                anchors.fill: parent
                text: i18n("Live meeting")
                icon.name: "meeting-attending"
                enabled: fullRep.state !== "meeting-ui-open" && fullRep.state !== "meeting-recording"
                onClicked: fullRep.actionRequested("meeting-live")
                leftPadding: meetingDot.visible ? 20 : undefined
                tooltipText: fullRep.state === "meeting-ui-open"
                    ? i18n("Meeting window is open")
                    : fullRep.state === "meeting-recording"
                    ? i18n("Meeting recording in progress")
                    : i18n("Open live meeting capture (record, then send to diarization)")
            }

            Rectangle {
                id: meetingDot
                property bool active: fullRep.state === "meeting-recording"
                visible: active
                width: 10; height: 10; radius: 5
                color: "#ff0000"
                z: 100
                anchors.verticalCenter: parent.verticalCenter
                x: 6
                onActiveChanged: {
                    if (active) { meetingDotAnim.start() }
                    else { meetingDotAnim.stop(); opacity = 1.0 }
                }
            }
            SequentialAnimation {
                id: meetingDotAnim
                loops: Animation.Infinite
                NumberAnimation { target: meetingDot; property: "opacity"; to: 0.2; duration: 600; easing.type: Easing.InOutSine }
                NumberAnimation { target: meetingDot; property: "opacity"; to: 1.0; duration: 600; easing.type: Easing.InOutSine }
            }
        }
```

`Easing.InOutSine` est la valeur de `translateDotAnim` lignes 441 et 442 du même fichier.

- [ ] **Step 4 : main.qml, trois lignes**

Ligne 22, remplacer :
```qml
    // State: "offline", "idle", "recording", "transcribing", "switching", "preparing", "diarize-ready", "diarizing"
```
par :
```qml
    // State: "offline", "idle", "recording", "transcribing", "switching", "preparing", "diarize-ready", "diarizing", "meeting-ui-open", "meeting-recording"
```

Ligne 117, la garde se termine par `&& root.state !== "diarizing") {`. Remplacer cette fin par :
```qml
&& root.state !== "diarizing" && root.state !== "meeting-ui-open" && root.state !== "meeting-recording") {
```

Après le bloc lignes 690-692 :
```qml
        case "cheatsheet":
            executable.run("dictee-cheatsheet --toggle")
            break
```
ajouter :
```qml
        case "meeting-live":
            executable.run("dictee-meeting-live")
            break
```

- [ ] **Step 5 : catalogues du plasmoid**

Dans `plasmoid/package/contents/locale/template.pot` et chacun des six `<lang>/LC_MESSAGES/plasma_applet_com.github.rcspam.dictee.po`, quatre blocs avant les entrées `#~` obsolètes (le `.po` français en a 53 en fin de fichier) :

```
#: contents/ui/FullRepresentation.qml
msgid "Live meeting"
msgstr ""
```

Dans le `.po` français : `Réunion en direct`, `Fenêtre de réunion ouverte`, `Enregistrement de la réunion en cours`, `Ouvrir la capture de réunion en direct (enregistrer, puis envoyer à la diarisation)`.

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137/plasmoid/package/contents/locale
for l in fr de es it pt uk; do msgfmt --check -o $l/LC_MESSAGES/plasma_applet_com.github.rcspam.dictee.mo $l/LC_MESSAGES/plasma_applet_com.github.rcspam.dictee.po || echo "ECHEC $l"; done
```
Attendu : aucun `ECHEC`. Les `.mo` du plasmoid sont suivis par git (six fichiers), ils font partie du commit.

- [ ] **Step 6 : relancer, et la syntaxe QML**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137
QT_QPA_PLATFORM=offscreen python3 tests/test-meeting-live-wiring.py 2>&1 | tail -1
python3 tests/test-keycode-tables.py 2>&1 | tail -1
if command -v qmllint >/dev/null; then qmllint plasmoid/package/contents/ui/main.qml plasmoid/package/contents/ui/FullRepresentation.qml 2>&1 | grep -i -E 'error|syntax' | head -3; echo "qmllint termine"; else echo "qmllint absent"; fi
```
Attendu : `OK`, `OK (skipped=2)`, et aucune ligne `error` de qmllint. Sans qmllint, compter les accolades du bloc inséré : 10 ouvrantes, 10 fermantes.

- [ ] **Step 7 : commit**

```bash
git add plasmoid/package/contents/ui/FullRepresentation.qml plasmoid/package/contents/ui/main.qml plasmoid/package/contents/locale tests/test-meeting-live-wiring.py
git commit -m "feat(plasmoid): a Live meeting button beside the diarize toggle

Launches dictee-meeting-live, greys out while the window is open or
recording, blinks red while it records. Unlike master, the 1.3.6 diarize
\"Meeting\" toggle stays where it is. The offline poll no longer treats the
two meeting states as a dead daemon."
```

---

### Task 7 : le binaire est livré par les quatre cibles

**Files:**
- Modify: `build-common.sh` 98 et 120 ; `build-rpm.sh` 77 et 103 ; `build-tar.sh` 164 ; `PKGBUILD` 128 ; `PKGBUILD-cuda` 210 ; `install.sh` 814
- Modify: `tests/test-meeting-live-wiring.py`

**Interfaces:**
- Produces: `/usr/bin/dictee-meeting-live` dans le .deb, le .rpm, le tarball et le paquet Arch.

- [ ] **Step 1 : la section packaging du test**

Avant `if __name__ == "__main__":` :

```python
class TestPackaging(unittest.TestCase):
    """One line per target, and the shebang list too: the Python scripts are
    shipped without their .py suffix and get their interpreter patched."""

    def test_every_target_ships_the_window(self):
        expectations = {
            "build-common.sh": ['cp ./dictee-meeting-live     "$PKG_DIR/usr/bin/dictee-meeting-live"',
                                '"$PKG_DIR/usr/bin/dictee-meeting-live" \\'],
            "build-rpm.sh": ['cp "$PKG_DIR/usr/bin/dictee-meeting-live" "$buildroot/usr/bin/"',
                             '"$buildroot/usr/bin/dictee-meeting-live" \\'],
            "build-tar.sh": ["dictee-transcribe dictee-meeting-live dictee-cheatsheet"],
            "PKGBUILD": ['install -Dm755 dictee-meeting-live "$pkgdir/usr/bin/dictee-meeting-live"'],
            "PKGBUILD-cuda": ['install -Dm755 dictee-meeting-live "$pkgdir/usr/bin/dictee-meeting-live"'],
            "install.sh": ["dictee-audio-sources dictee-meeting-live"],
        }
        for path, needles in expectations.items():
            src = read(path)
            for needle in needles:
                self.assertIn(needle, src, f"{path} does not ship dictee-meeting-live: {needle!r}")
```

Les six lignes attendues sont celles de master, lues le 2026-09-20 (build-common.sh 34 et 53, build-rpm.sh 78 et 105, build-tar.sh 191, PKGBUILD 145, PKGBUILD-cuda 244, install.sh 833).

- [ ] **Step 2 : lancer, vérifier l'échec sur build-common.sh**

```bash
QT_QPA_PLATFORM=offscreen python3 tests/test-meeting-live-wiring.py 2>&1 | grep -c 'does not ship'
```
Attendu : `1` (le test s'arrête au premier fichier).

- [ ] **Step 3 : les huit lignes**

`build-common.sh`, après la ligne 98 `    cp ./dictee-transcribe.py    "$PKG_DIR/usr/bin/dictee-transcribe"` :
```bash
    cp ./dictee-meeting-live     "$PKG_DIR/usr/bin/dictee-meeting-live"
```
et après la ligne 120 `        "$PKG_DIR/usr/bin/dictee-transcribe" \` :
```bash
        "$PKG_DIR/usr/bin/dictee-meeting-live" \
```

`build-rpm.sh`, après la ligne 77 `    cp "$PKG_DIR/usr/bin/dictee-transcribe" "$buildroot/usr/bin/"` :
```bash
    cp "$PKG_DIR/usr/bin/dictee-meeting-live" "$buildroot/usr/bin/"
```
et après la ligne 103 `        "$buildroot/usr/bin/dictee-transcribe" \` :
```bash
        "$buildroot/usr/bin/dictee-meeting-live" \
```

`build-tar.sh` ligne 164, remplacer `         dictee-transcribe dictee-cheatsheet dictee-reset \` par `         dictee-transcribe dictee-meeting-live dictee-cheatsheet dictee-reset \`.

`PKGBUILD` après la ligne 128 et `PKGBUILD-cuda` après la ligne 210, toutes deux `    install -Dm755 dictee-transcribe.py "$pkgdir/usr/bin/dictee-transcribe"` :
```bash
    install -Dm755 dictee-meeting-live "$pkgdir/usr/bin/dictee-meeting-live"
```

`install.sh` ligne 814, remplacer `        dictee-translate-langs dictee-audio-sources` par `        dictee-translate-langs dictee-audio-sources dictee-meeting-live`.

- [ ] **Step 4 : test, syntaxe, audit, build réel**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137
QT_QPA_PLATFORM=offscreen python3 tests/test-meeting-live-wiring.py 2>&1 | tail -1
bash -n build-common.sh build-rpm.sh build-tar.sh install.sh && echo "syntaxe OK"
python3 packaging/audit-deps.py | tail -1
./build-deb.sh 2>&1 | grep -E 'glibc check|FATAL|Built:' | tail -4
dpkg-deb -c .dev/dist/dictee-cpu_1.3.7~rc3-2_amd64.deb | grep -E 'usr/bin/dictee-meeting-live$'
dpkg-deb --fsys-tarfile .dev/dist/dictee-cpu_1.3.7~rc3-2_amd64.deb | tar -xO ./usr/bin/dictee-meeting-live | head -1
```
Attendu : `OK`, `syntaxe OK`, une ligne `✓ packaging deps audit OK …`, deux `glibc check OK` et trois `Built:`, une ligne `-rwxr-xr-x … ./usr/bin/dictee-meeting-live`, et la même première ligne que `… | tar -xO ./usr/bin/dictee-transcribe | head -1` (shebang patché). `VERSION="1.3.7~rc3-2"` est dans build-deb.sh ligne 11.

- [ ] **Step 5 : le script livré démarre sur Debian 12**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137 && timeout 600 podman run --rm -v "$PWD/.dev/dist:/d:ro" docker.io/library/debian:12 sh -c '
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq python3-pyqt6 >/dev/null 2>&1
dpkg -i /d/dictee-cpu_1.3.7~rc3-2_amd64.deb >/dev/null 2>&1 || true
QT_QPA_PLATFORM=offscreen timeout 30 dictee-meeting-live --help 2>&1 | head -3
'
```
Attendu : `usage: dictee-meeting-live [-h] [--start] [--stop]` sans traceback. `--help` sort avant toute construction de fenêtre, donc n'écrit aucun état.

- [ ] **Step 6 : commit**

```bash
git add build-common.sh build-rpm.sh build-tar.sh PKGBUILD PKGBUILD-cuda install.sh tests/test-meeting-live-wiring.py
git commit -m "pkg: ship dictee-meeting-live on every target

deb and rpm through build-common.sh and build-rpm.sh (copy plus shebang
patch list), the tarball and its installer, and both Arch PKGBUILDs. A test
pins the line in each file so the next new binary cannot skip a target."
```

---

### Task 8 : tout tourne en CI

**Files:**
- Create: `tests/test-meeting-slug.py`
- Modify: `.github/workflows/rust.yml` (job `test-key-capture`, lignes 70 à 120)

**Interfaces:**
- Consumes: les quatre fichiers de test des tâches 1 à 7.

- [ ] **Step 1 : les fonctions pures, portées de master en style unittest**

Fichier `tests/test-meeting-slug.py`, mêmes assertions que master (tests/test-meeting-slug.py, lu le 2026-09-20), réécrites pour unittest :

```python
#!/usr/bin/env python3
"""Pure helpers of dictee-meeting-live: folder slug, F9 model spec, whisper tokens.

Ported from master's tests/test-meeting-slug.py, rewritten for unittest so it
runs with python3 alone like the rest of this directory. Nothing here builds
a window, so the shared state file is never touched.

Run: python3 tests/test-meeting-slug.py
"""
import importlib.machinery
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
loader = importlib.machinery.SourceFileLoader(
    "meeting_live_pure", os.path.join(ROOT, "dictee-meeting-live"))
spec = importlib.util.spec_from_loader("meeting_live_pure", loader)
ml = importlib.util.module_from_spec(spec)
sys.modules["meeting_live_pure"] = ml
spec.loader.exec_module(ml)


class TestPureHelpers(unittest.TestCase):

    def test_slug(self):
        self.assertEqual(ml.slug_title("Réunion équipe !"), "r-union-quipe")
        self.assertEqual(ml.slug_title("  A  B  "), "a-b")
        self.assertEqual(ml.slug_title(""), "")

    def test_current_f9_spec(self):
        self.assertEqual(ml.current_f9_spec({"DICTEE_ASR_BACKEND": "whisper",
                                             "DICTEE_WHISPER_MODEL": "medium"}), "whisper-medium")
        self.assertEqual(ml.current_f9_spec({"DICTEE_ASR_BACKEND": "parakeet",
                                             "DICTEE_PARAKEET_QUANT": "int8"}), "parakeet-int8")
        self.assertEqual(ml.current_f9_spec({}), "parakeet-fp32")
        self.assertEqual(ml.current_f9_spec({"DICTEE_ASR_BACKEND": "whisper"}), "whisper-small")
        self.assertEqual(ml.current_f9_spec({"DICTEE_ASR_BACKEND": "canary"}), "parakeet-fp32")

    def test_parse_whisper_tokens(self):
        text = "[0.00s - 0.50s] Bonjour\n[0.50s - 1.20s] le\n[1.20s - 2.00s] monde\n"
        self.assertEqual(ml._parse_whisper_tokens(text), [
            {"text": "Bonjour", "start_s": 0.0, "end_s": 0.5},
            {"text": "le", "start_s": 0.5, "end_s": 1.2},
            {"text": "monde", "start_s": 1.2, "end_s": 2.0},
        ])
        # sentence-level lines (no 's' suffix) and blanks/garbage are robust
        self.assertEqual(ml._parse_whisper_tokens("[1 - 2] hi"),
                         [{"text": "hi", "start_s": 1.0, "end_s": 2.0}])
        self.assertEqual(ml._parse_whisper_tokens(""), [])
        self.assertEqual(ml._parse_whisper_tokens("garbage no brackets"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2 : les quatre suites en local**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee-137
for t in tests/test-meeting-slug.py tests/test-ptt-meeting-passthrough.py tests/test-meeting-live-wiring.py tests/offscreen-check_meeting_live_window.py; do printf '%-46s ' "$(basename $t)"; QT_QPA_PLATFORM=offscreen python3 $t 2>&1 | grep -E '^(OK|FAILED|[0-9]+ FAILED)' | head -1; done
```
Attendu : quatre `OK`.

- [ ] **Step 3 : le job qui a déjà PyQt6**

Dans `.github/workflows/rust.yml`, job `test-key-capture`, après l'étape (lignes 116 à 119) :
```yaml
    - name: Run animation-speech update tests
      run: python3 tests/offscreen-check_anim_speech_update.py
      env:
        QT_QPA_PLATFORM: offscreen
```
ajouter :
```yaml
    # The live meeting window and everything that points at it. Offscreen,
    # no capture is ever started, the engine probe is fed fake binaries, the
    # state file is redirected, and the French rendering reads the tracked
    # po/fr.mo: no gettext tooling.
    - name: Run live meeting window tests
      run: |
        python3 tests/test-meeting-slug.py
        python3 tests/test-ptt-meeting-passthrough.py
        python3 tests/test-meeting-live-wiring.py
        python3 tests/offscreen-check_meeting_live_window.py
      env:
        QT_QPA_PLATFORM: offscreen
```

- [ ] **Step 4 : valider le YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/rust.yml')); print('yaml OK')"
```

- [ ] **Step 5 : commit**

```bash
git add .github/workflows/rust.yml tests/test-meeting-slug.py
git commit -m "ci: run the live meeting window tests"
```

---

## Auto-revue

**Couverture de la spec.** Critère 1 (construction, widgets) : Task 1. Critère 2 (refus sans moteur, sonde positive) : Task 2. Critère 3 (plus de chaîne visible hors gettext, catalogues, rendu français) : Task 3, par un vérificateur par tokens dont la liste blanche vient d'un balayage sans liste blanche, un rendu à travers le `.mo` suivi par git, et un contrôle des placeholders. Critère 4 (touche de dictée réémise pendant la réunion) : Task 4, fonction de décision plus contrôle de position dans la boucle. Critère 5 (tray et plasmoid) : Tasks 5 et 6. Critère 6 (paquets) : Task 7, build réel et exécution sur Debian 12. Critère 7 (CI) : Task 8. Décision « deux boutons » : Task 6, avec un test qui exige `btnDiarize` avant `btnMeetingLive` et qui compte les accolades pour vérifier que le bouton est dans la rangée. États partagés : Tasks 4, 5, 6. Hors périmètre respecté : aucune tâche ne touche `src/`, `dictee-stream` ni l'état `streaming`.

**Erreurs de la première rédaction, trouvées aux relectures du 2026-09-20.**
- Le constructeur de la fenêtre écrit `meeting-ui-open` dans le vrai `/dev/shm/.dictee_state` ; les tests l'auraient fait sur la machine de développement, et avec la Task 4 en place dictee-ptt aurait ensuite laissé passer toutes les touches. D'où `STATE_FILE`, le refus de construire sans elle, et la comparaison du vrai fichier avant et après.
- La table de traduction ne couvrait que les chaînes passées à un constructeur de widget, 37 sur les 142 littéraux que remonte le balayage. Manquaient entre autres les tuples d'états, le dictionnaire de statuts, sept messages de repli des daemons, quatre autres chaînes françaises (`Essai en cours — {s} s`, `socket transcribe-daemon absente`, `⚙ Chunk … transcription + diarisation…`, `Enregistrement trop court`), le mot seul `"diarisation"`, dix-sept diagnostics anglais des workers, et la comparaison `!= "▶ Réécouter"` qui aurait cassé le test du son hors français.
- La liste blanche du vérificateur avait été écrite de mémoire ; elle est maintenant déduite de la liste réelle des littéraux hors table, tous lus.
- Six msgid existent déjà dans le catalogue (`Start`, `Pause`, `Stop`, `Meeting`, `Model:`, `Live meeting`) ; les rajouter aurait fait échouer `msgfmt --check`. Leur traduction actuelle est celle voulue.
- `msgfmt` 0.21 ne vérifie pas les placeholders `python-brace-format` (testé : un `{n}` contre `{m}` passe). Le test le fait.
- Le test du tray comptait trois occurrences de chaque attribut ; le code en produit six et cinq. Remplacé par des assertions sur les lignes exactes. Deux numéros de lignes du tray étaient faux (593 et 1013, pas 596 et 1015), comme un de build-rpm.sh (103, pas 104).
- Le bouton du plasmoid était placé après la fermeture du `RowLayout`. Le point exact est écrit avec ses lignes de contexte, et un test vérifie que la rangée n'est pas fermée avant le bouton.
- Le rendu français liait le domaine gettext avant de charger le script, que le script relie ensuite sur le `.mo` installé de la machine s'il en trouve un. Il passe maintenant par le premier répertoire de `LOCALE_DIRS`, sous le HOME jetable du test, avec le `po/fr.mo` suivi par git.
- La copie du script n'était pas épinglée ; elle l'est sur le commit 03d3ad8. Le test des fonctions pures omettait trois assertions de master ; elles sont reprises.

**Cohérence des noms.** `missing_live_engine_features` et `LIVE_ENGINE_CHECKS` (Task 2) sont ceux du test. `STATE_FILE` (Task 1) est le nom que dictee-ptt.py utilise déjà pour le même fichier. `keys_pass_through` (Task 4) est le nom attendu par le test textuel. `item_meeting_live_gtk` et `action_meeting_live_qt` (Task 5) apparaissent dans les lignes exactes que le test cherche. `btnMeetingLive` et `meetingDot` (Task 6) sont ceux du test. `_Msg` (Task 2) suit la convention des tests de master.
