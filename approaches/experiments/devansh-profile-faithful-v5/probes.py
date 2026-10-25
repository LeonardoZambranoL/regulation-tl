"""Build bumper probe files from v5 (zero API: ranker answers come from the cache; aborts if a call would be needed)."""
import json, re, sys, collections
from pathlib import Path

ROOT = Path(r"C:\Users\devan\Desktop\Competitions\Hackathon- Certify\regulation-tl\approaches\experiments")
sys.path.insert(0, str(ROOT / "devansh-toolkit" / "src"))
import retrieval.llm as llm
def no_api(*a, **k):
    raise SystemExit("would call the API - aborted")
llm.structured = no_api
from retrieval import refine

V3, V5 = ROOT / "devansh-profile-faithful-v3" / "outputs", ROOT / "devansh-profile-faithful-v5" / "outputs"
OUT = V5 / "probes"; OUT.mkdir(exist_ok=True)
spec = (V3 / "spec-with-profile-heldout-front-bumper.md").read_text(encoding="utf-8")
raw = json.loads((V3 / "raw-heldout-front-bumper.json").read_text(encoding="utf-8"))["requirements"]
v5 = json.loads((V5 / "ranked-heldout-front-bumper.json").read_text(encoding="utf-8"))["requirements"]

unique = refine.dedupe(raw)
ratings = refine.rank(spec, unique)                      # cached answers only
key = lambda r: (r["text"], r["source"]["regulation"], r["source"].get("paragraph"), r["source"]["page"])
in_v5 = {key(r) for r in v5}
rated1 = [r for r in unique if ratings.get(r["id"], 5) <= 1 and key(r) not in in_v5]

FAMILIES = {
    "direction-indicator": (r"direction[- ]indicator|hazard[- ]warning|emergency stop signal", ("6.5", "6.6", "6.23")),
    "front-position": (r"front position lamp|front and rear position lamps|position lamps?\b(?!.*rear)", ("6.9",)),
    "side-marker": (r"side[- ]marker", ("6.18",)),
    "daytime-running": (r"daytime running", ("6.19",)),
}
def family(r):
    if r["source"]["regulation"] not in ("UN R48", "UN R148"):
        return None
    t = r["text"].lower(); p = str(r["source"].get("paragraph") or "")
    hits = {f for f, (rx, secs) in FAMILIES.items()
            if re.search(rx, t) or (r["source"]["regulation"] == "UN R48" and any(p == s or p.startswith(s + ".") for s in secs))}
    return hits.pop() if len(hits) == 1 else None      # items about several functions (general rules) stay in every probe

blocks = collections.defaultdict(list)
for r in v5:
    f = family(r)
    if f:
        blocks[f].append(r)

def write(name, reqs):
    out = []
    for i, r in enumerate(reqs, 1):
        src = {k: r["source"][k] for k in ("regulation", "version", "page", "paragraph") if r["source"].get(k) not in (None, "")}
        out.append({"id": f"R-{i:04d}", "text": r["text"][:2000], "source": src})
    p = OUT / f"{name}.json"
    p.write_text(json.dumps({"team_id": "team-11", "case_id": "heldout-front-bumper", "requirements": out}, indent=2, ensure_ascii=False), encoding="utf-8")
    return p, len(out)

plan = [("1-v5", v5, "baseline (v3 + 11 mirrored)"),
        ("2-v5-plus-rated1", v5 + rated1, f"+{len(rated1)} items the ranker rated 1 ('certainly not')")]
n = 3
for f in ("direction-indicator", "front-position", "side-marker", "daytime-running"):
    ids = {id(r) for r in blocks[f]}
    plan.append((f"{n}-v5-minus-{f}", [r for r in v5 if id(r) not in ids], f"-{len(blocks[f])} {f} items"))
    n += 1
manifest = []
for name, reqs, what in plan:
    p, cnt = write(name, reqs)
    manifest.append({"file": p.name, "requirements": cnt, "change": what})
    print(f"{p.name:40s} {cnt:4d}  {what}")
(OUT / "manifest.json").write_text(json.dumps({"manifest": manifest,
    "blocks": {f: [{"regulation": r["source"]["regulation"], "paragraph": r["source"].get("paragraph"), "text": r["text"][:160]} for r in rs] for f, rs in blocks.items()},
    "rated1": [{"regulation": r["source"]["regulation"], "paragraph": r["source"].get("paragraph"), "text": r["text"][:160]} for r in rated1]},
    indent=2, ensure_ascii=False), encoding="utf-8")
print("rated1 by regulation:", collections.Counter(r["source"]["regulation"] for r in rated1))
