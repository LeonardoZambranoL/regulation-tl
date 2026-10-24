"""Single entry point for the A/B/C contextual clause-selection experiment.

Inference is deliberately gold-blind.  Evaluation starts only after all selected
prediction files have been written and fingerprinted.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOLKIT_SRC = ROOT / "approaches" / "experiments" / "devansh-toolkit" / "src"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TOOLKIT_SRC))

from experiment import Experiment, atomic_write_json, sha256_file  # noqa: E402


def case_paths(case: str, challenge_dir: Path) -> tuple[Path, Path]:
    candidates = [challenge_dir / "cases" / case, ROOT / "approaches" / "benchmarking" / "cases" / case]
    case_dir = next((p for p in candidates if p.is_dir()), None)
    if case_dir is None:
        raise SystemExit(f"case {case!r} was not found")
    return case_dir / "spec.md", case_dir / "expected.json"


def baseline_path(case: str, cfg: dict) -> Path:
    base = (HERE / cfg["baseline"]).resolve()
    return base / ("predictions.json" if case == "dev-rear-lamp" else f"predictions-{case}.json")


def validate(path: Path, index: Path) -> None:
    subprocess.run([sys.executable, str(ROOT / "approaches/benchmarking/challenge_tools/validate.py"),
                    str(path), "--index", str(index)], check=True)


def freeze_manifest(case: str, paths: dict[str, Path], trace_paths: dict[str, Path]) -> Path:
    manifest = {
        "case_id": case,
        "gold_accessible_during_inference": False,
        "predictions": {v: {"path": str(p.relative_to(HERE)), "sha256": sha256_file(p)} for v, p in paths.items()},
        "traces": {v: {"path": str(p.relative_to(HERE)), "sha256": sha256_file(p)} for v, p in trace_paths.items()},
    }
    out = HERE / "outputs" / case / "frozen-manifest.json"
    atomic_write_json(out, manifest)
    return out


def infer_case(case: str, cfg: dict, challenge_dir: Path, variants: list[str]) -> tuple[dict[str, Path], dict[str, Path]]:
    spec_path, _ = case_paths(case, challenge_dir)
    out_dir = HERE / "outputs" / case
    out_dir.mkdir(parents=True, exist_ok=True)
    spec_text = spec_path.read_text(encoding="utf-8")
    from retrieval.regselect import select
    fixed_selection = select(spec_text, **cfg["regulation_selection"])
    predictions: dict[str, Path] = {}
    traces: dict[str, Path] = {}

    if "a" in variants:
        src = baseline_path(case, cfg)
        if not src.is_file():
            raise FileNotFoundError(f"cached ranked baseline missing: {src}")
        dst = out_dir / "variant-a.json"
        shutil.copyfile(src, dst)
        baseline_doc = json.loads(dst.read_text(encoding="utf-8"))
        baseline_sources = sorted({(r["source"]["regulation"], r["source"]["version"])
                                   for r in baseline_doc["requirements"]})
        raw_name = "predictions.json" if case == "dev-rear-lamp" else f"predictions-{case}.json"
        raw_path = HERE.parent / "devansh-llm-clause-filter-writer" / "outputs" / raw_name
        report_name = ("predictions-refine-report.json" if case == "dev-rear-lamp" else
                       f"predictions-{case}-refine-report.json")
        report_path = src.parent / report_name
        pre_rank = json.loads(raw_path.read_text(encoding="utf-8"))["requirements"] if raw_path.is_file() else []
        rank_report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
        atomic_write_json(out_dir / "variant-a-trace.json", {
            "variant": "A", "case_id": case, "reused": str(src.relative_to(ROOT)),
            "prediction_sha256": sha256_file(dst),
            "models": {"inference": "reused frozen baseline; no model call in this run"},
            "selected_regulations": fixed_selection,
            "versions": baseline_sources,
            "pre_rank_requirements": pre_rank,
            "rank_report": rank_report,
            "note": "Existing ranked baseline reused without inference; its historical stage trace is unavailable."
        })
        predictions["a"], traces["a"] = dst, out_dir / "variant-a-trace.json"

    for variant in [v for v in variants if v in {"b", "c"}]:
        exp = Experiment(cfg, HERE)
        dst = out_dir / f"variant-{variant}.json"
        trace = out_dir / f"variant-{variant}-trace.json"
        try:
            exp.run_case(case, spec_path, variant.upper(), dst, trace, fixed_selection=fixed_selection)
        except Exception as exc:
            atomic_write_json(trace, {"variant": variant.upper(), "case_id": case, "incomplete": True,
                                      "errors": [{"type": type(exc).__name__, "message": str(exc)}]})
            raise
        predictions[variant], traces[variant] = dst, trace
    freeze_manifest(case, predictions, traces)
    return predictions, traces


def evaluate_case(case: str, challenge_dir: Path, variants: list[str]) -> None:
    from diagnostics import build_diagnostics

    _, expected = case_paths(case, challenge_dir)
    if not expected.is_file():
        raise FileNotFoundError(f"evaluation answer is missing: {expected}")
    index = challenge_dir / "regulations" / "index.json"
    out_dir = HERE / "outputs" / case
    manifest_path = out_dir / "frozen-manifest.json"
    frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
    eval_dir = HERE / "evaluation" / case
    eval_dir.mkdir(parents=True, exist_ok=True)
    for variant in variants:
        pred = out_dir / f"variant-{variant}.json"
        recorded = frozen["predictions"][variant]["sha256"]
        if sha256_file(pred) != recorded:
            raise RuntimeError(f"{pred} changed after inference was frozen")
        validate(pred, index)
        bench_json = eval_dir / f"variant-{variant}-bench.json"
        with bench_json.open("w", encoding="utf-8") as stream:
            subprocess.run([sys.executable, str(ROOT / "approaches/benchmarking/bench.py"),
                            HERE.name, str(pred), str(expected), "--index", str(index)], check=True, stdout=stream)
        req_json = eval_dir / f"variant-{variant}-requirements.json"
        subprocess.run([sys.executable, str(ROOT / "approaches/benchmarking/req_judge.py"), str(pred), str(expected),
                        "--out", str(req_json), "--record", HERE.name], check=True)
    build_diagnostics(case, HERE, expected, variants)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["infer", "evaluate", "all"], default="all")
    parser.add_argument("--cases", nargs="+", default=["dev-rear-lamp", "holdout-acpe"])
    parser.add_argument("--variants", nargs="+", choices=["a", "b", "c"], default=["a", "b", "c"])
    parser.add_argument("--challenge-dir", type=Path, default=ROOT.parent / "industrial-ai-hackathon")
    args = parser.parse_args()
    cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    print("Model plan:")
    print("  regulation_selection: none (deterministic combined selector)")
    print("  variant_a: none (reuse frozen baseline)")
    for stage, model in cfg["models"].items():
        print(f"  {stage}: {model}")
    if args.stage in {"evaluate", "all"}:
        print("  requirement_evaluator: claude-opus-5-5 (fixed shared req_judge for score comparability)")
    if args.stage in {"infer", "all"}:
        for case in args.cases:
            infer_case(case, cfg, args.challenge_dir, args.variants)
    # Gold becomes accessible only after every requested case/variant has been
    # generated and frozen. Evaluation never feeds information back to inference.
    if args.stage in {"evaluate", "all"}:
        for case in args.cases:
            evaluate_case(case, args.challenge_dir, args.variants)
        subprocess.run([sys.executable, str(ROOT / "approaches/benchmarking/dashboard_rows.py")], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
