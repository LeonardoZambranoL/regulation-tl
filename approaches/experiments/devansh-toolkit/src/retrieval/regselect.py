"""Regulation selection: which of the citeable UN Regulations apply to a product spec?

The oracle experiments show this is the biggest lever (perfect selection doubles page F1), so it runs before retrieval:
pipelines with "select": {"method": ...} only search inside the selected regulations.

    python -m retrieval.regselect                         # every method on the dev case, scored against the gold regulations
    python -m retrieval.regselect --method combined --spec path/to/spec.md
    python -m retrieval.regselect --method llm --print-prompt   # no API key? paste the prompt into Claude yourself

Methods (all but llm need no API key):
  rules     - generic domain rules: spec keywords -> regulations (lamp -> R48 installation, stop/position lamp -> R148, ...)
  scope     - BM25 between spec queries and each regulation's title + Scope (paragraph 1), top k
  retrieval - vote of the pooled clause search (what the bench used before), top k
  combined  - rules, falling back to scope when no rule fires; default
  llm       - Claude reads the spec + every regulation's title / scope / supersession note (needs ANTHROPIC_API_KEY or an
              `ant auth login` profile, and `pip install anthropic`)
Every method then applies two filters derived from the regulation texts themselves:
  supersession - R148/R149/R150 state which older regulations they combine ("combines the provisions of individual UN
                 Regulations Nos. 4, 6, 7, 23 ..."); when the new one is selected, the old ones are dropped
  category     - a regulation whose Scope only names vehicle categories other than the spec's (e.g. L3-only R53 for an M1
                 car) is dropped
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .corpus import LLM_CACHE_DIR, CLAUSE_DIR, DEFAULT_CHALLENGE_DIR, Chunk, load_index
from .pipeline import Pipeline, spec_queries
from .retrievers.lexical import BM25

HERE = Path(__file__).resolve().parent


@dataclass
class Profile:
    regulation: str
    title: str
    scope: str
    supersedes: set[str] = field(default_factory=set)
    categories: set[tuple[str, str]] = field(default_factory=set)  # ("M", "1"), ("L", ""), ...


_COMBINES = re.compile(r"provisions of (?:the )?individual UN Regulations Nos?\.?\s*([\d,\sand]+)", re.IGNORECASE)
# "M1", "N", "L3" - a footnote digit may follow ("category L31" = L3 + footnote 1); "The" / "This" must not match
_CATEGORY = re.compile(r"\b([LMNO])([1-7])?(?=\d?\b)")


def load_profiles(clause_dir: Path = CLAUSE_DIR, challenge_dir: Path = DEFAULT_CHALLENGE_DIR) -> dict[str, Profile]:
    index = load_index(challenge_dir)
    profiles = {}
    for path in sorted(Path(clause_dir).glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        clauses = doc["clauses"]
        scope_parts = [c["text"] for c in clauses if re.fullmatch(r"1(\.\d+)*", c["paragraph"] or "")]
        scope = " ".join(" ".join(scope_parts).split())[:1500]
        intro = " ".join(c["text"] for c in clauses[:2] if c["paragraph"] is None)
        supersedes = set()
        if m := _COMBINES.search(intro.replace("\r\n", " ")):
            supersedes = {f"UN R{n}" for n in re.findall(r"\d+", m.group(1))} & set(index)
        categories = {(a, b or "") for a, b in _CATEGORY.findall(scope[:600]) if "categor" in scope[:600].lower()}
        profiles[doc["regulation"]] = Profile(doc["regulation"], index.get(doc["regulation"], {}).get("title", ""),
                                              scope, supersedes, categories)
    return profiles


def spec_category(spec: str) -> tuple[str, str] | None:
    """'M1 — passenger car' -> ("M", "1")."""
    m = re.search(r"vehicle category[^\n]*\n+\s*([LMNOT])([1-7])?", spec, re.IGNORECASE)
    return (m.group(1), m.group(2) or "") if m else None


# ---- rules: generic domain knowledge, one line per family of products ----------------------------------------------------
# (reason, pattern on the spec text, regulations). Keep them general: they must work for the held-out product too.
RULES: list[tuple[str, str, list[str]]] = [
    ("lighting / light-signalling device -> installation on M, N, O vehicles",
     r"\b(lamps?|lighting|light[- ]signall?ing|headlamps?|retro-?reflect\w*|reflectors?)\b", ["UN R48"]),
    ("light-signalling lamp (position, stop, indicator, reversing, fog, parking, DRL, marker, plate lamp)",
     r"(position lamp|stop lamp|brake lamp|braking indication|direction indicator|turn signal|reversing|rear fog|"
     r"parking lamp|side marker|end-outline|daytime running|registration plate|manoeuvring lamp|tail ?lamp|rear lamp)",
     ["UN R148"]),
    ("road illumination (headlamp, front fog, cornering, AFS)",
     r"(head ?lamp|driving[- ]beam|passing[- ]beam|front fog|cornering lamp|adaptive front[- ]lighting|\bAFS\b)",
     ["UN R149"]),
    ("retro-reflective device / marking / warning triangle",
     r"(retro-?reflect|reflex reflector|warning triangle|marking plate|conspicuity marking)", ["UN R150"]),
    ("electrical / electronic sub-assembly -> EMC",
     r"\b(LEDs?|PCBs?|printed circuit|electronic\w*|ECU|control unit|sensors?|camera|radar|lidar|wiring|harness|"
     r"electric motor|actuators?)\b", ["UN R10"]),
    ("replaceable LED light source", r"(LED light source|LED substitute|replaceable LED)", ["UN R128"]),
    ("filament light source", r"(filament|halogen|incandescent|bulb)", ["UN R37"]),
    ("safety glazing", r"(glazing|windscreen|windshield|window pane|sunroof glass)", ["UN R43"]),
    ("light-vehicle braking system", r"(brake (system|disc|caliper|pad)|braking system|\bABS\b)", ["UN R13H"]),
    ("steering equipment", r"\bsteering (system|column|gear|wheel|equipment)", ["UN R79"]),
    ("safety-belt reminder", r"(seat[- ]?belt reminder|belt reminder)", ["UN R174"]),
    ("replacement airbag module", r"(replacement airbag|airbag module)", ["UN R114"]),
    ("vehicle alarm", r"\balarm\b", ["UN R163", "UN R116"]),
    ("immobiliser", r"immobili[sz]er", ["UN R162", "UN R116"]),
    ("protection against unauthorised use", r"(steering lock|unauthori[sz]ed use)", ["UN R161"]),
    ("connected / software-updatable component", r"(cyber|telematic|connectivity|over[- ]the[- ]air|\bOTA\b|"
     r"wireless|bluetooth|cellular)", ["UN R155"]),
    ("software update capability", r"(software update|over[- ]the[- ]air|\bOTA\b|firmware update)", ["UN R156"]),
    ("speedometer / odometer", r"(speedometer|odometer)", ["UN R39"]),
    ("speed limitation device", r"speed limit(ation|er)", ["UN R89"]),
    ("emergency braking (light vehicles)", r"(emergency braking|\bAEBS?\b)", ["UN R152"]),
    ("automated lane keeping", r"(lane keeping|\bALKS\b)", ["UN R157"]),
    ("driver control assistance", r"(driver control assistance|\bDCAS\b|lane change assist|adaptive cruise)", ["UN R171"]),
    ("acceleration control for pedal error", r"(pedal (error|misapplication)|acceleration control)", ["UN R175"]),
    ("front / rear protective devices", r"(bumper|front protective|rear protective)", ["UN R42"]),
    ("external projections", r"(external projection|exterior trim|ornament|hub ?cap|wheel nut)", ["UN R26"]),
    ("pedestrian protection (front end)", r"(bonnet|front[- ]end module|pedestrian)", ["UN R127", "UN GTR 9"]),
    ("spare unit / run-flat / tyre pressure", r"(spare (wheel|unit)|run[- ]?flat|tyre pressure|\bTPMS\b)", ["UN R64"]),
    ("studded tyres", r"studded tyre", ["UN R164"]),
    ("electric powertrain / traction battery", r"(traction battery|high[- ]voltage|electric power ?train|\bREESS\b)",
     ["UN R100"]),
    ("LPG system", r"\bLPG\b", ["UN R67"]),
    ("close-coupling device", r"close[- ]coupling", ["UN R102"]),
    ("replacement pollution control device", r"(catalytic converter|pollution control device|particulate filter)",
     ["UN R103"]),
    ("replacement exhaust silencer (motorcycles)", r"(silencer|exhaust silencing)", ["UN R92"]),
]


def select_rules(spec: str, profiles: dict[str, Profile]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = defaultdict(list)
    for reason, pattern, regs in RULES:
        if re.search(pattern, spec, re.IGNORECASE):
            for r in regs:
                if r in profiles:
                    hits[r].append(reason)
    if (cat := spec_category(spec)) and cat[0] == "L" and "UN R48" in hits:  # L3 vehicles: R53 replaces R48
        hits["UN R53"] = hits.pop("UN R48")
    return dict(hits)


def rank_scope(spec: str, profiles: dict[str, Profile]) -> list[tuple[str, float]]:
    """BM25 over one pseudo-document per regulation: title (x3) + scope."""
    regs = list(profiles)
    docs = [Chunk(i, r, "", 1, None, " ".join([profiles[r].title] * 3) + " " + profiles[r].scope) for i, r in enumerate(regs)]
    bm25 = BM25(with_title=False).fit(docs)
    score: dict[str, float] = defaultdict(float)
    for q in spec_queries(spec):
        for rank, h in enumerate(bm25.search(q, k=10)):
            score[regs[h.chunk_id]] += 1 / (10 + rank + 1)
    return sorted(score.items(), key=lambda x: -x[1])


def rank_retrieval(spec: str, pipe: Pipeline) -> list[tuple[str, float]]:
    score: dict[str, float] = defaultdict(float)
    for c, s in pipe.pooled(spec_queries(spec), k_per_query=200):
        score[c.regulation] += s
    return sorted(score.items(), key=lambda x: -x[1])


def llm_prompt(spec: str, profiles: dict[str, Profile]) -> str:
    lines = [f"- {p.regulation}: {p.title}. Scope: {p.scope[:400]}"
             + (f" (Supersedes: {', '.join(sorted(p.supersedes))})" if p.supersedes else "") for p in profiles.values()]
    return (
        "You are a UNECE type-approval expert. A company builds the product below. List every UN Regulation from the "
        "catalogue whose requirements the product (the component itself, its installation on the vehicle, and its "
        "electrical/electronic parts) must fulfil. Prefer the consolidated regulations over the ones they supersede. "
        "Exclude regulations for other vehicle categories or other systems. Be precise: every extra regulation costs "
        "precision.\n\n<spec>\n" + spec + "\n</spec>\n\n<catalogue>\n" + "\n".join(lines) + "\n</catalogue>"
    )


def select_llm(spec: str, profiles: dict[str, Profile]) -> dict[str, list[str]]:
    from .llm import structured

    schema = {
        "type": "object",
        "properties": {"regulations": {"type": "array", "items": {
            "type": "object",
            "properties": {"regulation": {"type": "string", "enum": sorted(profiles)}, "reason": {"type": "string"}},
            "required": ["regulation", "reason"], "additionalProperties": False}}},
        "required": ["regulations"], "additionalProperties": False,
    }
    data = structured(llm_prompt(spec, profiles), schema)
    out: dict[str, list[str]] = defaultdict(list)
    for item in data["regulations"]:
        out[item["regulation"]].append(item["reason"])
    return dict(out)


REGEX_PROMPT = """You help find which UN vehicle regulations (UNECE) apply to a product. You only see the product
specification, not the list of regulations. Write regular expressions that will be searched (case-insensitive) in the
TITLE and SCOPE paragraph of every UN Regulation, written in UNECE regulatory English (for example "light-signalling
devices", "retro-reflecting devices", "electrical/electronic sub-assemblies", "installation of lighting").

Write 6 to 20 patterns covering the product's own functions, components, materials that have their own regulations,
its installation on the vehicle, and its electrical / electronic content. Each pattern must be specific to this product:
never a generic word that appears in every regulation (vehicle, approval, regulation, type, category, device alone).
Allow spelling variants (hyphens, plurals: e.g. "retro-?reflect"). Use Python regex syntax.

<spec>
{spec}
</spec>"""


def regex_patterns(spec: str) -> list[dict]:
    """Claude writes regexes from the spec alone (cached per spec); invalid patterns are dropped."""
    from .llm import structured
    key = hashlib.sha1(REGEX_PROMPT.format(spec=spec).encode()).hexdigest()[:12]
    cache = LLM_CACHE_DIR / f"regselect_llmregex_{key}.json"
    if cache.is_file():
        patterns = json.loads(cache.read_text(encoding="utf-8"))
    else:
        schema = {"type": "object", "properties": {"patterns": {"type": "array", "items": {
            "type": "object", "properties": {"regex": {"type": "string"}, "meaning": {"type": "string"}},
            "required": ["regex", "meaning"], "additionalProperties": False}}},
            "required": ["patterns"], "additionalProperties": False}
        patterns = structured(REGEX_PROMPT.format(spec=spec), schema)["patterns"]
        LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(patterns, indent=2), encoding="utf-8")
    valid = []
    for p in patterns:
        try:
            re.compile(p["regex"], re.IGNORECASE)
            valid.append(p)
        except re.error:
            pass
    return valid


def select_llm_regex(spec: str, profiles: dict[str, Profile]) -> dict[str, list[str]]:
    """Dynamic regex: run the spec-derived patterns over each regulation's title + scope; any match selects it."""
    chosen: dict[str, list[str]] = {}
    for p in regex_patterns(spec):
        rx = re.compile(p["regex"], re.IGNORECASE)
        for reg, prof in profiles.items():
            if rx.search(prof.title + " . " + prof.scope):
                chosen.setdefault(reg, []).append(f"/{p['regex']}/ ({p['meaning']})")
    return chosen


def apply_filters(selected: dict[str, list[str]], spec: str, profiles: dict[str, Profile]) -> dict[str, list[str]]:
    out = dict(selected)
    for reg in list(out):  # supersession, as stated by the consolidated regulation itself
        for old in profiles[reg].supersedes if reg in profiles else ():
            out.pop(old, None)
    if cat := spec_category(spec):
        for reg in list(out):
            cats = profiles[reg].categories if reg in profiles else set()
            if cats and not any(c == cat[0] and (not n or not cat[1] or n == cat[1]) for c, n in cats):
                out.pop(reg)
    return out


def select(spec: str, method: str = "combined", k: int = 4, pipe: Pipeline | None = None,
           profiles: dict[str, Profile] | None = None) -> dict[str, list[str]]:
    """{regulation: [reasons]} for the spec."""
    profiles = profiles or load_profiles()
    if method == "rules":
        chosen = select_rules(spec, profiles)
    elif method in ("scope", "retrieval"):
        if method == "scope":
            ranked = rank_scope(spec, profiles)
        else:
            ranked = rank_retrieval(spec, pipe or Pipeline.from_file(HERE / "configs" / "bm25plus_bigrams.json"))
        # filter the whole ranking first, so superseded / wrong-category regulations do not use up the k slots
        kept = apply_filters({r: [f"{method} rank {i + 1}"] for i, (r, _) in enumerate(ranked)}, spec, profiles)
        return dict(list(kept.items())[:k])
    elif method == "combined":
        chosen = select_rules(spec, profiles) or select(spec, "scope", k, profiles=profiles)
    elif method == "llm":
        # cached per (spec, prompt) so benchmarks do not pay for the same call twice
        prompt_key = hashlib.sha1(llm_prompt(spec, profiles).encode()).hexdigest()[:12]
        cache = LLM_CACHE_DIR / f"regselect_llm_{prompt_key}.json"
        if cache.is_file():
            chosen = json.loads(cache.read_text(encoding="utf-8"))
        else:
            chosen = select_llm(spec, profiles)
            LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(chosen, indent=2), encoding="utf-8")
    elif method == "llm_regex":
        chosen = select_llm_regex(spec, profiles)
    else:
        raise ValueError(f"unknown method {method!r}")
    return apply_filters(chosen, spec, profiles)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--method", default="all", help="rules | scope | retrieval | combined | llm | all (no llm)")
    ap.add_argument("--case", default="dev-rear-lamp")
    ap.add_argument("--challenge-dir", default=str(DEFAULT_CHALLENGE_DIR))
    ap.add_argument("--spec", help="a spec.md (default: the case's)")
    ap.add_argument("-k", type=int, default=4, help="how many regulations the ranking methods keep")
    ap.add_argument("--print-prompt", action="store_true", help="print the llm prompt instead of calling the API")
    args = ap.parse_args(argv)

    case_dir = Path(args.challenge_dir) / "cases" / args.case
    spec = Path(args.spec or case_dir / "spec.md").read_text(encoding="utf-8")
    profiles = load_profiles(challenge_dir=Path(args.challenge_dir))
    if args.print_prompt:
        print(llm_prompt(spec, profiles))
        return 0
    expected = case_dir / "expected.json"
    gold = ({r["source"]["regulation"] for r in json.loads(expected.read_text(encoding="utf-8"))["requirements"]}
            if expected.is_file() and not args.spec else None)
    methods = ["rules", "scope", "retrieval", "combined"] if args.method == "all" else [args.method]
    for m in methods:
        chosen = select(spec, m, args.k, profiles=profiles)
        line = f"{m:<10} {sorted(chosen)}"
        if gold:
            tp = len(gold & set(chosen))
            p, r = tp / max(len(chosen), 1), tp / len(gold)
            line += f"   P {p:.2f} R {r:.2f} F1 {2 * p * r / (p + r) if p + r else 0:.2f}"
        print(line)
        if args.method != "all":
            for reg, reasons in sorted(chosen.items()):
                print(f"   {reg:<9} {'; '.join(reasons)}")
    if gold:
        print(f"gold       {sorted(gold)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
