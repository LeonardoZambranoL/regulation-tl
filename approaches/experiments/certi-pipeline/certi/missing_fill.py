"""Stage 8 — Missing-obligation fill (LLM, cited clauses only).

Most requirements we miss on the labelled cases sit in clauses we already cite: the clause states more obligations than
we extracted. For every cited clause, the model sees the verbatim clause text and our existing items and returns only
the obligations that are not covered yet. New items keep the clause's citation.

Usage:
    python -m certi.missing_fill --run runs/<run_id> --in outputs/x.json --out outputs/y.json
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .gap_fill import _clause_text
from .llm import CachedLLMClient

BATCH_CHARS = 24000
SCHEMA = {
    "type": "object",
    "properties": {
        "missing": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"clause": {"type": "string"}, "text": {"type": "string"}},
                "required": ["clause", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["missing"],
    "additionalProperties": False,
}


def missing_fill(run_dir: Path, in_path: Path, out_path: Path, model: str = "claude-sonnet-5-5") -> dict[str, int]:
    rich = json.loads((run_dir / "requirements_rich.json").read_text(encoding="utf-8"))["requirements"]
    product = json.loads((run_dir / "stage1_product.json").read_text(encoding="utf-8"))
    clause_of = {(r["source"]["regulation"], str(r["source"].get("paragraph", "")), r["text"]): r.get("clause_id") for r in rich}
    doc = json.loads(in_path.read_text(encoding="utf-8"))
    reqs = doc["requirements"]

    by_clause: dict[str, list[dict[str, Any]]] = {}
    for r in reqs:
        cid = clause_of.get((r["source"]["regulation"], str(r["source"].get("paragraph", "")), r["text"]))
        if cid:
            by_clause.setdefault(cid, []).append(r)

    cache: dict[str, list[dict[str, Any]]] = {}
    entries = []
    for cid, items in by_clause.items():
        text = _clause_text(cid, cache)
        if text:
            entries.append({"clause": cid, "regulation": items[0]["source"]["regulation"],
                            "clause_text": text[:4000], "existing": [r["text"] for r in items]})

    batches, cur, size = [], [], 0
    for e in entries:
        n = len(json.dumps(e, ensure_ascii=False))
        if cur and size + n > BATCH_CHARS:
            batches.append(cur)
            cur, size = [], 0
        cur.append(e)
        size += n
    if cur:
        batches.append(cur)

    profile = {"product": product["product"], "vehicle_categories": product["vehicle_categories"],
               "parts": [p["name"] for p in product["parts"]]}
    llm = CachedLLMClient(use_cache=True)

    def one(batch):
        return llm.call_json(stage="stage8_missing", model=model, prompt_file="stage8_missing_obligations_v1.md",
                             user_payload={"product_profile": profile, "clauses": batch}, schema=SCHEMA,
                             max_tokens=12000)["missing"]

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(one, batches))

    added = []
    for res in results:
        for m in res:
            items = by_clause.get(m["clause"])
            if items and m["text"].strip():
                added.append({"id": "", "text": " ".join(m["text"].split()), "source": dict(items[0]["source"])})

    out = reqs + added
    for i, r in enumerate(out, 1):
        r["id"] = f"R-{i:04d}"
    doc["requirements"] = out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stats = {"input": len(reqs), "clauses": len(entries), "batches": len(batches), "added": len(added), "output": len(out)}
    print(f"[Stage 8] {stats} | API calls {llm.stats['api_calls']} (cache {llm.stats['cache_hits']}) | "
          f"tokens in/out {llm.stats['input_tokens']}/{llm.stats['output_tokens']} -> {out_path}")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    args = ap.parse_args(argv)
    missing_fill(args.run, args.inp, args.out, model=args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
