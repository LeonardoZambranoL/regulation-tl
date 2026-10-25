"""v7 structural pruning (zero API): drop items that cannot be a distinct expert obligation.

    python prune.py <submission.json> <out.json> [--report report.json]

A administrative: paragraph under an approval / marking-of-approval / modification / conformity-of-production /
  penalties / discontinued / technical-services / transitional section, or in a communication / information-document /
  approval-mark annex.
B within-regulation near-repeat: token Jaccard >= 0.85 with an earlier item of the same regulation.
C definitions: paragraph under a "Definitions" section.
Section titles come from the team's parsed clauses (the heading clause of the paragraph's top-level number at or
before the item's page). Which components are applied is set by --tests (default: the adopted ones, see README).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "devansh-toolkit" / "src"))
from retrieval.corpus import load_clauses  # noqa: E402

ADMIN = re.compile(r"application for approval|^approval$|administrative provisions|modification|extension|amendment"
                   r"|conformity of production|penalties|discontinued|names and addresses|transitional"
                   r"|communication|information document|approval mark", re.I)
DEFS = re.compile(r"^definitions?$", re.I)


def headings() -> dict[str, list[tuple[int, str, str]]]:
    """regulation -> [(page, top-level key, title)] for clauses that are section / annex headings."""
    out: dict[str, list] = {}
    for c in load_clauses():
        if not c.paragraph:
            continue
        first = c.text.strip().split("\n")[0]
        m = re.fullmatch(r"(\d{1,2})", c.paragraph)
        if m:
            t = re.match(r"^\d{1,2}\.?\s+(.*)$", first)
            # a heading is short and not a sentence ("12 November 2008. The ..." is not)
            if not t or len(t.group(1)) > 90 or re.search(r"\.\s+\S", t.group(1)) or t.group(1)[:1].islower():
                continue
            out.setdefault(c.regulation, []).append((c.page, m.group(1), t.group(1).strip(" :.")))
        elif re.fullmatch(r"Annex \d+[A-Z]?", c.paragraph):
            out.setdefault(c.regulation, []).append((c.page, c.paragraph, first[len(c.paragraph):].strip()))
    return out


def section(item: dict, heads: dict) -> str:
    src = item["source"]
    para = (src.get("paragraph") or "").strip()
    m = re.match(r"(Annex \d+[A-Z]?)", para)
    key = m.group(1) if m else re.split(r"[ .]", para)[0]
    cands = [h for h in heads.get(src["regulation"], []) if h[1] == key and h[0] <= int(src["page"])]
    return max(cands)[2] if cands else ""


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+(?:\.[0-9]+)*", text.lower()))


def classify(reqs: list[dict]) -> dict[str, set[str]]:
    heads = headings()
    hit = {"A": set(), "B": set(), "C": set()}
    seen: dict[str, list[set[str]]] = {}
    for r in reqs:
        title = section(r, heads)
        if title and ADMIN.search(title) and not DEFS.match(title):
            hit["A"].add(r["id"])
        if title and DEFS.match(title):
            hit["C"].add(r["id"])
        t = tokens(r["text"])
        prev = seen.setdefault(r["source"]["regulation"], [])
        if any(len(t & p) / max(1, len(t | p)) >= 0.85 for p in prev):
            hit["B"].add(r["id"])
        else:
            prev.append(t)
    return hit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inp", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--tests", default="", help="components to apply, e.g. 'AB'")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    doc = json.loads(a.inp.read_text(encoding="utf-8"))
    hit = classify(doc["requirements"])
    drop = set().union(*(hit[k] for k in a.tests)) if a.tests else set()
    kept = [r for r in doc["requirements"] if r["id"] not in drop]
    a.out.write_text(json.dumps({**doc, "requirements": kept}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if a.report:
        a.report.write_text(json.dumps({k: sorted(v) for k, v in hit.items()}, indent=1) + "\n", encoding="utf-8")
    print(f"{len(doc['requirements'])} -> {len(kept)} (" + ", ".join(f"{k} {len(v)}" for k, v in hit.items()) + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
