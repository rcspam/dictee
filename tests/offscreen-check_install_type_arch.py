"""_detect_install_type on Arch: the CUDA package is named dictee-cuda.

It queried `pacman -Q dictee` only. The CUDA PKGBUILD installs `dictee-cuda`
(which provides dictee, but pacman -Q matches names, not provides), so on an
Arch machine with the CUDA variant the lookup failed, the function fell
through to the tarball or unknown kinds, and "Check for updates" offered the
tarball to a pacman install. The deb and rpm branches already ask for all
three names; this pins the same for pacman.

pacman, dpkg-query and rpm are stand-ins on a private PATH, so the result
does not depend on the machine running the test.

Usage: python3 tests/offscreen-check_install_type_arch.py
"""
import importlib.util
import os
import stat
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="dictee-install-type-")
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

detect = mod.DicteeSetupDialog._detect_install_type


def stub(path, body):
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


def arch_path(installed):
    """A PATH with only a fake pacman (no dpkg-query, no rpm) and the base
    tools subprocess needs. The fake answers like pacman -Q: one line per
    installed package, an error per unknown name, exit 1 when any is unknown."""
    d = tempfile.mkdtemp(prefix="dictee-fake-arch-", dir=_HOME)
    for tool in ("sh", "grep", "sed", "awk", "cat"):
        real = None
        for p in ("/usr/bin", "/bin"):
            if os.path.exists(os.path.join(p, tool)):
                real = os.path.join(p, tool)
                break
        if real:
            os.symlink(real, os.path.join(d, tool))
    stub(os.path.join(d, "pacman"), f"""
[ "$1" = "-Q" ] || exit 1
shift
rc=0
for name in "$@"; do
    case " {installed} " in
        *" $name "*) echo "$name 1.3.7.rc4-1" ;;
        *) echo "error: package '$name' was not found" >&2; rc=1 ;;
    esac
done
exit $rc
""")
    return d


fails = 0


def check(label, got, expected):
    global fails
    if got == expected:
        print(f"PASS {label}")
    else:
        print(f"FAIL {label}: got {got!r}, expected {expected!r}")
        fails += 1


saved = os.environ["PATH"]
try:
    os.environ["PATH"] = arch_path("dictee-cuda")
    r = detect()
    check("Arch with dictee-cuda: kind", r.get("kind"), "pacman")
    check("Arch with dictee-cuda: package name", r.get("pkg_name"), "dictee-cuda")

    os.environ["PATH"] = arch_path("dictee")
    r = detect()
    check("Arch with dictee (CPU): kind", r.get("kind"), "pacman")
    check("Arch with dictee (CPU): package name", r.get("pkg_name"), "dictee")

    os.environ["PATH"] = arch_path("")
    r = detect()
    check("Arch without dictee: not reported as pacman", r.get("kind") != "pacman", True)
finally:
    os.environ["PATH"] = saved

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("ALL PASS")
