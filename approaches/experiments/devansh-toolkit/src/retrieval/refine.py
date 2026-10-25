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

from .corpus import LLM_CACHE_DIR

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
        cache = LLM_CACHE_DIR / f"refine_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            return json.loads(cache.read_text(encoding="utf-8"))
        data = structured(prompt, SCHEMA, effort=effort)
        wanted = {r["id"] for r in batch}
        out = {d["id"]: d["keep"] for d in data["decisions"] if d["id"] in wanted}
        LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
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

SUBJECT = """Each item below is a requirement drafted for the product in <spec> (read its product profile too). For every
item, name its SUBJECT: the specific function, device, component, system or feature that must comply (e.g. a named lamp
or signal, a sensor, a marking, the vehicle's behaviour). Then decide from <spec> whether the product has that subject:

- "has": the product has it, or the subject is the product as a whole, its markings, approval documents, samples,
  tests, installation on the vehicle, electrical / electronic parts, or the vehicle behaviour the product provides;
- "possible": the spec or profile says the product may have it, leaves it open or unknown, or it is an optional
  feature or configuration (rules written "where / if / in case ... is used" stay "possible");
- "absent": the subject is a different function, device, component or system that the spec and profile neither list
  nor mention as a possibility, so the product clearly does not have it.

Answer "absent" only when you are sure; when in doubt answer "possible"."""

SUBJECT_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "string"}, "subject": {"type": "string"},
                                     "status": {"type": "string", "enum": ["has", "possible", "absent"]}},
    "required": ["id", "subject", "status"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False}


def subject_check(spec: str, reqs: list[dict], batch_size: int = 30, workers: int = 6, effort: str = "medium") -> dict[str, dict]:
    """id -> {"subject", "status"}: does the product have what the requirement is about? (cached per batch)"""
    from .llm import structured

    ordered = sorted(reqs, key=lambda r: (r["source"]["regulation"], r["source"]["page"], str(r["source"].get("paragraph"))))
    batches = [ordered[i:i + batch_size] for i in range(0, len(ordered), batch_size)]

    def run(batch: list[dict]) -> dict[str, dict]:
        items = "\n".join(f"[{r['id']}] {r['source']['regulation']} para {r['source'].get('paragraph') or '-'}: {r['text']}"
                          for r in batch)
        prompt = f"{SUBJECT}\n\n<spec>\n{spec}\n</spec>\n\n<items>\n{items}\n</items>\n\nAnswer for every item id."
        cache = LLM_CACHE_DIR / f"subject_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            return json.loads(cache.read_text(encoding="utf-8"))
        data = structured(prompt, SUBJECT_SCHEMA, effort=effort)
        wanted = {r["id"] for r in batch}
        out = {d["id"]: {"subject": d["subject"], "status": d["status"]} for d in data["items"] if d["id"] in wanted}
        LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out

    answers: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(run, batches):
            answers.update(part)
    return answers


PAIRS = """A requirements list is matched one to one against an answer key, so an obligation listed twice can only
count once. Below are candidate PAIRS of items (A and B) from the list. For each pair decide:

- "same": A and B state the same obligation (same subject, condition and constraint / value), e.g. because two
  regulations, or two paragraphs of one regulation, state it. Then say which ONE to keep: the copy from the
  regulation that approves the product or device itself rather than a vehicle-level or installation regulation, else
  the more specific and complete wording.
- "general": A (the parent clause) states in general terms exactly what B (its sub-clause) states completely and
  more specifically, so A adds nothing. Keep B.
- "different": anything else: different values, limits, categories, conditions, subjects, or one adds a constraint
  the other lacks; a pointer to a test or table versus that test's own content; two halves of one rule.

Be conservative: when unsure, answer "different"."""

PAIRS_SCHEMA = {"type": "object", "properties": {"pairs": {"type": "array", "items": {
    "type": "object", "properties": {"pair": {"type": "integer"},
                                     "verdict": {"type": "string", "enum": ["same", "general", "different"]},
                                     "keep": {"type": "string", "enum": ["A", "B"]}},
    "required": ["pair", "verdict", "keep"], "additionalProperties": False}}},
    "required": ["pairs"], "additionalProperties": False}


def candidate_pairs(reqs: list[dict], min_jaccard: float = 0.5) -> list[tuple[dict, dict, str]]:
    """(A, B, kind): items of different regulations whose word sets overlap >= min_jaccard ("cross"), and an item at a
    parent paragraph with an item at one of its sub-paragraphs in the same regulation ("parent")."""
    words = {r["id"]: set(norm(r["text"]).split()) for r in reqs}
    out = []
    for i, a in enumerate(reqs):
        for b in reqs[i + 1:]:
            ra, rb = a["source"]["regulation"], b["source"]["regulation"]
            pa, pb = str(a["source"].get("paragraph") or ""), str(b["source"].get("paragraph") or "")
            if ra != rb:
                wa, wb = words[a["id"]], words[b["id"]]
                if wa and wb and len(wa & wb) / len(wa | wb) >= min_jaccard:
                    out.append((a, b, "cross"))
            elif pa and pb and pa != pb:
                if pb.rstrip(".").startswith(pa.rstrip(".") + "."):
                    out.append((a, b, "parent"))
                elif pa.rstrip(".").startswith(pb.rstrip(".") + "."):
                    out.append((b, a, "parent"))
    return out


def merge_pairs(reqs: list[dict], batch_size: int = 40, workers: int = 6, effort: str = "medium") -> tuple[list[dict], list[dict]]:
    """Drop the redundant member of each confirmed pair (never both members of one pair). Returns (kept, decisions)."""
    from .llm import structured

    pairs = candidate_pairs(reqs)
    batches = [pairs[i:i + batch_size] for i in range(0, len(pairs), batch_size)]

    def fmt(r: dict) -> str:
        return f"{r['source']['regulation']} para {r['source'].get('paragraph') or '-'}: {r['text']}"

    def run(batch: list[tuple[dict, dict, str]]) -> list[dict]:
        items = "\n\n".join(f"pair {n}\n  A: {fmt(a)}\n  B: {fmt(b)}" for n, (a, b, _) in enumerate(batch))
        prompt = f"{PAIRS}\n\n<pairs>\n{items}\n</pairs>\n\nDecide every pair."
        cache = LLM_CACHE_DIR / f"pairs_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            answers = json.loads(cache.read_text(encoding="utf-8"))
        else:
            answers = structured(prompt, PAIRS_SCHEMA, effort=effort)["pairs"]
            LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(answers), encoding="utf-8")
        out = []
        for d in answers:
            if 0 <= d["pair"] < len(batch):
                a, b, kind = batch[d["pair"]]
                out.append({"a": a["id"], "b": b["id"], "kind": kind, "verdict": d["verdict"], "keep": d["keep"]})
        return out

    with ThreadPoolExecutor(max_workers=workers) as pool:
        decisions = [d for part in pool.map(run, batches) for d in part]
    drop: set[str] = set()
    for d in decisions:
        if d["verdict"] == "different":
            continue
        keep, lose = (d["b"], d["a"]) if d["verdict"] == "general" or d["keep"] == "B" else (d["a"], d["b"])
        if keep not in drop:
            drop.add(lose)
    return [r for r in reqs if r["id"] not in drop], decisions


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
        cache = LLM_CACHE_DIR / f"rank_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            return json.loads(cache.read_text(encoding="utf-8"))
        data = structured(prompt, RANK_SCHEMA, effort=effort)
        wanted = {r["id"] for r in batch}
        out = {d["id"]: d["confidence"] for d in data["ratings"] if d["id"] in wanted}
        LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
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


RESTATE = """Below is a requirements list extracted from one UN Regulation, each item cited at the paragraph it came from.
A reviewer matches every item one to one with an answer key, so an obligation listed twice can only count once and
the repeat is pure noise. Find the RESTATEMENTS: groups of items that state exactly the same obligation (same subject,
same condition, same constraint or value), typically because the regulation states it once in the main text and
repeats it in an annex, a summary, a test section or a general-requirements paragraph.

NOT restatements (leave them alone):
- items that differ in any value, unit, limit, frequency band, voltage system, category, class, variant or condition;
- an item that points to a test or table ("shall pass the test of Annex 6") and an item that states that test's own
  conditions or pass criteria in detail;
- two halves of one clause (e.g. minimum and maximum, emission and immunity, before and after a test);
- similar wording about different subjects (different lamps, functions, components or markings).

Be conservative: when unsure, do not group. Return only groups of two or more ids."""

RESTATE_SCHEMA = {"type": "object", "properties": {"groups": {"type": "array", "items": {
    "type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}},
    "required": ["ids", "reason"], "additionalProperties": False}}},
    "required": ["groups"], "additionalProperties": False}


def _body_first(r: dict) -> tuple:
    """Which copy of a restated obligation to keep: a numbered main-text paragraph before an annex / appendix one,
    then the earlier page (the place that imposes the obligation, which expert lists cite)."""
    para = str(r["source"].get("paragraph") or "")
    return (para.startswith(("Annex", "Appendix", "Table", "Figure")), r["source"]["page"])


def merge_restatements(reqs: list[dict], max_items: int = 150, workers: int = 6, effort: str = "medium") -> tuple[list[dict], list[dict]]:
    """Drop items that restate another item's obligation within the same regulation (one copy kept, see _body_first).
    Returns (kept, dropped groups). Cached per batch."""
    from .llm import structured

    by_reg: dict[str, list[dict]] = {}
    for r in reqs:
        by_reg.setdefault(r["source"]["regulation"], []).append(r)
    batches = []
    for reg, items in by_reg.items():
        items = sorted(items, key=lambda r: (r["source"]["page"], str(r["source"].get("paragraph"))))
        batches += [(reg, items[i:i + max_items]) for i in range(0, len(items), max_items)]

    def run(job: tuple[str, list[dict]]) -> list[dict]:
        reg, batch = job
        items = "\n".join(f"[{r['id']}] para {r['source'].get('paragraph') or '-'} (page {r['source']['page']}): {r['text']}"
                          for r in batch)
        prompt = f"{RESTATE}\n\n<regulation>{reg}</regulation>\n<items>\n{items}\n</items>"
        cache = LLM_CACHE_DIR / f"restate_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            return json.loads(cache.read_text(encoding="utf-8"))
        wanted = {r["id"] for r in batch}
        out = [{"ids": [i for i in g["ids"] if i in wanted], "reason": g["reason"]}
               for g in structured(prompt, RESTATE_SCHEMA, effort=effort)["groups"]]
        out = [g for g in out if len(set(g["ids"])) > 1]
        LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out

    with ThreadPoolExecutor(max_workers=workers) as pool:
        groups = [g for part in pool.map(run, batches) for g in part]
    by_id = {r["id"]: r for r in reqs}
    order = {r["id"]: n for n, r in enumerate(reqs)}  # ties (same kind, same page): the earlier item in the list
    drop: set[str] = set()
    for g in groups:
        copies = sorted((by_id[i] for i in dict.fromkeys(g["ids"])), key=lambda r: (*_body_first(r), order[r["id"]]))
        drop |= {r["id"] for r in copies[1:]}
        g["kept"] = copies[0]["id"]
    return [r for r in reqs if r["id"] not in drop], groups


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
    ap.add_argument("--skip-rationale", action="store_true",
                    help="drop items cited in a regulation's statement-of-rationale part (before 'II. Text of the Regulation')")
    ap.add_argument("--merge-pairs", action="store_true",
                    help="after refining, drop an item that repeats another regulation's / its sub-clause's obligation")
    ap.add_argument("--subject-check", action="store_true",
                    help="after refining, drop items whose subject (function / device / component) the product clearly lacks")
    ap.add_argument("--merge-restatements", action="store_true",
                    help="after refining, drop items that restate another item's obligation in the same regulation")
    args = ap.parse_args(argv)
    doc = json.loads(args.prediction.read_text(encoding="utf-8"))
    spec = args.spec.read_text(encoding="utf-8")
    if args.mode in ("rank", "scope"):
        refined, report = refine_ranked(spec, doc, args.drop_at_or_below, args.effort,
                                        SCOPE if args.mode == "scope" else None)
    else:
        refined, report = refine(spec, doc, args.effort)
    if args.merge_restatements:
        kept, groups = merge_restatements(refined["requirements"], effort=args.effort)
        report["restatement_groups"] = groups
        report["dropped_as_restatements"] = len(refined["requirements"]) - len(kept)
        report["kept"] = len(kept)
        refined = {**refined, "requirements": kept}
    if args.skip_rationale:
        from .classify import rationale_pages
        start = rationale_pages()
        kept = [r for r in refined["requirements"] if r["source"]["page"] >= start.get(r["source"]["regulation"], 0)]
        report["dropped_as_rationale"] = len(refined["requirements"]) - len(kept)
        report["kept"] = len(kept)
        refined = {**refined, "requirements": kept}
    if args.merge_pairs:
        kept, decisions = merge_pairs(refined["requirements"], effort=args.effort)
        report["pair_decisions"] = decisions
        report["dropped_by_pairs"] = len(refined["requirements"]) - len(kept)
        report["kept"] = len(kept)
        refined = {**refined, "requirements": kept}
    if args.subject_check:
        answers = subject_check(spec, refined["requirements"], effort=args.effort)
        kept = [r for r in refined["requirements"] if answers.get(r["id"], {}).get("status") != "absent"]
        report["subject_absent"] = [{"id": r["id"], "regulation": r["source"]["regulation"],
                                     "paragraph": r["source"].get("paragraph"), "subject": answers[r["id"]]["subject"],
                                     "text": r["text"][:200]} for r in refined["requirements"] if r not in kept]
        report["subject_status"] = {k: sum(a["status"] == k for a in answers.values()) for k in ("has", "possible", "absent")}
        report["kept"] = len(kept)
        refined = {**refined, "requirements": kept}
    for r in refined["requirements"]:  # the official validator rejects texts over 2,000 characters
        if len(r["text"]) > 2000:
            r["text"] = r["text"][:1997].rsplit(" ", 1)[0] + "..."
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(refined, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out.parent / (args.out.stem + "-refine-report.json")).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("refine:", json.dumps({k: v for k, v in report.items() if k not in ("restatement_groups", "subject_absent", "pair_decisions")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
