#!/usr/bin/env python3
"""Audit dependency parity across dictee's 4 packaging targets.

Reads packaging/dependencies.yaml (single source of truth) and parses the
real builder files to detect any divergence (missing dep, stray dep, kind
mismatch, name mismatch). Exits 0 if everything matches, 1 + diff otherwise.

Run manually:    python3 packaging/audit-deps.py
Run from a build script (fail-fast):
    python3 packaging/audit-deps.py || { echo "deps audit failed"; exit 1; }

Targets audited:
    deb-cpu, deb-cuda, deb-plasmoid       (build-deb.sh heredocs)
    rpm-cpu, rpm-cuda, rpm-plasmoid       (build-rpm.sh %spec sections)
    arch-cpu                              (PKGBUILD)
    arch-cuda                             (PKGBUILD-cuda)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("ERROR: PyYAML required (apt install python3-yaml / pip install pyyaml)\n")
    sys.exit(2)


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "packaging" / "dependencies.yaml"

DISTROS = ("deb", "rpm", "arch")
VARIANTS = ("cpu", "cuda", "plasmoid")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _split_csv(line: str) -> list[str]:
    """Split a `Depends:`-style comma-separated list while keeping ` | ` groups.

    Example: "python3, pipewire | alsa-utils, sox" -> ["python3", "pipewire | alsa-utils", "sox"]
    """
    return [p.strip() for p in line.split(",") if p.strip()]


def parse_deb(path: Path) -> dict[str, dict[str, set[str]]]:
    """Return {variant: {"hard": {...}, "optional": {...}}} from build-deb.sh.

    Recognizes blocks delimited by `Package: dictee-cuda|cpu|plasmoid` and
    grabs the next `Depends:` / `Recommends:` line in that block.
    """
    text = path.read_text()
    result: dict[str, dict[str, set[str]]] = {
        v: {"hard": set(), "optional": set()} for v in VARIANTS
    }
    name_map = {
        "dictee-cuda": "cuda",
        "dictee-cpu": "cpu",
        "dictee-plasmoid": "plasmoid",
    }
    # Anchor on `Package:` lines and read forward up to a blank line / next
    # Package: marker. Heredocs are terminated by `EOF` so we use that too.
    blocks = re.split(r"^Package:\s+", text, flags=re.MULTILINE)
    for block in blocks[1:]:
        m = re.match(r"(\S+)", block)
        if not m or m.group(1) not in name_map:
            continue
        variant = name_map[m.group(1)]
        # Stop at the next heredoc terminator
        head = block.split("\nEOF", 1)[0]
        for line in head.splitlines():
            if line.startswith("Depends:"):
                result[variant]["hard"].update(_split_csv(line[len("Depends:"):]))
            elif line.startswith("Recommends:"):
                result[variant]["optional"].update(_split_csv(line[len("Recommends:"):]))
    return result


def parse_rpm(path: Path) -> dict[str, dict[str, set[str]]]:
    """Return {variant: {hard, optional}} from build-rpm.sh %spec sections.

    Sections are bounded by `cat > "...<name>.spec" << EOF` and the next `EOF`.
    """
    text = path.read_text()
    result: dict[str, dict[str, set[str]]] = {
        v: {"hard": set(), "optional": set()} for v in VARIANTS
    }
    name_map = {
        "dictee-cuda.spec": "cuda",
        "dictee-cpu.spec": "cpu",
        "dictee-plasmoid.spec": "plasmoid",
    }
    pattern = re.compile(
        r'cat\s*>\s*"\$RPMBUILD_DIR/SPECS/(?P<name>[^"]+)"\s*<<\s*EOF\s*\n(?P<body>.*?)\nEOF',
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        variant = name_map.get(m.group("name"))
        if not variant:
            continue
        body = m.group("body")
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("Requires:"):
                value = stripped[len("Requires:"):].strip()
                # Skip the `%global __requires_exclude` lines (commented by spec)
                if value and not value.startswith("#"):
                    result[variant]["hard"].add(value)
            elif stripped.startswith("Recommends:"):
                value = stripped[len("Recommends:"):].strip()
                if value:
                    result[variant]["optional"].add(value)
    return result


def parse_pkgbuild(path: Path) -> dict[str, set[str]]:
    """Return {"hard": {...}, "optional": {...}} from a PKGBUILD-style file.

    Parses bash arrays `depends=( 'a' 'b' )` and `optdepends=( 'a: why' ... )`.
    For optdepends, only the package name (before `:`) is captured.
    """
    text = path.read_text()
    out = {"hard": set(), "optional": set()}

    def _grab(varname: str) -> list[str]:
        # Match an array `varname=( ... )` where the closing `)` is alone on
        # its line. This avoids being tripped by `)` characters inside quoted
        # strings (e.g. `'wl-clipboard: clipboard copy (Wayland)'`).
        m = re.search(
            rf"^{varname}=\(\s*\n(.*?)\n\s*\)\s*$",
            text,
            re.MULTILINE | re.DOTALL,
        )
        if not m:
            return []
        block = m.group(1)
        return re.findall(r"'([^']+)'", block)

    out["hard"].update(_grab("depends"))
    for entry in _grab("optdepends"):
        # 'pkg: explanation' → 'pkg'
        out["optional"].add(entry.split(":", 1)[0].strip())
    return out


# ---------------------------------------------------------------------------
# Expected (from manifest)
# ---------------------------------------------------------------------------

def build_expected(manifest: dict) -> dict[str, dict[str, set[str]]]:
    """Build the {target: {hard, optional}} dict from the YAML manifest."""
    targets = [f"{d}-{v}" for d in DISTROS for v in VARIANTS]
    # Arch has no plasmoid target
    targets.remove("arch-plasmoid")
    expected = {t: {"hard": set(), "optional": set()} for t in targets}

    for entry in manifest["depends"]:
        canonical = entry["canonical"]
        kind = entry["kind"]
        for variant in entry["variants"]:
            for distro in DISTROS:
                if distro == "arch" and variant == "plasmoid":
                    continue
                name = entry.get(distro)
                if not name:
                    continue
                target = f"{distro}-{variant}"
                effective_kind = entry.get(f"{distro}_kind", kind)
                if effective_kind == "omit":
                    continue
                if effective_kind not in ("hard", "optional"):
                    raise ValueError(f"{canonical}: invalid kind {effective_kind!r}")
                expected[target][effective_kind].add(name)
    return expected


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def diff_target(
    target: str,
    expected: dict[str, set[str]],
    observed: dict[str, set[str]],
) -> list[str]:
    """Return a list of human-readable error lines (empty = match)."""
    errors: list[str] = []
    for kind in ("hard", "optional"):
        exp = expected[kind]
        obs = observed[kind]
        missing = exp - obs
        extra = obs - exp
        for pkg in sorted(missing):
            errors.append(f"  [{target}/{kind}] MISSING (declared in manifest, absent in builder): {pkg}")
        for pkg in sorted(extra):
            errors.append(f"  [{target}/{kind}] EXTRA   (in builder, absent from manifest): {pkg}")
    return errors


def main() -> int:
    with MANIFEST.open() as fh:
        manifest = yaml.safe_load(fh)

    expected = build_expected(manifest)

    observed: dict[str, dict[str, set[str]]] = {}
    deb = parse_deb(ROOT / "build-deb.sh")
    rpm = parse_rpm(ROOT / "build-rpm.sh")
    arch_cpu = parse_pkgbuild(ROOT / "PKGBUILD")
    arch_cuda = parse_pkgbuild(ROOT / "PKGBUILD-cuda")

    for v in VARIANTS:
        observed[f"deb-{v}"] = deb[v]
        observed[f"rpm-{v}"] = rpm[v]
    observed["arch-cpu"] = arch_cpu
    observed["arch-cuda"] = arch_cuda

    targets = sorted(expected)
    errors_by_target: dict[str, list[str]] = {}
    total_errors = 0
    for target in targets:
        errs = diff_target(target, expected[target], observed[target])
        if errs:
            errors_by_target[target] = errs
            total_errors += len(errs)

    if total_errors == 0:
        print(f"✓ packaging deps audit OK — {len(targets)} targets, {sum(len(observed[t]['hard']) + len(observed[t]['optional']) for t in targets)} entries verified.")
        return 0

    print(f"✗ packaging deps audit FAILED — {total_errors} divergence(s) across {len(errors_by_target)} target(s).\n")
    for target in sorted(errors_by_target):
        print(f"=== {target} ===")
        for line in errors_by_target[target]:
            print(line)
        print()
    print("Fix : either update packaging/dependencies.yaml or the builder file.")
    print("      The manifest header lists the 6 builder sections to keep in sync.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
