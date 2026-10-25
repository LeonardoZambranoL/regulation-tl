"""Evaluate both repaired cases using unchanged shared tools, writing only our folder."""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "approaches/benchmarking"))
spec = importlib.util.spec_from_file_location("shared_bench", ROOT / "approaches/benchmarking/bench.py")
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
from check_unseen import missing


def main():
    runs = []
    for name, gold in [
        ("predictions.json", ROOT.parent / "industrial-ai-hackathon/cases/dev-rear-lamp/expected.json"),
        ("predictions-holdout-acpe.json", ROOT / "approaches/benchmarking/cases/holdout-acpe/expected.json"),
    ]:
        runs.append(shared.benchmark(HERE.name, HERE / "outputs" / name, gold,
            root=HERE / "benchmark", index_path=ROOT.parent / "industrial-ai-hackathon/regulations/index.json"))
    assert not missing(runs, {HERE.name})
    (HERE / "benchmark-summary.json").write_text(json.dumps({"unseen_status": "up to date", "runs": runs,
        "semantic_judge": "not run; no own API key available; citation results cannot validate wording gains"}, indent=2) + "\n")
    for r in runs:
        print(Path(r["gold_path"]).parent.name, {k: v["f2"] for k, v in r["metrics"].items()})
    print("unseen case: up to date")


if __name__ == "__main__":
    main()
