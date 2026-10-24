"""Expand profile-faithful's relevant clauses to whole pages and write one requirement per clause."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from retrieval.classify import PROMPTS as CLASSIFY_PROMPTS
from retrieval.classify import candidates, classify
from retrieval.corpus import Chunk, DEFAULT_CHALLENGE_DIR, LLM_CACHE_DIR, REPO_ROOT, load_corpus
from retrieval.llm import structured
from retrieval.profile import augment
from retrieval.regselect import select


EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
CACHE_DIR = LLM_CACHE_DIR
MAX_REQUIREMENTS = 5000

WRITER_INSTRUCTIONS = """You are a UNECE type-approval engineer writing a traceable requirements list for the
product in <spec>. Every numbered clause below is on a page judged relevant to the product. Produce EXACTLY ONE
non-empty requirement string for EVERY clause id, even when the clause is a heading, definition, note, test step,
administrative provision, cross-reference, or contains multiple obligations. Never omit a clause and never return a
second requirement for it.

Rules:
1. Preserve the regulation's subject, scope, conditions, exceptions, alternatives, values, units and references.
2. Make the text self-contained using the supplied parent clause when needed. Do not invent technical constraints.
3. When a clause contains several obligations or list items, combine them faithfully into one requirement string,
   using semicolons if needed. Do not split them into separate entries.
4. When text is descriptive rather than explicitly mandatory, express one faithful compliance requirement covering
   that clause's content; do not discard it merely because it lacks "shall".
5. Keep each requirement at most 1,900 characters so it remains below the submission limit.

Return every supplied id exactly once."""


def clause_pages(chunk: Chunk) -> tuple[int, ...]:
    """Return every source page occupied by a parsed clause, preserving metadata order."""
    pages = chunk.meta.get("pages") or [chunk.page]
    return tuple(dict.fromkeys(int(page) for page in pages))


def relevant_page_keys(chunks: list[Chunk]) -> set[tuple[str, str, int]]:
    return {
        (chunk.regulation, chunk.version, page)
        for chunk in chunks
        for page in clause_pages(chunk)
    }


def expand_to_relevant_pages(seed_chunks: list[Chunk], corpus: list[Chunk]) -> tuple[list[Chunk], set[tuple[str, str, int]]]:
    """Include each corpus clause once if any of its pages contains a relevant seed clause."""
    page_keys = relevant_page_keys(seed_chunks)
    expanded = [
        chunk
        for chunk in corpus
        if any((chunk.regulation, chunk.version, page) in page_keys for page in clause_pages(chunk))
    ]
    return expanded, page_keys


def _parents(chunks: list[Chunk], corpus: list[Chunk]) -> dict[int, Chunk]:
    by_paragraph = {
        (chunk.regulation, chunk.version, chunk.paragraph.rstrip(".")): chunk
        for chunk in corpus
        if chunk.paragraph
    }
    parents: dict[int, Chunk] = {}
    for chunk in chunks:
        parts = (chunk.paragraph or "").rstrip(".").split(".")
        for length in range(len(parts) - 1, 0, -1):
            parent = by_paragraph.get((chunk.regulation, chunk.version, ".".join(parts[:length])))
            if parent is not None:
                parents[chunk.id] = parent
                break
    return parents


def _batch_prompt(spec: str, batch: list[Chunk], parents: dict[int, Chunk]) -> str:
    items = []
    for chunk in batch:
        heading = f"[{chunk.id}] {chunk.regulation} para {chunk.paragraph or '-'} (pages {', '.join(map(str, clause_pages(chunk)))})"
        if chunk.id in parents:
            parent = parents[chunk.id]
            heading += f"\n  parent {parent.paragraph}: {' '.join(parent.text.split())[:500]}"
        items.append(f"{heading}\n  clause: {' '.join(chunk.text.split())[:6000]}")
    return (
        f"{WRITER_INSTRUCTIONS}\n\n<spec>\n{spec}\n</spec>\n\n<clauses>\n"
        + "\n\n".join(items)
        + "\n</clauses>"
    )


def _clean_requirement(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        raise ValueError("the LLM returned an empty requirement")
    return cleaned[:2000]


def write_one_per_clause(
    spec: str,
    chunks: list[Chunk],
    corpus: list[Chunk],
    *,
    batch_size: int = 8,
    workers: int = 6,
    effort: str = "medium",
) -> list[tuple[Chunk, str]]:
    """Return exactly one non-empty requirement for every input clause, in input order."""
    batch_schema = {
        "type": "object",
        "properties": {
            "clauses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "requirement": {"type": "string", "minLength": 1},
                    },
                    "required": ["id", "requirement"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["clauses"],
        "additionalProperties": False,
    }
    single_schema = {
        "type": "object",
        "properties": {"requirement": {"type": "string", "minLength": 1}},
        "required": ["requirement"],
        "additionalProperties": False,
    }
    parents = _parents(chunks, corpus)
    batches = [chunks[index : index + batch_size] for index in range(0, len(chunks), batch_size)]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def write_single(chunk: Chunk) -> str:
        prompt = _batch_prompt(spec, [chunk], parents) + "\n\nReturn one object containing the requirement string."
        key = hashlib.sha1(("single:" + effort + prompt).encode()).hexdigest()[:16]
        cache = CACHE_DIR / f"write_single_{key}.json"
        if cache.is_file():
            data = json.loads(cache.read_text(encoding="utf-8"))
        else:
            data = structured(prompt, single_schema, effort=effort)
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return _clean_requirement(data["requirement"])

    def run_batch(batch: list[Chunk]) -> dict[int, str]:
        prompt = _batch_prompt(spec, batch, parents)
        key = hashlib.sha1(("batch:" + effort + prompt).encode()).hexdigest()[:16]
        cache = CACHE_DIR / f"write_batch_{key}.json"
        if cache.is_file():
            data = json.loads(cache.read_text(encoding="utf-8"))
        else:
            data = structured(prompt, batch_schema, effort=effort)
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        wanted = {chunk.id for chunk in batch}
        seen: set[int] = set()
        output: dict[int, str] = {}
        duplicate_ids: set[int] = set()
        for item in data["clauses"]:
            clause_id = item["id"]
            if clause_id not in wanted:
                continue
            if clause_id in seen:
                duplicate_ids.add(clause_id)
                continue
            seen.add(clause_id)
            try:
                output[clause_id] = _clean_requirement(item["requirement"])
            except ValueError:
                pass

        # A batch response cannot be trusted when it omitted or duplicated an id. Retrying those clauses one at a
        # time gives the structured output only one possible clause and enforces the cardinality invariant.
        retry_ids = (wanted - set(output)) | duplicate_ids
        by_id = {chunk.id: chunk for chunk in batch}
        for clause_id in retry_ids:
            output[clause_id] = write_single(by_id[clause_id])
        return output

    written: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for partial in pool.map(run_batch, batches):
            written.update(partial)

    missing = [chunk.id for chunk in chunks if chunk.id not in written]
    if missing:
        raise RuntimeError(f"writer failed cardinality check; missing clause ids: {missing[:20]}")
    pairs = [(chunk, written[chunk.id]) for chunk in chunks]
    if len(pairs) != len(chunks):
        raise RuntimeError(f"writer cardinality mismatch: {len(pairs)} outputs for {len(chunks)} clauses")
    return pairs


def find_case(case: str, challenge_dir: Path) -> Path:
    for candidate in (
        challenge_dir / "cases" / case,
        REPO_ROOT / "approaches" / "benchmarking" / "cases" / case,
    ):
        if candidate.is_dir():
            return candidate
    raise SystemExit(f"case {case!r} not found in the challenge repo or approaches/benchmarking/cases")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(EXPERIMENT_DIR / "config.json"))
    parser.add_argument("--case", default="dev-rear-lamp")
    parser.add_argument("--challenge-dir", default=str(DEFAULT_CHALLENGE_DIR))
    parser.add_argument("--team-id", default="team-11")
    parser.add_argument("--out", default=str(EXPERIMENT_DIR / "outputs" / "predictions.json"))
    args = parser.parse_args(argv)

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    case_dir = find_case(args.case, Path(args.challenge_dir))
    raw_spec = (case_dir / "spec.md").read_text(encoding="utf-8")
    spec = augment(raw_spec, case_dir) if config.get("profile") else raw_spec
    regulations = set(select(raw_spec, **config["select"]))

    filter_config = config["filter"]
    seed_candidates = candidates(
        regulations,
        filter_config.get("candidates", "shall+implicit"),
        tuple(filter_config.get("exclude_labels", ())),
    )
    decisions = classify(
        spec,
        seed_candidates,
        effort=filter_config.get("effort", "medium"),
        instructions=CLASSIFY_PROMPTS[filter_config.get("prompt", "default")],
    )
    relevant_seeds = [chunk for chunk in seed_candidates if decisions.get(chunk.id)]
    corpus = [
        chunk
        for chunk in load_corpus("paragraph", config.get("source", "clauses"))
        if chunk.regulation in regulations and chunk.text.strip()
    ]
    expanded, pages = expand_to_relevant_pages(relevant_seeds, corpus)
    if len(expanded) > MAX_REQUIREMENTS:
        raise SystemExit(
            f"expanded set has {len(expanded)} clauses, exceeding the official {MAX_REQUIREMENTS}-requirement limit; "
            "refusing to truncate because that would violate one output per clause"
        )

    pairs = write_one_per_clause(spec, expanded, corpus, effort=config["write"].get("effort", "medium"))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "team_id": args.team_id,
        "case_id": args.case,
        "requirements": [
            {"id": f"R-{index:04d}", "text": text, "source": chunk.cite()}
            for index, (chunk, text) in enumerate(pairs, 1)
        ],
    }
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output.parent / f"{output.stem}-page-expansion-report.json").write_text(
        json.dumps(
            {
                "case_id": args.case,
                "regulations": sorted(regulations),
                "seed_candidates": len(seed_candidates),
                "relevant_seed_clauses": len(relevant_seeds),
                "relevant_pages": [
                    {"regulation": regulation, "version": version, "page": page}
                    for regulation, version, page in sorted(pages)
                ],
                "expanded_distinct_clauses": len(expanded),
                "output_requirements": len(pairs),
                "cardinality_ok": len(expanded) == len(pairs),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (output.parent / f"spec-with-profile-{args.case}.md").write_text(spec, encoding="utf-8")
    print(
        f"wrote {len(pairs)} requirements for {len(expanded)} clauses on {len(pages)} relevant pages "
        f"({len(relevant_seeds)} seed clauses) -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
