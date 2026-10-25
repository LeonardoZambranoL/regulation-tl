"""Folder-only staging and secret checks; require full verification when outputs are staged."""
import subprocess
import sys
from pathlib import Path

prefix = "approaches/experiments/jojo-source-repair-v2/"
paths = subprocess.check_output(["git", "diff", "--cached", "--name-only"], text=True).splitlines()
assert paths and all(p.startswith(prefix) and Path(p).name != ".env" for p in paths)
for path in paths:
    assert ("sk" + "-ant-").encode() not in subprocess.check_output(["git", "show", ":" + path])
if any("/outputs/" in p for p in paths):
    subprocess.run([sys.executable, prefix + "verify.py"], check=True)
print("Own-folder staged scope and secret scan: OK")
