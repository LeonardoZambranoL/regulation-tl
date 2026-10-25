"""Stage 6b — Lamp-function presence filter (one LLM call per case on spec + drawing; deterministic item filter).

The Stage 1 product profile can over-generalise lighting (e.g. "signalling lamp, e.g. side marker / direction indicator /
position lamp"), and every lamp function then pulls in its own R48 / R148 sections. This step asks once, from the raw
specification and drawing only, which lamp functions are physically present, then drops every requirement whose text
names lamp functions and none of them is present. Requirements that name no lamp function are untouched.

Usage:
    python -m certi.lamp_functions --case heldout-front-bumper --in outputs/x.json --out outputs/y.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .llm import CachedLLMClient
from .stages.stage0_load import load_stage0

# R48 lamp functions, with the phrases that name them in requirement text.
FUNCTIONS: dict[str, str] = {
    "main-beam / dipped-beam headlamp": r"\b(main[- ]beam|dipped[- ]beam|driving[- ]beam|passing[- ]beam|headlamps?)\b",
    "front fog lamp": r"\bfront fog\b",
    "rear fog lamp": r"\brear fog\b",
    "direction indicator lamp (incl. hazard warning)": r"\b(direction[- ]indicators?|hazard[- ]warning|turn signal)\b",
    "front position lamp": r"\bfront position\b",
    "rear position lamp": r"\brear position\b",
    "stop lamp": r"\b(stop lamps?|high[- ]mounted stop|s[1-4] (or s[1-4] )?categor\w*)\b",
    "reversing lamp": r"\b(reversing lamps?|reversing light)\b",
    "rear registration plate lamp": r"\b(rear[- ]registration[- ]plate (illuminating )?lamps?)\b",
    "end-outline marker lamp": r"\bend[- ]outline\b",
    "side-marker lamp": r"\bside[- ]marker\b",
    "daytime running lamp": r"\b(daytime running|\bdrl\b)",
    "parking lamp": r"\bparking lamps?\b",
    "cornering lamp": r"\bcornering lamps?\b",
    "manoeuvring lamp": r"\bmanoeuvring lamps?\b",
    "exterior courtesy lamp": r"\bexterior courtesy\b",
    "retro-reflector": r"\b(retro-?reflectors?|retro-?reflective devices?)\b",
}
FUNCTION_RX = {k: re.compile(v, re.I) for k, v in FUNCTIONS.items()}
SCHEMA = {
    "type": "object",
    "properties": {
        "functions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "present": {"type": "boolean"}, "evidence": {"type": "string"}},
                "required": ["name", "present", "evidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["functions"],
    "additionalProperties": False,
}


def present_functions(case: str, model: str = "claude-opus-5-5") -> dict[str, Any]:
    corpus = load_stage0(case)
    llm = CachedLLMClient(use_cache=True)
    out = llm.call_json(
        stage="stage6b_lamp_functions",
        model=model,
        prompt_file="stage6b_lamp_functions_v1.md",
        user_payload={"specification": corpus.spec_text, "functions": list(FUNCTIONS)},
        schema=SCHEMA,
        image_path=corpus.image_path,
        max_tokens=4000,
    )
    return {f["name"]: f for f in out["functions"]}


EXCEPTION_RX = re.compile(r"\(\s*(other than|except)[^)]*\)|\b(other than|with the exception of|except(?: for)?)\b[^.;:]*", re.I)


def named_functions(text: str) -> set[str]:
    """Lamp functions a requirement is about; functions named only as exceptions do not count."""
    text = EXCEPTION_RX.sub(" ", text)
    return {k for k, rx in FUNCTION_RX.items() if rx.search(text)}


# Pedestrian-protection test zones that belong to other vehicle parts than a bumper / front-end module.
OTHER_ZONE_RX = re.compile(r"\b(headform|hic(1000|1700)?|head impact|hit_[ds]|bonnet top|bonnet leading edge|windscreen|"
                           r"a-pillar|wrap around distance|wad\b|fire delay)", re.I)
OWN_ZONE_RX = re.compile(r"\b(bumper|legform|flexpli|sensing|sensor|front structure)", re.I)
ZONE_OBJECTS_RX = re.compile(r"\b(bonnet|hood|windscreen|windshield|a-pillar)\b", re.I)


# Lighting regulations whose numbered sections each cover one lamp function (R48 6.N installation, R148 5.N device).
FUNCTION_SECTION_RX = {"UN R48": re.compile(r"^(6\.\d+)\b"), "UN R148": re.compile(r"^(5\.\d+)\b")}
_HEADINGS: dict[str, dict[str, str]] = {}


def section_heading(regulation: str, paragraph: str) -> str:
    rx = FUNCTION_SECTION_RX.get(regulation)
    m = rx.match(str(paragraph).strip()) if rx else None
    if not m:
        return ""
    if regulation not in _HEADINGS:
        from .scope_filter import CLAUSES_DIR
        heads: dict[str, str] = {}
        for f in CLAUSES_DIR.glob("*.json"):
            d = json.loads(f.read_text(encoding="utf-8"))
            if d["regulation"] == regulation:
                for c in d["clauses"]:
                    para = str(c.get("paragraph") or "").strip().rstrip(".")
                    heads.setdefault(para, re.sub(r"^\S+\s*", "", c["text"].strip()).split("\n")[0][:80])
        _HEADINGS[regulation] = heads
    return _HEADINGS[regulation].get(m.group(1), "")


def filter_items(reqs: list[dict[str, Any]], present: set[str], spec_text: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop items about lamp functions the product lacks (named in the item or in its per-function section heading),
    and (if the spec names no bonnet / windscreen) items about head-impact zones that are not on the product."""
    zone_absent = not ZONE_OBJECTS_RX.search(spec_text)
    kept, dropped = [], []
    for r in reqs:
        t = r["text"]
        own = named_functions(t)
        heading = named_functions(section_heading(r["source"]["regulation"], r["source"].get("paragraph", "")))
        named = own if own & present else own | heading
        off_lamp = bool(named) and not (named & present)
        off_zone = zone_absent and bool(OTHER_ZONE_RX.search(t)) and not OWN_ZONE_RX.search(t)
        (dropped if off_lamp or off_zone else kept).append(r)
    return kept, dropped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    funcs = present_functions(args.case)
    present = {k for k, v in funcs.items() if v["present"]}
    print("[Stage 6b] present lamp functions:", {k: funcs[k]["evidence"] for k in present})
    doc = json.loads(args.inp.read_text(encoding="utf-8"))
    spec_text = load_stage0(args.case).spec_text
    kept, dropped = filter_items(doc["requirements"], present, spec_text)
    for i, r in enumerate(kept, 1):
        r["id"] = f"R-{i:04d}"
    doc["requirements"] = kept
    args.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[Stage 6b] kept {len(kept)}, dropped {len(dropped)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
