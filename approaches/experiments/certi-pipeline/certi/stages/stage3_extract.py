"""Stage 3 — Exhaustive Extraction & Stage 4 — Clause Coverage Ledger (with Second-Pass Auditor).

Iterates over ALL clauses of the BASE version of each gated regulation in document order,
grouped into parent-context-preserving batches.
Records a complete Clause Coverage Ledger (`extracted` | `not_an_obligation` | `not_applicable` | `unreviewed`).
Clauses containing obligation triggers ("shall"/"must"/numeric limits) with zero extracted items or unreviewed status
can be sent to the Stage 4 Second-Pass extractor.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ..llm import CachedLLMClient
from ..schemas import (
    STAGE3_EXTRACTOR_JSON_SCHEMA,
    ExtractedObligation,
    ProductReaderOutput,
)
from .stage0_load import ClauseNode, LoadedCorpus

SHALL_TRIGGER_RE = re.compile(
    r"\b(shall|must|may not|is not permitted|not less than|not more than)\b",
    re.IGNORECASE,
)


def is_trivial_non_obligation(clause: ClauseNode) -> tuple[bool, str]:
    """Pure-code pre-check for preambles, bare section headings, and empty figure placeholders."""
    if clause.paragraph is None:
        return True, "Preamble / title header without paragraph number"
    txt = clause.text.strip()
    if clause.paragraph.startswith("Figure ") or "Figure " in clause.paragraph:
        if not SHALL_TRIGGER_RE.search(txt):
            return True, "Figure caption without normative obligation text"
    # Single-line short section heading with no normative verb or colon/value
    if (
        len(txt) < 75
        and "\n" not in txt
        and not re.search(
            r"\b(shall|must|may|is|are|two|one|four|red|white|amber|rear|front|in accordance|minimum|maximum)\b",
            txt,
            re.IGNORECASE,
        )
    ):
        return True, "Section or sub-clause heading without normative obligation"
    # Section 2 Definitions (unless it contains 'shall' or 'must')
    if (
        clause.annex is None
        and clause.paragraph
        and re.match(r"^2(\.\d+)*$", clause.paragraph)
        and not SHALL_TRIGGER_RE.search(txt)
    ):
        return True, "Pure definition in Section 2 without normative obligation"
    return False, ""


def make_clause_batches(
    clauses: list[ClauseNode],
    max_clauses: int = 25,
    max_chars: int = 14000,
) -> list[list[ClauseNode]]:
    batches: list[list[ClauseNode]] = []
    current: list[ClauseNode] = []
    current_chars = 0
    for c in clauses:
        c_len = len(c.text) + 120
        if current and (len(current) >= max_clauses or current_chars + c_len > max_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(c)
        current_chars += c_len
    if current:
        batches.append(current)
    return batches


def resolve_sub_paragraph(
    clause: ClauseNode,
    proposed_sub: str | None,
) -> str:
    """Ensure the paragraph cited is a valid entry from the clause's sub_paragraphs or its repaired paragraph."""
    from .stage0_load import _paragraph_key

    if proposed_sub:
        nk = _paragraph_key(proposed_sub)
        if nk and nk in clause.sub_paragraphs:
            return clause.sub_paragraphs[nk]
        # Try prefixing with clause's Annex/Part/Appendix if LLM gave bare local number
        from .stage0_load import format_paragraph_citation
        prefixed = format_paragraph_citation(clause.annex, clause.part, clause.appendix, proposed_sub)
        if prefixed:
            nk_pref = _paragraph_key(prefixed)
            if nk_pref and nk_pref in clause.sub_paragraphs:
                return clause.sub_paragraphs[nk_pref]
    return clause.paragraph or "1"


def _extract_batch(
    *,
    stage_name: str,
    model: str,
    prompt_file: str,
    corpus: LoadedCorpus,
    product: ProductReaderOutput,
    reg: str,
    batch: list[ClauseNode],
    llm: CachedLLMClient,
) -> dict[str, Any]:
    reg_meta = corpus.regulations[reg]
    clause_items = []
    for c in batch:
        avail = sorted(set(c.sub_paragraphs.values()))
        if c.paragraph and c.paragraph not in avail:
            avail.insert(0, c.paragraph)
        clause_items.append({
            "clause_id": c.clause_id,
            "paragraph": c.paragraph or "",
            "available_sub_paragraphs": avail[:20],
            "parent_heading": c.parent_heading,
            "page": c.page,
            "text": c.text[:6000],
        })

    payload = {
        "product_spec": {
            "spec_markdown": corpus.spec_text,
            "product": product.product,
            "vehicle_categories": product.vehicle_categories,
            "has_electronics": product.has_electronics,
            "parts": [p.model_dump() for p in product.parts],
        },
        "regulation": reg,
        "regulation_title": reg_meta.title,
        "clauses": clause_items,
    }

    return llm.call_json(
        stage=stage_name,
        model=model,
        prompt_file=prompt_file,
        user_payload=payload,
        schema=STAGE3_EXTRACTOR_JSON_SCHEMA,
        max_tokens=12000,
    )


def run_stage3_and_4(
    corpus: LoadedCorpus,
    product: ProductReaderOutput,
    selected_regulations: list[str],
    llm: CachedLLMClient,
    config: dict[str, Any],
    run_dir: Path | None = None,
) -> tuple[list[ExtractedObligation], dict[str, Any]]:
    ext_cfg = config["extraction"]
    max_clauses = ext_cfg.get("batch_max_clauses", 25)
    max_chars = ext_cfg.get("batch_max_chars", 14000)
    workers = ext_cfg.get("workers", 8)

    ledger: dict[str, dict[str, Any]] = {}
    pass1_candidates: dict[str, list[ClauseNode]] = {}

    for reg in selected_regulations:
        reg_clauses = corpus.regulations[reg].clauses
        to_assess: list[ClauseNode] = []
        for c in reg_clauses:
            skip, reason = is_trivial_non_obligation(c)
            if skip:
                ledger[c.clause_id] = {
                    "clause_id": c.clause_id,
                    "regulation": reg,
                    "paragraph": c.paragraph,
                    "page": c.page,
                    "status": "not_an_obligation",
                    "reason": reason,
                    "extracted_count": 0,
                    "pass": "pre_filter",
                }
            else:
                ledger[c.clause_id] = {
                    "clause_id": c.clause_id,
                    "regulation": reg,
                    "paragraph": c.paragraph,
                    "page": c.page,
                    "status": "unreviewed",
                    "reason": "",
                    "extracted_count": 0,
                    "pass": "none",
                }
                to_assess.append(c)
        pass1_candidates[reg] = to_assess

    # Build all Pass 1 batches across selected regulations
    all_batches: list[tuple[str, list[ClauseNode]]] = []
    for reg in selected_regulations:
        for b in make_clause_batches(pass1_candidates[reg], max_clauses=max_clauses, max_chars=max_chars):
            all_batches.append((reg, b))

    extracted_items: list[ExtractedObligation] = []
    model_p1 = config["models"]["stage3_extractor"]
    prompt_p1 = config["prompts"]["stage3_extractor"]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_batch = {
            pool.submit(
                _extract_batch,
                stage_name="stage3_pass1",
                model=model_p1,
                prompt_file=prompt_p1,
                corpus=corpus,
                product=product,
                reg=reg,
                batch=b,
                llm=llm,
            ): (reg, b)
            for reg, b in all_batches
        }

        for fut in as_completed(future_to_batch):
            reg, batch = future_to_batch[fut]
            res = fut.result()
            decisions_by_id = {d["clause_id"]: d for d in res.get("clause_decisions", [])}
            for c in batch:
                dec = decisions_by_id.get(c.clause_id)
                if dec is None:
                    continue
                status = dec["status"]
                obs = dec.get("obligations", [])
                if status == "extracted" and not obs:
                    status = "not_an_obligation"
                elif obs:
                    status = "extracted"

                ledger[c.clause_id]["status"] = status
                ledger[c.clause_id]["reason"] = dec.get("reason", "")
                ledger[c.clause_id]["extracted_count"] = len(obs)
                ledger[c.clause_id]["pass"] = "pass1"

                for ob in obs:
                    text_clean = " ".join(ob["text"].split()).strip()
                    if not text_clean:
                        continue
                    resolved_para = resolve_sub_paragraph(c, ob.get("sub_paragraph"))
                    extracted_items.append(
                        ExtractedObligation(
                            clause_id=c.clause_id,
                            sub_paragraph=resolved_para,
                            text=text_clean[:2000],
                            paragraph=resolved_para,
                            page=c.page,
                            type=ob.get("type", "other"),
                            condition=ob.get("condition") or None,
                            measurable=bool(ob.get("measurable", False)),
                            quote_anchor=ob.get("quote_anchor", ""),
                            subject=ob.get("subject", "product"),
                            rating=int(ob.get("rating", 5)),
                            stage_origin="stage3_pass1",
                        )
                    )

    # Stage 4 — Clause Coverage Ledger & Second-Pass Extractor
    # Any clause that remained 'unreviewed' goes to Pass 2.
    if ext_cfg.get("run_second_pass", True):
        pass2_batches: list[tuple[str, list[ClauseNode]]] = []
        for reg in selected_regulations:
            p2_clauses = [
                c
                for c in corpus.regulations[reg].clauses
                if ledger[c.clause_id]["status"] == "unreviewed"
            ]
            for b in make_clause_batches(p2_clauses, max_clauses=max_clauses, max_chars=max_chars):
                pass2_batches.append((reg, b))

        if pass2_batches:
            model_p2 = config["models"]["stage4_second_pass"]
            prompt_p2 = config["prompts"]["stage4_second_pass"]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {
                    pool.submit(
                        _extract_batch,
                        stage_name="stage4_pass2",
                        model=model_p2,
                        prompt_file=prompt_p2,
                        corpus=corpus,
                        product=product,
                        reg=reg,
                        batch=b,
                        llm=llm,
                    ): (reg, b)
                    for reg, b in pass2_batches
                }
                for fut in as_completed(futs):
                    reg, batch = futs[fut]
                    res = fut.result()
                    decisions_by_id = {d["clause_id"]: d for d in res.get("clause_decisions", [])}
                    for c in batch:
                        dec = decisions_by_id.get(c.clause_id)
                        if dec is None:
                            continue
                        obs = dec.get("obligations", [])
                        status = "extracted" if obs else dec["status"]
                        ledger[c.clause_id]["status"] = status
                        ledger[c.clause_id]["reason"] = dec.get("reason", "")
                        ledger[c.clause_id]["extracted_count"] = len(obs)
                        ledger[c.clause_id]["pass"] = "pass2"
                        for ob in obs:
                            text_clean = " ".join(ob["text"].split()).strip()
                            if not text_clean:
                                continue
                            resolved_para = resolve_sub_paragraph(c, ob.get("sub_paragraph"))
                            extracted_items.append(
                                ExtractedObligation(
                                    clause_id=c.clause_id,
                                    sub_paragraph=resolved_para,
                                    text=text_clean[:2000],
                                    paragraph=resolved_para,
                                    page=c.page,
                                    type=ob.get("type", "other"),
                                    condition=ob.get("condition") or None,
                                    measurable=bool(ob.get("measurable", False)),
                                    quote_anchor=ob.get("quote_anchor", ""),
                                    subject=ob.get("subject", "product"),
                                    rating=int(ob.get("rating", 5)),
                                    stage_origin="stage4_pass2",
                                )
                            )

    # Product-neutral subject + confidence gate (fixed in advance, not swept on dev):
    # keep obligations on the product itself or its installation, rated 3+ ("likely applies") on a 1-5 scale.
    min_rating = ext_cfg.get("min_rating", 3)
    keep_subjects = set(ext_cfg.get("keep_subjects", ["product", "product_installation"]))
    extracted_items = [
        ob for ob in extracted_items if ob.subject in keep_subjects and ob.rating >= min_rating
    ]

    # Sort extracted items deterministically by (clause_id, paragraph, text)
    extracted_items.sort(key=lambda x: (x.clause_id, x.paragraph, x.text))

    # Compute per-regulation coverage statistics
    coverage_summary = {}
    for reg in selected_regulations:
        reg_clauses = corpus.regulations[reg].clauses
        counts = {"extracted": 0, "not_an_obligation": 0, "not_applicable": 0, "unreviewed": 0}
        for c in reg_clauses:
            st = ledger[c.clause_id]["status"]
            counts[st] = counts.get(st, 0) + 1
        reviewed = len(reg_clauses) - counts["unreviewed"]
        coverage_summary[reg] = {
            "total_clauses": len(reg_clauses),
            "reviewed_clauses": reviewed,
            "coverage_pct": round(reviewed * 100.0 / max(1, len(reg_clauses)), 2),
            "status_counts": counts,
        }

    stage34_report = {
        "coverage_by_regulation": coverage_summary,
        "total_extracted_obligations": len(extracted_items),
        "obligations": [item.model_dump() for item in extracted_items],
        "ledger": list(ledger.values()),
    }

    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "stage3_extracted.json").write_text(
            json.dumps([item.model_dump() for item in extracted_items], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (run_dir / "stage4_ledger.json").write_text(
            json.dumps(stage34_report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return extracted_items, stage34_report
