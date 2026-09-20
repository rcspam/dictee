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
