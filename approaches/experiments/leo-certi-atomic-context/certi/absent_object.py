"""Stage 11 — Absent-object check (batched LLM over short item texts, on the raw specification and drawing).

Requirements about objects the product does not have (other lamp functions, other vehicle parts, trailers, movable
components ...) almost never match the experts' list: the lamp-function cut removed 162 bumper items holding ~5 % of the
matches. This stage asks the model, with the original specification and drawing (not the derived profile), whether each
requirement concerns an object the product clearly lacks; conditional provisions that could apply are kept.

Usage:
    python -m certi.absent_object --case heldout-front-bumper --in outputs/x.json --out outputs/y.json
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .llm import CachedLLMClient
from .stages.stage0_load import load_stage0

import re

BATCH = 120
PRODUCT_TEST_RX = re.compile(r"\bimpact\b", re.I)
SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "absent": {"type": "boolean"}},
                "required": ["id", "absent"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def absent_ids(case: str, reqs: list[dict[str, Any]], model: str = "claude-opus-5-5") -> set[str]:
    corpus = load_stage0(case)
    llm = CachedLLMClient(use_cache=True)
    batches = [reqs[i : i + BATCH] for i in range(0, len(reqs), BATCH)]

    def one(batch):
        payload = {
            "specification": corpus.spec_text,
            "candidates": [{"id": r["id"], "regulation": r["source"]["regulation"],
                            "paragraph": r["source"].get("paragraph", ""), "text": r["text"]} for r in batch],
        }
        return llm.call_json(stage="stage11_absent", model=model, prompt_file="stage11_absent_object_v1.md",
                             user_payload=payload, schema=SCHEMA, image_path=corpus.image_path, max_tokens=8000)["items"]

    with ThreadPoolExecutor(max_workers=6) as ex:
        res = [x for out in ex.map(one, batches) for x in out]
    print(f"[Stage 11] API calls {llm.stats['api_calls']} (cache {llm.stats['cache_hits']}) | "
          f"tokens in/out {llm.stats['input_tokens']}/{llm.stats['output_tokens']}")
    return {x["id"] for x in res if x["absent"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    doc = json.loads(args.inp.read_text(encoding="utf-8"))
    flagged = absent_ids(args.case, doc["requirements"])
    # Consequences of testing the product itself (e.g. "after the impact test the doors shall open") stay.
    drop = {r["id"] for r in doc["requirements"] if r["id"] in flagged and not PRODUCT_TEST_RX.search(r["text"])}
    kept = [r for r in doc["requirements"] if r["id"] not in drop]
    for i, r in enumerate(kept, 1):
        r["id"] = f"R-{i:04d}"
    doc["requirements"] = kept
    args.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[Stage 11] dropped {len(drop)} absent-object items, kept {len(kept)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
