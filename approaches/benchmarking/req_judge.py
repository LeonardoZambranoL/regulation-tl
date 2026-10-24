"""Local stand-in for the platform's requirement-level score (the official one is only computed after upload).

    python approaches/benchmarking/req_judge.py <predictions.json> <expected.json> [--workers 6] [--effort medium]

The platform matches each submitted requirement one to one with an expected requirement "that states the same
engineering obligation (same scope, condition and constraint)"; precision = matched / submitted, recall = matched /
expected. Here Claude does that matching. To keep it cheap, a submitted requirement is only compared with expected
requirements of the same regulation cited at the same paragraph or within one page; connected groups are judged
together, so the one-to-one choice is made with all close alternatives in view.

Spends the Anthropic credits of whoever runs it (ANTHROPIC_API_KEY from the environment or the repo's .env). Answers
are cached in approaches/benchmarking/.cache/req_judge, so re-judging an unchanged file is free. It reads expected.json
only to score, like bench.py; never feed its output back into a prompt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(__file__).resolve().parent / ".cache" / "req_judge"
MODEL = "claude-opus-5-5"

PROMPT = """You are scoring a regulatory requirements extraction against an expert answer key, exactly like this rule:
"each submitted requirement is matched one to one with an expected requirement that states the same engineering
obligation (same scope, condition and constraint)."

Below are groups. In each group, match SUBMITTED items to EXPECTED items. A pair matches when the submitted item states
the same obligation as the expected one: same subject/scope, same condition, same constraint or value. Wording may
differ. A submitted item that bundles several obligations matches at most ONE expected item (pick the closest); an
expected item can be matched by at most one submitted item. Missing or different constraints, values or conditions
mean no match. Do not pair items from different groups.

{groups}

Return every matched pair as {{"s": <submitted id>, "e": <expected id>}}."""


def load_env() -> None:
    for path in (ROOT / ".env",):
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                key, sep, value = line.strip().partition("=")
                if sep and not key.startswith("#") and key.strip() not in os.environ:
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")


def para_key(p: str | None) -> str:
    """The platform's paragraph normalisation: case, spaces, commas and a closing dot do not matter."""
    return re.sub(r"[\s,]+", " ", (p or "").lower()).strip().rstrip(".").replace(" ", "")


def groups(sub: list[dict], exp: list[dict]) -> list[tuple[list[int], list[int]]]:
    """Connected components of 'could match' links (same regulation and same paragraph, or page within one)."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, s in enumerate(sub):
        a = s["source"]
        for j, e in enumerate(exp):
            b = e["source"]
            if a["regulation"] != b["regulation"]:
                continue
            same_para = a.get("paragraph") and para_key(a.get("paragraph")) == para_key(b.get("paragraph"))
            if same_para or abs(int(a["page"]) - int(b["page"])) <= 1:
                parent[find(("s", i))] = find(("e", j))
    comps: dict = {}
    for node in list(parent):
        comps.setdefault(find(node), []).append(node)
    out = []
    for nodes in comps.values():
        s_ids = sorted(i for k, i in nodes if k == "s")
        e_ids = sorted(j for k, j in nodes if k == "e")
        if s_ids and e_ids:
            out.append((s_ids, e_ids))
    return out


def judge_batch(batch: list[tuple[list[int], list[int]]], sub, exp, effort: str) -> list[tuple[int, int]]:
    text = []
    for g, (s_ids, e_ids) in enumerate(batch, 1):
        lines = [f"## Group {g}", "SUBMITTED:"]
        lines += [f"  s{i}: {' '.join(sub[i]['text'].split())[:1200]}" for i in s_ids]
        lines += ["EXPECTED:"] + [f"  e{j}: {' '.join(exp[j]['text'].split())}" for j in e_ids]
        text.append("\n".join(lines))
    prompt = PROMPT.format(groups="\n\n".join(text))
    cache = CACHE / f"{hashlib.sha1((MODEL + effort + prompt).encode()).hexdigest()[:16]}.json"
    if cache.is_file():
        pairs = json.loads(cache.read_text(encoding="utf-8"))
    else:
        import anthropic

        schema = {"type": "object", "properties": {"pairs": {"type": "array", "items": {
            "type": "object", "properties": {"s": {"type": "string"}, "e": {"type": "string"}},
            "required": ["s", "e"], "additionalProperties": False}}}, "required": ["pairs"], "additionalProperties": False}
        load_env()
        response = anthropic.Anthropic().beta.messages.create(
            model=MODEL, max_tokens=16000, messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}})
        pairs = json.loads(next(b.text for b in response.content if b.type == "text"))["pairs"]
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(pairs), encoding="utf-8")
    allowed = {(i, j) for s_ids, e_ids in batch for i in s_ids for j in e_ids}
    out = []
    for p in pairs:
        try:
            i, j = int(str(p["s"]).lstrip("s")), int(str(p["e"]).lstrip("e"))
        except ValueError:
            continue
        if (i, j) in allowed:
            out.append((i, j))
    return out


def score(sub: list[dict], exp: list[dict], workers: int = 6, effort: str = "medium", batch_items: int = 60) -> dict:
    comps = sorted(groups(sub, exp), key=lambda c: c[1][0])
    batches, cur, size = [], [], 0
    for c in comps:
        n = len(c[0]) + len(c[1])
        if cur and size + n > batch_items:
            batches.append(cur)
            cur, size = [], 0
        cur.append(c)
        size += n
    if cur:
        batches.append(cur)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda b: judge_batch(b, sub, exp, effort), batches))
    used_s, used_e, matched = set(), set(), []
    for pairs in results:  # enforce one to one even if the model repeats an id
        for i, j in pairs:
            if i not in used_s and j not in used_e:
                used_s.add(i)
                used_e.add(j)
                matched.append((i, j))
    p = len(matched) / len(sub) if sub else 0.0
    r = len(matched) / len(exp) if exp else 0.0
    f = lambda b: (1 + b * b) * p * r / (b * b * p + r) if p + r else 0.0
    return {"submitted": len(sub), "expected": len(exp), "matched": len(matched), "precision": p, "recall": r,
            "f1": f(1), "f2": f(2), "groups": len(comps), "calls": len(batches),
            "pairs": [{"submitted": sub[i].get("id"), "expected": exp[j].get("id")} for i, j in matched]}


def fingerprint(doc: dict) -> str:
    """Same as bench.py, so a recorded score attaches to the benchmark run of the same predictions file."""
    canonical = json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record(approach: str, prediction: dict, gold: Path, res: dict, effort: str) -> None:
    path = ROOT / "approaches" / "req_scores.json"
    scores = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    entry = {"approach": approach, "prediction_sha256": fingerprint(prediction), "case": gold.resolve().parent.name,
             "judge": f"req_judge {MODEL} {effort}",
             **{k: res[k] for k in ("precision", "recall", "f1", "f2", "matched", "submitted", "expected")}}
    scores = [s for s in scores if (s["approach"], s["prediction_sha256"]) != (approach, entry["prediction_sha256"])]
    path.write_text(json.dumps(scores + [entry], indent=2) + "\n", encoding="utf-8")
    print(f"recorded in {path.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prediction", type=Path)
    ap.add_argument("gold", type=Path)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--out", type=Path, help="write the full result (with matched pairs) here")
    ap.add_argument("--record", metavar="APPROACH", help="store the score in approaches/req_scores.json under this "
                    "experiment name; the dashboards show it for the run that scored this exact file")
    args = ap.parse_args(argv)
    prediction = json.loads(args.prediction.read_text(encoding="utf-8"))
    sub = prediction["requirements"]
    exp = json.loads(args.gold.read_text(encoding="utf-8"))["requirements"]
    res = score(sub, exp, args.workers, args.effort)
    if args.out:
        args.out.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    if args.record:
        record(args.record, prediction, args.gold, res, args.effort)
    print(f"requirements (local judge): P {res['precision']:.3f}  R {res['recall']:.3f}  F1 {res['f1']:.3f}  "
          f"F2 {res['f2']:.3f}  ({res['matched']} matched / {res['submitted']} submitted / {res['expected']} expected; "
          f"{res['calls']} calls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
