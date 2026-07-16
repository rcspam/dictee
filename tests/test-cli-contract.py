#!/usr/bin/env python3
"""CLI contract test for the transcribe-* Rust binaries.

Guards against a class of bug where a Python/shell caller passes a ``--flag`` (or
relies on an env var) that the target binary's Rust arg parser does not actually
implement — the flag is then silently mis-parsed or ignored at runtime. The
release/1.3 wizard failure (``transcribe-daemon --socket`` swallowed as the model
dir) was exactly this.

Every ``--flag`` a caller passes to a transcribe-* binary must be one the binary's
Rust arg parser accepts. ``ACCEPTED_FLAGS`` mirrors the parsers in
``src/bin/*.rs``; update it (and the binary's ``parse_*_args`` unit tests) when a
flag is added or removed.
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
    "transcribe-client": {"--json-timestamps", "--help", "-h"},
    "transcribe-diarize": {"--sensitivity", "--help", "-h"},
    "transcribe-diarize-batch": {
        "--sensitivity", "--model-dir", "--sortformer-dir",
        "--stdin", "--no-postprocess", "--no-diarize", "--help", "-h",
    },
    "diarize-only": {"--sensitivity", "--stream", "--help", "-h"},
    "transcribe-stream-diarize": {"--help", "-h"},
}
BINARIES = set(ACCEPTED_FLAGS)

# dictee-meeting-live is a Python script with no .py extension.
PY_CALLERS = [
    "dictee-setup.py", "dictee-transcribe.py", "dictee-tray.py",
    "dictee-ptt.py", "dictee-meeting-live",
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


def python_invocations(path, binaries=None):
    """Map binary -> set of flags passed to it, from a Python source file.

    Handles direct list literals (``["transcribe-daemon", "--socket", x]``) and
    incrementally built commands (``cmd = ["transcribe-client"]`` then
    ``cmd += ["--json-timestamps"]`` / ``cmd.append(...)``), tracked per scope.

    `binaries` restricts (and extends) the set of command names to look for;
    it defaults to the Rust BINARIES table, and the Python-tool contract test
    passes its own (dictee-transcribe, dictee-moss-diarize).
    """
    binaries = BINARIES if binaries is None else binaries
    tree = ast.parse(path.read_text(), filename=str(path))
    found = {}

    def record(binary, flags):
        found.setdefault(binary, set()).update(flags)

    # Pass A (whole module): every direct list literal that starts with a binary.
    for node in ast.walk(tree):
        if isinstance(node, ast.List) and node.elts \
                and isinstance(node.elts[0], ast.Constant) \
                and node.elts[0].value in binaries:
            record(node.elts[0].value, _flags_in_list(node.elts[1:]))

    # Pass B (per function): incrementally built commands. var_binary is rebuilt
    # per function so same-named `cmd` vars in different functions never bleed.
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        var_binary = {}
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.List) \
                    and node.value.elts \
                    and isinstance(node.value.elts[0], ast.Constant) \
                    and node.value.elts[0].value in binaries:
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
    ``;`` / ``(`` / ``&&`` / ``eval``, immediately followed by whitespace or EOL.
    Longest binary name wins, so ``transcribe-diarize-batch`` is not mistaken for
    ``transcribe-diarize`` nor ``transcribe.sock`` for ``transcribe``.
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
                for f in sorted(flags - ACCEPTED_FLAGS[binary]):
                    violations.append(f"{name}: '{binary}' does not accept '{f}'")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_python_tools_accept_the_flags_python_callers_pass(self):
        """Same contract, Python -> Python: meeting-live hands the meeting
        over with `dictee-transcribe --file ... --diarize --diar-engine ...`,
        and dictee-moss-diarize is called by dictee-transcribe. An argparse
        script rejects an unknown flag outright (exit 2), so a drifted flag
        breaks the handoff at Stop — after the meeting was recorded.

        Accepted flags are read from each tool's own argparse calls rather
        than mirrored in a table, so adding an option cannot desync them.
        """
        tools = {
            "dictee-transcribe": REPO / "dictee-transcribe.py",
            "dictee-moss-diarize": REPO / "dictee-moss-diarize",
        }
        accepted = {}
        for name, path in tools.items():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            flags = set()
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "add_argument"):
                    flags |= _flags_in_list(node.args)
            flags |= {"--help", "-h"}
            self.assertTrue(flags - {"--help", "-h"},
                            f"{name}: no argparse flags found — parser moved?")
            accepted[name] = flags

        violations = []
        for name in PY_CALLERS:
            p = REPO / name
            if not p.exists():
                continue
            for binary, flags in python_invocations(p, binaries=set(tools)).items():
                for f in sorted(flags - accepted[binary]):
                    violations.append(f"{name}: '{binary}' does not accept '{f}'")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_shell_callers_pass_only_accepted_flags(self):
        violations = []
        for name in SH_CALLERS:
            p = REPO / name
            if not p.exists():
                continue
            for binary, flags in shell_invocations(p).items():
                for f in sorted(flags - ACCEPTED_FLAGS[binary]):
                    violations.append(f"{name}: '{binary}' does not accept '{f}'")
        self.assertEqual(violations, [], "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
