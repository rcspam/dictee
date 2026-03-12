#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dictee-tray — Icône de zone de notification pour dictee
Substitut au plasmoid KDE pour les bureaux non-KDE.
Clic gauche = dictée, Ctrl+clic gauche = traduction, clic droit = menu.
"""

import os
import signal
import subprocess
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu


# === Configuration ===

STATE_FILE = "/dev/shm/.dictee_state"
APP_ID = "dictee"
SERVICES = ("dictee", "dictee-vosk", "dictee-whisper")
POLL_FAST_MS = 500   # polling état (recording/transcribing)
POLL_SLOW_MS = 3000  # polling daemon (systemctl)

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
    """Démarre le service daemon activé (comme le plasmoid)."""
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
    """Arrête tous les services daemon (comme le plasmoid)."""
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


class DicteeTray:
    def __init__(self, app):
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
        self.tray.setToolTip("Dictée — hors ligne")
        self.tray.activated.connect(self._on_activated)

        # Menu contextuel
        self.menu = QMenu()
        self._build_menu()
        self.tray.setContextMenu(self.menu)

        # Premier check
        self._check_daemon()
        self._check_state()
        self._apply_state()

        self.tray.show()

        # Timers (après show)
        self._timer_fast = QTimer()
        self._timer_fast.timeout.connect(self._poll_fast)
        self._timer_fast.start(POLL_FAST_MS)

        self._timer_slow = QTimer()
        self._timer_slow.timeout.connect(self._poll_slow)
        self._timer_slow.start(POLL_SLOW_MS)

    # === Menu ===

    def _build_menu(self):
        self.action_dictee = self.menu.addAction("Démarrer dictée")
        self.action_translate = self.menu.addAction("Démarrer traduction")
        self.action_cancel = self.menu.addAction("Annuler")
        self.menu.addSeparator()
        self.action_status = self.menu.addAction("")
        self.action_status.setEnabled(False)
        self.action_start = self.menu.addAction("Démarrer le daemon")
        self.action_stop = self.menu.addAction("Arrêter le daemon")
        self.menu.addSeparator()
        self.action_setup = self.menu.addAction("Configurer Dictée")
        self.menu.addSeparator()
        self.action_quit = self.menu.addAction("Quitter l'icône")

        self.menu.triggered.connect(self._on_menu_triggered)

    def _on_menu_triggered(self, action):
        if action == self.action_dictee:
            subprocess.Popen(["dictee"])
        elif action == self.action_translate:
            subprocess.Popen(["dictee", "--translate"])
        elif action == self.action_cancel:
            subprocess.Popen(["dictee", "--cancel"])
        elif action == self.action_start:
            daemon_start()
            QTimer.singleShot(2000, self._delayed_refresh)
        elif action == self.action_stop:
            daemon_stop()
            QTimer.singleShot(1000, self._delayed_refresh)
        elif action == self.action_setup:
            subprocess.Popen(["dictee-setup"])
        elif action == self.action_quit:
            self.app.quit()

    # === Clic tray ===

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Clic gauche
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                subprocess.Popen(["dictee", "--translate"])
            else:
                subprocess.Popen(["dictee"])
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            # Clic molette = annuler
            if self.state in ("recording", "transcribing"):
                subprocess.Popen(["dictee", "--cancel"])

    # === État ===

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

        # Icône tray
        icon = self._icons.get(self.state, self._icons["offline"])
        self.tray.setIcon(icon)

        # Tooltip
        tooltips = {
            "idle": "Dictée — prêt\nClic = dictée, Ctrl+clic = traduction",
            "offline": "Dictée — hors ligne",
            "recording": "Dictée — enregistrement\nClic = arrêter, Molette = annuler",
            "transcribing": "Dictée — transcription",
        }
        self.tray.setToolTip(tooltips.get(self.state, "Dictée"))

        # Menu : statut
        labels = {
            "idle": "Daemon actif",
            "offline": "Daemon arrêté",
            "recording": "Enregistrement…",
            "transcribing": "Transcription…",
        }
        self.action_status.setText(labels.get(self.state, "Daemon arrêté"))

        # Menu : daemon
        self.action_start.setEnabled(self.state == "offline")
        self.action_stop.setEnabled(self.state != "offline")

        # Menu : dictée / traduction
        is_busy = self.state in ("recording", "transcribing")
        self.action_dictee.setText("Arrêter dictée" if is_busy else "Démarrer dictée")
        self.action_translate.setText("Arrêter traduction" if is_busy else "Démarrer traduction")
        self.action_dictee.setEnabled(self.state != "offline")
        self.action_translate.setEnabled(self.state != "offline")

        # Menu : annuler (visible uniquement si actif)
        self.action_cancel.setVisible(is_busy)

        self._prev_state = self.state

    # === Polling ===

    def _poll_fast(self):
        self._check_state()
        self._apply_state()

    def _poll_slow(self):
        self._check_daemon()

    def _delayed_refresh(self):
        self._check_daemon()
        self._check_state()
        self._apply_state()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_ID)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("Erreur : pas de tray système disponible", file=sys.stderr)
        sys.exit(1)

    tray = DicteeTray(app)  # garder la référence (évite GC du menu)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
