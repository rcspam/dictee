"""Two Canary model checks in dictee-setup only knew about the fp32 encoder.

dictee_models and the tray learned to accept `encoder-model.int8.onnx` beside
`encoder-model.onnx`, but two sites in dictee-setup kept the fp32 filename
hardcoded:

  1. _asr_backend_ready("canary") -- the Apply guard. An int8-only Canary in
     the user dir was reported missing, and _on_apply aborted the save, so the
     backend could not be enabled at all. The system-dir half of that test only
     asks whether the directory exists, so a system install was never affected;
     the hole is the user dir alone.
  2. _canary_model_installed()'s except-ImportError fallback -- the duplicated
     copy of the logic used when dictee_models cannot be imported. It drives
     the install/delete buttons only, so it misreports rather than blocks.

Neither branch touches `self`, so both are called unbound: no Qt dialog is
built. The filesystem is faked instead of written to, because the system half
of the guard names /usr/share/dictee/canary, which a dev box may really have.
"""
import importlib.util
import os
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="dictee-canary-int8-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ["XDG_RUNTIME_DIR"] = _HOME
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Pin gettext to the msgids: the assertions below read the refusal messages,
# and on a French box _() would hand back the .mo translation instead.
os.environ["LANGUAGE"] = "C"
os.environ["LC_ALL"] = "C"
os.environ["LANG"] = "C"

# Resolved from this file, not hardcoded: the same fix lands on master and on
# release/1.3, and a hardcoded path would quietly test the other worktree's copy.
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dictee-setup.py")
spec = importlib.util.spec_from_file_location("dictee_setup", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_setup"] = mod
spec.loader.exec_module(mod)

assert mod.CONF_PATH.startswith(_HOME), f"CONF_PATH escaped the sandbox: {mod.CONF_PATH}"

SYS_CANARY = "/usr/share/dictee/canary"
CUDA_SO = "/usr/lib/dictee/libonnxruntime_providers_cuda.so"
USER_CANARY = os.path.join(mod.DICTEE_DATA_DIR, "canary")
USER_FP32 = os.path.join(USER_CANARY, "encoder-model.onnx")
USER_INT8 = os.path.join(USER_CANARY, "encoder-model.int8.onnx")
SYS_FP32 = os.path.join(mod.CANARY_MODEL_DIR, "encoder-model.onnx")
SYS_INT8 = os.path.join(mod.CANARY_MODEL_DIR, "encoder-model.int8.onnx")

_real_isdir = os.path.isdir
_real_isfile = os.path.isfile


class fake_fs:
    """Only the declared paths exist. Anything else is absent, so a path the
    code looks at but the scenario forgot shows up as a failure, not a pass."""

    def __init__(self, dirs=(), files=()):
        self.dirs, self.files = set(dirs), set(files)

    def __enter__(self):
        os.path.isdir = lambda p: p in self.dirs
        os.path.isfile = lambda p: p in self.files
        return self

    def __exit__(self, *exc):
        os.path.isdir, os.path.isfile = _real_isdir, _real_isfile
        return False


def ready(**fs):
    """_asr_backend_ready("canary"), unbound -- the canary branch ignores self."""
    with fake_fs(**fs):
        return mod.DicteeSetupDialog._asr_backend_ready(None, "canary")


def installed(**fs):
    """_canary_model_installed() forced down its except-ImportError fallback."""
    saved = sys.modules.get("dictee_models", "absent")
    sys.modules["dictee_models"] = None  # makes `from dictee_models import ...` raise
    try:
        with fake_fs(**fs):
            return mod.DicteeSetupDialog._canary_model_installed(None)
    finally:
        if saved == "absent":
            del sys.modules["dictee_models"]
        else:
            sys.modules["dictee_models"] = saved


failures = []


def check(label, got, want):
    if got == want:
        print(f"PASS {label}")
    else:
        failures.append(label)
        print(f"FAIL {label}: got {got!r}, expected {want!r}")


# --- 1. the Apply guard -------------------------------------------------------

# The regression: int8 alone in the user dir, no system install.
ok, msg = ready(files={USER_INT8, CUDA_SO})
check("apply guard accepts an int8-only Canary in the user dir", ok, True)

# The paths that already worked, which the fix must not break.
ok, _msg = ready(files={USER_FP32, CUDA_SO})
check("apply guard still accepts an fp32 Canary in the user dir", ok, True)

ok, _msg = ready(dirs={SYS_CANARY}, files={CUDA_SO})
check("apply guard still accepts a system Canary install", ok, True)

# And the guard must still catch a Canary that really is absent, otherwise the
# fix would trade a false refusal for a silently broken backend on F9.
ok, msg = ready(files={CUDA_SO})
check("apply guard still refuses a missing Canary", ok, False)
if not ok:
    check("  ...with the not-installed message", "not installed" in msg, True)

# The CUDA gate sits behind the model gate and must keep firing on its own.
ok, msg = ready(files={USER_INT8})
check("apply guard still refuses an int8 Canary without the CUDA build", ok, False)
if not ok:
    check("  ...with the CUDA message", "CUDA" in msg, True)

# --- 2. the ImportError fallback ---------------------------------------------

check("fallback sees an int8 Canary in the user dir", installed(files={USER_INT8}), True)
check("fallback sees an int8 Canary in the system dir", installed(files={SYS_INT8}), True)
check("fallback still sees an fp32 Canary", installed(files={USER_FP32}), True)
check("fallback still sees an fp32 system Canary", installed(files={SYS_FP32}), True)
check("fallback still reports a missing Canary", installed(files=set()), False)

print()
if failures:
    print(f"{len(failures)} FAILED: " + ", ".join(failures))
    sys.exit(1)
print("OK")
