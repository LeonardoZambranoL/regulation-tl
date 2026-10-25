"""Mirror obligations between linked regulations: when two selected regulations restate each other (one transposes the
other, e.g. a UN Regulation adopting a GTR), expert lists cite the obligation under BOTH. An item listed under only one
of them gets its counterpart from the other, in that regulation's own wording and citation.

    python -m retrieval.mirror <ranked.json> --out <mirrored.json> [--min-shared 5]

Two regulations are linked when the pair check (refine.merge_pairs) confirms at least --min-shared obligations that both
state. For each item of A with no confirmed partner in B, Claude reads B's operative clauses and returns the clause that
states the same obligation (or none) and the requirement in B's wording. Only adds items; cached per call.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

from .classify import rationale_pages
from .corpus import LLM_CACHE_DIR, load_corpus
from .refine import merge_pairs, norm

PROMPT = """Regulation B restates the requirements of regulation A (one transposes the other), and the requirements list
for the product in question must cite each obligation under BOTH regulations. Each item below is a requirement taken
from regulation A. For every item, find the clause of regulation B (numbered list below) that states the SAME obligation:
same subject, same condition, same limit or value (B may number and word it differently).

Return for every item: "clause" = the number of that B clause, or -1 if B states no such obligation; "text" = the
requirement written as ONE sentence in B's own wording, values and references (empty when clause is -1). Do not invent
obligations B does not state; values must come from B's clause."""

SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "string"}, "clause": {"type": "integer"}, "text": {"type": "string"}},
    "required": ["id", "clause", "text"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False}


def mirror(reqs: list[dict], min_shared: int = 5, effort: str = "medium") -> tuple[list[dict], dict]:
    from .llm import structured

    _, decisions = merge_pairs(reqs, effort=effort)
    by_id = {r["id"]: r for r in reqs}
    same = [d for d in decisions if d["verdict"] == "same" and d["kind"] == "cross"]
    shared = collections.Counter(tuple(sorted((by_id[d["a"]]["source"]["regulation"], by_id[d["b"]]["source"]["regulation"])))
                                 for d in same)
    links = [pair for pair, n in shared.items() if n >= min_shared]
    paired = {i for d in same for i in (d["a"], d["b"])}
    start = rationale_pages()
    corpus = load_corpus("paragraph", "clauses")
    added, report = [], {"links": {f"{a} <-> {b}": shared[(a, b)] for a, b in links}, "directions": []}
    next_id = max(int(r["id"].split("-")[-1]) for r in reqs if r["id"].split("-")[-1].isdigit()) + 1
    for a, b in links:
        for src, dst in ((a, b), (b, a)):
            items = [r for r in reqs if r["source"]["regulation"] == src and r["id"] not in paired
                     and r["source"]["page"] >= start.get(src, 0)]
            clauses = [c for c in corpus if c.regulation == dst and c.page >= start.get(dst, 0) and c.text.strip()]
            if not items or not clauses:
                continue
            listing = "\n".join(f"[{n}] para {c.paragraph or '-'} (page {c.page}): {' '.join(c.text.split())[:700]}"
                                for n, c in enumerate(clauses))
            asks = "\n".join(f"[{r['id']}] {src} para {r['source'].get('paragraph') or '-'}: {r['text']}" for r in items)
            prompt = (f"{PROMPT}\n\n<regulation_A>{src}</regulation_A>\n<regulation_B>{dst}</regulation_B>\n\n"
                      f"<clauses_of_B>\n{listing}\n</clauses_of_B>\n\n<items_from_A>\n{asks}\n</items_from_A>")
            cache = LLM_CACHE_DIR / f"mirror_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
            if cache.is_file():
                answers = json.loads(cache.read_text(encoding="utf-8"))
            else:
                answers = structured(prompt, SCHEMA, effort=effort)["items"]
                LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(answers), encoding="utf-8")
            existing = {norm(r["text"]) for r in reqs + added if r["source"]["regulation"] == dst}
            n_new = 0
            for ans in answers:
                if not (0 <= ans["clause"] < len(clauses)) or not ans["text"].strip() or norm(ans["text"]) in existing:
                    continue
                c = clauses[ans["clause"]]
                added.append({"id": f"R-{next_id:04d}", "text": ans["text"].strip()[:2000], "source": c.cite(),
                              "mirrored_from": ans["id"]})
                existing.add(norm(ans["text"]))
                next_id += 1
                n_new += 1
            report["directions"].append({"from": src, "to": dst, "asked": len(items), "added": n_new})
    report["added"] = [{"id": r["id"], "from": r["mirrored_from"], "regulation": r["source"]["regulation"],
                        "paragraph": r["source"].get("paragraph"), "text": r["text"][:200]} for r in added]
    return reqs + added, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prediction", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-shared", type=int, default=5)
    ap.add_argument("--effort", default="medium")
    args = ap.parse_args(argv)
    doc = json.loads(args.prediction.read_text(encoding="utf-8"))
    reqs, report = mirror(doc["requirements"], args.min_shared, args.effort)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({**doc, "requirements": reqs}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out.parent / (args.out.stem + "-mirror-report.json")).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("mirror:", json.dumps({"links": report["links"], "directions": report["directions"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
