"""Stage 0 — Load: read spec.md and/or image; read parsed regulations and index.json;
deterministically repair Annex/Part/Table/Sub-clause labels; build an in-memory index of clauses.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = EXP_DIR.parents[2]
CLAUSE_DIR = REPO_ROOT / "data-ingestion" / "clauses"

sys.path.insert(0, str(REPO_ROOT / "approaches" / "benchmarking"))
from challenge_tools.score_local import _paragraph_key  # noqa: E402

ANNEX_HDR = re.compile(r"^Annex\s+(\d+[A-Z]?)[ :\-]+([A-Z].*)$")
PART_HDR = re.compile(r"^(Appendix|Part)\s+([A-Z]|[IVX]+|\d+)[ :\-]+([A-Z].*)$")
NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)*)(\.)?\s+(\S.*)$")
CAPTION_RE = re.compile(r"^(Table|Figure)\s+([A-Za-z0-9]+(?:[-\u2013][A-Za-z0-9]+)*)(?:\s|:).*$")
COMBINES_RE = re.compile(
    r"provisions of (?:the )?individual UN Regulations Nos?\.?\s*([\d,\sand]+)",
    re.IGNORECASE,
)
CATEGORY_RE = re.compile(r"\b([LMNO])([1-7])?(?=\d?\b)")


def format_paragraph_citation(
    annex: str | None,
    part: str | None,
    appendix: str | None,
    label: str | None,
) -> str | None:
    """Format a clean official paragraph string without slash separators."""
    pieces = [
        f"Annex {annex}" if annex else None,
        f"Part {part}" if part else None,
        f"Appendix {appendix}" if appendix else None,
        label,
    ]
    joined = " ".join(p for p in pieces if p)
    return joined if joined else None


@dataclass
class ClauseNode:
    clause_id: str                # e.g. "UN_R150_base:12"
    vector_row: int               # 0..26768 matching gemini-embedding-2-preview_d768_n26769.npz
    regulation: str               # e.g. "UN R150"
    version: str                  # base version_label, e.g. "1.2.1"
    role: str                     # "base"
    raw_paragraph: str | None     # original paragraph string from clauses/*.json
    paragraph: str | None         # repaired official paragraph citation
    norm_paragraph: str | None    # _paragraph_key(paragraph)
    pages: list[int]              # 1-based PDF pages
    page: int                     # primary (first) 1-based PDF page
    text: str
    annex: str | None = None
    part: str | None = None
    appendix: str | None = None
    parent_heading: str = ""
    sub_paragraphs: dict[str, str] = field(default_factory=dict)  # norm_key -> official paragraph string
    sub_paragraph_texts: dict[str, str] = field(default_factory=dict)  # norm_key -> verbatim sub-clause text
    review_flags: list[str] = field(default_factory=list)


@dataclass
class RegulationMeta:
    regulation: str
    title: str
    base_version: str
    scope_text: str
    supersedes: set[str] = field(default_factory=set)
    categories: set[tuple[str, str]] = field(default_factory=set)
    clauses: list[ClauseNode] = field(default_factory=list)


@dataclass
class LoadedCorpus:
    case_id: str
    case_dir: Path
    spec_text: str
    image_path: Path | None
    index_raw: list[dict]
    regulations: dict[str, RegulationMeta]
    all_clauses: list[ClauseNode]
    by_clause_id: dict[str, ClauseNode]
    by_reg_norm_para: dict[tuple[str, str], list[ClauseNode]]
    sub_para_to_clause: dict[tuple[str, str], tuple[ClauseNode, str]]  # (reg, norm_key) -> (ClauseNode, official_para)


def resolve_index_path(explicit_path: Path | None = None) -> Path:
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    candidates.extend([
        REPO_ROOT.parent / "industrial-ai-hackathon" / "regulations" / "index.json",
        EXP_DIR / ".cache" / "regulations" / "index.json",
    ])
    for p in candidates:
        try:
            if p.is_file():
                p.read_bytes()
                return p
        except (PermissionError, OSError):
            continue
    raise FileNotFoundError("Could not locate readable regulations/index.json")


def resolve_case_dir(case_arg: str | Path) -> Path:
    p = Path(case_arg)
    candidates = [
        p,
        REPO_ROOT / case_arg,
        REPO_ROOT / "approaches" / "benchmarking" / "cases" / p.name,
        EXP_DIR / ".cache" / "cases" / p.name,
        REPO_ROOT.parent / "industrial-ai-hackathon" / "cases" / p.name,
    ]
    for c in candidates:
        try:
            if c.is_dir() and (c / "spec.md").is_file():
                (c / "spec.md").read_bytes()
                return c
        except (PermissionError, OSError):
            continue
    raise FileNotFoundError(f"Could not locate readable case directory for {case_arg!r}")


def load_stage0(case_arg: str | Path, index_arg: Path | None = None) -> LoadedCorpus:
    """Execute Stage 0: load case spec/image, index.json, and all 56 regulations with deterministic repairs."""
    case_dir = resolve_case_dir(case_arg)
    case_id = case_dir.name
    spec_text = (case_dir / "spec.md").read_text(encoding="utf-8")
    img_candidate = case_dir / "exploded_view.png"
    image_path = img_candidate if img_candidate.is_file() else None

    index_path = resolve_index_path(index_arg)
    index_raw = json.loads(index_path.read_text(encoding="utf-8"))
    index_by_reg = {}
    for entry in index_raw:
        reg = entry["regulation"]
        base_ver = next((v["version_label"] for v in entry.get("versions", []) if v.get("role") == "base"), "")
        index_by_reg[reg] = {"title": entry.get("title", ""), "base_version": base_ver}

    regulations: dict[str, RegulationMeta] = {}
    all_clauses: list[ClauseNode] = []
    by_clause_id: dict[str, ClauseNode] = {}
    by_reg_norm_para: dict[tuple[str, str], list[ClauseNode]] = {}
    sub_para_to_clause: dict[tuple[str, str], tuple[ClauseNode, str]] = {}

    vector_row = 0
    for cf in sorted(CLAUSE_DIR.glob("*.json")):
        doc = json.loads(cf.read_text(encoding="utf-8"))
        reg = doc["regulation"]
        ver = doc["version"]
        idx_meta = index_by_reg.get(reg, {"title": "", "base_version": ver})
        base_ver = idx_meta["base_version"] or ver

        true_annex: str | None = None
        true_part: str | None = None
        true_app: str | None = None
        last_clause_num: str | None = None
        last_block_num: str | None = None
        current_section_heading: str = ""

        reg_clauses: list[ClauseNode] = []
        for idx, c in enumerate(doc["clauses"]):
            cid = f"{cf.stem}:{idx}"
            raw_para = c.get("paragraph")
            pages = c.get("pages", [1])
            first_page = pages[0] if pages else 1
            text = c.get("text", "")
            flags = c.get("review_flags", [])

            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            local_label: str | None = None
            if raw_para:
                # Extract leaf label after the last '/'
                local_label = raw_para.split("/")[-1].strip()
                if local_label.startswith(("Annex ", "Part ", "Appendix ")):
                    local_label = None
                elif re.fullmatch(r"\d+(?:\.\d+)*", local_label):
                    last_block_num = local_label

            sub_paras: dict[str, str] = {}
            sub_para_lines: dict[str, list[str]] = {}
            active_sub_key: str | None = None

            for line_idx, ln in enumerate(lines):
                # 1. Check for true Annex heading (must not be a tabular row with 3+ consecutive spaces)
                m_ann = ANNEX_HDR.fullmatch(ln)
                if m_ann and not re.search(r"\S\s{3,}\S", ln):
                    num = int(re.match(r"\d+", m_ann.group(1)).group(0))
                    prev_num = int(re.match(r"\d+", true_annex).group(0)) if true_annex else 0
                    if num > prev_num or (num == prev_num and m_ann.group(1) != true_annex):
                        true_annex = m_ann.group(1)
                        true_part = None
                        true_app = None
                        last_clause_num = None
                        last_block_num = None
                        active_sub_key = None
                        current_section_heading = ln[:160]
                        if line_idx == 0:
                            local_label = None
                        continue

                # 2. Check for true Part / Appendix heading
                m_part = PART_HDR.fullmatch(ln)
                if (
                    m_part
                    and not re.search(r"\S\s{3,}\S", ln)
                    and not re.search(r"\b(shall|must|according|referred)\b", ln, re.IGNORECASE)
                ):
                    if m_part.group(1) == "Part":
                        true_part, true_app = m_part.group(2), None
                    else:
                        true_app = m_part.group(2)
                    last_clause_num = None
                    last_block_num = None
                    active_sub_key = None
                    current_section_heading = ln[:160]
                    if line_idx == 0:
                        local_label = None
                    continue

                # 3. Check for Table / Figure caption
                m_cap = CAPTION_RE.fullmatch(ln)
                if m_cap:
                    cap_label = f"{m_cap.group(1)} {m_cap.group(2)}"
                    enclosing_num = last_block_num or last_clause_num
                    if line_idx == 0:
                        if enclosing_num and m_cap.group(1) == "Table":
                            # Attach Table to enclosing block paragraph: e.g. "5.1.4.4.1. Table 3" or "Annex 6 Part 6 3. Table A6-1"
                            local_label = f"{enclosing_num}. {cap_label}"
                        else:
                            local_label = cap_label
                    # Map all candidate forms (including bare "Table 3") to the full attached label (`local_label`)
                    canonical_cap = format_paragraph_citation(true_annex, true_part, true_app, local_label or cap_label)
                    for cand_lbl in filter(
                        None,
                        [
                            cap_label,
                            f"{last_block_num}. {cap_label}" if last_block_num else None,
                            f"{last_clause_num}. {cap_label}" if last_clause_num else None,
                        ],
                    ):
                        full_cand = format_paragraph_citation(true_annex, true_part, true_app, cand_lbl)
                        if full_cand and (nk := _paragraph_key(full_cand)):
                            sub_paras[nk] = canonical_cap or full_cand
                        if nk_bare := _paragraph_key(cand_lbl):
                            sub_paras[nk_bare] = canonical_cap or full_cand
                    active_sub_key = _paragraph_key(canonical_cap) if canonical_cap else None
                    if active_sub_key:
                        sub_para_lines.setdefault(active_sub_key, []).append(ln)
                    continue

                # 4. Check for numbered sub-clauses inside the block (including line 0)
                # Do NOT treat table row numbers inside a Table/Figure block as numbered sub-clauses!
                if local_label and ("Table " in local_label or "Figure " in local_label):
                    if active_sub_key is not None:
                        sub_para_lines.setdefault(active_sub_key, []).append(ln)
                    continue
                m_num = NUMBER_RE.fullmatch(ln)
                if m_num:
                    lbl = m_num.group(1)
                    body = m_num.group(3)
                    # Reject obvious measurement units like "12 V" or "0.5 mm"
                    if not re.match(r"^(mm|cm|m|V|W|cd|lx|%|°|kg|s|Hz|nm|km/h|dB)\b", body):
                        if line_idx == 0 and local_label is None:
                            local_label = lbl
                        if line_idx == 0:
                            last_block_num = lbl
                        last_clause_num = lbl
                        if "." not in lbl and len(ln) < 120:
                            current_section_heading = ln[:120]
                        full_sub = format_paragraph_citation(true_annex, true_part, true_app, lbl)
                        if full_sub and (nk := _paragraph_key(full_sub)):
                            sub_paras[nk] = full_sub
                            active_sub_key = nk
                            sub_para_lines.setdefault(nk, []).append(ln)
                        continue

                if active_sub_key is not None:
                    sub_para_lines.setdefault(active_sub_key, []).append(ln)

            repaired_para = format_paragraph_citation(true_annex, true_part, true_app, local_label)
            if repaired_para is None and raw_para is not None:
                repaired_para = raw_para.replace(" / ", " ")

            norm_para = _paragraph_key(repaired_para) if repaired_para else None
            if repaired_para and norm_para:
                sub_paras[norm_para] = repaired_para
            if raw_para and (raw_nk := _paragraph_key(raw_para)):
                sub_paras.setdefault(raw_nk, repaired_para or raw_para.replace(" / ", " "))

            clean_full_text = " ".join(text.split())
            sub_para_texts: dict[str, str] = {}
            for nk in sub_paras:
                if nk == norm_para or len(sub_paras) <= 2:
                    sub_para_texts[nk] = clean_full_text
                elif nk in sub_para_lines and sub_para_lines[nk]:
                    sub_para_texts[nk] = " ".join(" ".join(sub_para_lines[nk]).split())
                else:
                    sub_para_texts[nk] = clean_full_text

            node = ClauseNode(
                clause_id=cid,
                vector_row=vector_row,
                regulation=reg,
                version=base_ver,
                role="base",
                raw_paragraph=raw_para,
                paragraph=repaired_para,
                norm_paragraph=norm_para,
                pages=pages,
                page=first_page,
                text=text,
                annex=true_annex,
                part=true_part,
                appendix=true_app,
                parent_heading=current_section_heading,
                sub_paragraphs=sub_paras,
                sub_paragraph_texts=sub_para_texts,
                review_flags=flags,
            )
            vector_row += 1
            reg_clauses.append(node)
            all_clauses.append(node)
            by_clause_id[cid] = node

            if norm_para:
                by_reg_norm_para.setdefault((reg, norm_para), []).append(node)
            for nk, official_str in sub_paras.items():
                sub_para_to_clause.setdefault((reg, nk), (node, official_str))

        # Extract scope text, supersession, and vehicle categories for RegulationMeta
        scope_parts = [
            c.text
            for c in reg_clauses
            if c.annex is None and c.paragraph and re.fullmatch(r"1(\.\d+)*", c.paragraph)
        ]
        scope_text = " ".join(" ".join(scope_parts).split())[:2000]
        intro_text = " ".join(c.text for c in reg_clauses[:3] if c.raw_paragraph is None)
        supersedes: set[str] = set()
        if m_comb := COMBINES_RE.search(intro_text.replace("\r\n", " ")):
            supersedes = {f"UN R{n}" for n in re.findall(r"\d+", m_comb.group(1))} & set(index_by_reg.keys())

        categories = {
            (a, b or "")
            for a, b in CATEGORY_RE.findall(scope_text[:800])
            if "categor" in scope_text[:800].lower()
        }

        regulations[reg] = RegulationMeta(
            regulation=reg,
            title=idx_meta["title"],
            base_version=base_ver,
            scope_text=scope_text,
            supersedes=supersedes,
            categories=categories,
            clauses=reg_clauses,
        )

    return LoadedCorpus(
        case_id=case_id,
        case_dir=case_dir,
        spec_text=spec_text,
        image_path=image_path,
        index_raw=index_raw,
        regulations=regulations,
        all_clauses=all_clauses,
        by_clause_id=by_clause_id,
        by_reg_norm_para=by_reg_norm_para,
        sub_para_to_clause=sub_para_to_clause,
    )
