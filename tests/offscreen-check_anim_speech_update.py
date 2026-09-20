"""The setup could install animation-speech, never update it.

Two holes, both closed here:

  1. _check_animation_speech hid the install button as soon as the binary
     existed. Whoever installed animation-speech once stayed on that version
     forever, with nothing in the UI offering the newer one. The button now
     stays, as an update check.
  2. The installed version was read through dpkg-query alone, so every
     non-Debian user got a bare "installed" with no number, and no comparison
     was possible at all. _animation_speech_version now asks rpm and pacman
     too, and falls back to the zipapp's own __version__, which a tarball
     install is the only way to reach.

The InstallThread half is exercised without network: its run() is driven with
a stubbed urllib, so what is asserted is the decision it takes, not GitHub's
answer.

Run: python3 tests/offscreen-check_anim_speech_update.py
"""
import importlib.util
import io
import json
import os
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="dictee-anim-update-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ["XDG_RUNTIME_DIR"] = _HOME
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Pin gettext to the msgids: the assertions read the messages back.
os.environ["LANGUAGE"] = "C"
os.environ["LC_ALL"] = "C"
os.environ["LANG"] = "C"

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dictee-setup.py")
spec = importlib.util.spec_from_file_location("dictee_setup", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_setup"] = mod
spec.loader.exec_module(mod)

failures = []


def check(label, got, want):
    if got == want:
        print(f"PASS {label}")
    else:
        failures.append(label)
        print(f"FAIL {label}: got {got!r}, expected {want!r}")


# --- 1. reading the installed version ----------------------------------------

read_version = mod.DicteeSetupDialog._animation_speech_version


class FakeRun:
    """Stands in for subprocess.run over the three package managers."""

    def __init__(self, answers):
        # answers: {"dpkg-query": (rc, stdout), ...}; a missing tool raises.
        self.answers = answers

    def __call__(self, cmd, **kw):
        tool = cmd[0]
        if tool not in self.answers:
            raise FileNotFoundError(tool)

        class R:
            pass

        R.returncode, R.stdout = self.answers[tool]
        return R


def with_stubs(answers, which=None):
    real_run, real_which = mod.subprocess.run, mod.shutil.which
    mod.subprocess.run = FakeRun(answers)
    mod.shutil.which = lambda name: which
    try:
        return read_version()
    finally:
        mod.subprocess.run, mod.shutil.which = real_run, real_which


check("reads a Debian version",
      with_stubs({"dpkg-query": (0, "1.2.1")}), "1.2.1")
check("drops the Debian packaging release suffix",
      with_stubs({"dpkg-query": (0, "1.2.1-2")}), "1.2.1")
check("falls through to rpm when dpkg-query answers nothing",
      with_stubs({"dpkg-query": (1, ""), "rpm": (0, "1.2.1")}), "1.2.1")
check("reads pacman's 'name version' answer",
      with_stubs({"pacman": (0, "animation-speech 1.2.1-1")}), "1.2.1")
check("says nothing rather than guessing when no manager knows",
      with_stubs({"dpkg-query": (1, "")}), "")

# The tarball install is the case no package manager can answer: the version
# then has to come out of the zipapp itself.
import zipfile  # noqa: E402

app = os.path.join(_HOME, "animation-speech")
with zipfile.ZipFile(app, "w") as z:
    z.writestr("animation_speech/__init__.py", "__version__ = '1.2.1'\n")
check("falls back to the zipapp when no package manager knows",
      with_stubs({}, which=app), "1.2.1")

not_an_app = os.path.join(_HOME, "not-a-zipapp")
with open(not_an_app, "w") as f:
    f.write("#!/bin/sh\necho hello\n")
check("survives a binary that is not a zipapp",
      with_stubs({}, which=not_an_app), "")


# --- 2. what the install thread decides --------------------------------------

def run_thread(installed, published, assets=None):
    """Drive InstallThread.run() with a stubbed GitHub and no installer."""
    payload = json.dumps({
        "tag_name": published,
        "assets": assets if assets is not None else [
            {"name": "animation-speech_9.9.9_all.deb",
             "browser_download_url": "https://example.invalid/x.deb"}],
    }).encode()

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    result = {}

    th = mod.InstallThread(installed)
    th.done = type("S", (), {"emit": staticmethod(
        lambda ok, msg: result.update(ok=ok, msg=msg))})()
    th.progress = type("S", (), {"emit": staticmethod(lambda *_a: None)})()

    import urllib.request
    saved = urllib.request.urlopen, urllib.request.urlretrieve
    urllib.request.urlopen = lambda *a, **k: FakeResp(payload)
    urllib.request.urlretrieve = lambda *a, **k: None
    saved_which, saved_run = mod.shutil.which, mod.subprocess.run
    # No package manager: the download branch would then pick the .tar.gz and
    # try to install it, which is exactly what we must not reach.
    mod.shutil.which = lambda name: None
    try:
        th.run()
    finally:
        urllib.request.urlopen, urllib.request.urlretrieve = saved
        mod.shutil.which, mod.subprocess.run = saved_which, saved_run
    return result


r = run_thread("1.2.1", "v1.2.1")
check("same version: reports success", r.get("ok"), True)
check("same version: says so instead of downloading",
      "already" in r.get("msg", ""), True)

r = run_thread("1.2.2", "v1.2.1")
check("newer than published: nothing to do either", r.get("ok"), True)
check("newer than published: same message", "already" in r.get("msg", ""), True)

# A newer release must fall through to the download path. There is no package
# manager in the stub, so it looks for a .tar.gz asset and finds none: proof
# that the version check let it through rather than short-circuiting.
r = run_thread("1.2.0", "v1.2.1")
check("newer release: goes past the version check", r.get("ok"), False)
check("newer release: reached the asset lookup",
      "tar.gz" in r.get("msg", ""), True)

# An unreadable local version must not silently skip the update.
r = run_thread("", "v1.2.1")
check("unknown local version: still goes looking", r.get("ok"), False)

# A release with no assets is reported as such, unchanged behaviour.
r = run_thread("1.2.0", "v1.2.1", assets=[])
check("empty release: still reported", r.get("ok"), False)
check("empty release: keeps its own message",
      "No assets" in r.get("msg", ""), True)

print()
if failures:
    print(f"{len(failures)} FAILED: " + ", ".join(failures))
    sys.exit(1)
print("OK")
