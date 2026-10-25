#!/usr/bin/env python3
"""Run the Certivity bonus change-impact pipeline on a subgoal case."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from change_impact import run_case  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="dev", help="subgoal case folder (default: dev)")
    parser.add_argument("--ablation", choices=("text", "semantic", "crossref", "agent", "exhaustive", "llm", "all"), default="exhaustive")
    parser.add_argument("--estimate-only", action="store_true", help="show review coverage and cost estimate without API calls")
    parser.add_argument("--assemble-only", action="store_true", help="assemble the exhaustive submission from completed cached responses; never call the API")
    parser.add_argument("--yes", action="store_true", help="confirm the estimated full LLM run without prompting")
    parser.add_argument("--team-id", default=os.environ.get("TEAM_ID", "team-11"))
    parser.add_argument("--max-workers", type=int, default=2)
    args = parser.parse_args()
    if args.assemble_only and (args.estimate_only or args.ablation not in ("exhaustive", "llm")):
        parser.error("--assemble-only requires the exhaustive pipeline and cannot be combined with --estimate-only")
    return run_case(args, root=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
