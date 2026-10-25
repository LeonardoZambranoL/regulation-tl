"""Stage 9 — Restatement merge (one LLM call per regulation; drops duplicates only).

Requirements are matched one to one, so a second copy of the same obligation can never match and only lowers precision.
The model groups items of one regulation that state exactly the same obligation; from each group we keep the copy at a
main-text paragraph (not annex / appendix / table), else the one on the earliest page.

Usage:
    python -m certi.restatement_merge --in outputs/x.json --out outputs/y.json
"""

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .llm import CachedLLMClient

SCHEMA = {
    "type": "object",
    "properties": {"groups": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}},
    "required": ["groups"],
    "additionalProperties": False,
}
SECONDARY = re.compile(r"\b(annex|appendix|table|figure)\b", re.I)


def _rank(r: dict[str, Any]) -> tuple[int, int, str]:
    para = str(r["source"].get("paragraph", ""))
    return (1 if SECONDARY.search(para) else 0, int(r["source"].get("page", 0)), r["id"])


def merge(reqs: list[dict[str, Any]], model: str = "claude-opus-5-5") -> tuple[list[dict[str, Any]], list[list[str]]]:
    by_reg: dict[str, list[dict[str, Any]]] = {}
    for r in reqs:
        by_reg.setdefault(r["source"]["regulation"], []).append(r)
    llm = CachedLLMClient(use_cache=True)

    def one(items: list[dict[str, Any]]) -> list[list[str]]:
        if len(items) < 2:
            return []
        payload = {"items": [{"id": r["id"], "paragraph": r["source"].get("paragraph", ""), "text": r["text"]} for r in items]}
        return llm.call_json(stage="stage9_restatement", model=model, prompt_file="stage9_restatement_merge_v1.md",
                             user_payload=payload, schema=SCHEMA, max_tokens=8000)["groups"]

    with ThreadPoolExecutor(max_workers=8) as ex:
        groups = [g for res in ex.map(one, by_reg.values()) for g in res]
    by_id = {r["id"]: r for r in reqs}
    drop: set[str] = set()
    for g in groups:
        members = [by_id[i] for i in dict.fromkeys(g) if i in by_id]
        if len(members) < 2:
            continue
        keep = min(members, key=_rank)
        drop |= {m["id"] for m in members if m is not keep}
    print(f"[Stage 9] {len(groups)} groups, dropping {len(drop)} restatements | API calls {llm.stats['api_calls']} "
          f"(cache {llm.stats['cache_hits']}) | tokens in/out {llm.stats['input_tokens']}/{llm.stats['output_tokens']}")
    return [r for r in reqs if r["id"] not in drop], groups


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default="claude-opus-5-5")
    args = ap.parse_args(argv)
    doc = json.loads(args.inp.read_text(encoding="utf-8"))
    kept, _ = merge(doc["requirements"], model=args.model)
    for i, r in enumerate(kept, 1):
        r["id"] = f"R-{i:04d}"
    doc["requirements"] = kept
    args.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[Stage 9] kept {len(kept)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
