#!/bin/bash
# uninstall.sh asks before deleting the ONNX models in /usr/share/dictee
# (--keep-models skips the question, the default answer is "no"). The tarball
# installs its models in that same directory (install.sh: MODEL_DIR), so any
# `rm -rf` of the directory itself that runs before the question deletes them
# anyway, prompt and flag notwithstanding. 1.3.7 did exactly that.
#
# Static check: every `rm -rf` before the model prompt may remove things
# INSIDE /usr/share/dictee, never the directory.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

python3 - "$ROOT/uninstall.sh" <<'EOF'
import re, shlex, sys
lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
prompt = next((i for i, l in enumerate(lines) if l.strip() == 'MODEL_DIR="/usr/share/dictee"'), None)
if prompt is None:
    print("FAIL: model prompt (MODEL_DIR=/usr/share/dictee) not found in uninstall.sh")
    sys.exit(1)
bad = []
for n, line in enumerate(lines[:prompt], 1):
    code = line.split("#", 1)[0]
    if "rm -rf" not in code:
        continue
    for tok in shlex.split(code.split("rm -rf", 1)[1]):
        if tok.rstrip("/") in ("/usr/share/dictee", "$MODEL_DIR", "${MODEL_DIR}"):
            bad.append(f"uninstall.sh:{n}: {line.strip()}")
if bad:
    print("FAIL: the models directory is removed before the model prompt:")
    print("\n".join("  " + b for b in bad))
    sys.exit(1)
print("PASS: nothing removes /usr/share/dictee before the model prompt")
EOF
