"""Check staged scope/secrets plus the final artifact and both recorded case runs."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREFIX = "approaches/experiments/jojo-final-bumper/"
sys.path.insert(0, str(ROOT / "approaches/benchmarking"))
from challenge_tools.validate import read_submission, validate, load_index
from check_unseen import missing

paths = subprocess.check_output(["git", "diff", "--cached", "--name-only"], text=True).splitlines()
assert paths and all(p.startswith(PREFIX) and Path(p).name != ".env" for p in paths), "staged paths outside our folder"
secret_prefix = "sk" + "-ant-"
for path in paths:
    content = subprocess.check_output(["git", "show", ":" + path])
    assert secret_prefix.encode() not in content, f"credential-like content in {path}"
index = load_index(ROOT.parent / "industrial-ai-hackathon/regulations/index.json")
for name in ["submission-heldout-front-bumper.json", "fallback-heldout-front-bumper.json", "predictions.json", "predictions-holdout-acpe.json"]:
    doc = read_submission(HERE / "outputs" / name)
    assert not validate(doc, kind="main", index=index), name
runs = json.loads((HERE / "benchmark-summary.json").read_text())["runs"]
assert len(runs) == 2 and not missing(runs, {HERE.name})
print("Own-folder scope, secret scan, four validations and both case runs: OK")
