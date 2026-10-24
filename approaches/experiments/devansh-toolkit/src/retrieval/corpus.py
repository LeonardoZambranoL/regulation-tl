"""Turn the regulations into citeable chunks: either the team's parsed clauses (data-ingestion/clauses) or the PDFs.

Every chunk knows the regulation, version, page and paragraph it came from, so whatever a
retriever returns can be cited directly in a submission (`source.regulation / version / page / paragraph`).

Two granularities:
  * "page"      - one chunk per PDF page (coarse, high recall per hit, what the page-level score counts)
  * "paragraph" - one chunk per numbered paragraph per page ("5.4.2.", "Annex 6 Part 4 3"), split at page breaks
"""

from __future__ import annotations

import hashlib
import json
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

APPROACH_DIR = Path(__file__).resolve().parents[2]  # approaches/experiments/devansh-toolkit
# the repo root holds the shared data (regulations/, data-ingestion/), wherever this approach folder sits
REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "regulations").is_dir())
PDF_DIR = REPO_ROOT / "regulations"
CLAUSE_DIR = REPO_ROOT / "data-ingestion" / "clauses"
CACHE_DIR = APPROACH_DIR / ".cache"
DEFAULT_CHALLENGE_DIR = REPO_ROOT.parent / "industrial-ai-hackathon"

_HEADER = re.compile(r"^UN [^|]+, version [\d.]+ \| page \d+ of \d+\s*$")
# "5.4.2.3. Text", "6.1 Text", "10. Text" - a number at line start followed by text or end of line
_PARA = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){0,6})\.?(?:\s+|$)(.*)$")
# "Annex 4 Photometric and colorimetric measurements" is a heading; "Annex 6." / "Annex 10 (values in" are wrapped references
_ANNEX = re.compile(r"^Annex\s+(\d+[A-Z]?)\s*[-–:]?\s+([A-Z][A-Za-z].*)$")
_PART = re.compile(r"^Part\s+(\d+|[IVX]+)\s*[-–:]\s*([A-Z].*)$")


@dataclass
class Chunk:
    id: int
    regulation: str          # "UN R48", must match regulations/index.json
    version: str             # version_label, e.g. "9.3.0"
    page: int                # 1-based PDF page
    paragraph: str | None    # "6.7.4.1", "Annex 6 Part 4 3", or None for page chunks / preamble
    text: str
    title: str = ""          # regulation title, handy to prepend for context
    meta: dict = field(default_factory=dict)

    def cite(self) -> dict:
        src = {"regulation": self.regulation, "version": self.version, "page": self.page}
        if self.paragraph:
            src["paragraph"] = self.paragraph
        return src


def regulation_name(pdf: Path) -> str:
    """UN_R13H_base.pdf -> "UN R13H", UN_GTR_9_base.pdf -> "UN GTR 9"."""
    return pdf.stem.rsplit("_", 1)[0].replace("_", " ")


def load_index(challenge_dir: Path = DEFAULT_CHALLENGE_DIR) -> dict[str, dict]:
    path = Path(challenge_dir) / "regulations" / "index.json"
    if not path.is_file():
        return {}
    return {e["regulation"]: e for e in json.loads(path.read_text(encoding="utf-8"))}


def _version_from_header(text: str) -> str:
    m = re.search(r"version ([\d.]+) \| page", text)
    return m.group(1) if m else ""


def _clean_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not _HEADER.match(ln.strip())]


def _annex_key(annex: str | None) -> tuple[int, str]:
    """Annexes come in order (1, 2A, 2B, 3 ...): a heading numbered below the current annex is a stray reference."""
    if not annex:
        return (0, "")
    m = re.match(r"(\d+)(.*)", annex)
    return (int(m.group(1)), m.group(2))


def _looks_like_paragraph_number(num: str, rest: str) -> bool:
    # skip table values / measurements such as "12 V", "0.5 mm", "100 cm2"
    if re.match(r"^(mm|cm|m|V|W|cd|lx|%|°|kg|s|Hz|nm)\b", rest):
        return False
    if rest == "":
        return "." in num  # a lone "0" / "1" is a table cell, a lone "5.4.2." is a heading whose text wrapped
    return rest[:1].isupper() or rest[:1] in "(\"“"


def parse_pdf(pdf: Path, index: dict[str, dict], granularity: str = "paragraph", start_id: int = 0) -> list[Chunk]:
    reg = regulation_name(pdf)
    entry = index.get(reg, {})
    role = "latest" if pdf.stem.endswith("_latest") else "base"
    version = next((v["version_label"] for v in entry.get("versions", []) if v["role"] == role), "")
    title = entry.get("title", "")
    chunks: list[Chunk] = []
    annex, part, current = None, None, None
    with pymupdf.open(pdf) as doc:
        for pno, page in enumerate(doc, start=1):
            raw = page.get_text()
            version = version or _version_from_header(raw)
            lines = _clean_lines(raw)
            if granularity == "page":
                chunks.append(Chunk(start_id + len(chunks), reg, version, pno, None, "\n".join(lines), title))
                continue
            buf: list[str] = []
            # a page with many "Annex N Title" lines is a table of contents, not the start of an annex
            is_toc = sum(bool(_ANNEX.match(ln)) for ln in lines) >= 3

            def flush():
                if buf:
                    chunks.append(Chunk(start_id + len(chunks), reg, version, pno, current, "\n".join(buf), title))
                    buf.clear()

            for ln in lines:
                if not is_toc and (m := _ANNEX.match(ln)) and _annex_key(m.group(1)) >= _annex_key(annex):
                    flush()
                    annex, part, current = m.group(1), None, f"Annex {m.group(1)}"
                elif annex and (m := _PART.match(ln)):
                    flush()
                    part = m.group(1)
                    current = f"Annex {annex} Part {part}"
                elif (m := _PARA.match(ln)) and _looks_like_paragraph_number(m.group(1), m.group(2)):
                    flush()
                    num = m.group(1)
                    prefix = f"Annex {annex}" + (f" Part {part}" if part else "") + " " if annex else ""
                    current = prefix + num
                buf.append(ln)
            flush()  # a paragraph that continues on the next page keeps its label there
    return chunks


def load_clauses(clause_dir: Path = CLAUSE_DIR, index: dict | None = None) -> list[Chunk]:
    """The team's parse (data-ingestion/clauses/*.json, made by data-ingestion/txt_to_clauses.py): one chunk per clause.
    A clause can span pages; the chunk is cited at its first page and keeps all of them in meta["pages"]."""
    index = load_index() if index is None else index
    chunks: list[Chunk] = []
    for path in sorted(Path(clause_dir).glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        title = index.get(doc["regulation"], {}).get("title", "")
        for c in doc["clauses"]:
            if not c["text"].strip() or not c["pages"]:
                continue
            para = (c["paragraph"] or "").replace(" / ", " ") or None  # "Annex 6 / Part 4 / 3" -> "Annex 6 Part 4 3"
            chunks.append(Chunk(len(chunks), doc["regulation"], doc["version"], c["pages"][0], para,
                                c["text"].replace("\r\n", "\n"), title, {"pages": c["pages"]}))
    return chunks


def load_corpus(
    granularity: str = "paragraph",
    source: str = "clauses",
    pdf_dir: Path = PDF_DIR,
    challenge_dir: Path = DEFAULT_CHALLENGE_DIR,
    use_cache: bool = True,
) -> list[Chunk]:
    """source="clauses": the team's pre-parsed clauses (fast, shared). source="pdf": parse the PDFs here with
    `granularity` "paragraph" or "page" (cached in .cache/ because parsing 55 PDFs takes a while)."""
    if source == "clauses" and granularity == "paragraph":
        return load_clauses(CLAUSE_DIR, load_index(challenge_dir))
    pdfs = sorted(Path(pdf_dir).glob("*.pdf"))
    stamp = hashlib.sha1(repr([(p.name, p.stat().st_size) for p in pdfs]).encode()).hexdigest()[:10]
    cache = CACHE_DIR / f"corpus_{granularity}_{stamp}.pkl"
    if use_cache and cache.is_file():
        return pickle.loads(cache.read_bytes())
    index = load_index(challenge_dir)
    chunks: list[Chunk] = []
    for pdf in pdfs:
        chunks.extend(parse_pdf(pdf, index, granularity, start_id=len(chunks)))
    CACHE_DIR.mkdir(exist_ok=True)
    cache.write_bytes(pickle.dumps(chunks))
    return chunks
