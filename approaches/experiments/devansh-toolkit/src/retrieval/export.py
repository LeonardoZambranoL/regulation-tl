"""Write a submission-format predictions file from a pipeline, for the shared benchmark and for uploading.

    python -m retrieval.export                           # uses ../config.json -> ../outputs/predictions.json
    python -m retrieval.export --config retrieval/configs/sel_rules_bm25plus_bigrams.json -n 190 --out ../outputs/x.json

Each of the top-n pooled spec chunks becomes one requirement (clause text, cited at its page + paragraph). This is the
retrieval-only baseline: the requirement text is the regulation clause itself, not yet split into single obligations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .corpus import APPROACH_DIR, DEFAULT_CHALLENGE_DIR, REPO_ROOT
from .pipeline import Pipeline, spec_queries


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(APPROACH_DIR / "config.json"))
    ap.add_argument("--case", default="dev-rear-lamp")
    ap.add_argument("--challenge-dir", default=str(DEFAULT_CHALLENGE_DIR))
    ap.add_argument("--team-id", default="regulation-tl")
    ap.add_argument("-n", type=int, help="number of requirements (default: config 'n', else 190)")
    ap.add_argument("--out", default=str(APPROACH_DIR / "outputs" / "predictions.json"))
    ap.add_argument("--sweep", help="comma-separated sizes: print official page/regulation scores + F2 for each, write nothing")
    args = ap.parse_args(argv)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    n = args.n or cfg.get("n", 190)
    # a case lives in the challenge repo (cases/<case>) or in the team's extra cases (approaches/benchmarking/cases/<case>)
    case_dir = next((d for d in (Path(args.challenge_dir) / "cases" / args.case,
                                 REPO_ROOT / "approaches" / "benchmarking" / "cases" / args.case) if d.is_dir()), None)
    if case_dir is None:
        raise SystemExit(f"case {args.case!r} not found in the challenge repo or approaches/benchmarking/cases")
    spec = (case_dir / "spec.md").read_text(encoding="utf-8")
    regs = None
    if cfg.get("select"):
        from .regselect import select
        regs = set(select(spec, **cfg["select"]))
    sizes = [int(x) for x in args.sweep.split(",")] if args.sweep else [n]
    if cfg.get("filter", {}).get("method") == "llm":
        # no retrieval cut: every "shall" clause of the selected regulations, kept or dropped by the LLM classifier
        from .classify import PROMPTS, candidates, classify, classify_multi
        cands = candidates(regs, cfg["filter"].get("candidates", "shall"))
        effort = cfg["filter"].get("effort", "medium")
        if cfg["filter"].get("agents") == "multi":
            decisions, report = classify_multi(spec, cands, effort=effort)
            report["regulations"] = sorted(regs)
            print("multi-agent review:", json.dumps(report))
            if not args.sweep:
                Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                (Path(args.out).parent / "review-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        else:
            decisions = classify(spec, cands, effort=effort, instructions=PROMPTS[cfg["filter"].get("prompt", "default")])
        ranked = [c for c in cands if decisions.get(c.id)]
        sizes = [len(ranked) if s <= 0 else s for s in sizes]
        n = len(ranked) if n <= 0 else n
    else:
        pipe = Pipeline(cfg, regs)
        ranked = [c for c, _ in pipe.pooled(spec_queries(spec), k_per_query=max(400, *sizes))]
    if args.sweep:
        from .bench import official_scorer
        score = official_scorer(Path(args.challenge_dir))
        gold = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
        f2 = lambda m: 5 * m["precision"] * m["recall"] / (4 * m["precision"] + m["recall"]) if m["precision"] + m["recall"] else 0
        print(f"{'N':>5}  page P   page R   page F1  page F2  reg F2")
        for size in sizes:
            sub = {"requirements": [{"id": str(i), "text": "-", "source": c.cite()} for i, c in enumerate(ranked[:size])]}
            r = score(sub, gold)
            pl = r["page_level"]
            print(f"{size:>5}  {pl['precision']:.3f}   {pl['recall']:.3f}   {pl['f1']:.3f}    {f2(pl):.3f}    {f2(r['regulation_level']):.3f}")
        return 0
    chosen = ranked[:n]
    doc = {"team_id": args.team_id, "case_id": args.case, "requirements": [
        {"id": f"R-{i:04d}", "text": " ".join(c.text.split())[:2000], "source": c.cite()}
        for i, c in enumerate(chosen, 1)]}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(chosen)} requirements from {sorted(regs) if regs else 'all regulations'} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
