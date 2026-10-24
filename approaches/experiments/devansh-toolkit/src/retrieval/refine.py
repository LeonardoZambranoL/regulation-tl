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


RANK = VERIFY.replace(
    "Keep an item only if it is a concrete\nobligation",
    "Rate how confident you are that an item is a concrete\nobligation").replace(
    "keep = false when the item:", "Rate 1 (certainly not) when the item:").replace(
    "keep = true for obligations", "Rate 5 (certainly) for obligations") + """

Rate every item 1-5: 1 = certainly not an obligation for this product, 2 = probably not, 3 = unsure,
4 = probably, 5 = certainly. Use 1 only when you are sure."""

SCOPE = """You are the compliance engineer who writes the requirement list a component supplier receives for the
product in <spec>. Experts in this role list the obligations the product itself must meet and leave out everything
else. Rate each draft item 1-5 for whether an expert would put it on that list (5 = certainly, 1 = certainly not).

Experts LEAVE OUT (rate 1-2):
- conditional variants whose condition is about a feature, option or configuration that <spec> does not state the
  product has (e.g. "where the device has a variable / adjustable / replaceable / movable / interdependent ...",
  "on vehicles whose shape ...", "if the manufacturer chooses ..."), unless the spec says the product has it;
- conformity-of-production and approval-process rules ("shall be manufactured to conform to the approved type",
  sampling, production checks, approval numbers being granted, communication to authorities);
- pure references that only point to other sections ("shall comply with the requirements of sections 5 and 6");
- steps of a laboratory or test procedure (how a sample is prepared, mounted, conditioned or measured) when they
  state no result the product must achieve;
- functions that belong to the vehicle or another system rather than to this product.

Experts KEEP (rate 4-5): construction and marking requirements of the product, its performance values and limits,
its colour / photometric / electrical / mechanical characteristics, test RESULTS it must achieve, its installation
position, number, orientation and visibility on the vehicle, and obligations the product's functions trigger.
Decide from the spec; do not assume features the spec does not mention."""

RANK_SCHEMA = {"type": "object", "properties": {"ratings": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "string"}, "confidence": {"type": "integer", "enum": [1, 2, 3, 4, 5]}},
    "required": ["id", "confidence"], "additionalProperties": False}}},
    "required": ["ratings"], "additionalProperties": False}


def rank(spec: str, reqs: list[dict], batch_size: int = 30, workers: int = 6, effort: str = "medium",
         prompt_text: str | None = None) -> dict[str, int]:
    """id -> confidence 1-5 that it is a real obligation for this product (cached per batch)."""
    from .llm import structured

    ordered = sorted(reqs, key=lambda r: (r["source"]["regulation"], r["source"]["page"], str(r["source"].get("paragraph"))))
    batches = [ordered[i:i + batch_size] for i in range(0, len(ordered), batch_size)]

    def run(batch: list[dict]) -> dict[str, int]:
        items = "\n".join(f"[{r['id']}] {r['source']['regulation']} para {r['source'].get('paragraph') or '-'}: {r['text']}"
                          for r in batch)
        prompt = f"{prompt_text or RANK}\n\n<spec>\n{spec}\n</spec>\n\n<items>\n{items}\n</items>\n\nRate every item id."
        cache = CACHE_DIR / f"rank_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            return json.loads(cache.read_text(encoding="utf-8"))
        data = structured(prompt, RANK_SCHEMA, effort=effort)
        wanted = {r["id"] for r in batch}
        out = {d["id"]: d["confidence"] for d in data["ratings"] if d["id"] in wanted}
        CACHE_DIR.mkdir(exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out

    ratings: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(run, batches):
            ratings.update(part)
    return ratings


def refine_ranked(spec: str, doc: dict, drop_at_or_below: int = 1, effort: str = "medium",
                  prompt_text: str | None = None) -> tuple[dict, dict]:
    """Keep everything except items rated <= drop_at_or_below (default: only "certainly not"); dedupe first.
    The cut-off is fixed in advance, not chosen on a scored case."""
    unique = dedupe(doc["requirements"])
    ratings = rank(spec, unique, effort=effort, prompt_text=prompt_text)
    kept = [r for r in unique if ratings.get(r["id"], 5) > drop_at_or_below]
    hist = {str(k): sum(v == k for v in ratings.values()) for k in range(1, 6)}
    report = {"input": len(doc["requirements"]), "after_dedupe": len(unique), "kept": len(kept),
              "drop_at_or_below": drop_at_or_below, "ratings": hist,
              "kept_if_cutoff": {str(c): sum(ratings.get(r["id"], 5) > c for r in unique) for c in range(0, 4)}}
    for r in kept:
        r.setdefault("confidence", ratings.get(r["id"]))
    return {**doc, "requirements": kept}, report


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
    ap.add_argument("--mode", choices=["verify", "rank", "scope"], default="verify",
                    help="verify: hard keep / drop; rank: rate 1-5 and drop only items rated <= --drop-at-or-below")
    ap.add_argument("--drop-at-or-below", type=int, default=1)
    args = ap.parse_args(argv)
    doc = json.loads(args.prediction.read_text(encoding="utf-8"))
    spec = args.spec.read_text(encoding="utf-8")
    if args.mode in ("rank", "scope"):
        refined, report = refine_ranked(spec, doc, args.drop_at_or_below, args.effort,
                                        SCOPE if args.mode == "scope" else None)
    else:
        refined, report = refine(spec, doc, args.effort)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(refined, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out.parent / (args.out.stem + "-refine-report.json")).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("refine:", json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
