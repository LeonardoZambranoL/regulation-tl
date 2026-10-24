"""Benchmark retrieval pipelines against the worked example (cases/<case>/expected.json).

    python -m retrieval.bench                                  # every config in retrieval/configs/
    python -m retrieval.bench retrieval/configs/bm25.json retrieval/configs/hybrid_rrf.json
    python -m retrieval.bench --case dev-rear-lamp --challenge-dir ../industrial-ai-hackathon

Three tasks:

  official - what the challenge scores. The top-N pooled spec chunks become a mock submission, scored with the challenge's
            own tools/score_local.py: regulation-level and page-level precision / recall / F1. The third, requirement
            level (LLM-matched text) runs only on the platform; req_R_max is its ceiling for these chunks.

  locate  - query = each expected requirement's text; did the retriever put its paragraph (or page) in the top k?
            Measures "can it find the passage once we know what we are looking for" (used when an LLM drafts requirements
            and we need the citation, or for query-by-requirement). Recall@k, MRR.
  spec    - queries = generated from spec.md only (what we really get on the held-out case); all queries are pooled with
            RRF into one ranked list. Measures "does the candidate set handed to the LLM contain the gold pages".
            Page recall at a budget of N pages, regulation recall within the top-ranked regulations.

Results are merged into retrieval/results/leaderboard_<case>.md (and .json) so the team can compare runs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from .corpus import DEFAULT_CHALLENGE_DIR
from .pipeline import Pipeline, spec_queries

HERE = Path(__file__).resolve().parent
LOCATE_KS = (1, 5, 10, 50)
PAGE_BUDGETS = (25, 50, 100, 200)
REG_TOPS = (3, 5, 10)


def para_key(p) -> str | None:
    """Same normalisation as tools/score_local.py, so '6.7.4.1.' == '6.7.4.1' and 'Annex 8, 2.1' == 'annex 8 2.1'."""
    t = str(p or "").casefold().replace("§", " ")
    t = re.sub(r"[,;:()\[\]]", " ", t)
    t = re.sub(r"(?<![0-9a-z])\.|\.(?![0-9a-z])", " ", t)
    t = " ".join(t.split())
    return re.sub(r"^(paragraphs?|para|par|section|clause)\s+", "", t) or None


def pages_of(chunk) -> list[int]:
    return chunk.meta.get("pages") or [chunk.page]


def eval_locate(pipe: Pipeline, gold: list[dict]) -> dict:
    results = pipe.search_many([g["text"] for g in gold], k=max(LOCATE_KS))
    hits_at = {k: 0 for k in LOCATE_KS}
    rr = 0.0
    for g, res in zip(gold, results):
        s = g["source"]
        gp = para_key(s.get("paragraph"))
        rank = next((i for i, (c, _) in enumerate(res) if c.regulation == s["regulation"] and
                     (s["page"] in pages_of(c) or (gp and para_key(c.paragraph) == gp))), None)
        if rank is not None:
            rr += 1 / (rank + 1)
            for k in LOCATE_KS:
                hits_at[k] += rank < k
    n = len(gold)
    return {**{f"R@{k}": hits_at[k] / n for k in LOCATE_KS}, "MRR": rr / n}


def eval_spec(pipe: Pipeline, gold: list[dict], spec: str) -> dict:
    ranked = pipe.pooled(spec_queries(spec), k_per_query=200)
    gold_pages = {(g["source"]["regulation"], g["source"]["page"]) for g in gold}
    gold_regs = {g["source"]["regulation"] for g in gold}
    page_order: list[tuple[str, int]] = []
    reg_score: dict[str, float] = defaultdict(float)
    for c, s in ranked:
        for p in pages_of(c):
            if (c.regulation, p) not in page_order:
                page_order.append((c.regulation, p))
        reg_score[c.regulation] += s
    regs = sorted(reg_score, key=lambda r: -reg_score[r])
    out = {f"page_R@{n}": len(gold_pages & set(page_order[:n])) / len(gold_pages) for n in PAGE_BUDGETS}
    out |= {f"reg_R@{n}": len(gold_regs & set(regs[:n])) / len(gold_regs) for n in REG_TOPS}
    out["top_regs"] = regs[:6]
    return out


def official_scorer(challenge_dir: Path):
    """The challenge's own tools/score_local.py score(), so our numbers are computed exactly like theirs."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("score_local", Path(challenge_dir) / "tools" / "score_local.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.score


def eval_official(pipe: Pipeline, gold: list[dict], spec: str, score, sizes: tuple[int, ...]) -> dict:
    """Pretend the top-N pooled spec chunks are our submission (one requirement per chunk, cited at its page + paragraph)
    and score it with the official scorer: regulation and page level precision / recall / F1. The platform's third level
    (requirement text matched by an LLM) cannot run offline; req_R_max is its ceiling: the share of expected requirements
    whose paragraph or page is among the cited ones, i.e. the best requirement recall an LLM could reach from these chunks."""
    ranked = pipe.pooled(spec_queries(spec), k_per_query=max(400, max(sizes)))
    expected = {"requirements": gold}
    out = {}
    for n in sizes:
        chosen = [c for c, _ in ranked[:n]]
        sub = {"requirements": [{"id": f"R-{i}", "text": c.text[:2000], "source": c.cite()} for i, c in enumerate(chosen)]}
        res = score(sub, expected)
        for level, tag in (("regulation_level", "reg"), ("page_level", "page")):
            for m in ("precision", "recall", "f1"):
                out[f"N{n}_{tag}_{m[0].upper() if m != 'f1' else 'F1'}"] = res[level][m]
        cited_pages = {(c.regulation, p) for c in chosen for p in pages_of(c)}
        cited_paras = {(c.regulation, para_key(c.paragraph)) for c in chosen if c.paragraph}
        covered = sum((g["source"]["regulation"], g["source"]["page"]) in cited_pages or
                      (g["source"]["regulation"], para_key(g["source"].get("paragraph"))) in cited_paras for g in gold)
        out[f"N{n}_req_R_max"] = covered / len(gold)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("configs", nargs="*", help="pipeline JSON configs (default: retrieval/configs/*.json)")
    ap.add_argument("--case", default="dev-rear-lamp")
    ap.add_argument("--challenge-dir", default=str(DEFAULT_CHALLENGE_DIR))
    ap.add_argument("--tasks", default="official,locate,spec")
    ap.add_argument("--sizes", default="100,190,400",
                    help="submission sizes N for the official task (the dev case expects 190 requirements)")
    ap.add_argument("--skip-missing-deps", action="store_true", help="skip configs whose optional libraries are missing")
    ap.add_argument("--combo", action="append", default=[], metavar="A+B[+C]",
                    help="fuse existing configs by name without writing JSON, e.g. --combo bm25+dense_bge_small "
                         "(repeatable; each combo is benchmarked as its own row)")
    ap.add_argument("--fusion", choices=["rrf", "score_fusion"], default="rrf", help="how --combo fuses (default rrf)")
    ap.add_argument("--weights", help="comma-separated fusion weights for --combo, e.g. 1,0.5")
    ap.add_argument("--rerank", metavar="MODEL", help="put a cross-encoder on top of each --combo, e.g. BAAI/bge-reranker-base")
    ap.add_argument("--candidates", type=int, default=100, help="first-stage candidates for --rerank")
    ap.add_argument("--save", action="store_true", help="also write each --combo to retrieval/configs/ so others can rerun it")
    ap.add_argument("--list", action="store_true", help="list available configs and retriever types, then exit")
    args = ap.parse_args(argv)

    if args.list:
        from .retrievers import REGISTRY
        print("retriever types:", ", ".join(sorted(REGISTRY)))
        print("configs (use the name with --combo):")
        for p in sorted((HERE / "configs").glob("*.json")):
            print(f"  {p.stem:<24} {json.loads(p.read_text(encoding='utf-8')).get('name', '')}")
        return 0

    case_dir = Path(args.challenge_dir) / "cases" / args.case
    if not case_dir.is_dir():
        print(f"error: {case_dir} not found. Clone https://github.com/Certivity/industrial-ai-hackathon next to this repo "
              "or pass --challenge-dir", file=sys.stderr)
        return 2
    gold = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))["requirements"]
    spec = (case_dir / "spec.md").read_text(encoding="utf-8")
    tasks = args.tasks.split(",")
    sizes = tuple(int(n) for n in args.sizes.split(","))
    score = official_scorer(Path(args.challenge_dir)) if "official" in tasks else None

    jobs: list[tuple[str, dict]] = [(Path(c).name, json.loads(Path(c).read_text(encoding="utf-8"))) for c in args.configs]
    for combo in args.combo:
        cfg = combo_config(combo, args.fusion, args.weights, args.rerank, args.candidates)
        stem = re.sub(r"[^A-Za-z0-9.-]+", "_", cfg["name"]).strip("_")
        if args.save:
            (HERE / "configs" / f"{stem}.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        jobs.append((f"{stem}.json", cfg))
    if not jobs:
        jobs = [(p.name, json.loads(p.read_text(encoding="utf-8"))) for p in sorted((HERE / "configs").glob("*.json"))]

    rows = []
    for config_name, cfg in jobs:
        name = cfg.get("name", Path(config_name).stem)
        t0 = time.time()
        try:
            regs = None
            if cfg.get("select"):
                from .regselect import select
                regs = set(select(spec, **cfg["select"]))
                print(f"{name}: selected {sorted(regs)}", file=sys.stderr)
            pipe = Pipeline(cfg, regs)
        except ImportError as exc:
            if args.skip_missing_deps:
                print(f"skip {name}: {exc}", file=sys.stderr)
                continue
            raise
        t_fit = time.time() - t0
        row = {"name": name, "config": config_name, "selected": sorted(regs) if regs else "all",
               "granularity": f'{cfg.get("source", "clauses")}/{cfg.get("granularity", "paragraph")}'}
        t1 = time.time()
        if "official" in tasks:
            row |= eval_official(pipe, gold, spec, score, sizes)
        if "locate" in tasks:
            row |= eval_locate(pipe, gold)
        if "spec" in tasks:
            row |= eval_spec(pipe, gold, spec)
        row["fit_s"], row["query_s"] = round(t_fit, 1), round(time.time() - t1, 1)
        rows.append(row)
        print(json.dumps(row), flush=True)

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    board = out_dir / f"leaderboard_{args.case}.json"
    # merge with earlier runs so the leaderboard accumulates; a re-run of the same config replaces its row
    old = json.loads(board.read_text(encoding="utf-8")) if board.is_file() else []
    rows = [r for r in old if r["config"] not in {x["config"] for x in rows}] + rows
    board.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    md = to_markdown(rows, args.case, sizes[len(sizes) // 2])
    (out_dir / f"leaderboard_{args.case}.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    return 0


def combo_config(combo: str, fusion: str, weights: str | None, rerank: str | None, candidates: int) -> dict:
    """"bm25+dense_bge_small" -> an rrf (or score_fusion) config over those configs' retrievers, optionally reranked."""
    parts = [json.loads((HERE / "configs" / f"{n}.json").read_text(encoding="utf-8")) for n in combo.split("+")]
    grans = {(p.get("source", "clauses"), p.get("granularity", "paragraph")) for p in parts}
    if len(grans) > 1:
        raise SystemExit(f"error: {combo} mixes chunkings {grans}; fuse configs that chunk the same way")
    retriever = parts[0]["retriever"] if len(parts) == 1 else {"type": fusion, "retrievers": [p["retriever"] for p in parts]}
    if weights and len(parts) > 1:
        retriever["weights"] = [float(w) for w in weights.split(",")]
    name = f"{fusion}({combo})" if len(parts) > 1 else combo
    if rerank:
        retriever = {"type": "rerank", "model": rerank, "candidates": candidates, "first_stage": retriever}
        name += f" -> {rerank.split('/')[-1]}"
    source, granularity = grans.pop()
    return {"name": name, "source": source, "granularity": granularity, "retriever": retriever}


def to_markdown(rows: list[dict], case: str, n: int = 190) -> str:
    """Official-style columns first (what the challenge scores), then our diagnostic retrieval columns."""
    official = [f"N{n}_reg_P", f"N{n}_reg_R", f"N{n}_reg_F1", f"N{n}_page_P", f"N{n}_page_R", f"N{n}_page_F1",
                f"N{n}_req_R_max"]
    diag = ["R@1", "R@10", "MRR", "page_R@100", "reg_R@5"]
    cols = [c for c in official + diag if any(c in r for r in rows)]
    head = [c.replace(f"N{n}_", "") for c in cols]
    lines = [f"Case `{case}`. **Official columns** = the challenge's own scorer (tools/score_local.py) on a mock submission "
             f"made of the top {n} pooled spec chunks: regulation and page precision / recall / F1, plus `req_R_max`, the "
             "ceiling on requirement recall from those chunks. Diagnostics: `R@k`/`MRR` = locate each expected requirement "
             "by its text; `page_R@100` = gold pages in the first 100 pooled pages; `reg_R@5` = gold regulations in the "
             "top 5. Other sizes N are in the .json.\n",
             "| pipeline | chunks | " + " | ".join(head) + " | fit s | query s |",
             "|---|---|" + "---:|" * (len(cols) + 2)]
    key = f"N{n}_page_F1"
    for r in sorted(rows, key=lambda r: -r.get(key, r.get("page_R@100", 0))):
        vals = " | ".join(f"{r[c]:.3f}" if c in r else "" for c in cols)
        lines.append(f"| {r['name']} | {r['granularity']} | {vals} | {r['fit_s']} | {r['query_s']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
