"""Verify exact edit boundary, official schemas, and both recorded case fingerprints."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "approaches/benchmarking"))
from challenge_tools.validate import validate, load_index
from check_unseen import missing

index = load_index(ROOT.parent / "industrial-ai-hackathon/regulations/index.json")
ledger = json.loads((HERE / "outputs/decision-ledger.json").read_text())
for filename in ["predictions.json", "predictions-holdout-acpe.json", "submission-heldout-front-bumper.json"]:
    old = json.loads((ROOT / "approaches/experiments/jojo-final-bumper/outputs" / filename).read_text())
    new = json.loads((HERE / "outputs" / filename).read_text())
    assert not validate(new, kind="main", index=index), filename
    assert old.keys() == new.keys() and old["team_id"] == new["team_id"] and old["case_id"] == new["case_id"]
    assert len(old["requirements"]) == len(new["requirements"])
    edits = {e["id"]: e for e in ledger if e["case_id"] == new["case_id"]}
    changed = set()
    for a, b in zip(old["requirements"], new["requirements"]):
        assert a["id"] == b["id"] and a["source"] == b["source"]
        if a["text"] != b["text"]:
            changed.add(a["id"])
            assert edits[a["id"]]["before"] == a["text"] and edits[a["id"]]["after"] == b["text"]
    assert changed == set(edits) and changed
for entry in ledger:
    for source in entry["evidence"]:
        assert hashlib.sha256((ROOT / source["file"]).read_bytes()).hexdigest() == source["file_sha256"]
report = json.loads((HERE / "benchmark-summary.json").read_text())
assert len(report["runs"]) == 2 and not missing(report["runs"], {HERE.name})
for run in report["runs"]:
    doc = json.loads(Path(run["prediction_path"]).read_text())
    digest = hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    assert digest == run["prediction_sha256"]
print("All three schemas, exact edit boundary, source evidence hashes and both current-case runs: OK")
