"""List experiments whose current dev result has no unseen-case (holdout-acpe) run after it.

    python approaches/benchmarking/check_unseen.py                 # every experiment
    python approaches/benchmarking/check_unseen.py <name> [<name>] # only these (the pre-push hook passes the changed ones)

An experiment is up to date when its latest holdout-acpe run is not older than the first dev run of its current dev
predictions (same prediction_sha256), so re-benchmarking unchanged dev predictions does not ask for a new holdout run.
Exit 1 if any listed experiment is missing one. Only reads approaches/leaderboard.json: no API calls, no keys.
Each person runs their OWN pipeline, with their OWN API keys, to make the holdout predictions; never run a teammate's.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from robust import DEV_CASE, EXCLUDED, UNSEEN_CASE, case_of  # noqa: E402

APPROACHES = Path(__file__).resolve().parents[1]


def missing(runs: list[dict], only: set[str] | None = None) -> list[str]:
    by: dict[tuple[str, str], list[dict]] = {}
    for run in sorted(runs, key=lambda r: r["completed_at"]):
        case = case_of(run)
        if case:
            by.setdefault((run["approach"], case), []).append(run)
    out = []
    for (approach, case), dev_runs in sorted(by.items()):
        if case != DEV_CASE or approach in EXCLUDED or (only is not None and approach not in only):
            continue
        current = dev_runs[-1]["prediction_sha256"]
        since = next(r["completed_at"] for r in dev_runs if r["prediction_sha256"] == current)
        unseen = by.get((approach, UNSEEN_CASE))
        if not unseen or unseen[-1]["completed_at"] < since:
            out.append(approach)
    return out


def main(argv: list[str]) -> int:
    runs = json.loads((APPROACHES / "leaderboard.json").read_text(encoding="utf-8"))
    names = missing(runs, set(argv) if argv else None)
    if not names:
        print("unseen case: every checked experiment is up to date")
        return 0
    print("These experiments have a dev result but no up-to-date unseen-case (holdout-acpe) run:")
    for n in names:
        print(f"  - {n}")
    print(f"""
Fix (run YOUR OWN pipeline with YOUR OWN API keys from your .env; never run a teammate's experiment):
  1. Run your pipeline on approaches/benchmarking/cases/{UNSEEN_CASE}/ and write
     approaches/experiments/<name>/outputs/predictions-{UNSEEN_CASE}.json  ("case_id": "{UNSEEN_CASE}").
  2. python approaches/benchmarking/bench.py <name> approaches/experiments/<name>/outputs/predictions-{UNSEEN_CASE}.json approaches/benchmarking/cases/{UNSEEN_CASE}/expected.json --index ../industrial-ai-hackathon/regulations/index.json
  3. python approaches/benchmarking/dashboard_rows.py, commit, push.
Experiments that are someone else's: leave them; their owner's push is checked the same way.""")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
