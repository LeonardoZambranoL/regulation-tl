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
import sys
import json
import re
from pathlib import Path

APPROACHES = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from robust import robust_table  # noqa: E402  (shared with bench.py so both rank the same way)
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


def sections(markdown: str) -> list[tuple[str, str]]:
    """[(heading, body)] of a markdown file; text before the first heading has heading ""."""
    out, heading, body = [], "", []
    for line in markdown.splitlines():
        if line.startswith("#"):
            out.append((heading, "\n".join(body).strip()))
            heading, body = line.lstrip("#").strip().lower(), []
        else:
            body.append(line)
    out.append((heading, "\n".join(body).strip()))
    return [(h, b) for h, b in out if b]


def tidy(text: str, limit: int = 2000) -> str:
    """Join wrapped lines into paragraphs but keep list items on their own lines; cut very long text."""
    lines, para = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or re.match(r"^(\d+[.)]|[-*])\s", line) or line.startswith("```"):
            if para:
                lines.append(" ".join(para))
                para = []
            if line and not line.startswith("```"):
                para = [line]
        else:
            para.append(line)
    if para:
        lines.append(" ".join(para))
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " ..."


def explain(folder: Path, shared: dict) -> dict:
    """Both explanations for the dashboards' Explain button, and where each came from.
    Plain: EXPLAIN.md ("# In plain words" section, or its text before any heading), else a draft in
    approaches/dashboard/explanations.json. Technical: EXPLAIN.md "# Technical" section, else the README's method /
    how-it-works / pipeline section, else a draft."""
    out = {"explain": "", "explain_source": "no plain explanation yet: add EXPLAIN.md to the experiment folder",
           "explain_technical": "", "explain_technical_source": "no technical explanation yet"}
    entry = shared.get(folder.name) if isinstance(shared.get(folder.name), dict) else {}
    path = folder / "EXPLAIN.md"
    parts = sections(path.read_text(encoding="utf-8")) if path.is_file() else []
    plain = next((b for h, b in parts if "plain" in h), None) or next((b for h, b in parts if not h), None)
    technical = next((b for h, b in parts if "technical" in h), None)
    if plain:
        out["explain"], out["explain_source"] = tidy(plain), "the experiment's EXPLAIN.md"
    elif entry.get("text"):
        out["explain"], out["explain_source"] = entry["text"], entry.get("draft") or "approaches/dashboard/explanations.json"
    if technical:
        out["explain_technical"], out["explain_technical_source"] = tidy(technical), "the experiment's EXPLAIN.md"
    else:
        readme = folder / "README.md"
        method = next((b for h, b in sections(readme.read_text(encoding="utf-8"))
                       if re.search(r"method|how it works|pipeline", h)), None) if readme.is_file() else None
        if method:
            out["explain_technical"], out["explain_technical_source"] = tidy(method), "the experiment's README (method section)"
        elif entry.get("technical"):
            out["explain_technical"], out["explain_technical_source"] = entry["technical"], entry.get("draft", "draft")
    return out


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
    shared_path = APPROACHES / "dashboard" / "explanations.json"
    shared = json.loads(shared_path.read_text(encoding="utf-8")) if shared_path.is_file() else {}
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
            **explain(folder, shared),
            "completed_at": r["completed_at"], "gold": r["gold_sha256"][:12], "evaluator": r["evaluator"],
            "case": golds.get(r["gold_sha256"], {}).get("case_id", r["gold_sha256"][:12]),
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
    robust = {t["approach"]: t for t in robust_table(board)}
    # requirement level (the platform's main score), estimated by req_judge.py --record for the exact predictions file
    req_path = APPROACHES / "req_scores.json"
    req = {(s["approach"], s["prediction_sha256"]): s
           for s in (json.loads(req_path.read_text(encoding="utf-8")) if req_path.is_file() else [])}
    sha = {r["run_id"]: r["prediction_sha256"] for r in board}
    for row in out:
        row["latest"] = row["run_id"] in keep
        t = robust.get(row["approach"]) if row["case"] == "dev-rear-lamp" else None
        row["robust_score"] = t["robust"] if t else None
        row["unseen_page_recall"] = t["unseen_page_recall"] if t else None
        row["unseen_clause_recall"] = t["unseen_clause_recall"] if t else None
        s = req.get((row["approach"], sha.get(row["run_id"])))
        for k in ("precision", "recall", "f2"):
            row[f"req_{k}"] = s[k] if s else None
    unseen_req = {row["approach"]: row["req_f2"] for row in out if row["latest"] and row["case"] == "holdout-acpe"}
    for row in out:
        row["unseen_req_f2"] = unseen_req.get(row["approach"]) if row["case"] == "dev-rear-lamp" else None
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", default=str(APPROACHES / "leaderboard.json"))
    ap.add_argument("--out", default=str(APPROACHES / "dashboard" / "leaderboard_rows.json"))
    ap.add_argument("--html-out", default=str(APPROACHES / "dashboard" / "dashboard.html"),
                    help="where to write the standalone dashboard (open.py uses a git-ignored copy)")
    ap.add_argument("--gold", action="append", help="gold expected.json for the clause level (repeatable); default: every "
                    "cases/*/expected.json in ../industrial-ai-hackathon next to the repo")
    args = ap.parse_args(argv)
    gold_paths = [Path(g) for g in args.gold] if args.gold else         sorted((APPROACHES.parent.parent / "industrial-ai-hackathon" / "cases").glob("*/expected.json"))
    # the team's extra test cases (e.g. holdout-acpe) are always known
    gold_paths += sorted((APPROACHES / "benchmarking" / "cases").glob("*/expected.json"))
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
        page = Path(args.html_out)
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(html, encoding="utf-8", newline="\n")
        print(f"standalone dashboard -> {page}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
