"""Submission-only step — expert-style section filter, calibrated on the worked example's answer key.

USES THE DEV ANSWER KEY as training data (see certi/dev_calibrated.py for the team-rule caveat); never apply it to
dev-rear-lamp.

On the worked example the experts left out whole kinds of sections: test-site and sample-preparation conditions,
test-equipment specifications and certification, measurement-method annexes, information documents / communication
forms, generic conformity-of-production clauses, measurement conventions in definitions, and annexes of a regulation
from which they listed nothing. This step removes those section types:
- for regulations NOT used by the worked example, by section heading type;
- for regulations used by it, annexes from which the experts listed no requirement on dev, and items inside a
  per-function lamp section (R48 6.N / R148 5.N) whose function the product does not have.

Usage:
    python -m certi.expert_style --case heldout-front-bumper --in outputs/x.json --out outputs/y.json
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from .dev_calibrated import clause_key, dev_clause_counts
from .lamp_functions import named_functions, present_functions, section_heading
from .scope_filter import CLAUSES_DIR

SKIPPED_SECTION_RX = re.compile(
    r"general test conditions|preparation of the vehicle|test impactor specifications|certification of the impactor|"
    r"information document|communication|methods? of determining|conformity of production",
    re.I,
)
DEFINITIONS_RX = re.compile(r"^\s*(\d+)\.?\s+(definitions?)\b", re.I)


def _regulation_index() -> dict[str, list[tuple[str, int, str]]]:
    index: dict[str, list[tuple[str, int, str]]] = {}
    for f in sorted(CLAUSES_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        rows = index.setdefault(d["regulation"], [])
        for c in d["clauses"]:
            rows.append((str(c.get("paragraph") or "").strip().rstrip("."), int(c["pages"][0]) if c.get("pages") else 0,
                         unicodedata.normalize("NFKC", c["text"]).strip()))
    return index


def _titles(rows: list[tuple[str, int, str]], para: str, page: int) -> list[str]:
    """Headings of the item's top-level section, level-2 section and annex (nearest at or before its page)."""
    out = []
    p = str(para).strip()
    m = re.match(r"(Annex \d+)", p)
    keys = [m.group(1)] if m else []
    m2 = re.match(r"(\d+)(?:\.(\d+))?", p if not m else "")
    if m2:
        keys.append(m2.group(1))
        if m2.group(2):
            keys.append(f"{m2.group(1)}.{m2.group(2)}")
    for k in keys:
        cands = [(pg, txt) for pp, pg, txt in rows if pp == k and pg <= page]
        if cands:
            out.append(max(cands)[1].split("\n")[0][:120])
    return out


DEFINES_RX = re.compile(r'^\s*\d+(\.\d+)+\.?\s*["“][^"”]{2,80}["”]\s*(\([^)]*\)\s*)?(means|is|are)\b', re.I)


def _definitions_sections(rows: list[tuple[str, int, str]]) -> list[tuple[str, int]]:
    """Top-level sections that are definitions: titled "N. Definitions", or whose sub-clauses define terms."""
    out = []
    for pp, pg, txt in rows:
        m = DEFINITIONS_RX.match(txt)
        if m and pp == m.group(1):
            out.append((pp, pg))
    defining: dict[tuple[str, int], int] = {}
    for pp, pg, txt in rows:
        if re.fullmatch(r"\d+\.\d+", pp) and DEFINES_RX.match(txt):
            key = (pp.split(".")[0], pg // 40)
            defining[key] = defining.get(key, 0) + 1
    for (top, bucket), n in defining.items():
        if n >= 3:
            first = min(pg for pp, pg, txt in rows if pp.split(".")[0] == top and pg // 40 == bucket and DEFINES_RX.match(txt))
            out.append((top, first))
    return out


def filter_items(case: str, reqs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], str]]]:
    counts = dev_clause_counts()
    shared = {reg for reg, _ in counts}
    dev_annexes = {(reg, m.group(1).lower()) for reg, key in counts for m in [re.match(r"(annex\s*\d+)", key)] if m}
    present = {k for k, v in present_functions(case).items() if v["present"]}
    index = _regulation_index()
    kept, dropped = [], []
    for r in reqs:
        s = r["source"]
        reg, para, page = s["regulation"], str(s.get("paragraph", "")), int(s.get("page", 0))
        reason = ""
        if reg in shared:
            m = re.match(r"(annex\s*\d+)", para.lower())
            if m and (reg, m.group(1).replace(" ", "")) not in {(a, b.replace(" ", "")) for a, b in dev_annexes}:
                reason = "annex not used by experts on dev"
            heading_fn = named_functions(section_heading(reg, para))
            if heading_fn and not heading_fn & present:
                reason = "lamp-function section of an absent function"
        else:
            titles = _titles(index.get(reg, []), para, page)
            if any(SKIPPED_SECTION_RX.search(t) for t in titles):
                reason = "section type experts skip: " + next(t for t in titles if SKIPPED_SECTION_RX.search(t))[:50]
            top = re.match(r"(\d+)", para)
            if top and not para.lower().startswith("annex"):
                for dp, dpg in _definitions_sections(index.get(reg, [])):
                    if top.group(1) == dp and page >= dpg and page - dpg <= 6:
                        reason = "measurement convention in definitions"
        (dropped.append((r, reason)) if reason else kept.append(r))
    return kept, dropped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.case == "dev-rear-lamp":
        raise SystemExit("expert_style must not be applied to the case whose answer key it learns from")
    doc = json.loads(args.inp.read_text(encoding="utf-8"))
    kept, dropped = filter_items(args.case, doc["requirements"])
    for r, why in dropped:
        print(f"  - {r['source']['regulation']:8} {str(r['source'].get('paragraph')):22} p{r['source']['page']:<4} [{why}] {r['text'][:70]}")
    for i, r in enumerate(kept, 1):
        r["id"] = f"R-{i:04d}"
    doc["requirements"] = kept
    args.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[expert-style] dropped {len(dropped)}, kept {len(kept)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
