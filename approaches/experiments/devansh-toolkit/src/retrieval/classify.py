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

from .corpus import LLM_CACHE_DIR, DEFAULT_CHALLENGE_DIR, Chunk, load_corpus

SHALL = re.compile(r"\b(shall|must)\b", re.IGNORECASE)
IMPLICIT = re.compile(
    r"\b(not (less|more|lower|higher|greater) than|at (least|most)|minimum|maximum|is not permitted|are not permitted|"
    r"(is|are) prohibited|(is|are) required|may (only|be [a-z]+ed) .{0,80}provided|provided that|"
    r"apply the|is (exposed|subjected|tested|measured)|are (exposed|subjected|tested|measured))\b"
    r"|^\S+\s+[A-Z][a-z]+( [a-z]+){0,4}:\s"            # "6.14.2. Number: Two ...", "6.4.4.2. In height: ..."
    r"|\d\s?(mm|cm|cd|lx|°|º|V|W|Hz|MHz|kHz|ms|s|%)\b",  # a value with a unit
    re.IGNORECASE | re.MULTILINE)

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


NEUTRAL_INSTRUCTIONS = """You are a UNECE type-approval engineer. A supplier builds the product in <spec> and needs every
engineering requirement it must fulfil under the selected UN Regulations. For each numbered clause below decide
whether it states a requirement that this product must fulfil.

Obligations are often written without "shall": specification-style lines ("Height: not less than ... mm",
"Number: two", "Angle: 45 degrees"), permissions with conditions ("may ... provided that ..."), prohibitions
("... is not permitted"), test instructions ("Apply the test ...", "The sample is exposed to ..."), and table rows.
Treat these as requirements when they apply.

applies = true for requirements on the product itself, its markings and approval documentation from the
manufacturer, its performance and the tests it must pass, its installation or integration in the vehicle, and its
electrical / electronic behaviour, for the functions, components and vehicle categories described in the spec.

applies = false for: functions, components or vehicle categories the product does not have; pure definitions;
duties of type-approval authorities or technical services; headings or scope statements without an obligation of
their own; transitional provisions.

Decide from the spec, not from what products of this kind usually have."""

AUDITOR_INSTRUCTIONS = """You are a completeness auditor for a UNECE type-approval team. Another engineer is deciding
which numbered clauses below apply to the product in <spec>; your job is to make sure NOTHING that applies is missed.
For each clause decide whether it could state a requirement that this product (the device itself, its markings, its
installation on the vehicle, its electrical / electronic behaviour, the tests it must pass) has to fulfil.

applies = true unless the clause clearly does not apply: it only concerns a function or device the product does not
have, a vehicle category other than the spec's, a pure definition, an administrative duty of authorities or technical
services, or a scope statement without an obligation. General requirements, test procedures and marking rules that
cover devices of this kind apply. When in doubt, answer true."""

ADJUDICATOR_INSTRUCTIONS = """You are the senior UNECE type-approval engineer settling disagreements. Two reviewers
judged whether each numbered clause below states a requirement that the product in <spec> must fulfil:
- Reviewer A is strict about applicability (rejects clauses for functions the product does not have).
- Reviewer B is a completeness auditor (keeps anything that could apply).
They disagreed on every clause below. Read the clause and the spec, decide yourself, and give a one-sentence reason.
applies = true when the clause states an obligation for this product (device, markings, installation, electrical /
electronic behaviour, tests) given its actual functions and vehicle category; false otherwise."""


PROMPTS = {"default": INSTRUCTIONS, "neutral": NEUTRAL_INSTRUCTIONS}


OPERATIVE_HEADING = re.compile(r"\bII\.\s*Text of the Regulation\b", re.IGNORECASE)


def rationale_pages() -> dict[str, int]:
    """regulation -> first page of its operative text, for regulations that open with a statement of technical rationale
    (GTR layout: "I. Statement of technical rationale and justification" ... "II. Text of the Regulation"). Clauses on
    earlier pages explain the regulation's history and options; they are not its requirements."""
    first: dict[str, int] = {}
    for c in load_corpus("paragraph", "clauses"):
        if c.regulation not in first and OPERATIVE_HEADING.search(" ".join(c.text.split())):
            first[c.regulation] = c.page
    return first


def candidates(regulations: set[str], mode: str = "shall", exclude_labels: tuple[str, ...] = ()) -> list[Chunk]:
    """Clauses the reviewers judge. "shall": only clauses containing shall / must (misses implicit obligations);
    "all": every clause of the selected regulations. `exclude_labels`: skip clauses cited at a paragraph label starting
    with one of these words (e.g. "Table", "Figure", "Appendix": value tables whose obligation is imposed, and cited,
    by the numbered clause that refers to them)."""
    chunks = [c for c in load_corpus("paragraph", "clauses") if c.regulation in regulations and c.text.strip()
              and not (exclude_labels and (c.paragraph or "").startswith(tuple(exclude_labels)))]
    if mode == "all":
        return chunks
    if mode == "shall+implicit":
        # obligations written without shall / must: spec-style lines with values, prohibitions, conditional
        # permissions, test instructions (about a third of the dev experts' no-shall paragraphs look like this)
        return [c for c in chunks if SHALL.search(c.text) or IMPLICIT.search(c.text)]
    return [c for c in chunks if SHALL.search(c.text)]


def _batch_prompt(spec: str, batch: list[Chunk], instructions: str = INSTRUCTIONS, notes: dict[int, str] | None = None) -> str:
    notes = notes or {}
    items = "\n\n".join(f"[{c.id}] {c.regulation} para {c.paragraph or '-'} (page {c.page})"
                        f"{(' ' + notes[c.id]) if c.id in notes else ''}\n{' '.join(c.text.split())[:900]}"
                        for c in batch)
    return f"{instructions}\n\n<spec>\n{spec}\n</spec>\n\n<clauses>\n{items}\n</clauses>\n\nDecide every clause id."


def classify(spec: str, chunks: list[Chunk], batch_size: int = 40, workers: int = 6, effort: str = "medium",
             instructions: str = INSTRUCTIONS, notes: dict[int, str] | None = None) -> dict[int, bool]:
    """chunk id -> applies. `instructions` sets the reviewer's role (each role has its own cache)."""
    from .llm import structured

    schema = {"type": "object", "properties": {"decisions": {"type": "array", "items": {
        "type": "object", "properties": {"id": {"type": "integer"}, "applies": {"type": "boolean"}},
        "required": ["id", "applies"], "additionalProperties": False}}},
        "required": ["decisions"], "additionalProperties": False}
    batches = [chunks[i:i + batch_size] for i in range(0, len(chunks), batch_size)]

    def run(batch: list[Chunk]) -> dict[int, bool]:
        prompt = _batch_prompt(spec, batch, instructions, notes)
        cache = LLM_CACHE_DIR / f"classify_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            return {int(k): v for k, v in json.loads(cache.read_text(encoding="utf-8")).items()}
        data = structured(prompt, schema, effort=effort)
        wanted = {c.id for c in batch}
        out = {d["id"]: d["applies"] for d in data["decisions"] if d["id"] in wanted}
        LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out

    decisions: dict[int, bool] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(run, batches):
            decisions.update(part)
    return decisions


def classify_multi(spec: str, chunks: list[Chunk], workers: int = 6, effort: str = "medium") -> tuple[dict[int, bool], dict]:
    """Three agents that check each other: A (strict applicability, the single-agent reviewer) and B (completeness
    auditor) judge every clause independently; C (adjudicator) re-judges only the clauses where A and B disagree.
    Final: both yes -> yes, both no -> no, disagreement -> C's decision. Returns (decisions, report)."""
    a = classify(spec, chunks, workers=workers, effort=effort, instructions=INSTRUCTIONS)
    b = classify(spec, chunks, workers=workers, effort=effort, instructions=AUDITOR_INSTRUCTIONS)
    disputed = [c for c in chunks if a.get(c.id) != b.get(c.id)]
    notes = {c.id: f"[reviewer A: {'applies' if a.get(c.id) else 'does not apply'}; "
                   f"reviewer B: {'applies' if b.get(c.id) else 'does not apply'}]" for c in disputed}
    judged = classify(spec, disputed, batch_size=25, workers=workers, effort="high",
                      instructions=ADJUDICATOR_INSTRUCTIONS, notes=notes) if disputed else {}
    final = {}
    for c in chunks:
        final[c.id] = a.get(c.id) if a.get(c.id) == b.get(c.id) else bool(judged.get(c.id, b.get(c.id)))
    report = {
        "clauses": len(chunks),
        "agent_a_yes": sum(bool(a.get(c.id)) for c in chunks),
        "agent_b_yes": sum(bool(b.get(c.id)) for c in chunks),
        "agreed_yes": sum(bool(a.get(c.id)) and bool(b.get(c.id)) for c in chunks),
        "disputed": len(disputed),
        "disputed_kept_by_adjudicator": sum(bool(judged.get(c.id)) for c in disputed),
        "final_yes": sum(final.values()),
    }
    return final, report


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
