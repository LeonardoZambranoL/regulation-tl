"""Requirement writer: turn each kept clause into the single engineering obligations it states.

The platform matches requirements one to one with the experts' list, where each expected requirement is ONE obligation
(same scope, condition and constraint). A raw clause often holds several (a list, a table, one rule per variant), so
handing in whole clauses caps recall, and headings / paragraph numbers / non-obligations cost precision. Claude reads
each clause with its parent clause (for the subject) and the spec, and returns zero or more self-contained requirement
sentences. Every requirement keeps the clause's citation. Cached per batch in .cache/.
"""

from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor

from .corpus import LLM_CACHE_DIR, Chunk, load_corpus

INSTRUCTIONS = """You are a UNECE type-approval engineer writing the requirements list for the product in <spec>. Each
numbered clause below was already judged relevant to this product. Rewrite each clause as the individual engineering
obligations it imposes on this product.

Rules:
1. One requirement = ONE obligation: who/what (subject), the modal ("shall", "shall not"), the constraint or value, and
   the condition under which it applies ("where...", "if...", "for ..."). Write one sentence.
2. Self-contained: name the subject explicitly (use the parent clause or heading for it, e.g. "The number of rear
   position lamps shall be two." for a line "Number: two" under a rear position lamp heading). No paragraph numbers,
   headings or "this paragraph". Keep cross-references only when they carry the constraint ("as defined in Annex 5").
3. Stay close to the regulation's wording, terms and values; do not paraphrase numbers, units or test conditions.
4. Split when the clause lists separate obligations: list items (a), (b), (c), separate sentences with their own
   "shall", table rows or values given per variant/category/test level. Each split requirement repeats its subject and
   condition. Keep one requirement when a single sentence imposes one obligation with several attributes (e.g. "shall
   be clearly legible and indelible").
5. Write nothing (empty list) for: definitions, scope or heading lines without an obligation, duties of authorities or
   technical services, administrative or transitional provisions, and obligations that only concern functions,
   components or vehicle categories this product does not have. Within a clause, keep only the parts that apply to
   this product.

Return for every clause id the list of requirement sentences (possibly empty)."""

STRICT_EXTRA = """
6. Requirements are obligations ON THE PRODUCT: what it must be, bear, achieve, withstand or how it must be installed,
   including the test levels, conditions and pass/fail results it must meet. Write nothing for how a laboratory
   carries out a test (apparatus, measuring equipment, chamber or collector dimensions, sample cleaning, handling or
   preparation steps, timing of measurements), for conformity-of-production or sampling procedures, and for the
   manufacturer's or authority's quality and documentation procedures."""

FAITHFUL_EXTRA = """
7. Keep the regulation's own scope and subject. Do NOT narrow a requirement to this product's vehicle category,
   variant or function (if the clause says "for M1 and N1 category vehicles", write "M1 and N1"), do NOT replace the
   regulation's subject with the product's name (write "the rear retro-reflector", "the stop lamp", "the ESA" as the
   clause does), and do NOT drop alternatives or the second half of a combined obligation ("two S1 or S2 category
   devices and one S3 or S4 category device" stays one requirement). Every value, unit, condition, exception and
   referenced standard in the clause must appear in the requirement.
8. Split only where the regulation states separate obligations (own "shall", list items, per-variant values). Do not
   split one sentence into several requirements because it has several attributes."""

PROMPTS = {"default": INSTRUCTIONS, "strict": INSTRUCTIONS.replace(
    "\n\nReturn for every clause id", STRICT_EXTRA + "\n\nReturn for every clause id")}
# faithful = strict, minus the instruction to keep only the parts that apply (it made the writer narrow the scope),
# plus rules 7-8: keep the regulation's own scope, subject, values and alternatives
PROMPTS["faithful"] = PROMPTS["strict"].replace(
    " Within a clause, keep only the parts that apply to\n   this product.", "").replace(
    "\n\nReturn for every clause id", FAITHFUL_EXTRA + "\n\nReturn for every clause id")


MARKING = re.compile(r"\b(bears?|marked|markings?|labelled|inscriptions?)\b", re.IGNORECASE)
MARKING_EXTRA = """
9. Marking clauses: when a clause lists several markings, or several objects that must bear a marking (e.g. the
   device and a separate module or component), write one requirement per marking item AND per object that must bear
   it, each repeating the clause's condition ("in case ...", "where ..."). Do not merge two markings or two objects
   into one requirement."""
for _name in list(PROMPTS):
    PROMPTS[_name + "_marking"] = PROMPTS[_name].replace("\n\nReturn for every clause id", MARKING_EXTRA + "\n\nReturn for every clause id")


def _parents(chunks: list[Chunk]) -> dict[int, Chunk]:
    """chunk id -> its parent clause (longest proper paragraph prefix in the same regulation), for the subject."""
    by_para = {}
    for c in load_corpus("paragraph", "clauses"):
        if c.paragraph:
            by_para.setdefault((c.regulation, c.paragraph.rstrip(".")), c)
    out = {}
    for c in chunks:
        parts = (c.paragraph or "").rstrip(".").split(".")
        for k in range(len(parts) - 1, 0, -1):
            p = by_para.get((c.regulation, ".".join(parts[:k])))
            if p is not None:
                out[c.id] = p
                break
    return out


def _prompt(spec: str, batch: list[Chunk], parents: dict[int, Chunk], instructions: str = INSTRUCTIONS) -> str:
    items = []
    for c in batch:
        head = f"[{c.id}] {c.regulation} para {c.paragraph or '-'} (page {c.page})"
        if c.id in parents:
            p = parents[c.id]
            head += f"\n  parent {p.paragraph}: {' '.join(p.text.split())[:300]}"
        items.append(f"{head}\n  clause: {' '.join(c.text.split())[:2500]}")
    return f"{instructions}\n\n<spec>\n{spec}\n</spec>\n\n<clauses>\n" + "\n\n".join(items) + "\n</clauses>"


def write(spec: str, chunks: list[Chunk], batch_size: int = 8, workers: int = 6, effort: str = "medium",
          prompt: str = "default") -> list[tuple[Chunk, str]]:
    """[(clause, requirement sentence)] in clause order; clauses with no obligation for this product yield nothing."""
    from .llm import structured

    schema = {"type": "object", "properties": {"clauses": {"type": "array", "items": {
        "type": "object", "properties": {"id": {"type": "integer"}, "requirements": {"type": "array", "items": {"type": "string"}}},
        "required": ["id", "requirements"], "additionalProperties": False}}},
        "required": ["clauses"], "additionalProperties": False}
    parents = _parents(chunks)
    batches = [chunks[i:i + batch_size] for i in range(0, len(chunks), batch_size)]

    def run(batch: list[Chunk]) -> dict[int, list[str]]:
        text = _prompt(spec, batch, parents, PROMPTS[prompt])
        cache = LLM_CACHE_DIR / f"write_{hashlib.sha1((effort + text).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            return {int(k): v for k, v in json.loads(cache.read_text(encoding="utf-8")).items()}
        data = structured(text, schema, effort=effort)
        wanted = {c.id for c in batch}
        out = {d["id"]: [t.strip() for t in d["requirements"] if t.strip()] for d in data["clauses"] if d["id"] in wanted}
        LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out

    texts: dict[int, list[str]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(run, batches):
            texts.update(part)
    return [(c, t) for c in chunks for t in texts.get(c.id, [])]
