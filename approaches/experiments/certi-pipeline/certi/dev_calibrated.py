"""Submission-only step — dev-calibrated clause judgment for regulations shared with the worked example.

USES THE DEV ANSWER KEY (cases/dev-rear-lamp/expected.json) AS TRAINING DATA. The competition provides it "so you can
calibrate"; the team rule in AGENTS.md ("uses_gold must stay false") forbids it for benchmarked experiments, so this step
is NOT part of the benchmarked pipeline and its output must never be scored on dev-rear-lamp (it would be circular).

Idea: for general clauses of a regulation that the worked example also used (marking composition, measurement
conditions, fitting conventions, EMC), the experts' judgment does not depend on the product. Among items of shared
regulations, keep those whose clause the experts listed on dev, plus items specific to a lamp function present in this
product (the dev case had other functions, so there is no evidence about them). Drop the rest.

Usage:
    python -m certi.dev_calibrated --case heldout-front-bumper --in outputs/x.json --out outputs/y.json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any

from .lamp_functions import named_functions, present_functions, section_heading

EXP_DIR = Path(__file__).resolve().parent.parent
DEV_GOLD = EXP_DIR.parents[3] / "industrial-ai-hackathon" / "cases" / "dev-rear-lamp" / "expected.json"
sys.path.insert(0, str(EXP_DIR.parents[1] / "benchmarking"))
from challenge_tools.score_local import _paragraph_key  # noqa: E402


def clause_key(source: dict[str, Any]) -> tuple[str, str]:
    return source["regulation"], _paragraph_key(str(source.get("paragraph", "")))


def dev_clause_counts() -> collections.Counter:
    gold = json.loads(DEV_GOLD.read_text(encoding="utf-8"))["requirements"]
    return collections.Counter(clause_key(r["source"]) for r in gold)


def calibrate(case: str, reqs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    counts = dev_clause_counts()
    shared = {reg for reg, _ in counts}
    present = {k for k, v in present_functions(case).items() if v["present"]}
    kept, dropped = [], []
    for r in reqs:
        s = r["source"]
        reg = s["regulation"]
        if reg not in shared or clause_key(s) in counts:
            kept.append(r)
            continue
        functions = named_functions(r["text"]) | named_functions(section_heading(reg, s.get("paragraph", "")))
        if functions & present or "part c" in str(s.get("paragraph", "")).lower():
            kept.append(r)
        else:
            dropped.append(r)
    return kept, dropped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.case == "dev-rear-lamp":
        raise SystemExit("dev_calibrated must not be applied to the case whose answer key it learns from")
    doc = json.loads(args.inp.read_text(encoding="utf-8"))
    kept, dropped = calibrate(args.case, doc["requirements"])
    for i, r in enumerate(kept, 1):
        r["id"] = f"R-{i:04d}"
    doc["requirements"] = kept
    args.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[dev-calibrated] dropped {len(dropped)}, kept {len(kept)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
