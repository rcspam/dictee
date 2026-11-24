#!/usr/bin/env python3
"""running_version() in dictee-setup.py: the version the About, the welcome
page and the update check show.

On the dev machine /usr/bin/dictee-setup is a symlink into the repository,
and /usr/share/dictee/VERSION is whatever package was installed last (it said
1.3.5 under the 1.4 code). A source checkout must report its own line,
"<major>.<minor>-devel" from Cargo.toml; a real install keeps reading VERSION.

The function is pulled out of dictee-setup.py with ast, so no Qt is needed.
"""
import ast
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP = os.path.join(HERE, "..", "dictee-setup.py")


def _load():
    src = open(SETUP, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "running_version")
    ns = {"os": os, "__file__": SETUP}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), SETUP, "exec"), ns)
    return ns["running_version"]


running_version = _load()


class RunningVersion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_checkout_reports_devel_line_from_cargo(self):
        script = self._write("repo/dictee-setup.py", "")
        self._write("repo/Cargo.toml", '[package]\nname = "x"\nversion = "1.4.0-beta"\n')
        stale = self._write("share/VERSION", "1.3.5 build ccd352e\n")
        self.assertEqual(running_version(script, (stale,)), "1.4-devel")

    def test_symlink_into_checkout_is_followed(self):
        script = self._write("repo/dictee-setup.py", "")
        self._write("repo/Cargo.toml", 'version = "1.4.0-beta"\n')
        link = os.path.join(self.root, "bin", "dictee-setup")
        os.makedirs(os.path.dirname(link))
        os.symlink(script, link)
        stale = self._write("share/VERSION", "1.3.5 build ccd352e\n")
        self.assertEqual(running_version(link, (stale,)), "1.4-devel")

    def test_installed_copy_reads_version_file(self):
        script = self._write("usr/bin/dictee-setup", "")
        ver = self._write("share/VERSION", "1.4.0~beta build abc1234\n")
        self.assertEqual(running_version(script, (ver,)), "1.4.0~beta build abc1234")

    def test_nothing_known_is_dev(self):
        script = self._write("usr/bin/dictee-setup", "")
        missing = os.path.join(self.root, "nope", "VERSION")
        self.assertEqual(running_version(script, (missing,)), "dev")


if __name__ == "__main__":
    unittest.main()
