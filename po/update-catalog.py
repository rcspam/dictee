#!/usr/bin/env python3
"""Regenerate po/dictee.pot from the Python UIs, merge it into every
language and compile the .mo files.

xgettext 0.21 does not look inside f-strings, so a _('...') written there
never reached the catalog: the Python parser finds those calls and they are
appended to the pot. Merging runs without fuzzy matching: a new string stays
untranslated until someone translates it, rather than borrowing an unrelated
neighbour's translation.

Run from anywhere: python3 po/update-catalog.py
"""
import ast
import os
import subprocess
import sys
import tempfile

PO_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PO_DIR)
SOURCES = ["dictee-setup.py", "dictee-tray.py", "dictee-transcribe.py"]
KEYWORDS = ("_", "N_")
LANGS = ["de", "es", "fr", "it", "pt", "uk"]
POT = os.path.join(PO_DIR, "dictee.pot")


def _marked_calls(path):
    """(msgid, line) of every _("literal") / N_("literal") in the file,
    f-strings included."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in KEYWORDS and len(node.args) == 1
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value):
            yield node.args[0].value, node.lineno


def code_msgids():
    """msgid -> [file:line, ...] for all the sources."""
    found = {}
    for name in SOURCES:
        for msgid, line in _marked_calls(os.path.join(ROOT, name)):
            found.setdefault(msgid, []).append(f"{name}:{line}")
    return found


def pot_msgids(path):
    """The msgids of a .pot / .po file, header excluded."""
    ids, current, in_id = set(), None, False
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if line.startswith("#"):
                continue
            if line.startswith("msgid "):
                current, in_id = ast.literal_eval(line[6:]), True
            elif line.startswith('"') and in_id:
                current += ast.literal_eval(line)
            else:
                if in_id and current:
                    ids.add(current)
                in_id = False
        if in_id and current:
            ids.add(current)
    return ids


def _po_quote(text):
    return '"' + (text.replace("\\", "\\\\").replace('"', '\\"')
                  .replace("\n", "\\n").replace("\t", "\\t")) + '"'


def main():
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "xgettext.pot")
        subprocess.run(
            ["xgettext", "--language=Python", "--from-code=UTF-8",
             *[f"-k{k}" for k in KEYWORDS], "--add-comments=xgettext",
             "--package-name=dictee", "--package-version=1.4",
             "-o", base, *SOURCES], cwd=ROOT, check=True)
        extracted = pot_msgids(base)
        extra = {m: refs for m, refs in code_msgids().items()
                 if m not in extracted}
        sources = [base]
        if extra:
            supplement = os.path.join(tmp, "fstrings.pot")
            with open(supplement, "w", encoding="utf-8") as f:
                f.write('msgid ""\nmsgstr ""\n'
                        '"Content-Type: text/plain; charset=UTF-8\\n"\n\n')
                for msgid in sorted(extra):
                    f.write(f"#: {' '.join(extra[msgid])}\n"
                            f"msgid {_po_quote(msgid)}\nmsgstr \"\"\n\n")
            sources.append(supplement)
        subprocess.run(["msgcat", "--use-first", "-o", POT, *sources],
                       check=True)
    for lang in LANGS:
        po = os.path.join(PO_DIR, f"{lang}.po")
        subprocess.run(["msgmerge", "--quiet", "--no-fuzzy-matching",
                        "--update", "--backup=none", po, POT], check=True)
        subprocess.run(["msgfmt", "--check", "-o",
                        os.path.join(PO_DIR, f"{lang}.mo"), po], check=True)
        stats = subprocess.run(
            ["msgfmt", "--statistics", "-o", os.devnull, po],
            capture_output=True, text=True,
            env=dict(os.environ, LC_ALL="C", LANGUAGE="")).stderr.strip()
        print(f"{lang}: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
