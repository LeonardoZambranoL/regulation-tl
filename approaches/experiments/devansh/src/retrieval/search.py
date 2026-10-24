"""Try a pipeline by hand: print the top chunks (with citations) for a query.

    python -m retrieval.search "stop lamp luminous intensity" --config bm25 -k 10
    python -m retrieval.search --spec ../industrial-ai-hackathon/cases/dev-rear-lamp/spec.md --config hybrid_rrf -k 30
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import Pipeline, spec_queries

HERE = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", help="free-text query")
    ap.add_argument("--spec", help="a spec.md: generate queries from it and pool the results")
    ap.add_argument("--config", default="bm25", help="config name in retrieval/configs/ or a path (default bm25)")
    ap.add_argument("-k", type=int, default=10)
    ap.add_argument("--json", action="store_true", help="print JSON (citation + text) instead of a listing")
    args = ap.parse_args(argv)
    if not args.query and not args.spec:
        ap.error("give a query or --spec")

    path = Path(args.config) if args.config.endswith(".json") else HERE / "configs" / f"{args.config}.json"
    pipe = Pipeline.from_file(path)
    if args.spec:
        results = pipe.pooled(spec_queries(Path(args.spec).read_text(encoding="utf-8")))[:args.k]
    else:
        results = pipe.search(args.query, args.k)

    if args.json:
        print(json.dumps([{"source": c.cite(), "score": s, "text": c.text} for c, s in results], indent=2, ensure_ascii=False))
        return 0
    for rank, (c, s) in enumerate(results, 1):
        src = c.cite()
        print(f"{rank:>3}. {src['regulation']} v{src['version']} p.{src['page']} {src.get('paragraph') or '':<20} {s:.4f}")
        print("     " + " ".join(c.text.split())[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
