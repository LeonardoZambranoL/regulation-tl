"""Stage 6 — Section scope filter (one LLM call per case, no clause re-reading).

Groups the Stage 5 requirements by regulation section (two paragraph levels, or annex + first level), asks the model once
to label every section (product / test on product / test tool / other object / non-normative) against the Stage 1
product profile, and keeps only the requirements in A/B sections.

Why sections and not a top-N cut: with G expected requirements, N submitted and M matched, F2 = 5M / (4G + N), so an
item raises F2 whenever its match probability exceeds F2 / 5 (about 0.12 here). Main-text sections of the selected
regulations match far above that on dev and holdout-acpe, so we keep them all and drop only whole sections whose
subject is not the product.

Usage:
    python -m certi.scope_filter --run runs/heldout-front-bumper_d8b016a5 --out outputs/predictions_front_bumper_scope.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .llm import CachedLLMClient

EXP_DIR = Path(__file__).resolve().parent.parent
CLAUSES_DIR = EXP_DIR.parents[2] / "data-ingestion" / "clauses"

KEEP_LABELS = {"A_product", "B_test_on_product"}
LABELS = ["A_product", "B_test_on_product", "C_test_tool", "D_other_object", "E_non_normative"]
SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string", "enum": LABELS},
                    "reason": {"type": "string"},
                },
                "required": ["id", "label", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sections"],
    "additionalProperties": False,
}


def section_key(paragraph: str) -> tuple[str, str]:
    """('main', '6.3') for '6.3.1.2'; ('annex', 'Annex 5 / 2') for 'Annex 5 2.4' or 'Annex 6 Part 6 3.1'."""
    p = str(paragraph).strip()
    m = re.match(r"(Annex \d+)\s*(?:/\s*)?(Part [A-Z0-9]+)?\s*(\d+)?", p)
    if m:
        base = m.group(1) + (f" {m.group(2)}" if m.group(2) else "")
        return "annex", base + (f" / {m.group(3)}" if m.group(3) else "")
    m = re.match(r"(\d+)(?:\.(\d+))?", p)
    if m:
        return "main", m.group(1) + (f".{m.group(2)}" if m.group(2) else "")
    return "main", p[:20]


def load_headings() -> dict[str, list[tuple[str, int, str]]]:
    """regulation -> [(paragraph, first page, first line of text)]."""
    out: dict[str, list[tuple[str, int, str]]] = {}
    for f in sorted(CLAUSES_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        rows = out.setdefault(d["regulation"], [])
        for c in d["clauses"]:
            para = str(c.get("paragraph") or "").strip().rstrip(".")
            first = re.sub(r"^\S+\s*", "", c["text"].strip()).split("\n")[0]
            rows.append((para, int(c["pages"][0]) if c.get("pages") else 0, first[:90]))
    return out


def heading_for(rows: list[tuple[str, int, str]], kind: str, key: str, page: int) -> str:
    target = key.replace(" Part ", " Part ") if kind == "annex" else key
    cands = [(pg, txt) for para, pg, txt in rows if para == target and pg <= page]
    if not cands and kind == "annex":
        annex = key.split(" / ")[0].split(" Part ")[0]
        cands = [(pg, txt) for para, pg, txt in rows if para == annex and pg <= page]
    return max(cands)[1] if cands else ""


def build_sections(reqs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    headings = load_headings()
    sections: dict[str, dict[str, Any]] = {}
    item_section: list[str] = []
    for r in reqs:
        s = r["source"]
        kind, key = section_key(s.get("paragraph", ""))
        # Page bucket separates restarted numbering in one document (e.g. GTR rationale vs regulation text).
        page_bucket = s["page"] // 40
        sid = f"{s['regulation']} | {key} | p{page_bucket}"
        if sid not in sections:
            sections[sid] = {
                "id": sid,
                "regulation": s["regulation"],
                "paragraph": key,
                "heading": heading_for(headings.get(s["regulation"], []), kind, key, s["page"]),
                "first_page": s["page"],
                "samples": [],
                "n_items": 0,
            }
        sec = sections[sid]
        sec["n_items"] += 1
        if len(sec["samples"]) < 3:
            sec["samples"].append(r["text"][:200])
        item_section.append(sid)
    return list(sections.values()), item_section


# Words in part names that describe a role or a generic shape rather than a concrete object.
ROLE_WORDS = {
    "front", "rear", "side", "part", "parts", "sensor", "sensors", "impact", "pedestrian", "lighting", "light", "lamp",
    "temperature", "thermal", "cover", "device", "unit", "module", "system", "housing", "housings", "lens", "lenses",
    "bracket", "brackets", "fastener", "fasteners", "clip", "clips", "wiring", "area", "holder", "decorative",
    "signalling", "structure", "assembly", "control", "software", "function", "with", "incl", "heating", "lower", "upper",
    "member", "cross", "plate", "protection", "entry", "guide", "guides", "port", "insert", "inserts", "trim", "trims",
}


def _singular(w: str) -> str:
    return w[:-1] if w.endswith("s") and not w.endswith("ss") else w


def part_vocab(product: dict[str, Any]) -> set[str]:
    words = set()
    for p in product["parts"]:
        for w in re.findall(r"[a-z]+", p["name"].lower()):
            if len(w) > 3 and w not in ROLE_WORDS:
                words.add(_singular(w))
    return words | {"vehicle"}


def names_product(text: str, vocab: set[str]) -> bool:
    return any(_singular(w) in vocab for w in re.findall(r"[a-z]+", text.lower()))


def run_scope_filter(run_dir: Path, out_path: Path, model: str = "claude-opus-5-5") -> dict[str, Any]:
    rich = json.loads((run_dir / "requirements_rich.json").read_text(encoding="utf-8"))
    product = json.loads((run_dir / "stage1_product.json").read_text(encoding="utf-8"))
    reqs = rich["requirements"]
    sections, item_section = build_sections(reqs)

    profile = {
        "product": product["product"],
        "vehicle_categories": product["vehicle_categories"],
        "parts": [{"name": p["name"], "function": p["function"]} for p in product["parts"]],
    }
    payload = {
        "product_profile": profile,
        "sections": [{k: s[k] for k in ("id", "regulation", "paragraph", "heading", "samples")} for s in sections],
    }
    llm = CachedLLMClient(use_cache=True)
    result = llm.call_json(
        stage="stage6_section_scope",
        model=model,
        prompt_file="stage6_section_scope_v1.md",
        user_payload=payload,
        schema=SCHEMA,
        max_tokens=16000,
    )
    labels = {x["id"]: x for x in result["sections"]}
    # Unlabelled sections are kept (recall first). Inside test-tool sections, an item that names the vehicle or one of
    # the product's parts describes the tool acting on the product (impact speed, impact point, measured vehicle
    # quantity), so it is kept too.
    vocab = part_vocab(product)
    kept = []
    for r, sid in zip(reqs, item_section):
        label = labels.get(sid, {}).get("label", "A_product")
        if label in KEEP_LABELS or (label == "C_test_tool" and names_product(r["text"], vocab)):
            kept.append(r)

    doc = {
        "team_id": rich.get("team_id", "team-11"),
        "case_id": rich["case_id"],
        "requirements": [
            {"id": f"R-{i:04d}", "text": r["text"], "source": r["source"]} for i, r in enumerate(kept, 1)
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report = [
        {**{k: s[k] for k in ("id", "heading", "n_items")}, **labels.get(s["id"], {"label": "A_product", "reason": "unlabelled"})}
        for s in sections
    ]
    (run_dir / "stage6_section_scope.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[Stage 6] {len(sections)} sections, kept {len(kept)}/{len(reqs)} requirements -> {out_path}")
    print(f"          LLM API calls: {llm.stats['api_calls']} (cache hits: {llm.stats['cache_hits']}), "
          f"tokens in/out: {llm.stats['input_tokens']}/{llm.stats['output_tokens']}")
    return {"sections": report, "kept": len(kept), "total": len(reqs)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, required=True, help="runs/<run_id> directory with requirements_rich.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default="claude-opus-5-5")
    args = ap.parse_args(argv)
    run_scope_filter(args.run, args.out, model=args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
