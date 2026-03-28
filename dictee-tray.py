#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dictee-tray — Icône de zone de notification pour dictee
Substitut au plasmoid KDE pour les bureaux non-KDE.
Clic gauche = dictée, Ctrl+clic gauche = traduction, clic droit = menu.

Backend automatique :
- GNOME/Unity/Cinnamon : AyatanaAppIndicator3 + GTK3
- KDE/autres : PyQt6 QSystemTrayIcon
"""

import gettext
import os
import signal
import subprocess
import sys

# === i18n ===
LOCALE_DIRS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "po"),
    "/usr/share/locale",
    "/usr/local/share/locale",
]
for _d in LOCALE_DIRS:
    if os.path.isfile(os.path.join(_d, "fr", "LC_MESSAGES", "dictee.mo")):
        gettext.bindtextdomain("dictee", _d)
        break
gettext.textdomain("dictee")
_ = gettext.gettext

# === Configuration ===

STATE_FILE = "/dev/shm/.dictee_state"
TRANSLATE_FLAG = "/tmp/dictee_translate"
APP_ID = "dictee"
SERVICES = ("dictee", "dictee-vosk", "dictee-whisper", "dictee-canary")
CONF_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "dictee.conf",
)
POLL_SLOW_MS = 3000


def read_conf_value(key, default=""):
    """Read a single value from dictee.conf."""
    if not os.path.exists(CONF_PATH):
        return default
    try:
        with open(CONF_PATH) as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    val = line.split("=", 1)[1].strip()
                    # Remove surrounding quotes if present
                    if len(val) >= 2 and val[0] in ('"', "'") and val[-1] == val[0]:
                        val = val[1:-1]
                    return val
    except OSError:
        pass
    return default


ASR_BACKENDS = [
    ("parakeet", "Parakeet"),
    ("canary", "Canary"),
    ("vosk", "Vosk"),
    ("whisper", "Whisper"),
]

TRANSLATE_BACKENDS = [
    ("google", "Google Translate"),
    ("bing", "Bing"),
    ("ollama", "Ollama"),
    ("libretranslate", "LibreTranslate"),
]


def _current_asr_backend():
    return read_conf_value("DICTEE_ASR_BACKEND", "parakeet")


def _current_translate_backend():
    backend = read_conf_value("DICTEE_TRANSLATE_BACKEND", "trans")
    if backend == "trans":
        engine = read_conf_value("DICTEE_TRANS_ENGINE", "google")
        return engine  # "google" or "bing"
    return backend  # "ollama" or "libretranslate"


def _is_translate_enabled():
    return read_conf_value("DICTEE_TRANSLATE", "false").lower() == "true"


def _asr_service_exists(key):
    """Check if the systemd service for an ASR backend exists."""
    svc_map = {"parakeet": "dictee", "canary": "dictee-canary",
               "vosk": "dictee-vosk", "whisper": "dictee-whisper"}
    svc = svc_map.get(key, "")
    try:
        result = subprocess.run(
            ["systemctl", "--user", "list-unit-files", f"{svc}.service"],
            capture_output=True, text=True,
        )
        return svc in result.stdout
    except FileNotFoundError:
        return False


# Icônes
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ICON_SEARCH_DIRS = [
    os.path.join(_SCRIPT_DIR, "icons"),
    "/usr/share/icons/hicolor/scalable/apps",
]

ICON_DIR = None
for _d in _ICON_SEARCH_DIRS:
    if os.path.isfile(os.path.join(_d, "parakeet-active.svg")):
        ICON_DIR = _d
        break


def _is_dark_theme():
    """Détecte si le thème du panel est sombre (KDE/GNOME)."""
    try:
        result = subprocess.run(
            ["kreadconfig6", "--group", "Colors:Window", "--key", "BackgroundNormal"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            r, g, b = (int(x) for x in result.stdout.strip().split(","))
            return (r + g + b) / 3 < 128
    except (FileNotFoundError, ValueError):
        pass
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True,
        )
        if "dark" in result.stdout.lower():
            return True
    except FileNotFoundError:
        pass
    return False


_DARK = _is_dark_theme()

ICON_MAP = {
    "idle": "parakeet-active-dark" if _DARK else "parakeet-active",
    "offline": "parakeet-offline",
    "recording": "parakeet-recording",
    "transcribing": "parakeet-transcribing",
}


def _icon_path(name):
    """Chemin absolu vers le fichier SVG d'une icône."""
    if ICON_DIR:
        path = os.path.join(ICON_DIR, f"{name}.svg")
        if os.path.isfile(path):
            return path
    return None


def daemon_is_active():
    """Vérifie si un des 3 services daemon est actif via systemctl."""
    for svc in SERVICES:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", svc],
                capture_output=True, text=True,
            )
            if result.stdout.strip() == "active":
                return True
        except FileNotFoundError:
            return False
    return False


def _conf_asr_service():
    """Lit DICTEE_ASR_BACKEND dans dictee.conf et retourne le nom du service."""
    mapping = {"parakeet": "dictee", "vosk": "dictee-vosk",
               "whisper": "dictee-whisper", "canary": "dictee-canary"}
    try:
        with open(CONF_PATH) as f:
            for line in f:
                if line.startswith("DICTEE_ASR_BACKEND="):
                    backend = line.strip().split("=", 1)[1]
                    return mapping.get(backend)
    except FileNotFoundError:
        pass
    return None


def _write_state(state):
    """Écrit l'état dans le fichier partagé (sans flock — best effort)."""
    try:
        with open(STATE_FILE, "w") as f:
            f.write(state + "\n")
    except OSError:
        pass


def daemon_start():
    """Démarre le service daemon configuré (enable + restart)."""
    # 1. Lire le backend depuis dictee.conf
    conf_svc = _conf_asr_service()
    if conf_svc:
        result = subprocess.run(
            ["systemctl", "--user", "enable", "--now", conf_svc],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            _write_state("idle")
        return
    # 2. Fallback: chercher un service déjà enabled
    for svc in SERVICES:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", svc],
                capture_output=True, text=True,
            )
            if result.stdout.strip() == "enabled":
                result = subprocess.run(
                    ["systemctl", "--user", "restart", svc],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                if result.returncode == 0:
                    _write_state("idle")
                return
        except FileNotFoundError:
            pass
    subprocess.run(
        ["systemctl", "--user", "restart", "dictee"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def daemon_stop():
    """Arrête tous les services daemon et nettoie l'état failed."""
    for svc in SERVICES:
        try:
            subprocess.run(
                ["systemctl", "--user", "stop", svc],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["systemctl", "--user", "reset-failed", svc],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass


def read_state():
    """Lit l'état depuis /dev/shm/.dictee_state."""
    try:
        with open(STATE_FILE, "r") as f:
            state = f.read().strip()
            if state in ("recording", "transcribing", "switching"):
                return state
            if state in ("cancelled", "idle"):
                return "idle"
    except (FileNotFoundError, PermissionError):
        pass
    return None


def _detect_backend():
    """Détecte le backend à utiliser : 'appindicator' ou 'qt'."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if any(name in desktop for name in ("GNOME", "UNITY", "CINNAMON")):
        try:
            import gi
            gi.require_version('AyatanaAppIndicator3', '0.1')
            gi.require_version('Gtk', '3.0')
            from gi.repository import AyatanaAppIndicator3  # noqa: F401
            return "appindicator"
        except (ImportError, ValueError):
            pass
    return "qt"


# ═══════════════════════════════════════════════════════════════
#  Backend AppIndicator3 (GNOME / Unity / Cinnamon)
# ═══════════════════════════════════════════════════════════════

class DicteeTrayAppIndicator:
    def __init__(self):
        import gi
        gi.require_version('AyatanaAppIndicator3', '0.1')
        gi.require_version('Gtk', '3.0')
        from gi.repository import AyatanaAppIndicator3, Gtk, GLib
        self.Gtk = Gtk
        self.GLib = GLib
        self.AyatanaAppIndicator3 = AyatanaAppIndicator3

        self.state = "offline"
        self._prev_state = None
        self._daemon_active = False

        # Créer l'indicateur
        icon_name = ICON_MAP.get("offline", "parakeet-offline")
        icon_p = _icon_path(icon_name)
        if icon_p:
            self.indicator = AyatanaAppIndicator3.Indicator.new(
                APP_ID, icon_p,
                AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS)
            self.indicator.set_icon_theme_path(ICON_DIR or "")
        else:
            self.indicator = AyatanaAppIndicator3.Indicator.new(
                APP_ID, "dialog-information",
                AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS)

        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

        # Menu
        self.menu = Gtk.Menu()
        self._build_menu()
        self.menu.connect("show", lambda _: self._refresh_backend_radios())
        self.indicator.set_menu(self.menu)

        # Premier check
        self._check_daemon()
        self._check_state()
        self._apply_state()

        # Polling état (GLib timer)
        GLib.timeout_add(POLL_SLOW_MS, self._poll)

        # Watch fichier état via GLib.io_add_watch si disponible
        self._setup_file_watch()

    def _build_menu(self):
        Gtk = self.Gtk

        self.item_dictee = Gtk.MenuItem(label=_("Start dictation"))
        self.item_dictee.connect("activate", lambda _: subprocess.Popen(["dictee"]))
        self.menu.append(self.item_dictee)

        self.item_translate = Gtk.MenuItem(label=_("Start translation"))
        self.item_translate.connect("activate", lambda _: subprocess.Popen(["dictee", "--translate"]))
        self.menu.append(self.item_translate)

        self.item_cancel = Gtk.MenuItem(label=_("Cancel"))
        self.item_cancel.connect("activate", lambda _: subprocess.Popen(["dictee", "--cancel"]))
        self.menu.append(self.item_cancel)

        self.menu.append(Gtk.SeparatorMenuItem())

        self.item_daemon = Gtk.MenuItem(label="")
        self.item_daemon.connect("activate", self._on_daemon_toggle)
        self.menu.append(self.item_daemon)

        # ASR backend submenu
        self.submenu_asr = Gtk.Menu()
        self.item_asr = Gtk.MenuItem(label=_("ASR backend"))
        self.item_asr.set_submenu(self.submenu_asr)
        self.menu.append(self.item_asr)

        self._asr_radios = []
        group = None
        for key, label in ASR_BACKENDS:
            item = Gtk.RadioMenuItem(label=label, group=group)
            if group is None:
                group = item
            item.connect("toggled", self._on_asr_toggled, key)
            self.submenu_asr.append(item)
            self._asr_radios.append((key, item))

        # Translate backend submenu
        self.submenu_trans = Gtk.Menu()
        self.item_trans = Gtk.MenuItem(label=_("Translation"))
        self.item_trans.set_submenu(self.submenu_trans)
        self.menu.append(self.item_trans)

        self._trans_radios = []
        group = None
        for key, label in TRANSLATE_BACKENDS:
            item = Gtk.RadioMenuItem(label=label, group=group)
            if group is None:
                group = item
            item.connect("toggled", self._on_trans_toggled, key)
            self.submenu_trans.append(item)
            self._trans_radios.append((key, item))

        self.menu.append(Gtk.SeparatorMenuItem())

        item_setup = Gtk.MenuItem(label=_("Configure Dictée"))
        item_setup.connect("activate", lambda _: subprocess.Popen(["dictee-setup"]))
        self.menu.append(item_setup)

        item_postprocess = Gtk.MenuItem(label=_("Post-processing..."))
        item_postprocess.connect("activate", lambda _: subprocess.Popen(["dictee-setup", "--postprocess"]))
        self.menu.append(item_postprocess)

        self.menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label=_("Quit icon"))
        item_quit.connect("activate", lambda _: self.Gtk.main_quit())
        self.menu.append(item_quit)

        self.menu.show_all()

    def _on_daemon_toggle(self, _item):
        if self.state == "offline":
            daemon_start()
            self._start_retries = 0
            self.GLib.timeout_add(1000, self._poll_daemon_start)
        else:
            daemon_stop()
            self.GLib.timeout_add(1000, self._delayed_refresh)

    def _poll_daemon_start(self):
        self._start_retries += 1
        self._check_daemon()
        if self._daemon_active:
            self._check_state()
            self._apply_state()
            return False
        if self._start_retries >= 10:
            self._check_state()
            self._apply_state()
            return False
        return True  # retry in 1s

    def _setup_file_watch(self):
        """Surveille le fichier état via inotify (GLib)."""
        try:
            from gi.repository import Gio
            if os.path.isfile(STATE_FILE):
                f = Gio.File.new_for_path(STATE_FILE)
                self._monitor = f.monitor_file(Gio.FileMonitorFlags.NONE, None)
                self._monitor.connect("changed", self._on_file_changed)
        except Exception:
            pass

    def _on_file_changed(self, _monitor, _file, _other, event):
        self._check_state()
        self._apply_state()

    def _check_daemon(self):
        self._daemon_active = daemon_is_active()

    def _check_state(self):
        file_state = read_state()
        if file_state in ("recording", "transcribing"):
            self.state = file_state
        elif file_state == "switching":
            self.state = "idle"  # Stay idle during backend switch
        elif self._daemon_active:
            self.state = "idle"
        else:
            self.state = "offline"

    def _apply_state(self):
        if self.state == self._prev_state:
            return

        # Icône
        icon_name = ICON_MAP.get(self.state, ICON_MAP["offline"])
        icon_p = _icon_path(icon_name)
        if icon_p:
            self.indicator.set_icon_full(icon_p, self.state)
        else:
            self.indicator.set_icon_full(icon_name, self.state)

        # Menu daemon
        if self.state == "offline":
            self.item_daemon.set_label(f"▶ {_('Start daemon')}")
        else:
            labels = {"idle": _("Daemon active"), "recording": _("Recording…"),
                      "transcribing": _("Transcribing…")}
            self.item_daemon.set_label(f"■ {labels.get(self.state, _('Daemon active'))}")

        # Menu dictée / traduction
        is_busy = self.state in ("recording", "transcribing")
        is_translating = is_busy and os.path.isfile(TRANSLATE_FLAG)
        self.item_dictee.set_label(
            _("Stop translation") if is_translating
            else _("Stop dictation") if is_busy
            else _("Start dictation"))
        self.item_dictee.set_sensitive(self.state != "offline")
        self.item_translate.set_sensitive(self.state != "offline")
        self.item_translate.set_visible(not is_busy)
        self.item_cancel.set_visible(is_busy)

        self._prev_state = self.state

    def _poll(self):
        self._check_daemon()
        self._check_state()
        self._apply_state()
        # Re-setup file watch si perdu
        self._setup_file_watch()
        return True  # GLib.SOURCE_CONTINUE

    def _on_asr_toggled(self, item, key):
        if item.get_active():
            subprocess.Popen(["dictee-switch-backend", "asr", key])
            from gi.repository import GLib
            GLib.timeout_add(2000, self._delayed_daemon_refresh)

    def _on_trans_toggled(self, item, key):
        if item.get_active():
            subprocess.Popen(["dictee-switch-backend", "translate", key])

    def _delayed_daemon_refresh(self):
        self._check_daemon()
        self._check_state()
        self._apply_state()
        return False  # one-shot

    def _refresh_backend_radios(self):
        current_asr = _current_asr_backend()
        for key, item in self._asr_radios:
            item.handler_block_by_func(self._on_asr_toggled)
            item.set_active(key == current_asr)
            item.set_sensitive(_asr_service_exists(key))
            item.handler_unblock_by_func(self._on_asr_toggled)

        # Disable translation submenu when using canary (built-in translation)
        self.item_trans.set_sensitive(current_asr != "canary")
        current_trans = _current_translate_backend()
        for key, item in self._trans_radios:
            item.handler_block_by_func(self._on_trans_toggled)
            item.set_active(key == current_trans)
            item.handler_unblock_by_func(self._on_trans_toggled)

    def _delayed_refresh(self):
        self._check_daemon()
        self._check_state()
        self._apply_state()
        return False  # GLib.SOURCE_REMOVE

    def run(self):
        self.Gtk.main()


# ═══════════════════════════════════════════════════════════════
#  Backend Qt (KDE / Sway / Hyprland / autres)
# ═══════════════════════════════════════════════════════════════

class DicteeTrayQt:
    def __init__(self, app):
        from PyQt6.QtCore import Qt, QTimer, QFileSystemWatcher
        from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
        from PyQt6.QtWidgets import QSystemTrayIcon, QMenu

        self.Qt = Qt
        self.QTimer = QTimer
        self.QIcon = QIcon
        self.QSystemTrayIcon = QSystemTrayIcon
        self.QApplication = type(app)

        self.app = app
        self.state = "offline"
        self._prev_state = None
        self._daemon_active = False

        # Charger les icônes
        self._icons = {}
        for state_name, icon_name in ICON_MAP.items():
            path = _icon_path(icon_name)
            if path:
                self._icons[state_name] = QIcon(path)
            else:
                self._icons[state_name] = QIcon.fromTheme(icon_name)

        # Tray icon
        self.tray = QSystemTrayIcon(self._icons.get("offline", QIcon()), app)
        self.tray.setToolTip(_("Dictation — offline"))
        self.tray.activated.connect(self._on_activated)

        # Menu contextuel
        self.menu = QMenu()
        self._build_menu(QFont)
        self.tray.setContextMenu(self.menu)

        # Premier check
        self._check_daemon()
        self._check_state()
        self._apply_state()

        self.tray.show()

        # Watcher fichier état
        self._watcher = QFileSystemWatcher()
        if os.path.isfile(STATE_FILE):
            self._watcher.addPath(STATE_FILE)
        self._watcher.fileChanged.connect(self._on_state_changed)

        # Timer lent pour le check daemon
        self._timer_slow = QTimer()
        self._timer_slow.timeout.connect(self._poll_slow)
        self._timer_slow.start(POLL_SLOW_MS)

    def _build_menu(self, QFont):
        self.action_dictee = self.menu.addAction(_("Start dictation"))
        self.action_translate = self.menu.addAction(_("Start translation"))
        self.action_cancel = self.menu.addAction(_("Cancel"))
        self.menu.addSeparator()
        self.action_daemon = self.menu.addAction("")
        self.action_daemon_hint = self.menu.addAction("")
        hint_font = self.action_daemon_hint.font() or QFont()
        hint_font.setPointSize(8)
        hint_font.setItalic(True)
        self.action_daemon_hint.setFont(hint_font)
        self.action_daemon_hint.setEnabled(False)
        # ASR backend submenu
        from PyQt6.QtGui import QActionGroup
        self.menu_asr = self.menu.addMenu(_("ASR backend"))
        self.menu_asr.aboutToShow.connect(self._refresh_asr_menu)
        self._asr_group = QActionGroup(self.menu_asr)
        self._asr_group.setExclusive(True)
        self._asr_actions = {}
        for key, label in ASR_BACKENDS:
            action = self.menu_asr.addAction(label)
            action.setCheckable(True)
            action.setData(key)
            self._asr_group.addAction(action)
            self._asr_actions[key] = action
        self._asr_group.triggered.connect(self._on_asr_selected)

        # Translate backend submenu
        self.menu_trans = self.menu.addMenu(_("Translation"))
        self.menu_trans.aboutToShow.connect(self._refresh_trans_menu)
        self._trans_group = QActionGroup(self.menu_trans)
        self._trans_group.setExclusive(True)
        self._trans_actions = {}
        for key, label in TRANSLATE_BACKENDS:
            action = self.menu_trans.addAction(label)
            action.setCheckable(True)
            action.setData(key)
            self._trans_group.addAction(action)
            self._trans_actions[key] = action
        self._trans_group.triggered.connect(self._on_trans_selected)

        self.menu.addSeparator()
        self.action_setup = self.menu.addAction(_("Configure Dictée"))
        self.action_postprocess = self.menu.addAction(_("Post-processing..."))
        self.menu.addSeparator()
        self.action_quit = self.menu.addAction(_("Quit icon"))
        self.menu.triggered.connect(self._on_menu_triggered)

    def _dot_icon(self, color):
        from PyQt6.QtGui import QPixmap, QPainter, QColor
        pix = QPixmap(16, 16)
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(color))
        p.setPen(self.Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 12, 12)
        p.end()
        return self.QIcon(pix)

    def _on_menu_triggered(self, action):
        if action == self.action_dictee:
            subprocess.Popen(["dictee"])
        elif action == self.action_translate:
            subprocess.Popen(["dictee", "--translate"])
        elif action == self.action_cancel:
            subprocess.Popen(["dictee", "--cancel"])
        elif action == self.action_daemon:
            if self.state == "offline":
                daemon_start()
                self._start_retries = 0
                self._poll_timer = self.QTimer()
                self._poll_timer.timeout.connect(self._poll_daemon_start_qt)
                self._poll_timer.start(1000)
            else:
                daemon_stop()
                self.QTimer.singleShot(1000, self._delayed_refresh)
        elif action == self.action_setup:
            subprocess.Popen(["dictee-setup"])
        elif action == self.action_postprocess:
            subprocess.Popen(["dictee-setup", "--postprocess"])
        elif action == self.action_quit:
            self.app.quit()

    def _on_activated(self, reason):
        if reason == self.QSystemTrayIcon.ActivationReason.Trigger:
            modifiers = self.QApplication.keyboardModifiers()
            if modifiers & self.Qt.KeyboardModifier.ControlModifier:
                subprocess.Popen(["dictee", "--translate"])
            else:
                subprocess.Popen(["dictee"])
        elif reason == self.QSystemTrayIcon.ActivationReason.MiddleClick:
            if self.state in ("recording", "transcribing"):
                subprocess.Popen(["dictee", "--cancel"])

    def _on_asr_selected(self, action):
        key = action.data()
        subprocess.Popen(["dictee-switch-backend", "asr", key])
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, self._delayed_daemon_refresh)

    def _on_trans_selected(self, action):
        key = action.data()
        subprocess.Popen(["dictee-switch-backend", "translate", key])

    def _delayed_daemon_refresh(self):
        self._check_daemon()
        self._check_state()
        self._apply_state()

    def _refresh_asr_menu(self):
        current = _current_asr_backend()
        for key, action in self._asr_actions.items():
            action.setChecked(key == current)
            action.setEnabled(_asr_service_exists(key))

    def _refresh_trans_menu(self):
        # Disable when using canary (built-in translation)
        self.menu_trans.setEnabled(_current_asr_backend() != "canary")
        current = _current_translate_backend()
        for key, action in self._trans_actions.items():
            action.setChecked(key == current)

    def _check_daemon(self):
        self._daemon_active = daemon_is_active()

    def _check_state(self):
        file_state = read_state()
        if file_state in ("recording", "transcribing"):
            self.state = file_state
        elif file_state == "switching":
            self.state = "idle"  # Stay idle during backend switch
        elif self._daemon_active:
            self.state = "idle"
        else:
            self.state = "offline"

    def _apply_state(self):
        if self.state == self._prev_state:
            return

        icon = self._icons.get(self.state, self._icons["offline"])
        self.tray.setIcon(icon)

        tooltips = {
            "idle": _("Dictation — ready") + "\n" + _("Click = dictation, Ctrl+click = translation"),
            "offline": _("Dictation — offline"),
            "recording": _("Dictation — recording") + "\n" + _("Click = stop, Middle = cancel"),
            "transcribing": _("Dictation — transcribing"),
        }
        self.tray.setToolTip(tooltips.get(self.state, _("Dictation")))

        pad = "\u2003" * 6
        if self.state == "offline":
            self.action_daemon.setText(f"  {_('Daemon stopped')}{pad}▶")
            self.action_daemon.setIcon(self._dot_icon("#e74c3c"))
            self.action_daemon_hint.setText(f" {_('click to start')}")
        else:
            labels = {"idle": _("Daemon active"), "recording": _("Recording…"),
                      "transcribing": _("Transcribing…")}
            self.action_daemon.setText(
                f"{labels.get(self.state, '  ' + _('Daemon active'))}{pad}■")
            self.action_daemon.setIcon(self._dot_icon("#2ecc71"))
            self.action_daemon_hint.setText(f" {_('click to stop')}")

        is_busy = self.state in ("recording", "transcribing")
        is_translating = is_busy and os.path.isfile(TRANSLATE_FLAG)
        self.action_dictee.setText(
            _("Stop translation") if is_translating
            else _("Stop dictation") if is_busy
            else _("Start dictation"))
        self.action_dictee.setEnabled(self.state != "offline")
        self.action_translate.setText(_("Start translation"))
        self.action_translate.setEnabled(self.state != "offline")
        self.action_translate.setVisible(not is_busy)
        self.action_cancel.setVisible(is_busy)

        self._prev_state = self.state

    def _on_state_changed(self, path):
        self._check_state()
        self._apply_state()
        if not self._watcher.files():
            self._watcher.addPath(path)

    def _poll_slow(self):
        self._check_daemon()
        if os.path.isfile(STATE_FILE) and STATE_FILE not in (self._watcher.files() or []):
            self._watcher.addPath(STATE_FILE)
        self._check_state()
        self._apply_state()

    def _poll_daemon_start_qt(self):
        self._start_retries += 1
        self._check_daemon()
        if self._daemon_active or self._start_retries >= 10:
            self._poll_timer.stop()
            self._check_state()
            self._apply_state()

    def _delayed_refresh(self):
        self._check_daemon()
        self._check_state()
        self._apply_state()


# ═══════════════════════════════════════════════════════════════

def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # First-run guard: prompt user to run setup wizard if not configured yet
    if not os.path.exists(CONF_PATH):
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            app = QApplication(sys.argv)
            result = QMessageBox.question(
                None, "Dictée",
                _("Dictée is not configured yet.\nDo you want to run the setup wizard?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if result == QMessageBox.StandardButton.Yes:
                subprocess.Popen(["dictee-setup", "--wizard"])
        except ImportError:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk
            dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=_("Dictée is not configured yet.\nDo you want to run the setup wizard?"),
            )
            dialog.set_title("Dictée")
            if dialog.run() == Gtk.ResponseType.YES:
                subprocess.Popen(["dictee-setup", "--wizard"])
            dialog.destroy()
        sys.exit(0)

    backend = _detect_backend()

    if backend == "appindicator":
        tray = DicteeTrayAppIndicator()
        tray.run()
    else:
        import time
        from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.setApplicationName(APP_ID)
        app.setDesktopFileName("dictee-tray")

        retries = 10
        while not QSystemTrayIcon.isSystemTrayAvailable() and retries > 0:
            time.sleep(1)
            retries -= 1

        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("Error: no system tray available", file=sys.stderr)
            sys.exit(1)

        tray = DicteeTrayQt(app)
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
