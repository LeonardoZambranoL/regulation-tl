"""v7 sureness rater: Claude rates every written requirement 1-5 with its source clause in view (context), then a
cut-off removes the low band.

    python rate.py <submission.json> <spec-with-profile.md> <ratings.json> [--budget-usd 15]

Context per item: the product spec + profile, the regulation's title and the full text of the clause the item cites
(team-parsed clauses), so Claude can check that the item states what the clause says AND that the clause applies to
this product. Ratings are probability bands, so a cut-off can be read as an expected hit rate. Answers are cached in
devansh-profile-faithful-v7/.cache (key: prompt); spend is tallied from each response's usage and the run stops once
the budget is reached.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "devansh-toolkit" / "src"))
from retrieval import llm  # noqa: E402
from retrieval.corpus import load_clauses, load_index  # noqa: E402

CACHE = HERE / ".cache"
PRICE_IN, PRICE_OUT = 5 / 1e6, 25 / 1e6  # USD per token, claude-opus-5-5 (assumed)

PROMPT = """An expert compliance engineer has written the requirement list for the product in <spec>: every obligation
from the UN Regulations below that the product (or its supplier) must meet, one obligation per line. The experts are
inclusive: they list construction, marking and approval-mark obligations, performance values, test conditions and test
results, installation and visibility rules, documents to submit and conformity-of-production duties, whenever the
clause applies to this product.

Below are draft items, each with the regulation clause it was written from. For each item estimate the probability that
the expert list contains an obligation that matches it one to one (same subject, same condition, same value or
constraint). An item is unlikely to match when:
- the clause concerns a function, lamp type, component, vehicle category or option the product in <spec> does not have
  (check the spec and profile, not what such products usually have);
- the item does not state what the clause says (a different or missing value, condition or subject), or only restates
  part of another item;
- the clause is not an obligation at all (scope, explanation, background, a definition, a list of contents).

Answer with a band: 1 = below 10% likely, 2 = 10-25%, 3 = 25-50%, 4 = 50-75%, 5 = above 75%. Use the full range."""

SCHEMA = {"type": "object", "properties": {"ratings": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "string"}, "band": {"type": "integer", "enum": [1, 2, 3, 4, 5]}},
    "required": ["id", "band"], "additionalProperties": False}}},
    "required": ["ratings"], "additionalProperties": False}


def para_key(p: str | None) -> str:
    return re.sub(r"[\s,]+", "", (p or "").lower()).rstrip(".")


def clause_lookup():
    by: dict[tuple[str, str], list] = {}
    for c in load_clauses():
        by.setdefault((c.regulation, para_key(c.paragraph)), []).append(c)

    def find(src: dict) -> str:
        cands = by.get((src["regulation"], para_key(src.get("paragraph"))), [])
        if not cands:
            return "(clause text not found)"
        page = int(src["page"])
        best = min(cands, key=lambda c: 0 if page in c.meta.get("pages", [c.page]) else abs(c.page - page))
        return " ".join(best.text.split())[:2500]
    return find


class Spend:
    def __init__(self, budget: float):
        self.usd, self.budget, self.calls, self.lock = 0.0, budget, 0, threading.Lock()

    def __call__(self, u: dict) -> None:
        with self.lock:
            self.calls += 1
            self.usd += (u["input_tokens"] + u.get("cache_creation_input_tokens", 0)) * PRICE_IN \
                + u.get("cache_read_input_tokens", 0) * PRICE_IN * 0.1 + u["output_tokens"] * PRICE_OUT


def rate(reqs: list[dict], spec: str, spend: Spend, batch_size: int = 20, workers: int = 6,
         effort: str = "medium") -> dict[str, int]:
    find = clause_lookup()
    titles = {k: v.get("title", "") for k, v in load_index().items()}
    ordered = sorted(reqs, key=lambda r: (r["source"]["regulation"], int(r["source"]["page"]),
                                          str(r["source"].get("paragraph"))))
    batches, cur = [], []
    for r in ordered:  # one regulation per batch
        if cur and (len(cur) >= batch_size or cur[-1]["source"]["regulation"] != r["source"]["regulation"]):
            batches.append(cur)
            cur = []
        cur.append(r)
    if cur:
        batches.append(cur)

    def run(batch: list[dict]) -> dict[str, int]:
        reg = batch[0]["source"]["regulation"]
        items = []
        for r in batch:
            s = r["source"]
            items.append(f"[{r['id']}] para {s.get('paragraph') or '-'}, page {s['page']}\n  ITEM: {r['text']}\n"
                         f"  CLAUSE: {find(s)}")
        prompt = (f"{PROMPT}\n\n<spec>\n{spec}\n</spec>\n\n<regulation>{reg}: {titles.get(reg, '')}</regulation>\n\n"
                  "<items>\n" + "\n\n".join(items) + "\n</items>\n\nRate every item id.")
        cache = CACHE / f"rate_{hashlib.sha1((effort + prompt).encode()).hexdigest()[:16]}.json"
        if cache.is_file():
            return json.loads(cache.read_text(encoding="utf-8"))
        if spend.usd >= spend.budget:
            raise RuntimeError(f"budget reached (${spend.usd:.2f})")
        data = llm.structured(prompt, SCHEMA, effort=effort)
        wanted = {r["id"] for r in batch}
        out = {d["id"]: d["band"] for d in data["ratings"] if d["id"] in wanted}
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out

    llm.USAGE_CALLBACK = spend
    ratings: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(run, batches):
            ratings.update(part)
    return ratings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("submission", type=Path)
    ap.add_argument("spec", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--budget-usd", type=float, default=15.0)
    a = ap.parse_args()
    reqs = json.loads(a.submission.read_text(encoding="utf-8"))["requirements"]
    spend = Spend(a.budget_usd)
    ratings = rate(reqs, a.spec.read_text(encoding="utf-8"), spend)
    a.out.write_text(json.dumps(ratings, indent=1) + "\n", encoding="utf-8")
    hist = {b: sum(v == b for v in ratings.values()) for b in range(1, 6)}
    print(f"{len(ratings)}/{len(reqs)} rated {hist}; {spend.calls} new calls, ${spend.usd:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
