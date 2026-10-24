"""Write a submission-format predictions file from a pipeline, for the shared benchmark and for uploading.

    python -m retrieval.export                           # uses ../config.json -> ../outputs/predictions.json
    python -m retrieval.export --config retrieval/configs/sel_rules_bm25plus_bigrams.json -n 190 --out ../outputs/x.json

Each of the top-n pooled spec chunks becomes one requirement (clause text, cited at its page + paragraph). This is the
retrieval-only baseline: the requirement text is the regulation clause itself, not yet split into single obligations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .corpus import APPROACH_DIR, DEFAULT_CHALLENGE_DIR
from .pipeline import Pipeline, spec_queries


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(APPROACH_DIR / "config.json"))
    ap.add_argument("--case", default="dev-rear-lamp")
    ap.add_argument("--challenge-dir", default=str(DEFAULT_CHALLENGE_DIR))
    ap.add_argument("--team-id", default="regulation-tl")
    ap.add_argument("-n", type=int, help="number of requirements (default: config 'n', else 190)")
    ap.add_argument("--out", default=str(APPROACH_DIR / "outputs" / "predictions.json"))
    args = ap.parse_args(argv)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    n = args.n or cfg.get("n", 190)
    spec = (Path(args.challenge_dir) / "cases" / args.case / "spec.md").read_text(encoding="utf-8")
    regs = None
    if cfg.get("select"):
        from .regselect import select
        regs = set(select(spec, **cfg["select"]))
    pipe = Pipeline(cfg, regs)
    chosen = [c for c, _ in pipe.pooled(spec_queries(spec), k_per_query=max(400, n))][:n]
    doc = {"team_id": args.team_id, "case_id": args.case, "requirements": [
        {"id": f"R-{i:04d}", "text": " ".join(c.text.split())[:2000], "source": c.cite()}
        for i, c in enumerate(chosen, 1)]}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(chosen)} requirements from {sorted(regs) if regs else 'all regulations'} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
