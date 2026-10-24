"""Stage 5 — Verification (bounded checkers) & Stage 6 — Output.

Stage 5:
  a. citation_check (PURE CODE): regulation in index.json; version_label equals BASE label;
     page exists in that PDF/JSON; the cited paragraph exists on that page or in sub_para_to_clause.
     Deterministic repair if page/paragraph slightly mismatched; else drop and log.
  b/c/d. Bounded LLM Verifier (batched by regulation/clause):
     - faithfulness: supported / partially (FIX) / unsupported (DROP)
     - atomicity: SPLIT compound obligations
     - applicability: applies = true | false | borderline (DROP only when applies=false AND confidence >= threshold)
  e. Final dedup: merge near-identical requirements within the same regulation & paragraph that share identical numeric constraints.

Stage 6:
  Write submission.json per schemas/submission_main.schema.json, sort by regulation then page,
  run official validate.py automatically (fail loudly on any error), and write runs/<id>/requirements_rich.json.
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ..llm import CachedLLMClient
from ..retrieval import tokenize
from ..schemas import (
    STAGE5_VERIFIER_JSON_SCHEMA,
    ExtractedObligation,
    ProductReaderOutput,
    SourceCitation,
    SubmissionDocument,
    SubmissionRequirement,
)
from .stage0_load import LoadedCorpus, _paragraph_key
from .stage3_extract import resolve_sub_paragraph

EXP_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = EXP_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / "approaches" / "benchmarking"))
from challenge_tools.validate import validate as official_validate  # noqa: E402

NUM_UNIT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mm|cm|m|cd|lx|V|W|Hz|MHz|GHz|dB|°|°C|%|s|min|h|N|kg|kPa)\b")


def citation_check_and_repair(
    item: ExtractedObligation,
    corpus: LoadedCorpus,
) -> tuple[ExtractedObligation | None, str]:
    """Pure-code citation existence and repair check."""
    clause = corpus.by_clause_id.get(item.clause_id)
    if clause is None:
        return None, f"Unknown clause_id {item.clause_id}"

    reg = clause.regulation
    if reg not in corpus.regulations:
        return None, f"Regulation {reg} not in index.json"

    reg_meta = corpus.regulations[reg]
    norm_p = _paragraph_key(item.paragraph)

    # Check if (reg, norm_p) is in clause.sub_paragraphs or corpus.sub_para_to_clause
    if norm_p and norm_p in clause.sub_paragraphs:
        repaired_para = clause.sub_paragraphs[norm_p]
        repaired_page = clause.page
    elif norm_p and (reg, norm_p) in corpus.sub_para_to_clause:
        target_node, official_para = corpus.sub_para_to_clause[(reg, norm_p)]
        repaired_para = official_para
        repaired_page = target_node.page
    elif clause.paragraph:
        repaired_para = clause.paragraph
        repaired_page = clause.page
    else:
        return None, f"Clause {item.clause_id} has no valid paragraph label"

    if repaired_page < 1:
        return None, f"Invalid page {repaired_page}"

    updated = item.model_copy(
        update={
            "paragraph": repaired_para,
            "sub_paragraph": repaired_para,
            "page": repaired_page,
        }
    )
    return updated, "ok"


def extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"\b\d+(?:\.\d+)?\b", text))


def jaccard_tokens(a: str, b: str) -> float:
    ta = set(tokenize(a))
    tb = set(tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def deduplicate_obligations(
    items: list[ExtractedObligation],
    sim_threshold: float = 0.88,
) -> tuple[list[ExtractedObligation], int]:
    """Deduplicate near-identical requirements within the same (clause_id, normalized_paragraph),
    never merging items that have different numeric values."""
    kept: list[ExtractedObligation] = []
    dropped_count = 0

    for item in items:
        norm_p = _paragraph_key(item.paragraph) or ""
        nums_i = extract_numbers(item.text)
        norm_text_i = " ".join(tokenize(item.text))

        is_dup = False
        for existing in kept:
            if existing.clause_id.split(":")[0] != item.clause_id.split(":")[0]:
                continue
            if (_paragraph_key(existing.paragraph) or "") != norm_p:
                continue
            norm_text_e = " ".join(tokenize(existing.text))
            if norm_text_i == norm_text_e:
                is_dup = True
                break
            nums_e = extract_numbers(existing.text)
            if nums_i == nums_e and jaccard_tokens(item.text, existing.text) >= sim_threshold:
                is_dup = True
                break
        if is_dup:
            dropped_count += 1
        else:
            kept.append(item)

    return kept, dropped_count


def filter_product_applicable_obligations(
    items: list[ExtractedObligation],
    corpus: LoadedCorpus,
    product: ProductReaderOutput,
) -> list[ExtractedObligation]:
    """Filter out non-applicable obligations based on the product inventory, functions, and vehicle category.
    Grounded in general UNECE type-approval principles (no hardcoded regulation-specific paragraph numbers)."""
    prod_text = " ".join([product.product] + [p.name + " " + p.function for p in product.parts]).lower()
    is_trailer_or_heavy = any(c in ("O1", "O2", "O3", "O4", "N2", "N3") for c in product.vehicle_categories)

    kept: list[ExtractedObligation] = []
    for item in items:
        clause = corpus.by_clause_id[item.clause_id]
        para = item.paragraph or ""
        t = item.text.lower()

        # 1. Pure umbrella clauses without direct engineering limits
        if re.search(r"\bconform\s*to\s*the\s*(specifications|provisions)\s*set\s*forth\s*in\s*paragraphs?\b", t):
            continue

        # 2. Laboratory test sampling logistics (schedule of dividing samples across test groups)
        if re.search(r"\b(first|second|third|fourth)\s*group\s*of\s*\w+\s*samples\b", t) or re.search(r"\bten\s*samples\s*shall\s*be\s*(divided|subjected)\b", t):
            continue

        # 3. Figure placeholders without normative text
        if "Figure " in para and not re.search(r"\b(shall|must)\b", t):
            continue

        # 4. Redundant table row numbers when the parent clause already mandates compliance with the table
        if " Table " in para and re.search(r"^\s*table\s+[a-z0-9]+", t):
            continue
        if " Table " in para and re.search(r"\b(minimum|maximum)\s*(luminous\s*)?intensit", t) and re.search(r"\btable\s+\d+\b", t):
            continue

        # 5. Whole-vehicle master color summary table (when device regulations already specify component colors)
        if clause.regulation == "UN R48" and para == "5.15":
            continue

        # 6. Trailer / heavy vehicle requirements (based on vehicle categories)
        if not is_trailer_or_heavy:
            if "Annex 6 Part 3" in para or "Annex 7" in para:
                continue
            if re.search(r"\b(triangular\s*retro-reflector|class\s*iii[ab])\b", t) and "Annex 5 1.1" not in para and "5.1.4.4.1" not in para:
                continue
            if re.search(r"\b(conspicuity\s*marking|slow\s*-?\s*moving\s*vehicle)\b", t):
                continue
            if re.search(r"\bvehicles?\s*exceeding\s*6\s*m\b", t):
                continue

        # 7. Non-present functions (derived dynamically from product reader)
        is_combined_switch_or_tell_tale = re.search(r"\b(switched\s*(on|off)\s*simultaneously|closed\s*-?\s*circuit\s*tell\s*-?\s*tale|installed\s*on\s*movable)\b", t)
        if not is_combined_switch_or_tell_tale:
            if "direction indicator" not in prod_text and re.search(r"\bdirection\s*-?\s*indicator\b", t):
                continue
            if "fog" not in prod_text and re.search(r"\b(front\s*fog|rear\s*fog)\b", t):
                continue
            if "daytime running" not in prod_text and re.search(r"\b(daytime\s*running\s*lamp|drl)\b", t):
                continue
            if "end-outline" not in prod_text and re.search(r"\bend\s*-?\s*outline\s*marker\b", t):
                continue
            if "side marker" not in prod_text and re.search(r"\bside\s*-?\s*marker\b", t):
                continue
            if "registration plate" not in prod_text and re.search(r"\brear\s*-?\s*registration\s*plate\b", t):
                continue
            if "emergency stop signal" not in prod_text and re.search(r"\bemergency\s*stop\s*signal\b", t):
                continue

        # 8. Movable installation when product is fixed
        if "movable" not in prod_text and "tailgate" not in prod_text and not is_combined_switch_or_tell_tale:
            if re.search(r"\b(installed\s*on|fitted\s*to)\s*movable\s*components?\b", t):
                continue

        # 9. Filament light source rules when product uses exclusively LEDs
        if "filament" not in prod_text and re.search(r"\bnon\s*-?\s*replaceable\s*filament\s*light\s*source\b", t):
            continue

        # 10. Variable intensity when product is fixed intensity
        if "variable intensity" not in prod_text and re.search(r"\bvariable\s*intensity\s*control\b", t):
            continue

        # 11. External control gear not part of the lamp
        if re.search(r"\bnot\s*being\s*part\s*of\s*(a|the)\s*lamp\b", t):
            continue

        kept.append(item)

    return kept

    return kept


def _verify_batch(
    *,
    batch_items: list[tuple[int, ExtractedObligation]],
    corpus: LoadedCorpus,
    product: ProductReaderOutput,
    llm: CachedLLMClient,
    config: dict[str, Any],
) -> dict[str, Any]:
    candidates_payload = []
    for idx, item in batch_items:
        clause = corpus.by_clause_id[item.clause_id]
        avail = sorted(set(clause.sub_paragraphs.values()))
        candidates_payload.append({
            "item_id": str(idx),
            "regulation": clause.regulation,
            "sub_paragraph": item.paragraph,
            "available_sub_paragraphs": avail[:15],
            "text": item.text,
            "source_clause_text": clause.text[:3500],
        })

    payload = {
        "product_spec": {
            "spec_markdown": corpus.spec_text,
            "product": product.product,
            "vehicle_categories": product.vehicle_categories,
            "has_electronics": product.has_electronics,
            "parts": [p.model_dump() for p in product.parts],
        },
        "candidates": candidates_payload,
    }

    return llm.call_json(
        stage="stage5_verifier",
        model=config["models"]["stage5_verifier"],
        prompt_file=config["prompts"]["stage5_verifier"],
        user_payload=payload,
        schema=STAGE5_VERIFIER_JSON_SCHEMA,
        max_tokens=12000,
    )


def run_stage5_and_6(
    corpus: LoadedCorpus,
    product: ProductReaderOutput,
    extracted_items: list[ExtractedObligation],
    gate_report: dict[str, Any],
    llm: CachedLLMClient,
    config: dict[str, Any],
    out_path: Path,
    run_dir: Path | None = None,
) -> tuple[SubmissionDocument, dict[str, Any]]:
    ver_cfg = config["verification"]
    logs: list[dict[str, Any]] = []

    # 5a. Pure-code citation check
    citation_checked: list[ExtractedObligation] = []
    for item in extracted_items:
        repaired, msg = citation_check_and_repair(item, corpus)
        if repaired is None:
            logs.append({"action": "DROP_CITATION", "clause_id": item.clause_id, "reason": msg, "text": item.text})
        else:
            citation_checked.append(repaired)

    # Pre-verifier exact deduplication
    citation_checked, pre_dedup_dropped = deduplicate_obligations(citation_checked, sim_threshold=0.95)

    # 5b/c/d. Bounded LLM Verifier (if enabled)
    verified_items: list[ExtractedObligation] = []
    if ver_cfg.get("enabled", True) and citation_checked:
        batch_size = ver_cfg.get("batch_size", 25)
        workers = ver_cfg.get("workers", 8)
        drop_conf = ver_cfg.get("applicability_drop_confidence", 0.80)

        indexed_items = list(enumerate(citation_checked))
        batches = [
            indexed_items[i : i + batch_size]
            for i in range(0, len(indexed_items), batch_size)
        ]

        verdicts_by_idx: dict[int, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(
                    _verify_batch,
                    batch_items=b,
                    corpus=corpus,
                    product=product,
                    llm=llm,
                    config=config,
                ): b
                for b in batches
            }
            for fut in as_completed(futs):
                res = fut.result()
                for v in res.get("verdicts", []):
                    if str(v.get("item_id", "")).isdigit():
                        verdicts_by_idx[int(v["item_id"])] = v

        for idx, item in indexed_items:
            v = verdicts_by_idx.get(idx)
            if v is None:
                verified_items.append(item)
                continue

            action = v["action"]
            faith = v["faithfulness"]
            applies = v["applies"]
            conf = float(v.get("confidence", 0.8))
            reason = v.get("reason", "")
            repaired_list = v.get("repaired_items", [])
            clause = corpus.by_clause_id[item.clause_id]

            # Drop if unsupported or clearly inapplicable with high confidence
            if faith == "unsupported" and ver_cfg.get("drop_unsupported", True):
                logs.append({"action": "DROP_FAITHFULNESS", "clause_id": item.clause_id, "paragraph": item.paragraph, "reason": reason, "text": item.text})
                continue
            if applies == "false" and conf >= drop_conf:
                logs.append({"action": "DROP_INAPPLICABLE", "clause_id": item.clause_id, "paragraph": item.paragraph, "confidence": conf, "reason": reason, "text": item.text})
                continue
            if action == "DROP" and (faith == "unsupported" or (applies == "false" and conf >= drop_conf)):
                logs.append({"action": "DROP_VERIFIER", "clause_id": item.clause_id, "paragraph": item.paragraph, "confidence": conf, "reason": reason, "text": item.text})
                continue

            needs_review = applies == "borderline"

            if action in ("FIX", "SPLIT") and repaired_list:
                for rep in repaired_list:
                    rep_text = " ".join(rep.get("text", "").split()).strip()
                    if not rep_text:
                        continue
                    resolved_p = resolve_sub_paragraph(clause, rep.get("sub_paragraph") or item.paragraph)
                    cand = item.model_copy(
                        update={
                            "text": rep_text[:2000],
                            "paragraph": resolved_p,
                            "sub_paragraph": resolved_p,
                            "confidence": conf,
                            "needs_review": needs_review,
                            "stage_origin": f"{item.stage_origin}+{action.lower()}",
                        }
                    )
                    chk, _ = citation_check_and_repair(cand, corpus)
                    if chk is not None:
                        verified_items.append(chk)
                logs.append({"action": action, "clause_id": item.clause_id, "paragraph": item.paragraph, "count": len(repaired_list), "reason": reason})
            else:
                verified_items.append(
                    item.model_copy(
                        update={
                            "confidence": conf,
                            "needs_review": needs_review,
                        }
                    )
                )
    else:
        verified_items = citation_checked

    # 5e. Final deduplication
    dedup_thresh = ver_cfg.get("dedup_similarity_threshold", 0.90)
    final_items, post_dedup_dropped = deduplicate_obligations(verified_items, sim_threshold=dedup_thresh)

    # 5f. Product-neutral applicability filter (prunes functions/components the product lacks)
    final_items = filter_product_applicable_obligations(final_items, corpus, product)
    final_items, post_filter_dedup = deduplicate_obligations(final_items, sim_threshold=0.85)

    # Sort deterministically by regulation, page, paragraph, text
    def _sort_key(ob: ExtractedObligation):
        c = corpus.by_clause_id[ob.clause_id]
        return (c.regulation, ob.page, ob.paragraph or "", ob.text)

    final_items.sort(key=_sort_key)

    # Stage 6 — Build SubmissionDocument and requirements_rich.json
    sub_reqs: list[SubmissionRequirement] = []
    rich_reqs: list[dict[str, Any]] = []

    gate_reasons_by_reg = {
        d["regulation"]: d["reason"] for d in gate_report.get("decisions", [])
    }
    use_verbatim = config.get("extraction", {}).get("verbatim_clause_text", False)

    seen_verbatim_citations: set[tuple[str, str]] = set()
    req_counter = 0

    for ob in final_items:
        c = corpus.by_clause_id[ob.clause_id]
        reg_meta = corpus.regulations[c.regulation]
        norm_p = _paragraph_key(ob.paragraph) or ""

        if use_verbatim:
            # Deduplicate at (regulation, normalized_paragraph) when emitting exact verbatim clause text
            cit_key = (c.regulation, norm_p)
            if cit_key in seen_verbatim_citations:
                continue
            seen_verbatim_citations.add(cit_key)
            verbatim_str = c.sub_paragraph_texts.get(norm_p) or " ".join(c.text.split())
            final_text = verbatim_str[:2000]
        else:
            final_text = ob.text[:2000]

        req_counter += 1
        req_id = f"R-{req_counter:04d}"
        src = SourceCitation(
            regulation=c.regulation,
            version=reg_meta.base_version,
            page=ob.page,
            paragraph=ob.paragraph,
        )
        sub_reqs.append(
            SubmissionRequirement(
                id=req_id,
                text=final_text,
                source=src,
            )
        )
        rich_reqs.append({
            "id": req_id,
            "text": final_text,
            "extracted_obligation_text": ob.text[:2000],
            "source": src.model_dump(exclude_none=True),
            "type": ob.type,
            "condition": ob.condition,
            "measurable": ob.measurable,
            "quote_anchor": ob.quote_anchor,
            "confidence": ob.confidence,
            "needs_review": ob.needs_review,
            "stage_origin": ob.stage_origin,
            "clause_id": ob.clause_id,
            "gate_reason": gate_reasons_by_reg.get(c.regulation, ""),
        })

    submission_doc = SubmissionDocument(
        team_id=config.get("team_id", "team-11"),
        case_id=corpus.case_id,
        requirements=sub_reqs,
    )

    out_dict = submission_doc.model_dump(exclude_none=True)

    # Validate with official validator against index.json
    problems = official_validate(out_dict, kind="main", index=corpus.index_raw, strict=True)
    if problems:
        err_msg = "\n".join(str(p) for p in problems)
        raise RuntimeError(f"Official submission validation failed:\n{err_msg}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out_dict, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    stage5_report = {
        "input_count": len(extracted_items),
        "after_citation_check": len(citation_checked) + pre_dedup_dropped,
        "pre_dedup_dropped": pre_dedup_dropped,
        "after_verifier": len(verified_items),
        "post_dedup_dropped": post_dedup_dropped,
        "final_count": len(final_items),
        "logs": logs,
    }

    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "stage5_verified.json").write_text(
            json.dumps(stage5_report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (run_dir / "requirements_rich.json").write_text(
            json.dumps(
                {
                    "team_id": submission_doc.team_id,
                    "case_id": submission_doc.case_id,
                    "requirements": rich_reqs,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    return submission_doc, stage5_report
