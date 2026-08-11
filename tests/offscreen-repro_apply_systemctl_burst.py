"""_on_apply fired one systemctl process per service instead of grouping them.

systemd serialises those requests anyway, so the burst bought nothing: measured
on 9 throwaway units, 9 parallel calls take 2.30 s against 0.30 s for a single
grouped call. Grouping has one trap, also measured: a grouped call aborts
entirely on the first unit systemd cannot resolve, leaving the units named
beside it untouched -- and a CPU install ships no dictee-kyutai.service.

So the code groups, and retries unit by unit when a group fails. Two scenarios:

  1. every unit resolvable -> grouped, few calls, no retry
  2. dictee-kyutai missing -> the group fails, every unit of that group is
     retried on its own, so nothing is left unhandled

Both check the set of actions is what the pre-grouping code asked for, and
that dictee-ptt is still enabled WITHOUT --now (Apply must not start it).

HOME is redirected to a throwaway dir so the real dictee.conf is never touched,
and every subprocess is captured rather than run.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="dictee-apply-test-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ["XDG_RUNTIME_DIR"] = _HOME
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = "/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-setup.py"
spec = importlib.util.spec_from_file_location("dictee_setup", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_setup"] = mod
spec.loader.exec_module(mod)

assert mod.CONF_PATH.startswith(_HOME), f"CONF_PATH escaped the sandbox: {mod.CONF_PATH}"

from PyQt6.QtWidgets import QApplication

ASR_UNITS = {"dictee", "dictee-vosk", "dictee-whisper", "dictee-whisper-rust",
             "dictee-canary", "dictee-nemotron", "dictee-kyutai"}
ALL_UNITS = ASR_UNITS | {"dictee-tray", "dictee-ptt"}

calls = []          # every systemctl argv, in order
bg_calls = []       # the ones sent through Popen
resolvable = set()  # what the fake systemd can resolve this round


def units_of(cmd):
    """Unit names in a systemctl argv, options and verb dropped."""
    return [x for x in cmd[3:] if not x.startswith("-")]


class _Res:
    def __init__(self, out="", code=0):
        self.stdout = out
        self.stderr = ""
        self.returncode = code


class _EmptyStream:
    def readline(self, *a, **kw):
        return ""

    def read(self, *a, **kw):
        return ""

    def close(self):
        pass


class _Proc:
    """Popen stand-in. Records, never runs, and reproduces the measured
    systemctl behaviour: a call naming an unresolvable unit fails as a whole."""
    def __init__(self, cmd, *a, **kw):
        self.cmd = list(cmd)
        self.stdout = _EmptyStream()
        self.stderr = _EmptyStream()
        self.returncode = 0
        if cmd and cmd[0] == "systemctl":
            calls.append(list(cmd))
            bg_calls.append(list(cmd))
            named = units_of(cmd)
            if named and not all(u in resolvable for u in named):
                self.returncode = 1

    def wait(self, *a, **kw):
        return self.returncode

    def poll(self, *a, **kw):
        return self.returncode

    def terminate(self, *a, **kw):
        pass

    kill = terminate

    def communicate(self, *a, **kw):
        return ("", "")


def fake_run(cmd, *a, **kw):
    if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "systemctl":
        calls.append(list(cmd))
    return _Res()


mod.subprocess.run = fake_run
mod.subprocess.Popen = _Proc


class _Msg:
    """Never let a modal block the run."""
    @staticmethod
    def information(*a, **kw):
        return None

    warning = critical = question = information


mod.QMessageBox = _Msg

app = QApplication([])


def actions(cmds):
    """Expand grouped calls: one (verb, unit, now) triple per unit named."""
    out = set()
    for c in cmds:
        now = "--now" in c
        for unit in units_of(c):
            out.add((c[2], unit.removesuffix(".service"), now))
    return out


def run_apply(tray_on, known):
    global resolvable
    resolvable = known
    calls.clear()
    bg_calls.clear()
    dlg = mod.DicteeSetupDialog()
    dlg.chk_tray.setChecked(tray_on)
    dlg._on_apply(show_message=False, mark_setup_done=False)
    dlg.close()
    return actions(calls)


def burst():
    """The enable/disable rafale -- restarts are legitimate, count only these."""
    return [c for c in bg_calls if c[2] in ("enable", "disable")]


def common_checks(label, acts, tray_on):
    """The invariants that must survive any grouping or retry."""
    asr = {(v, u, n) for (v, u, n) in acts if u in ASR_UNITS}
    enabled = {u for (v, u, n) in asr if v == "enable"}
    disabled = {(u, n) for (v, u, n) in asr if v == "disable"}
    assert len(enabled) == 1, f"{label}: expected 1 enabled ASR, got {enabled}"
    assert disabled == {(u, True) for u in ASR_UNITS - enabled}, \
        f"{label}: wrong disable set {disabled}"

    want_tray = ("enable" if tray_on else "disable", "dictee-tray", True)
    assert want_tray in acts, f"{label}: missing {want_tray}"

    # dictee-ptt is enabled for boot only: starting it here would be a change
    assert ("enable", "dictee-ptt", False) in acts, f"{label}: ptt not enabled"
    assert ("enable", "dictee-ptt", True) not in acts, f"{label}: ptt started by Apply"


# 1. everything resolvable: group, and stop spawning one process per unit
for tray_on in (True, False):
    acts = run_apply(tray_on, ALL_UNITS)
    common_checks(f"all resolvable / tray={tray_on}", acts, tray_on)
    assert len(burst()) <= 3, (
        f"tray={tray_on}: {len(burst())} enable/disable calls, expected <= 3:\n  "
        + "\n  ".join(" ".join(c) for c in burst()))
    print(f"PASS all resolvable / tray={tray_on}: {len(burst())} enable/disable calls, no retry")

# 2. CPU install: dictee-kyutai does not exist, so the group fails as a whole
acts = run_apply(True, ALL_UNITS - {"dictee-kyutai"})
common_checks("kyutai missing", acts, True)
grouped = [c for c in burst() if len(units_of(c)) > 1]
singles = [c for c in burst() if len(units_of(c)) == 1]
assert grouped, "kyutai missing: nothing was grouped, the fast path is gone"
for g in grouped:
    for u in units_of(g):
        assert [g[2], u] in [[s[2], units_of(s)[0]] for s in singles], \
            f"kyutai missing: {u} was in a failed group but never retried alone"
print(f"PASS kyutai missing: group failed, all {len(units_of(grouped[0]))} units retried alone "
      f"({len(burst())} enable/disable calls)")
print("OK")
