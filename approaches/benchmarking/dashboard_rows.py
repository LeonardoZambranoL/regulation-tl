"""Build the comparison dashboard's data from approaches/leaderboard.json (standard library only).

    python approaches/benchmarking/dashboard_rows.py      # -> approaches/dashboard/leaderboard_rows.json

One row per benchmark run, every experiment. Each row carries:
  - the scores bench.py recorded (page / regulation precision, recall, F1, F2, counts), and the gold pages it missed
  - `latest`: the approach's newest run for that gold set and evaluator
  - `description`: config.json "name", else the first prose line of the experiment's README.md
  - overfitting risk: the experiment's risk.json (see approaches/dashboard/README.md) plus automatic flags
Local file paths are left out. Then upload the file to the dashboard (approaches/dashboard/README.md says how).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

APPROACHES = Path(__file__).resolve().parent.parent
LEVELS = ("low", "medium", "high")


def describe(folder: Path) -> str:
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
            if line.strip() and not line.lstrip().startswith(("#", "```", "|", "-", "<")):
                return line.strip()[:200]
    return ""


def risk(folder: Path, page: dict, reg: dict) -> dict:
    """Declared risk (risk.json) plus flags we can see from the outside."""
    declared = {}
    path = folder / "risk.json"
    if path.is_file():
        try:
            declared = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            declared = {"notes": "risk.json is not valid JSON"}
    flags = list(declared.get("tuned_on_dev", []))
    level = declared.get("level") if declared.get("level") in LEVELS else None
    if declared.get("uses_gold"):
        flags.append("reads the gold answer")
        level = "high"
    if page["f2"] >= 0.999 and reg["f2"] >= 0.999:
        flags.append("matches the gold set exactly: check it does not read expected.json")
        level = "high"
    if not path.is_file():
        flags.append("no risk.json declared")
        level = level or "unknown"
    return {
        "risk_level": level or "unknown",
        "risk_flags": "; ".join(flags),
        "uses_llm": bool(declared.get("uses_llm", False)),
        "deterministic": declared.get("deterministic"),
        "risk_notes": declared.get("notes", ""),
    }


def rows(board: list[dict]) -> list[dict]:
    out, latest = [], {}
    for r in sorted(board, key=lambda r: r["completed_at"]):
        p, g = r["metrics"]["page_level"], r["metrics"]["regulation_level"]
        folder = APPROACHES / "experiments" / r["approach"]
        missed = round((1 - p["recall"]) * p["n_expected"])
        out.append({
            "run_id": r["run_id"], "approach": r["approach"], "description": describe(folder),
            "completed_at": r["completed_at"], "gold": r["gold_sha256"][:12], "evaluator": r["evaluator"],
            "page_precision": p["precision"], "page_recall": p["recall"], "page_f1": p["f1"], "page_f2": p["f2"],
            "pages_cited": p["n_submitted"], "pages_expected": p["n_expected"], "pages_missed": missed,
            "reg_precision": g["precision"], "reg_recall": g["recall"], "reg_f2": g["f2"],
            "regs_cited": g["n_submitted"], "regs_expected": g["n_expected"],
            **risk(folder, p, g),
        })
        latest[(r["approach"], r["gold_sha256"], r["evaluator"])] = r["run_id"]
    keep = set(latest.values())
    for row in out:
        row["latest"] = row["run_id"] in keep
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", default=str(APPROACHES / "leaderboard.json"))
    ap.add_argument("--out", default=str(APPROACHES / "dashboard" / "leaderboard_rows.json"))
    args = ap.parse_args(argv)
    data = rows(json.loads(Path(args.board).read_text(encoding="utf-8")))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(data)} runs, {sum(r['latest'] for r in data)} latest -> {out}")
    # the standalone page anyone can open from disk: the template with the data embedded
    template = APPROACHES / "dashboard" / "standalone_template.html"
    if template.is_file():
        built = max((r["completed_at"] for r in data), default="")[:16].replace("T", " ") + " UTC" if data else "never"
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        html = template.read_text(encoding="utf-8").replace("/*__DATA__*/", payload).replace("/*__GENERATED__*/", built)
        page = APPROACHES / "dashboard" / "dashboard.html"
        page.write_text(html, encoding="utf-8", newline="\n")
        print(f"standalone dashboard -> {page}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
