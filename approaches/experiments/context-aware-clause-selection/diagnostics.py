"""Post-freeze evaluation diagnostics. This module is the only experiment code that reads gold."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from experiment import atomic_write_json


def source_key(item: dict) -> tuple[str, str, str]:
    source = item["source"]
    para = re.sub(r"[\s,]+", "", str(source.get("paragraph", "")).lower()).rstrip(".")
    return source["regulation"], source["version"], para


def norm(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9.]+", text.lower()))


def _bench_metrics(path: Path) -> dict:
    # bench.py emits one JSON object. Be tolerant of a short informational prefix.
    text = path.read_text(encoding="utf-8")
    return json.loads(text[text.find("{"):])


def _trace_index(trace: dict) -> tuple[dict, set, set, set]:
    candidates = {source_key({"source": c["source"]}): c for c in trace.get("candidates", [])}
    selected = {key for key, c in candidates.items() if c.get("selected")}
    written = {source_key(r) for r in trace.get("pre_rank_requirements", [])}
    final_ids = set()
    return candidates, selected, written, final_ids


def build_diagnostics(case: str, experiment_dir: Path, expected_path: Path, variants: list[str]) -> None:
    out_dir = experiment_dir / "outputs" / case
    eval_dir = experiment_dir / "evaluation" / case
    gold = json.loads(expected_path.read_text(encoding="utf-8"))["requirements"]
    summaries, matched_by_variant, records = {}, {}, {}

    for variant in variants:
        pred = json.loads((out_dir / f"variant-{variant}.json").read_text(encoding="utf-8"))
        trace = json.loads((out_dir / f"variant-{variant}-trace.json").read_text(encoding="utf-8"))
        req = json.loads((eval_dir / f"variant-{variant}-requirements.json").read_text(encoding="utf-8"))
        bench = _bench_metrics(eval_dir / f"variant-{variant}-bench.json")
        sub_by_id = {r["id"]: r for r in pred["requirements"]}
        pairs = {p["submitted"]: p["expected"] for p in req["pairs"]}
        matched_gold = set(pairs.values())
        matched_by_variant[variant] = matched_gold
        candidates, selected, written, _ = _trace_index(trace)
        regs = set(trace.get("selected_regulations", {}))
        pre_rank_by_id = {r["id"]: r for r in trace.get("pre_rank_requirements", [])}
        final_ids = set(sub_by_id)

        false_negatives = []
        for item in gold:
            if item["id"] in matched_gold:
                continue
            key = source_key(item)
            if item["source"]["regulation"] not in regs and regs:
                category = "regulation_excluded"
            elif candidates and key not in candidates:
                category = "paragraph_never_candidate"
            elif key in candidates and not candidates[key].get("selected"):
                category = "paragraph_classified_irrelevant"
            elif key in selected and key not in written:
                category = "writer_omitted_obligation"
            elif any(source_key(r) == key and rid not in final_ids for rid, r in pre_rank_by_id.items()):
                category = "ranker_removed_valid_obligation"
            elif any(source_key(r) == key for r in pred["requirements"]):
                category = "writer_partial_or_semantic_matcher_rejection"
            else:
                category = "unresolved_stage_attribution"
            false_negatives.append({"expected": item, "category": category,
                                    "candidate_decision": candidates.get(key, {}).get("decision")})

        seen: list[dict] = []
        false_positives = []
        for item in pred["requirements"]:
            if item["id"] in pairs:
                seen.append(item)
                continue
            key = source_key(item)
            decision = candidates.get(key, {}).get("decision", {})
            words = norm(item["text"])
            duplicate = next((r for r in seen if source_key(r)[:2] == key[:2] and words and
                              len(words & norm(r["text"])) / len(words | norm(r["text"])) >= .9), None)
            if duplicate:
                category = "duplicate_requirement"
            elif not item["source"].get("paragraph"):
                category = "incorrect_or_missing_citation"
            elif decision.get("applicability") == "CONDITIONAL" and not decision.get("conditions"):
                category = "incorrect_or_missing_conditions"
            elif re.search(r"\b(authority|contracting part|technical service|approval number|notify)\b", item["text"], re.I):
                category = "administrative_not_engineering"
            elif decision.get("applicability") in {"NOT_APPLICABLE", "UNCERTAIN"}:
                category = "outside_or_unproven_product_scope"
            elif candidates.get(key, {}).get("source_text") and words:
                source_words = norm(candidates[key]["source_text"])
                # A very low source overlap is only a screening signal: the
                # requirement may legitimately expand a heading or defined term.
                content_words = {w for w in words if len(w) > 3}
                overlap = len(content_words & source_words) / max(len(content_words), 1)
                category = ("possibly_unsupported_by_source" if overlap < .12 else
                            "possible_legitimate_additional_obligation_absent_from_gold")
            else:
                category = "possible_legitimate_additional_obligation_absent_from_gold"
            false_positives.append({"submitted": item, "category": category,
                                    "candidate_decision": decision,
                                    "note": "Gold absence alone is not treated as technical invalidity."})
            seen.append(item)

        recovery_keys = {source_key({"source": c["source"]}) for c in trace.get("candidates", [])
                         if c.get("branch") == "recovery"}
        recovery_matches = [p for p in req["pairs"] if source_key(sub_by_id[p["submitted"]]) in recovery_keys]
        page = bench["metrics"]["page_level"]
        clause = bench["metrics"].get("clause_level", {})
        regulation = bench["metrics"]["regulation_level"]
        summaries[variant] = {
            "requirement": {k: req[k] for k in ("submitted", "matched", "precision", "recall", "f1", "f2")},
            "page": {k: page.get(k) for k in ("precision", "recall", "f2")},
            "clause": {k: clause.get(k) for k in ("precision", "recall", "f2")},
            "regulation": {k: regulation.get(k) for k in ("precision", "recall", "f2")},
            "conditional_clauses": trace.get("counts", {}).get("conditional"),
            "uncertain_clauses": trace.get("counts", {}).get("uncertain"),
            "recovery_requirements_matched": len(recovery_matches),
            "duplicates_removed_by_ranker": (trace.get("rank_report", {}).get("input", 0) -
                                               trace.get("rank_report", {}).get("after_dedupe", 0)),
            "false_negative_categories": dict(Counter(x["category"] for x in false_negatives)),
            "false_positive_categories": dict(Counter(x["category"] for x in false_positives)),
        }
        records[variant] = {"false_negatives": false_negatives, "false_positives": false_positives,
                            "recovery_matches": recovery_matches}
        atomic_write_json(eval_dir / f"variant-{variant}-diagnostics.json", records[variant])

    comparisons = {}
    for left, right in zip(variants, variants[1:]):
        comparisons[f"{left}_to_{right}"] = {
            "new_matches_gained": sorted(matched_by_variant[right] - matched_by_variant[left]),
            "previous_matches_lost": sorted(matched_by_variant[left] - matched_by_variant[right]),
            "requirement_f2_delta": summaries[right]["requirement"]["f2"] - summaries[left]["requirement"]["f2"],
            "requirement_recall_delta": summaries[right]["requirement"]["recall"] - summaries[left]["requirement"]["recall"],
        }
    best = max(variants, key=lambda v: summaries[v]["requirement"]["f2"])
    baseline = summaries.get("a")
    context = summaries.get("b")
    recovery = summaries.get("c")
    context_clause_recall_delta = ((context["clause"]["recall"] - baseline["clause"]["recall"])
                                   if baseline and context and context["clause"]["recall"] is not None else None)
    context_clause_precision_delta = ((context["clause"]["precision"] - baseline["clause"]["precision"])
                                      if baseline and context and context["clause"]["precision"] is not None else None)
    recovery_req_delta = ((recovery["requirement"]["f2"] - context["requirement"]["f2"])
                          if context and recovery else None)
    report = {
        "case_id": case, "scope_note": ("Holdout ACPE includes whole-regulation administrative obligations; treat "
                                           "this comparison as supporting evidence." if case == "holdout-acpe" else None),
        "variants": summaries, "comparisons": comparisons,
        "highest_requirement_f2_variant": best,
        "recommendation": ({"a": "retain baseline", "b": "adopt Variant B", "c": "adopt Variant C"}[best]),
        "answers": {
            "context_clause_recall_delta_vs_baseline": context_clause_recall_delta,
            "context_clause_precision_delta_vs_baseline": context_clause_precision_delta,
            "new_golden_obligations_from_non_shall": summaries.get("c", {}).get("recovery_requirements_matched"),
            "non_shall_requirement_f2_delta_vs_context": recovery_req_delta,
            "non_shall_gains_outweigh_false_positives": recovery_req_delta is not None and recovery_req_delta > 0,
            "remaining_false_negative_origins": summaries[best]["false_negative_categories"],
        },
    }
    atomic_write_json(eval_dir / "comparison.json", report)
    f = lambda value: "—" if value is None else f"{value:.3f}"
    lines = [f"# A/B/C comparison: {case}", "", report["scope_note"] or
             "Development is the primary labelled comparison; results may still be optimistic.", "",
             "| Variant | Req count | Req P | Req R | Req F2 | Page F2 | Clause F2 | Reg recall | Conditional | Uncertain |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for variant in variants:
        row = summaries[variant]
        lines.append(f"| {variant.upper()} | {row['requirement']['submitted']} | {f(row['requirement']['precision'])} | "
                     f"{f(row['requirement']['recall'])} | {f(row['requirement']['f2'])} | "
                     f"{f(row['page']['f2'])} | {f(row['clause']['f2'])} | {f(row['regulation']['recall'])} | "
                     f"{row['conditional_clauses'] if row['conditional_clauses'] is not None else '—'} | "
                     f"{row['uncertain_clauses'] if row['uncertain_clauses'] is not None else '—'} |")
    lines += ["", f"Recommendation: **{report['recommendation']}** (highest measured requirement F2).", "",
              f"Non-`shall` matches introduced by C: {report['answers']['new_golden_obligations_from_non_shall']}.",
              f"C vs B requirement-F2 delta: {f(report['answers']['non_shall_requirement_f2_delta_vs_context'])}.", "",
              "## Remaining false-negative origins", ""]
    lines += [f"- {name}: {count}" for name, count in
              sorted(report["answers"]["remaining_false_negative_origins"].items())]
    lines += ["", "## Match changes", ""]
    for name, comparison in comparisons.items():
        lines += [f"- {name}: {len(comparison['new_matches_gained'])} gained, "
                  f"{len(comparison['previous_matches_lost'])} lost; requirement F2 delta "
                  f"{comparison['requirement_f2_delta']:.3f}."]
    (eval_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
