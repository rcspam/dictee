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

from PyQt6.QtCore import Qt, QTimer, QFileSystemWatcher
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu


# === Configuration ===

STATE_FILE = "/dev/shm/.dictee_state"
TRANSLATE_FLAG = "/tmp/dictee_translate"
APP_ID = "dictee"
SERVICES = ("dictee", "dictee-vosk", "dictee-whisper")
POLL_SLOW_MS = 3000  # polling daemon (systemctl) + fallback re-watch

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


def _dot_icon(color):
    """Crée une icône 16×16 avec un cercle coloré."""
    pix = QPixmap(16, 16)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 12, 12)
    p.end()
    return QIcon(pix)


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

        # Watcher fichier état (remplace le polling rapide)
        self._watcher = QFileSystemWatcher()
        if os.path.isfile(STATE_FILE):
            self._watcher.addPath(STATE_FILE)
        self._watcher.fileChanged.connect(self._on_state_changed)

        # Timer lent pour le check daemon (systemctl) et re-watch fallback
        self._timer_slow = QTimer()
        self._timer_slow.timeout.connect(self._poll_slow)
        self._timer_slow.start(POLL_SLOW_MS)

    # === Menu ===

    def _build_menu(self):
        self.action_dictee = self.menu.addAction("Démarrer dictée")
        self.action_translate = self.menu.addAction("Démarrer traduction")
        self.action_cancel = self.menu.addAction("Annuler")
        self.menu.addSeparator()
        self.action_daemon = self.menu.addAction("")
        self.action_daemon_hint = self.menu.addAction("")
        hint_font = self.action_daemon_hint.font() or QFont()
        hint_font.setPointSize(8)
        hint_font.setItalic(True)
        self.action_daemon_hint.setFont(hint_font)
        self.action_daemon_hint.setEnabled(False)
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
        elif action == self.action_daemon:
            if self.state == "offline":
                daemon_start()
                QTimer.singleShot(2000, self._delayed_refresh)
            else:
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

        # Menu : daemon (ligne unique toggle avec picto play/stop en bout de ligne)
        pad = "\u2003" * 6  # em spaces pour pousser le picto à droite
        if self.state == "offline":
            self.action_daemon.setText(f"  Daemon arrêté{pad}▶")
            self.action_daemon.setIcon(_dot_icon("#e74c3c"))
            self.action_daemon_hint.setText(" cliquer pour démarrer")
        else:
            labels = {"idle": "Daemon actif", "recording": "Enregistrement…", "transcribing": "Transcription…"}
            self.action_daemon.setText(f"{labels.get(self.state, '  Daemon actif')}{pad}■")
            self.action_daemon.setIcon(_dot_icon("#2ecc71"))
            self.action_daemon_hint.setText(" cliquer pour arrêter")

        # Menu : dictée / traduction
        is_busy = self.state in ("recording", "transcribing")
        is_translating = is_busy and os.path.isfile(TRANSLATE_FLAG)
        self.action_dictee.setText(
            "Arrêter traduction" if is_translating
            else "Arrêter dictée" if is_busy
            else "Démarrer dictée")
        self.action_dictee.setEnabled(self.state != "offline")
        self.action_translate.setText("Démarrer traduction")
        self.action_translate.setEnabled(self.state != "offline")
        self.action_translate.setVisible(not is_busy)

        # Menu : annuler (visible uniquement si actif)
        self.action_cancel.setVisible(is_busy)

        self._prev_state = self.state

    # === Réaction aux changements d'état ===

    def _on_state_changed(self, path):
        """Appelé par QFileSystemWatcher quand le fichier état change."""
        self._check_state()
        self._apply_state()
        # Re-watch : QFileSystemWatcher perd le watch après réécriture (nouveau inode)
        if not self._watcher.files():
            self._watcher.addPath(path)

    def _poll_slow(self):
        self._check_daemon()
        # Fallback : re-ajouter le fichier si le watcher l'a perdu
        if os.path.isfile(STATE_FILE) and STATE_FILE not in (self._watcher.files() or []):
            self._watcher.addPath(STATE_FILE)
        self._check_state()
        self._apply_state()

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
