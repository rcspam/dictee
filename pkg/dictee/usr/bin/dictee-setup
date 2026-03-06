#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dictee-setup — Configuration de la dictée vocale
UI GTK3 pour configurer le raccourci clavier et les options de traduction.
Sauvegarde dans ~/.config/dictee.conf (format shell, sourceable par dictee.sh).
"""

import os
import re
import shutil
import subprocess
import locale
import tempfile
import threading

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

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
    ("zh", "中文"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("ar", "العربية"),
]

DICTEE_COMMAND = "/usr/bin/dictee"
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
    raw = os.environ.get("XDG_CURRENT_DESKTOP", "inconnu")
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


def save_config(translate, backend, lang_source, lang_target):
    """Écrit dictee.conf."""
    os.makedirs(os.path.dirname(CONF_PATH), exist_ok=True)
    with open(CONF_PATH, "w") as f:
        f.write("# Généré par dictee-setup\n")
        f.write(f"DICTEE_TRANSLATE={str(translate).lower()}\n")
        f.write(f"DICTEE_TRANSLATE_BACKEND={backend}\n")
        f.write(f"DICTEE_LANG_SOURCE={lang_source}\n")
        f.write(f"DICTEE_LANG_TARGET={lang_target}\n")


# === Raccourci KDE ===


def gtk_accel_to_kde(accel_str):
    """Convertit '<Super>d' en 'Meta+D'."""
    s = accel_str
    s = s.replace("<Super>", "Meta+")
    s = s.replace("<Primary>", "Ctrl+")
    s = s.replace("<Control>", "Ctrl+")
    s = s.replace("<Alt>", "Alt+")
    s = s.replace("<Shift>", "Shift+")
    # Mettre la dernière touche en majuscule
    parts = s.rsplit("+", 1)
    if len(parts) == 2:
        s = parts[0] + "+" + parts[1].upper()
    return s


def check_kde_conflict(accel_kde):
    """Vérifie si le raccourci est déjà utilisé dans kglobalshortcutsrc."""
    rc = os.path.expanduser("~/.config/kglobalshortcutsrc")
    if not os.path.isfile(rc):
        return None
    try:
        with open(rc) as f:
            current_group = ""
            for line in f:
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    current_group = line[1:-1]
                    continue
                if current_group == "dictee.desktop":
                    continue
                if "=" in line:
                    _key, val = line.split("=", 1)
                    parts = val.split(",")
                    if parts and parts[0].strip() == accel_kde:
                        return current_group
    except OSError:
        pass
    return None


def apply_kde_shortcut(accel_gtk):
    """Applique le raccourci clavier sous KDE Plasma 6."""
    accel_kde = gtk_accel_to_kde(accel_gtk)

    # Créer le fichier .desktop
    apps_dir = os.path.expanduser("~/.local/share/applications")
    os.makedirs(apps_dir, exist_ok=True)
    desktop_path = os.path.join(apps_dir, "dictee.desktop")
    with open(desktop_path, "w") as f:
        f.write("[Desktop Entry]\n")
        f.write("Type=Application\n")
        f.write("Name=Dictée vocale\n")
        f.write("Comment=Saisie vocale push-to-talk\n")
        f.write(f"Exec={DICTEE_COMMAND}\n")
        f.write("Icon=audio-input-microphone\n")
        f.write("NoDisplay=true\n")
        f.write("Categories=Utility;\n")

    # Configurer le raccourci global
    subprocess.run(
        [
            "kwriteconfig6",
            "--file", "kglobalshortcutsrc",
            "--group", "dictee.desktop",
            "--key", "_launch",
            f"{accel_kde},none,Dictée vocale",
        ],
        check=True,
    )

    # Recharger KWin
    subprocess.run(
        ["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"],
        check=False,
    )

    return accel_kde


# === Raccourci GNOME ===


def apply_gnome_shortcut(accel_gtk):
    """Applique le raccourci clavier sous GNOME/Unity/Cinnamon."""
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    base_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
    slot = "dictee"
    path = f"{base_path}/{slot}/"

    # Lire la liste actuelle
    try:
        result = subprocess.run(
            ["gsettings", "get", schema, "custom-keybindings"],
            capture_output=True, text=True, check=True,
        )
        current = result.stdout.strip()
        # Ajouter notre path si absent
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

    # Configurer le raccourci
    sub_schema = f"{schema}.custom-keybinding"
    subprocess.run(
        ["gsettings", "set", sub_schema + ":" + path, "name", "Dictée vocale"],
        check=True,
    )
    subprocess.run(
        ["gsettings", "set", sub_schema + ":" + path, "command", DICTEE_COMMAND],
        check=True,
    )
    subprocess.run(
        ["gsettings", "set", sub_schema + ":" + path, "binding", accel_gtk],
        check=True,
    )


# === UI ===


class DicteeSetupWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Configuration de la dictée vocale")
        self.set_default_size(460, -1)
        self.set_border_width(18)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)

        self.de_name, self.de_type = detect_desktop()
        self.captured_accel = None

        conf = load_config()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(vbox)

        # -- Section raccourci --
        frame_shortcut = Gtk.Frame(label=" Raccourci clavier ")
        frame_shortcut.set_shadow_type(Gtk.ShadowType.NONE)
        frame_shortcut.get_label_widget().set_markup(
            "<b>Raccourci clavier</b>"
        )
        box_sc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box_sc.set_margin_start(12)
        box_sc.set_margin_end(12)
        box_sc.set_margin_top(6)
        box_sc.set_margin_bottom(6)
        frame_shortcut.add(box_sc)
        vbox.pack_start(frame_shortcut, False, False, 0)

        lbl_de = Gtk.Label()
        lbl_de.set_xalign(0)
        lbl_de.set_markup(f"Environnement détecté : <b>{self.de_name}</b>")
        box_sc.pack_start(lbl_de, False, False, 0)

        if self.de_type in ("kde", "gnome"):
            self.btn_capture = Gtk.Button(label="Appuyez pour capturer un raccourci…")
            self.btn_capture.connect("clicked", self._on_capture_clicked)
            box_sc.pack_start(self.btn_capture, False, False, 0)

            self.lbl_conflict = Gtk.Label()
            self.lbl_conflict.set_xalign(0)
            self.lbl_conflict.set_no_show_all(True)
            box_sc.pack_start(self.lbl_conflict, False, False, 0)
        else:
            lbl_unsup = Gtk.Label()
            lbl_unsup.set_xalign(0)
            lbl_unsup.set_line_wrap(True)
            lbl_unsup.set_markup(
                f"<i>ℹ Environnement non supporté pour la configuration automatique.\n"
                f"Configurez le raccourci manuellement dans votre gestionnaire de fenêtres :\n"
                f"Commande : <b>{DICTEE_COMMAND}</b></i>"
            )
            box_sc.pack_start(lbl_unsup, False, False, 0)

        # -- Section traduction --
        frame_translate = Gtk.Frame(label=" Traduction ")
        frame_translate.set_shadow_type(Gtk.ShadowType.NONE)
        frame_translate.get_label_widget().set_markup("<b>Traduction</b>")
        box_tr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box_tr.set_margin_start(12)
        box_tr.set_margin_end(12)
        box_tr.set_margin_top(6)
        box_tr.set_margin_bottom(6)
        frame_translate.add(box_tr)
        vbox.pack_start(frame_translate, False, False, 0)

        self.chk_translate = Gtk.CheckButton(label="Activer la traduction")
        self.chk_translate.set_active(conf.get("DICTEE_TRANSLATE", "false") == "true")
        self.chk_translate.connect("toggled", self._on_translate_toggled)
        box_tr.pack_start(self.chk_translate, False, False, 0)

        # Conteneur des options de traduction
        self.box_tr_opts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.box_tr_opts.set_margin_start(20)
        box_tr.pack_start(self.box_tr_opts, False, False, 0)

        # Backend radio buttons
        lbl_backend = Gtk.Label()
        lbl_backend.set_xalign(0)
        lbl_backend.set_text("Backend :")
        self.box_tr_opts.pack_start(lbl_backend, False, False, 0)

        self.radio_trans = Gtk.RadioButton.new_with_label(
            None, "translate-shell (rapide, Google Translate)"
        )
        self.box_tr_opts.pack_start(self.radio_trans, False, False, 0)

        self.radio_ollama = Gtk.RadioButton.new_with_label_from_widget(
            self.radio_trans, "ollama (100% local, translategemma)"
        )
        self.box_tr_opts.pack_start(self.radio_ollama, False, False, 0)

        if conf.get("DICTEE_TRANSLATE_BACKEND") == "ollama":
            self.radio_ollama.set_active(True)

        # Langues
        grid_lang = Gtk.Grid(column_spacing=8, row_spacing=6)
        grid_lang.set_margin_top(6)
        self.box_tr_opts.pack_start(grid_lang, False, False, 0)

        lbl_src = Gtk.Label(label="Langue source :")
        lbl_src.set_xalign(0)
        grid_lang.attach(lbl_src, 0, 0, 1, 1)

        self.combo_src = Gtk.ComboBoxText()
        for code, name in LANGUAGES:
            self.combo_src.append(code, f"{code} — {name}")
        default_src = conf.get("DICTEE_LANG_SOURCE", self._system_lang())
        self.combo_src.set_active_id(default_src)
        if self.combo_src.get_active_id() is None:
            self.combo_src.set_active(0)
        grid_lang.attach(self.combo_src, 1, 0, 1, 1)

        lbl_tgt = Gtk.Label(label="Langue cible :")
        lbl_tgt.set_xalign(0)
        grid_lang.attach(lbl_tgt, 0, 1, 1, 1)

        self.combo_tgt = Gtk.ComboBoxText()
        for code, name in LANGUAGES:
            self.combo_tgt.append(code, f"{code} — {name}")
        default_tgt = conf.get("DICTEE_LANG_TARGET", "en")
        self.combo_tgt.set_active_id(default_tgt)
        if self.combo_tgt.get_active_id() is None:
            self.combo_tgt.set_active(1)
        grid_lang.attach(self.combo_tgt, 1, 1, 1, 1)

        # Appliquer l'état initial
        self._on_translate_toggled(self.chk_translate)

        # -- Section animation-speech --
        frame_anim = Gtk.Frame(label=" Animation vocale ")
        frame_anim.set_shadow_type(Gtk.ShadowType.NONE)
        frame_anim.get_label_widget().set_markup("<b>Animation vocale</b>")
        box_anim = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box_anim.set_margin_start(12)
        box_anim.set_margin_end(12)
        box_anim.set_margin_top(6)
        box_anim.set_margin_bottom(6)
        frame_anim.add(box_anim)
        vbox.pack_start(frame_anim, False, False, 0)

        self.lbl_anim_status = Gtk.Label()
        self.lbl_anim_status.set_xalign(0)
        self.lbl_anim_status.set_line_wrap(True)
        box_anim.pack_start(self.lbl_anim_status, False, False, 0)

        self.btn_install_anim = Gtk.Button(label="Installer animation-speech")
        self.btn_install_anim.connect("clicked", self._on_install_animation)
        self.btn_install_anim.set_no_show_all(True)
        box_anim.pack_start(self.btn_install_anim, False, False, 0)

        self.progress_anim = Gtk.ProgressBar()
        self.progress_anim.set_no_show_all(True)
        box_anim.pack_start(self.progress_anim, False, False, 0)

        self._check_animation_speech()

        # -- Boutons --
        box_buttons = Gtk.Box(spacing=8)
        box_buttons.set_halign(Gtk.Align.END)
        box_buttons.set_margin_top(12)
        vbox.pack_start(box_buttons, False, False, 0)

        btn_cancel = Gtk.Button(label="Annuler")
        btn_cancel.connect("clicked", lambda _: self.close())
        box_buttons.pack_start(btn_cancel, False, False, 0)

        btn_apply = Gtk.Button(label="Appliquer")
        btn_apply.get_style_context().add_class("suggested-action")
        btn_apply.connect("clicked", self._on_apply)
        box_buttons.pack_start(btn_apply, False, False, 0)

    @staticmethod
    def _system_lang():
        lang = os.environ.get("LANG", "")
        if lang:
            return lang.split("_")[0].split(".")[0]
        try:
            return locale.getdefaultlocale()[0].split("_")[0]
        except (AttributeError, IndexError):
            return "fr"

    def _on_translate_toggled(self, widget):
        self.box_tr_opts.set_sensitive(widget.get_active())

    # -- Capture raccourci --

    def _on_capture_clicked(self, _widget):
        self.btn_capture.set_label("Appuyez sur une combinaison de touches…")
        self.lbl_conflict.hide()
        self._capture_handler = self.connect("key-press-event", self._on_key_captured)

    def _on_key_captured(self, _widget, event):
        keyval = event.keyval
        state = event.state & (
            Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.SHIFT_MASK
            | Gdk.ModifierType.MOD1_MASK  # Alt
            | Gdk.ModifierType.SUPER_MASK
        )

        # Ignorer les modificateurs seuls
        if keyval in (
            Gdk.KEY_Shift_L, Gdk.KEY_Shift_R,
            Gdk.KEY_Control_L, Gdk.KEY_Control_R,
            Gdk.KEY_Alt_L, Gdk.KEY_Alt_R,
            Gdk.KEY_Super_L, Gdk.KEY_Super_R,
            Gdk.KEY_Meta_L, Gdk.KEY_Meta_R,
            Gdk.KEY_ISO_Level3_Shift,
        ):
            return False

        self.disconnect(self._capture_handler)

        accel = Gtk.accelerator_name(keyval, state)
        label = Gtk.accelerator_get_label(keyval, state)
        self.captured_accel = accel
        self.btn_capture.set_label(f"Raccourci : {label}")

        # Vérifier conflit (KDE)
        if self.de_type == "kde":
            conflict = check_kde_conflict(gtk_accel_to_kde(accel))
            if conflict:
                self.lbl_conflict.set_markup(
                    f'<span foreground="orange">⚠ Raccourci utilisé par « {conflict} »</span>'
                )
                self.lbl_conflict.show()
            else:
                self.lbl_conflict.hide()

        return True

    # -- Animation-speech --

    def _check_animation_speech(self):
        """Vérifie si animation-speech-ctl est installé."""
        if shutil.which(ANIMATION_SPEECH_BIN):
            # Récupérer la version installée
            try:
                result = subprocess.run(
                    ["dpkg-query", "-W", "-f", "${Version}", "animation-speech"],
                    capture_output=True, text=True,
                )
                version = result.stdout.strip() if result.returncode == 0 else ""
                if version:
                    self.lbl_anim_status.set_markup(
                        f'<span foreground="green">✓ animation-speech {version} installé</span>'
                    )
                else:
                    self.lbl_anim_status.set_markup(
                        '<span foreground="green">✓ animation-speech installé</span>'
                    )
            except FileNotFoundError:
                self.lbl_anim_status.set_markup(
                    '<span foreground="green">✓ animation-speech installé</span>'
                )
            self.btn_install_anim.hide()
        else:
            self.lbl_anim_status.set_markup(
                "<i>animation-speech</i> affiche une animation visuelle pendant\n"
                "l'enregistrement et permet d'annuler avec Echap."
            )
            self.btn_install_anim.show()

    def _on_install_animation(self, _widget):
        """Télécharge et installe le .deb depuis GitHub releases."""
        self.btn_install_anim.set_sensitive(False)
        self.btn_install_anim.set_label("Téléchargement…")
        self.progress_anim.show()
        self.progress_anim.pulse()
        self._pulse_id = GLib.timeout_add(100, self._pulse_progress)

        thread = threading.Thread(target=self._download_and_install, daemon=True)
        thread.start()

    def _pulse_progress(self):
        self.progress_anim.pulse()
        return True

    @staticmethod
    def _is_debian_based():
        """Détecte si le système utilise dpkg (Debian/Ubuntu/Mint…)."""
        return shutil.which("dpkg") is not None

    def _download_and_install(self):
        """Thread : télécharge le .deb ou .tar.gz via gh et installe."""
        try:
            # Vérifier que gh est disponible
            if not shutil.which("gh"):
                GLib.idle_add(
                    self._install_error,
                    "L'outil 'gh' (GitHub CLI) est nécessaire.\n"
                    "Installez-le : sudo apt install gh && gh auth login",
                )
                return

            tmp_dir = tempfile.mkdtemp(prefix="dictee-setup-")

            if self._is_debian_based():
                # Télécharger le .deb
                result = subprocess.run(
                    ["gh", "release", "download", "--repo", ANIMATION_SPEECH_REPO,
                     "--pattern", "*.deb", "--dir", tmp_dir],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    GLib.idle_add(self._install_error, result.stderr.strip() or "Erreur téléchargement .deb")
                    return

                # Trouver le fichier téléchargé
                debs = [f for f in os.listdir(tmp_dir) if f.endswith(".deb")]
                if not debs:
                    GLib.idle_add(self._install_error, "Aucun .deb trouvé dans la release.")
                    return

                deb_path = os.path.join(tmp_dir, debs[0])
                GLib.idle_add(self._update_install_label, "Installation…")
                result = subprocess.run(
                    ["pkexec", "dpkg", "-i", deb_path],
                    capture_output=True, text=True,
                )
            else:
                # Télécharger le .tar.gz
                result = subprocess.run(
                    ["gh", "release", "download", "--repo", ANIMATION_SPEECH_REPO,
                     "--pattern", "*.tar.gz", "--dir", tmp_dir],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    GLib.idle_add(self._install_error, result.stderr.strip() or "Erreur téléchargement .tar.gz")
                    return

                tarballs = [f for f in os.listdir(tmp_dir) if f.endswith(".tar.gz")]
                if not tarballs:
                    GLib.idle_add(self._install_error, "Aucun .tar.gz trouvé dans la release.")
                    return

                tarball_path = os.path.join(tmp_dir, tarballs[0])
                GLib.idle_add(self._update_install_label, "Installation…")
                # Extraire dans /usr/local via pkexec
                result = subprocess.run(
                    ["pkexec", "tar", "xzf", tarball_path, "-C", "/usr/local"],
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
                GLib.idle_add(self._install_success)
            else:
                err = result.stderr.strip() or "Erreur lors de l'installation."
                GLib.idle_add(self._install_error, err)

        except Exception as e:
            GLib.idle_add(self._install_error, str(e))

    def _update_install_label(self, text):
        self.btn_install_anim.set_label(text)
        return False

    def _install_success(self):
        GLib.source_remove(self._pulse_id)
        self.progress_anim.hide()
        self._check_animation_speech()
        return False

    def _install_error(self, msg):
        GLib.source_remove(self._pulse_id)
        self.progress_anim.hide()
        self.btn_install_anim.set_label("Installer animation-speech")
        self.btn_install_anim.set_sensitive(True)
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Erreur d'installation",
        )
        dialog.format_secondary_text(msg)
        dialog.run()
        dialog.destroy()
        return False

    # -- Appliquer --

    def _on_apply(self, _widget):
        # Sauvegarder la config
        translate = self.chk_translate.get_active()
        backend = "ollama" if self.radio_ollama.get_active() else "trans"
        lang_src = self.combo_src.get_active_id()
        lang_tgt = self.combo_tgt.get_active_id()

        save_config(translate, backend, lang_src, lang_tgt)

        # Appliquer le raccourci si capturé
        shortcut_msg = ""
        if self.captured_accel and self.de_type in ("kde", "gnome"):
            try:
                if self.de_type == "kde":
                    apply_kde_shortcut(self.captured_accel)
                    kde_accel = gtk_accel_to_kde(self.captured_accel)
                    shortcut_msg = f"\nRaccourci appliqué : {kde_accel}"
                    shortcut_msg += "\nUn re-login peut être nécessaire pour activer le raccourci."
                else:
                    apply_gnome_shortcut(self.captured_accel)
                    shortcut_msg = f"\nRaccourci appliqué : {self.captured_accel}"
            except Exception as e:
                shortcut_msg = f"\nErreur raccourci : {e}"

        # Dialog de confirmation
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Configuration sauvegardée",
        )
        dialog.format_secondary_text(
            f"Fichier : {CONF_PATH}{shortcut_msg}"
        )
        dialog.run()
        dialog.destroy()
        self.close()


def main():
    win = DicteeSetupWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
