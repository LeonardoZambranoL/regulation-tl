"""Stage 10 — Same-paragraph duplicate removal (deterministic).

Requirements are matched one to one, so a copy of an item at the same paragraph can never match. Within one
(regulation, paragraph), an item is dropped when its normalised text equals an earlier item's. (Near-copies are kept: on
holdout-acpe the experts wrote two requirements at one paragraph where our two items were near-copies.)

Usage:
    python -m certi.dedup_same_paragraph --in outputs/x.json --out outputs/y.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

def _words(t: str) -> set[str]:
    return set(re.findall(r"[a-z]+", t.lower()))


def _numbers(t: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", t))


def dedup(reqs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in reqs:
        key = (r["source"]["regulation"], str(r["source"].get("paragraph", "")).strip().rstrip(".").lower())
        norm = " ".join(r["text"].lower().split())
        dup = False
        for k in seen.get(key, []):
            if norm == " ".join(k["text"].lower().split()):
                dup = True
                break
        (dropped if dup else kept).append(r)
        if not dup:
            seen.setdefault(key, []).append(r)
    return kept, dropped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    doc = json.loads(args.inp.read_text(encoding="utf-8"))
    kept, dropped = dedup(doc["requirements"])
    for i, r in enumerate(kept, 1):
        r["id"] = f"R-{i:04d}"
    doc["requirements"] = kept
    args.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[Stage 10] dropped {len(dropped)} same-paragraph duplicates, kept {len(kept)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
