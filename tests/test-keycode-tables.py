#!/usr/bin/env python3
"""Confront the hand-written keycode tables with the kernel's own constants.

dictee-setup.py maps a captured key to an evdev keycode through
QT_TO_LINUX_KEYCODE, then back to a label through LINUX_KEYCODE_NAMES. Both are
written by hand, and nothing ever compares them to reality — which is how four
entries came to hold X11 keycodes (evdev + 8) instead of evdev ones.

The tray (dictee-tray.py) and the plasmoid (main.qml) carry their own label
tables, kept in sync manually. They are checked here too, so a divergence shows
up as a test failure instead of a user seeing "Home" in setup and "key110" in
the tray for the same key.

Run: python3 -m pytest tests/test-keycode-tables.py -v
"""
import ast
import re
import unittest
from pathlib import Path

from evdev import ecodes

ROOT = Path(__file__).resolve().parent.parent
SETUP = ROOT / "dictee-setup.py"
TRAY = ROOT / "dictee-tray.py"
QML = ROOT / "plasmoid/package/contents/ui/main.qml"

# What each trailing comment in QT_TO_LINUX_KEYCODE means, in kernel terms.
# Only the entries whose comment is not literally the evdev name need an entry.
COMMENT_TO_KERNEL = {
    "Escape": "KEY_ESC",
    "Pause/Break": "KEY_PAUSE",
    "Backspace — non, pas utile": "KEY_BACKSPACE",
    "` (backtick / grave)": "KEY_GRAVE",
    "² (twosuperior, AZERTY)": "KEY_GRAVE",
}

# Print Screen is genuinely ambiguous: the kernel has both KEY_PRINT (210) and
# KEY_SYSRQ (99), and which one a given keyboard emits has not been measured.
# Accept either until someone presses the key and reports what comes out.
AMBIGUOUS = {"Print Screen (SysRq)": ("KEY_PRINT", "KEY_SYSRQ")}


def _kernel_code(label):
    """evdev keycode expected for a table comment, or None if unknown."""
    names = AMBIGUOUS.get(label)
    if names:
        return tuple(getattr(ecodes, n) for n in names)
    name = COMMENT_TO_KERNEL.get(label, f"KEY_{label.upper()}")
    code = getattr(ecodes, name, None)
    return (code,) if code is not None else None


def _parse_commented_dict(text, varname):
    """Yield (value, trailing_comment) for each line of a dict literal.

    ast drops comments, and the comment is what tells us which key each entry is
    supposed to be — so the block is read line by line instead.
    """
    start = text.index(f"{varname} = {{")
    end = text.index("\n}", start)
    for line in text[start:end].splitlines()[1:]:
        m = re.match(r"\s*(0x[0-9a-fA-F]+|\d+)\s*:\s*(\d+)\s*,\s*#\s*(.+?)\s*$", line)
        if m:
            yield int(m.group(2)), m.group(3)


def _parse_dict_literal(path, varname):
    """Return a module-level dict without importing the module.

    Evaluated rather than literal_eval'd: _PTT_KEY_LABELS builds its F-key runs
    with comprehensions and f-strings, which are not literals.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == varname:
                    expr = ast.Expression(body=node.value)
                    ast.fix_missing_locations(expr)
                    return eval(compile(expr, path.name, "eval"), {}, {})
    raise AssertionError(f"{varname} not found in {path.name}")


class TestQtToLinuxKeycode(unittest.TestCase):
    """Every value must be the evdev keycode its own comment names."""

    def test_values_match_kernel_constants(self):
        text = SETUP.read_text(encoding="utf-8")
        wrong = []
        for value, label in _parse_commented_dict(text, "QT_TO_LINUX_KEYCODE"):
            expected = _kernel_code(label)
            if expected is None:
                continue  # comment not mappable to a kernel name; skip, don't guess
            if value not in expected:
                got = ecodes.KEY.get(value, "?")
                if isinstance(got, list):
                    got = "/".join(got)
                wrong.append(
                    f"{label}: table says {value} ({got}), "
                    f"kernel says {expected[0]}")
        self.assertEqual(wrong, [], "\n  " + "\n  ".join(wrong))


class TestLinuxKeycodeNames(unittest.TestCase):
    """The reverse table must agree with the kernel, and with Qt."""

    def setUp(self):
        self.names = _parse_dict_literal(SETUP, "LINUX_KEYCODE_NAMES")

    def test_codes_carry_the_right_label(self):
        wrong = []
        for code, label in self.names.items():
            if label.startswith("`"):
                continue  # the grave key label is layout-dependent (issue #25)
            expected = _kernel_code(label)
            if expected is None or code in expected:
                continue
            real = ecodes.KEY.get(code, "?")
            if isinstance(real, list):
                real = "/".join(real)
            wrong.append(f"{code} is labelled {label!r} but the kernel calls it {real}")
        self.assertEqual(wrong, [], "\n  " + "\n  ".join(wrong))

    def test_labels_survive_qkeysequence(self):
        """A label that Qt cannot parse yields an empty shortcut.

        _compute_cheatsheet_keysequence builds "Ctrl+<label>" from these names
        and only rejects empty or "Key "-prefixed ones, so an unparseable label
        is registered as a blank shortcut instead of being refused.
        """
        try:
            from PyQt6.QtGui import QKeySequence
        except ImportError:
            self.skipTest("PyQt6 not available")
        broken = []
        for code, label in self.names.items():
            if QKeySequence(f"Ctrl+{label}").toString() == "":
                broken.append(f"{code}: {label!r} renders as an empty shortcut")
        self.assertEqual(broken, [], "\n  " + "\n  ".join(broken))


class TestSatelliteTables(unittest.TestCase):
    """The tray and the plasmoid must not contradict setup or the kernel."""

    def test_tray_labels_match_kernel(self):
        labels = _parse_dict_literal(TRAY, "_PTT_KEY_LABELS")
        wrong = []
        for code, label in labels.items():
            expected = _kernel_code({"Esc": "Escape", "BackSpace": "Backspace"}
                                    .get(label, label))
            if expected is not None and code not in expected:
                wrong.append(f"tray: {code} labelled {label!r}")
        self.assertEqual(wrong, [], "\n  " + "\n  ".join(wrong))

    def test_plasmoid_named_keys_match_tray(self):
        """main.qml mirrors _PTT_KEY_LABELS by hand; catch the drift."""
        qml = QML.read_text(encoding="utf-8")
        m = re.search(r"var named = \{(.+?)\}", qml, re.S)
        self.assertIsNotNone(m, "named map not found in main.qml")
        pairs = dict(re.findall(r'(\d+)\s*:\s*"([^"]+)"', m.group(1)))
        tray = _parse_dict_literal(TRAY, "_PTT_KEY_LABELS")
        drift = [f"{c}: qml={l!r} tray={tray.get(int(c))!r}"
                 for c, l in pairs.items() if tray.get(int(c)) != l]
        self.assertEqual(drift, [], "\n  " + "\n  ".join(drift))


if __name__ == "__main__":
    unittest.main(verbosity=2)
