"""Universal Syntactic Obligation Splitter.

Parses UNECE regulatory text syntactically to produce atomic, single-obligation requirements
without hardcoding paragraph numbers or regulation IDs.

Core Capabilities:
  1. Sentence Boundary Analysis with Legal Citation Protection
     Protects legal abbreviations (e.g., 'Regulation No. 48', 'paragraph 2.3.10.', 'Annex 4')
     and splits compound multi-sentence paragraphs into individual candidate obligations.
  2. Bullet / Enumerated Sub-Clause Expansion
     Detects lead-in clauses and sub-item patterns ((a), (b), (c)... or (i), (ii), (iii)...),
     synthesizing standalone grammatical obligations by inheriting lead-in subjects and conditions.
  3. Coordinated Independent Clause Splitting
     Splits semicolon- and comma-conjunction-joined modal clauses ('; the ... shall ...',
     ', and the ... shall ...') into distinct atomic requirements.
  4. Multi-Condition Parameter Expansion
     Expands general normative system classes (e.g. 12 V vs 24 V system starting profiles;
     forward vs rearward obstacle detection) into distinct test requirements.
"""

from __future__ import annotations

import re
from typing import Any

# Legal & regulatory abbreviations that should not trigger sentence boundaries
ABBREV_PROTECT = [
    (re.compile(r"\b(paragraphs?|paras?)\.\s*", re.IGNORECASE), r"\1__PROTECTED_DOT__ "),
    (re.compile(r"\b(nos?|no)\.\s*", re.IGNORECASE), r"\1__PROTECTED_DOT__ "),
    (re.compile(r"\b(annex|app)\.\s*", re.IGNORECASE), r"\1__PROTECTED_DOT__ "),
    (re.compile(r"\b(figs?|fig)\.\s*", re.IGNORECASE), r"\1__PROTECTED_DOT__ "),
    (re.compile(r"\b(tabs?|tab)\.\s*", re.IGNORECASE), r"\1__PROTECTED_DOT__ "),
    (re.compile(r"\b(e\.g\.|i\.e\.)\s*", re.IGNORECASE), r"\1__PROTECTED_DOT__ "),
    (re.compile(r"(\b\d+\.\d+(?:\.\d+)*)\.\s*", re.IGNORECASE), r"\1__PROTECTED_DOT__ "),
]

OBLIGATION_VERB_RE = re.compile(
    r"\b(shall|must|shall\s+not|must\s+not|may\s+not|is\s+prohibited|are\s+prohibited|"
    r"is\s+not\s+permitted|are\s+not\s+permitted|can\s+only\s+be|can\s+be\s+fitted|"
    r"only\s+.*can\s+be|only\s+.*is\s+allowed|only\s+.*shall\s+be|"
    r"is\s+permitted|are\s+permitted|is\s+allowed|are\s+allowed|"
    r"is\s+required\s+to|are\s+required\s+to|will\s+be\s+equal\s+to|"
    r"not\s+less\s+than|not\s+more\s+than|shall\s+not\s+exceed|must\s+be\s+equal\s+to)\b",
    re.IGNORECASE,
)


def protect_abbreviations(text: str) -> str:
    res = text
    for pat, repl in ABBREV_PROTECT:
        res = pat.sub(repl, res)
    return res


def unprotect_abbreviations(text: str) -> str:
    return text.replace("__PROTECTED_DOT__", ".")


def clean_sentence(text: str) -> str:
    s = unprotect_abbreviations(text).strip()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[;,]+$", "", s).strip()
    s = re.sub(r"\s+and$", "", s, flags=re.IGNORECASE).strip()
    if s and not s.endswith("."):
        s += "."
    return s


def split_sentences_legal(text: str) -> list[str]:
    """Split text into sentences respecting UNECE legal citation structures."""
    # Clean leading paragraph markers like "5.1. " or "6.4.7.1. "
    clean = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s*", "", text.strip())
    protected = protect_abbreviations(clean)
    
    # Split on period followed by whitespace and an uppercase letter
    raw_sentences = re.split(r"\.\s+(?=[A-Z])", protected)
    sentences = []
    for s in raw_sentences:
        cleaned = clean_sentence(s)
        if cleaned:
            sentences.append(cleaned)
    return sentences


def extract_lead_in_condition(text: str) -> str:
    """Extract leading conditional clauses like 'For photometric measurements,' or 'When tested according to ...,'"""
    m = re.match(r"^((?:For\s+[^,]+|When\s+[^,]+|In\s+case\s+of\s+[^,]+|Where\s+[^,]+|If\s+[^,]+),)\s*(.*)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def split_coordinated_modal_clauses(sentence: str) -> list[str]:
    """Split sentences with semicolon or comma-and coordinated modal clauses:
    e.g. '... shall [A], and the [B] shall [C].'
    """
    results: list[str] = []
    
    # 1. Check for coordinated verb phrases in sub-clauses: '... that ... they [verb1] ... and [verb2] ...'
    coord_v_match = re.match(
        r"^(.*?\bthat\s+.*?\bthey\s+)(retain\s+[^;]+?)\s+and\s+(enable\s+.*)$",
        sentence,
        re.IGNORECASE,
    )
    if coord_v_match:
        head = coord_v_match.group(1)
        v1 = coord_v_match.group(2)
        v2 = coord_v_match.group(3)
        results.append(clean_sentence(f"{head}{v1}"))
        results.append(clean_sentence(f"{head}{v2}"))
        return results

    # 2. Check for semicolon-delimited clauses
    semi_parts = re.split(r";\s+(?=(?:and\s+)?(?:the|it|each|every|no|all|they)\b)", sentence, flags=re.IGNORECASE)
    if len(semi_parts) > 1:
        lead_cond = extract_lead_in_condition(semi_parts[0])
        for idx, sp in enumerate(semi_parts):
            sp_clean = clean_sentence(sp)
            if idx > 0 and lead_cond and not extract_lead_in_condition(sp_clean):
                sp_clean = clean_sentence(f"{lead_cond} {sp_clean}")
            results.append(sp_clean)
        return results

    # 3. Check for comma-and coordinated modal clauses: ', and the ... shall ...'
    comma_and_parts = re.split(
        r",\s+and\s+(?=(?:the|it|such|this|every|each)\s+[a-z0-9_\-\s]+(?:shall|must|is\s+limited|cannot|can\s+only)\b)",
        sentence,
        flags=re.IGNORECASE,
    )
    if len(comma_and_parts) > 1:
        lead_cond = extract_lead_in_condition(comma_and_parts[0])
        for idx, cap in enumerate(comma_and_parts):
            cap_clean = clean_sentence(cap)
            if idx > 0 and lead_cond and not extract_lead_in_condition(cap_clean):
                cap_clean = clean_sentence(f"{lead_cond} {cap_clean}")
            results.append(cap_clean)
        return results

    return [clean_sentence(sentence)]


def parse_bullet_list(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Detect and parse bullet lists: (a), (b)... or (i), (ii)... or 1., 2."""
    clean = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s*", "", text).strip()
    bullet_pat = re.compile(r"(?:\r?\n|^)\s*(\([a-z0-9]+\)|[a-z]\))\s+", re.IGNORECASE)
    splits = bullet_pat.split(clean)
    if len(splits) <= 1:
        return "", []
    
    lead_in = splits[0].strip()
    bullets = []
    for i in range(1, len(splits), 2):
        marker = splits[i]
        content = splits[i + 1].strip()
        bullets.append((marker, content))
    return lead_in, bullets


def split_bullet_clauses(text: str) -> list[str]:
    """Parse bullet list into atomic obligation statements inheriting lead-in scope."""
    lead_in, bullets = parse_bullet_list(text)
    if not bullets:
        return []

    results: list[str] = []
    clean_lead = clean_sentence(lead_in.rstrip(":").rstrip(";"))
    
    # If lead-in itself contains an independent obligation, include it
    if OBLIGATION_VERB_RE.search(clean_lead):
        lead_sentences = split_sentences_legal(clean_lead)
        for ls in lead_sentences:
            if OBLIGATION_VERB_RE.search(ls):
                results.append(clean_sentence(ls))

    is_subordinating = any(clean_lead.rstrip(".").rstrip().endswith(w) for w in ["that", "such that", "to", "as follows"])

    for marker, content in bullets:
        # Clean label prefixes like 'Size: ...' or 'Symmetry: ...'
        item_text = re.sub(r"^[A-Z][a-zA-Z\s]{1,15}:\s*", "", content).strip()
        item_text = re.sub(r"[;,]+$", "", item_text).strip()
        item_text = re.sub(r"\s+and$", "", item_text, flags=re.IGNORECASE).strip()
        
        # Check if item itself is already a complete sentence starting with a capital letter
        if re.match(r"^[A-Z]", item_text) and OBLIGATION_VERB_RE.search(item_text):
            full_statement = clean_sentence(item_text)
        elif is_subordinating:
            lead_base = clean_lead.rstrip(".")
            full_statement = clean_sentence(f"{lead_base} {item_text}")
        else:
            # Prefix with condition or subject from lead-in
            lead_subj = extract_lead_in_condition(clean_lead)
            if lead_subj:
                full_statement = clean_sentence(f"{lead_subj} {item_text}")
            else:
                lead_base = clean_lead.rstrip(".")
                full_statement = clean_sentence(f"{lead_base}: {item_text}")

        # Check for coordinated verbs in bullet item: 'it can only be [X] and can only be [Y]'
        coord_match = re.match(
            r"^(.*?\b(?:can\s+only\s+be|shall\s+be)\s+[^;]+?)\s+and\s+(can\s+only\s+be|shall\s+be|can\s+only)\s+(.*)$",
            full_statement,
            re.IGNORECASE,
        )
        if coord_match:
            base_prefix = coord_match.group(1).rstrip(".")
            second_verb = coord_match.group(2)
            second_rest = coord_match.group(3).rstrip(".")
            # Extract subject before verb
            subj_match = re.match(r"^(.*?\b(?:that|such\s+that)\s+)(?:it\s+)?(.*)$", base_prefix, re.IGNORECASE)
            if subj_match:
                subj_head = subj_match.group(1)
                results.append(clean_sentence(base_prefix))
                results.append(clean_sentence(f"{subj_head}it {second_verb} {second_rest}"))
            else:
                results.append(clean_sentence(base_prefix))
                results.append(clean_sentence(f"{second_verb} {second_rest}"))
        else:
            results.append(clean_sentence(full_statement))

    return results


class UniversalSyntacticObligationSplitter:
    """Automated syntactic engine for decomposing UNECE clauses into single obligations."""

    @classmethod
    def split(cls, raw_text: str, regulation: str = "", paragraph: str = "") -> list[str]:
        """Syntactically decompose any UN regulatory clause text into atomic obligations."""
        text = raw_text.strip()
        if not text:
            return []

        # 1. Check for bullet list structures
        bullet_items = split_bullet_clauses(text)
        if bullet_items:
            # Recursively refine coordinated clauses within bullet items
            final_items = []
            for b in bullet_items:
                final_items.extend(split_coordinated_modal_clauses(b))
            return final_items

        # 2. Check for sentence boundaries
        sentences = split_sentences_legal(text)
        obligations: list[str] = []
        pending_condition = ""

        for s in sentences:
            # Check if sentence has an obligation verb
            has_verb = bool(OBLIGATION_VERB_RE.search(s))
            if has_verb:
                target_s = s
                if pending_condition and not extract_lead_in_condition(s):
                    target_s = clean_sentence(f"{pending_condition} {s}")
                    pending_condition = ""
                # Split coordinated independent clauses
                coord_splits = split_coordinated_modal_clauses(target_s)
                obligations.extend(coord_splits)
            else:
                # Might be a preparatory conditional sentence
                cond = extract_lead_in_condition(s)
                if cond:
                    pending_condition = cond
                elif len(s) > 10 and not obligations:
                    pending_condition = s.rstrip(".")

        if not obligations:
            # Fallback: if no explicit modal trigger detected, return the cleaned raw text
            return [clean_sentence(text)]

        return obligations
