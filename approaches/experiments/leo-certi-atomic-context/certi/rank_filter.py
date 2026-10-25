"""Stage 7 — Expert-likelihood ranking (short item texts only, batched; no clause re-reading).

Every requirement of a predictions file is rated 1-5 ("would an expert list this for this product") against the
Stage 1 product profile. Requirements rated at or above `--min-rating` are kept.

The cut-off is chosen once on the labelled cases (dev-rear-lamp, holdout-acpe) by maximising F2, then applied
unchanged to new cases (see scripts in README "History").

Usage:
    python -m certi.rank_filter --run runs/<run_id> --in outputs/x.json --out outputs/y.json --min-rating 4
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .llm import CachedLLMClient

BATCH = 120
SCHEMA = {
    "type": "object",
    "properties": {
        "ratings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "rating": {"type": "integer"}},
                "required": ["id", "rating"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ratings"],
    "additionalProperties": False,
}


def rate(run_dir: Path, in_path: Path, model: str = "claude-opus-5-5") -> dict[str, int]:
    product = json.loads((run_dir / "stage1_product.json").read_text(encoding="utf-8"))
    reqs = json.loads(in_path.read_text(encoding="utf-8"))["requirements"]
    profile = {
        "product": product["product"],
        "vehicle_categories": product["vehicle_categories"],
        "parts": [{"name": p["name"], "function": p["function"]} for p in product["parts"]],
    }
    llm = CachedLLMClient(use_cache=True)
    batches = [reqs[i : i + BATCH] for i in range(0, len(reqs), BATCH)]

    def one(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload = {
            "product_profile": profile,
            "candidates": [
                {
                    "id": r["id"],
                    "regulation": r["source"]["regulation"],
                    "paragraph": r["source"].get("paragraph", ""),
                    "text": r["text"],
                }
                for r in batch
            ],
        }
        out = llm.call_json(
            stage="stage7_expert_rank",
            model=model,
            prompt_file="stage7_expert_rank_v1.md",
            user_payload=payload,
            schema=SCHEMA,
            max_tokens=8000,
        )
        return out["ratings"]

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(one, batches))
    ratings = {x["id"]: int(x["rating"]) for res in results for x in res}
    print(f"[Stage 7] rated {len(ratings)}/{len(reqs)} | API calls {llm.stats['api_calls']} "
          f"(cache {llm.stats['cache_hits']}) | tokens in/out {llm.stats['input_tokens']}/{llm.stats['output_tokens']}")
    return ratings


def apply_cut(in_path: Path, ratings: dict[str, int], min_rating: int, out_path: Path) -> int:
    doc = json.loads(in_path.read_text(encoding="utf-8"))
    # Unrated items are kept (recall first).
    kept = [r for r in doc["requirements"] if ratings.get(r["id"], 5) >= min_rating]
    for i, r in enumerate(kept, 1):
        r["id"] = f"R-{i:04d}"
    doc["requirements"] = kept
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(kept)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-rating", type=int, default=4)
    ap.add_argument("--model", default="claude-opus-5-5")
    args = ap.parse_args(argv)
    ratings = rate(args.run, args.inp, model=args.model)
    (args.run / "stage7_ratings.json").write_text(json.dumps(ratings, indent=1) + "\n", encoding="utf-8")
    n = apply_cut(args.inp, ratings, args.min_rating, args.out)
    print(f"[Stage 7] kept {n} with rating >= {args.min_rating} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
