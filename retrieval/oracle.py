"""Where is accuracy lost? Ceiling experiments that "cheat" with the gold answer to measure what each pipeline stage is
worth before we build it.

    python -m retrieval.oracle                       # default: bm25+ bigrams on clauses, dev-rear-lamp
    python -m retrieval.oracle --config tfidf_char -n 190

  A  retrieval only (what we have)
  B  + perfect regulation selection           -> value of a regulation-selection step
  C  B with a bigger budget (2N)               -> recall vs precision trade-off
  D  B, keeping only clauses that say "shall"  -> value of a cheap obligation filter
  E  perfect regulations + EVERY "shall" clause, no retrieval at all
     -> if req_R_max is 1.0, the remaining problem is choosing among these clauses, not searching
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .bench import HERE, official_scorer, pages_of, para_key
from .corpus import DEFAULT_CHALLENGE_DIR
from .pipeline import Pipeline, spec_queries


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="bm25plus_bigrams")
    ap.add_argument("--case", default="dev-rear-lamp")
    ap.add_argument("--challenge-dir", default=str(DEFAULT_CHALLENGE_DIR))
    ap.add_argument("-n", type=int, default=190, help="submission size")
    args = ap.parse_args(argv)

    case_dir = Path(args.challenge_dir) / "cases" / args.case
    gold = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))["requirements"]
    spec = (case_dir / "spec.md").read_text(encoding="utf-8")
    score = official_scorer(Path(args.challenge_dir))
    pipe = Pipeline.from_file(HERE / "configs" / f"{args.config}.json")
    ranked = [c for c, _ in pipe.pooled(spec_queries(spec), k_per_query=max(400, 2 * args.n))]
    gold_regs = {g["source"]["regulation"] for g in gold}
    shall = re.compile(r"\bshall\b")

    def report(tag: str, chosen) -> None:
        sub = {"requirements": [{"id": str(i), "text": "-", "source": c.cite()} for i, c in enumerate(chosen)]}
        res = score(sub, {"requirements": gold})
        pages = {(c.regulation, p) for c in chosen for p in pages_of(c)}
        paras = {(c.regulation, para_key(c.paragraph)) for c in chosen}
        reach = sum((g["source"]["regulation"], g["source"]["page"]) in pages or
                    (g["source"]["regulation"], para_key(g["source"].get("paragraph"))) in paras for g in gold) / len(gold)
        rl, pl = res["regulation_level"], res["page_level"]
        print(f"{tag:<52} reg F1 {rl['f1']:.2f} | page P {pl['precision']:.2f} R {pl['recall']:.2f} F1 {pl['f1']:.2f} "
              f"| req_R_max {reach:.2f} | n={len(chosen)}")

    in_gold = [c for c in ranked if c.regulation in gold_regs]
    n = args.n
    report("A  retrieval only", ranked[:n])
    report("B  + perfect regulation selection", in_gold[:n])
    report(f"C  + perfect regulation selection, n={2 * n}", in_gold[:2 * n])
    report("D  + perfect regs, only 'shall' clauses", [c for c in in_gold if shall.search(c.text)][:n])
    report("E  perfect regs, ALL 'shall' clauses, no retrieval",
           [c for c in pipe.chunks if c.regulation in gold_regs and shall.search(c.text)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
