#!/usr/bin/env python3
"""Generate Defaults.js from config/main.xml so the QML reset button always
reflects the source of truth (kcfg defaults) without manual duplication.

Run from the plasmoid/ directory (or anywhere — paths are resolved relative
to this script's location).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


NS = "{http://www.kde.org/standards/kcfg/1.0}"

SCRIPT_DIR = Path(__file__).parent.resolve()
SRC = SCRIPT_DIR / "package" / "contents" / "config" / "main.xml"
DST = SCRIPT_DIR / "package" / "contents" / "ui" / "Defaults.js"


def _format_value(value: str, type_: str) -> str:
    if type_ in ("Int", "UInt"):
        return str(int(value))
    if type_ == "Double":
        return str(float(value))
    if type_ == "Bool":
        return "true" if value.strip().lower() == "true" else "false"
    # String, Path, etc.
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def main() -> int:
    tree = ET.parse(SRC)
    root = tree.getroot()

    entries: list[tuple[str, str]] = []
    for entry in root.iter(f"{NS}entry"):
        name = entry.get("name")
        type_ = entry.get("type") or "String"
        default = entry.find(f"{NS}default")
        if default is None or default.text is None:
            continue
        entries.append((name, _format_value(default.text, type_)))

    lines = [
        "// AUTO-GENERATED — do not edit by hand.",
        "// Regenerate with: plasmoid/gen-defaults.py",
        f"// Source: {SRC.relative_to(SCRIPT_DIR)}",
        ".pragma library",
        "",
        "var defaults = {",
    ]
    lines.extend(f"    {name}: {value}," for name, value in entries)
    lines.append("}")
    lines.append("")

    DST.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(entries)} defaults to {DST.relative_to(SCRIPT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
