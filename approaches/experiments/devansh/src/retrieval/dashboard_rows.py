"""Flatten the team's approaches/leaderboard.json into rows for the comparison dashboard.

    python -m retrieval.dashboard_rows            # -> approaches/experiments/devansh/outputs/leaderboard_rows.json

One row per benchmark run (every person's experiments), with `latest` marking each approach's newest run on a gold set.
Local file paths are left out.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .corpus import APPROACH_DIR, REPO_ROOT


def describe(approach: str) -> str:
    """One line on what an experiment does: its config.json "name", else the first prose line of its README."""
    folder = REPO_ROOT / "approaches" / "experiments" / approach
    cfg = folder / "config.json"
    if cfg.is_file():
        try:
            name = json.loads(cfg.read_text(encoding="utf-8")).get("name", "")
            if name:
                return name.split(": ", 1)[-1][:200]
        except ValueError:
            pass
    readme = folder / "README.md"
    if readme.is_file():
        for line in readme.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith(("#", "```", "|", "-")):
                return line.strip()[:200]
    return ""


def rows(board: list[dict]) -> list[dict]:
    out, latest = [], {}
    for r in sorted(board, key=lambda r: r["completed_at"]):
        p, g = r["metrics"]["page_level"], r["metrics"]["regulation_level"]
        row = {
            "run_id": r["run_id"], "approach": r["approach"], "description": describe(r["approach"]),
            "completed_at": r["completed_at"],
            "gold": r["gold_sha256"][:12], "evaluator": r["evaluator"],
            "page_precision": p["precision"], "page_recall": p["recall"], "page_f1": p["f1"], "page_f2": p["f2"],
            "pages_cited": p["n_submitted"], "pages_expected": p["n_expected"], "pages_matched": p["n_matched"],
            "reg_precision": g["precision"], "reg_recall": g["recall"], "reg_f2": g["f2"],
            "regs_cited": g["n_submitted"], "regs_expected": g["n_expected"],
        }
        out.append(row)
        latest[(r["approach"], r["gold_sha256"], r["evaluator"])] = r["run_id"]
    for row in out:
        row["latest"] = row["run_id"] in latest.values()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--board", default=str(REPO_ROOT / "approaches" / "leaderboard.json"))
    ap.add_argument("--out", default=str(APPROACH_DIR / "outputs" / "leaderboard_rows.json"))
    args = ap.parse_args(argv)
    data = rows(json.loads(Path(args.board).read_text(encoding="utf-8")))
    Path(args.out).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"{len(data)} runs, {sum(r['latest'] for r in data)} latest -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
