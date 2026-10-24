"""The Robust score: one number that rewards approaches that also work on a product they were not built on.

    robust = (dev page F2 + unseen-case clause recall) / 2

- dev page F2: latest run on the official labelled case (dev-rear-lamp), the challenge's page level with recall weighted.
- unseen-case clause recall: latest run on approaches/benchmarking/cases/holdout-acpe, a different product (ACPE).
  Recall only, because that answer key covers R175 alone, so its precision is understated. Clause (paragraph) recall,
  not page recall: R175 is about ten pages, so page recall saturates near 1.0 and separates nothing; finding the right
  numbered rules is the real test. Citations without a paragraph score 0 here.
An approach without an unseen-case run has no Robust score and ranks below every approach that has one.
Used by bench.py (LEADERBOARD.md) and dashboard_rows.py (both dashboards), so they always agree.
"""

from __future__ import annotations

DEV_CASE = "dev-rear-lamp"
UNSEEN_CASE = "holdout-acpe"
EXCLUDED = {"gold-self-check"}  # copies the answer key, not an approach


def case_of(run: dict) -> str | None:
    """Which case a run was scored on, from the gold file it used."""
    path = str(run.get("gold_path", "")).replace("\\", "/")
    for case in (UNSEEN_CASE, DEV_CASE):
        if f"/{case}/" in path:
            return case
    return None


def robust_table(runs: list[dict]) -> list[dict]:
    """[{approach, robust, dev_page_f2, dev_clause_f2, unseen_page_recall, unseen_clause_recall}], best first."""
    latest: dict[tuple[str, str], dict] = {}
    for run in sorted(runs, key=lambda r: r["completed_at"]):
        case = case_of(run)
        if case and run["approach"] not in EXCLUDED:
            latest[(run["approach"], case)] = run
    table = []
    for (approach, case), dev in latest.items():
        if case != DEV_CASE:
            continue
        unseen = latest.get((approach, UNSEEN_CASE))
        clause = lambda r, k: (r["metrics"].get("clause_level") or {}).get(k) if r else None
        dev_f2 = dev["metrics"]["page_level"]["f2"]
        unseen_recall = clause(unseen, "recall")
        table.append({
            "approach": approach,
            "robust": (dev_f2 + unseen_recall) / 2 if unseen_recall is not None else None,
            "dev_page_f2": dev_f2,
            "dev_clause_f2": clause(dev, "f2"),
            "unseen_page_recall": unseen["metrics"]["page_level"]["recall"] if unseen else None,
            "unseen_clause_recall": unseen_recall,
        })
    table.sort(key=lambda t: (t["robust"] is None, -(t["robust"] or 0), -t["dev_page_f2"], t["approach"]))
    return table


def render_markdown(runs: list[dict]) -> list[str]:
    """The robust ranking as markdown lines (top of LEADERBOARD.md)."""
    table = robust_table(runs)
    fmt = lambda v: "—" if v is None else f"{v:.4f}"
    lines = ["## Robust ranking (main ranking)", "",
             "Robust score = (dev page F2 + unseen-case clause recall) / 2. The unseen case "
             f"(`benchmarking/cases/{UNSEEN_CASE}`) is a product the approaches were not built on; approaches without an "
             "unseen-case run rank last. Clause recall because page recall saturates on the short R175.", "",
             "| Rank | Approach | Robust | Dev page F2 | Unseen clause recall | Dev clause F2 | Unseen page recall |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for i, t in enumerate(table, 1):
        rank = str(i) if t["robust"] is not None else "–"
        lines.append(f"| {rank} | [{t['approach']}](experiments/{t['approach']}/) | {fmt(t['robust'])} | "
                     f"{fmt(t['dev_page_f2'])} | {fmt(t['unseen_clause_recall'])} | {fmt(t['dev_clause_f2'])} | "
                     f"{fmt(t['unseen_page_recall'])} |")
    if not table:
        lines.append("| | No approach has been scored on the dev case yet. | | | | | |")
    return lines + [""]
