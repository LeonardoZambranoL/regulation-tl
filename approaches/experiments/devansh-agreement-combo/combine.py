"""Agreement combination of two clause selectors (no new LLM calls).

Keep a requirement when its paragraph was picked by BOTH the per-clause classifier pipeline
(devansh-writer-faithful-ranked) and the deliberate section-by-section selector (devansh-deliberate-faithful-ranked);
when only one picked it, keep it only if the 1-5 ranker rated it 4 or 5 (cut-off fixed in advance).

    python approaches/experiments/devansh-agreement-combo/combine.py [--suffix=-holdout-acpe]
"""
import argparse
import json
import re
from pathlib import Path

X = Path(__file__).resolve().parent.parent


def pk(p):  # official paragraph normalisation (see approaches/benchmarking/challenge_tools/score_local.py)
    t = str(p or "").casefold().replace("§", " ")
    t = re.sub(r"[,;:()\[\]]", " ", t)
    t = re.sub(r"(?<![0-9a-z])\.|\.(?![0-9a-z])", " ", t)
    t = " ".join(t.split())
    return re.sub(r"^(paragraphs?|para|par|section|clause)\s+", "", t) or None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suffix", default="", help='"" for dev-rear-lamp, "-holdout-acpe" for the unseen case')
    ap.add_argument("--min-confidence", type=int, default=4)
    a = ap.parse_args()
    A = json.loads((X / "devansh-writer-faithful-ranked/outputs" / f"predictions{a.suffix}.json").read_text(encoding="utf-8"))
    B = json.loads((X / "devansh-deliberate-faithful-ranked/outputs" / f"predictions{a.suffix}.json").read_text(encoding="utf-8"))
    key = lambda r: (r["source"]["regulation"], pk(r["source"].get("paragraph")))
    pa, pb = {key(r) for r in A["requirements"]}, {key(r) for r in B["requirements"]}
    agreed = pa & pb
    keep = [r for r in A["requirements"] if key(r) in agreed or (r.get("confidence") or 5) >= a.min_confidence]
    keep += [r for r in B["requirements"] if key(r) not in pa and (r.get("confidence") or 5) >= a.min_confidence]
    for i, r in enumerate(keep, 1):
        r["id"] = f"R-{i:04d}"
    out = X / "devansh-agreement-combo/outputs" / f"predictions{a.suffix}.json"
    out.write_text(json.dumps({**A, "requirements": keep}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"agreed paragraphs {len(agreed)}, requirements kept {len(keep)} -> {out.name}")


if __name__ == "__main__":
    main()
