#!/usr/bin/env python3
"""CLI contract test for the transcribe-* Rust binaries.

Guards against the 1.3.5 class of bug: dictee-setup invoked
``transcribe-daemon --socket <path>`` — a flag the daemon did not implement, so
the socket path was silently swallowed as the model directory and the wizard's
"Test dictation" step failed for everyone.

Every ``--flag`` a Python or shell caller passes to a transcribe-* binary must
be one the binary's Rust arg parser actually accepts. ``ACCEPTED_FLAGS`` mirrors
the parsers in ``src/bin/*.rs`` (the ``parse_*_args`` functions, each covered by
its own Rust unit tests). When you add a flag to a binary, add it here too.
"""
import ast
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Flags accepted by each binary's Rust arg parser (src/bin/<name>.rs).
ACCEPTED_FLAGS = {
    "transcribe": {"--help", "-h"},
    "transcribe-daemon": {"--canary", "--socket", "--help", "-h"},
    "transcribe-client": {"--socket", "--help", "-h"},
    "transcribe-diarize": {"--sensitivity", "--help", "-h"},
    "transcribe-diarize-batch": {
        "--sensitivity", "--model-dir", "--sortformer-dir",
        "--stdin", "--no-postprocess", "--no-diarize", "--help", "-h",
    },
    "diarize-only": {"--sensitivity", "--help", "-h"},
    "transcribe-stream-diarize": {"--help", "-h"},
}
BINARIES = set(ACCEPTED_FLAGS)

PY_CALLERS = [
    "dictee-setup.py", "dictee-transcribe.py", "dictee-tray.py", "dictee-ptt.py",
]
SH_CALLERS = ["dictee", "dictee-common.sh", "dictee-switch-backend", "dictee-reset"]


def _flags_in_list(elts):
    """Collect '--flag' / '-h' string constants from a list of AST elements."""
    out = set()
    for e in elts:
        if isinstance(e, ast.Constant) and isinstance(e.value, str) \
                and e.value.startswith("-"):
            out.add(e.value)
    return out


def python_invocations(path):
    """Map binary -> set of flags passed to it, from a Python source file.

    Handles both direct list literals (``["transcribe-daemon", "--socket", x]``)
    and incrementally built commands (``cmd = ["transcribe-client"]`` followed by
    ``cmd += ["--socket", x]`` / ``cmd.append("--socket")``), tracked per scope.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    found = {}

    def record(binary, flags):
        found.setdefault(binary, set()).update(flags)

    # Pass A (whole module): every direct list literal that starts with a binary
    # name, e.g. ["transcribe-daemon", "--socket", sock]. Scope-independent.
    for node in ast.walk(tree):
        if isinstance(node, ast.List) and node.elts \
                and isinstance(node.elts[0], ast.Constant) \
                and node.elts[0].value in BINARIES:
            record(node.elts[0].value, _flags_in_list(node.elts[1:]))

    # Pass B (per function): incrementally built commands, e.g.
    #   cmd = ["transcribe-client"]; cmd += ["--socket", x]; cmd.append(wav)
    # var_binary is rebuilt per function so same-named `cmd` vars in different
    # functions never bleed into each other.
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        var_binary = {}
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.List) \
                    and node.value.elts \
                    and isinstance(node.value.elts[0], ast.Constant) \
                    and node.value.elts[0].value in BINARIES:
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        var_binary[tgt.id] = node.value.elts[0].value
        for node in ast.walk(scope):
            if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) \
                    and node.target.id in var_binary \
                    and isinstance(node.value, ast.List):
                record(var_binary[node.target.id], _flags_in_list(node.value.elts))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and isinstance(node.func.value, ast.Name) \
                    and node.func.value.id in var_binary:
                binary = var_binary[node.func.value.id]
                if node.func.attr == "append":
                    record(binary, _flags_in_list(node.args))
                elif node.func.attr == "extend" and node.args \
                        and isinstance(node.args[0], ast.List):
                    record(binary, _flags_in_list(node.args[0].elts))
    return found


def shell_invocations(path):
    """Map binary -> set of flags, from a shell script.

    Only matches a binary used as a command word: at line start, after a pipe /
    ``;`` / ``(`` / ``&&`` / ``eval``, and immediately followed by whitespace or
    end of line. Longest binary name wins, so ``transcribe-diarize-batch`` is not
    mistaken for ``transcribe-diarize`` nor ``transcribe.sock`` for ``transcribe``.
    """
    names = sorted(BINARIES, key=len, reverse=True)
    bin_re = re.compile(
        r"(?:^|[|&;(]|\beval\s+|\s)(" + "|".join(re.escape(b) for b in names)
        + r")(?=\s|$)")
    found = {}
    for line in path.read_text().splitlines():
        for m in bin_re.finditer(line):
            rest = line[m.end():]
            for flag in re.findall(r"(?<!\S)(--?[A-Za-z][-\w]*)", rest):
                found.setdefault(m.group(1), set()).add(flag)
    return found


class CliContractTest(unittest.TestCase):
    def test_python_callers_pass_only_accepted_flags(self):
        violations = []
        for name in PY_CALLERS:
            p = REPO / name
            if not p.exists():
                continue
            for binary, flags in python_invocations(p).items():
                bad = flags - ACCEPTED_FLAGS[binary]
                for f in sorted(bad):
                    violations.append(f"{name}: '{binary}' does not accept '{f}'")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_shell_callers_pass_only_accepted_flags(self):
        violations = []
        for name in SH_CALLERS:
            p = REPO / name
            if not p.exists():
                continue
            for binary, flags in shell_invocations(p).items():
                bad = flags - ACCEPTED_FLAGS[binary]
                for f in sorted(bad):
                    violations.append(f"{name}: '{binary}' does not accept '{f}'")
        self.assertEqual(violations, [], "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
