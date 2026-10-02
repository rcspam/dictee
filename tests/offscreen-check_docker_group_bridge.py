"""docker_cmd in dictee-setup: bridging the docker group without sg.

When the post-install has just added the user to the docker group, this
process does not carry it yet and docker_cmd ran everything through
`sg docker -c`. Arch dropped sg from shadow 4.20 (#35): there the call raised
FileNotFoundError, the callers took that for "no docker", and the wizard
started by install.sh showed Docker as missing until the next login. The
bridge now follows dictee-ptt's input_group_bridge: sg where it exists,
util-linux's `newgrp -c` otherwise, the bare command when neither can help.

sg and newgrp are stand-ins on a private PATH; subprocess.run is captured, so
nothing is executed and the result does not depend on this machine.

Usage: python3 tests/offscreen-check_docker_group_bridge.py
"""
import importlib.util
import os
import stat
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="dictee-docker-bridge-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ["XDG_RUNTIME_DIR"] = _HOME
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LANGUAGE"] = "C"
os.environ["LC_ALL"] = "C"
os.environ["LANG"] = "C"

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dictee-setup.py")
spec = importlib.util.spec_from_file_location("dictee_setup", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_setup"] = mod
spec.loader.exec_module(mod)

SHADOW_HELP = "Usage: newgrp [-] [group]\n"
UTIL_LINUX_HELP = "Usage: newgrp <group> [[-c] <command>]\n -c, --command <command>\n"
ARGS = ["docker", "inspect", "-f", "{{.State.Running}}", "dictee-libretranslate"]


def tools_path(sg, newgrp):
    """A PATH holding only the stand-ins asked for."""
    d = tempfile.mkdtemp(prefix="dictee-fake-tools-", dir=_HOME)
    for name, present in (("sg", sg), ("newgrp", newgrp)):
        if present:
            p = os.path.join(d, name)
            with open(p, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
    return d


class Captured:
    """Replaces subprocess.run: answers `newgrp --help` with the chosen text
    and records the one command docker_cmd finally runs."""
    def __init__(self, newgrp_help):
        self.newgrp_help = newgrp_help
        self.cmd = None

    def __call__(self, cmd, **kwargs):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        r = R()
        if list(cmd[:2]) == ["newgrp", "--help"]:
            r.stdout = self.newgrp_help
            return r
        self.cmd = list(cmd)
        return r


fails = 0


def check(label, got, expected):
    global fails
    if got == expected:
        print(f"PASS {label}")
    else:
        print(f"FAIL {label}: got {got!r}, expected {expected!r}")
        fails += 1


def run_case(use_sg, sg, newgrp, newgrp_help):
    saved_path, saved_run, saved_flag = os.environ["PATH"], mod.subprocess.run, mod._docker_use_sg
    cap = Captured(newgrp_help)
    try:
        os.environ["PATH"] = tools_path(sg, newgrp)
        mod.subprocess.run = cap
        mod._docker_use_sg = use_sg
        mod.docker_cmd(ARGS, capture_output=True, text=True, timeout=5)
    except FileNotFoundError as e:
        return f"FileNotFoundError: {e}"
    finally:
        os.environ["PATH"], mod.subprocess.run, mod._docker_use_sg = saved_path, saved_run, saved_flag
    return cap.cmd


joined = "docker inspect -f '{{.State.Running}}' dictee-libretranslate"
check("group effective: the bare command",
      run_case(False, True, True, UTIL_LINUX_HELP), ARGS)
check("group just added, sg (Debian/Fedora)",
      run_case(True, True, True, SHADOW_HELP), ["sg", "docker", "-c", joined])
check("group just added, no sg, util-linux newgrp (Arch)",
      run_case(True, False, True, UTIL_LINUX_HELP), ["newgrp", "docker", "-c", joined])
check("group just added, nothing can bridge: bare command, no crash",
      run_case(True, False, True, SHADOW_HELP), ARGS)
check("group just added, no sg, no newgrp: bare command, no crash",
      run_case(True, False, False, ""), ARGS)

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("ALL PASS")
