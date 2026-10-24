"""Refine written requirements for a one-to-one LLM judge: verify each one, drop near-duplicates.

The platform matches each submitted requirement with at most one expert requirement ("same scope, condition and
constraint"). Every requirement that matches nothing costs precision, and on the dev case most of those come from
paragraphs the experts did not list. This step gives every written requirement a second, product-neutral review and
removes repeats, which can never match twice.

    python -m retrieval.refine <predictions.json> --spec <spec.md> --out <refined.json> [--effort medium]

Verifier answers are cached per batch in .cache (key: prompt), so re-runs are free.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .corpus import CACHE_DIR

VERIFY = """You review a draft list of engineering requirements for the product in <spec>, before it is handed to the
supplier's engineers. Each item below was extracted from a UN Regulation clause. Keep an item only if it is a concrete
obligation that the supplier of THIS product must design, build, mark, document for approval, install or test for.

keep = false when the item:
- concerns a function, component, vehicle category or variant the product in <spec> does not have;
- is only a definition, an explanation, a condition without an obligation, or a reference to another clause;
- describes how an authority or technical service works (granting, notifying, numbering approvals, sampling plans);
- is a step of a laboratory test procedure (equipment set-up, measurement method) rather than a result the product
  must achieve;
- repeats an obligation that another item in the list already states.

keep = true for obligations on the product's construction, markings, performance values, durability and test results,
its installation and visibility on the vehicle, its electrical / electronic behaviour, and the documents and samples
the manufacturer must submit. Decide from the spec, not from what products of this kind usually have."""

SCHEMA = {"type": "object", "properties": {"decisions": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "string"}, "keep": {"type": "boolean"}},
    "required": ["id", "keep"], "additionalProperties": False}}},
    "required": ["decisions"], "additionalProperties": False}


def norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9.]+", text.lower()))


def dedupe(reqs: list[dict]) -> list[dict]:
    """Drop requirements whose normalised text repeats one already kept in the same regulation, or whose word set is
    at least 90% the same (Jaccard) as one kept from the same paragraph."""
    kept, seen = [], {}
    for r in reqs:
        key = (r["source"]["regulation"], r["source"].get("paragraph"))
        words = set(norm(r["text"]).split())
        dup = False
        for other in seen.get(key, []):
            if words and len(words & other) / len(words | other) >= 0.9:
                dup = True
                break
        if not dup and any(norm(k["text"]) == norm(r["text"]) for k in kept if k["source"]["regulation"] == r["source"]["regulation"]):
            dup = True
        if not dup:
            kept.append(r)
            seen.setdefault(key, []).append(words)
    return kept


def verify(spec: str, reqs: list[dict], batch_size: int = 30, workers: int = 6, effort: str = "medium") -> dict[str, bool]:
    from .llm import structured

    # keep neighbouring requirements (same regulation, close paragraphs) in one batch so repeats are visible together
    ordered = sorted(reqs, key=lambda r: (r["source"]["regulation"], r["source"]["page"], str(r["source"].get("paragraph"))))
    batches = [ordered[i:i + batch_size] for i in range(0, len(ordered), batch_size)]

    def run(batch: list[dict]) -> dict[str, bool]:
        items = "\n".join(f"[{r['id']}] {r['source']['regulation']} para {r['source'].get('paragraph') or '-'}: {r['text']}"
                          for r in batch)
        prompt = f"{VERIFY}\n\n<spec>\n{spec}\n</spec>\n\n<items>\n{items}\n</items>\n\nDecide every item id."
        cache = CACHE_DIR / f"refine_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            return json.loads(cache.read_text(encoding="utf-8"))
        data = structured(prompt, SCHEMA, effort=effort)
        wanted = {r["id"] for r in batch}
        out = {d["id"]: d["keep"] for d in data["decisions"] if d["id"] in wanted}
        CACHE_DIR.mkdir(exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out

    decisions: dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(run, batches):
            decisions.update(part)
    return decisions


def refine(spec: str, doc: dict, effort: str = "medium") -> tuple[dict, dict]:
    reqs = doc["requirements"]
    unique = dedupe(reqs)
    decisions = verify(spec, unique, effort=effort)
    kept = [r for r in unique if decisions.get(r["id"], True)]  # undecided items are kept (recall first)
    report = {"input": len(reqs), "after_dedupe": len(unique), "kept": len(kept),
              "dropped_by_verifier": len(unique) - len(kept)}
    return {**doc, "requirements": kept}, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prediction", type=Path)
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--effort", default="medium")
    args = ap.parse_args(argv)
    doc = json.loads(args.prediction.read_text(encoding="utf-8"))
    refined, report = refine(args.spec.read_text(encoding="utf-8"), doc, args.effort)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(refined, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out.parent / (args.out.stem + "-refine-report.json")).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("refine:", json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
