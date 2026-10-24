"""Run selected benchmark case(s) and report live Anthropic API cost and elapsed time.

From PowerShell at the repository root:
    python approaches/experiments/leo-greedy-profile-faithful/run.py
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_DIR = Path(__file__).resolve().parent
TOOLKIT_SRC = REPO_ROOT / "approaches" / "experiments" / "devansh-toolkit" / "src"
CHALLENGE_DIR = REPO_ROOT.parent / "industrial-ai-hackathon"
HOLDOUT_DIR = REPO_ROOT / "approaches" / "benchmarking" / "cases" / "holdout-acpe"
EXPERIMENT = "leo-greedy-profile-faithful"
OUTPUT_DIR = EXPERIMENT_DIR / "outputs"

# Anthropic Claude Sonnet 5.5 standard global API list prices, USD per million tokens.
MODEL = "claude-sonnet-5-5"
PRICE_PER_MILLION = {
    "input_tokens": 2.00,
    "output_tokens": 10.00,
    "cache_read_input_tokens": 0.10,
    "cache_creation_input_tokens": 2.50,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-benchmark", action="store_true", help="generate predictions without scoring them")
    parser.add_argument("--case", choices=("dev-rear-lamp", "holdout-acpe", "both"), default="dev-rear-lamp")
    args = parser.parse_args()

    os.environ["LLM_CACHE_DIR"] = str(EXPERIMENT_DIR / ".cache-sonnet-5-5")
    os.environ["ANTHROPIC_MODEL"] = MODEL
    sys.path.insert(0, str(TOOLKIT_SRC))
    sys.path.insert(0, str(EXPERIMENT_DIR / "src"))
    from retrieval import llm
    from greedy_export import main as export_main

    totals = {name: 0 for name in PRICE_PER_MILLION}
    request_count = 0
    lock = threading.Lock()
    started = time.monotonic()

    def on_usage(usage: dict) -> None:
        nonlocal request_count
        with lock:
            request_count += 1
            for name in totals:
                totals[name] += int(usage.get(name, 0) or 0)
            spent = current_cost()
            elapsed = time.monotonic() - started
            print(
                f"\n[API {request_count}] {usage.get('model', llm.MODEL)} | "
                f"input {usage.get('input_tokens', 0):,}, output {usage.get('output_tokens', 0):,}, "
                f"cache read {usage.get('cache_read_input_tokens', 0):,}, "
                f"cache write {usage.get('cache_creation_input_tokens', 0):,} | "
                f"spent so far ${spent:.4f} | elapsed {format_duration(elapsed)}",
                flush=True,
            )

    def current_cost() -> float:
        return sum(totals[name] * rate for name, rate in PRICE_PER_MILLION.items()) / 1_000_000

    def format_duration(seconds: float) -> str:
        seconds = max(0, int(seconds))
        hours, rem = divmod(seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    cases = ("dev-rear-lamp", "holdout-acpe") if args.case == "both" else (args.case,)
    print(f"Model: {llm.MODEL}")
    duration = "20–60 minutes" if len(cases) == 2 else "10–30 minutes"
    print(f"Expected duration: about {duration} on a cold cache; cached runs are usually faster.")
    print("Expected spend: varies with cache hits and selected clauses; live cost below is calculated from API token usage.")
    print("Pricing assumes standard global Sonnet 5.5 rates; any fallback model may have a different rate.")
    print("Starting with prior spend for this process: $0.0000\n", flush=True)

    llm.USAGE_CALLBACK = on_usage
    try:
        for case in cases:
            suffix = "-holdout-acpe" if case == "holdout-acpe" else ""
            output = OUTPUT_DIR / f"predictions{suffix}.json"
            print(f"=== Generating {case} ===", flush=True)
            result = export_main([
                "--config", str(EXPERIMENT_DIR / "config.json"),
                "--case", case,
                "--team-id", "team-11",
                "--out", str(output),
            ])
            if result:
                return result

        if not args.skip_benchmark:
            index_path = CHALLENGE_DIR / "regulations" / "index.json"
            jobs = (
                ("dev-rear-lamp", OUTPUT_DIR / "predictions.json", CHALLENGE_DIR / "cases" / "dev-rear-lamp" / "expected.json"),
                ("holdout-acpe", OUTPUT_DIR / "predictions-holdout-acpe.json", HOLDOUT_DIR / "expected.json"),
            )
            for case, predictions, expected in jobs:
                if case not in cases:
                    continue
                subprocess.run([
                    sys.executable,
                    str(REPO_ROOT / "approaches" / "benchmarking" / "bench.py"),
                    EXPERIMENT,
                    str(predictions),
                    str(expected),
                    "--index",
                    str(index_path),
                ], cwd=REPO_ROOT, check=True)
            if "holdout-acpe" in cases:
                subprocess.run([
                    sys.executable,
                    str(REPO_ROOT / "approaches" / "benchmarking" / "check_unseen.py"),
                    EXPERIMENT,
                ], cwd=REPO_ROOT, check=True)
            subprocess.run([
                sys.executable,
                str(REPO_ROOT / "approaches" / "benchmarking" / "dashboard_rows.py"),
            ], cwd=REPO_ROOT, check=True)
    finally:
        llm.USAGE_CALLBACK = None
        elapsed = time.monotonic() - started
        print("\n=== Run summary ===")
        print(f"Elapsed: {format_duration(elapsed)}")
        print(f"API requests: {request_count}")
        print(f"Tokens: input {totals['input_tokens']:,}, output {totals['output_tokens']:,}, "
              f"cache read {totals['cache_read_input_tokens']:,}, "
              f"cache write {totals['cache_creation_input_tokens']:,}")
        print(f"Estimated API spend: ${current_cost():.4f} USD")
        print("Cached LLM responses do not incur new API usage and are not included.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
