"""Source-faithfulness repair. Reads only inherited predictions and source clauses, never gold."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "approaches/experiments/jojo-final-bumper/outputs"
FILES = ["predictions.json", "predictions-holdout-acpe.json", "submission-heldout-front-bumper.json"]


def norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def evidence(regulation, paragraph, page):
    """Resolve a unique clause by regulation, normalized paragraph AND cited page."""
    filename = regulation.replace(" ", "_") + "_base.json"
    path = ROOT / "data-ingestion/clauses" / filename
    doc = json.loads(path.read_text())
    clauses = [c for c in doc["clauses"] if norm(c["paragraph"]) == norm(paragraph) and page in c["pages"]]
    assert len(clauses) == 1, (filename, paragraph, page, len(clauses))
    return {"file": str(path.relative_to(ROOT)), "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "regulation": regulation, "paragraph": clauses[0]["paragraph"], "pages": clauses[0]["pages"],
            "text": clauses[0]["text"]}


def main():
    rules = json.loads((HERE / "rules.json").read_text())
    pins = json.loads((HERE / "inputs.json").read_text())
    for filename, digest in json.loads((HERE / "source-pins.json").read_text()).items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == digest, "Source changed; review before rerunning"
    output = HERE / "outputs"
    output.mkdir(exist_ok=True)
    ledger, summary = [], {}
    for filename in FILES:
        path = SOURCE / filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pins[filename], "Input changed; review before rerunning"
        doc = json.loads(path.read_text())
        changes = []
        for row in doc["requirements"]:
            old = row["text"]
            applied = []
            for rule in rules:
                src = row["source"]
                if src["regulation"] != rule["regulation"] or norm(src.get("paragraph")) != norm(rule["paragraph"]):
                    continue
                if not re.search(rule["match"], old, re.I):
                    continue
                if rule.get("exclude") and re.search(rule["exclude"], old, re.I):
                    continue
                proof = [evidence(rule["regulation"], ref["paragraph"], ref["page"]) for ref in rule["evidence"]]
                if rule["operation"] == "prefix":
                    new = rule["text"] + old[0].lower() + old[1:]
                elif rule["operation"] == "append":
                    new = old.rstrip(".") + rule["text"]
                else:
                    new = rule["text"]
                applied.append((rule, new, proof))
            assert len(applied) <= 1, (filename, row["id"], "overlapping rules")
            if applied:
                rule, new, proof = applied[0]
                assert new != old and 0 < len(new) <= 2000
                row["text"] = new
                entry = {"case_id": doc["case_id"], "id": row["id"], "rule": rule["name"],
                         "source": row["source"], "before": old, "after": new,
                         "reason": rule["reason"], "evidence": proof}
                ledger.append(entry)
                changes.append(row["id"])
        assert changes, "Each case must contain a substantive repair"
        assert all(set(r) == {"id", "text", "source"} for r in doc["requirements"])
        target = output / filename
        target.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        summary[doc["case_id"]] = {"input_items": len(doc["requirements"]), "output_items": len(doc["requirements"]),
                                  "changed_text_count": len(changes), "changed_ids": changes,
                                  "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    (output / "decision-ledger.json").write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n")
    (output / "run-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
