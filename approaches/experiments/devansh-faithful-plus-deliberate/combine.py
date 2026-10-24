"""Final candidate: the faithful-writer requirements, plus the deliberate agent's requirements from paragraphs the
faithful pipeline did not cite (recall), with near-duplicates removed. No new LLM calls.

    python approaches/experiments/devansh-faithful-plus-deliberate/combine.py [--suffix=-holdout-acpe] [--team-id team-11]
"""
import argparse
import json
import sys
from pathlib import Path

X = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(X / "devansh-toolkit" / "src"))
from retrieval.refine import dedupe  # noqa: E402

sys.path.insert(0, str(X.parent / "benchmarking"))
from dashboard_rows import paragraph_key as pk  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suffix", default="")
    ap.add_argument("--team-id", default="team-11")
    a = ap.parse_args()
    A = json.loads((X / "devansh-writer-faithful-ranked/outputs" / f"predictions{a.suffix}.json").read_text(encoding="utf-8"))
    B = json.loads((X / "devansh-deliberate-faithful-ranked/outputs" / f"predictions{a.suffix}.json").read_text(encoding="utf-8"))
    key = lambda r: (r["source"]["regulation"], pk(r["source"].get("paragraph")))
    pa = {key(r) for r in A["requirements"]}
    extra = [r for r in B["requirements"] if key(r) not in pa]
    reqs = dedupe([dict(r) for r in A["requirements"] + extra])
    for i, r in enumerate(reqs, 1):
        r["id"] = f"R-{i:04d}"
        r.pop("confidence", None)  # not part of the submission format
        r["text"] = r["text"][:2000]
    doc = {"team_id": a.team_id, "case_id": A["case_id"], "requirements": reqs}
    out = X / "devansh-faithful-plus-deliberate/outputs" / f"predictions{a.suffix}.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"faithful {len(A['requirements'])} + deliberate-only {len(extra)} -> {len(reqs)} after dedupe -> {out.name}")


if __name__ == "__main__":
    main()
