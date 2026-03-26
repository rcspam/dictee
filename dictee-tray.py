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
SERVICES = ("dictee", "dictee-vosk", "dictee-whisper")
CONF_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "dictee.conf",
)
POLL_SLOW_MS = 3000

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


def daemon_start():
    """Démarre le service daemon activé."""
    for svc in SERVICES:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", svc],
                capture_output=True, text=True,
            )
            if result.stdout.strip() == "enabled":
                subprocess.Popen(
                    ["systemctl", "--user", "start", svc],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                return
        except FileNotFoundError:
            pass
    subprocess.Popen(
        ["systemctl", "--user", "start", "dictee"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def daemon_stop():
    """Arrête tous les services daemon."""
    for svc in SERVICES:
        try:
            subprocess.run(
                ["systemctl", "--user", "stop", svc],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass


def read_state():
    """Lit l'état depuis /dev/shm/.dictee_state."""
    try:
        with open(STATE_FILE, "r") as f:
            state = f.read().strip()
            if state in ("recording", "transcribing"):
                return state
            if state == "cancelled":
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
            self.GLib.timeout_add(2000, self._delayed_refresh)
        else:
            daemon_stop()
            self.GLib.timeout_add(1000, self._delayed_refresh)

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
                self.QTimer.singleShot(2000, self._delayed_refresh)
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

    def _check_daemon(self):
        self._daemon_active = daemon_is_active()

    def _check_state(self):
        file_state = read_state()
        if file_state in ("recording", "transcribing"):
            self.state = file_state
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
