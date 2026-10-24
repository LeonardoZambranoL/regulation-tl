"""Build the comparison dashboard's data from approaches/leaderboard.json (standard library only).

    python approaches/benchmarking/dashboard_rows.py      # -> approaches/dashboard/leaderboard_rows.json

One row per benchmark run, every experiment. Each row carries:
  - the scores bench.py recorded (page / regulation precision, recall, F1, F2, counts), and the gold pages it missed
  - `latest`: the approach's newest run for that gold set and evaluator
  - `description`: config.json "name", else the first prose line of the experiment's README.md
  - overfitting risk: the experiment's risk.json (see approaches/dashboard/README.md) plus automatic flags
  - clause level (paragraph) precision / recall / F1 / F2, when the experiment's outputs/predictions.json is the file
    that run scored and the gold file is found (--gold, default: the challenge repo next to this one)
Local file paths are left out. Then upload the file to the dashboard (approaches/dashboard/README.md says how).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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


def fingerprint(doc: dict) -> str:
    """Same canonical hash as bench.py, so a file can be matched to the run that scored it."""
    canonical = json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def paragraph_key(paragraph) -> str | None:
    """The official scorer's paragraph normalisation (challenge_tools/score_local.py _paragraph_key)."""
    text = str(paragraph or "").casefold().replace("§", " ")
    text = re.sub(r"[,;:()\[\]]", " ", text)
    text = re.sub(r"(?<![0-9a-z])\.|\.(?![0-9a-z])", " ", text)
    text = " ".join(text.split())
    text = re.sub(r"^(paragraphs?|para|par|section|clause)\s+", "", text)
    return text or None


def clause_scores(prediction: dict, gold: dict) -> dict:
    """Clause level: distinct (regulation, version, normalised paragraph) cited vs gold, precision / recall / F1 / F2.
    Stricter than the page level (a neighbouring paragraph on the right page does not count). A requirement without a
    paragraph cites no clause, so a page-only submission scores 0 here."""
    def cited(doc):
        return {(r["source"]["regulation"], r["source"].get("version", ""), k) for r in doc.get("requirements", [])
                if (k := paragraph_key(r["source"].get("paragraph")))}
    sub, ref = cited(prediction), cited(gold)
    hit = len(sub & ref)
    p = hit / len(sub) if sub else 0.0
    r = hit / len(ref) if ref else 0.0
    return {"clause_precision": p, "clause_recall": r,
            "clause_f1": 2 * p * r / (p + r) if p + r else 0.0,
            "clause_f2": 5 * p * r / (4 * p + r) if 4 * p + r else 0.0,
            "clauses_cited": len(sub), "clauses_expected": len(ref), "clauses_matched": hit}


def load_golds(paths: list[Path]) -> dict[str, dict]:
    golds = {}
    for path in paths:
        if path.is_file():
            doc = json.loads(path.read_text(encoding="utf-8"))
            golds[fingerprint(doc)] = doc
    return golds


def rows(board: list[dict], golds: dict[str, dict] | None = None) -> list[dict]:
    """golds: gold documents by bench fingerprint, for the clause level (computed only where the experiment's current
    outputs/predictions.json is exactly the file that run scored)."""
    golds = golds or {}
    predictions: dict[str, tuple[str, dict]] = {}
    for path in (APPROACHES / "experiments").glob("*/outputs/predictions.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            predictions[path.parent.parent.name] = (fingerprint(doc), doc)
        except ValueError:
            pass
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
        pred = predictions.get(r["approach"])
        gold = golds.get(r["gold_sha256"])
        recorded = r["metrics"].get("clause_level")  # bench.py records it since the clause level was added
        if recorded:
            out[-1].update({"clause_precision": recorded["precision"], "clause_recall": recorded["recall"],
                            "clause_f1": recorded["f1"], "clause_f2": recorded["f2"],
                            "clauses_cited": recorded["n_submitted"], "clauses_expected": recorded["n_expected"],
                            "clauses_matched": recorded["n_matched"]})
        elif pred and gold and pred[0] == r.get("prediction_sha256"):
            out[-1].update(clause_scores(pred[1], gold))
        else:
            out[-1].update({k: None for k in ("clause_precision", "clause_recall", "clause_f1", "clause_f2",
                                              "clauses_cited", "clauses_expected", "clauses_matched")})
        # newest run per approach and gold set; the evaluator id is ignored because it only changed with line endings
        latest[(r["approach"], r["gold_sha256"])] = r["run_id"]
    keep = set(latest.values())
    for row in out:
        row["latest"] = row["run_id"] in keep
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", default=str(APPROACHES / "leaderboard.json"))
    ap.add_argument("--out", default=str(APPROACHES / "dashboard" / "leaderboard_rows.json"))
    ap.add_argument("--gold", action="append", help="gold expected.json for the clause level (repeatable); default: every "
                    "cases/*/expected.json in ../industrial-ai-hackathon next to the repo")
    args = ap.parse_args(argv)
    gold_paths = [Path(g) for g in args.gold] if args.gold else         sorted((APPROACHES.parent.parent / "industrial-ai-hackathon" / "cases").glob("*/expected.json"))
    data = rows(json.loads(Path(args.board).read_text(encoding="utf-8")), load_golds(gold_paths))
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
