#!/usr/bin/env python3
"""Evaluate a bonus change-impact submission against the public subgoal dev answer."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHALLENGE_ROOT = ROOT.parents[2].parent / "industrial-ai-hackathon"


def norm(text: str) -> str:
    text = text.casefold().replace("�", " ")
    text = re.sub(r"[^a-z0-9.%+-]+", " ", text)
    return " ".join(text.split())


def token_f1(left: str, right: str) -> float:
    a, b = norm(left).split(), norm(right).split()
    if not a or not b:
        return 0.0
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    p, r = common / len(a), common / len(b)
    return 2 * p * r / (p + r) if p + r else 0.0


def citation_match(pred: dict, gold: dict) -> bool:
    ps, gs = pred.get("source") or {}, gold.get("source") or {}
    if not ps or not gs:
        return not ps and not gs
    if ps.get("paragraph") and gs.get("paragraph") and norm(ps["paragraph"]) != norm(gs["paragraph"]):
        return False
    return ps.get("page") == gs.get("page")


def score(submission: dict, expected: dict, audit: dict | None = None) -> dict:
    pred = submission.get("changes", [])
    gold = expected.get("changes", [])
    pred_old = {c["requirement_id"]: c for c in pred if c.get("requirement_id") is not None}
    gold_old = {c["requirement_id"]: c for c in gold if c.get("requirement_id") is not None}
    matched_ids = set(pred_old) & set(gold_old)
    correct_types = sum(pred_old[rid].get("change") == gold_old[rid].get("change") for rid in matched_ids)
    correct_cites = sum(citation_match(pred_old[rid], gold_old[rid]) for rid in matched_ids)
    type_correct_ids = {rid for rid in matched_ids if pred_old[rid].get("change") == gold_old[rid].get("change")}

    pred_added = [c for c in pred if c.get("change") == "added"]
    gold_added = [c for c in gold if c.get("change") == "added"]
    pairs = []
    for i, p in enumerate(pred_added):
        for j, g in enumerate(gold_added):
            if citation_match(p, g):
                similarity = token_f1(p.get("new_text", ""), g.get("new_text", ""))
                if similarity >= 0.45:
                    pairs.append((similarity, i, j))
    pairs.sort(reverse=True)
    used_p, used_g, added_matches = set(), set(), []
    for similarity, i, j in pairs:
        if i not in used_p and j not in used_g:
            used_p.add(i)
            used_g.add(j)
            added_matches.append((i, j, similarity))

    old_precision = len(matched_ids) / len(pred_old) if pred_old else 0.0
    old_recall = len(matched_ids) / len(gold_old) if gold_old else 0.0
    add_precision = len(added_matches) / len(pred_added) if pred_added else 0.0
    add_recall = len(added_matches) / len(gold_added) if gold_added else 0.0
    pred_ids, gold_ids = set(pred_old), set(gold_old)
    by_type={}
    for kind in ("modified","removed","added"):
        gold_rows=[c for c in gold if c.get("change")==kind]
        pred_rows=[c for c in pred if c.get("change")==kind]
        if kind=="added":
            correct=len(added_matches)
        else:
            correct=sum(1 for row in gold_rows if row.get("requirement_id") in pred_old and pred_old[row["requirement_id"]].get("change")==kind)
        by_type[kind]={"expected":len(gold_rows),"submitted":len(pred_rows),"matched_correctly":correct,
                       "precision":correct/len(pred_rows) if pred_rows else 0.0,
                       "recall":correct/len(gold_rows) if gold_rows else 0.0,
                       "missed":len(gold_rows)-correct}

    audit_old={r.get("requirement_id"):r for r in (audit or {}).get("existing_requirement_decisions",[])}
    audit_clauses=(audit or {}).get("new_clause_obligations",[])
    audit_paragraphs = {c["id"]: c.get("paragraph") for c in
                        (audit or {}).get("alignment", {}).get("new_clauses", [])}
    expected_added_misses=[]
    for j,g in enumerate(gold_added):
        if j in used_g:continue
        src=g.get("source") or {};para=norm(src.get("paragraph", ""))
        same_clause=[]
        for result in audit_clauses:
            # Worklist clause IDs retain the parent when Claude cites a list item/range.
            parent = audit_paragraphs.get(result.get("clause_id"))
            rows=[o for o in result.get("obligations",[]) if norm(parent or o.get("paragraph") or "")==para and o.get("page")==src.get("page")]
            same_clause.extend(rows)
        matched=[o for o in same_clause if token_f1(o.get("text", ""),g.get("new_text", ""))>=0.45]
        competing = [i for _, i, candidate_j in pairs if candidate_j == j and i in used_p]
        if competing:
            diagnosis="matching_output_entry_already_used_for_another_expected_obligation"
            details="Possible bundled obligations or overlapping expected entries; inspect the matching submitted text. This is not evidence that Claude omitted or rejected the obligation."
        elif matched:
            diagnosis="model_classified_as_"+matched[0].get("novelty","unknown")
            details=matched[0].get("reason")
        elif same_clause:
            diagnosis="clause_reviewed_but_expected_atomic_obligation_not_extracted_or_split_differently"
            details=None
        elif audit is not None:
            diagnosis="source_clause_not_returned_as_an_obligation_by_track_b"
            details=None
        else:
            diagnosis="no_exhaustive_clause_audit_available"
            details=None
        expected_added_misses.append({"expected_text":g.get("new_text"),"source":src,"diagnosis":diagnosis,"model_evidence":details,
                                     "competing_submitted_texts":[pred_added[i].get("new_text") for i in dict.fromkeys(competing)]})
    missed_old=[]
    for rid in sorted(gold_ids-pred_ids):
        decision=audit_old.get(rid)
        missed_old.append({"requirement_id":rid,"diagnosis":"classified_unchanged" if decision and decision.get("decision")=="unchanged" else ("not_in_audit" if decision is None else "other_audit_decision"),
                           "model_evidence":decision.get("reason") if decision else None})
    return {
        "official_metric_available": False,
        "expected_change_count":len(gold),
        "matched_by_change_type":by_type,
        "old_requirement_impact": {
            "precision": old_precision, "recall": old_recall,
            "matched": len(matched_ids), "submitted": len(pred_old), "expected": len(gold_old),
        },
        "change_type_accuracy_on_matched_ids": correct_types / len(matched_ids) if matched_ids else 0.0,
        "citation_accuracy_on_matched_old_ids": correct_cites / len(matched_ids) if matched_ids else 0.0,
        "correct_type_ids": sorted(type_correct_ids),
        "added_obligation_proxy": {
            "precision": add_precision, "recall": add_recall, "matches": len(added_matches),
            "submitted": len(pred_added), "expected": len(gold_added),
            "matched_text_token_f1_mean": sum(x[2] for x in added_matches) / len(added_matches) if added_matches else 0.0,
            "citation_and_text_threshold": 0.45,
        },
        "errors": {
            "false_positive_requirement_ids": sorted(pred_ids - gold_ids),
            "false_negative_requirement_ids": sorted(gold_ids - pred_ids),
            "missed_existing_requirement_diagnosis":missed_old,
            "wrong_change_type": [
                {"requirement_id": rid, "predicted": pred_old[rid].get("change"), "expected": gold_old[rid].get("change")}
                for rid in sorted(matched_ids) if pred_old[rid].get("change") != gold_old[rid].get("change")
            ],
            "wrong_citation": [
                {"requirement_id": rid, "predicted": pred_old[rid].get("source"), "expected": gold_old[rid].get("source")}
                for rid in sorted(matched_ids) if not citation_match(pred_old[rid], gold_old[rid])
            ],
            "unmatched_added": [
                {"text": p.get("new_text"), "source": p.get("source")}
                for i, p in enumerate(pred_added) if i not in used_p
            ],
            "missed_added": expected_added_misses,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--expected", type=Path, default=CHALLENGE_ROOT / "subgoal" / "dev" / "expected.json")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--audit", type=Path, help="exhaustive assessment JSON for per-miss diagnosis")
    args = parser.parse_args()
    result = score(json.loads(args.submission.read_text(encoding="utf-8")),
                   json.loads(args.expected.read_text(encoding="utf-8")),
                   json.loads(args.audit.read_text(encoding="utf-8")) if args.audit else None)
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
