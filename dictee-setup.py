#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dictee-setup — Voice dictation configuration
Qt6 UI to configure keyboard shortcut and translation options.
Saves to ~/.config/dictee.conf (shell format, sourceable by dictee).
Supports PyQt6 (preferred) and PySide6 (fallback).
"""

import gettext
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import locale
import tempfile

try:
    from PyQt6.QtCore import Qt, QThread, QTimer, QIODevice, QObject, QProcess, pyqtSignal as Signal
    from PyQt6.QtGui import QKeySequence, QIcon, QPainter, QColor, QLinearGradient, QImage, QPixmap
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
        QLabel, QPushButton, QRadioButton, QButtonGroup, QComboBox,
        QFormLayout, QProgressBar, QMessageBox, QSizePolicy, QCheckBox,
        QFrame, QScrollArea, QWidget, QStackedWidget, QSlider, QTextEdit,
        QToolTip, QGridLayout, QTabWidget, QLineEdit,
    )
    from PyQt6.QtMultimedia import QAudioSource, QAudioFormat, QMediaDevices
except ImportError:
    from PySide6.QtCore import Qt, QThread, QTimer, QIODevice, QObject, QProcess, Signal
    from PySide6.QtGui import QKeySequence, QIcon, QPainter, QColor, QLinearGradient, QImage, QPixmap
    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
        QLabel, QPushButton, QRadioButton, QButtonGroup, QComboBox,
        QFormLayout, QProgressBar, QMessageBox, QSizePolicy, QCheckBox, QGridLayout,
        QFrame, QScrollArea, QWidget, QStackedWidget, QSlider, QTextEdit,
        QToolTip, QTabWidget, QLineEdit,
    )
    from PySide6.QtMultimedia import QAudioSource, QAudioFormat, QMediaDevices

# === i18n ===

LOCALE_DIRS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "share", "locale"),
    os.path.expanduser("~/.local/share/locale"),
    "/usr/local/share/locale",
    "/usr/share/locale",
]

for _d in LOCALE_DIRS:
    if os.path.isfile(os.path.join(_d, "fr", "LC_MESSAGES", "dictee.mo")):
        gettext.bindtextdomain("dictee", _d)
        break

gettext.textdomain("dictee")
_ = gettext.gettext

_NATIVE_TEXT = QKeySequence.SequenceFormat.NativeText

# === Configuration ===

CONF_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "dictee.conf",
)

LANGUAGES = [
    ("fr", "Français"),
    ("en", "English"),
    ("es", "Español"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("pt", "Português"),
    ("nl", "Nederlands"),
    ("pl", "Polski"),
    ("ru", "Русский"),
    ("uk", "Українська"),
    ("bg", "Български"),
    ("cs", "Čeština"),
    ("da", "Dansk"),
    ("el", "Ελληνικά"),
    ("et", "Eesti"),
    ("fi", "Suomi"),
    ("hr", "Hrvatski"),
    ("hu", "Magyar"),
    ("lt", "Lietuvių"),
    ("lv", "Latviešu"),
    ("mt", "Malti"),
    ("ro", "Română"),
    ("sk", "Slovenčina"),
    ("sl", "Slovenščina"),
    ("sv", "Svenska"),
    ("zh", "中文"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("ar", "العربية"),
]

# Langues supportées par chaque backend ASR (pour filtrer la langue source)
# Parakeet TDT 0.6B v3 : 25 langues européennes (source: NVIDIA HuggingFace)
PARAKEET_LANGUAGES = {
    "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr",
    "hr", "hu", "it", "lt", "lv", "mt", "nl", "pl", "pt", "ro",
    "ru", "sk", "sl", "sv", "uk",
}
ASR_LANGUAGES = {
    "parakeet": PARAKEET_LANGUAGES,
    "vosk": {"fr", "en", "de", "es", "it", "pt", "ru", "zh", "ja"},
    "whisper": None,   # None = toutes
}

# Langues supportées par chaque backend de traduction (pour filtrer la langue cible)
# None = toutes, set() = limité
TRANSLATE_LANGUAGES = {
    "trans:google": None,
    "trans:bing": None,
    "ollama": None,
    "libretranslate": None,  # Dynamique — filtré via les langues installées
}

DICTEE_COMMAND = "/usr/bin/dictee"
DICTEE_TRANSLATE_COMMAND = "/usr/bin/dictee --translate"
DICTEE_DESKTOP = "dictee.desktop"
DICTEE_TRANSLATE_DESKTOP = "dictee-translate.desktop"

# Mapping Qt key → Linux keycode (evdev) pour dictee-ptt
QT_TO_LINUX_KEYCODE = {
    0x01000030: 59,   # F1
    0x01000031: 60,   # F2
    0x01000032: 61,   # F3
    0x01000033: 62,   # F4
    0x01000034: 63,   # F5
    0x01000035: 64,   # F6
    0x01000036: 65,   # F7
    0x01000037: 66,   # F8
    0x01000038: 67,   # F9
    0x01000039: 68,   # F10
    0x0100003a: 87,   # F11
    0x0100003b: 88,   # F12
    0x01000000: 1,    # Escape
    0x01000010: 110,  # Home
    0x01000011: 107,  # End
    0x01000016: 119,  # Delete
    0x01000015: 118,  # Insert
    0x01000017: 104,  # Pause/Break
    0x01000009: 210,  # Print Screen (SysRq)
    0x01000025: 14,   # Backspace — non, pas utile
}

LINUX_KEYCODE_NAMES = {
    59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6",
    65: "F7", 66: "F8", 67: "F9", 68: "F10", 87: "F11", 88: "F12",
    1: "Escape", 110: "Home", 107: "End", 119: "Delete", 118: "Insert",
}


def qt_key_to_linux_keycode(seq):
    """Convertit une QKeySequence en keycode Linux evdev."""
    if seq is None:
        return 0
    key_int = seq[0].toCombined() if hasattr(seq[0], 'toCombined') else int(seq[0])
    # Masquer les modificateurs Qt (0x0e000000)
    key_only = key_int & 0x01ffffff
    return QT_TO_LINUX_KEYCODE.get(key_only, 0)


def linux_keycode_name(code):
    """Retourne le nom lisible d'un keycode Linux."""
    return LINUX_KEYCODE_NAMES.get(code, f"Key {code}")
ANIMATION_SPEECH_REPO = "rcspam/animation-speech"
ANIMATION_SPEECH_BIN = "animation-speech-ctl"

# === Détection DE ===


def detect_desktop():
    """Retourne (nom_affiché, type) avec type = 'kde' | 'gnome' | 'unsupported'."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "KDE" in desktop:
        return "KDE Plasma", "kde"
    for name in ("GNOME", "UNITY", "CINNAMON"):
        if name in desktop:
            label = desktop.replace(";", " / ").title()
            return label, "gnome"
    raw = os.environ.get("XDG_CURRENT_DESKTOP", _("unknown"))
    return raw, "unsupported"


# === Config fichier ===


def load_config():
    """Charge dictee.conf et retourne un dict des valeurs."""
    conf = {}
    if os.path.isfile(CONF_PATH):
        with open(CONF_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"^([A-Z_]+)=(.*)$", line)
                if m:
                    conf[m.group(1)] = m.group(2)
    return conf


def save_config(backend, lang_source, lang_target, clipboard=True, animation="speech",
                ollama_model="translategemma", ollama_cpu=False, trans_engine="google",
                lt_port=5000, lt_langs="", asr_backend="parakeet", whisper_model="small",
                whisper_lang="", vosk_model="fr", audio_source="",
                ptt_mode="toggle", ptt_key=67, ptt_key_translate=0,
                ptt_mod_translate="", postprocess=True,
                pp_elisions=True, pp_numbers=True, pp_typography=True,
                pp_capitalization=True, pp_fuzzy_dict=True,
                llm_postprocess=False, llm_model="ministral:3b",
                llm_timeout=10, llm_cpu=False):
    """Écrit dictee.conf (sans DICTEE_TRANSLATE — le déclenchement est au runtime)."""
    os.makedirs(os.path.dirname(CONF_PATH), exist_ok=True)
    with open(CONF_PATH, "w") as f:
        f.write("# Generated by dictee-setup\n")
        f.write(f"DICTEE_ASR_BACKEND={asr_backend}\n")
        f.write(f"DICTEE_TRANSLATE_BACKEND={backend}\n")
        f.write(f"DICTEE_LANG_SOURCE={lang_source}\n")
        f.write(f"DICTEE_LANG_TARGET={lang_target}\n")
        f.write(f"DICTEE_CLIPBOARD={'true' if clipboard else 'false'}\n")
        f.write(f"DICTEE_ANIMATION={animation}\n")
        if asr_backend == "vosk":
            f.write(f"DICTEE_VOSK_MODEL={vosk_model}\n")
        elif asr_backend == "whisper":
            f.write(f"DICTEE_WHISPER_MODEL={whisper_model}\n")
            if whisper_lang:
                f.write(f"DICTEE_WHISPER_LANG={whisper_lang}\n")
        if backend == "trans":
            f.write(f"DICTEE_TRANS_ENGINE={trans_engine}\n")
        elif backend == "libretranslate":
            f.write(f"DICTEE_LIBRETRANSLATE_PORT={lt_port}\n")
            if lt_langs:
                f.write(f"DICTEE_LIBRETRANSLATE_LANGS={lt_langs}\n")
        elif backend == "ollama":
            f.write(f"DICTEE_OLLAMA_MODEL={ollama_model}\n")
            if ollama_cpu:
                f.write("OLLAMA_NUM_GPU=0\n")
        if audio_source:
            f.write(f"DICTEE_AUDIO_SOURCE={audio_source}\n")
        # PTT (push-to-talk)
        f.write(f"DICTEE_PTT_MODE={ptt_mode}\n")
        f.write(f"DICTEE_PTT_KEY={ptt_key}\n")
        if ptt_key_translate:
            f.write(f"DICTEE_PTT_KEY_TRANSLATE={ptt_key_translate}\n")
        if ptt_mod_translate:
            f.write(f"DICTEE_PTT_MOD_TRANSLATE={ptt_mod_translate}\n")
        # Post-traitement
        f.write(f"DICTEE_POSTPROCESS={'true' if postprocess else 'false'}\n")
        if not pp_elisions:
            f.write("DICTEE_PP_ELISIONS=false\n")
        if not pp_numbers:
            f.write("DICTEE_PP_NUMBERS=false\n")
        if not pp_typography:
            f.write("DICTEE_PP_TYPOGRAPHY=false\n")
        if not pp_capitalization:
            f.write("DICTEE_PP_CAPITALIZATION=false\n")
        if not pp_fuzzy_dict:
            f.write("DICTEE_PP_FUZZY_DICT=false\n")
        if llm_postprocess:
            f.write(f"DICTEE_LLM_POSTPROCESS=true\n")
            f.write(f"DICTEE_LLM_MODEL={llm_model}\n")
            f.write(f"DICTEE_LLM_TIMEOUT={llm_timeout}\n")
            if llm_cpu:
                f.write("DICTEE_LLM_CPU=true\n")


# === Raccourci KDE ===


def qt_key_to_kde(key_sequence):
    """Convertit une QKeySequence en format KDE ('Meta+D')."""
    return key_sequence.toString()


def find_kde_shortcut_for_command(command):
    """Trouve le raccourci KDE existant pour une commande donnée.

    Scanne les .desktop dans ~/.local/share/applications/ pour trouver
    ceux dont Exec correspond, puis lit le raccourci dans kglobalshortcutsrc.
    Retourne (raccourci, nom_desktop) ou (None, None).
    """
    apps_dir = os.path.expanduser("~/.local/share/applications")
    rc_path = os.path.expanduser("~/.config/kglobalshortcutsrc")

    if not os.path.isdir(apps_dir) or not os.path.isfile(rc_path):
        return None, None

    # Trouver les .desktop dont Exec correspond
    matching_desktops = []
    try:
        for fname in os.listdir(apps_dir):
            if not fname.endswith(".desktop"):
                continue
            fpath = os.path.join(apps_dir, fname)
            try:
                with open(fpath) as f:
                    for line in f:
                        if line.strip().startswith("Exec="):
                            exec_cmd = line.strip().split("=", 1)[1].strip()
                            if exec_cmd == command:
                                matching_desktops.append(fname)
                            break
            except OSError:
                continue
    except OSError:
        return None, None

    if not matching_desktops:
        return None, None

    # Lire le raccourci depuis kglobalshortcutsrc
    try:
        with open(rc_path) as f:
            content = f.read()
    except OSError:
        return None, None

    for desktop_name in matching_desktops:
        target = f"[services][{desktop_name}]"
        idx = content.find(target)
        if idx < 0:
            continue
        for line in content[idx + len(target):].split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("["):
                break
            if line.startswith("_launch="):
                accel = line.split("=", 1)[1].split(",")[0].strip()
                if accel and accel != "none":
                    return accel, desktop_name

    return None, None


def _dictee_desktop_names():
    """Retourne les noms de tous les .desktop qui pointent vers dictee."""
    apps_dir = os.path.expanduser("~/.local/share/applications")
    names = {DICTEE_DESKTOP, DICTEE_TRANSLATE_DESKTOP}
    try:
        for fname in os.listdir(apps_dir):
            if not fname.endswith(".desktop"):
                continue
            try:
                with open(os.path.join(apps_dir, fname)) as f:
                    for line in f:
                        if line.strip().startswith("Exec="):
                            if "/usr/bin/dictee" in line:
                                names.add(fname)
                            break
            except OSError:
                continue
    except OSError:
        pass
    return names


def check_kde_conflict(accel_kde):
    """Vérifie si le raccourci est déjà utilisé dans kglobalshortcutsrc."""
    rc = os.path.expanduser("~/.config/kglobalshortcutsrc")
    if not os.path.isfile(rc):
        return None
    own_desktops = _dictee_desktop_names()
    try:
        with open(rc) as f:
            current_group = ""
            for line in f:
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    current_group = line[1:-1]
                    continue
                if any(d in current_group for d in own_desktops):
                    continue
                if "=" in line:
                    _key, val = line.split("=", 1)
                    parts = val.split(",")
                    if parts and parts[0].strip() == accel_kde:
                        return current_group
    except OSError:
        pass
    return None


def apply_kde_shortcut(accel_kde, desktop_name, command, label, key_sequence=None):
    """Applique le raccourci clavier sous KDE Plasma 6.

    1. Crée le .desktop dans ~/.local/share/applications/
    2. Écrit le raccourci dans kglobalshortcutsrc (persistance)
    3. Enregistre et active via D-Bus kglobalaccel (activation immédiate)
    """
    apps_dir = os.path.expanduser("~/.local/share/applications")
    os.makedirs(apps_dir, exist_ok=True)
    desktop_path = os.path.join(apps_dir, desktop_name)
    with open(desktop_path, "w") as f:
        f.write("[Desktop Entry]\n")
        f.write(f"Exec={command}\n")
        f.write(f"Name={label}\n")
        f.write("NoDisplay=true\n")
        f.write("StartupNotify=false\n")
        f.write("Type=Application\n")
        f.write("X-KDE-GlobalAccel-CommandShortcut=true\n")

    # Écrire le raccourci dans kglobalshortcutsrc (persistance au reboot)
    subprocess.run(
        [
            "kwriteconfig6",
            "--file", "kglobalshortcutsrc",
            "--group", "services",
            "--group", desktop_name,
            "--key", "_launch",
            f"{accel_kde},none,{label}",
        ],
        check=True,
    )
    subprocess.run(
        [
            "kwriteconfig6",
            "--file", "kglobalshortcutsrc",
            "--group", "services",
            "--group", desktop_name,
            "--key", "_k_friendly_name",
            label,
        ],
        check=True,
    )

    # Activer immédiatement via D-Bus kglobalaccel
    if key_sequence is not None:
        _activate_kde_shortcut_dbus(desktop_name, label, key_sequence)

    return accel_kde


def _activate_kde_shortcut_dbus(desktop_name, label, key_sequence):
    """Active un raccourci via D-Bus kglobalaccel (sans redémarrage de session).

    Utilise doRegister + setForeignShortcutKeys pour enregistrer le composant
    et activer la touche immédiatement dans kglobalacceld.
    """
    # Convertir QKeySequence en code Qt int (modifiers | key)
    try:
        combined = key_sequence[0]
        # PyQt6 : QKeyCombination → .toCombined() → int
        if hasattr(combined, "toCombined"):
            qt_key_int = combined.toCombined()
        # PySide6 : déjà int ou enum avec .value
        elif hasattr(combined, "value"):
            qt_key_int = combined.value
        else:
            qt_key_int = int(combined)
    except (IndexError, TypeError):
        return  # Pas de touche valide

    action_id = f"['{desktop_name}', '_launch', '{label}', '{label}']"

    # 1. Enregistrer le composant
    subprocess.run(
        [
            "gdbus", "call", "--session",
            "--dest", "org.kde.kglobalaccel",
            "--object-path", "/kglobalaccel",
            "--method", "org.kde.KGlobalAccel.doRegister",
            action_id,
        ],
        capture_output=True,
    )

    # 2. Affecter la touche
    keys = f"[([{qt_key_int}, 0, 0, 0],)]"
    subprocess.run(
        [
            "gdbus", "call", "--session",
            "--dest", "org.kde.kglobalaccel",
            "--object-path", "/kglobalaccel",
            "--method", "org.kde.KGlobalAccel.setForeignShortcutKeys",
            action_id,
            keys,
        ],
        capture_output=True,
    )


def remove_kde_shortcut(desktop_name):
    """Supprime un raccourci KDE global (désactive via D-Bus + nettoie kglobalshortcutsrc)."""
    # Supprimer de kglobalshortcutsrc
    subprocess.run(
        ["kwriteconfig6", "--file", "kglobalshortcutsrc",
         "--group", "services", "--group", desktop_name,
         "--key", "_launch", "--delete"],
        capture_output=True,
    )
    # Désactiver via D-Bus (touche vide = aucun raccourci)
    action_id = f"['{desktop_name}', '_launch', '', '']"
    keys = "[([0, 0, 0, 0],)]"
    subprocess.run(
        ["gdbus", "call", "--session",
         "--dest", "org.kde.kglobalaccel",
         "--object-path", "/kglobalaccel",
         "--method", "org.kde.KGlobalAccel.setForeignShortcutKeys",
         action_id, keys],
        capture_output=True,
    )


# === Raccourci GNOME ===


def qt_key_to_gnome(key_sequence):
    """Convertit une QKeySequence en format GNOME ('<Super>d')."""
    s = key_sequence.toString()
    s = s.replace("Meta+", "<Super>")
    s = s.replace("Ctrl+", "<Primary>")
    s = s.replace("Alt+", "<Alt>")
    s = s.replace("Shift+", "<Shift>")
    if not s.endswith(">"):
        parts = s.rsplit(">", 1)
        if len(parts) == 2:
            s = parts[0] + ">" + parts[1].lower()
    return s


def apply_gnome_shortcut(accel_gnome):
    """Applique le raccourci clavier sous GNOME/Unity/Cinnamon."""
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    base_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
    slot = "dictee"
    path = f"{base_path}/{slot}/"

    try:
        result = subprocess.run(
            ["gsettings", "get", schema, "custom-keybindings"],
            capture_output=True, text=True, check=True,
        )
        current = result.stdout.strip()
        if path not in current:
            if current in ("@as []", "[]"):
                new_list = f"['{path}']"
            else:
                new_list = current.rstrip("]") + f", '{path}']"
            subprocess.run(
                ["gsettings", "set", schema, "custom-keybindings", new_list],
                check=True,
            )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    sub_schema = f"{schema}.custom-keybinding"
    subprocess.run(
        ["gsettings", "set", sub_schema + ":" + path, "name", _("Voice dictation")],
        check=True,
    )
    subprocess.run(
        ["gsettings", "set", sub_schema + ":" + path, "command", DICTEE_COMMAND],
        check=True,
    )
    subprocess.run(
        ["gsettings", "set", sub_schema + ":" + path, "binding", accel_gnome],
        check=True,
    )


# === Ollama helpers ===

# (model_id, label, min_ram_gb, min_vram_gb)
OLLAMA_MODELS = [
    ("translategemma", _("translategemma 4B (3.3 GB, 55 languages, 8 GB RAM)"), 8, 4),
    ("translategemma:12b", _("translategemma 12B (8 GB, best quality, 16 GB RAM)"), 16, 8),
    ("aya:8b", _("aya 8B (5 GB, Cohere, 23 languages, 16 GB RAM)"), 16, 8),
]


def ollama_is_installed():
    """Vérifie si ollama est installé."""
    return shutil.which("ollama") is not None


def get_system_ram_gb():
    """Retourne la RAM totale en Go."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024 / 1024, 1)
    except (OSError, ValueError):
        pass
    return 0


def get_gpu_vram_gb():
    """Retourne (VRAM totale, VRAM libre) en Go. (0, 0) si pas de GPU."""
    # NVIDIA
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("\n")[0].split(",")
            total_mb = int(parts[0].strip())
            free_mb = int(parts[1].strip())
            return round(total_mb / 1024, 1), round(free_mb / 1024, 1)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        pass
    # AMD
    try:
        import glob
        for path in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
            total = int(open(path).read().strip())
            free_path = path.replace("vram_total", "vram_used")
            used = int(open(free_path).read().strip()) if os.path.exists(free_path) else 0
            total_gb = round(total / 1024**3, 1)
            free_gb = round((total - used) / 1024**3, 1)
            return total_gb, free_gb
    except (OSError, ValueError):
        pass
    return 0, 0


def ollama_list_models():
    """Retourne la liste des modèles ollama installés."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            models = []
            for line in result.stdout.strip().split("\n")[1:]:  # skip header
                if line.strip():
                    models.append(line.split()[0].split(":")[0])
            return models
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []


def ollama_has_model(model_name):
    """Vérifie si un modèle ollama spécifique est installé."""
    installed = ollama_list_models()
    # Normaliser : "translategemma" → "translategemma:latest"
    def _normalize(name):
        return name if ":" in name else name + ":latest"
    target = _normalize(model_name)
    return any(_normalize(m) == target for m in installed)


class OllamaPullThread(QThread):
    """Thread pour télécharger un modèle ollama."""
    finished = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name

    def run(self):
        try:
            self.progress.emit(_("Downloading {model}…").format(model=self.model_name))
            result = subprocess.run(
                ["ollama", "pull", self.model_name],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, result.stderr.strip() or _("Download failed."))
        except subprocess.TimeoutExpired:
            self.finished.emit(False, _("Download timed out (10 min)."))
        except Exception as e:
            self.finished.emit(False, str(e))


# === Modèles ASR ===

MODEL_DIR = "/usr/share/dictee"
DICTEE_DATA_DIR = os.path.expanduser("~/.local/share/dictee")

# === Logo SVG (fichiers assets/) ===

def _find_assets_dir():
    """Trouve le répertoire assets/ contenant les bannières SVG."""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"),
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "assets"),
        "/usr/share/dictee/assets",
        os.path.expanduser("~/.local/share/dictee/assets"),
    ]
    for d in candidates:
        if os.path.isfile(os.path.join(d, "banner-dark.svg")):
            return d
    return None

ASSETS_DIR = _find_assets_dir()

# === Backends ASR alternatifs (venvs) ===

VOSK_VENV = os.path.join(DICTEE_DATA_DIR, "vosk-env")
WHISPER_VENV = os.path.join(DICTEE_DATA_DIR, "whisper-env")

VOSK_MODELS = {
    "fr": "vosk-model-small-fr-0.22",
    "en": "vosk-model-small-en-us-0.15",
    "de": "vosk-model-small-de-0.15",
    "es": "vosk-model-small-es-0.42",
    "it": "vosk-model-small-it-0.22",
    "pt": "vosk-model-small-pt-0.3",
    "ru": "vosk-model-small-ru-0.22",
    "zh": "vosk-model-small-cn-0.22",
    "ja": "vosk-model-small-ja-0.22",
}

WHISPER_MODELS = ["tiny", "small", "medium", "large-v3"]


def venv_is_installed(venv_path):
    """Vérifie si un venv Python est installé et contient des packages."""
    site = os.path.join(venv_path, "lib")
    if not os.path.isdir(site):
        return False
    for d in os.listdir(site):
        sp = os.path.join(site, d, "site-packages")
        if os.path.isdir(sp) and len(os.listdir(sp)) > 3:
            return True
    return False


class VenvInstallThread(QThread):
    """Thread pour créer un venv et installer un package pip."""
    finished = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, venv_path, pip_package):
        super().__init__()
        self.venv_path = venv_path
        self.pip_package = pip_package

    def run(self):
        try:
            self.progress.emit(_("Creating virtual environment…"))
            os.makedirs(self.venv_path, exist_ok=True)
            result = subprocess.run(
                ["python3", "-m", "venv", self.venv_path],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                self.finished.emit(False, result.stderr.strip())
                return
            pip = os.path.join(self.venv_path, "bin", "pip")
            self.progress.emit(_("Installing {pkg}…").format(pkg=self.pip_package))
            result = subprocess.run(
                [pip, "install", "--upgrade", self.pip_package],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                self.finished.emit(False, result.stderr.strip()[-500:])
                return
            self.finished.emit(True, "")
        except subprocess.TimeoutExpired:
            self.finished.emit(False, _("Installation timed out."))
        except Exception as e:
            self.finished.emit(False, str(e))

ASR_MODELS = [
    {
        "id": "tdt",
        "name": "Parakeet-TDT 0.6B v3",
        "desc": _("Multilingual transcription (25 languages, ~2.5 GB)"),
        "help": _(
            "<b>Parakeet-TDT 0.6B v3</b> — Main transcription model<br><br>"
            "FastConformer encoder + Token-and-Duration Transducer (TDT) decoder.<br>"
            "Supports <b>25 languages</b> including French, English, Spanish, German, etc.<br>"
            "Native punctuation and capitalization (no post-processing needed).<br><br>"
            "<b>Required</b> for all transcription modes (dictation, batch, daemon).<br>"
            "Used by: <code>transcribe</code>, <code>transcribe-daemon</code>, "
            "<code>transcribe-diarize</code>, <code>dictee</code>"
        ),
        "dir": os.path.join(MODEL_DIR, "tdt"),
        "check_file": "encoder-model.onnx",
        "files": [
            ("https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/encoder-model.onnx", "encoder-model.onnx"),
            ("https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/encoder-model.onnx.data", "encoder-model.onnx.data"),
            ("https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/decoder_joint-model.onnx", "decoder_joint-model.onnx"),
            ("https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/vocab.txt", "vocab.txt"),
        ],
        "required": True,
    },
    {
        "id": "sortformer",
        "name": "Sortformer",
        "desc": _("Speaker diarization (4 speakers max, ~50 MB)"),
        "help": _(
            "<b>Sortformer</b> — Speaker diarization model<br><br>"
            "Identifies and separates up to <b>4 different speakers</b> in an audio recording.<br>"
            "Labels each transcription segment with the speaker who said it.<br><br>"
            "<b>Optional</b> — only needed if you want speaker identification.<br>"
            "Used by: <code>transcribe-diarize</code>, <code>transcribe-stream-diarize</code>"
        ),
        "dir": os.path.join(MODEL_DIR, "sortformer"),
        "check_file": "diar_streaming_sortformer_4spk-v2.1.onnx",
        "files": [
            ("https://huggingface.co/altunenes/parakeet-rs/resolve/main/diar_streaming_sortformer_4spk-v2.1.onnx", "diar_streaming_sortformer_4spk-v2.1.onnx"),
        ],
        "required": False,
    },
    {
        "id": "nemotron",
        "name": "Nemotron 0.6B",
        "desc": _("English streaming (~2.5 GB)"),
        "help": _(
            "<b>Nemotron 0.6B</b> — English streaming model<br><br>"
            "Optimized for <b>real-time English</b> transcription with low latency.<br>"
            "Processes audio in streaming chunks instead of waiting for the full recording.<br><br>"
            "<b>Optional</b> — only needed for English streaming + diarization mode.<br>"
            "Used by: <code>transcribe-stream-diarize</code>"
        ),
        "dir": os.path.join(MODEL_DIR, "nemotron"),
        "check_file": "encoder.onnx",
        "files": [
            ("https://huggingface.co/altunenes/parakeet-rs/resolve/main/nemotron-speech-streaming-en-0.6b/encoder.onnx", "encoder.onnx"),
            ("https://huggingface.co/altunenes/parakeet-rs/resolve/main/nemotron-speech-streaming-en-0.6b/encoder.onnx.data", "encoder.onnx.data"),
            ("https://huggingface.co/altunenes/parakeet-rs/resolve/main/nemotron-speech-streaming-en-0.6b/decoder_joint.onnx", "decoder_joint.onnx"),
            ("https://huggingface.co/altunenes/parakeet-rs/resolve/main/nemotron-speech-streaming-en-0.6b/tokenizer.model", "tokenizer.model"),
        ],
        "required": False,
    },
]


def model_is_installed(model):
    """Vérifie si un modèle ASR est installé."""
    return os.path.isfile(os.path.join(model["dir"], model["check_file"]))


class ModelDownloadThread(QThread):
    """Thread pour télécharger un modèle ASR."""
    finished = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, model):
        super().__init__()
        self.model = model

    def run(self):
        import urllib.request
        try:
            model_dir = self.model["dir"]
            os.makedirs(model_dir, exist_ok=True)
            total_files = len([f for f in self.model["files"]
                               if not os.path.isfile(os.path.join(model_dir, f[1]))])
            done = 0
            for url, filename in self.model["files"]:
                dest = os.path.join(model_dir, filename)
                if os.path.isfile(dest):
                    continue
                self.progress.emit(_("Downloading {name}…").format(name=filename))
                resp = urllib.request.urlopen(url, timeout=1800)
                total_size = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(dest, "wb") as f:
                    while True:
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int(downloaded * 100 / total_size)
                            size_mb = downloaded / (1024 * 1024)
                            total_mb = total_size / (1024 * 1024)
                            self.progress.emit(
                                f"{filename}  {pct}%  ({size_mb:.0f}/{total_mb:.0f} Mo)")
                done += 1
                if total_files > 1:
                    self.progress.emit(_("Downloaded {done}/{total}").format(
                        done=done, total=total_files))
            self.finished.emit(True, "")
        except PermissionError:
            self.finished.emit(False, _("Permission denied. Run: sudo chmod 777 {dir}").format(
                dir=self.model["dir"]))
        except Exception as e:
            self.finished.emit(False, str(e))


# === LibreTranslate (Docker) ===

LIBRETRANSLATE_IMAGE = "libretranslate/libretranslate"
LIBRETRANSLATE_CONTAINER = "dictee-libretranslate"
LIBRETRANSLATE_PORT = 5000


def docker_is_installed():
    """Vérifie si docker est installé et accessible."""
    return shutil.which("docker") is not None


def docker_is_accessible():
    """Vérifie si l'utilisateur peut exécuter docker (permissions)."""
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def docker_has_image(image=LIBRETRANSLATE_IMAGE):
    """Vérifie si l'image Docker est téléchargée."""
    try:
        result = subprocess.run(
            ["docker", "images", "-q", image],
            capture_output=True, text=True, timeout=5,
        )
        return bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def docker_container_running(name=LIBRETRANSLATE_CONTAINER):
    """Vérifie si le container est en cours d'exécution."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() == "true"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def docker_container_exists(name=LIBRETRANSLATE_CONTAINER):
    """Vérifie si le container existe (arrêté ou en cours)."""
    try:
        result = subprocess.run(
            ["docker", "inspect", name],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


_lt_langs_cache = {"langs": [], "time": 0, "port": 0}


def libretranslate_available_languages(port=LIBRETRANSLATE_PORT, max_age=5):
    """Récupère la liste des codes langues disponibles dans LibreTranslate.
    Cache le résultat pendant max_age secondes pour éviter de bloquer l'UI."""
    import time as _time
    now = _time.monotonic()
    if (_lt_langs_cache["port"] == port
            and _lt_langs_cache["langs"]
            and now - _lt_langs_cache["time"] < max_age):
        return _lt_langs_cache["langs"]
    try:
        import urllib.request, json as _json
        url = f"http://localhost:{port}/languages"
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = _json.loads(resp.read())
            result = [lang["code"] for lang in data]
            _lt_langs_cache.update({"langs": result, "time": now, "port": port})
            return result
    except Exception:
        return []


def docker_start_libretranslate(port=LIBRETRANSLATE_PORT, languages="fr,en,es,de"):
    """Démarre le container LibreTranslate. Recrée si les langues ont changé."""
    if docker_container_exists():
        # Vérifier si les langues du conteneur existant correspondent
        needs_recreate = False
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.Args}}", LIBRETRANSLATE_CONTAINER],
                capture_output=True, text=True, timeout=5,
            )
            current_args = result.stdout.strip()
            if f"--load-only {languages}" not in current_args:
                needs_recreate = True
        except Exception:
            needs_recreate = True  # En cas de doute, recréer
        if needs_recreate:
            subprocess.run(["docker", "rm", "-f", LIBRETRANSLATE_CONTAINER],
                           capture_output=True, timeout=10)
            subprocess.run([
                "docker", "run", "-d",
                "--name", LIBRETRANSLATE_CONTAINER,
                "-p", f"{port}:5000",
                "--restart", "unless-stopped",
                LIBRETRANSLATE_IMAGE,
                "--load-only", languages,
            ], capture_output=True, timeout=30)
            return
        subprocess.run(["docker", "start", LIBRETRANSLATE_CONTAINER],
                       capture_output=True, timeout=10)
    else:
        subprocess.run([
            "docker", "run", "-d",
            "--name", LIBRETRANSLATE_CONTAINER,
            "-p", f"{port}:5000",
            "--restart", "unless-stopped",
            LIBRETRANSLATE_IMAGE,
            "--load-only", languages,
        ], capture_output=True, timeout=30)


def docker_stop_libretranslate():
    """Arrête le container LibreTranslate."""
    subprocess.run(["docker", "stop", LIBRETRANSLATE_CONTAINER],
                   capture_output=True, timeout=15)


def _docker_container_size():
    """Retourne la taille du conteneur LibreTranslate (ex: '1.2 GB')."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-s", "--filter", f"name={LIBRETRANSLATE_CONTAINER}",
             "--format", "{{.Size}}"],
            capture_output=True, text=True, timeout=5)
        size_str = result.stdout.strip()
        if size_str:
            # Format: "479MB (virtual 1.16GB)" → on prend "virtual 1.16GB"
            if "virtual" in size_str:
                import re
                m = re.search(r'virtual\s+([\d.]+\s*[KMGT]B)', size_str)
                if m:
                    return m.group(1)
            return size_str
    except Exception:
        pass
    return ""


class DockerPullThread(QThread):
    """Thread pour télécharger l'image Docker LibreTranslate."""
    finished = Signal(bool, str)
    progress = Signal(str)

    def run(self):
        try:
            self.progress.emit(_("Downloading Docker image…"))
            result = subprocess.run(
                ["docker", "pull", LIBRETRANSLATE_IMAGE],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, result.stderr.strip() or _("Download failed."))
        except subprocess.TimeoutExpired:
            self.finished.emit(False, _("Download timed out (10 min)."))
        except Exception as e:
            self.finished.emit(False, str(e))


class _VoskModelDownloadThread(QThread):
    """Thread pour télécharger un modèle Vosk."""
    finished = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, model_name):
        super().__init__()
        self._model_name = model_name

    def run(self):
        import zipfile
        from urllib.request import urlretrieve
        try:
            base = os.path.join(DICTEE_DATA_DIR, "vosk-models")
            os.makedirs(base, exist_ok=True)
            url = f"https://alphacephei.com/vosk/models/{self._model_name}.zip"
            zip_path = os.path.join(base, f"{self._model_name}.zip")

            self.progress.emit(_("Downloading {name}…").format(name=self._model_name))

            def _reporthook(block, block_size, total):
                downloaded = block * block_size
                if total > 0:
                    pct = min(100, downloaded * 100 // total)
                    mb = downloaded / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    self.progress.emit(f"{pct}% ({mb:.0f}/{total_mb:.0f} MB)")

            urlretrieve(url, zip_path, _reporthook)
            self.progress.emit(_("Extracting…"))
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(base)
            os.remove(zip_path)
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))


class _DockerActionThread(QThread):
    """Thread pour démarrer/arrêter LibreTranslate sans bloquer l'UI."""
    finished = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, action, port=LIBRETRANSLATE_PORT, languages="fr,en,es,de"):
        super().__init__()
        self._action = action
        self._port = port
        self._languages = languages

    def run(self):
        try:
            if self._action == "start":
                self.progress.emit(_("Starting container…"))
                docker_start_libretranslate(port=self._port, languages=self._languages)
                self._wait_ready()
            elif self._action == "restart":
                self.progress.emit(_("Stopping container…"))
                subprocess.run(["docker", "rm", "-f", LIBRETRANSLATE_CONTAINER],
                               capture_output=True, timeout=15)
                self.progress.emit(_("Starting container with {langs}…").format(
                    langs=self._languages))
                result = subprocess.run([
                    "docker", "run", "-d",
                    "--name", LIBRETRANSLATE_CONTAINER,
                    "-p", f"{self._port}:5000",
                    "--restart", "unless-stopped",
                    LIBRETRANSLATE_IMAGE,
                    "--load-only", self._languages,
                ], capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    self.finished.emit(False, result.stderr.strip() or _("Docker run failed."))
                    return
                self._wait_ready()
            else:
                self.progress.emit(_("Stopping container…"))
                docker_stop_libretranslate()
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))

    def _wait_ready(self):
        """Attend que l'API LibreTranslate soit prête (max 180s).
        Détecte les crashs (réseau absent, modèle introuvable) et les remonte."""
        import time, urllib.request
        url = f"http://localhost:{self._port}/languages"
        self.progress.emit(_("Starting server…"))
        consecutive_dead = 0
        for i in range(90):
            # 1. Vérifier si le conteneur tourne encore
            try:
                state = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Running}}", LIBRETRANSLATE_CONTAINER],
                    capture_output=True, text=True, timeout=3)
                running = state.stdout.strip() == "true"
            except Exception:
                running = False
            if not running:
                consecutive_dead += 1
                if consecutive_dead >= 3:
                    error_msg = self._get_container_error()
                    raise RuntimeError(
                        _("LibreTranslate container stopped unexpectedly.") +
                        ("\n" + error_msg if error_msg else "") +
                        "\n\n" + _("Check your network connection — language models "
                                   "require a download on first use."))
            else:
                consecutive_dead = 0

            # 2. Tester si l'API répond
            try:
                with urllib.request.urlopen(url, timeout=3):
                    self.progress.emit(_("Ready!"))
                    return
            except Exception:
                pass

            # 3. Analyser les logs Docker pour afficher un message clair
            # LibreTranslate écrit les téléchargements sur stdout et le serveur sur stderr
            try:
                result = subprocess.run(
                    ["docker", "logs", "--tail", "15", LIBRETRANSLATE_CONTAINER],
                    capture_output=True, text=True, timeout=3)
                # Combiner stdout (téléchargements) + stderr (serveur)
                log_stdout = result.stdout.strip()
                log_stderr = result.stderr.strip()
                log_combined = (log_stdout + "\n" + log_stderr).strip()
                if log_combined:
                    log_lower = log_combined.lower()
                    # Détecter les erreurs réseau
                    if any(err in log_lower for err in [
                        "connectionerror", "connection refused", "network is unreachable",
                        "name resolution", "temporary failure", "no route to host",
                        "could not resolve", "urlopen error",
                    ]):
                        last_line = log_combined.split("\n")[-1]
                        raise RuntimeError(
                            _("Network error while downloading language models.") +
                            "\n" + last_line +
                            "\n\n" + _("Check your network connection and retry."))
                    # Priorité stdout (téléchargements) puis stderr (serveur)
                    msg = self._parse_lt_log(
                        log_stdout if log_stdout else log_stderr, i * 2)
                    self.progress.emit(msg)
                else:
                    self.progress.emit(_("Starting server… ({s}s)").format(s=i * 2))
            except RuntimeError:
                raise
            except Exception:
                self.progress.emit(_("Starting server… ({s}s)").format(s=i * 2))
            time.sleep(2)
        raise TimeoutError(_("LibreTranslate did not start within 3 minutes."))

    @staticmethod
    def _parse_lt_log(log_text, elapsed_s):
        """Analyse les logs LibreTranslate et retourne un message utilisateur clair."""
        import re
        # Parcourir les lignes de la plus récente à la plus ancienne
        lines = log_text.strip().split("\n")
        for line in reversed(lines):
            ll = line.lower().strip()
            if not ll:
                continue
            # "Downloading French → English (1.9) ..."
            m = re.search(r'[Dd]ownloading\s+(\w+)\s*→\s*(\w+)', line)
            if m:
                return _("Downloading: {src} → {tgt}…").format(
                    src=m.group(1), tgt=m.group(2))
            # "Downloading model: fr"
            m = re.search(r'[Dd]ownloading model:\s*(\w+)', line)
            if m:
                return _("Downloading model: {lang}…").format(lang=m.group(1))
            # "Downloading MiniSBD models"
            if "downloading" in ll:
                return _("Downloading language model…")
            # "Updating language models" / "Found 98 models" / "Keep 20 models"
            if "updating language models" in ll:
                return _("Updating language models…")
            m = re.search(r'[Ff]ound (\d+) models', line)
            if m:
                return _("Found {n} models, selecting…").format(n=m.group(1))
            if "keep" in ll and "models" in ll:
                return _("Downloading language model…")
            # "Loaded support for 9 languages (18 models total)!"
            m = re.search(r'[Ll]oaded support for (\d+) languages.*?(\d+) models', line)
            if m:
                return _("Loaded {n} languages ({m} models).").format(
                    n=m.group(1), m=m.group(2))
            # "Booting..."
            if ll == "booting...":
                return _("Starting server…")
            # "Power cycling..."
            if "power cycling" in ll:
                return _("Starting server…")
            # "Starting gunicorn" or "Listening at"
            if "starting gunicorn" in ll or "listening at" in ll:
                return _("Starting server…")
            # "Booting worker"
            if "booting worker" in ll:
                return _("Starting server…")
        # Fallback avec timer
        return _("Starting server… ({s}s)").format(s=elapsed_s)

    def _get_container_error(self):
        """Récupère les dernières lignes de log du conteneur crashé."""
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", "10", LIBRETRANSLATE_CONTAINER],
                capture_output=True, text=True, timeout=3)
            log = result.stderr.strip() or result.stdout.strip()
            if log:
                # Garder les 3 dernières lignes pertinentes
                lines = [l for l in log.split("\n") if l.strip()][-3:]
                return "\n".join(lines)
        except Exception:
            pass
        return ""


# === Thread d'installation ===


class InstallThread(QThread):
    finished = Signal(bool, str)
    progress = Signal(str)

    def run(self):
        import json
        import urllib.request
        import urllib.error
        try:
            self.progress.emit(_("Checking latest release…"))
            api_url = f"https://api.github.com/repos/{ANIMATION_SPEECH_REPO}/releases/latest"
            req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json"})
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    release = json.loads(resp.read().decode())
            except urllib.error.URLError as e:
                self.finished.emit(False, _("Cannot reach GitHub: {err}").format(err=str(e)))
                return

            assets = release.get("assets", [])
            if not assets:
                self.finished.emit(False, _("No assets found in the release."))
                return

            tmp_dir = tempfile.mkdtemp(prefix="dictee-setup-")
            if shutil.which("dpkg"):
                pattern = ".deb"
            elif shutil.which("rpm"):
                pattern = ".rpm"
            else:
                pattern = ".tar.gz"

            asset = next((a for a in assets if a["name"].endswith(pattern)), None)
            if not asset:
                self.finished.emit(False,
                    _("No {pat} found in the release.").format(pat=pattern))
                return

            self.progress.emit(_("Downloading…"))
            dest = os.path.join(tmp_dir, asset["name"])
            urllib.request.urlretrieve(asset["browser_download_url"], dest)

            self.progress.emit(_("Installing…"))
            if pattern == ".deb":
                result = subprocess.run(
                    ["pkexec", "bash", "-c", f"dpkg -i '{dest}'; apt-get install -f -y"],
                    capture_output=True, text=True,
                )
            elif pattern == ".rpm":
                result = subprocess.run(
                    ["pkexec", "rpm", "-U", dest],
                    capture_output=True, text=True,
                )
            else:
                result = subprocess.run(
                    ["pkexec", "tar", "xzf", dest, "-C", "/usr/local"],
                    capture_output=True, text=True,
                )

            # Nettoyage
            try:
                for f in os.listdir(tmp_dir):
                    os.remove(os.path.join(tmp_dir, f))
                os.rmdir(tmp_dir)
            except OSError:
                pass

            if result.returncode == 0:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, result.stderr.strip() or _("Installation error."))

        except Exception as e:
            self.finished.emit(False, str(e))


# === Bouton capture raccourci ===


class ShortcutButton(QPushButton):
    """Bouton qui capture une combinaison de touches quand activé."""

    shortcutCaptured = Signal(QKeySequence)

    def __init__(self, parent=None):
        super().__init__(_("Click to capture a shortcut…"), parent)
        self._capturing = False
        self._sequence = None
        self._changed = False
        self.clicked.connect(self._start_capture)

    def _start_capture(self):
        self._capturing = True
        self.setText(_("Press a key combination…"))
        self.setFocus()

    def keyPressEvent(self, event):
        if not self._capturing:
            super().keyPressEvent(event)
            return

        key = event.key()

        # Ignorer les modificateurs seuls
        # PyQt6 : enums scoped (Qt.Key.Key_X), PySide6 : enums flat (Qt.Key_X)
        _Key = getattr(Qt, "Key", Qt)
        if key in (
            _Key.Key_Shift, _Key.Key_Control, _Key.Key_Alt,
            _Key.Key_Meta, _Key.Key_Super_L, _Key.Key_Super_R,
            _Key.Key_AltGr,
        ):
            return

        modifiers = event.modifiers()
        # PyQt6 : .value pour convertir en int, PySide6 : déjà int
        key_int = key.value if hasattr(key, "value") else int(key)
        mod_int = modifiers.value if hasattr(modifiers, "value") else int(modifiers)
        seq = QKeySequence(mod_int | key_int)

        self._capturing = False
        self._sequence = seq
        self._changed = True
        self.setText(_("Shortcut: {label}").format(label=seq.toString(_NATIVE_TEXT)))
        self.shortcutCaptured.emit(seq)

    def sequence(self):
        return self._sequence


# === Audio sources ===




class LevelMeter(QWidget):
    """VU-mètre custom — rendu direct QPainter, très réactif."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0
        self.setFixedHeight(14)
        self.setMinimumWidth(60)

    def setLevel(self, value):
        self._level = max(0, min(100, value))
        self.repaint()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # Background
        p.setBrush(QColor(26, 26, 46))
        p.setPen(QColor(85, 85, 85))
        p.drawRoundedRect(0, 0, w - 1, h - 1, 4, 4)
        # Bar
        bar_w = int((w - 4) * self._level / 100)
        if bar_w > 0:
            grad = QLinearGradient(2, 0, w - 2, 0)
            grad.setColorAt(0.0, QColor(34, 204, 68))
            grad.setColorAt(0.6, QColor(170, 204, 34))
            grad.setColorAt(1.0, QColor(238, 68, 34))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawRoundedRect(2, 2, bar_w, h - 4, 3, 3)
        p.end()


class AudioLevelMonitor:
    """VU-mètre via Qt Multimedia — QAudioSource + readyRead, zéro thread."""

    def __init__(self, meter, device=None):
        self._meter = meter
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if device is None:
            device = QMediaDevices.defaultAudioInput()
        self._source = QAudioSource(device, fmt)
        self._io = None

    def start(self):
        self._io = self._source.start()
        if self._io:
            self._io.readyRead.connect(self._on_data)

    def stop(self):
        self._source.stop()
        self._io = None

    def _on_data(self):
        if not self._io:
            return
        data = self._io.readAll().data()
        n = len(data) // 2
        if n > 0:
            samples = struct.unpack(f"<{n}h", data[:n * 2])
            rms = math.sqrt(sum(s * s for s in samples) / n)
            if rms > 1:
                db = 20 * math.log10(rms / 32767)
                level = max(0, min(100, int((db + 50) * 2)))
            else:
                level = 0
            self._meter.setLevel(level)


class TestDicteeThread(QThread):
    """Enregistre le micro puis transcrit via transcribe-client <fichier>."""
    result = Signal(str)

    def __init__(self, duration=5, postprocess=False, parent=None):
        super().__init__(parent)
        self._rec_proc = None
        self._duration = duration
        self._postprocess = postprocess
        self._stopped = False

    def stop(self):
        self._stopped = True
        if self._rec_proc and self._rec_proc.poll() is None:
            self._rec_proc.terminate()
            try:
                self._rec_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._rec_proc.kill()

    def run(self):
        wav_path = os.path.join(tempfile.gettempdir(), "dictee_test.wav")
        try:
            # Enregistrer le micro
            if shutil.which("pw-record"):
                cmd = ["pw-record", "--format=s16", "--rate=16000", "--channels=1",
                       wav_path]
            elif shutil.which("parecord"):
                cmd = ["parecord", "--format=s16le", "--rate=16000", "--channels=1",
                       "--file-format=wav", wav_path]
            else:
                self.result.emit(_("Error: ") + "pw-record / parecord not found")
                return

            self._rec_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Attendre la durée demandée
            try:
                self._rec_proc.wait(timeout=self._duration)
            except subprocess.TimeoutExpired:
                self._rec_proc.terminate()
                self._rec_proc.wait(timeout=3)

            if self._stopped:
                return

            if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
                self.result.emit(_("Error: ") + _("No audio recorded."))
                return

            # Transcrire via transcribe-client <fichier>
            r = subprocess.run(
                ["transcribe-client", wav_path],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0 and r.stdout.strip():
                text = r.stdout.strip()
                if self._postprocess and shutil.which("dictee-postprocess"):
                    pp = subprocess.run(
                        ["dictee-postprocess"],
                        input=text, capture_output=True, text=True, timeout=15,
                    )
                    if pp.returncode == 0 and pp.stdout.strip():
                        text = pp.stdout.strip()
                self.result.emit(text)
            elif r.stderr.strip():
                self.result.emit(_("Error: ") + r.stderr.strip())
            else:
                self.result.emit(_("No transcription result."))

        except subprocess.TimeoutExpired:
            self.result.emit(_("Timeout ({duration}s)").format(duration=self._duration))
        except FileNotFoundError as e:
            self.result.emit(_("Error: ") + str(e))
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass


# === UI ===


class ScrollGuardFilter(QObject):
    """Empêche les QComboBox/QSlider/QSpinBox de capturer le scroll quand ils n'ont pas le focus."""
    def eventFilter(self, obj, event):
        if event.type() == event.Type.Wheel and not obj.hasFocus():
            event.ignore()
            return True
        return False


class DicteeSetupDialog(QDialog):
    def __init__(self, wizard=False, open_postprocess=False):
        super().__init__()
        self.wizard_mode = wizard or not os.path.exists(CONF_PATH)
        self.setWindowTitle(_("Voice dictation configuration"))
        self.setMinimumSize(710, 680)
        self.resize(710, 700)
        self.setWindowIcon(QIcon.fromTheme("dictee-setup"))
        self.de_name, self.de_type = detect_desktop()
        self._install_thread = None
        self._model_widgets = {}
        self._model_threads = {}
        self._venv_threads = {}
        self._audio_monitor = None
        self._test_thread = None
        self._dirty = True  # config non enregistrée au départ
        self._open_postprocess = open_postprocess

        self.conf = load_config()

        if self.wizard_mode:
            self._build_wizard_ui()
        else:
            self._build_classic_ui()

        # Empêcher le scroll accidentel sur les widgets interactifs
        self._scroll_guard = ScrollGuardFilter(self)
        for w in self.findChildren((QComboBox, QSlider)):
            w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            w.installEventFilter(self._scroll_guard)

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, '_open_postprocess', False):
            self._open_postprocess = False
            QTimer.singleShot(100, self._open_postprocess_dialog)

    def _open_postprocess_dialog(self):
        """Ouvre la fenêtre post-traitement dans un dialogue séparé (réutilisé)."""
        if hasattr(self, '_pp_dialog') and self._pp_dialog is not None:
            self._pp_dialog.show()
            self._pp_dialog.raise_()
            self._pp_dialog.activateWindow()
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(_("Post-processing"))
        dlg.resize(1000, 700)
        dlg.setMinimumSize(800, 500)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(6)
        lay.setContentsMargins(16, 16, 16, 12)
        self._build_postprocess_section(lay, self.conf)
        self._pp_dialog = dlg
        dlg.show()

    # ── Classic mode ──────────────────────────────────────────────

    def _build_classic_ui(self):
        conf = self.conf
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._main_scroll = scroll
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 16)

        # -- Section backend ASR --
        grp_asr = QGroupBox(_("ASR backend"))
        lay_asr = QVBoxLayout(grp_asr)
        lay_asr.setSpacing(8)
        lay_asr.setContentsMargins(16, 16, 16, 12)

        current_asr = conf.get("DICTEE_ASR_BACKEND", "parakeet")
        self.cmb_asr_backend = QComboBox()
        self.cmb_asr_backend.addItem("Parakeet-TDT 0.6B", "parakeet")
        self.cmb_asr_backend.addItem("Vosk", "vosk")
        self.cmb_asr_backend.addItem("faster-whisper", "whisper")
        self._set_combo_by_data(self.cmb_asr_backend, current_asr, 0)
        lay_asr.addWidget(self.cmb_asr_backend)

        self._build_parakeet_options(lay_asr)
        self._build_vosk_options(lay_asr)
        self._build_whisper_options(lay_asr)

        def _on_asr_changed():
            backend = self.cmb_asr_backend.currentData()
            self.w_parakeet_options.setVisible(backend == "parakeet")
            self.w_vosk_options.setVisible(backend == "vosk")
            self.w_whisper_options.setVisible(backend == "whisper")
            if hasattr(self, 'combo_src'):
                self._update_src_languages()
        self.cmb_asr_backend.currentIndexChanged.connect(lambda: _on_asr_changed())
        _on_asr_changed()

        layout.addWidget(grp_asr)

        # -- Section raccourci --
        grp_shortcut = QGroupBox(_("Keyboard shortcut"))
        lay_sc = QVBoxLayout(grp_shortcut)
        lay_sc.setSpacing(8)
        lay_sc.setContentsMargins(16, 16, 16, 12)
        self._build_shortcut_section(lay_sc)
        layout.addWidget(grp_shortcut)

        # -- Section retour visuel --
        grp_visual = QGroupBox(_("Visual feedback"))
        lay_vis = QVBoxLayout(grp_visual)
        lay_vis.setSpacing(6)
        lay_vis.setContentsMargins(16, 16, 16, 12)
        self._build_visual_section(lay_vis, conf)
        layout.addWidget(grp_visual)

        # -- Section traduction --
        grp_translate = QGroupBox()
        lay_tr = QVBoxLayout(grp_translate)
        lay_tr.setSpacing(6)
        lay_tr.setContentsMargins(16, 16, 16, 12)
        self._build_translation_section(lay_tr, conf)
        layout.addWidget(grp_translate)

        # -- Section microphone --
        grp_mic = QGroupBox(_("Microphone"))
        lay_mic = QVBoxLayout(grp_mic)
        lay_mic.setSpacing(6)
        lay_mic.setContentsMargins(16, 16, 16, 12)
        self._build_mic_section(lay_mic, conf)
        layout.addWidget(grp_mic)

        # -- Section options --
        grp_options = QGroupBox(_("Options"))
        lay_opt = QVBoxLayout(grp_options)
        lay_opt.setSpacing(6)
        lay_opt.setContentsMargins(16, 16, 16, 12)
        self.chk_clipboard = QCheckBox(_("Copy transcription to clipboard"))
        self.chk_clipboard.setChecked(conf.get("DICTEE_CLIPBOARD", "true") == "true")
        lay_opt.addWidget(self.chk_clipboard)
        layout.addWidget(grp_options)

        # -- Section services --
        grp_services = QGroupBox(_("Startup services"))
        lay_srv = QVBoxLayout(grp_services)
        lay_srv.setSpacing(6)
        lay_srv.setContentsMargins(16, 16, 16, 12)
        self.chk_daemon = QCheckBox(_("Start transcription daemon at startup"))
        self.chk_tray = QCheckBox(_("Show notification area icon"))
        self.chk_daemon.setChecked(self._is_service_enabled("dictee"))
        self.chk_tray.setChecked(self._is_service_enabled("dictee-tray"))
        lay_srv.addWidget(self.chk_daemon)
        lay_srv.addWidget(self.chk_tray)
        layout.addWidget(grp_services)

        # -- Bouton post-traitement --
        btn_postprocess = QPushButton(_("Post-processing..."))
        accent = self.palette().color(self.palette().ColorRole.Highlight).name()
        btn_postprocess.setStyleSheet(
            f"font-weight: bold; padding: 8px 16px; font-size: 13px;")
        btn_postprocess.clicked.connect(self._open_postprocess_dialog)
        layout.addWidget(btn_postprocess)

        layout.addStretch()
        scroll.setWidget(content)
        outer_layout.addWidget(scroll, 1)

        # -- Boutons --
        lay_buttons = QHBoxLayout()
        lay_buttons.setContentsMargins(20, 8, 20, 16)

        btn_wizard = QPushButton(_("Setup wizard"))
        btn_wizard.clicked.connect(self._on_launch_wizard)
        lay_buttons.addWidget(btn_wizard)

        lay_buttons.addStretch()

        btn_cancel = QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        lay_buttons.addWidget(btn_cancel)
        lay_buttons.addSpacing(8)
        btn_apply = QPushButton(_("Apply"))
        btn_apply.clicked.connect(self._on_apply)
        lay_buttons.addWidget(btn_apply)
        lay_buttons.addSpacing(8)
        btn_ok = QPushButton(_("OK"))
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_ok)
        lay_buttons.addWidget(btn_ok)

        outer_layout.addLayout(lay_buttons)

        # Marquer _dirty dès qu'un widget de config change
        for w in content.findChildren(QComboBox):
            w.currentIndexChanged.connect(self._mark_dirty)
        for w in content.findChildren(QCheckBox):
            w.toggled.connect(self._mark_dirty)

        content_h = content.sizeHint().height()
        buttons_h = lay_buttons.sizeHint().height() if hasattr(lay_buttons, 'sizeHint') else 50
        self.setMaximumHeight(content_h + buttons_h + 10)

    def _on_launch_wizard(self):
        """Ferme le dialog et relance en mode wizard."""
        self.reject()
        exe = os.path.abspath(sys.argv[0])
        os.execv(sys.executable, [sys.executable, exe, "--wizard"])

    # ── Wizard mode ───────────────────────────────────────────────

    @staticmethod
    def _is_dark_theme():
        """Détecte si le thème Qt courant est sombre."""
        app = QApplication.instance()
        if app:
            bg = app.palette().color(app.palette().ColorRole.Window)
            return bg.lightness() < 128
        return True

    def _logo_pixmap(self, width):
        """Retourne un QPixmap du logo adapté au thème, à la largeur demandée."""
        from PyQt6.QtCore import QByteArray
        if not ASSETS_DIR:
            return QPixmap()
        fname = "banner-dark.svg" if self._is_dark_theme() else "banner-light.svg"
        svg_path = os.path.join(ASSETS_DIR, fname)
        with open(svg_path, "rb") as f:
            svg_data = f.read()
        img = QImage()
        img.loadFromData(QByteArray(svg_data))
        pix = QPixmap.fromImage(img)
        return pix.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)

    def _make_logo_header(self):
        """Crée un QLabel header avec le logo banner (200px de large)."""
        lbl = QLabel()
        lbl.setPixmap(self._logo_pixmap(200))
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl.setContentsMargins(24, 12, 24, 4)
        return lbl

    def _build_wizard_ui(self):
        conf = self.conf
        self.setWindowTitle(_("Voice dictation configuration") + " — " + _("Setup wizard"))
        self.resize(700, 600)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        # Build 6 pages (page 0 = welcome/logo)
        self._build_wizard_page0()
        self._build_wizard_page1(conf)
        self._build_wizard_page2(conf)
        self._build_wizard_page3(conf)
        self._build_wizard_page4(conf)
        self._build_wizard_page5(conf)

        # Navigation bar
        nav = QHBoxLayout()
        nav.setContentsMargins(20, 8, 20, 16)

        self.btn_prev = QPushButton(_("Previous"))
        self.btn_prev.clicked.connect(self._wizard_prev)
        nav.addWidget(self.btn_prev)

        self.lbl_step = QLabel()
        self.lbl_step.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self.lbl_step, 1)

        self.btn_next = QPushButton(_("Next"))
        self.btn_next.clicked.connect(self._wizard_next)
        nav.addWidget(self.btn_next)

        outer.addLayout(nav)
        self._update_wizard_nav()

    def _update_wizard_nav(self):
        idx = self.stack.currentIndex()
        total = self.stack.count()
        self.btn_prev.setEnabled(idx > 0)
        if idx == 0:
            self.lbl_step.setText("")
        else:
            self.lbl_step.setText(_("Step {n} of {total}").format(n=idx, total=total - 1))
        if idx == total - 1:
            self.btn_next.setText(_("Finish"))
            self.btn_next.setStyleSheet("font-weight: bold; background: #4a4; color: white; padding: 8px 20px; border-radius: 4px;")
        elif idx == 0:
            self.btn_next.setText(_("Start configuration"))
            self.btn_next.setStyleSheet("font-weight: bold; font-size: 15px; padding: 10px 28px;")
        else:
            self.btn_next.setText(_("Next"))
            self.btn_next.setStyleSheet("")
        # Start/stop audio level thread on page 4 (index 4)
        if idx == 4:
            self._start_audio_level()
        else:
            self._stop_audio_level()

    def _wizard_prev(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._update_wizard_nav()

    def _wizard_next(self):
        idx = self.stack.currentIndex()
        if idx == self.stack.count() - 1:
            self.accept()
        else:
            if not self._validate_wizard_page(idx):
                return
            self.stack.setCurrentIndex(idx + 1)
            self._update_wizard_nav()
            if idx + 1 == self.stack.count() - 1:
                # Sauver la config et démarrer les services AVANT les checks
                self._on_apply()
                self._run_wizard_checks()

    def _validate_wizard_page(self, idx):
        """Valide la page courante avant d'avancer. Retourne True si OK."""
        if idx == 1:
            # Page ASR : vérifier qu'un modèle est installé pour le backend sélectionné
            asr = self._wizard_asr
            if asr == "parakeet":
                for m in ASR_MODELS:
                    if m["required"] and not model_is_installed(m):
                        QMessageBox.warning(self, _("Model required"),
                            _("Please download the required model before continuing."))
                        return False
        return True

    # -- Project logos grid --

    def _build_project_logos(self):
        """Grille de logos des projets sous-jacents pour la page d'accueil."""
        from PyQt6.QtCore import QByteArray
        if not ASSETS_DIR:
            return None
        logos_dir = os.path.join(ASSETS_DIR, "logos")
        if not os.path.isdir(logos_dir):
            return None

        projects = [
            ("parakeet.svg", "Parakeet"),
            ("kde-plasma.svg", "Plasma 6 plasmoid"),
            ("libretranslate.svg", "LibreTranslate"),
        ]

        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(16)
        grid.setContentsMargins(0, 0, 0, 0)

        col = 0
        row = 0
        for fname, label_text in projects:
            svg_path = os.path.join(logos_dir, fname)
            if not os.path.isfile(svg_path):
                continue

            # Charger le SVG
            with open(svg_path, "rb") as f:
                svg_data = f.read()
            img = QImage()
            img.loadFromData(QByteArray(svg_data))
            pix = QPixmap.fromImage(img)
            pix = pix.scaledToWidth(64, Qt.TransformationMode.SmoothTransformation)

            # Widget empilé : icône + nom
            cell = QWidget()
            cell_lay = QVBoxLayout(cell)
            cell_lay.setSpacing(4)
            cell_lay.setContentsMargins(8, 4, 8, 4)

            lbl_icon = QLabel()
            lbl_icon.setPixmap(pix)
            lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_lay.addWidget(lbl_icon)

            lbl_name = QLabel(label_text)
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_name.setStyleSheet("font-size: 13px; opacity: 0.7;")
            cell_lay.addWidget(lbl_name)

            grid.addWidget(cell, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1

        # Centrer la rangée du bas (2 éléments sur 3 colonnes)
        if row == 1 and col <= 2:
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(2, 1)

        # Wrapper pour centrer horizontalement la grille
        wrapper = QWidget()
        wrapper_lay = QHBoxLayout(wrapper)
        wrapper_lay.setContentsMargins(0, 0, 0, 0)
        wrapper_lay.addStretch()
        wrapper_lay.addWidget(container)
        wrapper_lay.addStretch()
        return wrapper

    # -- Wizard Page 0: Welcome / Logo --

    def _build_wizard_page0(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(20)
        lay.setContentsMargins(32, 24, 32, 24)

        lay.addStretch(2)

        # Logo banner à gauche (grand)
        lbl_logo = QLabel()
        lbl_logo.setPixmap(self._logo_pixmap(560))
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(lbl_logo)

        # Version
        lbl_ver = QLabel("v1.1.0")
        lbl_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ver.setStyleSheet("font-size: 14px; opacity: 0.5;")
        lay.addWidget(lbl_ver)

        lay.addSpacing(16)

        # Grille de logos des projets sous-jacents
        logos_widget = self._build_project_logos()
        if logos_widget:
            lay.addWidget(logos_widget)

        lay.addSpacing(16)

        # Tagline — headline + subtitle
        lbl_headline = QLabel(
            "<p style='font-size: 22px; font-weight: bold;'>"
            + _("Speak freely, type instantly") + "</p>")
        lbl_headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_headline)

        lbl_sub = QLabel(
            "<p style='font-size: 17px;'>"
            + _("100% local voice dictation for Linux with 25+ languages, "
                "translation, and real-time visual feedback.") + "</p>")
        lbl_sub.setWordWrap(True)
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_sub)

        lay.addStretch(3)
        self.stack.addWidget(page)

    # -- Wizard Page 1: ASR --

    def _build_wizard_page1(self, conf):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.setContentsMargins(24, 0, 24, 16)

        # Header logo compact
        lay.addWidget(self._make_logo_header())

        lbl_asr = QLabel("<b>" + _("Choose a speech recognition engine:") + "</b>")
        lay.addWidget(lbl_asr)

        self._wizard_asr = conf.get("DICTEE_ASR_BACKEND", "parakeet")
        self._asr_cards = {}

        for backend_id, name, desc, size in [
            ("parakeet", "Parakeet-TDT 0.6B", _("25 languages, ~2.5 GB, ~0.8s") + " — " + _("recommended"), "~2.5 Go"),
            ("vosk", "Vosk", _("9+ languages, ~50 MB, ~1.5s") + " — " + _("lightweight"), "~50 Mo"),
            ("whisper", "faster-whisper", _("99 languages, ~500 MB–3 GB, ~0.3s"), "~0.5–3 Go"),
        ]:
            card = self._make_radio_card(name, desc, backend_id == self._wizard_asr)
            card.mousePressEvent = lambda e, bid=backend_id: self._select_asr_radio(bid)
            self._asr_cards[backend_id] = card
            lay.addWidget(card)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("QFrame { color: #444; }")
        lay.addWidget(sep)

        # Sub-options container
        self.w_wizard_asr_sub = QWidget()
        lay_sub = QVBoxLayout(self.w_wizard_asr_sub)
        lay_sub.setContentsMargins(16, 0, 0, 0)
        lay_sub.setSpacing(4)

        # Parakeet models
        self._build_parakeet_options(lay_sub)

        # Vosk options
        self._build_vosk_options(lay_sub)

        # Whisper options
        self._build_whisper_options(lay_sub)

        lay.addWidget(self.w_wizard_asr_sub)
        self._update_asr_sub_visibility()

        lay.addStretch()
        self.stack.addWidget(page)

    def _update_asr_sub_visibility(self):
        asr = self._wizard_asr if hasattr(self, '_wizard_asr') else "parakeet"
        self.w_parakeet_options.setVisible(asr == "parakeet")
        self.w_vosk_options.setVisible(asr == "vosk")
        self.w_whisper_options.setVisible(asr == "whisper")

    def _select_asr_radio(self, backend_id):
        self._wizard_asr = backend_id
        for bid, card in self._asr_cards.items():
            card.setStyleSheet(self._card_style(bid == backend_id))
        self._update_asr_sub_visibility()
        if hasattr(self, 'combo_src'):
            self._update_src_languages()

    # -- Wizard Page 2: Shortcuts --

    def _build_wizard_page2(self, conf):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.setContentsMargins(24, 0, 24, 16)

        lay.addWidget(self._make_logo_header())

        lbl = QLabel("<h2>" + _("Keyboard shortcuts") + "</h2>"
                     "<p>" + _("Configure the keyboard shortcuts for voice dictation.") + "</p>")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        self._build_shortcut_section(lay)

        lay.addStretch()
        self.stack.addWidget(page)

    # -- Wizard Page 3: Translation --

    def _build_wizard_page3(self, conf):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.setContentsMargins(24, 0, 24, 16)

        lay.addWidget(self._make_logo_header())

        lbl = QLabel("<h2>" + _("Translation") + "</h2>"
                     "<p>" + _("Configure the translation backend (optional).") + "</p>")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        self._build_translation_section(lay, conf)

        lay.addStretch()
        self.stack.addWidget(page)

    # -- Wizard Page 4: Mic, Visual, Services --

    def _build_wizard_page4(self, conf):
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.setSpacing(0)

        page_lay.addWidget(self._make_logo_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(16)
        lay.setContentsMargins(24, 8, 24, 16)

        # Microphone
        lbl = QLabel("<h2>" + _("Microphone, display and services") + "</h2>")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        grp_mic = QGroupBox(_("Microphone"))
        lay_mic = QVBoxLayout(grp_mic)
        lay_mic.setSpacing(6)
        lay_mic.setContentsMargins(16, 16, 16, 12)
        self._build_mic_section(lay_mic, conf)
        lay.addWidget(grp_mic)

        # Post-processing
        grp_pp = QGroupBox(_("Post-processing"))
        lay_pp = QVBoxLayout(grp_pp)
        lay_pp.setSpacing(6)
        lay_pp.setContentsMargins(16, 16, 16, 12)
        self._build_postprocess_section(lay_pp, conf)
        lay.addWidget(grp_pp)

        # Visual feedback
        grp_vis = QGroupBox(_("Visual feedback"))
        lay_vis = QVBoxLayout(grp_vis)
        lay_vis.setSpacing(6)
        lay_vis.setContentsMargins(16, 16, 16, 12)
        self._build_visual_section(lay_vis, conf)
        lay.addWidget(grp_vis)

        # Services
        grp_srv = QGroupBox(_("Startup services"))
        lay_srv = QVBoxLayout(grp_srv)
        lay_srv.setSpacing(6)
        lay_srv.setContentsMargins(16, 16, 16, 12)
        self.chk_daemon = QCheckBox(_("Start transcription daemon at startup"))
        self.chk_tray = QCheckBox(_("Show notification area icon"))
        # Dans le wizard, cocher par défaut (première install)
        self.chk_daemon.setChecked(self._is_service_enabled("dictee") or self.wizard_mode)
        self.chk_tray.setChecked(self._is_service_enabled("dictee-tray"))
        lay_srv.addWidget(self.chk_daemon)
        lay_srv.addWidget(self.chk_tray)
        lay.addWidget(grp_srv)

        # Options
        self.chk_clipboard = QCheckBox(_("Copy transcription to clipboard"))
        self.chk_clipboard.setChecked(conf.get("DICTEE_CLIPBOARD", "true") == "true")
        lay.addWidget(self.chk_clipboard)

        lay.addStretch()
        scroll.setWidget(content)
        page_lay.addWidget(scroll)
        self.stack.addWidget(page)

    # -- Wizard Page 5: Test --

    def _build_wizard_page5(self, conf):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.setContentsMargins(24, 0, 24, 16)

        lay.addWidget(self._make_logo_header())

        lbl = QLabel("<h2>" + _("Test") + "</h2>"
                     "<p>" + _("Let's verify that everything works correctly.") + "</p>")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        # Checks container
        self.w_checks = QWidget()
        lay_checks = QVBoxLayout(self.w_checks)
        lay_checks.setSpacing(6)
        lay_checks.setContentsMargins(0, 0, 0, 0)
        self._check_labels = {}
        for check_id, label in [
            ("daemon", _("ASR daemon")),
            ("model", _("ASR model")),
            ("shortcut", _("Keyboard shortcut")),
            ("audio", _("Audio (PipeWire/PulseAudio)")),
            ("dotool", _("dotool")),
        ]:
            row = QHBoxLayout()
            lbl_icon = QLabel("⏳")
            lbl_icon.setFixedWidth(24)
            lbl_name = QLabel(label)
            lbl_status = QLabel()
            row.addWidget(lbl_icon)
            row.addWidget(lbl_name)
            row.addWidget(lbl_status, 1)
            lay_checks.addLayout(row)
            self._check_labels[check_id] = (lbl_icon, lbl_status)
        lay.addWidget(self.w_checks)

        # Test dictée
        grp_test = QGroupBox(_("Dictation test"))
        lay_test = QVBoxLayout(grp_test)
        lay_test.setSpacing(8)

        lbl_test = QLabel(_("Click the button below and speak for a few seconds."))
        lbl_test.setWordWrap(True)
        lay_test.addWidget(lbl_test)

        self.btn_test_dictee = QPushButton("🎤 " + _("Test dictation"))
        self.btn_test_dictee.setMinimumHeight(40)
        self.btn_test_dictee.clicked.connect(self._on_test_dictee)
        lay_test.addWidget(self.btn_test_dictee)

        self.txt_test_result = QTextEdit()
        self.txt_test_result.setReadOnly(True)
        self.txt_test_result.setMaximumHeight(80)
        self.txt_test_result.setPlaceholderText(_("Result will appear here…"))
        lay_test.addWidget(self.txt_test_result)

        lay.addWidget(grp_test)

        self.lbl_final = QLabel()
        self.lbl_final.setWordWrap(True)
        self.lbl_final.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_final)

        lay.addStretch()
        self.stack.addWidget(page)

    # ── Shared widget builders ────────────────────────────────────

    def _make_radio_card(self, title, description, selected=False):
        card = QFrame()
        card.setObjectName("radioCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(self._card_style(selected))
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        lbl_title = QLabel(f"<b>{title}</b>")
        lbl_desc = QLabel(f"<small>{description}</small>")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("opacity: 0.65;")
        lay.addWidget(lbl_title)
        lay.addWidget(lbl_desc)
        return card

    @staticmethod
    def _card_style(selected):
        children = "QFrame#radioCard * { border: none; background: transparent; color: #eee; }"
        if selected:
            return (children +
                    " QFrame#radioCard { border: 2px solid #5566ff; border-radius: 8px;"
                    " background: #252545; padding: 4px; }")
        return (children +
                " QFrame#radioCard { border: 1px solid #444; border-radius: 8px;"
                " background: #1a1a2e; padding: 4px; }"
                " QFrame#radioCard:hover { border: 1px solid #666; }")

    def _build_shortcut_section(self, lay_sc):
        """Builds the PTT keyboard shortcut widgets into the given layout."""
        # Mode hold / toggle
        lbl_mode = QLabel(_("Activation mode") + " :")
        lay_sc.addWidget(lbl_mode)

        self.cmb_ptt_mode = QComboBox()
        self.cmb_ptt_mode.addItem(_("Hold (push-to-talk) — hold key to record, release to transcribe"), "hold")
        self.cmb_ptt_mode.addItem(_("Toggle — press to start, press again to stop"), "toggle")
        existing_mode = self.conf.get("DICTEE_PTT_MODE", "toggle")
        idx = self.cmb_ptt_mode.findData(existing_mode)
        if idx >= 0:
            self.cmb_ptt_mode.setCurrentIndex(idx)
        lay_sc.addWidget(self.cmb_ptt_mode)

        lay_sc.addSpacing(8)

        # Touche dictée
        lbl_dictee = QLabel(_("Voice dictation key") + " :")
        lay_sc.addWidget(lbl_dictee)
        self.btn_capture = ShortcutButton()
        existing_key = int(self.conf.get("DICTEE_PTT_KEY", 67))
        if existing_key:
            self.btn_capture.setText(_("Key: {name}").format(
                name=linux_keycode_name(existing_key)))
            self._ptt_key = existing_key
        else:
            self._ptt_key = 67
        lay_sc.addWidget(self.btn_capture)
        self.btn_capture.shortcutCaptured.connect(self._on_ptt_key_captured)

        self.lbl_ptt_warning = QLabel()
        self.lbl_ptt_warning.setVisible(False)
        self.lbl_ptt_warning.setWordWrap(True)
        lay_sc.addWidget(self.lbl_ptt_warning)

        lay_sc.addSpacing(4)

        # Touche traduction : modificateur + même touche ou touche séparée
        lay_sc.addSpacing(4)
        lbl_translate = QLabel(_("Dictation + Translation") + " :")
        lay_sc.addWidget(lbl_translate)

        # Choix : même touche + modificateur ou touche séparée
        self.cmb_translate_mode = QComboBox()
        self.cmb_translate_mode.addItem(_("Same key + Alt (e.g., Alt+F9)"), "same_alt")
        self.cmb_translate_mode.addItem(_("Same key + Ctrl"), "same_ctrl")
        self.cmb_translate_mode.addItem(_("Same key + Shift"), "same_shift")
        self.cmb_translate_mode.addItem(_("Separate key"), "separate")
        self.cmb_translate_mode.addItem(_("Disabled"), "disabled")

        # Charger config existante
        existing_mod = self.conf.get("DICTEE_PTT_MOD_TRANSLATE", "")
        existing_key_tr = int(self.conf.get("DICTEE_PTT_KEY_TRANSLATE", 0))
        existing_key = int(self.conf.get("DICTEE_PTT_KEY", 67))

        if not existing_key_tr:
            self.cmb_translate_mode.setCurrentIndex(4)  # disabled
        elif existing_mod == "alt":
            self.cmb_translate_mode.setCurrentIndex(0)
        elif existing_mod == "ctrl":
            self.cmb_translate_mode.setCurrentIndex(1)
        elif existing_mod == "shift":
            self.cmb_translate_mode.setCurrentIndex(2)
        elif existing_key_tr != existing_key:
            self.cmb_translate_mode.setCurrentIndex(3)  # separate
        else:
            self.cmb_translate_mode.setCurrentIndex(0)  # default alt

        lay_sc.addWidget(self.cmb_translate_mode)

        # Bouton capture touche séparée (visible uniquement si "separate")
        self.btn_capture_translate = ShortcutButton()
        if existing_key_tr and existing_key_tr != existing_key:
            self.btn_capture_translate.setText(_("Key: {name}").format(
                name=linux_keycode_name(existing_key_tr)))
            self._ptt_key_translate = existing_key_tr
        else:
            self._ptt_key_translate = 0
            self.btn_capture_translate.setText(_("Click to capture a shortcut…"))
        self.btn_capture_translate.setVisible(
            self.cmb_translate_mode.currentData() == "separate")
        lay_sc.addWidget(self.btn_capture_translate)
        self.btn_capture_translate.shortcutCaptured.connect(self._on_ptt_key_translate_captured)

        self.cmb_translate_mode.currentIndexChanged.connect(self._on_translate_mode_changed)

        lay_sc.addSpacing(8)

        # Info groupe input
        in_input_group = "input" in os.popen("groups").read().split()
        if not in_input_group:
            row_input = QHBoxLayout()
            lbl_group = QLabel(
                '<span style="color: orange;">⚠ ' +
                _("Your user is not in the 'input' group (required for keyboard shortcuts).") +
                '</span>')
            lbl_group.setWordWrap(True)
            row_input.addWidget(lbl_group)
            btn_fix_input = QPushButton(_("Fix (requires password)"))
            btn_fix_input.setFixedWidth(200)

            def _fix_input_group():
                user = os.environ.get("USER", "")
                if not user:
                    return
                try:
                    result = subprocess.run(
                        ["pkexec", "usermod", "-aG", "input", user],
                        capture_output=True, text=True, timeout=15)
                    if result.returncode == 0:
                        btn_fix_input.setVisible(False)
                        lbl_group.setText(
                            '<span style="color: green;">✓ ' +
                            _("User added to 'input' group. Log out and back in to activate.") +
                            '</span>')
                    else:
                        QMessageBox.critical(self, _("Error"), result.stderr.strip())
                except Exception as e:
                    QMessageBox.critical(self, _("Error"), str(e))

            btn_fix_input.clicked.connect(_fix_input_group)
            row_input.addWidget(btn_fix_input)
            row_input.addStretch()
            lay_sc.addLayout(row_input)

    def _build_parakeet_options(self, parent_layout):
        """Build Parakeet model download widgets."""
        self.w_parakeet_options = QWidget()
        lay_parakeet = QVBoxLayout(self.w_parakeet_options)
        lay_parakeet.setContentsMargins(0, 4, 0, 0)
        lay_parakeet.setSpacing(4)

        for model in ASR_MODELS:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.setContentsMargins(24, 0, 0, 0)

            installed = model_is_installed(model)
            required = _(" (required)") if model["required"] else ""

            lbl = QLabel()
            icon = '<span style="color: green;">✓</span>' if installed \
                else '<span style="color: orange;">⚠</span>'
            line2 = model["desc"] + (required if not installed else "")
            lbl.setText(f'{icon} {model["name"]}<br>'
                        f'<span style="font-size: 9.5pt; color: gray;">{line2}</span>')
            lbl.setWordWrap(True)
            row.addWidget(lbl, 1)

            btn_info = QPushButton("?")
            btn_info.setFixedSize(24, 24)
            btn_info.setToolTip(model["help"])
            btn_info.setStyleSheet("font-weight: bold; border-radius: 12px;")
            btn_info.clicked.connect(lambda checked, b=btn_info, m=model:
                QToolTip.showText(b.mapToGlobal(b.rect().bottomLeft()), m["help"], b))
            row.addWidget(btn_info)

            btn = QPushButton(_("Download") if not installed else _("Installed"))
            btn.setFixedWidth(120)
            # Sortformer requires TDT — disable if TDT not installed
            tdt_installed = model_is_installed(ASR_MODELS[0])
            if installed:
                btn.setEnabled(False)
            elif model["id"] == "sortformer" and not tdt_installed:
                btn.setEnabled(False)
                btn.setToolTip(_("Requires Parakeet-TDT 0.6B v3 to be installed first"))
            row.addWidget(btn)

            lay_parakeet.addLayout(row)

            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setVisible(False)
            lay_parakeet.addWidget(progress)

            self._model_widgets[model["id"]] = {"label": lbl, "button": btn, "progress": progress, "model": model}
            btn.clicked.connect(lambda checked, m=model: self._on_model_download(m))

        parent_layout.addWidget(self.w_parakeet_options)

    def _build_vosk_options(self, parent_layout):
        """Build Vosk install + language widgets."""
        self.w_vosk_options = QWidget()
        vosk_outer = QVBoxLayout(self.w_vosk_options)
        vosk_outer.setContentsMargins(0, 4, 0, 0)
        vosk_outer.setSpacing(4)

        row_vosk = QHBoxLayout()
        row_vosk.setContentsMargins(24, 0, 0, 0)
        vosk_installed = venv_is_installed(VOSK_VENV)
        if vosk_installed:
            # Venv OK — pas besoin de l'afficher, le combo ✓/✗ suffit
            self.btn_install_vosk = QWidget()  # placeholder invisible
            self.btn_install_vosk.setFixedWidth(0)
        else:
            self.btn_install_vosk = QPushButton(_("Install Vosk engine"))
            self.btn_install_vosk.setFixedWidth(150)
            self.btn_install_vosk.clicked.connect(lambda: self._install_venv("vosk", VOSK_VENV, "vosk"))

        lbl_vosk_lang = QLabel(_("Language:"))
        self.cmb_vosk_lang = QComboBox()
        self._refresh_vosk_lang_combo()
        cur_vosk = self.conf.get("DICTEE_VOSK_MODEL", "fr")
        idx = self.cmb_vosk_lang.findData(cur_vosk)
        if idx >= 0:
            self.cmb_vosk_lang.setCurrentIndex(idx)
        row_vosk.addWidget(lbl_vosk_lang)
        self.cmb_vosk_lang.currentIndexChanged.connect(lambda: (
            self._update_src_languages(), self._update_vosk_dl_button()))
        row_vosk.addWidget(self.cmb_vosk_lang)

        self.btn_dl_vosk_model = QPushButton(_("Download model"))
        self.btn_dl_vosk_model.setFixedWidth(150)
        self.btn_dl_vosk_model.clicked.connect(self._on_vosk_model_download)
        row_vosk.addWidget(self.btn_dl_vosk_model)

        row_vosk.addStretch()
        row_vosk.addWidget(self.btn_install_vosk)
        vosk_outer.addLayout(row_vosk)

        self.progress_vosk_model = QProgressBar()
        self.progress_vosk_model.setRange(0, 0)
        self.progress_vosk_model.setVisible(False)
        vosk_outer.addWidget(self.progress_vosk_model)

        self._update_vosk_dl_button()

        parent_layout.addWidget(self.w_vosk_options)

    # -- Vosk model management --

    def _vosk_model_installed(self, lang_code):
        """Vérifie si le modèle Vosk pour une langue est téléchargé."""
        model_name = VOSK_MODELS.get(lang_code, "")
        model_dir = os.path.join(DICTEE_DATA_DIR, "vosk-models", model_name)
        return os.path.isdir(model_dir)

    def _refresh_vosk_lang_combo(self):
        """Repeuple le combo Vosk avec indicateur ✓/✗ par modèle."""
        current = self.cmb_vosk_lang.currentData()
        self.cmb_vosk_lang.blockSignals(True)
        self.cmb_vosk_lang.clear()
        for code, name in VOSK_MODELS.items():
            installed = self._vosk_model_installed(code)
            prefix = "✓" if installed else "✗"
            self.cmb_vosk_lang.addItem(f"{prefix}  {code} — {name}", code)
        self.cmb_vosk_lang.blockSignals(False)
        if current:
            idx = self.cmb_vosk_lang.findData(current)
            if idx >= 0:
                self.cmb_vosk_lang.setCurrentIndex(idx)

    def _update_vosk_dl_button(self):
        """Affiche/masque le bouton télécharger selon si le modèle est installé."""
        code = self.cmb_vosk_lang.currentData()
        if code and self._vosk_model_installed(code):
            self.btn_dl_vosk_model.setVisible(False)
        else:
            self.btn_dl_vosk_model.setVisible(True)
            self.btn_dl_vosk_model.setEnabled(True)
            self.btn_dl_vosk_model.setText(_("Download model"))

    def _on_vosk_model_download(self):
        """Télécharge le modèle Vosk sélectionné."""
        code = self.cmb_vosk_lang.currentData()
        if not code or self._vosk_model_installed(code):
            return
        model_name = VOSK_MODELS[code]
        self.btn_dl_vosk_model.setEnabled(False)
        self.btn_dl_vosk_model.setText(_("Downloading…"))
        self.progress_vosk_model.setVisible(True)

        self._vosk_dl_thread = _VoskModelDownloadThread(model_name)
        self._vosk_dl_thread.progress.connect(
            lambda text: self.btn_dl_vosk_model.setText(text))
        self._vosk_dl_thread.finished.connect(self._on_vosk_model_download_finished)
        self._vosk_dl_thread.start()

    def _on_vosk_model_download_finished(self, success, message):
        self.progress_vosk_model.setVisible(False)
        if success:
            self._refresh_vosk_lang_combo()
            self._update_vosk_dl_button()
            self._update_src_languages()
        else:
            self.btn_dl_vosk_model.setEnabled(True)
            self.btn_dl_vosk_model.setText(_("Download model"))
            QMessageBox.critical(self, _("Download error"), message)

    def _build_whisper_options(self, parent_layout):
        """Build Whisper install + model/language widgets."""
        self.w_whisper_options = QWidget()
        whisper_outer = QVBoxLayout(self.w_whisper_options)
        whisper_outer.setContentsMargins(0, 4, 0, 0)
        whisper_outer.setSpacing(4)

        row = QHBoxLayout()
        row.setContentsMargins(24, 0, 0, 0)
        whisper_installed = venv_is_installed(WHISPER_VENV)
        if whisper_installed:
            self.btn_install_whisper = QWidget()
            self.btn_install_whisper.setFixedWidth(0)
        else:
            self.btn_install_whisper = QPushButton(_("Install Whisper engine"))
            self.btn_install_whisper.setFixedWidth(150)
            self.btn_install_whisper.clicked.connect(lambda: self._install_venv("whisper", WHISPER_VENV, "faster-whisper"))

        lbl_wh_model = QLabel(_("Model:"))
        self.cmb_whisper_model = QComboBox()
        for m in WHISPER_MODELS:
            self.cmb_whisper_model.addItem(m)
        cur_wh = self.conf.get("DICTEE_WHISPER_MODEL", "small")
        idx = self.cmb_whisper_model.findText(cur_wh)
        if idx >= 0:
            self.cmb_whisper_model.setCurrentIndex(idx)
        lbl_wh_lang = QLabel(_("Language:"))
        self.txt_whisper_lang = QComboBox()
        self.txt_whisper_lang.setEditable(True)
        self.txt_whisper_lang.addItems(["", "fr", "en", "es", "de", "it", "pt", "ru", "zh", "ja", "ko", "ar"])
        cur_wl = self.conf.get("DICTEE_WHISPER_LANG", "")
        self.txt_whisper_lang.setCurrentText(cur_wl)
        lbl_auto = QLabel(_("(empty = auto-detect)"))
        lbl_auto.setStyleSheet("color: gray;")

        row.addWidget(lbl_wh_model)
        row.addWidget(self.cmb_whisper_model)
        row.addWidget(lbl_wh_lang)
        row.addWidget(self.txt_whisper_lang)
        row.addWidget(lbl_auto)
        row.addStretch()
        row.addWidget(self.btn_install_whisper)
        whisper_outer.addLayout(row)

        parent_layout.addWidget(self.w_whisper_options)

    def _build_visual_section(self, lay_vis, conf):
        """Build visual feedback checkboxes and install button."""
        self.chk_anim_speech = QCheckBox(_("animation-speech (overlay)"))
        self.chk_plasmoid = QCheckBox(_("KDE Plasma widget (panel)"))
        self.chk_gnome_ext = QCheckBox(_("GNOME Shell extension (not yet available)"))
        self.chk_gnome_ext.setEnabled(False)

        anim = conf.get("DICTEE_ANIMATION", "speech")
        self.chk_anim_speech.setChecked(anim in ("speech", "both"))
        self.chk_plasmoid.setChecked(anim in ("plasmoid", "both"))

        # Smart pre-check based on desktop
        if not os.path.exists(CONF_PATH):
            if self.de_type == "kde":
                self.chk_plasmoid.setChecked(True)
            else:
                self.chk_anim_speech.setChecked(True)

        lay_vis.addWidget(self.chk_anim_speech)
        lay_vis.addWidget(self.chk_plasmoid)
        lay_vis.addWidget(self.chk_gnome_ext)

        # Avertissement GNOME / compositors sans wlr-layer-shell
        self.lbl_anim_warn = QLabel(
            '<span style="color: orange;">⚠ '
            + _("animation-speech requires a Wayland compositor with layer-shell support "
                "(KDE, Sway, Hyprland…). It does not work on GNOME.")
            + '</span>'
        )
        self.lbl_anim_warn.setWordWrap(True)
        self.lbl_anim_warn.setVisible(self.de_type == "gnome")
        if self.de_type == "gnome":
            self.chk_anim_speech.setEnabled(False)
            self.chk_anim_speech.setChecked(False)
        lay_vis.addWidget(self.lbl_anim_warn)

        self.lbl_anim_status = QLabel()
        self.lbl_anim_status.setWordWrap(True)
        lay_vis.addWidget(self.lbl_anim_status)

        self.btn_install_anim = QPushButton(_("Install animation-speech"))
        self.btn_install_anim.setVisible(False)
        self.btn_install_anim.clicked.connect(self._on_install_animation)
        lay_vis.addWidget(self.btn_install_anim)

        self.progress_anim = QProgressBar()
        self.progress_anim.setRange(0, 0)
        self.progress_anim.setVisible(False)
        lay_vis.addWidget(self.progress_anim)

        self._check_animation_speech()

    def _build_translation_section(self, lay_tr, conf):
        """Build translation backend selection, languages, sub-options."""
        lay_tr_title = QHBoxLayout()
        lay_tr_title.setContentsMargins(0, 0, 0, 0)
        lay_tr_title.setSpacing(6)
        lbl_tr_title = QLabel("<b>" + _("Translation") + "</b>")
        lay_tr_title.addWidget(lbl_tr_title)
        btn_help_tr = QPushButton("?")
        btn_help_tr.setFixedSize(22, 22)
        btn_help_tr.setToolTip(
            _("How to translate:") + "\n\n"
            + _("• Keyboard shortcut: configure above (Dictation + Translation)") + "\n"
            + _("• Plasmoid: long press or translation button") + "\n"
            + _("• CLI: dictee --translate") + "\n"
            + _("• Direct: transcribe-client | trans -b :en")
        )
        lay_tr_title.addWidget(btn_help_tr)
        lay_tr_title.addStretch()
        lay_tr.addLayout(lay_tr_title)

        # Languages
        form_lang = QFormLayout()
        form_lang.setHorizontalSpacing(12)
        form_lang.setVerticalSpacing(8)

        self.combo_src = QComboBox()
        self.combo_tgt = QComboBox()
        for code, name in LANGUAGES:
            self.combo_src.addItem(f"{code} — {name}", code)
            self.combo_tgt.addItem(f"{code} — {name}", code)

        default_src = conf.get("DICTEE_LANG_SOURCE", self._system_lang())
        default_tgt = conf.get("DICTEE_LANG_TARGET", "en")
        self._set_combo_by_data(self.combo_src, default_src, 0)
        self._set_combo_by_data(self.combo_tgt, default_tgt, 1)

        form_lang.addRow(_("Source language:"), self.combo_src)
        form_lang.addRow(_("Target language:"), self.combo_tgt)
        lay_tr.addLayout(form_lang)
        lay_tr.addSpacing(4)

        # Backend ComboBox
        lbl_backend = QLabel(_("Backend:"))
        lay_tr.addWidget(lbl_backend)

        self.cmb_trans_backend = QComboBox()
        # Local-first order in wizard
        if self.wizard_mode:
            self.cmb_trans_backend.addItem(_("LibreTranslate (local)"), "libretranslate")
            self.cmb_trans_backend.addItem(_("ollama (local)"), "ollama")
            self.cmb_trans_backend.addItem(_("Google Translate (cloud)"), "trans:google")
            self.cmb_trans_backend.addItem(_("Bing (cloud)"), "trans:bing")
        else:
            self.cmb_trans_backend.addItem(_("Google Translate (cloud)"), "trans:google")
            self.cmb_trans_backend.addItem(_("Bing (cloud)"), "trans:bing")
            self.cmb_trans_backend.addItem(_("LibreTranslate (local)"), "libretranslate")
            self.cmb_trans_backend.addItem(_("ollama (local)"), "ollama")
        lay_tr.addWidget(self.cmb_trans_backend)

        # LibreTranslate widget
        self.lt_widget = QFrame()
        lay_lt = QVBoxLayout(self.lt_widget)
        lay_lt.setContentsMargins(32, 4, 0, 0)
        lay_lt.setSpacing(4)

        lay_lt_port = QHBoxLayout()
        lay_lt_port.setSpacing(8)
        lbl_lt_port = QLabel(_("Port:"))
        lay_lt_port.addWidget(lbl_lt_port)
        self.spin_lt_port = QComboBox()
        self.spin_lt_port.setEditable(True)
        for p in ("5000", "5001", "5002", "8080"):
            self.spin_lt_port.addItem(p)
        default_port = str(conf.get("DICTEE_LIBRETRANSLATE_PORT", "5000"))
        idx = self.spin_lt_port.findText(default_port)
        if idx >= 0:
            self.spin_lt_port.setCurrentIndex(idx)
        else:
            self.spin_lt_port.setCurrentText(default_port)
        lay_lt_port.addWidget(self.spin_lt_port)
        lay_lt_port.addStretch()
        lay_lt.addLayout(lay_lt_port)

        # -- Langues LibreTranslate --
        lbl_lt_langs = QLabel("<small>" + _("Languages to load in LibreTranslate:") + "</small>")
        lay_lt.addWidget(lbl_lt_langs)

        saved_lt_langs = set(
            conf.get("DICTEE_LIBRETRANSLATE_LANGS", "de,en,es,fr").split(","))
        # Toujours inclure source et cible
        saved_lt_langs.add(conf.get("DICTEE_LANG_SOURCE", self._system_lang()))
        saved_lt_langs.add(conf.get("DICTEE_LANG_TARGET", "en"))

        self._lt_lang_checks = {}
        grid_langs = QGridLayout()
        grid_langs.setSpacing(2)
        for i, (code, name) in enumerate(LANGUAGES):
            chk = QCheckBox(f"{code} — {name}")
            chk.setChecked(code in saved_lt_langs)
            chk.stateChanged.connect(self._on_lt_langs_changed)
            self._lt_lang_checks[code] = chk
            grid_langs.addWidget(chk, i // 4, i % 4)
        lay_lt.addLayout(grid_langs)

        self.lbl_lt_langs_hint = QLabel()
        self.lbl_lt_langs_hint.setWordWrap(True)
        self.lbl_lt_langs_hint.setVisible(False)
        lay_lt.addWidget(self.lbl_lt_langs_hint)

        self.btn_lt_restart_langs = QPushButton(_("Restart with new languages"))
        self.btn_lt_restart_langs.setVisible(False)
        self.btn_lt_restart_langs.clicked.connect(self._on_lt_restart_langs)
        lay_lt.addWidget(self.btn_lt_restart_langs)

        self.lbl_lt_status = QLabel()
        self.lbl_lt_status.setWordWrap(True)
        lay_lt.addWidget(self.lbl_lt_status)

        lay_lt_buttons = QHBoxLayout()
        lay_lt_buttons.setSpacing(8)
        self.btn_lt_pull = QPushButton(_("Download image"))
        self.btn_lt_pull.setVisible(False)
        self.btn_lt_pull.clicked.connect(self._on_lt_pull)
        lay_lt_buttons.addWidget(self.btn_lt_pull)
        self.btn_lt_start = QPushButton(_("Start"))
        self.btn_lt_start.setVisible(False)
        self.btn_lt_start.clicked.connect(self._on_lt_start)
        lay_lt_buttons.addWidget(self.btn_lt_start)
        self.btn_lt_stop = QPushButton(_("Stop"))
        self.btn_lt_stop.setVisible(False)
        self.btn_lt_stop.clicked.connect(self._on_lt_stop)
        lay_lt_buttons.addWidget(self.btn_lt_stop)
        lay_lt_buttons.addStretch()
        lay_lt.addLayout(lay_lt_buttons)

        self.progress_lt = QProgressBar()
        self.progress_lt.setRange(0, 0)
        self.progress_lt.setVisible(False)
        lay_lt.addWidget(self.progress_lt)

        lay_tr.addWidget(self.lt_widget)
        self.lt_widget.setVisible(False)
        self._docker_pull_thread = None
        self._lt_action_thread = None

        # Ollama widget
        self.ollama_widget = QFrame()
        lay_ollama = QVBoxLayout(self.ollama_widget)
        lay_ollama.setContentsMargins(32, 4, 0, 0)
        lay_ollama.setSpacing(4)

        lay_model = QHBoxLayout()
        lay_model.setSpacing(8)
        lbl_model = QLabel(_("Model:"))
        self.combo_ollama_model = QComboBox()
        for model_id, model_label, _ram, _vram in OLLAMA_MODELS:
            self.combo_ollama_model.addItem(model_label, model_id)
        default_model = conf.get("DICTEE_OLLAMA_MODEL", "translategemma")
        self._set_combo_by_data(self.combo_ollama_model, default_model, 0)
        lay_model.addWidget(lbl_model)
        lay_model.addWidget(self.combo_ollama_model, 1)
        lay_ollama.addLayout(lay_model)

        self.lbl_ollama_status = QLabel()
        self.lbl_ollama_status.setWordWrap(True)
        lay_ollama.addWidget(self.lbl_ollama_status)

        self.chk_ollama_cpu = QCheckBox(_("Force CPU (OLLAMA_NUM_GPU=0)"))
        self.chk_ollama_cpu.setChecked(conf.get("OLLAMA_NUM_GPU") == "0")
        self.chk_ollama_cpu.setToolTip(
            _("Use CPU instead of GPU for ollama inference (slower but no VRAM needed)"))
        lay_ollama.addWidget(self.chk_ollama_cpu)

        self.btn_ollama_pull = QPushButton(_("Download model"))
        self.btn_ollama_pull.setVisible(False)
        self.btn_ollama_pull.clicked.connect(self._on_ollama_pull)
        lay_ollama.addWidget(self.btn_ollama_pull)

        self.progress_ollama = QProgressBar()
        self.progress_ollama.setRange(0, 0)
        self.progress_ollama.setVisible(False)
        lay_ollama.addWidget(self.progress_ollama)

        lay_tr.addWidget(self.ollama_widget)

        self.combo_ollama_model.currentIndexChanged.connect(self._on_ollama_model_changed)
        self._ollama_pull_thread = None

        # Restore saved backend
        saved_backend = conf.get("DICTEE_TRANSLATE_BACKEND", "")
        saved_engine = conf.get("DICTEE_TRANS_ENGINE", "google")
        if saved_backend == "ollama":
            self._set_combo_by_data(self.cmb_trans_backend, "ollama", 0)
        elif saved_backend == "libretranslate":
            self._set_combo_by_data(self.cmb_trans_backend, "libretranslate", 0)
        elif saved_backend == "trans" and saved_engine == "bing":
            self._set_combo_by_data(self.cmb_trans_backend, "trans:bing", 0)
        elif saved_backend == "trans":
            self._set_combo_by_data(self.cmb_trans_backend, "trans:google", 0)
        else:
            # Pas de config → wizard: libretranslate, classique: google
            default = "libretranslate" if self.wizard_mode else "trans:google"
            self._set_combo_by_data(self.cmb_trans_backend, default, 0)

        def _on_trans_backend_changed():
            data = self.cmb_trans_backend.currentData()
            self.lt_widget.setVisible(data == "libretranslate")
            self.ollama_widget.setVisible(data == "ollama")
            if data == "libretranslate":
                self._check_lt_status()
            if data == "ollama":
                self._check_ollama_status()
            self._update_tgt_languages()
        self.cmb_trans_backend.currentIndexChanged.connect(lambda: _on_trans_backend_changed())
        # Rafraîchir le statut et checkboxes LibreTranslate quand on change la langue
        def _on_lang_changed():
            if self.cmb_trans_backend.currentData() == "libretranslate":
                self._update_lt_lang_checks()
                self._on_lt_langs_changed()
                self._check_lt_status()
        self.combo_src.currentIndexChanged.connect(_on_lang_changed)
        self.combo_tgt.currentIndexChanged.connect(_on_lang_changed)
        self._update_lt_lang_checks()
        _on_trans_backend_changed()

    # -- Post-processing section --

    def _build_postprocess_section(self, lay, conf):
        """Build post-processing section: pipeline toggles, venv, config files, LLM."""
        # Checkbox activer
        self.chk_postprocess = QCheckBox(_("Enable post-processing (regex rules + dictionary)"))
        self.chk_postprocess.setChecked(conf.get("DICTEE_POSTPROCESS", "true") == "true")
        lay.addWidget(self.chk_postprocess)

        # Conteneur pour tout le contenu PP (grisé si désactivé)
        self._pp_content = QWidget()
        pp_lay = QVBoxLayout(self._pp_content)
        pp_lay.setContentsMargins(0, 0, 0, 0)
        pp_lay.setSpacing(6)

        # --- Pipeline toggles — général ---
        grid_gen = QGridLayout()
        grid_gen.setContentsMargins(20, 0, 0, 0)

        self.chk_pp_numbers = QCheckBox(_("Number conversion (text2num)"))
        self.chk_pp_numbers.setChecked(conf.get("DICTEE_PP_NUMBERS", "true") == "true")
        grid_gen.addWidget(self.chk_pp_numbers, 0, 0)

        self.chk_pp_capitalization = QCheckBox(_("Auto-capitalization"))
        self.chk_pp_capitalization.setChecked(conf.get("DICTEE_PP_CAPITALIZATION", "true") == "true")
        grid_gen.addWidget(self.chk_pp_capitalization, 0, 1)

        self.chk_pp_fuzzy_dict = QCheckBox(_("Fuzzy dictionary matching"))
        self.chk_pp_fuzzy_dict.setChecked(conf.get("DICTEE_PP_FUZZY_DICT", "true") == "true")
        grid_gen.addWidget(self.chk_pp_fuzzy_dict, 1, 0)

        pp_lay.addLayout(grid_gen)

        # --- Pipeline toggles — spécifiques à la langue ---
        lang_src = conf.get("DICTEE_LANG_SOURCE", "fr")
        is_fr = lang_src == "fr"

        lbl_lang = QLabel("<b>" + _("French-specific:") + "</b>")
        lbl_lang.setContentsMargins(20, 4, 0, 0)
        lbl_lang.setVisible(is_fr)
        pp_lay.addWidget(lbl_lang)

        grid_lang = QGridLayout()
        grid_lang.setContentsMargins(20, 0, 0, 0)

        self.chk_pp_elisions = QCheckBox(_("Elisions"))
        self.chk_pp_elisions.setChecked(conf.get("DICTEE_PP_ELISIONS", "true") == "true")
        self.chk_pp_elisions.setVisible(is_fr)
        grid_lang.addWidget(self.chk_pp_elisions, 0, 0)

        self.chk_pp_typography = QCheckBox(_("Typography (non-breaking spaces)"))
        self.chk_pp_typography.setChecked(conf.get("DICTEE_PP_TYPOGRAPHY", "true") == "true")
        self.chk_pp_typography.setVisible(is_fr)
        grid_lang.addWidget(self.chk_pp_typography, 0, 1)

        self._lang_pp_widgets = [lbl_lang, self.chk_pp_elisions, self.chk_pp_typography]
        pp_lay.addLayout(grid_lang)

        # --- Sous-onglets d'édition ---
        self._pp_tabs = QTabWidget()

        # Couleurs d'accentuation pour les onglets
        accent = self.palette().color(self.palette().ColorRole.Highlight)
        accent_hex = accent.name()
        self._pp_tabs.setStyleSheet(f"""
            QTabBar::tab:selected {{
                color: {accent_hex};
                font-weight: bold;
            }}
        """)

        # Onglet Règles
        tab_rules = QWidget()
        tab_rules_lay = QVBoxLayout(tab_rules)
        tab_rules_lay.setContentsMargins(8, 8, 8, 8)
        self._build_rules_tab(tab_rules_lay)
        self._pp_tabs.addTab(tab_rules, _("Regex rules"))

        # Onglet Dictionnaire
        tab_dict = QWidget()
        tab_dict_lay = QVBoxLayout(tab_dict)
        tab_dict_lay.setContentsMargins(8, 8, 8, 8)
        self._build_dictionary_tab(tab_dict_lay)
        self._pp_tabs.addTab(tab_dict, _("Dictionary"))

        # Onglet Continuation
        tab_cont = QWidget()
        tab_cont_lay = QVBoxLayout(tab_cont)
        tab_cont_lay.setContentsMargins(8, 8, 8, 8)
        self._build_continuation_tab(tab_cont_lay)
        self._pp_tabs.addTab(tab_cont, _("Continuation"))

        # Bouton Mode avancé (masqué pour l'onglet Règles)
        self._btn_advanced = QPushButton(_("Advanced mode"))
        self._btn_advanced.setCheckable(True)
        self._btn_advanced.setMaximumWidth(150)
        corner = QWidget()
        corner_lay = QHBoxLayout(corner)
        corner_lay.setContentsMargins(0, 0, 4, 0)
        corner_lay.addWidget(self._btn_advanced)
        self._pp_tabs.setCornerWidget(corner)

        def _on_tab_changed(idx):
            self._btn_advanced.setVisible(idx != 0)
            self._btn_advanced.setChecked(False)
            self._toggle_advanced_mode(False)
        self._pp_tabs.currentChanged.connect(_on_tab_changed)
        self._btn_advanced.toggled.connect(self._toggle_advanced_mode)
        _on_tab_changed(0)

        pp_lay.addWidget(self._pp_tabs)

        # --- Panneau de test ---
        grp_test = QGroupBox(_("Test"))
        test_lay = QVBoxLayout(grp_test)
        test_lay.setSpacing(6)
        self._build_test_panel(test_lay)
        pp_lay.addWidget(grp_test)

        # LLM correction
        self.chk_llm = QCheckBox(_("LLM grammar correction (ollama)"))
        self.chk_llm.setChecked(conf.get("DICTEE_LLM_POSTPROCESS", "false") == "true")
        pp_lay.addWidget(self.chk_llm)

        # Sous-options LLM
        self._llm_widget = QWidget()
        llm_lay = QFormLayout(self._llm_widget)
        llm_lay.setContentsMargins(20, 4, 0, 0)

        self.cmb_llm_model = QComboBox()
        saved_model = conf.get("DICTEE_LLM_MODEL", "ministral:3b")
        self.cmb_llm_model.setEditable(True)
        self.cmb_llm_model.addItem("ministral:3b")
        self.cmb_llm_model.addItem("gemma3:4b")
        self.cmb_llm_model.addItem("gemma3:1b")
        # Détecter les modèles installés
        try:
            import subprocess as _sp
            out = _sp.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                for line in out.stdout.strip().splitlines()[1:]:
                    name = line.split()[0] if line.split() else ""
                    if name and self.cmb_llm_model.findText(name) < 0:
                        self.cmb_llm_model.addItem(name)
        except (FileNotFoundError, _sp.TimeoutExpired):
            pass
        idx = self.cmb_llm_model.findText(saved_model)
        if idx >= 0:
            self.cmb_llm_model.setCurrentIndex(idx)
        else:
            self.cmb_llm_model.setEditText(saved_model)
        llm_lay.addRow(_("Model:"), self.cmb_llm_model)

        self.chk_llm_cpu = QCheckBox(_("Force CPU (free GPU VRAM)"))
        self.chk_llm_cpu.setChecked(conf.get("DICTEE_LLM_CPU", "false") == "true")
        llm_lay.addRow("", self.chk_llm_cpu)

        lbl_vram = QLabel(
            "<i>" + _("~2 GB VRAM with Ministral 3B (+ ~2.5 GB Parakeet)") + "</i>")
        lbl_vram.setStyleSheet("font-size: 11px; opacity: 0.6;")
        llm_lay.addRow("", lbl_vram)

        pp_lay.addWidget(self._llm_widget)
        self._llm_widget.setVisible(self.chk_llm.isChecked())
        self.chk_llm.toggled.connect(self._llm_widget.setVisible)

        # Ajouter le conteneur et connecter le toggle
        lay.addWidget(self._pp_content)
        self._pp_content.setEnabled(self.chk_postprocess.isChecked())
        self.chk_postprocess.toggled.connect(self._pp_content.setEnabled)

    # ── Post-processing tabs ────────────────────────────────────

    def _build_rules_tab(self, lay):
        """Onglet Règles : éditeur texte monospace."""
        import os as _os
        XDG_CFG = _os.environ.get("XDG_CONFIG_HOME", _os.path.expanduser("~/.config"))
        self._rules_path = _os.path.join(XDG_CFG, "dictee", "rules.conf")

        info = QLabel(
            "<i>" + _("User rules in {path} — applied after system rules.").format(
                path="~/.config/dictee/rules.conf") + "</i>")
        info.setWordWrap(True)
        lay.addWidget(info)

        self._rules_editor = QTextEdit()
        self._rules_editor.setStyleSheet("font-family: monospace; font-size: 12px;")
        self._rules_editor.setPlaceholderText(
            "# [lang] /PATTERN/REPLACEMENT/FLAGS\n"
            "# Example:\n"
            "# [fr] /point à la ligne/\\n/ig\n")
        self._load_rules_file()
        lay.addWidget(self._rules_editor)

        btns = QHBoxLayout()
        btn_save = QPushButton(_("Save"))
        btn_restore = QPushButton(_("Restore defaults"))
        btns.addStretch()
        btns.addWidget(btn_restore)
        btns.addWidget(btn_save)
        lay.addLayout(btns)

        btn_save.clicked.connect(self._save_rules_file)
        btn_restore.clicked.connect(self._restore_rules_defaults)

    def _load_rules_file(self):
        import os as _os
        _os.makedirs(_os.path.dirname(self._rules_path), exist_ok=True)
        if _os.path.isfile(self._rules_path):
            with open(self._rules_path, encoding="utf-8") as f:
                self._rules_editor.setPlainText(f.read())
        else:
            self._rules_editor.clear()

    def _save_rules_file(self):
        import os as _os
        _os.makedirs(_os.path.dirname(self._rules_path), exist_ok=True)
        with open(self._rules_path, "w", encoding="utf-8") as f:
            f.write(self._rules_editor.toPlainText())
        QMessageBox.information(self, "dictee", _("Rules saved."))

    def _restore_rules_defaults(self):
        import os as _os
        for candidate in [
            _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "rules.conf.default"),
            "/usr/share/dictee/rules.conf.default",
        ]:
            if _os.path.isfile(candidate):
                shutil.copy2(candidate, self._rules_path)
                self._load_rules_file()
                QMessageBox.information(self, "dictee", _("Default rules restored."))
                return
        QMessageBox.warning(self, "dictee", _("Default rules file not found."))

    def _build_dictionary_tab(self, lay):
        """Onglet Dictionnaire : vue formulaire avec accordéons + mode avancé."""
        import os as _os

        XDG_CFG = _os.environ.get("XDG_CONFIG_HOME", _os.path.expanduser("~/.config"))
        self._dict_path = _os.path.join(XDG_CFG, "dictee", "dictionary.conf")

        # Chercher le fichier système
        self._dict_sys_path = None
        for candidate in [
            _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "dictionary.conf.default"),
            "/usr/share/dictee/dictionary.conf.default",
        ]:
            if _os.path.isfile(candidate):
                self._dict_sys_path = candidate
                break

        self._dict_stack = QStackedWidget()

        # --- Page 0 : Vue formulaire ---
        form_page = QWidget()
        form_top_lay = QVBoxLayout(form_page)
        form_top_lay.setContentsMargins(0, 0, 0, 0)

        # Barre d'outils
        toolbar = QHBoxLayout()
        self._dict_search = QComboBox()
        self._dict_search.setEditable(True)
        self._dict_search.setPlaceholderText("Search...")
        self._dict_search.setMinimumWidth(180)
        self._dict_search.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        toolbar.addWidget(self._dict_search)

        self._dict_lang_filter = QComboBox()
        self._dict_lang_filter.addItem(_("All languages"), "")
        toolbar.addWidget(self._dict_lang_filter)

        toolbar.addStretch()
        form_top_lay.addLayout(toolbar)

        # Zone scrollable (accordéons système uniquement)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        self._dict_sys_layout = QVBoxLayout(scroll_content)
        self._dict_sys_layout.setContentsMargins(4, 4, 4, 4)
        self._dict_sys_layout.setSpacing(6)
        scroll.setWidget(scroll_content)
        form_top_lay.addWidget(scroll, 3)

        # Zone personnelle (fixe, ne scrolle pas avec le système)
        self._dict_personal_container = QWidget()
        self._dict_personal_layout = QVBoxLayout(self._dict_personal_container)
        self._dict_personal_layout.setContentsMargins(4, 4, 4, 4)
        self._dict_personal_layout.setSpacing(4)
        form_top_lay.addWidget(self._dict_personal_container, 0)

        # Bouton ajouter + Appliquer/Annuler
        btns_form = QHBoxLayout()
        self._btn_dict_add = QPushButton("+ " + _("Add"))
        self._btn_dict_add.clicked.connect(lambda: self._add_dict_entry())
        btns_form.addWidget(self._btn_dict_add)
        btns_form.addStretch()
        btn_cancel_form = QPushButton(_("Cancel"))
        btn_cancel_form.clicked.connect(self._load_dict_form)
        btn_apply_form = QPushButton(_("Apply"))
        btn_apply_form.clicked.connect(self._save_dict_personal)
        btns_form.addWidget(btn_cancel_form)
        btns_form.addWidget(btn_apply_form)
        form_top_lay.addLayout(btns_form)

        self._dict_stack.addWidget(form_page)

        # --- Page 1 : Mode avancé ---
        adv_page = QWidget()
        adv_lay = QVBoxLayout(adv_page)
        adv_lay.setContentsMargins(0, 0, 0, 0)

        self._dict_adv_editor = QTextEdit()
        self._dict_adv_editor.setStyleSheet("font-family: monospace; font-size: 12px;")
        self._dict_adv_editor.setPlaceholderText(
            "# [lang] WORD=REPLACEMENT\n"
            "# Example:\n"
            "# [fr] sncf=SNCF\n"
            "# [*] api=API\n")
        adv_lay.addWidget(self._dict_adv_editor)

        btns_adv = QHBoxLayout()
        btns_adv.addStretch()
        btn_cancel_adv = QPushButton(_("Cancel"))
        btn_cancel_adv.clicked.connect(lambda: (
            self._btn_advanced.setChecked(False),
        ))
        btn_save_adv = QPushButton(_("Save"))
        btn_save_adv.clicked.connect(self._save_dict_advanced)
        btns_adv.addWidget(btn_cancel_adv)
        btns_adv.addWidget(btn_save_adv)
        adv_lay.addLayout(btns_adv)

        self._dict_stack.addWidget(adv_page)

        lay.addWidget(self._dict_stack)

        # Données personnelles
        self._dict_personal_rows = []

        # Connecter recherche et filtre
        self._dict_search.editTextChanged.connect(self._filter_dict_entries)
        self._dict_lang_filter.currentIndexChanged.connect(self._filter_dict_entries)

        # Charger le formulaire
        self._load_dict_form()

    def _parse_dict_with_categories(self, path):
        """Parse un fichier dictionnaire, retourne [(category, [(lang, word, replacement)])]."""
        categories = []
        current_cat = _("Other")
        current_entries = []
        cat_re = re.compile(r"^#\s*──\s*(.+?)\s*─")
        entry_re = re.compile(r"^\s*\[([a-z]{2}|\*)\]\s*(.+?)=(.+?)\s*$")
        if not os.path.isfile(path):
            return categories
        with open(path, encoding="utf-8") as f:
            for line in f:
                line_s = line.strip()
                if not line_s:
                    continue
                m_cat = cat_re.match(line_s)
                if m_cat:
                    if current_entries:
                        categories.append((current_cat, current_entries))
                    current_cat = m_cat.group(1).strip()
                    current_entries = []
                    continue
                if line_s.startswith("#"):
                    continue
                m = entry_re.match(line_s)
                if m:
                    current_entries.append((m.group(1), m.group(2).strip(), m.group(3).strip()))
        if current_entries:
            categories.append((current_cat, current_entries))
        return categories

    def _load_dict_form(self):
        """Vide et reconstruit le formulaire dictionnaire."""
        # Vider le layout système (scrollable)
        sys_layout = self._dict_sys_layout
        while sys_layout.count():
            item = sys_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Vider le layout personnel (fixe)
        perso_layout = self._dict_personal_layout
        while perso_layout.count():
            item = perso_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self._dict_personal_rows.clear()

        # Collecter toutes les langues pour le filtre
        all_langs = set()

        # --- Catégories système (dans le scroll) ---
        if self._dict_sys_path:
            sys_cats = self._parse_dict_with_categories(self._dict_sys_path)
            for cat_name, entries in sys_cats:
                for lang, _w, _r in entries:
                    if lang != "*":
                        all_langs.add(lang)
                # Bouton titre repliable (pas de checkbox)
                n_entries = len(entries)
                entry_lbl = _("entries") if n_entries > 1 else _("entry")
                btn_title = f"\u25b8 {cat_name} ({n_entries} {entry_lbl})"
                btn_toggle = QPushButton(btn_title)
                btn_toggle.setFlat(True)
                btn_toggle.setStyleSheet("text-align: left; font-weight: bold; padding: 4px;")
                sys_layout.addWidget(btn_toggle)

                # Contenu caché par défaut
                content_w = QWidget()
                content_w.setVisible(False)
                content_lay = QVBoxLayout(content_w)
                content_lay.setSpacing(2)
                content_lay.setContentsMargins(16, 0, 0, 4)

                def _make_toggle(btn, cw, cn=cat_name, ne=n_entries):
                    def _toggle():
                        vis = not cw.isVisible()
                        cw.setVisible(vis)
                        arrow = "\u25be" if vis else "\u25b8"
                        el = _("entries") if ne > 1 else _("entry")
                        btn.setText(f"{arrow} {cn} ({ne} {el})")
                    return _toggle
                btn_toggle.clicked.connect(_make_toggle(btn_toggle, content_w))

                for lang, word, repl in entries:
                    row = QHBoxLayout()
                    lbl_lang = QLabel(f"[{lang}]")
                    lbl_lang.setFixedWidth(40)
                    lbl_word = QLabel(word)
                    lbl_arrow = QLabel("\u2192")
                    lbl_arrow.setFixedWidth(20)
                    lbl_arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    lbl_repl = QLabel(repl)
                    row.addWidget(lbl_lang)
                    row.addWidget(lbl_word)
                    row.addWidget(lbl_arrow)
                    row.addWidget(lbl_repl)
                    row.addStretch()

                    container = QWidget()
                    container.setLayout(row)
                    container.setEnabled(False)
                    container.setProperty("dict_lang", lang)
                    container.setProperty("dict_word", word)
                    container.setProperty("dict_repl", repl)
                    content_lay.addWidget(container)

                sys_layout.addWidget(content_w)

        sys_layout.addStretch()

        # --- Entrées personnelles (zone fixe) ---
        accent = self.palette().color(self.palette().ColorRole.Highlight).name()
        sep_lbl = QLabel(f"<b style='color:{accent};'>" + _("YOUR PERSONAL ENTRIES") + "</b>")
        sep_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        perso_layout.addWidget(sep_lbl)

        # Collecter les mots système pour éviter les doublons
        sys_words = set()
        if self._dict_sys_path:
            for _cat, entries in self._parse_dict_with_categories(self._dict_sys_path):
                for lang, word, _r in entries:
                    sys_words.add((lang, word.lower()))
                    sys_words.add(("*", word.lower()))

        user_cats = self._parse_dict_with_categories(self._dict_path)
        has_entries = False
        for _cat, entries in user_cats:
            for lang, word, repl in entries:
                if (lang, word.lower()) in sys_words:
                    continue
                self._add_dict_entry(lang, word, repl)
                if lang != "*":
                    all_langs.add(lang)
                has_entries = True

        if not has_entries:
            self._dict_empty_label = QLabel(
                "<i>" + _("Add words that the ASR transcribes incorrectly.") + "</i>")
            self._dict_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            perso_layout.addWidget(self._dict_empty_label)
        else:
            self._dict_empty_label = None

        # Mettre à jour le filtre de langue
        self._dict_lang_filter.blockSignals(True)
        current = self._dict_lang_filter.currentData()
        self._dict_lang_filter.clear()
        self._dict_lang_filter.addItem(_("All languages"), "")
        for lang in sorted(all_langs):
            self._dict_lang_filter.addItem(lang, lang)
        # Restaurer la sélection
        idx = self._dict_lang_filter.findData(current)
        if idx >= 0:
            self._dict_lang_filter.setCurrentIndex(idx)
        self._dict_lang_filter.blockSignals(False)

    def _add_dict_entry(self, lang="*", word="", repl=""):
        """Crée une ligne éditable pour une entrée dictionnaire personnelle."""
        # Supprimer le label vide si présent
        if hasattr(self, '_dict_empty_label') and self._dict_empty_label is not None:
            self._dict_empty_label.deleteLater()
            self._dict_empty_label = None

        row_widget = QWidget()
        row_lay = QHBoxLayout(row_widget)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(4)

        cmb_lang = QComboBox()
        cmb_lang.setFixedWidth(60)
        cmb_lang.addItem("*")
        for code, _name in LANGUAGES:
            cmb_lang.addItem(code)
        idx = cmb_lang.findText(lang)
        if idx >= 0:
            cmb_lang.setCurrentIndex(idx)
        row_lay.addWidget(cmb_lang)

        edt_word = QLineEdit(word)
        edt_word.setPlaceholderText(_("Word"))
        row_lay.addWidget(edt_word)

        lbl_arrow = QLabel("\u2192")
        lbl_arrow.setFixedWidth(20)
        lbl_arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_lay.addWidget(lbl_arrow)

        edt_repl = QLineEdit(repl)
        edt_repl.setPlaceholderText(_("Replacement"))
        row_lay.addWidget(edt_repl)

        btn_del = QPushButton("\u2715")
        btn_del.setToolTip(_("Remove"))
        btn_del.setFixedWidth(30)
        btn_del.clicked.connect(lambda: self._remove_dict_entry(row_widget))
        row_lay.addWidget(btn_del)

        row_widget.setProperty("dict_lang_cmb", cmb_lang)
        row_widget.setProperty("dict_word_edt", edt_word)
        row_widget.setProperty("dict_repl_edt", edt_repl)

        self._dict_personal_layout.addWidget(row_widget)
        self._dict_personal_rows.append(row_widget)

    def _remove_dict_entry(self, entry):
        """Supprime une entrée personnelle du dictionnaire."""
        if entry in self._dict_personal_rows:
            self._dict_personal_rows.remove(entry)
        entry.deleteLater()

        if not self._dict_personal_rows:
            self._dict_empty_label = QLabel(
                "<i>" + _("Add words that the ASR transcribes incorrectly.") + "</i>")
            self._dict_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._dict_personal_layout.addWidget(self._dict_empty_label)

    def _filter_dict_entries(self):
        """Filtre les entrées visibles selon recherche et langue."""
        search = self._dict_search.currentText().lower()
        lang_filter = self._dict_lang_filter.currentData() or ""

        # Filtrer les groupes système (paires btn_toggle + content_w)
        layout = self._dict_sys_layout
        # Parcourir par paires : QPushButton titre, QWidget contenu
        i = 0
        while i < layout.count():
            item = layout.itemAt(i)
            if item is None:
                i += 1
                continue
            btn = item.widget()
            # Chercher le content_w suivant
            if btn is None or not isinstance(btn, QPushButton):
                i += 1
                continue
            i += 1
            if i >= layout.count():
                break
            content_item = layout.itemAt(i)
            content_w = content_item.widget() if content_item else None
            if content_w is None:
                i += 1
                continue
            i += 1
            # Filtrer les enfants du content_w
            content_lay = content_w.layout()
            if content_lay is None:
                continue
            any_visible = False
            for j in range(content_lay.count()):
                child_item = content_lay.itemAt(j)
                if child_item is None:
                    continue
                child = child_item.widget()
                if child is None:
                    continue
                c_lang = child.property("dict_lang") or ""
                c_word = child.property("dict_word") or ""
                c_repl = child.property("dict_repl") or ""
                visible = True
                if lang_filter and c_lang != "*" and c_lang != lang_filter:
                    visible = False
                if search and search not in c_word.lower() and search not in c_repl.lower():
                    visible = False
                child.setVisible(visible)
                if visible:
                    any_visible = True
            # Cacher le bouton titre + contenu si aucune entrée visible
            btn.setVisible(any_visible)
            content_w.setVisible(any_visible and content_w.isVisible())

        # Filtrer les entrées perso
        for row in self._dict_personal_rows:
            cmb = row.property("dict_lang_cmb")
            edt = row.property("dict_word_edt")
            if cmb is None or edt is None:
                continue
            r_lang = cmb.currentText()
            r_word = edt.text().lower()
            edt_r = row.property("dict_repl_edt")
            r_repl = edt_r.text().lower() if edt_r else ""
            visible = True
            if lang_filter and r_lang != "*" and r_lang != lang_filter:
                visible = False
            if search and search not in r_word and search not in r_repl:
                visible = False
            row.setVisible(visible)

    def _save_dict_personal(self):
        """Valide et sauvegarde les entrées personnelles du dictionnaire."""
        import os as _os

        entries = []
        empty_rows = []
        for row in self._dict_personal_rows:
            cmb = row.property("dict_lang_cmb")
            edt_w = row.property("dict_word_edt")
            edt_r = row.property("dict_repl_edt")
            if cmb is None or edt_w is None or edt_r is None:
                continue
            lang = cmb.currentText()
            word = edt_w.text().strip()
            repl = edt_r.text().strip()

            if not word and not repl:
                # Ligne vide — la supprimer visuellement
                empty_rows.append(row)
                continue
            if not word:
                QMessageBox.warning(self, "dictee",
                    _("Word cannot be empty."))
                return
            if "=" in word:
                QMessageBox.warning(self, "dictee",
                    _("Word cannot contain '=': {word}").format(word=word))
                return
            # Doublon lang+mot
            for prev_lang, prev_word, _pr in entries:
                if prev_lang == lang and prev_word.lower() == word.lower():
                    QMessageBox.warning(self, "dictee",
                        _("Duplicate entry: [{lang}] {word}").format(lang=lang, word=word))
                    return
            entries.append((lang, word, repl))

        # Supprimer les lignes vides de l'UI
        for row in empty_rows:
            self._remove_dict_entry(row)

        _os.makedirs(_os.path.dirname(self._dict_path), exist_ok=True)
        with open(self._dict_path, "w", encoding="utf-8") as f:
            f.write("# User dictionary for dictee\n")
            f.write("# Format: [lang] WORD=REPLACEMENT\n\n")
            for lang, word, repl in entries:
                f.write(f"[{lang}] {word}={repl}\n")

        QMessageBox.information(self, "dictee", _("Dictionary saved."))

    def _save_dict_advanced(self):
        """Sauvegarde le contenu du mode avancé et rebascule en vue formulaire."""
        import os as _os

        _os.makedirs(_os.path.dirname(self._dict_path), exist_ok=True)
        with open(self._dict_path, "w", encoding="utf-8") as f:
            f.write(self._dict_adv_editor.toPlainText())

        self._btn_advanced.setChecked(False)
        QMessageBox.information(self, "dictee", _("Dictionary saved."))

    # ── Continuation tab ────────────────────────────────────────

    _LANG_FLAGS = {
        "fr": "\U0001f1eb\U0001f1f7", "en": "\U0001f1ec\U0001f1e7",
        "de": "\U0001f1e9\U0001f1ea", "es": "\U0001f1ea\U0001f1f8",
        "it": "\U0001f1ee\U0001f1f9", "pt": "\U0001f1f5\U0001f1f9",
        "uk": "\U0001f1fa\U0001f1e6",
    }

    _LANG_FULLNAMES = {
        "fr": "Français", "en": "English", "de": "Deutsch",
        "es": "Español", "it": "Italiano", "pt": "Português",
        "uk": "Українська",
    }

    def _parse_cont_with_categories(self, path):
        """Parse un fichier continuation, retourne {lang: [(subcategory, [mot, ...])]}.

        Catégories principales : commentaires ``# ── Langue ─``
        Sous-catégories : commentaires ``# Sous-titre`` (sans ──)
        Entrées : ``[lang] mot1 mot2 ...``
        """
        result = {}  # lang -> [(subcat, [words])]
        current_lang = None
        current_subcat = _("Other")
        entry_re = re.compile(r"^\s*\[([a-z]{2})\]\s+(.+)$")
        lang_re = re.compile(r"^#\s*──\s*(.+?)\s*─")
        subcat_re = re.compile(r"^#\s+(.+)$")

        if not os.path.isfile(path):
            return result
        with open(path, encoding="utf-8") as f:
            for line in f:
                line_s = line.strip()
                if not line_s:
                    continue
                # Lang header  # ── French ──
                m_lang = lang_re.match(line_s)
                if m_lang:
                    current_subcat = _("Other")
                    continue
                # Sub-category  # Articles
                if line_s.startswith("#"):
                    m_sub = subcat_re.match(line_s)
                    if m_sub and "──" not in line_s:
                        current_subcat = m_sub.group(1).strip()
                    continue
                # Entry  [fr] le la les ...
                m = entry_re.match(line_s)
                if m:
                    lang = m.group(1)
                    words = m.group(2).split()
                    current_lang = lang
                    if lang not in result:
                        result[lang] = []
                    # Merge into existing subcat or create new
                    if result[lang] and result[lang][-1][0] == current_subcat:
                        result[lang][-1][1].extend(words)
                    else:
                        result[lang].append((current_subcat, list(words)))
        return result

    def _build_continuation_tab(self, lay):
        """Onglet Continuation : accordéons par langue avec chips + mode avancé."""
        import os as _os

        XDG_CFG = _os.environ.get("XDG_CONFIG_HOME", _os.path.expanduser("~/.config"))
        self._cont_path = _os.path.join(XDG_CFG, "dictee", "continuation.conf")

        # Chercher le fichier système
        self._cont_sys_path = None
        for candidate in [
            _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "continuation.conf.default"),
            "/usr/share/dictee/continuation.conf.default",
        ]:
            if _os.path.isfile(candidate):
                self._cont_sys_path = candidate
                break

        # Mots perso par langue : {lang: set()}
        self._cont_personal_words = {}

        self._cont_stack = QStackedWidget()

        # --- Page 0 : Vue formulaire ---
        form_page = QWidget()
        form_top_lay = QVBoxLayout(form_page)
        form_top_lay.setContentsMargins(0, 0, 0, 0)

        # Info label
        info = QLabel(_(
            "Words that never end a sentence. "
            "If the ASR puts a period after one, it is removed."
        ))
        info.setWordWrap(True)
        font = info.font()
        font.setItalic(True)
        info.setFont(font)
        form_top_lay.addWidget(info)

        # Zone scrollable pour les accordéons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cont_scroll_content = QWidget()
        self._cont_form_layout = QVBoxLayout(self._cont_scroll_content)
        self._cont_form_layout.setContentsMargins(4, 4, 4, 4)
        self._cont_form_layout.setSpacing(6)
        scroll.setWidget(self._cont_scroll_content)
        form_top_lay.addWidget(scroll)

        # Boutons formulaire
        btns_form = QHBoxLayout()
        btns_form.addStretch()
        btn_cancel = QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(self._load_cont_form)
        btn_apply = QPushButton(_("Apply"))
        btn_apply.clicked.connect(self._save_cont_personal)
        btns_form.addWidget(btn_cancel)
        btns_form.addWidget(btn_apply)
        form_top_lay.addLayout(btns_form)

        self._cont_stack.addWidget(form_page)

        # --- Page 1 : Mode avancé ---
        adv_page = QWidget()
        adv_lay = QVBoxLayout(adv_page)
        adv_lay.setContentsMargins(0, 0, 0, 0)

        self._cont_adv_editor = QTextEdit()
        self._cont_adv_editor.setStyleSheet("font-family: monospace; font-size: 12px;")
        self._cont_adv_editor.setPlaceholderText(
            "# [lang] word1 word2 word3 ...\n"
            "# Example:\n"
            "# [fr] donc alors\n"
            "# [en] however moreover\n")
        adv_lay.addWidget(self._cont_adv_editor)

        btns_adv = QHBoxLayout()
        btns_adv.addStretch()
        btn_cancel_adv = QPushButton(_("Cancel"))
        btn_cancel_adv.clicked.connect(lambda: (
            self._btn_advanced.setChecked(False),
        ))
        btn_save_adv = QPushButton(_("Save"))
        btn_save_adv.clicked.connect(self._save_cont_advanced)
        btns_adv.addWidget(btn_cancel_adv)
        btns_adv.addWidget(btn_save_adv)
        adv_lay.addLayout(btns_adv)

        self._cont_stack.addWidget(adv_page)

        lay.addWidget(self._cont_stack)

        # Charger le formulaire
        self._load_cont_form()

    def _load_cont_form(self):
        """Vide et reconstruit les accordéons de l'onglet Continuation."""
        layout = self._cont_form_layout

        # Vider le layout existant
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                sub = item.layout()
                while sub.count():
                    si = sub.takeAt(0)
                    sw = si.widget()
                    if sw:
                        sw.deleteLater()

        # Charger les mots système
        sys_cats = {}
        if self._cont_sys_path:
            sys_cats = self._parse_cont_with_categories(self._cont_sys_path)

        # Charger les mots perso
        user_cats = self._parse_cont_with_categories(self._cont_path)
        self._cont_personal_words.clear()
        for lang, subcats in user_cats.items():
            words_set = set()
            for _sc, words in subcats:
                words_set.update(words)
            self._cont_personal_words[lang] = words_set

        # Déterminer la langue active
        active_lang = self.conf.get("DICTEE_LANG_SOURCE", "fr")

        # Collecter toutes les langues (système + perso)
        all_langs = sorted(set(list(sys_cats.keys()) + list(self._cont_personal_words.keys())))

        # Construire un accordéon par langue
        for lang in all_langs:
            sys_words_all = []
            sys_subcats = sys_cats.get(lang, [])
            for _sc, words in sys_subcats:
                sys_words_all.extend(words)

            perso_words = self._cont_personal_words.get(lang, set())
            total = len(sys_words_all) + len(perso_words)

            flag = self._LANG_FLAGS.get(lang, "")
            name = self._LANG_FULLNAMES.get(lang, lang.upper())
            title = f"{flag} {name} ({total} " + (_("words") if total != 1 else _("word")) + ")"

            # Bouton titre repliable
            btn_lang = QPushButton(("\u25be " if lang == active_lang else "\u25b8 ") + title)
            btn_lang.setFlat(True)
            btn_lang.setStyleSheet("text-align: left; font-weight: bold; padding: 4px;")
            layout.addWidget(btn_lang)

            group = QWidget()
            group.setVisible(lang == active_lang)
            group_lay = QVBoxLayout(group)
            group_lay.setSpacing(4)
            group_lay.setContentsMargins(16, 4, 0, 8)

            def _make_lang_toggle(btn, w, t=title):
                def _toggle():
                    vis = not w.isVisible()
                    w.setVisible(vis)
                    btn.setText(("\u25be " if vis else "\u25b8 ") + t)
                return _toggle
            btn_lang.clicked.connect(_make_lang_toggle(btn_lang, group))

            # --- Mots système par sous-catégorie ---
            for subcat, words in sys_subcats:
                # Sous-titre
                lbl_sub = QLabel(f"<b>{subcat}</b>")
                group_lay.addWidget(lbl_sub)

                # Chips grisés (HTML inline)
                chips_html = " ".join(
                    f'<span style="background:#ddd;color:#555;border-radius:10px;'
                    f'padding:2px 8px;margin:2px;display:inline-block;font-size:11px;">'
                    f'{word}</span>'
                    for word in words
                )
                lbl_chips = QLabel(chips_html)
                lbl_chips.setWordWrap(True)
                lbl_chips.setTextFormat(Qt.TextFormat.RichText)
                group_lay.addWidget(lbl_chips)

            # --- Séparateur dashed ---
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("border: 1px dashed #999;")
            group_lay.addWidget(sep)

            acc = self.palette().color(self.palette().ColorRole.Highlight).name()
            lbl_yours = QLabel(f"<i style='color:{acc};'>" + _("Your additions:") + "</i>")
            group_lay.addWidget(lbl_yours)

            # --- Chips perso (QPushButtons cliquables) ---
            perso_container = QWidget()
            perso_container.setProperty("cont_lang", lang)
            perso_flow = QHBoxLayout(perso_container)
            perso_flow.setContentsMargins(0, 0, 0, 0)
            perso_flow.setSpacing(4)

            # Wrap dans un widget qui gère le wrapping
            perso_wrap = QWidget()
            perso_wrap_lay = self._make_flow_layout(perso_wrap)
            perso_wrap.setProperty("cont_lang", lang)
            perso_wrap.setProperty("is_perso_wrap", True)

            hl_color = self.palette().color(self.palette().ColorRole.Highlight)
            hl_text = self.palette().color(self.palette().ColorRole.HighlightedText)
            hl_hex = hl_color.name()
            hl_text_hex = hl_text.name()

            for word in sorted(perso_words):
                btn = QPushButton(f"{word} \u2715")
                btn.setFlat(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    f"QPushButton {{ background:{hl_hex}; color:{hl_text_hex}; "
                    f"border-radius:10px; padding:2px 8px; font-size:11px; }}"
                    f"QPushButton:hover {{ background:{hl_color.darker(120).name()}; }}"
                )
                btn.clicked.connect(lambda checked, w=word, l=lang: self._remove_cont_word(l, w))
                perso_wrap_lay.addWidget(btn)

            group_lay.addWidget(perso_wrap)

            # --- QLineEdit pour ajouter ---
            add_edit = QLineEdit()
            add_edit.setPlaceholderText(_("Add a word..."))
            add_edit.returnPressed.connect(
                lambda le=add_edit, l=lang: self._add_cont_word(l, le)
            )
            group_lay.addWidget(add_edit)

            layout.addWidget(group)

        layout.addStretch()

    def _make_flow_layout(self, parent):
        """Crée un layout horizontal avec wrapping simulé via QHBoxLayout.

        Note : un vrai FlowLayout serait idéal, mais QHBoxLayout + word-wrap
        sur le conteneur parent suffit ici car les chips sont petits.
        On utilise un simple QVBoxLayout contenant des QHBoxLayouts pour simuler.
        Retourne le layout (on ajoute directement les widgets).
        """
        # Utiliser un simple layout wrap-friendly
        try:
            from PyQt6.QtWidgets import QLayout
        except ImportError:
            from PySide6.QtWidgets import QLayout
        lay = QHBoxLayout(parent)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        return lay

    def _add_cont_word(self, lang, line_edit):
        """Ajoute un mot perso à la langue donnée et reconstruit le formulaire."""
        word = line_edit.text().strip().lower()
        if not word:
            return
        if lang not in self._cont_personal_words:
            self._cont_personal_words[lang] = set()
        if word in self._cont_personal_words[lang]:
            return  # déjà présent
        # Vérifier qu'il n'est pas déjà dans le système
        if self._cont_sys_path:
            sys_cats = self._parse_cont_with_categories(self._cont_sys_path)
            for _sc, words in sys_cats.get(lang, []):
                if word in words:
                    QMessageBox.information(self, "dictee",
                        _("'{word}' is already in the system list.").format(word=word))
                    return
        self._cont_personal_words[lang].add(word)
        self._load_cont_form()

    def _remove_cont_word(self, lang, word):
        """Supprime un mot perso et reconstruit le formulaire."""
        if lang in self._cont_personal_words:
            self._cont_personal_words[lang].discard(word)
        self._load_cont_form()

    def _save_cont_personal(self):
        """Sauvegarde les mots perso dans ~/.config/dictee/continuation.conf."""
        import os as _os

        _os.makedirs(_os.path.dirname(self._cont_path), exist_ok=True)
        with open(self._cont_path, "w", encoding="utf-8") as f:
            f.write("# User continuation words for dictee\n")
            f.write("# Format: [lang] word1 word2 ...\n\n")
            for lang in sorted(self._cont_personal_words.keys()):
                words = sorted(self._cont_personal_words[lang])
                if words:
                    f.write(f"[{lang}] {' '.join(words)}\n")

        QMessageBox.information(self, "dictee", _("Continuation words saved."))

    def _save_cont_advanced(self):
        """Sauvegarde le contenu du mode avancé et rebascule en vue formulaire."""
        import os as _os

        _os.makedirs(_os.path.dirname(self._cont_path), exist_ok=True)
        with open(self._cont_path, "w", encoding="utf-8") as f:
            f.write(self._cont_adv_editor.toPlainText())

        self._btn_advanced.setChecked(False)
        QMessageBox.information(self, "dictee", _("Continuation words saved."))

    def _toggle_advanced_mode(self, checked):
        """Bascule formulaire ↔ éditeur texte pour l'onglet actif."""
        idx = self._pp_tabs.currentIndex()
        if idx == 1:  # Dictionnaire
            if checked:
                if os.path.isfile(self._dict_path):
                    with open(self._dict_path, encoding="utf-8") as f:
                        self._dict_adv_editor.setPlainText(f.read())
                else:
                    self._dict_adv_editor.clear()
            else:
                self._load_dict_form()
            self._dict_stack.setCurrentIndex(1 if checked else 0)
        elif idx == 2:  # Continuation
            if checked:
                if os.path.isfile(self._cont_path):
                    with open(self._cont_path, encoding="utf-8") as f:
                        self._cont_adv_editor.setPlainText(f.read())
                else:
                    self._cont_adv_editor.clear()
            else:
                self._load_cont_form()
            self._cont_stack.setCurrentIndex(1 if checked else 0)

    def _build_mic_section(self, lay_mic, conf):
        """Build microphone source selection, volume slider, level meter."""
        saved_src = conf.get("DICTEE_AUDIO_SOURCE", "")

        self._audio_devices = QMediaDevices.audioInputs()
        self.cmb_audio_source = QComboBox()
        self.cmb_audio_source.addItem(_("System default"), "")
        for dev in self._audio_devices:
            self.cmb_audio_source.addItem(dev.description(), dev.id().data().decode())
        if saved_src:
            idx = self.cmb_audio_source.findData(saved_src)
            if idx >= 0:
                self.cmb_audio_source.setCurrentIndex(idx)
        self.cmb_audio_source.currentIndexChanged.connect(self._on_audio_source_changed)

        lay_mic.addWidget(QLabel(_("Audio source:")))
        lay_mic.addWidget(self.cmb_audio_source)

        # Volume slider
        lay_vol = QHBoxLayout()
        lay_vol.setSpacing(8)
        lbl_vol = QLabel(_("Volume:"))
        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(30)
        self.slider_volume.valueChanged.connect(self._on_volume_changed)
        self.lbl_vol_pct = QLabel("30%")
        lay_vol.addWidget(lbl_vol)
        lay_vol.addWidget(self.slider_volume, 1)
        lay_vol.addWidget(self.lbl_vol_pct)
        lay_mic.addLayout(lay_vol)

        # Level meter (custom painted — instant repaint)
        self.mic_level = LevelMeter()
        lay_mic.addWidget(self.mic_level)

        # In wizard mode, start audio level only when page 4 becomes visible
        if not self.wizard_mode:
            self._start_audio_level()

    # ── Wizard checks (page 5) ───────────────────────────────────

    def _run_wizard_checks(self):
        checks = {
            "daemon": self._check_daemon_active,
            "model": self._check_model_installed_fn,
            "shortcut": self._check_shortcut_registered,
            "audio": lambda: len(QMediaDevices.audioInputs()) > 0,
            "dotool": lambda: shutil.which("dotool") is not None,
        }
        all_ok = True
        for check_id, fn in checks.items():
            lbl_icon, lbl_status = self._check_labels[check_id]
            try:
                ok = fn()
            except Exception:
                ok = False
            if ok:
                lbl_icon.setText('<span style="color: green;">✓</span>')
                if check_id == "shortcut":
                    ptt_k = getattr(self, '_ptt_key', int(self.conf.get("DICTEE_PTT_KEY", 67)))
                    lbl_status.setText('<span style="color: green;">'
                                      + linux_keycode_name(ptt_k) + '</span>')
                else:
                    lbl_status.setText('<span style="color: green;">' + _("OK") + '</span>')
            else:
                lbl_icon.setText('<span style="color: red;">✗</span>')
                lbl_status.setText('<span style="color: red;">' + _("Not found") + '</span>')
                all_ok = False

        if all_ok:
            ptt_key = getattr(self, '_ptt_key', int(self.conf.get("DICTEE_PTT_KEY", 67)))
            shortcut = linux_keycode_name(ptt_key)
            ptt_mode = ""
            if hasattr(self, 'cmb_ptt_mode'):
                ptt_mode = self.cmb_ptt_mode.currentData()
            else:
                ptt_mode = self.conf.get("DICTEE_PTT_MODE", "toggle")
            mode_label = "hold" if ptt_mode == "hold" else "toggle"
            self.lbl_final.setText(
                '<div style="background: #1e2e1e; padding: 12px; border-radius: 8px;">'
                '<span style="color: #afa; font-size: 14pt; font-weight: bold;">'
                + _("Everything is ready!") + '</span><br>'
                '<span style="color: #8a8;">'
                + _("Press {key} anytime to dictate.").format(key=shortcut)
                + f' ({mode_label})'
                + '</span></div>'
            )

    def _check_daemon_active(self):
        asr = self._wizard_asr if hasattr(self, '_wizard_asr') else "parakeet"
        svc = {"parakeet": "dictee", "vosk": "dictee-vosk", "whisper": "dictee-whisper"}.get(asr, "dictee")
        # Le daemon peut mettre quelques secondes à démarrer (chargement modèle)
        import time
        for _ in range(10):
            try:
                r = subprocess.run(["systemctl", "--user", "is-active", svc],
                                   capture_output=True, text=True)
                if r.stdout.strip() == "active":
                    return True
            except (FileNotFoundError, OSError):
                pass
            time.sleep(0.5)
        return False

    def _check_model_installed_fn(self):
        asr = self._wizard_asr if hasattr(self, '_wizard_asr') else "parakeet"
        if asr == "parakeet":
            return all(model_is_installed(m) for m in ASR_MODELS if m["required"])
        elif asr == "vosk":
            return venv_is_installed(VOSK_VENV)
        elif asr == "whisper":
            return venv_is_installed(WHISPER_VENV)
        return True

    def _check_shortcut_registered(self):
        """Vérifie qu'une touche PTT est configurée (wizard ou dictee.conf)."""
        # Wizard en cours : on a _ptt_key défini
        if hasattr(self, '_ptt_key') and self._ptt_key:
            return True
        # Sinon, vérifier la config existante
        key = self.conf.get("DICTEE_PTT_KEY", "")
        return bool(key and int(key) > 0)

    # ── Audio helpers ─────────────────────────────────────────────

    def _on_volume_changed(self, value):
        self.lbl_vol_pct.setText(f"{value}%")
        # Debounce: apply volume after 50ms of inactivity
        if not hasattr(self, '_vol_timer'):
            self._vol_timer = QTimer(self)
            self._vol_timer.setSingleShot(True)
            self._vol_timer.timeout.connect(self._apply_volume)
        self._vol_timer.start(50)

    def _apply_volume(self):
        value = self.slider_volume.value()
        vol = value / 100.0
        src = self.cmb_audio_source.currentData()
        if shutil.which("wpctl"):
            subprocess.Popen(["wpctl", "set-volume", str(src) if src else "@DEFAULT_SOURCE@",
                              f"{vol:.2f}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("pactl"):
            pct = f"{value}%"
            subprocess.Popen(["pactl", "set-source-volume",
                              str(src) if src else "@DEFAULT_SOURCE@", pct],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _on_audio_source_changed(self, _index):
        """Restart audio level thread on new source."""
        self._stop_audio_level()
        self._start_audio_level()

    def _start_audio_level(self):
        if self._audio_monitor is not None:
            return
        idx = self.cmb_audio_source.currentIndex()
        if idx > 0 and idx - 1 < len(self._audio_devices):
            device = self._audio_devices[idx - 1]
        else:
            device = QMediaDevices.defaultAudioInput()
        self._audio_monitor = AudioLevelMonitor(self.mic_level, device)
        self._audio_monitor.start()

    def _stop_audio_level(self):
        if self._audio_monitor:
            self._audio_monitor.stop()
            self._audio_monitor = None

    def closeEvent(self, event):
        self._stop_audio_level()
        super().closeEvent(event)

    # ── Test dictation ────────────────────────────────────────────

    def _on_test_dictee(self):
        if self._test_thread and self._test_thread.isRunning():
            self._test_thread.stop()
            self.btn_test_dictee.setText("🎤 " + _("Test dictation"))
            self.btn_test_dictee.setEnabled(True)
            if hasattr(self, '_test_timer'):
                self._test_timer.stop()
            return
        self.txt_test_result.clear()
        self._test_countdown = 5
        self.btn_test_dictee.setText("⏹ " + _("Recording… {n}s").format(n=self._test_countdown))
        self._test_timer = QTimer(self)
        self._test_timer.timeout.connect(self._on_test_tick)
        self._test_timer.start(1000)
        pp_enabled = self.chk_postprocess.isChecked() if hasattr(self, 'chk_postprocess') else False
        self._test_thread = TestDicteeThread(duration=5, postprocess=pp_enabled)
        self._test_thread.result.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_tick(self):
        self._test_countdown -= 1
        if self._test_countdown > 0:
            self.btn_test_dictee.setText("⏹ " + _("Recording… {n}s").format(n=self._test_countdown))
        else:
            self.btn_test_dictee.setText("⏳ " + _("Transcribing…"))
            self._test_timer.stop()

    def _on_test_result(self, text):
        if hasattr(self, '_test_timer'):
            self._test_timer.stop()
        self.btn_test_dictee.setText("🎤 " + _("Test dictation"))
        self.txt_test_result.setPlainText(text)

    # ── Static helpers ────────────────────────────────────────────

    @staticmethod
    def _is_service_enabled(name):
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", name],
                capture_output=True, text=True,
            )
            return result.stdout.strip() == "enabled"
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

    @staticmethod
    def _system_lang():
        lang = os.environ.get("LANG", "")
        if lang:
            return lang.split("_")[0].split(".")[0]
        try:
            return locale.getdefaultlocale()[0].split("_")[0]
        except (AttributeError, IndexError):
            return "fr"

    @staticmethod
    def _set_combo_by_data(combo, data, fallback_idx):
        for i in range(combo.count()):
            if combo.itemData(i) == data:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(fallback_idx)

    # -- Filtrage langues selon backend --

    def _filter_lang_combo(self, combo, allowed_codes):
        """Repeuple un combo avec uniquement les langues autorisées.
        allowed_codes=None signifie toutes les langues."""
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for code, name in LANGUAGES:
            if allowed_codes is None or code in allowed_codes:
                combo.addItem(f"{code} — {name}", code)
        combo.blockSignals(False)
        # Restaurer la sélection précédente si toujours disponible
        idx = combo.findData(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)

    def _update_src_languages(self):
        """Filtre la langue source selon le backend ASR sélectionné."""
        if self.wizard_mode and hasattr(self, '_wizard_asr'):
            asr = self._wizard_asr
        elif hasattr(self, 'cmb_asr_backend'):
            asr = self.cmb_asr_backend.currentData()
        else:
            asr = "parakeet"
        if asr == "vosk" and hasattr(self, 'cmb_vosk_lang'):
            # Vosk = mono-langue, uniquement la langue du modèle sélectionné
            vosk_lang = self.cmb_vosk_lang.currentData()
            allowed = {vosk_lang} if vosk_lang else ASR_LANGUAGES.get("vosk")
        else:
            allowed = ASR_LANGUAGES.get(asr)
        self._filter_lang_combo(self.combo_src, allowed)

    def _update_tgt_languages(self):
        """Filtre la langue cible selon le backend de traduction sélectionné."""
        if not hasattr(self, 'cmb_trans_backend'):
            return
        backend = self.cmb_trans_backend.currentData()
        if backend == "libretranslate":
            # Langues installées dans Docker
            port = int(self.spin_lt_port.currentText()) if hasattr(self, 'spin_lt_port') else 5000
            avail = libretranslate_available_languages(port=port)
            allowed = set(avail) if avail else None
        else:
            allowed = TRANSLATE_LANGUAGES.get(backend)
        self._filter_lang_combo(self.combo_tgt, allowed)

    # -- Capture raccourci --

    def _on_ptt_key_captured(self, seq):
        code = qt_key_to_linux_keycode(seq)
        if code:
            self._ptt_key = code
            self.btn_capture.setText(_("Key: {name}").format(name=linux_keycode_name(code)))
            self.btn_capture._changed = True
            self._dirty = True
            self._check_ptt_warning(code, self.lbl_ptt_warning)
        else:
            key_str = seq.toString() if seq else "?"
            self.lbl_ptt_warning.setText(
                '<span style="color: red;">⚠ ' +
                _("Key '{key}' is not supported. Use a function key (F1-F12).").format(key=key_str) +
                '</span>'
            )
            self.lbl_ptt_warning.setVisible(True)

    def _on_ptt_key_translate_captured(self, seq):
        code = qt_key_to_linux_keycode(seq)
        if code:
            self._ptt_key_translate = code
            self.btn_capture_translate.setText(_("Key: {name}").format(name=linux_keycode_name(code)))
            self.btn_capture_translate._changed = True
            self._dirty = True
        else:
            key_str = seq.toString() if seq else "?"
            self.btn_capture_translate.setText(
                _("Key '{key}' not supported").format(key=key_str))

    def _check_ptt_warning(self, code, lbl):
        """Avertit si la touche risque de poser problème."""
        # Touches dangereuses : lettres, chiffres, espace, enter, tab
        dangerous = {14, 15, 28, 57}  # backspace, tab, enter, space
        dangerous.update(range(2, 12))  # 1-0
        dangerous.update(range(16, 26))  # q-p
        dangerous.update(range(30, 39))  # a-l
        dangerous.update(range(44, 51))  # z-m
        if code in dangerous:
            lbl.setText(
                '<span style="color: orange;">⚠ ' +
                _("This key is used for typing. Prefer a function key (F1-F12) "
                  "or a special key (Home, End, Insert, etc.).") +
                '</span>'
            )
            lbl.setVisible(True)
        elif code == 1:  # ESC
            lbl.setText(
                '<span style="color: orange;">⚠ ' +
                _("Escape is used to cancel dictation. Choose another key.") +
                '</span>'
            )
            lbl.setVisible(True)
        else:
            lbl.setVisible(False)

    def _on_translate_mode_changed(self, _idx):
        mode = self.cmb_translate_mode.currentData()
        self.btn_capture_translate.setVisible(mode == "separate")

    def _on_shortcut_captured(self, seq):
        """Legacy — redirige vers PTT."""
        self._on_ptt_key_captured(seq)

    def _on_shortcut_translate_captured(self, seq):
        """Legacy — redirige vers PTT."""
        self._on_ptt_key_translate_captured(seq)

    # -- Animation-speech --

    def _check_animation_speech(self):
        parts = []
        has_anim = shutil.which(ANIMATION_SPEECH_BIN)
        if has_anim:
            try:
                result = subprocess.run(
                    ["dpkg-query", "-W", "-f", "${Version}", "animation-speech"],
                    capture_output=True, text=True,
                )
                v = result.stdout.strip() if result.returncode == 0 else ""
                if v:
                    parts.append('<span style="color: green;">' +
                                 _("animation-speech {version} installed").format(version=v) +
                                 '</span>')
                else:
                    parts.append('<span style="color: green;">' +
                                 _("animation-speech installed") + '</span>')
            except FileNotFoundError:
                parts.append('<span style="color: green;">' +
                             _("animation-speech installed") + '</span>')
            self.btn_install_anim.setVisible(False)
        else:
            self.btn_install_anim.setVisible(True)
            if self.de_type == "gnome":
                self.btn_install_anim.setEnabled(False)

        has_plasmoid = os.path.isdir(
            os.path.expanduser("~/.local/share/plasma/plasmoids/com.github.rcspam.dictee")
        ) or os.path.isdir("/usr/share/plasma/plasmoids/com.github.rcspam.dictee")
        if has_plasmoid:
            parts.append('<span style="color: green;">' +
                         _("Dictee plasmoid installed") + '</span>')

        if parts:
            self.lbl_anim_status.setText(" — ".join(parts))

    def _on_install_animation(self):
        self.btn_install_anim.setEnabled(False)
        self.btn_install_anim.setText(_("Downloading…"))
        self.progress_anim.setVisible(True)

        self._install_thread = InstallThread()
        self._install_thread.progress.connect(lambda text: self.btn_install_anim.setText(text))
        self._install_thread.finished.connect(self._on_install_finished)
        self._install_thread.start()

    def _on_install_finished(self, success, message):
        self.progress_anim.setVisible(False)
        if success:
            self._check_animation_speech()
        else:
            self.btn_install_anim.setText(_("Install animation-speech"))
            self.btn_install_anim.setEnabled(True)
            QMessageBox.critical(self, _("Installation error"), message)

    # -- Ollama backend --

    def _on_ollama_model_changed(self, _index):
        if self.cmb_trans_backend.currentData() == "ollama":
            self._check_ollama_status()

    def _check_ollama_status(self):
        if not ollama_is_installed():
            self.lbl_ollama_status.setText(
                '<span style="color: red;">⚠ ' +
                _("ollama is not installed") + '</span><br>'
                '<small><a href="https://ollama.com">https://ollama.com</a></small>'
            )
            self.lbl_ollama_status.setOpenExternalLinks(True)
            self.btn_ollama_pull.setVisible(False)
            return

        model = self.combo_ollama_model.currentData()
        min_ram = 8
        min_vram = 4
        for m_id, _label, m_ram, m_vram in OLLAMA_MODELS:
            if m_id == model:
                min_ram, min_vram = m_ram, m_vram
                break

        sys_ram = get_system_ram_gb()
        vram_total, vram_free = get_gpu_vram_gb()
        warnings = []
        if sys_ram and sys_ram < min_ram:
            warnings.append(
                '<span style="color: orange;">⚠ ' +
                _("RAM: {actual} GB / {required} GB recommended").format(
                    actual=sys_ram, required=min_ram) +
                '</span>')
        vram_insufficient = False
        if vram_total:
            if vram_free < min_vram:
                vram_insufficient = True
                warnings.append(
                    '<span style="color: orange;">⚠ ' +
                    _("VRAM free: {free} GB / {required} GB required (total: {total} GB)").format(
                        free=vram_free, required=min_vram, total=vram_total) +
                    '</span>')
        else:
            vram_insufficient = True
            warnings.append(
                '<small><i>' +
                _("No GPU detected — ollama will use CPU (slower).") +
                '</i></small>')

        if vram_insufficient and not vram_total:
            self.chk_ollama_cpu.setChecked(True)

        hw_info = ""
        if warnings:
            hw_info = "<br>" + "<br>".join(warnings)

        if ollama_has_model(model):
            self.lbl_ollama_status.setText(
                '<span style="color: green;">✓ ' +
                _("Model {model} ready").format(model=model) + '</span>' +
                hw_info
            )
            self.btn_ollama_pull.setVisible(False)
        else:
            self.lbl_ollama_status.setText(
                '<span style="color: orange;">⚠ ' +
                _("Model {model} not downloaded").format(model=model) + '</span>' +
                hw_info
            )
            self.btn_ollama_pull.setVisible(True)
            self.btn_ollama_pull.setText(_("Download model"))
            self.btn_ollama_pull.setEnabled(True)

    def _on_ollama_pull(self):
        model = self.combo_ollama_model.currentData()
        self.btn_ollama_pull.setEnabled(False)
        self.progress_ollama.setVisible(True)

        self._ollama_pull_thread = OllamaPullThread(model)
        self._ollama_pull_thread.progress.connect(
            lambda text: self.btn_ollama_pull.setText(text))
        self._ollama_pull_thread.finished.connect(self._on_ollama_pull_finished)
        self._ollama_pull_thread.start()

    def _on_ollama_pull_finished(self, success, message):
        self.progress_ollama.setVisible(False)
        if success:
            self._check_ollama_status()
        else:
            self.btn_ollama_pull.setText(_("Download model"))
            self.btn_ollama_pull.setEnabled(True)
            QMessageBox.critical(self, _("Download error"), message)

    # -- LibreTranslate backend --

    def _on_lt_toggled(self, checked):
        self.lt_widget.setVisible(checked)
        if checked:
            self._check_lt_status()

    def _check_lt_status(self):
        if not docker_is_installed():
            self.lbl_lt_status.setText(
                '<span style="color: red;">⚠ ' +
                _("Docker is not installed") + '</span><br>'
                '<small>sudo apt install docker.io</small>')
            self.btn_lt_pull.setVisible(False)
            self.btn_lt_start.setVisible(False)
            self.btn_lt_stop.setVisible(False)
            return

        if not docker_is_accessible():
            self.lbl_lt_status.setText(
                '<span style="color: red;">⚠ ' +
                _("Docker permission denied") + '</span>')
            # Bouton ajouter au groupe docker
            if not hasattr(self, '_btn_fix_docker_group'):
                self._btn_fix_docker_group = QPushButton(_("Fix permissions (requires password)"))
                self._btn_fix_docker_group.setFixedWidth(280)
                self._btn_fix_docker_group.clicked.connect(self._on_fix_docker_group)
                self.lt_widget.layout().addWidget(self._btn_fix_docker_group)
            self._btn_fix_docker_group.setVisible(True)
            self.btn_lt_pull.setVisible(False)
            self.btn_lt_start.setVisible(False)
            self.btn_lt_stop.setVisible(False)
            return
        if hasattr(self, '_btn_fix_docker_group'):
            self._btn_fix_docker_group.setVisible(False)

        if not docker_has_image():
            self.lbl_lt_status.setText(
                '<span style="color: orange;">⚠ ' +
                _("Docker image not downloaded (~2 GB)") + '</span>'
            )
            self.btn_lt_pull.setVisible(True)
            self.btn_lt_pull.setEnabled(True)
            self.btn_lt_start.setVisible(False)
            self.btn_lt_stop.setVisible(False)
            return

        if docker_container_running():
            port = self.spin_lt_port.currentText()
            # Taille du conteneur (image + données modèles)
            size_info = _docker_container_size()
            size_str = f" — {size_info}" if size_info else ""
            status_html = (
                '<span style="color: green;">✓ ' +
                _("LibreTranslate running on port {port}").format(port=port) +
                '</span>' +
                ('<small style="color: #888;"> ' + size_str + '</small>' if size_str else '')
            )
            # Vérifier que les langues source/cible sont disponibles
            avail = libretranslate_available_languages(port=int(port))
            if avail:
                src = self.combo_src.currentData()
                tgt = self.combo_tgt.currentData()
                missing = []
                if src not in avail:
                    missing.append(src)
                if tgt not in avail:
                    missing.append(tgt)
                if missing:
                    status_html += (
                        '<br><span style="color: orange;">⚠ ' +
                        _("Language(s) not available: {langs}").format(
                            langs=", ".join(missing)) +
                        '</span><br><small>' +
                        _("Available: {langs}. Restart to add missing languages.").format(
                            langs=", ".join(avail)) +
                        '</small>'
                    )
            self.lbl_lt_status.setText(status_html)
            self.btn_lt_pull.setVisible(False)
            self.btn_lt_start.setVisible(False)
            self.btn_lt_stop.setVisible(True)
        else:
            self.lbl_lt_status.setText(
                '<span style="color: orange;">⚠ ' +
                _("LibreTranslate stopped") + '</span>'
            )
            self.btn_lt_pull.setVisible(False)
            self.btn_lt_start.setVisible(True)
            self.btn_lt_stop.setVisible(False)

    def _get_lt_selected_langs(self):
        """Retourne les langues cochées, en forçant source et cible."""
        langs = set()
        for code, chk in self._lt_lang_checks.items():
            if chk.isChecked():
                langs.add(code)
        # Toujours inclure source et cible
        langs.add(self.combo_src.currentData())
        langs.add(self.combo_tgt.currentData())
        return sorted(langs)

    def _update_lt_lang_checks(self):
        """Coche automatiquement les langues source/cible (sans griser)."""
        src = self.combo_src.currentData()
        tgt = self.combo_tgt.currentData()
        for code, chk in self._lt_lang_checks.items():
            if code in (src, tgt) and not chk.isChecked():
                chk.blockSignals(True)
                chk.setChecked(True)
                chk.blockSignals(False)

    def _on_lt_langs_changed(self):
        """Affiche le bouton de redémarrage si les langues ont changé."""
        if not docker_container_running():
            self.btn_lt_restart_langs.setVisible(False)
            self.lbl_lt_langs_hint.setVisible(False)
            return
        selected = set(self._get_lt_selected_langs())
        port = self.spin_lt_port.currentText()
        installed = set(libretranslate_available_languages(port=int(port)))
        if selected != installed and installed:
            added = selected - installed
            removed = installed - selected
            parts = []
            if added:
                parts.append("+ " + ", ".join(sorted(added)))
            if removed:
                parts.append("− " + ", ".join(sorted(removed)))
            self.lbl_lt_langs_hint.setText(
                '<small style="color: #888;">' +
                _("Changes: {changes}").format(changes=" / ".join(parts)) +
                '</small>')
            self.lbl_lt_langs_hint.setVisible(True)
            self.btn_lt_restart_langs.setVisible(True)
        else:
            self.lbl_lt_langs_hint.setVisible(False)
            self.btn_lt_restart_langs.setVisible(False)

    def _on_lt_restart_langs(self):
        """Redémarre le conteneur Docker avec les nouvelles langues."""
        if self._lt_is_busy():
            return
        languages = ",".join(self._get_lt_selected_langs())
        port = int(self.spin_lt_port.currentText())

        # Sauvegarder immédiatement dans la config
        self._save_lt_langs_to_config(languages)

        self._lt_set_buttons_busy(True)
        self.lbl_lt_status.setText(
            '<span style="color: #888;">⏳ ' +
            _("Restarting with languages: {langs}…").format(langs=languages) + '</span>')

        self._lt_action_thread = _DockerActionThread("restart", port=port, languages=languages)
        self._lt_action_thread.progress.connect(self._on_lt_progress)
        self._lt_action_thread.finished.connect(self._on_lt_restart_langs_finished)
        self._lt_action_thread.start()

    def _save_lt_langs_to_config(self, langs):
        """Met à jour DICTEE_LIBRETRANSLATE_LANGS dans dictee.conf (écriture atomique)."""
        os.makedirs(os.path.dirname(CONF_PATH), exist_ok=True)
        if not os.path.exists(CONF_PATH):
            with open(CONF_PATH, "w") as f:
                f.write(f"# Generated by dictee-setup\nDICTEE_LIBRETRANSLATE_LANGS={langs}\n")
            return
        lines = []
        found = False
        with open(CONF_PATH) as f:
            for line in f:
                if line.startswith("DICTEE_LIBRETRANSLATE_LANGS="):
                    lines.append(f"DICTEE_LIBRETRANSLATE_LANGS={langs}\n")
                    found = True
                else:
                    lines.append(line)
        if not found:
            inserted = False
            for i, line in enumerate(lines):
                if line.startswith("DICTEE_LIBRETRANSLATE_PORT="):
                    lines.insert(i + 1, f"DICTEE_LIBRETRANSLATE_LANGS={langs}\n")
                    inserted = True
                    break
            if not inserted:
                lines.append(f"DICTEE_LIBRETRANSLATE_LANGS={langs}\n")
        tmp_path = CONF_PATH + ".tmp"
        with open(tmp_path, "w") as f:
            f.writelines(lines)
        os.replace(tmp_path, CONF_PATH)

    def _on_lt_restart_langs_finished(self, success, message):
        self._lt_set_buttons_busy(False)
        self._lt_starting_after_apply = False
        # Invalider le cache pour forcer une requête fraîche
        _lt_langs_cache["time"] = 0
        if not success:
            QMessageBox.critical(self, _("Error"), message)
        self.btn_lt_restart_langs.setVisible(False)
        self.lbl_lt_langs_hint.setVisible(False)
        self._check_lt_status()

    def _on_fix_docker_group(self):
        """Ajoute l'utilisateur au groupe docker via pkexec."""
        user = os.environ.get("USER", "")
        if not user:
            return
        try:
            result = subprocess.run(
                ["pkexec", "usermod", "-aG", "docker", user],
                capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                QMessageBox.information(
                    self, _("Docker"),
                    _("User added to 'docker' group.") + "\n\n" +
                    _("You must log out and log back in for this to take effect."))
            else:
                QMessageBox.critical(self, _("Error"), result.stderr.strip())
        except Exception as e:
            QMessageBox.critical(self, _("Error"), str(e))
        self._check_lt_status()

    def _on_lt_pull(self):
        self.btn_lt_pull.setEnabled(False)
        self.progress_lt.setVisible(True)

        self._docker_pull_thread = DockerPullThread()
        self._docker_pull_thread.progress.connect(
            lambda text: self.btn_lt_pull.setText(text))
        self._docker_pull_thread.finished.connect(self._on_lt_pull_finished)
        self._docker_pull_thread.start()

    def _on_lt_pull_finished(self, success, message):
        self.progress_lt.setVisible(False)
        if success:
            self._check_lt_status()
        else:
            self.btn_lt_pull.setText(_("Download image"))
            self.btn_lt_pull.setEnabled(True)
            QMessageBox.critical(self, _("Download error"), message)

    def _on_lt_start(self):
        if self._lt_is_busy():
            return
        port = int(self.spin_lt_port.currentText())
        languages = ",".join(self._get_lt_selected_langs())
        self._save_lt_langs_to_config(languages)

        self._lt_set_buttons_busy(True)
        self.lbl_lt_status.setText(
            '<span style="color: #888;">⏳ ' +
            _("Starting LibreTranslate…") + '</span>')

        self._lt_action_thread = _DockerActionThread("start", port=port, languages=languages)
        self._lt_action_thread.progress.connect(self._on_lt_progress)
        self._lt_action_thread.finished.connect(self._on_lt_action_finished)
        self._lt_action_thread.start()

    def _on_lt_stop(self):
        if self._lt_is_busy():
            return

        self._lt_set_buttons_busy(True)
        self.lbl_lt_status.setText(
            '<span style="color: #888;">⏳ ' +
            _("Stopping LibreTranslate…") + '</span>')

        self._lt_action_thread = _DockerActionThread("stop")
        self._lt_action_thread.progress.connect(self._on_lt_progress)
        self._lt_action_thread.finished.connect(self._on_lt_action_finished)
        self._lt_action_thread.start()

    def _lt_is_busy(self):
        """Vérifie si une opération Docker est en cours."""
        return (self._lt_action_thread is not None
                and self._lt_action_thread.isRunning())

    def _lt_set_buttons_busy(self, busy):
        """Désactive/réactive tous les boutons Docker LT."""
        enabled = not busy
        self.btn_lt_start.setEnabled(enabled)
        self.btn_lt_stop.setEnabled(enabled)
        self.btn_lt_restart_langs.setEnabled(enabled)
        self.progress_lt.setVisible(busy)

    def _on_lt_progress(self, text):
        """Met à jour le label de statut avec la progression."""
        self.lbl_lt_status.setText(
            '<span style="color: #888;">⏳ ' + text + '</span>')

    def _on_lt_action_finished(self, success, message):
        self._lt_set_buttons_busy(False)
        self._lt_starting_after_apply = False
        _lt_langs_cache["time"] = 0
        if not success:
            QMessageBox.critical(self, _("Error"), message)
        self._check_lt_status()

    # -- Modèles ASR --

    def _on_model_download(self, model):
        mid = model["id"]
        w = self._model_widgets[mid]
        w["button"].setEnabled(False)
        w["progress"].setVisible(True)

        thread = ModelDownloadThread(model)
        thread.progress.connect(lambda text, _m=mid: self._on_model_progress(_m, text))
        thread.finished.connect(lambda ok, msg, _m=mid: self._on_model_download_finished(_m, ok, msg))
        self._model_threads[mid] = thread
        thread.start()

    def _on_model_progress(self, mid, text):
        w = self._model_widgets[mid]
        w["button"].setText(text)
        # Extraire le pourcentage du texte ("filename  42.3%")
        import re as _re
        m = _re.search(r"([\d.]+)%", text)
        if m:
            try:
                pct = int(float(m.group(1)))
                w["progress"].setRange(0, 100)
                w["progress"].setValue(pct)
            except ValueError:
                pass

    def _on_model_download_finished(self, mid, success, message):
        w = self._model_widgets[mid]
        w["progress"].setVisible(False)
        model = w["model"]
        if success:
            w["button"].setText(_("Installed"))
            w["button"].setEnabled(False)
            w["button"].setToolTip("")
            w["label"].setText(f'<span style="color: green;">✓</span> {model["name"]}<br>'
                               f'<span style="font-size: 9.5pt; color: gray;">{model["desc"]}</span>')
            # If TDT just installed, enable Sortformer button
            if mid == "tdt" and "sortformer" in self._model_widgets:
                dep_w = self._model_widgets["sortformer"]
                if not model_is_installed(dep_w["model"]):
                    dep_w["button"].setEnabled(True)
                    dep_w["button"].setToolTip("")
        else:
            w["button"].setText(_("Download"))
            w["button"].setEnabled(True)
            QMessageBox.critical(self, _("Download error"), message)

    # -- Installation venv ASR --

    def _install_venv(self, name, venv_path, pip_package):
        btn = self.btn_install_vosk if name == "vosk" else self.btn_install_whisper
        if not isinstance(btn, QPushButton):
            return
        btn.setEnabled(False)
        btn.setText(_("Installing…"))
        thread = VenvInstallThread(venv_path, pip_package)
        thread.progress.connect(lambda text: btn.setText(text))
        thread.finished.connect(lambda ok, msg, n=name: self._on_venv_installed(n, ok, msg))
        self._venv_threads[name] = thread
        thread.start()

    def _on_venv_installed(self, name, success, message):
        btn = self.btn_install_vosk if name == "vosk" else self.btn_install_whisper
        if success:
            if isinstance(btn, QPushButton):
                btn.setText(_("Installed"))
                btn.setEnabled(False)
        else:
            if isinstance(btn, QPushButton):
                btn.setText(_("Install"))
                btn.setEnabled(True)
            QMessageBox.critical(self, _("Installation error"), message)

    def _mark_dirty(self):
        self._dirty = True

    # -- Panneau de test post-traitement --

    def _build_test_panel(self, lay):
        """Panneau de test compact : entrée → sortie sur une ligne + micro."""
        # Ligne unique : [input] → [output] [🎤]
        row = QHBoxLayout()
        row.setSpacing(4)

        self._test_input = QLineEdit()
        self._test_input.setPlaceholderText(_("Type text or record..."))
        row.addWidget(self._test_input, 3)

        lbl_arrow = QLabel("\u2192")
        lbl_arrow.setFixedWidth(20)
        lbl_arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(lbl_arrow)

        self._test_output = QLineEdit()
        self._test_output.setReadOnly(True)
        self._test_output.setPlaceholderText(_("Output"))
        row.addWidget(self._test_output, 3)

        accent = self.palette().color(self.palette().ColorRole.Highlight).name()
        self._btn_record = QPushButton("\U0001f3a4")
        self._btn_record.setFixedWidth(36)
        self._btn_record.setToolTip(_("Record"))
        self._btn_record.setStyleSheet(
            f"font-size: 16px; background-color: {accent}; color: white; border-radius: 4px;")
        row.addWidget(self._btn_record)

        btn_details = QPushButton("\u2026")
        btn_details.setFixedWidth(28)
        btn_details.setToolTip(_("Pipeline details"))
        btn_details.setCheckable(True)
        row.addWidget(btn_details)

        lay.addLayout(row)

        # Détails pipeline (caché par défaut)
        self._test_details_label = QLabel("")
        self._test_details_label.setWordWrap(True)
        self._test_details_label.setStyleSheet("font-family: monospace; font-size: 10px;")
        self._test_details_label.setVisible(False)
        lay.addWidget(self._test_details_label)

        btn_details.toggled.connect(self._test_details_label.setVisible)

        # Connecter
        self._test_input.textChanged.connect(self._schedule_test_run)
        self._btn_record.clicked.connect(self._toggle_recording)

        # Timer debounce
        self._test_timer = QTimer()
        self._test_timer.setSingleShot(True)
        self._test_timer.setInterval(300)
        self._test_timer.timeout.connect(self._run_test_pipeline)

        # État enregistrement
        self._recording_process = None

    def _schedule_test_run(self):
        self._test_timer.start()

    def _run_test_pipeline(self):
        """Exécute le pipeline de postprocess étape par étape."""
        text = self._test_input.text()
        if not text.strip():
            self._test_output.setText("")
            self._test_details_label.setText("")
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        try:
            import importlib.util
            lang = self.conf.get("DICTEE_LANG_SOURCE", "fr")
            os.environ["DICTEE_LANG_SOURCE"] = lang

            spec = importlib.util.spec_from_file_location(
                "dictee_postprocess",
                os.path.join(script_dir, "dictee-postprocess.py"))
            pp = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pp)

            steps = []
            current = text

            # Lire l'état des toggles (protégé si widgets pas encore créés)
            do_numbers = self.chk_pp_numbers.isChecked() if hasattr(self, 'chk_pp_numbers') else True
            do_elisions = self.chk_pp_elisions.isChecked() if hasattr(self, 'chk_pp_elisions') else True
            do_typography = self.chk_pp_typography.isChecked() if hasattr(self, 'chk_pp_typography') else True
            do_capitalization = self.chk_pp_capitalization.isChecked() if hasattr(self, 'chk_pp_capitalization') else True
            do_fuzzy_dict = self.chk_pp_fuzzy_dict.isChecked() if hasattr(self, 'chk_pp_fuzzy_dict') else True

            # 1. Règles regex
            rules = pp.load_rules()
            if rules:
                new = pp.apply_rules(current, rules).strip()
                steps.append((_("Rules"), current, new))
                current = new

            # 2. Rejet mauvaise langue
            _LATIN = {"fr", "en", "de", "es", "it", "pt", "nl", "pl", "ro",
                       "cs", "sv", "da", "no", "fi", "hu", "tr"}
            _CYRILLIC = {"ru", "uk", "bg", "sr", "mk", "be"}
            letters = [c for c in current if c.isalpha()]
            if letters and lang:
                cyrillic = sum(1 for c in letters if '\u0400' <= c <= '\u04ff')
                ratio = cyrillic / len(letters)
                if lang in _LATIN and ratio > 0.5:
                    self._test_output.setText(
                        _("Rejected: ASR detected Cyrillic instead of {lang}").format(lang=lang))
                    self._test_details_label.setText("")
                    return
                if lang in _CYRILLIC and ratio < 0.2:
                    self._test_output.setText(
                        _("Rejected: ASR detected Latin instead of {lang}").format(lang=lang))
                    self._test_details_label.setText("")
                    return

            # 3. Continuation
            cont_words = pp.load_continuation()
            if cont_words:
                new = pp.fix_continuation(current, cont_words)
                steps.append((_("Continuation"), current, new))
                current = new

            # 4. Élisions (FR)
            if lang == "fr" and do_elisions:
                new = pp.fix_elisions(current)
                steps.append((_("Elisions"), current, new))
                current = new

            # 5. Nombres
            if do_numbers:
                new = pp.convert_numbers(current)
                steps.append((_("Numbers"), current, new))
                current = new

            # 6. Typographie (FR)
            if lang == "fr" and do_typography:
                new = pp.fix_french_typography(current)
                steps.append((_("Typography"), current, new))
                current = new

            # 7. Dictionnaire
            dictionary = pp.load_dictionary()
            if dictionary:
                new = pp.apply_dictionary(current, dictionary, fuzzy=do_fuzzy_dict)
                steps.append((_("Dictionary"), current, new))
                current = new

            # 8. Capitalisation
            if do_capitalization:
                new = pp.fix_capitalization(current)
                steps.append((_("Capitalization"), current, new))
                current = new

            self._test_output.setText(current)

            # Détails
            lines = []
            for i, (name, before, after) in enumerate(steps, 1):
                changed = before != after
                marker = " \u2190 " + _("changed") if changed else ""
                display = after.replace("\n", "\\n").replace("\t", "\\t")
                if len(display) > 100:
                    display = display[:100] + "\u2026"
                lines.append(f"{i}. {name} \u2192 {display}{marker}")
            self._test_details_label.setText("\n".join(lines))

        except Exception as e:
            self._test_output.setText(f"Error: {e}")

    def _toggle_recording(self):
        """Démarre/arrête l'enregistrement micro."""
        if self._recording_process is not None:
            self._recording_process.terminate()
            self._recording_process.waitForFinished(2000)
            self._recording_process = None
            self._btn_record.setText("\U0001f3a4")
            self._transcribe_recorded()
            return

        # Vérifier daemon
        services = ["dictee.service", "dictee-vosk.service", "dictee-whisper.service"]
        active = False
        for svc in services:
            try:
                r = subprocess.run(["systemctl", "--user", "is-active", svc],
                                   capture_output=True, text=True, timeout=3)
                if r.stdout.strip() == "active":
                    active = True
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        if not active:
            reply = QMessageBox.question(
                self, "dictee",
                _("No ASR service is running. Start the default service?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                backend = self.conf.get("DICTEE_ASR_BACKEND", "parakeet")
                svc_map = {"parakeet": "dictee.service", "vosk": "dictee-vosk.service",
                           "whisper": "dictee-whisper.service"}
                subprocess.Popen(["systemctl", "--user", "start",
                                  svc_map.get(backend, "dictee.service")])
            else:
                return

        # Démarrer enregistrement
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        self._tmp_wav = os.path.join(runtime_dir, "dictee-test-recording.wav")
        self._recording_process = QProcess(self)
        self._recording_process.start("pw-record", [
            "--rate", "16000", "--channels", "1", "--format", "s16",
            self._tmp_wav])
        self._btn_record.setText(_("Stop"))

    def _transcribe_recorded(self):
        """Envoie le WAV enregistré au daemon via socket Unix."""
        import socket as _socket
        wav_path = getattr(self, '_tmp_wav', None)
        if not wav_path or not os.path.isfile(wav_path):
            return
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        sock_path = os.path.join(runtime_dir, "dictee", "transcribe.sock")
        if not os.path.exists(sock_path):
            sock_path = "/tmp/transcribe.sock"
        try:
            s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            s.settimeout(30)
            s.connect(sock_path)
            s.sendall((wav_path + "\n").encode())
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            s.close()
            text = data.decode("utf-8").strip()
            if text:
                self._test_input.setText(text)
        except (_socket.error, OSError) as e:
            QMessageBox.warning(self, "dictee",
                                _("Cannot connect to ASR daemon: {err}").format(err=str(e)))
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    # -- Appliquer --

    def _on_apply(self):
        trans_data = self.cmb_trans_backend.currentData()
        if trans_data == "ollama":
            backend = "ollama"
        elif trans_data == "libretranslate":
            backend = "libretranslate"
        else:
            backend = "trans"
        lang_src = self.combo_src.currentData()
        lang_tgt = self.combo_tgt.currentData()
        clipboard = self.chk_clipboard.isChecked()

        a_speech = self.chk_anim_speech.isChecked()
        a_plasmoid = self.chk_plasmoid.isChecked()
        if a_speech and a_plasmoid:
            animation = "both"
        elif a_speech:
            animation = "speech"
        elif a_plasmoid:
            animation = "plasmoid"
        else:
            animation = "none"

        ollama_model = self.combo_ollama_model.currentData()
        ollama_cpu = self.chk_ollama_cpu.isChecked()
        if trans_data and trans_data.startswith("trans:"):
            trans_engine = trans_data.split(":")[1]
        else:
            trans_engine = "google"
        lt_port = int(self.spin_lt_port.currentText()) if self.spin_lt_port.currentText().isdigit() else 5000
        lt_langs = ",".join(self._get_lt_selected_langs()) if hasattr(self, '_lt_lang_checks') else ""

        # Backend ASR — wizard uses _wizard_asr, classic uses cmb_asr_backend
        if self.wizard_mode and hasattr(self, '_wizard_asr'):
            asr_backend = self._wizard_asr
        else:
            asr_backend = self.cmb_asr_backend.currentData() or "parakeet"

        whisper_model = self.cmb_whisper_model.currentText()
        whisper_lang = self.txt_whisper_lang.currentText().strip()
        vosk_model = self.cmb_vosk_lang.currentData() or "fr"

        # Audio source
        audio_source = ""
        if hasattr(self, 'cmb_audio_source') and self.cmb_audio_source.isEnabled():
            audio_source = self.cmb_audio_source.currentData() or ""

        # PTT config
        ptt_mode = self.cmb_ptt_mode.currentData() if hasattr(self, 'cmb_ptt_mode') else "toggle"
        ptt_key = getattr(self, '_ptt_key', 67)
        ptt_mod_translate = ""

        translate_mode = self.cmb_translate_mode.currentData() if hasattr(self, 'cmb_translate_mode') else "disabled"
        if translate_mode == "same_alt":
            ptt_key_translate = ptt_key
            ptt_mod_translate = "alt"
        elif translate_mode == "same_ctrl":
            ptt_key_translate = ptt_key
            ptt_mod_translate = "ctrl"
        elif translate_mode == "same_shift":
            ptt_key_translate = ptt_key
            ptt_mod_translate = "shift"
        elif translate_mode == "separate":
            ptt_key_translate = getattr(self, '_ptt_key_translate', 0)
        else:  # disabled
            ptt_key_translate = 0

        # Post-processing
        postprocess = self.chk_postprocess.isChecked() if hasattr(self, 'chk_postprocess') else True
        pp_elisions = self.chk_pp_elisions.isChecked() if hasattr(self, 'chk_pp_elisions') else True
        pp_numbers = self.chk_pp_numbers.isChecked() if hasattr(self, 'chk_pp_numbers') else True
        pp_typography = self.chk_pp_typography.isChecked() if hasattr(self, 'chk_pp_typography') else True
        pp_capitalization = self.chk_pp_capitalization.isChecked() if hasattr(self, 'chk_pp_capitalization') else True
        pp_fuzzy_dict = self.chk_pp_fuzzy_dict.isChecked() if hasattr(self, 'chk_pp_fuzzy_dict') else True
        llm_postprocess = self.chk_llm.isChecked() if hasattr(self, 'chk_llm') else False
        llm_model = self.cmb_llm_model.currentText() if hasattr(self, 'cmb_llm_model') else "ministral:3b"
        llm_cpu = self.chk_llm_cpu.isChecked() if hasattr(self, 'chk_llm_cpu') else False

        save_config(backend, lang_src, lang_tgt, clipboard, animation,
                    ollama_model, ollama_cpu, trans_engine, lt_port, lt_langs,
                    asr_backend, whisper_model, whisper_lang, vosk_model,
                    audio_source=str(audio_source),
                    ptt_mode=ptt_mode, ptt_key=ptt_key,
                    ptt_key_translate=ptt_key_translate,
                    ptt_mod_translate=ptt_mod_translate,
                    postprocess=postprocess,
                    pp_elisions=pp_elisions, pp_numbers=pp_numbers,
                    pp_typography=pp_typography, pp_capitalization=pp_capitalization,
                    pp_fuzzy_dict=pp_fuzzy_dict,
                    llm_postprocess=llm_postprocess,
                    llm_model=llm_model, llm_cpu=llm_cpu)

        # Services systemd — recharger d'abord (nécessaire après première install .deb)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)

        # Services systemd — ASR
        asr_services = {"parakeet": "dictee", "vosk": "dictee-vosk", "whisper": "dictee-whisper"}
        active_svc = asr_services.get(asr_backend, "dictee")
        if self.chk_daemon.isChecked():
            for svc_name in asr_services.values():
                if svc_name == active_svc:
                    subprocess.run(["systemctl", "--user", "enable", "--now", svc_name], capture_output=True)
                    subprocess.run(["systemctl", "--user", "restart", svc_name], capture_output=True)
                else:
                    subprocess.run(["systemctl", "--user", "disable", "--now", svc_name], capture_output=True)
        else:
            for svc_name in asr_services.values():
                subprocess.run(["systemctl", "--user", "disable", "--now", svc_name], capture_output=True)

        # Tray
        action = "enable" if self.chk_tray.isChecked() else "disable"
        subprocess.run(["systemctl", "--user", action, "--now", "dictee-tray"], capture_output=True)

        # PTT service — activer et (re)démarrer
        subprocess.run(["systemctl", "--user", "enable", "dictee-ptt"], capture_output=True)
        subprocess.run(["systemctl", "--user", "restart", "dictee-ptt"], capture_output=True)

        # Supprimer les anciens raccourcis KDE/GNOME (dictee-ptt les remplace)
        shortcut_msg = ""
        if self.de_type == "kde":
            for desktop in (DICTEE_DESKTOP, DICTEE_TRANSLATE_DESKTOP):
                try:
                    remove_kde_shortcut(desktop)
                except Exception:
                    pass
            shortcut_msg = "\n" + _("PTT key: {key} ({mode})").format(
                key=linux_keycode_name(ptt_key), mode=ptt_mode)

        self._dirty = False

        # Proposer de démarrer/redémarrer LibreTranslate si nécessaire
        # Proposer de démarrer/redémarrer LibreTranslate si nécessaire
        self._lt_starting_after_apply = False
        if backend == "libretranslate" and docker_is_installed() and docker_is_accessible():
            self._prompt_lt_server()

        if not self.wizard_mode:
            QMessageBox.information(
                self,
                _("Configuration saved"),
                _("File: {path}").format(path=CONF_PATH) + shortcut_msg,
            )

    def _prompt_lt_server(self):
        """Propose de démarrer/redémarrer LibreTranslate après Apply."""
        selected = set(self._get_lt_selected_langs())
        running = docker_container_running()
        port = int(self.spin_lt_port.currentText())

        if running:
            # Vérifier si les langues ont changé
            installed = set(libretranslate_available_languages(port=port))
            if selected == installed:
                return  # Rien à faire, tout est à jour
            # Langues différentes → proposer restart
            added = selected - installed
            removed = installed - selected
            details = []
            if added:
                details.append(_("Add: {langs}").format(langs=", ".join(sorted(added))))
            if removed:
                details.append(_("Remove: {langs}").format(langs=", ".join(sorted(removed))))
            msg = (
                _("The LibreTranslate languages have changed.") + "\n\n" +
                "\n".join(details) + "\n\n" +
                _("Restart the server now to apply changes?") + "\n" +
                _("(This will download missing models if needed)")
            )
            reply = QMessageBox.question(
                self, _("LibreTranslate"), msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._lt_starting_after_apply = True
                self._on_lt_restart_langs()
        else:
            # Serveur arrêté → proposer de le démarrer
            if not docker_has_image():
                return  # Pas d'image, rien à proposer
            n_langs = len(selected)
            msg = (
                _("LibreTranslate is not running.") + "\n\n" +
                _("Start the server with {n} languages ({langs})?").format(
                    n=n_langs, langs=", ".join(sorted(selected))) + "\n" +
                _("(This will download missing models if needed)")
            )
            reply = QMessageBox.question(
                self, _("LibreTranslate"), msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._lt_starting_after_apply = True
                self._on_lt_start()

    def _on_ok(self):
        if self._dirty:
            self._on_apply()
        # Ne pas fermer si LibreTranslate est en cours de démarrage
        if getattr(self, '_lt_starting_after_apply', False):
            return
        self.accept()


def main():
    wizard_flag = "--wizard" in sys.argv
    postprocess_flag = "--postprocess" in sys.argv
    app = QApplication([])
    app.setApplicationName("dictee-setup")
    app.setDesktopFileName("dictee-setup")
    app.setWindowIcon(QIcon.fromTheme("dictee-setup"))
    dialog = DicteeSetupDialog(wizard=wizard_flag, open_postprocess=postprocess_flag)
    dialog.exec()


if __name__ == "__main__":
    main()
