"""Deliberate clause selection: an agent reads each section of a regulation as a whole and picks the exact clauses.

The per-clause classifier judges 40 unrelated clauses at a time, each without its section around it, so it cannot see
that the obligation sits in a child clause and not in its heading, or that a conditional branch concerns a feature the
spec never mentions. Here every call gets ONE section (all its clauses in document order, with their numbers, so the
tree of parents, children and siblings is visible), the full spec, and thinks before choosing (adaptive thinking,
effort high by default). It returns the chosen clause ids with a one-line reason each.

    python -m retrieval.deliberate --case dev-rear-lamp            # prints how many clauses it picks per regulation

Cached per section prompt in .cache/, so re-runs are free.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .corpus import CACHE_DIR, DEFAULT_CHALLENGE_DIR, REPO_ROOT, Chunk, load_corpus

PROMPT = """You are the compliance engineer who writes the requirement list that the supplier of the product in <spec>
receives. You are reading ONE section of a UN Regulation that applies to this product. Choose the exact numbered clauses
from which you would write the product's requirements.

Think it through first:
- Which of the product's functions, components and variants does this section concern? Which features does the spec
  actually state (and which does it not mention)?
- Where exactly is each obligation stated? Choose the MOST SPECIFIC clause that carries it: the child that states the
  value, number, angle, colour, marking or test result, not the heading above it. Choose a parent clause only when the
  obligation is written in the parent's own text. A clause can state an obligation without "shall" (e.g.
  "Number: two", "In height: not less than 250 mm", "... is not permitted", "Apply the test pulses ...").
- Leave out: clauses for functions, components, vehicle categories or variants the product does not have; conditional
  branches whose condition is a feature or option the spec does not state; definitions; headings and scope lines
  without their own obligation; pure references to other sections; conformity-of-production, sampling and approval
  procedures and authorities' duties; steps of how a laboratory performs a test when they state no result the product
  must achieve; functions of the vehicle or another system rather than this product.
- Keep: construction and marking requirements of the product, its performance values and limits, colour, photometric,
  electrical, mechanical and durability characteristics, test results it must achieve, its installation position,
  number, orientation and visibility on the vehicle, and obligations its functions trigger.

Choose as many or as few clauses as the section really contains for this product (often none). Give each chosen id a
one-line reason."""

SCHEMA = {"type": "object", "properties": {"chosen": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "integer"}, "reason": {"type": "string"}},
    "required": ["id", "reason"], "additionalProperties": False}}},
    "required": ["chosen"], "additionalProperties": False}


def section_key(c: Chunk) -> str:
    """Group clauses into sections: body paragraphs by their first two number levels ("6.7"), annex text by annex + part
    + first number. Clauses without a number stay with the preceding section."""
    p = (c.paragraph or "").strip()
    m = re.match(r"^(annex \S+(?: part \S+)?)\s*(\d+)?", p, re.IGNORECASE)
    if m:
        return f"{m.group(1)} {m.group(2) or ''}".strip()
    nums = re.findall(r"\d+", p)
    return ".".join(nums[:2]) if nums else ""


def sections(regulations: set[str], max_clauses: int = 45) -> list[list[Chunk]]:
    """Ordered clause groups of the selected regulations, long sections split into windows of max_clauses."""
    groups: OrderedDict[tuple[str, str], list[Chunk]] = OrderedDict()
    last: dict[str, str] = {}
    for c in load_corpus("paragraph", "clauses"):
        if c.regulation not in regulations or not c.text.strip():
            continue
        key = section_key(c) or last.get(c.regulation, "")
        last[c.regulation] = key
        groups.setdefault((c.regulation, key), []).append(c)
    # pack consecutive sections of one regulation into windows of up to max_clauses (a section is split only when it
    # alone is longer), so every call sees whole sections in document order without hundreds of tiny calls
    out: list[list[Chunk]] = []
    window: list[Chunk] = []
    for chunks in groups.values():
        parts = [chunks[i:i + max_clauses] for i in range(0, len(chunks), max_clauses)]
        for part in parts:
            if window and (window[0].regulation != part[0].regulation or len(window) + len(part) > max_clauses):
                out.append(window)
                window = []
            window = window + part
    if window:
        out.append(window)
    return out


def _prompt(spec: str, chunks: list[Chunk]) -> str:
    keys = list(dict.fromkeys(section_key(c) or "preamble" for c in chunks))
    head = f"{chunks[0].regulation} ({chunks[0].title}), section(s) {', '.join(keys)}"
    body = "\n\n".join(f"[{c.id}] para {c.paragraph or '-'} (page {c.page})\n{' '.join(c.text.split())[:1200]}" for c in chunks)
    return f"{PROMPT}\n\n<spec>\n{spec}\n</spec>\n\n<section>\n{head}\n\n{body}\n</section>"


def select_clauses(spec: str, regulations: set[str], effort: str = "high", workers: int = 6) -> tuple[list[Chunk], dict]:
    """The chosen clauses in document order, and {chunk id: reason}."""
    from .llm import structured

    groups = sections(regulations)

    def run(chunks: list[Chunk]) -> dict[int, str]:
        prompt = _prompt(spec, chunks)
        cache = CACHE_DIR / f"deliberate_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            return {int(k): v for k, v in json.loads(cache.read_text(encoding="utf-8")).items()}
        data = structured(prompt, SCHEMA, effort=effort, max_tokens=32000)
        wanted = {c.id for c in chunks}
        out = {d["id"]: d["reason"] for d in data["chosen"] if d["id"] in wanted}
        CACHE_DIR.mkdir(exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out

    reasons: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(run, groups):
            reasons.update(part)
    chosen = [c for g in groups for c in g if c.id in reasons]
    return chosen, reasons


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default="dev-rear-lamp")
    ap.add_argument("--challenge-dir", default=str(DEFAULT_CHALLENGE_DIR))
    ap.add_argument("--select", default="combined")
    ap.add_argument("--effort", default="high")
    args = ap.parse_args(argv)
    from .regselect import select
    case_dir = next(d for d in (Path(args.challenge_dir) / "cases" / args.case,
                                REPO_ROOT / "approaches" / "benchmarking" / "cases" / args.case) if d.is_dir())
    spec = (case_dir / "spec.md").read_text(encoding="utf-8")
    regs = set(select(spec, args.select))
    groups = sections(regs)
    print(f"{len(groups)} sections, {sum(map(len, groups))} clauses in {sorted(regs)}")
    chosen, _ = select_clauses(spec, regs, args.effort)
    per = {}
    for c in chosen:
        per[c.regulation] = per.get(c.regulation, 0) + 1
    print(f"chosen {len(chosen)} clauses: {per}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
