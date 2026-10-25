"""Exhaustive, bounded LLM reviews for existing requirements and new clause obligations."""
from __future__ import annotations

import hashlib
import difflib
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

PRICE={"input_tokens":2.0,"output_tokens":10.0,"cache_read_input_tokens":0.10,"cache_creation_input_tokens":2.50}

OLD_SCHEMA = {
    "type": "object",
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "requirement_id": {"type": "string"},
                    "decision": {"type": "string", "enum": ["unchanged", "modified", "removed"]},
                    "new_text": {"type": ["string", "null"], "maxLength": 2000},
                    "reason": {"type": "string", "minLength": 1},
                    "source_page": {"type": ["integer", "null"], "minimum": 1},
                    "source_paragraph": {"type": ["string", "null"]},
                },
                "required": ["requirement_id", "decision", "new_text", "reason", "source_page", "source_paragraph"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["reviews"],
    "additionalProperties": False,
}

NEW_SCHEMA = {
    "type": "object",
    "properties": {
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_id": {"type": "string"},
                    "coverage": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_unit": {"type": "string", "minLength": 1},
                                "obligation_index": {"type": ["integer", "null"], "minimum": 0},
                                "exclusion_reason": {"type": ["string", "null"]},
                            },
                            "required": ["source_unit", "obligation_index", "exclusion_reason"],
                            "additionalProperties": False,
                        },
                    },
                    "obligations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "minLength": 1, "maxLength": 2000},
                                "novelty": {"type": "string", "enum": ["new", "existing", "modified_existing"]},
                                "reason": {"type": "string", "minLength": 1},
                                "page": {"type": "integer", "minimum": 1},
                                "paragraph": {"type": ["string", "null"]},
                                "old_match": {"type": ["string", "null"]},
                            },
                            "required": ["text", "novelty", "reason", "page", "paragraph", "old_match"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["clause_id", "coverage", "obligations"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clauses"],
    "additionalProperties": False,
}


def _norm(text: str) -> str:
    text=text.casefold().replace("per cent","percent").replace("%"," percent ").replace("°"," degree ")
    return re.sub(r"[^a-z0-9]+"," ",text).strip()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z]+|\d+(?:[.,]\d+)*",_norm(text))


def _sim(a: str,b: str) -> float:
    x,y=_tokens(a),_tokens(b)
    if not x or not y:return 0.0
    ca,cb=Counter(x),Counter(y); common=sum((ca&cb).values())
    p,r=common/len(x),common/len(y)
    return 2*p*r/(p+r) if p+r else 0.0


def _label(value: Any) -> str:
    return re.sub(r"[\s.,:;]+$","",str(value or "")).casefold()


def _refs(text: str) -> set[str]:
    return {_label(m.group(1)) for m in re.finditer(r"\b(?:paragraph|section|para(?:graph)?)\s+(\d{1,2}(?:\.\d{1,3}){0,6})",text,re.I)}


def _clause_obj(row: dict, ident: str) -> dict:
    pages=[int(x) for x in row.get("pages",[]) if x]
    return {"id":ident,"paragraph":row.get("paragraph"),"pages":pages,"text":row.get("text","")}


def _same_text(left: str, right: str) -> bool:
    # Only layout whitespace is ignored: preserve case, punctuation, numbers and units.
    return bool(left.strip()) and " ".join(left.split()) == " ".join(right.split())


def _unchanged_gate(req: dict, old_clause: dict | None, old_by: dict, new_by: dict,
                    flagged: set[str]) -> dict:
    """Conservative shortcut; ambiguity or changed dependencies requires model review."""
    checked = []
    def result(eligible: bool, reason: str) -> dict:
        return {"automatic_unchanged": eligible, "reason": reason, "checked_paragraphs": checked}

    source = req.get("source") or {}
    key = _label(source.get("paragraph"))
    if not old_clause or not key or len(old_by.get(key, [])) != 1 or len(new_by.get(key, [])) != 1:
        return result(False, "Source or same-paragraph counterpart is missing or ambiguous.")
    if source.get("page") not in old_clause["pages"]:
        return result(False, "Original source page is not confirmed by the parsed clause.")
    pending = [key]
    seen = set()
    texts = [req.get("text", "")]
    while pending or texts:
        if pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            old_rows, new_rows = old_by.get(current, []), new_by.get(current, [])
            if len(old_rows) != 1 or len(new_rows) != 1:
                return result(False, f"Dependency {current} is missing or ambiguous.")
            old_row, new_row = old_rows[0], new_rows[0]
            if old_row["id"] in flagged or new_row["id"] in flagged:
                return result(False, f"Parser marked {current} for boundary review.")
            if not _same_text(old_row["text"], new_row["text"]):
                return result(False, f"Source or dependency {current} changed.")
            checked.append(current)
            texts.append(old_row["text"])
            # Governing numbered parents can alter applicability without editing the leaf.
            parent = current
            while "." in parent:
                parent = parent.rsplit(".", 1)[0]
                if parent in old_by or parent in new_by:
                    pending.append(parent)
            scoped_parent = current
            while " / " in scoped_parent:
                scoped_parent = scoped_parent.rsplit(" / ", 1)[0]
                if scoped_parent in old_by or scoped_parent in new_by:
                    pending.append(scoped_parent)
        else:
            text = texts.pop()
            if re.search(r"\b(?:paragraphs|sections|tables|annexes)\b|\b(?:above|below|preceding|following)\s+(?:paragraph|section|table)\b", text, re.I):
                return result(False, "Grouped or relative references require semantic review.")
            if re.search(r"\b(?:paragraph|section)\s+\d+(?:\.\d+)*\.?\s*(?:to\b|through\b|and\b|or\b|[-–])", text, re.I):
                return result(False, "A reference range or list requires semantic review.")
            references = set(_refs(text))
            for kind, label in re.findall(r"\b(Table|Annex)\s+(\d+[A-Za-z]?)\b", text, re.I):
                root = f"{kind.casefold()} {label.casefold()}"
                labels = {p for p in set(old_by) | set(new_by)
                          if p == root or p.startswith(root + " ") or p.startswith(root + ".")}
                if not labels:
                    return result(False, f"Referenced {root} cannot be resolved.")
                references.update(labels)
            for ref in references:
                # Include a referenced section's children, including inserted/deleted children.
                pending.append(ref)
                pending.extend(p for p in set(old_by) | set(new_by) if p.startswith(ref + "."))

    # An unreferenced definition can still change a term used in an otherwise identical rule.
    context = " ".join([req.get("text", "")] + [old_by[p][0]["text"] for p in checked]).casefold()
    for label in sorted(set(old_by) | set(new_by)):
        if not (label == "2" or label.startswith("2.")):
            continue
        old_rows, new_rows = old_by.get(label, []), new_by.get(label, [])
        if len(old_rows) == len(new_rows) == 1 and _same_text(old_rows[0]["text"], new_rows[0]["text"]):
            continue
        definition = " ".join(row["text"] for row in old_rows + new_rows)
        terms = re.findall(r'["“]([^"”]+)["”]', definition)
        if not terms:
            return result(False, f"Changed definition/scope in {label} cannot be resolved safely.")
        if any(re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", context) for term in terms):
            return result(False, f"A definition used by this requirement changed in {label}.")
    return result(True, "Source wording, numbered parents and resolved dependencies are unchanged; no changed definition was found for terms used here.")


def _evidence_spans(clauses: list[dict]) -> list[dict]:
    """Retain provenance while finding sentences/list items inside all parsed blocks."""
    spans = []
    for clause in clauses:
        flat = " ".join(clause["text"].split())
        parts = [p.strip() for p in re.split(r"(?=\([a-z]\)\s)|(?<=[.!?;])\s+(?=[A-Z(])", flat) if p.strip()]
        for index, part in enumerate(parts):
            text = re.sub(r"^\([a-z0-9]+\)\s*", "", part)
            label = _label(clause.get("paragraph"))
            if re.fullmatch(r"\d+(?:\.\d+)*", label):
                text = re.sub(r"^" + re.escape(label) + r"\.?\s+", "", text, count=1)
            if len(_tokens(text)) < 5:
                continue
            spans.append({"block_id": clause["id"], "paragraph": clause["paragraph"],
                          "pages": clause["pages"], "text": text,
                          "preceding_context": parts[index-1][-500:] if index else "",
                          "following_context": parts[index+1][:500] if index+1 < len(parts) else ""})
    return spans


def _rank_evidence(query: str, spans: list[dict], limit: int) -> list[dict]:
    ranked = sorted(((_sim(query, span["text"]), i, span) for i, span in enumerate(spans)),
                    key=lambda item: (-item[0], item[1]))
    result, seen = [], set()
    for similarity, _, span in ranked:
        if span["block_id"] in seen:
            continue
        seen.add(span["block_id"])
        result.append({**span, "similarity": round(similarity, 4)})
        if len(result) >= limit:
            break
    return result


def _word_edits(old_text: str, new_text: str) -> list[dict]:
    # Preserve qualifiers, case, punctuation, decimal values and units in the comparison.
    pattern = r"\d+(?:\.\d+)*|[^\W\d_]+|[^\w\s]"
    old_tokens, new_tokens = re.findall(pattern, old_text), re.findall(pattern, new_text)
    edits = []
    for operation, a, b, c, d in difflib.SequenceMatcher(None, old_tokens, new_tokens, autojunk=False).get_opcodes():
        if operation != "equal":
            edits.append({"operation": operation, "old": " ".join(old_tokens[a:b]),
                          "new": " ".join(new_tokens[c:d]),
                          "old_context": " ".join(old_tokens[max(0,a-6):min(len(old_tokens),b+6)]),
                          "new_context": " ".join(new_tokens[max(0,c-6):min(len(new_tokens),d+6)])})
    return edits


def _related_context(text: str, by_label: dict) -> list[dict]:
    labels = set(_refs(text))
    for kind, number in re.findall(r"\b(Table|Annex)\s+(\d+[A-Za-z]?)\b", text, re.I):
        root = f"{kind.casefold()} {number.casefold()}"
        labels.update(label for label in by_label if label == root or label.startswith(root + " / "))
    return [clause for label in sorted(labels) for clause in by_label.get(label, [])][:5]


def build_work(requirements: list[dict], old_doc: dict, new_doc: dict) -> tuple[list[dict],list[dict],dict]:
    old=[_clause_obj(c,f"o{i:03}") for i,c in enumerate(old_doc["clauses"])]
    new=[_clause_obj(c,f"n{i:03}") for i,c in enumerate(new_doc["clauses"])]
    old_by:dict[str,list[dict]]={}
    new_by:dict[str,list[dict]]={}
    for c in old:old_by.setdefault(_label(c["paragraph"]),[]).append(c)
    for c in new:new_by.setdefault(_label(c["paragraph"]),[]).append(c)
    flagged = {c["id"] for c, raw in zip(old, old_doc["clauses"]) if raw.get("review_flags")}
    flagged.update(c["id"] for c, raw in zip(new, new_doc["clauses"]) if raw.get("review_flags"))
    old_spans, new_spans = _evidence_spans(old), _evidence_spans(new)

    def nearest(query: str, clauses: list[dict], limit=4):
        ranked=sorted(((_sim(query,c["text"]),c) for c in clauses),key=lambda pair:(-pair[0],pair[1]["id"]))
        return [{**c,"similarity":round(score,4)} for score,c in ranked[:limit]]

    old_work=[]
    for req in requirements:
        src=req.get("source") or {}; para=_label(src.get("paragraph")); page=int(src.get("page") or 0)
        options=old_by.get(para,[])
        old_clause=min(options,key=lambda c:min((abs(page-p) for p in c["pages"]),default=page)) if options else (nearest(req.get("text",""),old,1)[0] if old else None)
        query=(old_clause or {}).get("text",req.get("text",""))
        old_evidence = _rank_evidence(req.get("text", ""), old_spans, 2)
        new_evidence = _rank_evidence(req.get("text", ""), new_spans, 3)
        comparison_text = old_evidence[0]["text"] if old_evidence else req.get("text", "")
        comparisons = [{"old_evidence": old_evidence[0] if old_evidence else None,
                        "new_evidence": evidence,
                        "word_changes": _word_edits(comparison_text, evidence["text"])} for evidence in new_evidence]
        matches=[]; seen=set()
        for c in new_by.get(para,[]):
            matches.append({**c,"similarity":round(_sim(query,c["text"]),4)});seen.add(c["id"])
        for c in nearest(query,new,5):
            if c["id"] not in seen:matches.append(c);seen.add(c["id"])
        evidence_scores = {span["block_id"]: span["similarity"] for span in new_evidence}
        for clause in new:
            if clause["id"] in evidence_scores and clause["id"] not in seen:
                matches.append({**clause,"similarity":evidence_scores[clause["id"]]})
                seen.add(clause["id"])
        for match in matches:
            match["similarity"] = max(match["similarity"], evidence_scores.get(match["id"], 0.0))
        matches.sort(key=lambda c:(-c["similarity"],c["id"]))
        reference_text = req.get("text", "")+" "+query+" "+comparison_text
        old_related = _related_context(reference_text, old_by)
        new_related = _related_context(reference_text, new_by)
        gate = _unchanged_gate(req, old_clause, old_by, new_by, flagged)
        if gate["automatic_unchanged"] and old_evidence and old_evidence[0]["block_id"] != old_clause["id"]:
            gate = {**gate,"automatic_unchanged":False,"reason":"Best obligation evidence is outside the cited parsed block; boundary needs model review."}
        old_work.append({"requirement":req,"old_clause":old_clause,"new_matches":matches[:5],"unchanged_gate":gate,
                         "old_obligation_evidence":old_evidence,"obligation_comparisons":comparisons,
                         "old_referenced_clauses":old_related,"new_referenced_clauses":new_related})

    def scoped(clause: dict, by_paragraph: dict) -> dict:
        # Parent introductions carry applicability that repeated step text omits.
        label = _label(clause.get("paragraph"))
        parents = []
        while "." in label:
            label = label.rsplit(".", 1)[0]
            parents.extend(by_paragraph.get(label, []))
        return {**clause, "parent_context": list(reversed(parents))}

    new_work=[]
    for clause in new:
        para=_label(clause["paragraph"])
        exact=old_by.get(para,[])
        matches=[{**c,"similarity":round(_sim(clause["text"],c["text"]),4)} for c in exact]
        seen={c["id"] for c in matches}
        for c in nearest(clause["text"],old,3):
            if c["id"] not in seen:matches.append(c);seen.add(c["id"])
        matches.sort(key=lambda c:(-c["similarity"],c["id"]))
        new_work.append({"clause":scoped(clause, new_by),
                         "paragraph_existed_before":bool(exact),
                         "old_matches":[scoped(c, old_by) for c in matches[:4]]})
    align={"existing_requirement_count":len(old_work),"new_clause_count":len(new_work),
           "existing_requirements":[{"id":x["requirement"]["id"],"old_clause":(x["old_clause"] or {}).get("id"),
             "old_paragraph":(x["old_clause"] or {}).get("paragraph"),"unchanged_gate":x["unchanged_gate"],
             "old_obligation_evidence":x["old_obligation_evidence"],"obligation_comparisons":x["obligation_comparisons"],
             "new_matches":[{"id":c["id"],"paragraph":c["paragraph"],"similarity":c["similarity"]} for c in x["new_matches"]]} for x in old_work],
           "new_clauses":[{"id":x["clause"]["id"],"paragraph":x["clause"]["paragraph"],
             "old_matches":[{"id":c["id"],"paragraph":c["paragraph"],"similarity":c["similarity"]} for c in x["old_matches"]]} for x in new_work]}
    return old_work,new_work,align


def _chunks(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i:i+size] for i in range(0,len(items),size)]


def estimate(old_work: list[dict],new_work: list[dict],old_batch=10,new_batch=6) -> dict:
    # Conservative planning estimate from exact serialized prompt sizes plus response allowance.
    total_old = len(old_work)
    old_work = [x for x in old_work if not x["unchanged_gate"]["automatic_unchanged"]]
    old_input=sum(len(json.dumps(batch,ensure_ascii=False)) for batch in _chunks(old_work,old_batch))
    new_input=sum(len(json.dumps(batch,ensure_ascii=False)) for batch in _chunks(new_work,new_batch))
    in_tokens=int((old_input+new_input)/3.6*1.15)
    req_tokens=len(old_work)*90+len(new_work)*260
    requests=len(_chunks(old_work,old_batch))+len(_chunks(new_work,new_batch))
    low=(in_tokens*2+req_tokens*10)/1e6
    high=(int(in_tokens*1.6)*2+int(req_tokens*2.5)*10)/1e6
    return {"existing_requirement_reviews":total_old,"existing_requirement_llm_reviews":len(old_work),
            "existing_requirement_automatic_unchanged":total_old-len(old_work),
            "new_clause_reviews":len(new_work),"requests_uncached":requests,
            "estimated_input_tokens":in_tokens,"estimated_output_tokens":req_tokens,
            "estimated_cost_usd_low":round(low,3),"estimated_cost_usd_high":round(high,3),
            "estimated_runtime_minutes":[round(requests*0.15,1),round(requests*0.5,1)]}


def _prompt_track_a(batch: list[dict],regulation: str,old_version: str,new_version: str) -> str:
    packed=[]
    for x in batch:
        packed.append({"requirement":x["requirement"],"old_source_clause":x["old_clause"],"candidate_new_clauses":x["new_matches"],
                       "old_obligation_evidence":x["old_obligation_evidence"],"obligation_comparisons":x["obligation_comparisons"],
                       "old_referenced_clauses":x["old_referenced_clauses"],"new_referenced_clauses":x["new_referenced_clauses"]})
    return f"""Assess EVERY listed old requirement against {regulation} {old_version} -> {new_version}. These are exhaustive assigned items, not a candidate sample. Return exactly one review per ID.
Decide unchanged / modified / removed based on engineering obligation meaning. Follow relocated and renumbered clauses using text matches. Check referenced clauses included in context. A title change, paragraph number change, or placing unchanged operative wording under a new heading is NOT by itself a modification. Do not add a heading-based restriction to old requirement text if its operative obligation is substantively the same. A new separate situation/obligation belongs in Track B unless it changes this ID's old obligation. Modified new_text must be concise, faithful, a single obligation, and <=2000 characters. For modified, cite new-version page and paragraph that state it. Removed has no source citation. reason is required for all decisions; unchanged reason is for the audit only. Never invent facts or cite an unshown location.
Return structured JSON reviews for every provided requirement_id, including unchanged ones.
Review the focused obligation_comparisons before deciding. They contain source excerpts and exact word edits; they are retrieval candidates, so first verify which old/new pair corresponds to this requirement. The original obligation may appear in a neighboring parsed block, such as a table block, rather than the block named by its citation. Use the recovered evidence with its surrounding context and inspect the referenced tables provided.
For every relevant insertion, deletion or replacement, distinguish formatting/renumbering from changed qualifiers, target selection, scope, exceptions, constraints or references. A single changed modifier can require revising a requirement even when the main action and numeric values remain the same. Do not silently drop such edits when summarizing. If a qualifier changes which target, condition or procedure applies, report modified and preserve it in new_text. If you conclude unchanged despite a wording difference, reason must explicitly identify that difference and explain why it requires no change to the engineering requirement. Do not assume every word edit is substantive, and do not invent a constraint unsupported by the source.
{json.dumps(packed,ensure_ascii=False,separators=(',',':'))}"""


def _prompt_track_b(batch: list[dict],regulation: str,old_version: str,new_version: str) -> str:
    packed=[{"new_clause":x["clause"],"paragraph_existed_before":x["paragraph_existed_before"],
             "candidate_old_clauses":x["old_matches"]} for x in batch]
    return f"""Extract atomic engineering, system, manufacturer, test-target, test-procedure, and compliance obligations from EVERY listed new-version clause in {regulation} {new_version}. For each clause, return one clause result, even if obligations is empty. Split distinct obligations into separate items. Preserve each obligation's conditions, values, units and exceptions.
First inventory the clause's independently executable steps, independently testable operating cases, and distinct mandatory actions or permissions in coverage. Each source_unit must identify the source wording/list marker and its scope. Map each included unit to its own zero-based obligation_index in obligations; use null and a specific exclusion_reason only for non-obligation material. Existing obligations must still be extracted and mapped, not excluded. Do not inventory a heading, a shared condition, or each word joined by 'and' as separate obligations.
ATOMIZATION RULES: Different independently executable procedure steps require separate entries, even when they share a heading or introductory sentence. Different operating cases with independently testable constraints require separate entries; repeat the shared actor, scope, limits, exceptions and safety conditions in each so it stands alone. A mandatory action and a separate permission require separate entries even within one sentence. Keep alternative ways to satisfy ONE obligation and its applicability conditions together. Do not mechanically split conjunctions, definitions, or lists of conditions. Do not bundle independent steps into a range citation or a semicolon-separated summary. Before returning, verify every inventoried obligation has its own entry and no entry combines multiple independent units. coverage is an extraction completeness check, not a second novelty decision.
Compare each new obligation against candidate old-version clauses AND their parent_context. Retrieval similarity is not evidence of equivalence. Compare actor, action, object, applicability conditions and test/procedure scope. Repeated wording under a separately introduced procedure or applicability context is a NEW scoped obligation, even if the same action was required elsewhere before. Do not merge it into, or discard it because of, a requirement from another paragraph. Include the distinguishing procedure or applicability in the emitted text.
When paragraph_existed_before is false, classify an obligation as existing or modified_existing only with positive evidence that it is a relocation/renumbering or replacement of the SAME scoped obligation. Cite the candidate old clause ID in old_match and explain the matching scope and continuity in reason; saying 'same wording' or 'same step' is insufficient. A new paragraph number alone does not prove novelty. Where the action repeats but the new context creates a separately applicable obligation, label new. If context is insufficient to establish equivalence, retain the candidate as new and explain the uncertainty rather than suppressing it on lexical similarity.
Label existing for the same scoped obligation without substantive change, modified_existing for a changed replacement of that same scoped obligation (Track A handles ID assignment), and new for a separate obligation. Do not emit background or headings as obligations. A legal or transitional provision is not automatically irrelevant: include it if it imposes a new applicable compliance obligation, and exclude it if it does not create a new engineering/product requirement. A new sentence inside an old clause can still be a new obligation. Do not combine separate independently testable or design obligations. Each item needs exact new PDF page and paragraph from the supplied clause, not its parent_context; preserve its wording in concise one-obligation text, <=2000 characters. Cite pages present in the clause's pages array. Return every clause_id exactly once.
{json.dumps(packed,ensure_ascii=False,separators=(',',':'))}"""


def _api_schema(schema: dict) -> dict:
    """Send structural constraints to Claude; enforce value limits locally."""
    local_only = {
        "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
        "minLength", "maxLength", "pattern", "format",
        "minItems", "maxItems", "uniqueItems",
    }
    result = {key: value for key, value in schema.items() if key not in local_only}
    limits = {key: value for key, value in schema.items() if key in local_only}
    if limits:
        result["description"] = (
            schema.get("description", "") + " Output must satisfy: " + json.dumps(limits)
        ).strip()
    for keyword in ("properties", "$defs", "definitions"):
        if keyword in result:
            result[keyword] = {name: _api_schema(child) for name, child in result[keyword].items()}
    if isinstance(result.get("items"), dict):
        result["items"] = _api_schema(result["items"])
    for keyword in ("anyOf", "oneOf", "allOf"):
        if keyword in result:
            result[keyword] = [_api_schema(child) for child in result[keyword]]
    return result


def _validate_atomic_coverage(response: dict) -> None:
    """Require a separate output entry for every inventoried independent unit."""
    for clause in response.get("clauses", []):
        mapped = []
        units = set()
        for unit in clause["coverage"]:
            label = _norm(unit["source_unit"])
            if not label or label in units:
                raise ValueError(f"{clause['clause_id']}: coverage units must be distinct and nonempty")
            units.add(label)
            index = unit["obligation_index"]
            if index is None:
                if not (unit["exclusion_reason"] or "").strip():
                    raise ValueError(f"{clause['clause_id']}: excluded unit needs an explanation")
                continue
            if unit["exclusion_reason"] is not None or not 0 <= index < len(clause["obligations"]):
                raise ValueError(f"{clause['clause_id']}: invalid coverage index or exclusion reason")
            mapped.append(index)
        if len(mapped) != len(set(mapped)):
            raise ValueError(f"{clause['clause_id']}: independent coverage units share an obligation; split them into separate entries with shared conditions repeated")
        if set(mapped) != set(range(len(clause["obligations"]))):
            raise ValueError(f"{clause['clause_id']}: every obligation needs exactly one coverage unit")


def _call_cached(prompt: str,schema: dict,model: str,cache_dir: Path,usage: dict,usage_log: Path,phase: str,
                 id_field: str,expected_ids: set[str]) -> dict:
    from jsonschema import Draft202012Validator
    from retrieval import llm
    validator = Draft202012Validator(schema)
    api_schema = _api_schema(schema)
    key=hashlib.sha256((model+"\n"+prompt+"\n"+json.dumps(schema,sort_keys=True)).encode()).hexdigest()
    path=cache_dir/f"{phase}-{key}.json"
    if path.is_file():
        cached=json.loads(path.read_text(encoding="utf-8"))
        if validator.is_valid(cached) and _ids_match(cached,id_field,expected_ids):
            try:
                _validate_atomic_coverage(cached)
                return cached
            except ValueError:
                pass
        path.unlink()
    last=None
    request_prompt=prompt
    for attempt in range(3):
        try:
            response=llm.structured(request_prompt,api_schema,model=model,effort="medium",max_tokens=12000)
            errors=list(validator.iter_errors(response))
            if errors:raise ValueError("; ".join(e.message for e in errors[:4]))
            if not _ids_match(response,id_field,expected_ids):raise ValueError(f"Response must contain exactly one result for every assigned {id_field}")
            _validate_atomic_coverage(response)
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(response,ensure_ascii=False),encoding="utf-8")
            return response
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if isinstance(status, int) and 400 <= status < 500 and status not in (408, 409, 429):
                raise RuntimeError(f"{phase} request rejected (HTTP {status}); not retrying: {exc}") from exc
            last=exc
            if isinstance(exc, ValueError):
                request_prompt=prompt+"\nYour previous response failed local validation. Correct these errors in the complete response:\n"+str(exc)[:3000]
            if attempt<2:time.sleep(2**(attempt+1))
    raise RuntimeError(f"{phase} batch failed after retries: {last}") from last


def _ids_match(response: dict,field: str,expected: set[str]) -> bool:
    rows=response.get("reviews" if field=="requirement_id" else "clauses",[])
    ids=[row.get(field) for row in rows]
    return set(ids)==expected and len(ids)==len(expected)


def _load_completed_reviews(directory: Path, schema: dict, collection: str,
                            id_field: str, expected: list[str], ignored_ids: set[str] | None = None) -> list[dict]:
    """Recover complete, unambiguous saved responses without generating anything."""
    from jsonschema import Draft202012Validator
    validator = Draft202012Validator(schema)
    rows = {}
    for path in sorted(directory.glob("*.json")):
        response = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(response)
        _validate_atomic_coverage(response)
        for row in response[collection]:
            ident = row[id_field]
            if ident in (ignored_ids or set()):
                continue
            if ident in rows and rows[ident] != row:
                raise ValueError(f"Conflicting cached reviews for {ident}; assembly-only cannot choose between runs")
            rows[ident] = row
    missing = set(expected) - set(rows)
    extra = set(rows) - set(expected)
    if missing or extra:
        raise ValueError(f"Incomplete or incompatible {collection} cache: missing={sorted(missing)}, extra={sorted(extra)}. No API calls were made.")
    return [rows[ident] for ident in expected]


def _resolve_citation(page: int, paragraph: str | None, clauses: list[dict]) -> dict:
    """Validate a page and optionally map a supported list-item citation to its parent clause."""
    candidates = [c for c in clauses if page in (c.get("pages") or [])]
    cited = _label(paragraph)
    for clause in candidates:
        if _label(clause.get("paragraph")) == cited:
            return {"page": page, **({"paragraph": clause["paragraph"]} if clause.get("paragraph") else {})}
    # Printed annex paragraphs often omit their enclosing annex/appendix labels.
    # Restore the qualified label only when the source and page identify it uniquely.
    if re.match(r"^\d", cited):
        scoped = []
        for clause in candidates:
            qualified = str(clause.get("paragraph") or "")
            if "/" not in qualified:
                continue
            local = qualified.rsplit("/", 1)[-1].strip()
            # Reuse the same suffix checks for annex list items, ranges and tables.
            # The local alias contains no slash, so this cannot recurse again.
            try:
                _resolve_citation(page, paragraph, [{**clause, "paragraph": local}])
            except ValueError:
                continue
            scoped.append(clause)
        if len(scoped) == 1:
            return {"page": page, "paragraph": scoped[0]["paragraph"]}
        if len(scoped) > 1:
            raise ValueError(f"Ambiguous unqualified annex citation {paragraph!r} on page {page}")
    for clause in sorted(candidates, key=lambda c: len(_label(c.get("paragraph"))), reverse=True):
        parent = _label(clause.get("paragraph"))
        if not parent or not cited.startswith(parent):
            continue
        suffix = cited[len(parent):].strip()
        table_item = re.fullmatch(
            r"\.?\s*table\s+(\d+)\s*(?:[,;:]\s*)?(?:item|row)\s+(\d+(?:\.[a-z])?)\.?",
            suffix,
        )
        if table_item:
            table_number, item = table_item.groups()
            text = clause.get("text", "").casefold()
            table_heading = re.search(r"\btable\s+" + re.escape(table_number) + r"\b", text)
            # A number in prose is not evidence of a numbered table row.
            row = re.search(r"(?m)^\s*" + re.escape(item) + r"\.\s+\S", text)
            if table_heading and row and row.start() > table_heading.start():
                return {"page": page, "paragraph": clause["paragraph"]}
            continue
        item_range = re.fullmatch(
            r"\.?\s*\(\s*([a-z]|[0-9]+)\s*\)\s*(?:[-–—]|to)\s*\(\s*([a-z]|[0-9]+)\s*\)",
            suffix,
        )
        if item_range:
            first, last = item_range.groups()
            if first.isdigit() != last.isdigit():
                continue
            start, end = (int(first), int(last)) if first.isdigit() else (ord(first), ord(last))
            # Bound expansion and verify every item, not just range endpoints.
            if end < start or end - start > 100:
                continue
            labels = [str(i) if first.isdigit() else chr(i) for i in range(start, end + 1)]
            text = clause.get("text", "").casefold()
            positions = [re.search(r"\(\s*" + re.escape(label) + r"\s*\)", text) for label in labels]
            if all(match is not None for match in positions):
                offsets = [match.start() for match in positions]
                if offsets == sorted(offsets):
                    return {"page": page, "paragraph": clause["paragraph"]}
            continue
        if not re.fullmatch(r"\.?\s*(?:\([a-z0-9]+\)\s*)+", suffix):
            continue
        markers = re.findall(r"\([a-z0-9]+\)", suffix)
        text = clause.get("text", "").casefold()
        if all(marker in text for marker in markers):
            return {"page": page, "paragraph": clause["paragraph"]}
    raise ValueError(f"Citation {paragraph!r} on page {page} does not match a source clause or a supported list item")


def run_exhaustive(requirements: list[dict],old_doc: dict,new_doc: dict,regulation: str,old_version: str,new_version: str,
                   model: str,cache_dir: Path,output_dir: Path,team_id: str,case_id: str,
                   old_batch=10,new_batch=6,assemble_only=False,prepared_work=None) -> tuple[dict,dict]:
    from retrieval import llm
    from threading import Lock
    old_work,new_work,align=prepared_work if prepared_work is not None else build_work(requirements,old_doc,new_doc)
    plan=estimate(old_work,new_work,old_batch,new_batch)
    automatic = [x for x in old_work if x["unchanged_gate"]["automatic_unchanged"]]
    automatic_ids = {x["requirement"]["id"] for x in automatic}
    model_work = [x for x in old_work if x["requirement"]["id"] not in automatic_ids]
    automatic_results = [{"requirement_id":x["requirement"]["id"],"decision":"unchanged",
                          "new_text":None,"reason":x["unchanged_gate"]["reason"],
                          "source_page":None,"source_paragraph":None} for x in automatic]
    old_prompts=[_prompt_track_a(b,regulation,old_version,new_version) for b in _chunks(model_work,old_batch)]
    new_prompts=[_prompt_track_b(b,regulation,old_version,new_version) for b in _chunks(new_work,new_batch)]
    old_cache=cache_dir/"track-a";new_cache=cache_dir/"track-b"
    old_results=[];new_results=[];usage={k:0 for k in PRICE};calls=0;lock=Lock();log_path=output_dir/f"usage-exhaustive-{case_id}.jsonl"
    log_path.parent.mkdir(parents=True,exist_ok=True)
    def on_usage(v):
        nonlocal calls
        with lock:
            calls+=1
            for key in usage:usage[key]+=int(v.get(key,0) or 0)
            usd=sum(usage[k]*PRICE[k] for k in PRICE)/1e6
            with log_path.open("a",encoding="utf-8") as f:f.write(json.dumps({"model":v.get("model",model),"phase":"exhaustive","call":calls,**v,"cumulative_estimated_usd":round(usd,6)})+"\n")
            print(f"[API {calls}] {v.get('model',model)} | input {v.get('input_tokens',0):,}, output {v.get('output_tokens',0):,} | spend ${usd:.4f}",flush=True)
    started=time.monotonic()
    if assemble_only:
        old_results = _load_completed_reviews(old_cache, OLD_SCHEMA, "reviews", "requirement_id",
                                              [x["requirement"]["id"] for x in model_work], ignored_ids=automatic_ids)
        new_results = _load_completed_reviews(new_cache, NEW_SCHEMA, "clauses", "clause_id",
                                              [x["clause"]["id"] for x in new_work])
        print(f"Assembly only: loaded {len(old_results)} requirement reviews and {len(new_results)} clause reviews; no API calls.", flush=True)
    else:
        llm.USAGE_CALLBACK=on_usage
        try:
            for batch,prompt in zip(_chunks(model_work,old_batch),old_prompts):
                expected={x["requirement"]["id"] for x in batch}
                result=_call_cached(prompt,OLD_SCHEMA,model,old_cache,usage,log_path,"existing","requirement_id",expected)
                old_results.extend(result["reviews"])
            for batch,prompt in zip(_chunks(new_work,new_batch),new_prompts):
                expected={x["clause"]["id"] for x in batch}
                result=_call_cached(prompt,NEW_SCHEMA,model,new_cache,usage,log_path,"newclauses","clause_id",expected)
                new_results.extend(result["clauses"])
        finally:llm.USAGE_CALLBACK=None

    old_results.extend(automatic_results)
    result_by_id = {row["requirement_id"]:row for row in old_results}
    if len(old_results)!=len(old_work) or set(result_by_id)!={x["requirement"]["id"] for x in old_work}:
        raise ValueError("Combined automatic and model reviews do not cover every existing requirement exactly once")
    old_results = [result_by_id[x["requirement"]["id"]] for x in old_work]

    by_id={x["requirement"]["id"]:x["requirement"] for x in old_work}
    old_output=[]
    citation_normalizations=[]
    for row in old_results:
        if row["decision"]=="unchanged":continue
        kind=row["decision"];entry={"requirement_id":row["requirement_id"],"change":kind,"reason":row["reason"]}
        if kind=="modified":
            if not row.get("new_text") or not row.get("source_page") or not row.get("source_paragraph"):
                raise ValueError(f"Modified {row['requirement_id']} is missing new text/citation")
            if len(row["new_text"])>2000:
                raise ValueError(f"Modified {row['requirement_id']} new_text exceeds the official 2000-character limit")
            entry["new_text"]=row["new_text"]
            entry["source"]=_resolve_citation(row["source_page"],row["source_paragraph"],new_doc["clauses"])
            if entry["source"].get("paragraph")!=row["source_paragraph"]:
                citation_normalizations.append({"requirement_id":row["requirement_id"],"original_paragraph":row["source_paragraph"],"source":entry["source"]})
        old_output.append(entry)

    new_clause_by_id={x["clause"]["id"]:x["clause"] for x in new_work}
    added=[]
    for result in new_results:
        clause=new_clause_by_id[result["clause_id"]]
        for obligation in result["obligations"]:
            if obligation["novelty"]!="new":continue
            source=_resolve_citation(obligation["page"],obligation.get("paragraph"),[clause])
            if source.get("paragraph")!=obligation.get("paragraph"):
                citation_normalizations.append({"clause_id":clause["id"],"original_paragraph":obligation.get("paragraph"),"source":source})
            if len(obligation["text"])>2000:raise ValueError(f"Track B text for {clause['id']} exceeds the 2000-character limit")
            added.append({"requirement_id":None,"change":"added","new_text":obligation["text"],"reason":obligation["reason"],
                          "source":source})
    # Exact-normalized deduplication avoids merging similar but distinct test/design obligations.
    dedup=[];seen=set()
    for item in added:
        key=(_norm(item["new_text"]),item["source"].get("paragraph"),item["source"].get("page"))
        if key and key not in seen:seen.add(key);dedup.append(item)
    submission={"team_id":team_id,"case_id":case_id,"changes":old_output+dedup}
    audit={"plan":plan,"alignment":align,"assembly_only":assemble_only,"automatic_unchanged_requirement_ids":sorted(automatic_ids),"citation_normalizations":citation_normalizations,"existing_requirement_decisions":old_results,
           "new_clause_obligations":new_results,"usage":{"api_calls_uncached":calls,"tokens":usage,
           "estimated_api_cost_usd":round(sum(usage[k]*PRICE[k] for k in PRICE)/1e6,6),
           "elapsed_seconds":round(time.monotonic()-started,2)},"counts":{"modified":sum(r["decision"]=="modified" for r in old_results),
           "removed":sum(r["decision"]=="removed" for r in old_results),"unchanged":sum(r["decision"]=="unchanged" for r in old_results),
           "new_obligations_extracted":sum(len(c["obligations"]) for c in new_results),"added_submitted":len(dedup)}}
    return submission,audit
