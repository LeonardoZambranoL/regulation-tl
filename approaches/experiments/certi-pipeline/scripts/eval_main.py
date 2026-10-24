"""Evaluation harness: scores predictions against expected.json at Regulation, Page, and Clause levels,
reports per-regulation breakdown, and diagnoses misses and false positives by pipeline stage.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / "approaches" / "benchmarking"))
sys.path.insert(0, str(EXP_DIR))

from bench import score as team_bench_score  # noqa: E402
from challenge_tools.score_local import _paragraph_key  # noqa: E402
from challenge_tools.validate import validate as official_validate  # noqa: E402
from certi.stages.stage0_load import resolve_case_dir, resolve_index_path  # noqa: E402


def evaluate_predictions(
    pred_path: Path,
    case_arg: str = "dev-rear-lamp",
    run_dir: Path | None = None,
) -> dict[str, Any]:
    case_dir = resolve_case_dir(case_arg)
    gold_path = case_dir / "expected.json"
    index_path = resolve_index_path()

    pred = json.loads(pred_path.read_text(encoding="utf-8"))
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))

    problems = official_validate(pred, kind="main", index=index, strict=True)
    if problems:
        raise ValueError(f"Validation failed:\n" + "\n".join(str(p) for p in problems))

    metrics = team_bench_score(pred, gold)

    # Per-regulation breakdown (page & clause level)
    gold_regs = sorted({r["source"]["regulation"] for r in gold["requirements"]})
    pred_regs = sorted({r["source"]["regulation"] for r in pred["requirements"]})
    all_regs = sorted(set(gold_regs) | set(pred_regs))

    per_reg: dict[str, dict[str, Any]] = {}
    for reg in all_regs:
        p_sub = {
            "requirements": [r for r in pred["requirements"] if r["source"]["regulation"] == reg]
        }
        g_sub = {
            "requirements": [r for r in gold["requirements"] if r["source"]["regulation"] == reg]
        }
        if g_sub["requirements"] and p_sub["requirements"]:
            m = team_bench_score(p_sub, g_sub)
            per_reg[reg] = {
                "n_pred": len(p_sub["requirements"]),
                "n_gold": len(g_sub["requirements"]),
                "page_f2": round(m["page_level"]["f2"], 4),
                "page_p": round(m["page_level"]["precision"], 4),
                "page_r": round(m["page_level"]["recall"], 4),
                "clause_f2": round(m["clause_level"]["f2"], 4),
                "clause_p": round(m["clause_level"]["precision"], 4),
                "clause_r": round(m["clause_level"]["recall"], 4),
            }
        else:
            per_reg[reg] = {
                "n_pred": len(p_sub["requirements"]),
                "n_gold": len(g_sub["requirements"]),
                "page_f2": 0.0,
                "page_p": 0.0,
                "page_r": 0.0,
                "clause_f2": 0.0,
                "clause_p": 0.0,
                "clause_r": 0.0,
            }

    # Diagnose missed gold clauses and false positive predicted clauses
    pred_clauses = {
        (r["source"]["regulation"], _paragraph_key(r["source"].get("paragraph")))
        for r in pred["requirements"]
        if _paragraph_key(r["source"].get("paragraph"))
    }
    gold_clauses = {
        (r["source"]["regulation"], _paragraph_key(r["source"].get("paragraph"))): r
        for r in gold["requirements"]
        if _paragraph_key(r["source"].get("paragraph"))
    }

    stage3_clauses = set()
    if run_dir and (run_dir / "stage3_extracted.json").is_file():
        s3 = json.loads((run_dir / "stage3_extracted.json").read_text(encoding="utf-8"))
        for item in s3:
            reg_name = item["clause_id"].split("_base:")[0].replace("_", " ")
            stage3_clauses.add((reg_name, _paragraph_key(item["paragraph"])))

    missed_clauses = []
    for (reg, nk), g_req in sorted(gold_clauses.items()):
        if (reg, nk) not in pred_clauses:
            if reg not in pred_regs:
                cause = "Stage 2 Gate rejected regulation"
            elif (reg, nk) in stage3_clauses:
                cause = "Stage 5 Verifier dropped it"
            else:
                cause = "Stage 3 Extractor skipped it"
            missed_clauses.append({
                "gold_id": g_req["id"],
                "regulation": reg,
                "page": g_req["source"]["page"],
                "paragraph": g_req["source"].get("paragraph"),
                "cause": cause,
                "gold_text": g_req["text"][:140],
            })

    fp_clauses = []
    for r in pred["requirements"]:
        reg = r["source"]["regulation"]
        nk = _paragraph_key(r["source"].get("paragraph"))
        if nk and (reg, nk) not in gold_clauses:
            fp_clauses.append({
                "pred_id": r["id"],
                "regulation": reg,
                "page": r["source"]["page"],
                "paragraph": r["source"].get("paragraph"),
                "text": r["text"][:140],
            })

    report = {
        "case_id": case_dir.name,
        "prediction_path": str(pred_path),
        "n_submitted_requirements": len(pred["requirements"]),
        "n_expected_requirements": len(gold["requirements"]),
        "metrics": metrics,
        "per_regulation": per_reg,
        "missed_gold_clauses_count": len(missed_clauses),
        "false_positive_clauses_count": len(fp_clauses),
        "missed_gold_clauses": missed_clauses,
        "false_positive_clauses_sample": fp_clauses[:30],
    }
    return report


def print_eval_report(report: dict[str, Any]) -> None:
    m = report["metrics"]
    rl = m["regulation_level"]
    pl = m["page_level"]
    cl = m["clause_level"]

    print(f"\n================ EVALUATION: {report['case_id']} ================")
    print(f"Requirements submitted: {report['n_submitted_requirements']} (expected: {report['n_expected_requirements']})")
    print(f"  Regulation Level : P={rl['precision']:.4f}  R={rl['recall']:.4f}  F1={rl['f1']:.4f}  F2={rl['f2']:.4f}  ({rl['n_matched']}/{rl['n_expected']} matched, {rl['n_submitted']} cited)")
    print(f"  Page Level       : P={pl['precision']:.4f}  R={pl['recall']:.4f}  F1={pl['f1']:.4f}  F2={pl['f2']:.4f}  ({pl['n_matched']}/{pl['n_expected']} matched, {pl['n_submitted']} cited)")
    print(f"  Clause Level     : P={cl['precision']:.4f}  R={cl['recall']:.4f}  F1={cl['f1']:.4f}  F2={cl['f2']:.4f}  ({cl['n_matched']}/{cl['n_expected']} matched, {cl['n_submitted']} cited)")
    print("\nPer-Regulation Breakdown:")
    print(f"  {'Regulation':<10} {'Pred':>5} {'Gold':>5} | {'Page P':>7} {'Page R':>7} {'Page F2':>8} | {'Clause P':>8} {'Clause R':>8} {'Clause F2':>9}")
    for reg, st in report["per_regulation"].items():
        print(
            f"  {reg:<10} {st['n_pred']:>5} {st['n_gold']:>5} | "
            f"{st['page_p']:>7.4f} {st['page_r']:>7.4f} {st['page_f2']:>8.4f} | "
            f"{st['clause_p']:>8.4f} {st['clause_r']:>8.4f} {st['clause_f2']:>9.4f}"
        )

    if report["missed_gold_clauses"]:
        causes = Counter(x["cause"] for x in report["missed_gold_clauses"])
        print(f"\nMissed Gold Clauses ({report['missed_gold_clauses_count']}) by cause: {dict(causes)}")
        for x in report["missed_gold_clauses"][:10]:
            print(f"  - [{x['cause']}] {x['regulation']} p.{x['page']} ({x['paragraph']}): {x['gold_text']}...")

    if report["false_positive_clauses_sample"]:
        print(f"\nTop False Positive Clauses (out of {report['false_positive_clauses_count']}):")
        for x in report["false_positive_clauses_sample"][:10]:
            print(f"  + {x['regulation']} p.{x['page']} ({x['paragraph']}): {x['text']}...")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("predictions", nargs="?", type=Path, default=EXP_DIR / "outputs" / "predictions.json")
    ap.add_argument("--case", default="dev-rear-lamp")
    ap.add_argument("--run-dir", type=Path, default=None)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args()

    report = evaluate_predictions(args.predictions, case_arg=args.case, run_dir=args.run_dir)
    print_eval_report(report)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
