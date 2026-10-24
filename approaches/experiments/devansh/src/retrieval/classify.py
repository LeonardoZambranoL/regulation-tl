"""LLM clause classifier: which clauses of the selected regulations apply to this product?

The oracle showed that with the right regulations every gold requirement is among their "shall" clauses, so the task
after regulation selection is choosing among about 1,200 clauses. Claude reads them in batches with the spec and returns
applies / does not apply. Decisions are cached per batch in .cache/, so reruns cost nothing.

    python -m retrieval.classify                      # dev case, rules selection, prints kept counts and scores
    python -m retrieval.classify --select llm --workers 8
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .corpus import CACHE_DIR, DEFAULT_CHALLENGE_DIR, Chunk, load_corpus

SHALL = re.compile(r"\b(shall|must)\b", re.IGNORECASE)

INSTRUCTIONS = """You are a UNECE type-approval engineer. A supplier builds the product in <spec> and needs every engineering
requirement it must fulfil under the selected UN Regulations. For each numbered clause below decide whether it states a
requirement that this product (the device itself, its markings, its installation on the vehicle, its electrical /
electronic behaviour) must fulfil.

applies = true for: construction, marking and labelling, photometric / colour / optical performance, durability and test
requirements of the functions the product has; installation rules (position, visibility, orientation, electrical
connection, tell-tales) for those functions; general requirements that cover every device or lamp of this kind;
EMC requirements for electrical / electronic sub-assemblies when the product contains electronics.

applies = false for: functions or devices the product does not have (e.g. headlamps, direction indicators, front lamps,
fog lamps when absent); vehicle categories other than the spec's; pure definitions; administrative duties of type-approval
authorities or technical services (communication forms, notification of other Contracting Parties, transitional
provisions, names and addresses); scope statements without an obligation.

Be strict about functions the product does not have, and inclusive about general requirements that apply to it."""


def candidates(regulations: set[str]) -> list[Chunk]:
    return [c for c in load_corpus("paragraph", "clauses") if c.regulation in regulations and SHALL.search(c.text)]


def _batch_prompt(spec: str, batch: list[Chunk]) -> str:
    items = "\n\n".join(f"[{c.id}] {c.regulation} para {c.paragraph or '-'} (page {c.page})\n{' '.join(c.text.split())[:900]}"
                        for c in batch)
    return f"{INSTRUCTIONS}\n\n<spec>\n{spec}\n</spec>\n\n<clauses>\n{items}\n</clauses>\n\nDecide every clause id."


def classify(spec: str, chunks: list[Chunk], batch_size: int = 40, workers: int = 6, effort: str = "medium") -> dict[int, bool]:
    """chunk id -> applies."""
    from .llm import structured

    schema = {"type": "object", "properties": {"decisions": {"type": "array", "items": {
        "type": "object", "properties": {"id": {"type": "integer"}, "applies": {"type": "boolean"}},
        "required": ["id", "applies"], "additionalProperties": False}}},
        "required": ["decisions"], "additionalProperties": False}
    batches = [chunks[i:i + batch_size] for i in range(0, len(chunks), batch_size)]

    def run(batch: list[Chunk]) -> dict[int, bool]:
        prompt = _batch_prompt(spec, batch)
        cache = CACHE_DIR / f"classify_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            return {int(k): v for k, v in json.loads(cache.read_text(encoding="utf-8")).items()}
        data = structured(prompt, schema, effort=effort)
        wanted = {c.id for c in batch}
        out = {d["id"]: d["applies"] for d in data["decisions"] if d["id"] in wanted}
        CACHE_DIR.mkdir(exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out

    decisions: dict[int, bool] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(run, batches):
            decisions.update(part)
    return decisions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default="dev-rear-lamp")
    ap.add_argument("--challenge-dir", default=str(DEFAULT_CHALLENGE_DIR))
    ap.add_argument("--select", default="combined", help="regulation selection method (see regselect)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--effort", default="medium")
    args = ap.parse_args(argv)

    from .bench import official_scorer
    from .regselect import select

    case_dir = Path(args.challenge_dir) / "cases" / args.case
    spec = (case_dir / "spec.md").read_text(encoding="utf-8")
    regs = set(select(spec, args.select))
    cands = candidates(regs)
    decisions = classify(spec, cands, workers=args.workers, effort=args.effort)
    kept = [c for c in cands if decisions.get(c.id)]
    print(f"regulations {sorted(regs)}: {len(cands)} 'shall' clauses, {len(decisions)} decided, {len(kept)} kept")
    expected = case_dir / "expected.json"
    if expected.is_file():
        gold = json.loads(expected.read_text(encoding="utf-8"))
        r = official_scorer(Path(args.challenge_dir))(
            {"requirements": [{"id": str(i), "text": "-", "source": c.cite()} for i, c in enumerate(kept)]}, gold)
        pl = r["page_level"]
        f2 = 5 * pl["precision"] * pl["recall"] / (4 * pl["precision"] + pl["recall"]) if pl["recall"] else 0
        print(f"page P {pl['precision']:.3f} R {pl['recall']:.3f} F1 {pl['f1']:.3f} F2 {f2:.3f} | reg F1 {r['regulation_level']['f1']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
