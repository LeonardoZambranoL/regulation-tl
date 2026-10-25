"""Version alignment, candidate generation and structured impact verification."""

from __future__ import annotations

import difflib
import hashlib
import json
from functools import lru_cache
import os
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
TOOLKIT = REPO_ROOT / "approaches" / "experiments" / "devansh-toolkit" / "src"
if str(TOOLKIT) not in sys.path:
    sys.path.insert(0, str(TOOLKIT))

DEFAULT_MODEL = "claude-sonnet-5-5"
PRICE = {
    "input_tokens": 2.0,
    "output_tokens": 10.0,
    "cache_read_input_tokens": 0.10,
    "cache_creation_input_tokens": 2.50,
}

HEADER_RE = re.compile(r"UN\s+R\d+[A-Z]?,\s*version\s+([\d.]+)\s*\|\s*page\s+(\d+)\s+of\s+\d+", re.I)
ANNEX_RE = re.compile(r"^\s*Annex\s+(\d+[A-Z]?)(?:\s*[-–:]\s*Appendix\s+(\d+))?(?:\s+(.*))?$", re.I)
PARA_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,3}){0,6})\.?\s+(.+?)\s*$")
NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*(?:\s*(?:km/h|km|m/s|mm|cm|m|kg|g|%|per\s+cent|seconds?|secs?|s|lux|hz|n))?", re.I)
REFERENCE_RE = re.compile(r"\b(?:paragraph|section|para(?:graph)?)\s+(\d{1,2}(?:\.\d{1,3}){0,6})", re.I)
OBLIGATION_RE = re.compile(
    r"\b(?:shall|must|may not|shall not|must not|is required|are required|is prohibited|are prohibited|"
    r"is not permitted|are not permitted|at least|not more than|no greater than|shall be)\b",
    re.I,
)
IMPERATIVE_RE = re.compile(r"(?m)^\s*\([a-z0-9]+\)\s+(?:position|hold|release|operate|record|apply|select|accelerate)\b", re.I)
DECISION_WORDS = {
    "shall", "must", "may", "not", "no", "unless", "except", "only", "if", "when", "where", "before", "after",
    "minimum", "maximum", "at", "least", "greater", "less", "more", "required", "prohibited", "permitted",
    "continuous", "standstill", "creeping", "forward", "rearward", "forwardly", "rearwards",
}

STRUCTURED_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "old_requirement_status": {"enum": ["unchanged", "modified", "removed", "none"]},
                    "new_text": {"type": ["string", "null"]},
                    "reason": {"type": ["string", "null"]},
                    "source_page": {"type": ["integer", "null"]},
                    "source_paragraph": {"type": ["string", "null"]},
                    "new_obligations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "minLength": 1},
                                "reason": {"type": "string", "minLength": 1},
                                "page": {"type": "integer", "minimum": 1},
                                "paragraph": {"type": ["string", "null"]},
                            },
                            "required": ["text", "reason", "page", "paragraph"],
                            "additionalProperties": False,
                        },
                    },
                    "confidence": {"enum": ["low", "medium", "high"]},
                },
                "required": [
                    "candidate_id", "old_requirement_status", "new_text", "reason", "source_page",
                    "source_paragraph", "new_obligations", "confidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized(text: str) -> str:
    text = text.casefold().replace("�", " ").replace("\u200b", " ")
    text = text.replace("°", " deg ").replace("º", " deg ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@lru_cache(maxsize=100_000)
def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z]+(?:'[a-z]+)?|\d+(?:[.,]\d+)*(?:%|°)?", normalized(text))


def token_similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    ca, cb = Counter(ta), Counter(tb)
    overlap = sum((ca & cb).values())
    precision, recall = overlap / len(ta), overlap / len(tb)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


@lru_cache(maxsize=200_000)
def text_similarity(a: str, b: str) -> float:
    # Token multiset overlap is stable under renumbering and far cheaper than a
    # character-level alignment across the full old/new corpus cross product.
    return token_similarity(a, b)


def paragraph_key(value: str | None) -> str:
    return re.sub(r"[\s.,:;]+$", "", normalized(value or "")).replace("paragraph ", "")


def obligation_features(text: str) -> dict[str, list[str]]:
    lower = normalized(text)
    numbers = sorted({normalized(m.group(0)) for m in NUMBER_RE.finditer(text)})
    terms = sorted({t for t in tokens(lower) if t in DECISION_WORDS})
    refs = sorted({paragraph_key(m.group(1)) for m in REFERENCE_RE.finditer(text)})
    return {"numbers": numbers, "terms": terms, "references": refs}


def substantive_delta(old: str, new: str) -> bool:
    if not normalized(old) or not normalized(new):
        return bool(normalized(old) or normalized(new))
    a, b = obligation_features(old), obligation_features(new)
    if a["numbers"] != b["numbers"] or a["terms"] != b["terms"] or a["references"] != b["references"]:
        return True
    return text_similarity(old, new) < 0.70


def has_obligation(text: str) -> bool:
    return bool(OBLIGATION_RE.search(text) or IMPERATIVE_RE.search(text))


def _clean_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def parse_pdf(path: Path, cache_dir: Path) -> dict[str, Any]:
    digest = sha256_file(path)
    cache_path = cache_dir / f"parse-{digest}.json"
    if cache_path.is_file():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    records: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    container = "main"
    current_key: str | None = None
    hierarchy: dict[str, list[tuple[int, str]]] = defaultdict(list)
    page_records: list[dict[str, Any]] = []
    pdf = pymupdf.open(path)
    try:
        for physical_page, page in enumerate(pdf, start=1):
            raw = page.get_text()
            header = HEADER_RE.search(raw)
            printed_page = int(header.group(2)) if header else physical_page
            lines = _clean_lines(raw)
            page_body = []
            for line in lines:
                if HEADER_RE.fullmatch(line):
                    continue
                if (annex := ANNEX_RE.match(line)) and annex.group(1):
                    container = f"Annex {annex.group(1)}"
                    if annex.group(2):
                        container += f" Appendix {annex.group(2)}"
                    current_key = None
                    hierarchy[container] = []
                    page_body.append(line)
                    continue
                match = PARA_RE.match(line)
                if match:
                    paragraph, remainder = match.group(1).rstrip("."), match.group(2).strip()
                    # Don't mistake a measurement row or numbered list value for a clause heading.
                    if (remainder and remainder[0].isalpha()) or remainder.startswith(("(", '"', "“", "‘")):
                        key = f"{container}|{paragraph}"
                        depth = paragraph.count(".") + 1
                        stack = hierarchy[container]
                        while stack and stack[-1][0] >= depth:
                            stack.pop()
                        parent = stack[-1][1] if stack else None
                        stack.append((depth, paragraph))
                        if key not in records:
                            records[key] = {
                                "key": key, "container": container, "paragraph": paragraph,
                                "page": printed_page, "pages": [printed_page], "parent": parent,
                                "depth": depth, "text": "", "title": remainder[:220], "is_heading": False,
                                "tables": [],
                            }
                            order.append(key)
                        record = records[key]
                        if printed_page not in record["pages"]:
                            record["pages"].append(printed_page)
                        if record["text"]:
                            record["text"] += " "
                        record["text"] += line
                        current_key = key
                        page_body.append(line)
                        continue
                if current_key is not None:
                    record = records[current_key]
                    if printed_page not in record["pages"]:
                        record["pages"].append(printed_page)
                    record["text"] += " " + line
                page_body.append(line)

            # Keep table geometry/order when PyMuPDF exposes it; page text remains the citation source of record.
            table_rows = []
            try:
                found = page.find_tables()
                for table in found.tables:
                    for row in table.extract():
                        cells = [" ".join(str(cell or "").split()) for cell in row]
                        if any(cells):
                            table_rows.append(cells)
            except Exception:
                pass
            if table_rows and current_key is not None:
                records[current_key]["tables"].extend(table_rows)
            page_records.append({"page": printed_page, "physical_page": physical_page, "text": "\n".join(page_body)})
    finally:
        pdf.close()

    provisions = []
    for index, key in enumerate(order):
        record = records[key]
        text = re.sub(r"\s+", " ", record["text"]).strip()
        record["is_heading"] = not has_obligation(text) and len(tokens(text)) < 14
        record["index"] = index
        record["text"] = text
        record["tables"] = record["tables"][:80]
        provisions.append(record)
    doc = {
        "source": str(path),
        "sha256": digest,
        "page_count": len(page_records),
        "printed_version": next((m.group(1) for p in page_records if (m := HEADER_RE.search(p["text"]))), ""),
        "pages": page_records,
        "provisions": provisions,
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc


def provision_index(doc: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for item in doc["provisions"]:
        result[paragraph_key(item["paragraph"])].append(item)
    return result


def align_provisions(old_doc: dict, new_doc: dict) -> dict[str, Any]:
    old, new = old_doc["provisions"], new_doc["provisions"]
    new_by_key = provision_index(new_doc)
    alignments = {}
    for old_item in old:
        exact = new_by_key.get(paragraph_key(old_item["paragraph"]), [])
        scored = []
        for new_item in new:
            text_score = text_similarity(old_item["text"], new_item["text"])
            same_container = old_item["container"] == new_item["container"]
            same_parent = paragraph_key(old_item.get("parent")) == paragraph_key(new_item.get("parent"))
            key_bonus = 0.28 if new_item in exact else 0.0
            context_bonus = 0.08 if same_container else 0.0
            context_bonus += 0.06 if same_parent and old_item.get("parent") else 0.0
            score = min(1.0, text_score + key_bonus + context_bonus)
            scored.append((score, new_item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["index"]))
        alignments[old_item["key"]] = [
            {"new_key": item["key"], "score": round(score, 4), "same_paragraph": item in exact}
            for score, item in scored[:5]
        ]

    unmatched_new = []
    for item in new:
        best = max((text_similarity(item["text"], prior["text"]) for prior in old), default=0.0)
        has_same_key = any(paragraph_key(prior["paragraph"]) == paragraph_key(item["paragraph"]) for prior in old)
        if not has_same_key and best < 0.82:
            unmatched_new.append({"key": item["key"], "best_old_similarity": round(best, 4)})
    return {
        "old_to_new": alignments,
        "unmatched_new": unmatched_new,
        "counts": {"old_provisions": len(old), "new_provisions": len(new), "unmatched_new": len(unmatched_new)},
    }


def _req_source(req: dict) -> tuple[str, int]:
    source = req.get("source") or {}
    return paragraph_key(source.get("paragraph")), int(source.get("page") or 0)


def _best_provision(query: str, items: list[dict]) -> tuple[float, dict | None]:
    best_score, best = 0.0, None
    for item in items:
        score = text_similarity(query, item["text"])
        if score > best_score:
            best_score, best = score, item
    return best_score, best


def _context(doc: dict, item: dict | None, radius: int = 1) -> list[dict]:
    if not item:
        return []
    provisions = doc["provisions"]
    start, end = max(0, item["index"] - radius), min(len(provisions), item["index"] + radius + 1)
    return [
        {k: p[k] for k in ("container", "paragraph", "page", "pages", "parent", "text")}
        for p in provisions[start:end]
    ]


def textwrap_lines(text: str) -> list[str]:
    parts = re.split(r"(?<=[.;:])\s+|(?<=\))\s+(?=[A-Z(])", re.sub(r"\s+", " ", text).strip())
    return [part.strip() for part in parts if part.strip()]


def _short_diff(old: str, new: str, max_chars: int = 3600) -> str:
    diff = "\n".join(difflib.unified_diff(textwrap_lines(old), textwrap_lines(new),
                                          fromfile="old", tofile="new", lineterm=""))
    if len(diff) > max_chars:
        diff = diff[:max_chars] + "\n[diff clipped]"
    return diff or "(no textual difference)"


def _references(text: str) -> set[str]:
    return {paragraph_key(match.group(1)) for match in REFERENCE_RE.finditer(text)}


def _dependency_map(doc: dict) -> dict[str, set[str]]:
    by_para = provision_index(doc)
    graph: dict[str, set[str]] = defaultdict(set)
    for item in doc["provisions"]:
        for reference in _references(item["text"]):
            if reference in by_para:
                graph[item["key"]].update(p["key"] for p in by_para[reference])
    return graph


def candidate_set(old_doc: dict, new_doc: dict, requirements: list[dict], alignment: dict) -> dict[str, Any]:
    old_by_para, new_by_para = provision_index(old_doc), provision_index(new_doc)
    old_candidates = []
    for req in requirements:
        para, page = _req_source(req)
        source_options = old_by_para.get(para, [])
        old_prov = min(source_options, key=lambda p: abs(p["page"] - page)) if source_options else None
        if old_prov is None:
            _, old_prov = _best_provision(req.get("text", ""), old_doc["provisions"])

        same_label = new_by_para.get(para, [])
        scored_new = sorted(
            ((text_similarity(req.get("text", ""), p["text"]) + (0.18 if p in same_label else 0.0), p)
             for p in new_doc["provisions"]),
            key=lambda pair: (-pair[0], pair[1]["index"]),
        )
        picks: list[dict] = []
        seen = set()
        for item in same_label + [pair[1] for pair in scored_new[:4]]:
            if item["key"] not in seen:
                picks.append(item)
                seen.add(item["key"])
        best_new = max(picks, key=lambda p: text_similarity(req.get("text", ""), p["text"]), default=None)
        exact_new = " ".join(p["text"] for p in same_label)
        old_text = old_prov["text"] if old_prov else ""
        if exact_new:
            differs = substantive_delta(old_text, exact_new)
        else:
            sim = text_similarity(req.get("text", ""), best_new["text"]) if best_new else 0.0
            differs = sim < 0.80 or any(
                number not in tokens(best_new["text"])
                for number in obligation_features(req.get("text", ""))["numbers"]
            ) if best_new else True

        reference_targets = _references(req.get("text", "") + " " + old_text)
        referenced_new = []
        for ref in reference_targets:
            old_ref = old_by_para.get(ref, [])
            new_ref = new_by_para.get(ref, [])
            if old_ref and (not new_ref or substantive_delta(" ".join(p["text"] for p in old_ref),
                                                             " ".join(p["text"] for p in new_ref))):
                referenced_new.extend(new_ref)
                differs = True

        if differs:
            old_candidates.append({
                "candidate_id": f"old:{req['id']}",
                "kind": "old_requirement",
                "requirement_id": req["id"],
                "requirement": req,
                "old_provision": old_prov,
                "old_context": _context(old_doc, old_prov),
                "new_candidates": [
                    {k: p[k] for k in ("key", "container", "paragraph", "page", "pages", "parent", "text", "tables")}
                    for p in picks[:4]
                ],
                "new_context": [_context(new_doc, p, 1) for p in picks[:3]],
                "referenced_new": [
                    {k: p[k] for k in ("container", "paragraph", "page", "text")} for p in referenced_new[:8]
                ],
                "diff": _short_diff(old_text, exact_new or (best_new["text"] if best_new else "")),
                "candidate_score": round(max((s for s, _ in scored_new[:3]), default=0.0), 4),
                "confidence_hint": "high" if substantive_delta(old_text, exact_new) else "medium",
            })

    new_candidates = []
    for item in new_doc["provisions"]:
        if item["is_heading"] or not has_obligation(item["text"]):
            continue
        same = old_by_para.get(paragraph_key(item["paragraph"]), [])
        best_score, best_old = _best_provision(item["text"], old_doc["provisions"])
        changed_same = bool(same) and substantive_delta(" ".join(p["text"] for p in same), item["text"])
        if (not same and best_score < 0.80) or changed_same:
            new_candidates.append({
                "candidate_id": f"new:{item['index']}:{hashlib.sha1(item['key'].encode()).hexdigest()[:8]}",
                "kind": "new_provision",
                "new_provision": {k: item[k] for k in ("key", "container", "paragraph", "page", "pages", "parent", "text", "tables")},
                "old_context": _context(old_doc, best_old, 1),
                "new_context": _context(new_doc, item, 1),
                "diff": _short_diff(best_old["text"] if best_old else "", item["text"]),
                "match_score": round(best_score, 4),
                "changed_same_label": changed_same,
            })
    return {
        "old_requirements": old_candidates,
        "new_provisions": new_candidates,
        "counts": {
            "old_requirements": len(old_candidates),
            "new_provisions": len(new_candidates),
            "total_items": len(old_candidates) + len(new_candidates),
        },
        "dependency_map": {key: sorted(value) for key, value in _dependency_map(old_doc).items()},
    }


def render_candidate(candidate: dict) -> str:
    if candidate["kind"] == "old_requirement":
        payload = {
            "candidate_id": candidate["candidate_id"],
            "task": "Reassess one existing requirement against the new regulation.",
            "requirement": candidate["requirement"],
            "old_provision": candidate["old_provision"],
            "old_context": candidate["old_context"],
            "new_candidate_provisions": candidate["new_candidates"],
            "new_surrounding_context": candidate["new_context"],
            "changed_referenced_provisions": candidate["referenced_new"],
            "structured_text_diff": candidate["diff"],
        }
    else:
        payload = {
            "candidate_id": candidate["candidate_id"],
            "task": "Check whether this new/changed provision introduces distinct obligations absent from the old version.",
            "new_provision": candidate["new_provision"],
            "old_nearest_context": candidate["old_context"],
            "new_surrounding_context": candidate["new_context"],
            "structured_text_diff": candidate["diff"],
        }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def prompt_for(batch: list[dict], regulation: str, old_version: str, new_version: str) -> str:
    rendered = "\n\n".join(render_candidate(item) for item in batch)
    return f"""You are a careful regulatory change-impact analyst for engineering requirements.
Compare {regulation} version {old_version} to version {new_version}. Only report changes that alter an actual engineering,
system, manufacturer, test-target, test-procedure, or compliance obligation. Distinguish substantive effects from
formatting, pagination, moved text, renumbering, or editorial wording. A changed legal/technical scope, threshold,
unit, condition, exception, definition, table, annex or cross-reference can change an obligation even when the cited
paragraph itself looks unchanged.

For old_requirement items:
- status unchanged means the underlying obligation remains the same even if wording or numbering changed.
- status modified means the existing obligation changes; return a complete, faithful updated one-obligation text.
- status removed means no corresponding obligation remains; do not invent a substitute.
- reason must cite the new regulation paragraph and identify the substantive delta; distinguish editorial changes.
- source must cite the actual new PDF printed page and paragraph where the updated obligation is stated.
- Do not mark an unchanged requirement just because its paragraph was reformatted or renumbered.

For new_provision items:
- return zero new_obligations if the provision is editorial, duplicates an old obligation, or does not introduce an
  obligation relevant to the existing regulation's requirement set.
- otherwise return one entry per distinct new obligation, preserving conditions and values. Include mandatory test
  procedures/targets as obligations when the regulation requires them.
- cite only the displayed new-version page and paragraph; never invent a citation.

Every candidate must appear exactly once in items. Use only the supplied candidate IDs. Return valid structured JSON.

Candidates:
{rendered}"""


def _estimate(batches: list[list[dict]], smoke: bool = True) -> dict[str, float | int]:
    prompt_chars = sum(len(prompt_for(batch, "UN R175", "0.1.0", "1.0.0")) for batch in batches)
    input_tokens = int(prompt_chars / 3.6 * 1.15)
    output_tokens = sum(230 if item["kind"] == "old_requirement" else 480 for batch in batches for item in batch)
    if smoke and batches:
        prompt = prompt_for(batches[0][:1], "UN R175", "0.1.0", "1.0.0")
        input_tokens += int(len(prompt) / 3.6 * 1.15)
        output_tokens += 300
    low = input_tokens * PRICE["input_tokens"] / 1_000_000 + output_tokens * PRICE["output_tokens"] / 1_000_000
    return {
        "requests": len(batches) + (1 if smoke and batches else 0),
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_cost_usd_low": round(low, 4),
        "estimated_cost_usd_high": round(low * 1.8 + 0.03, 4),
        "estimated_runtime_minutes_low": round(max(1, len(batches) / 2 * 0.15 + 0.5), 1),
        "estimated_runtime_minutes_high": round(max(3, len(batches) / 2 * 0.45 + 2), 1),
    }


def _batches(items: list[dict], size: int = 4) -> list[list[dict]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _cache_call(prompt: str, batch: list[dict], cache_dir: Path, model: str) -> dict:
    cache_key = hashlib.sha256((model + "\n" + prompt).encode()).hexdigest()
    cache_path = cache_dir / f"llm-{cache_key}.json"
    if cache_path.is_file():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    from jsonschema import Draft202012Validator
    from retrieval import llm

    last_error = None
    for attempt in range(3):
        try:
            response = llm.structured(prompt, STRUCTURED_SCHEMA, model=model, effort="medium", max_tokens=12000)
            errors = list(Draft202012Validator(STRUCTURED_SCHEMA).iter_errors(response))
            if errors:
                raise ValueError("; ".join(error.message for error in errors[:3]))
            wanted = {item["candidate_id"] for item in batch}
            got = [row["candidate_id"] for row in response["items"]]
            if set(got) != wanted or len(got) != len(wanted):
                raise ValueError(f"response candidate IDs mismatch; wanted={sorted(wanted)}, got={got}")
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
            return response
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"LLM batch failed after retries: {last_error}") from last_error


def _llm_verify(
    items: list[dict], cache_dir: Path, model: str, workers: int, usage_log: Path,
) -> tuple[list[dict], dict]:
    from retrieval import llm

    totals = {key: 0 for key in PRICE}
    api_calls = 0
    lock = threading.Lock()
    usage_log.parent.mkdir(parents=True, exist_ok=True)

    def on_usage(value: dict) -> None:
        nonlocal api_calls
        with lock:
            api_calls += 1
            for key in totals:
                totals[key] += int(value.get(key, 0) or 0)
            amount = sum(totals[k] * PRICE[k] for k in PRICE) / 1_000_000
            with usage_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "api_call": api_calls, "model": value.get("model", model), **value,
                    "cumulative_estimated_usd_at_configured_rates": round(amount, 6),
                    "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }) + "\n")
            print(
                f"[API {api_calls}] {value.get('model', model)}: input {value.get('input_tokens',0):,}, "
                f"output {value.get('output_tokens',0):,}, estimated spend USD {amount:.4f}",
                flush=True,
            )

    llm.USAGE_CALLBACK = on_usage
    batches = _batches(items)
    responses = []
    try:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 2))) as pool:
            futures = [
                pool.submit(
                    _cache_call,
                    prompt_for(batch, "UN R175", "0.1.0", "1.0.0"),
                    batch, cache_dir, model,
                )
                for batch in batches
            ]
            for future in futures:
                responses.append(future.result())
    finally:
        llm.USAGE_CALLBACK = None
    flattened = [row for response in responses for row in response["items"]]
    actual_cost = sum(totals[k] * PRICE[k] for k in PRICE) / 1_000_000
    return flattened, {
        "requests_expected_uncached": len(batches),
        "api_calls_this_run": api_calls,
        "tokens": totals,
        "estimated_api_cost_usd": round(actual_cost, 6),
        "model": model,
    }


def _verified_submission(rows: list[dict], team_id: str, case_id: str, candidate_map: dict[str, dict]) -> dict:
    changes = []
    used_old: set[str] = set()
    seen_added: list[dict] = []
    for row in rows:
        candidate = candidate_map[row["candidate_id"]]
        status = row["old_requirement_status"]
        if candidate["kind"] == "old_requirement":
            req = candidate["requirement"]
            rid = req["id"]
            if rid not in used_old and status in ("modified", "removed"):
                change = {"requirement_id": rid, "change": status}
                if status == "modified" and row.get("new_text") and row.get("reason"):
                    change["new_text"] = row["new_text"][:2000]
                    page = row.get("source_page")
                    para = row.get("source_paragraph")
                    if not page:
                        best = candidate["new_candidates"][0] if candidate["new_candidates"] else None
                        page = best.get("page") if best else None
                        para = best.get("paragraph") if best else None
                    if page:
                        change["source"] = {"page": int(page), **({"paragraph": para} if para else {})}
                    else:
                        continue
                    change["reason"] = row["reason"]
                    changes.append(change)
                    used_old.add(rid)
                elif status == "removed" and row.get("reason"):
                    change["reason"] = row["reason"]
                    changes.append(change)
                    used_old.add(rid)
        for added in row.get("new_obligations", []):
            text = " ".join(added["text"].split())[:2000]
            if not text:
                continue
            citation = {"page": int(added["page"])}
            if added.get("paragraph"):
                citation["paragraph"] = added["paragraph"]
            candidate_added = {
                "requirement_id": None, "change": "added", "new_text": text,
                "reason": added["reason"], "source": citation,
            }
            if not any(
                item["source"].get("paragraph") == citation.get("paragraph")
                and text_similarity(item["new_text"], text) > 0.90
                for item in seen_added
            ):
                seen_added.append(candidate_added)
    changes.extend(seen_added)
    return {"team_id": team_id, "case_id": case_id, "changes": changes}


def _best_new_for_req(req: dict, old_doc: dict, new_doc: dict) -> tuple[dict | None, dict | None]:
    old_by, new_by = provision_index(old_doc), provision_index(new_doc)
    para, page = _req_source(req)
    old_options = old_by.get(para, [])
    old_item = min(old_options, key=lambda p: abs(p["page"] - page)) if old_options else _best_provision(req.get("text", ""), old_doc["provisions"])[1]
    exact = new_by.get(para, [])
    if exact:
        return old_item, max(exact, key=lambda p: text_similarity(req.get("text", ""), p["text"]))
    _, best = _best_provision(req.get("text", ""), new_doc["provisions"])
    return old_item, best


def deterministic_submission(
    level: str, old_doc: dict, new_doc: dict, requirements: list[dict], candidates: dict, team_id: str, case_id: str,
) -> dict:
    changes = []
    base_old = {c["requirement_id"]: c for c in candidates["old_requirements"]}
    impacted_ids = set(base_old)
    if level == "text":
        impacted_ids = set(base_old)
    elif level == "semantic":
        impacted_ids = {
            req["id"] for req in requirements if req["id"] in base_old
            and (base_old[req["id"]]["confidence_hint"] == "high"
                 or base_old[req["id"]]["candidate_score"] < 0.60)
        }
    elif level == "crossref":
        impacted_ids = set(base_old)

    for req in requirements:
        if req["id"] not in impacted_ids:
            continue
        _, new_item = _best_new_for_req(req, old_doc, new_doc)
        if new_item and text_similarity(req.get("text", ""), new_item["text"]) < 0.18:
            changes.append({
                "requirement_id": req["id"], "change": "removed",
                "reason": f"Old obligation from paragraph {req.get('source', {}).get('paragraph','')} could not be located in the new version.",
            })
        elif new_item:
            changes.append({
                "requirement_id": req["id"], "change": "modified", "new_text": new_item["text"][:2000],
                "reason": f"Textual comparison found a provision change near paragraph {new_item['paragraph']}.",
                "source": {"page": new_item["page"], "paragraph": new_item["paragraph"]},
            })

    for candidate in candidates["new_provisions"]:
        item = candidate["new_provision"]
        if level == "semantic" and candidate["match_score"] > 0.35 and not candidate["changed_same_label"]:
            continue
        changes.append({
            "requirement_id": None, "change": "added", "new_text": item["text"][:2000],
            "reason": f"Textual diff identifies a potentially new obligation in paragraph {item['paragraph']}.",
            "source": {"page": item["page"], "paragraph": item["paragraph"]},
        })
    return {"team_id": team_id, "case_id": case_id, "changes": changes}


def _validate_submission(submission: dict, old: list[dict], schema_path: Path) -> list[str]:
    from jsonschema import Draft202012Validator

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    issues = [error.message for error in Draft202012Validator(schema).iter_errors(submission)]
    valid_ids = {item["id"] for item in old}
    for index, change in enumerate(submission.get("changes", [])):
        if change.get("change") in ("modified", "removed") and change.get("requirement_id") not in valid_ids:
            issues.append(f"changes[{index}] uses unknown requirement id")
        source = change.get("source")
        if change.get("change") in ("modified", "added") and (not source or int(source.get("page", 0)) < 1):
            issues.append(f"changes[{index}] is missing a valid new-version citation")
    return issues


def run_case(args, root: Path) -> int:
    print(f"[prepare] Loading {args.case} inputs and cached regulation text", flush=True)
    challenge = Path(os.environ.get("INDUSTRIAL_AI_HACKATHON", root.parents[2].parent / "industrial-ai-hackathon"))
    case_dir = challenge / "subgoal" / args.case
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    if args.case != "dev":
        case_config = root / "cases" / args.case / "config.json"
        if not case_config.is_file():
            raise SystemExit(f"No configuration for case {args.case}: {case_config}")
        config.update(json.loads(case_config.read_text(encoding="utf-8")))
    old_pdf = root / "data" / "subgoal" / args.case / "old.pdf"
    new_pdf = root / "data" / "subgoal" / args.case / "new.pdf"
    old_json = case_dir / "requirements_old.json"
    expected_json = case_dir / "expected.json"
    schema_path = challenge / "schemas" / "submission_subgoal.schema.json"
    output_dir = root / "outputs" if args.case == "dev" else root / "outputs" / args.case
    cache_dir = root / ".cache"
    required = (old_pdf, new_pdf, old_json, schema_path)
    if not all(path.is_file() for path in required):
        missing = [str(path) for path in required if not path.is_file()]
        raise SystemExit("Required case inputs are missing:\n" + "\n".join(missing))
    requirements = json.loads(old_json.read_text(encoding="utf-8"))
    from tool_agent import analyze as tool_analyze, as_alignment_doc, ingest_versions, smoke_test
    ingested = ingest_versions(root, args.case, old_pdf, new_pdf, regulation=config["regulation"],
                               old_version=config["old_version"], new_version=config["new_version"], output_dir=output_dir)
    old_doc = as_alignment_doc(ingested["old_doc"], sha256_file(old_pdf))
    new_doc = as_alignment_doc(ingested["new_doc"], ingested["new_sha256"])
    if args.assemble_only:
        saved_preflight_path=output_dir/f"preflight-{args.case}.json"
        if not saved_preflight_path.is_file():
            raise ValueError("Assembly-only requires the preflight from the cached run. No API calls were made.")
        saved_preflight=json.loads(saved_preflight_path.read_text(encoding="utf-8"))
        for key,current in (("old_pdf_sha256",old_doc["sha256"]),("new_pdf_sha256",new_doc["sha256"]),("model",config.get("model",DEFAULT_MODEL))):
            if saved_preflight.get(key)!=current:
                raise ValueError(f"Assembly-only inputs differ from the cached run: {key}. No API calls were made.")
    from preparation_cache import cached_prepare
    preparation_dir = cache_dir / "preparation" / args.case
    preparation_sources = [Path(__file__), root / "src" / "tool_agent.py",
                           root / "src" / "preparation_cache.py"]
    preparation_inputs = {"old_doc": old_doc, "new_doc": new_doc, "requirements": requirements}
    alignment = cached_prepare(preparation_dir, "alignment", preparation_inputs,
                               preparation_sources, lambda: align_provisions(old_doc, new_doc))
    candidate_data = cached_prepare(preparation_dir, "candidates", preparation_inputs,
                                   preparation_sources,
                                   lambda: candidate_set(old_doc, new_doc, requirements, alignment))

    benchmark_path = root / "benchmarking" / f"ablation-{args.case}.json"
    benchmark_path.parent.mkdir(parents=True, exist_ok=True)
    results = {}
    ablations = ("text", "semantic", "crossref", "agent", "exhaustive") if args.ablation == "all" else ("exhaustive" if args.ablation == "llm" else args.ablation,)
    exhaustive_requested = "exhaustive" in ablations
    exhaustive_work = None
    exhaustive_alignment = None
    exhaustive_plan = None
    if exhaustive_requested:
        from exhaustive import build_work as build_exhaustive_work, estimate as estimate_exhaustive
        exhaustive_old, exhaustive_new, exhaustive_alignment = cached_prepare(
            preparation_dir, "exhaustive-work",
            {"old_doc": ingested["old_doc"], "new_doc": ingested["new_doc"],
             "requirements": requirements},
            preparation_sources + [root / "src" / "exhaustive.py"],
            lambda: build_exhaustive_work(requirements, ingested["old_doc"], ingested["new_doc"]))
        exhaustive_work = (exhaustive_old, exhaustive_new)
        exhaustive_plan = estimate_exhaustive(exhaustive_old, exhaustive_new)
    for level in ablations:
        if level in ("agent", "exhaustive"):
            continue
        results[level] = deterministic_submission(level, old_doc, new_doc, requirements, candidate_data,
                                                  args.team_id, config["case_id"])
    batches = _batches(candidate_data["old_requirements"] + candidate_data["new_provisions"])
    diff_tokens = int(len(ingested["diff"]) / 3.6 * 1.15)
    estimated_input_low, estimated_input_high = diff_tokens + 10000, diff_tokens + 120000
    estimated_output_low, estimated_output_high = 5000, 60000
    legacy_estimate = {
        "expected_model_turns": "12-30, depending on tool exploration",
        "estimated_input_tokens_range": [estimated_input_low, estimated_input_high],
        "estimated_output_tokens_range": [estimated_output_low, estimated_output_high],
        "estimated_cost_usd_low": round((estimated_input_low*2 + estimated_output_low*10)/1_000_000, 4),
        "estimated_cost_usd_high": round((estimated_input_high*2 + estimated_output_high*10)/1_000_000, 4),
        "estimated_runtime_minutes_range": [2, 20],
    }
    estimate = {"exhaustive": exhaustive_plan, "legacy_agent": legacy_estimate} if exhaustive_requested else legacy_estimate
    if args.assemble_only:
        estimate={"assembly_only":True,"new_api_requests":0,"estimated_api_cost_usd":0.0}
    output_dir.mkdir(parents=True, exist_ok=True)
    preflight = {
        "case": args.case, "model": config.get("model", DEFAULT_MODEL),
        "old_pdf_sha256": old_doc["sha256"], "new_pdf_sha256": new_doc["sha256"],
        "parse_counts": {
            "old_pages": old_doc["page_count"], "new_pages": new_doc["page_count"],
            "old_provisions": len(old_doc["provisions"]), "new_provisions": len(new_doc["provisions"]),
        },
        "alignment": alignment["counts"], "candidate_counts": candidate_data["counts"],
        "exhaustive_coverage": exhaustive_plan,
        "diff_lines": len(ingested["diff"].splitlines()), "diff_chars": len(ingested["diff"]),
        "new_text_cache_sha256": ingested["new_sha256"],
        "estimate": estimate,
    }
    (output_dir / f"preflight-{args.case}.json").write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    (output_dir / f"alignment-{args.case}.json").write_text(json.dumps(alignment, indent=2) + "\n", encoding="utf-8")
    if exhaustive_alignment is not None:
        (output_dir / f"alignment-{args.case}-exhaustive.json").write_text(json.dumps(exhaustive_alignment,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (output_dir / f"candidates-{args.case}.json").write_text(json.dumps(candidate_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(preflight, indent=2), flush=True)
    if args.estimate_only:
        return 0

    if "agent" in ablations:
        items = candidate_data["old_requirements"] + candidate_data["new_provisions"]
        model = config.get("model", DEFAULT_MODEL)
        os.environ["ANTHROPIC_MODEL"] = model
        state = {
            "old_text": ingested["old_text"], "new_text": ingested["new_text"], "diff": ingested["diff"],
            "old_clauses": ingested["old_doc"]["clauses"], "new_clauses": ingested["new_doc"]["clauses"],
            "requirements": requirements, "req_by_id": {r["id"]:r for r in requirements},
            "new_page_count": ingested["new_pages"], "regulation": config["regulation"],
            "old_version": config["old_version"], "new_version": config["new_version"],
        }
        usage_log = output_dir / f"usage-{args.case}.jsonl"
        if candidate_data["old_requirements"]:
            smoke_path=output_dir / f"smoke-{args.case}.json"
            if smoke_path.is_file():
                smoke_usage=json.loads(smoke_path.read_text(encoding="utf-8")).get("usage",{})
                print("Reusing the completed structured smoke check; continuing with diff-driven tool review.",flush=True)
            else:
                smoke_result, smoke_usage = smoke_test(candidate_data["old_requirements"][0], model, usage_log)
                smoke_path.write_text(json.dumps({"result":smoke_result,"usage":smoke_usage},indent=2)+"\n",encoding="utf-8")
                print("Structured smoke check passed; continuing with diff-driven tool review.",flush=True)
        rows, usage = tool_analyze(state, model, usage_log, output_dir / f"checkpoint-{args.case}.json")
        submission = {"team_id":args.team_id,"case_id":config["case_id"],"changes":rows}
        (output_dir / f"usage-summary-{args.case}.json").write_text(json.dumps({**usage,"smoke":smoke_usage if candidate_data["old_requirements"] else {},"estimate":estimate},indent=2)+"\n",encoding="utf-8")
        problems = _validate_submission(submission, requirements, schema_path)
        if problems:
            raise RuntimeError("Submission validation failed:\n" + "\n".join(problems))
        results["agent"] = submission

    if exhaustive_requested:
        from exhaustive import run_exhaustive
        model=config.get("model",DEFAULT_MODEL)
        os.environ["ANTHROPIC_MODEL"]=model
        exhaustive_submission,audit=run_exhaustive(
            requirements,ingested["old_doc"],ingested["new_doc"],config["regulation"],config["old_version"],
            config["new_version"],model,cache_dir/"exhaustive"/args.case,output_dir,args.team_id,config["case_id"],
            assemble_only=args.assemble_only,
            prepared_work=(*exhaustive_work, exhaustive_alignment))
        problems=_validate_submission(exhaustive_submission,requirements,schema_path)
        if problems:raise RuntimeError("Exhaustive submission validation failed:\n"+"\n".join(problems))
        results["exhaustive"]=exhaustive_submission
        (output_dir/f"assessment-{args.case}-exhaustive.json").write_text(json.dumps(audit,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

    if expected_json.is_file():
        from benchmark import score
        for label, submission in results.items():
            audit_path=output_dir/f"assessment-{args.case}-exhaustive.json"
            audit=json.loads(audit_path.read_text(encoding="utf-8")) if label=="exhaustive" and audit_path.is_file() else None
            report = score(submission, json.loads(expected_json.read_text(encoding="utf-8")), audit=audit)
            (output_dir / f"evaluation-{args.case}-{label}.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print(f"{label}: old-impact P/R={report['old_requirement_impact']['precision']:.3f}/"
                  f"{report['old_requirement_impact']['recall']:.3f}; added proxy P/R="
                  f"{report['added_obligation_proxy']['precision']:.3f}/"
                  f"{report['added_obligation_proxy']['recall']:.3f}")

    for label, submission in results.items():
        path = output_dir / f"subgoal-{args.case}-{label}.json"
        path.write_text(json.dumps(submission, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{label}: wrote {len(submission['changes'])} changes -> {path}")
    if args.ablation in ("llm","exhaustive"):
        final_path = output_dir / f"subgoal-{args.case}.json"
        final_path.write_text(json.dumps(results["exhaustive"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Submission: {final_path}")
    if args.ablation == "all":
        summary = {}
        for label in results:
            result_file = output_dir / f"evaluation-{args.case}-{label}.json"
            if result_file.is_file():
                evaluation = json.loads(result_file.read_text(encoding="utf-8"))
                summary[label] = {
                    "old_requirement_impact": evaluation["old_requirement_impact"],
                    "matched_by_change_type":evaluation["matched_by_change_type"],
                    "change_type_accuracy": evaluation["change_type_accuracy_on_matched_ids"],
                    "added_obligation_proxy": evaluation["added_obligation_proxy"],
                }
        (output_dir / f"ablation-{args.case}.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
    return 0
