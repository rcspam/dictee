#!/usr/bin/env python3
"""Aggregate dscore raw outputs (results/raw/*.txt) into a decision matrix.
Filename convention: <cand>__<corpus>__<mode>__<conv>.txt
Parses the OVERALL row of dscore (DER = 1st float, JER = 2nd float).
Writes results/DER-matrix.md and results/DER.tsv.
"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "results", "raw")
OUT_MD = os.path.join(HERE, "results", "DER-matrix.md")
OUT_TSV = os.path.join(HERE, "results", "DER.tsv")

FLOAT = re.compile(r"-?\d+\.\d+")


def parse_overall(path):
    der = jer = None
    for line in open(path):
        if "OVERALL" in line:
            nums = FLOAT.findall(line)
            if nums:
                der = float(nums[0])
                jer = float(nums[1]) if len(nums) > 1 else None
    return der, jer


def main():
    rows = []  # (cand, corpus, mode, conv, der, jer)
    for p in sorted(glob.glob(os.path.join(RAW, "*.txt"))):
        stem = os.path.basename(p)[:-4]
        parts = stem.split("__")
        if len(parts) != 4:
            continue
        cand, corpus, mode, conv = parts
        der, jer = parse_overall(p)
        rows.append((cand, corpus, mode, conv, der, jer))

    with open(OUT_TSV, "w") as f:
        f.write("candidate\tcorpus\tmode\tconvention\tDER\tJER\n")
        for r in rows:
            f.write("\t".join("" if x is None else str(x) for x in r) + "\n")

    corpora = sorted({r[1] for r in rows})
    cands = sorted({r[0] for r in rows})
    lines = ["# Matrice DER — benchmark diarisation", ""]
    for conv in ("dihard", "ami"):
        title = "collar 0 + overlap (DIHARD)" if conv == "dihard" else "collar 0.25 sans overlap (AMI/CALLHOME)"
        for mode in ("auto", "oracle"):
            sub = [r for r in rows if r[3] == conv and r[2] == mode]
            if not sub:
                continue
            lines.append(f"## {title} — mode {mode} (DER %, plus bas = mieux)")
            lines.append("")
            lines.append("| candidat | " + " | ".join(corpora) + " |")
            lines.append("|---|" + "---|" * len(corpora))
            for c in cands:
                cells = []
                for corp in corpora:
                    m = [r for r in sub if r[0] == c and r[1] == corp]
                    cells.append(f"{m[0][4]:.1f}" if m and m[0][4] is not None else "—")
                if any(x != "—" for x in cells):
                    lines.append(f"| {c} | " + " | ".join(cells) + " |")
            lines.append("")

    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {OUT_MD} and {OUT_TSV} ({len(rows)} scored combos)")


if __name__ == "__main__":
    main()
