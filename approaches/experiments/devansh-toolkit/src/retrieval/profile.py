"""Product profile: Claude reads the spec AND the exploded-view image and writes down what the product is, so every
later step (regulation selection, clause choice, writing, final check) decides from the same, richer description.

The image of a case is not decoration: its callouts name performance targets ("stop lamp: 60 to 185 cd on axis",
"no water ingress after the spray test", "reversing lamp visible to 45 degrees outboard"), each pointing at specific
regulation paragraphs. The raw spec alone also leaves configuration implicit (several functions in one housing = a
grouped / combined lamp; LED modules on a PCB = light source modules + electronics).

    python -m retrieval.profile --case dev-rear-lamp        # prints the profile; cached per (spec, image) in .cache/
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .corpus import LLM_CACHE_DIR, DEFAULT_CHALLENGE_DIR, REPO_ROOT

PROMPT = """You are a UNECE type-approval engineer starting a compliance file. Read the product specification below and,
if attached, the exploded-view image with its callouts. Write a precise product profile that later steps use to decide
which regulation clauses apply. Use only what the spec and image state or directly imply; mark everything else unknown.

Capture:
- product: one-sentence description; vehicle categories it is for; where it is mounted on the vehicle.
- functions: every function the product performs (use regulation terms where clear, e.g. "rear position lamp",
  "stop lamp", "reversing lamp", "rear retro-reflector"), with the category/class if stated or implied.
- components: every part with its material and what it does.
- configuration: how functions are combined (one housing / one lens for several functions = grouped, combined or
  reciprocally incorporated lamps), light-source technology (LEDs, light source modules, replaceable or not if stated),
  electronics (PCB, control gear), mounting / aiming.
- performance_callouts: every numeric or test target stated in the image or spec, verbatim, with the component it
  belongs to (e.g. "stop lamp: 60 to 185 cd on axis").
- present_features: optional features the spec or image state the product HAS.
- absent_or_unknown_features: optional features a regulation might ask about that are NOT stated (e.g. variable
  intensity control, replaceable light sources, sequential activation, logos), so rules conditional on them are judged
  carefully.
- regulation_topics: the requirement topics an expert would expect for this product (marking, colour, photometry,
  geometric visibility, installation position and number, electrical connection, EMC, water / dust / heat / corrosion
  tests, mechanical robustness ...), each with the product feature that triggers it."""

SCHEMA = {"type": "object", "properties": {
    "product": {"type": "string"}, "vehicle_categories": {"type": "string"}, "mounting": {"type": "string"},
    "functions": {"type": "array", "items": {"type": "string"}},
    "components": {"type": "array", "items": {"type": "string"}},
    "configuration": {"type": "array", "items": {"type": "string"}},
    "performance_callouts": {"type": "array", "items": {"type": "string"}},
    "present_features": {"type": "array", "items": {"type": "string"}},
    "absent_or_unknown_features": {"type": "array", "items": {"type": "string"}},
    "regulation_topics": {"type": "array", "items": {"type": "string"}}},
    "required": ["product", "vehicle_categories", "mounting", "functions", "components", "configuration",
                 "performance_callouts", "present_features", "absent_or_unknown_features", "regulation_topics"],
    "additionalProperties": False}


def find_image(case_dir: Path) -> Path | None:
    for name in ("exploded_view.png", "exploded_view.jpg", "exploded_view.jpeg"):
        if (case_dir / name).is_file():
            return case_dir / name
    images = sorted(case_dir.glob("*.png")) + sorted(case_dir.glob("*.jp*g"))
    return images[0] if images else None


def build_profile(spec: str, image: Path | None = None, effort: str = "high") -> dict:
    from .llm import structured
    key = hashlib.sha1((PROMPT + spec + (hashlib.sha1(image.read_bytes()).hexdigest() if image else "")).encode()).hexdigest()[:16]
    cache = LLM_CACHE_DIR / f"profile_{key}.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    profile = structured(f"{PROMPT}\n\n<spec>\n{spec}\n</spec>", SCHEMA, effort=effort,
                         images=[image] if image else None)
    LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return profile


def render(profile: dict) -> str:
    """Markdown block appended to the spec for every later step."""
    lines = ["", "## Product profile (derived from the spec and the exploded view)", "",
             f"- Product: {profile['product']}", f"- Vehicle categories: {profile['vehicle_categories']}",
             f"- Mounting: {profile['mounting']}"]
    for title, k in (("Functions", "functions"), ("Components", "components"), ("Configuration", "configuration"),
                     ("Performance targets (from image / spec)", "performance_callouts"),
                     ("Features the product HAS", "present_features"),
                     ("Optional features NOT stated in the spec (experts still list rules that apply only if such a "
                      "feature is used, written WITH their condition, e.g. 'In case replaceable light source modules "
                      "are used, ...': keep those rules and state the condition; drop only rules for functions or "
                      "components the product clearly does not have)", "absent_or_unknown_features"),
                     ("Requirement topics an expert expects", "regulation_topics")):
        lines.append(f"\n### {title}")
        lines += [f"- {x}" for x in profile[k]]
    return "\n".join(lines) + "\n"


def augment(spec: str, case_dir: Path, effort: str = "high") -> str:
    return spec + render(build_profile(spec, find_image(case_dir), effort))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default="dev-rear-lamp")
    ap.add_argument("--challenge-dir", default=str(DEFAULT_CHALLENGE_DIR))
    a = ap.parse_args(argv)
    case_dir = next(d for d in (Path(a.challenge_dir) / "cases" / a.case,
                                REPO_ROOT / "approaches" / "benchmarking" / "cases" / a.case) if d.is_dir())
    spec = (case_dir / "spec.md").read_text(encoding="utf-8")
    print(f"image: {find_image(case_dir)}")
    print(render(build_profile(spec, find_image(case_dir))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
