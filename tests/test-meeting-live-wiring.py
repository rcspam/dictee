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


if __name__ == "__main__":
    unittest.main(verbosity=2)
