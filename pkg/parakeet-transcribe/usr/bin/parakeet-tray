#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parakeet-tray — Icône de zone de notification pour transcribe-daemon
Affiche l'état du daemon dans la boîte à miniatures du panel.
"""

import os
import signal
import subprocess

import gi

gi.require_version("Gtk", "3.0")

# Essayer AyatanaAppIndicator3 (Ubuntu/Debian), puis AppIndicator3, sinon fallback StatusIcon
AppIndicator3 = None
for _ai_ns in ("AyatanaAppIndicator3", "AppIndicator3"):
    try:
        gi.require_version(_ai_ns, "0.1")
        AppIndicator3 = getattr(__import__("gi.repository", fromlist=[_ai_ns]), _ai_ns)
        break
    except (ValueError, ImportError, AttributeError):
        continue
HAS_APPINDICATOR = AppIndicator3 is not None

from gi.repository import Gtk, GLib, GdkPixbuf  # noqa: E402

SOCKET_PATH = "/tmp/transcribe.sock"
DAEMON_BIN = "transcribe-daemon"
APP_ID = "parakeet-transcribe"
POLL_INTERVAL_MS = 3000

# Icônes personnalisées — AppIndicator3 veut un répertoire + nom sans extension
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
    # KDE : lire la couleur de fond du panel
    try:
        result = subprocess.run(
            ["kreadconfig6", "--group", "Colors:Window", "--key", "BackgroundNormal"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Format: "r,g,b"
            r, g, b = (int(x) for x in result.stdout.strip().split(","))
            return (r + g + b) / 3 < 128
    except (FileNotFoundError, ValueError):
        pass
    # GNOME : vérifier prefer-dark
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
ICON_ACTIVE = "parakeet-active-dark" if _DARK else "parakeet-active"
ICON_INACTIVE = "parakeet-inactive-dark" if _DARK else "parakeet-inactive"


def daemon_is_running():
    """Vérifie si transcribe-daemon est en cours d'exécution."""
    # Vérifier la socket
    if os.path.exists(SOCKET_PATH):
        # Vérifier que le processus tourne aussi
        try:
            result = subprocess.run(
                ["pgrep", "-x", DAEMON_BIN],
                capture_output=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return True  # pgrep absent, on fait confiance à la socket
    return False


def daemon_start():
    """Démarre le daemon via systemd --user (ou en direct)."""
    try:
        subprocess.Popen(
            ["systemctl", "--user", "start", "parakeet-transcribe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        # Pas de systemctl, lancer en direct
        subprocess.Popen(
            [DAEMON_BIN],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def daemon_stop():
    """Arrête le daemon via systemd --user (ou kill)."""
    try:
        subprocess.Popen(
            ["systemctl", "--user", "stop", "parakeet-transcribe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        subprocess.run(["pkill", "-x", DAEMON_BIN], check=False)


class ParakeetTray:
    def __init__(self):
        self.running = daemon_is_running()

        if HAS_APPINDICATOR:
            self._init_appindicator()
        else:
            self._init_statusicon()

        self._update_status()
        GLib.timeout_add(POLL_INTERVAL_MS, self._poll_status)

    # === AppIndicator3 (KDE Plasma, GNOME avec extension) ===

    def _init_appindicator(self):
        icon = ICON_ACTIVE if self.running else ICON_INACTIVE
        self.indicator = AppIndicator3.Indicator.new(
            APP_ID,
            icon,
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        if ICON_DIR:
            self.indicator.set_icon_theme_path(ICON_DIR)
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Parakeet Transcribe")
        self._build_menu()
        self.indicator.set_menu(self.menu)
        self.use_appindicator = True

    # === Gtk.StatusIcon (fallback) ===

    @staticmethod
    def _load_icon_pixbuf(name, size=22):
        """Charge l'icône SVG en pixbuf pour StatusIcon."""
        if ICON_DIR:
            path = os.path.join(ICON_DIR, f"{name}.svg")
            if os.path.isfile(path):
                return GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
        return None

    def _init_statusicon(self):
        icon = ICON_ACTIVE if self.running else ICON_INACTIVE
        pixbuf = self._load_icon_pixbuf(icon)
        if pixbuf:
            self.status_icon = Gtk.StatusIcon.new_from_pixbuf(pixbuf)
        else:
            self.status_icon = Gtk.StatusIcon.new_from_icon_name(icon)
        self.status_icon.set_title("Parakeet Transcribe")
        self.status_icon.set_tooltip_text("Parakeet Transcribe")
        self.status_icon.connect("popup-menu", self._on_statusicon_popup)
        self.status_icon.connect("activate", self._on_statusicon_activate)
        self._build_menu()
        self.use_appindicator = False

    def _on_statusicon_popup(self, icon, button, activate_time):
        self.menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, activate_time)

    def _on_statusicon_activate(self, _icon):
        self.menu.popup_at_pointer(None)

    # === Menu contextuel ===

    def _build_menu(self):
        self.menu = Gtk.Menu()

        # Statut
        self.item_status = Gtk.MenuItem()
        self.item_status.set_sensitive(False)
        self.menu.append(self.item_status)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Démarrer / Arrêter
        self.item_start = Gtk.MenuItem(label="Démarrer le daemon")
        self.item_start.connect("activate", self._on_start)
        self.menu.append(self.item_start)

        self.item_stop = Gtk.MenuItem(label="Arrêter le daemon")
        self.item_stop.connect("activate", self._on_stop)
        self.menu.append(self.item_stop)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Dictée
        item_dictee = Gtk.MenuItem(label="Dictée vocale")
        item_dictee.connect("activate", lambda _: subprocess.Popen(["dictee"]))
        self.menu.append(item_dictee)

        item_translate = Gtk.MenuItem(label="Dictée + Traduction")
        item_translate.connect(
            "activate", lambda _: subprocess.Popen(["dictee", "--translate"])
        )
        self.menu.append(item_translate)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Configuration
        item_setup = Gtk.MenuItem(label="Configuration…")
        item_setup.connect("activate", lambda _: subprocess.Popen(["dictee-setup"]))
        self.menu.append(item_setup)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Quitter
        item_quit = Gtk.MenuItem(label="Quitter l'icône")
        item_quit.connect("activate", self._on_quit)
        self.menu.append(item_quit)

        self.menu.show_all()

    def _update_status(self):
        if self.running:
            self.item_status.set_label("● Daemon actif")
            self.item_start.set_sensitive(False)
            self.item_stop.set_sensitive(True)
            icon = ICON_ACTIVE
        else:
            self.item_status.set_label("○ Daemon arrêté")
            self.item_start.set_sensitive(True)
            self.item_stop.set_sensitive(False)
            icon = ICON_INACTIVE

        if self.use_appindicator:
            self.indicator.set_icon_full(icon, "Parakeet Transcribe")
        else:
            pixbuf = self._load_icon_pixbuf(icon)
            if pixbuf:
                self.status_icon.set_from_pixbuf(pixbuf)
            else:
                self.status_icon.set_from_icon_name(icon)
            tooltip = "Parakeet – actif" if self.running else "Parakeet – arrêté"
            self.status_icon.set_tooltip_text(tooltip)

    def _poll_status(self):
        was_running = self.running
        self.running = daemon_is_running()
        if self.running != was_running:
            self._update_status()
        return True  # continuer le polling

    # === Actions ===

    def _on_start(self, _widget):
        daemon_start()
        # Vérifier après un délai (le daemon met un peu à démarrer)
        GLib.timeout_add(2000, self._delayed_refresh)

    def _on_stop(self, _widget):
        daemon_stop()
        GLib.timeout_add(1000, self._delayed_refresh)

    def _delayed_refresh(self):
        self.running = daemon_is_running()
        self._update_status()
        return False  # exécuter une seule fois

    def _on_quit(self, _widget):
        Gtk.main_quit()


def main():
    # Permettre Ctrl+C
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    ParakeetTray()
    Gtk.main()


if __name__ == "__main__":
    main()
