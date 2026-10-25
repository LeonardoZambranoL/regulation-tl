"""Stage 8 — Granularity gap fill (deterministic, no LLM).

Experts write one requirement per obligation. On the labelled cases most missed requirements sit in clauses we
already cite, where the clause states more obligations than we extracted. For every cited clause this splits the
verbatim clause text into obligation sentences (certi.syntactic_splitter) and adds each sentence that no existing item
of that clause already covers (token Jaccard below a fixed 0.5).

Usage:
    python -m certi.gap_fill --run runs/<run_id> --in outputs/x.json --out outputs/y.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .syntactic_splitter import UniversalSyntacticObligationSplitter

EXP_DIR = Path(__file__).resolve().parent.parent
CLAUSES_DIR = EXP_DIR.parents[2] / "data-ingestion" / "clauses"
SIM_MAX = 0.5
OBLIGATION = re.compile(r"\b(shall|must)\b", re.I)


def _tokens(t: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", t.lower()))


def _jaccard(a: str, b: str) -> float:
    x, y = _tokens(a), _tokens(b)
    return len(x & y) / len(x | y) if x | y else 0.0


DANGLING = re.compile(r"\b(be|either|with|following|apply|of|to|the|and|or|are|is|shall)\s*[.:;]?$", re.I)


def _fragment(u: str) -> bool:
    """Lead-in fragments and flattened table rows are not stand-alone obligations."""
    toks = u.split()
    numeric = sum(bool(re.fullmatch(r"[\d.,±+\-/°%]+", t)) for t in toks)
    return bool(DANGLING.search(u.rstrip())) or u.rstrip().endswith(":") or numeric > 0.3 * len(toks) or "Table" in u[:40]


def _clause_text(clause_id: str, cache: dict[str, list[dict[str, Any]]]) -> str:
    stem, _, pos = clause_id.rpartition(":")
    if stem not in cache:
        path = CLAUSES_DIR / f"{stem}.json"
        cache[stem] = json.loads(path.read_text(encoding="utf-8"))["clauses"] if path.is_file() else []
    clauses = cache[stem]
    i = int(pos)
    if not 0 <= i < len(clauses):
        return ""
    # Drop the leading paragraph number ("6.1.1. ...").
    return re.sub(r"^\s*\S+\s+", "", clauses[i]["text"].strip(), count=1)


def gap_fill(run_dir: Path, in_path: Path, out_path: Path) -> dict[str, int]:
    rich = json.loads((run_dir / "requirements_rich.json").read_text(encoding="utf-8"))["requirements"]
    clause_of = {(r["source"]["regulation"], str(r["source"].get("paragraph", "")), r["text"]): r.get("clause_id") for r in rich}
    doc = json.loads(in_path.read_text(encoding="utf-8"))
    reqs = doc["requirements"]

    by_clause: dict[str, list[dict[str, Any]]] = {}
    for r in reqs:
        cid = clause_of.get((r["source"]["regulation"], str(r["source"].get("paragraph", "")), r["text"]))
        if cid:
            by_clause.setdefault(cid, []).append(r)

    cache: dict[str, list[dict[str, Any]]] = {}
    added: list[dict[str, Any]] = []
    for cid, items in by_clause.items():
        text = _clause_text(cid, cache)
        if not text:
            continue
        units = UniversalSyntacticObligationSplitter.split(text, regulation=items[0]["source"]["regulation"])
        have = [r["text"] for r in items]
        src = items[0]["source"]
        for u in units:
            u = " ".join(u.split())
            if len(u) < 25 or not OBLIGATION.search(u) or _fragment(u):
                continue
            if max((_jaccard(u, h) for h in have), default=0.0) >= SIM_MAX:
                continue
            have.append(u)
            added.append({"id": "", "text": u, "source": dict(src)})

    out = reqs + added
    for i, r in enumerate(out, 1):
        r["id"] = f"R-{i:04d}"
    doc["requirements"] = out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stats = {"input": len(reqs), "clauses": len(by_clause), "added": len(added), "output": len(out)}
    print(f"[Stage 8] {stats} -> {out_path}")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    gap_fill(args.run, args.inp, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
