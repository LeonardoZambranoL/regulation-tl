"""Run the shared citation benchmark on both cases, with all artifacts kept in this folder.

Only this evaluation file reads answer keys. No gold data is passed to build.py.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "approaches/benchmarking"))
# This file has the same basename as the shared module, so load it by full path.
import importlib.util
spec = importlib.util.spec_from_file_location("shared_bench", ROOT / "approaches/benchmarking/bench.py")
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
from check_unseen import missing


def main():
    index = ROOT.parent / "industrial-ai-hackathon/regulations/index.json"
    runs, comparisons, diagnostics = [], {}, {}
    for case, prediction, gold in [
        ("dev-rear-lamp", "predictions.json", ROOT.parent / "industrial-ai-hackathon/cases/dev-rear-lamp/expected.json"),
        ("holdout-acpe", "predictions-holdout-acpe.json", ROOT / "approaches/benchmarking/cases/holdout-acpe/expected.json"),
    ]:
        # Use the shared benchmark unchanged, with its supported root parameter. This
        # obeys the request to commit/edit only the experiment's own folder.
        run = shared.benchmark(HERE.name, HERE / "outputs" / prediction, gold,
                               root=HERE / "benchmark", index_path=index)
        runs.append(run)
        pred = json.loads((HERE / "outputs" / prediction).read_text())
        expected = json.loads(gold.read_text())
        original = json.loads((ROOT / "approaches/experiments/certi-pipeline/outputs" / prediction).read_text())
        comparisons[case] = {"original": shared.score(original, expected), "final": run["metrics"]}
        key = lambda r: (r["source"]["regulation"], r["source"]["version"], shared._paragraph_key(r["source"].get("paragraph")))
        original_counts, gold_counts = Counter(map(key, original["requirements"])), Counter(map(key, expected["requirements"]))
        common = set(original_counts) & set(gold_counts)
        diagnostics[case] = {
            "purpose": "Aggregate over-splitting measurement only; not an item-level correctness judgement or adopted cut",
            "submitted_items": len(original["requirements"]), "expected_items": len(expected["requirements"]),
            "submitted_paragraphs": len(original_counts), "expected_paragraphs": len(gold_counts),
            "common_paragraphs": len(common),
            "submitted_items_at_common_paragraphs": sum(original_counts[k] for k in common),
            "expected_items_at_common_paragraphs": sum(gold_counts[k] for k in common),
            "fixed_cap_3_items_removed": sum(max(0, n - 3) for n in original_counts.values()),
            "fixed_cap_3_same_paragraph_expected_count_capped_by_removals": sum(min(n - 3, gold_counts[k]) for k, n in original_counts.items() if n > 3),
            "decision": "Do not adopt a cap: paragraph counts cannot establish <12% semantic match rate; fresh judge unavailable with zero API budget.",
        }
    assert not missing(runs, {HERE.name})
    report = {"unseen_status": "up to date", "runs": runs, "comparison_to_source": comparisons,
              "over_splitting_diagnostics": diagnostics,
              "requirement_judge": {"executed": False, "reason": "No own configured API key or cached per-item judge matches; no newly claimed requirement score."}}
    (HERE / "benchmark-summary.json").write_text(json.dumps(report, indent=2) + "\n")
    for case, values in comparisons.items():
        print(case, {k: round(v["f2"], 6) for k, v in values["final"].items()})
    print("unseen case: up to date (both runs recorded in this experiment's isolated benchmark directory)")


if __name__ == "__main__":
    main()
