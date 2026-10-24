"""Split extracted regulation text into source-preserving JSON blocks (no LLM)."""

import argparse
import json
import re
import sys
from pathlib import Path


PAGE = re.compile(r"^=== PDF PAGE (\d+) ===$")
FOOTER = re.compile(r"^UN .+, version .+ \| page \d+ of \d+$")
META = re.compile(r"^[ \t]*(UN .+?) \(version ([^)]+)\)[ \t]*\r?$", re.MULTILINE)
NUMBER = re.compile(r"^(\d+(?:\.\d+)*)(\.)?\s+(\S.*)$")
# Require a title, not a bare inline reference such as 'Annex 1.'.
ANNEX = re.compile(r"^Annex\s+(\d+[A-Z]?)[ :\-]+([A-Z].*)$")
SUBSECTION = re.compile(r"^(Appendix|Part)\s+([A-Z]|[IVX]+|\d+)[ :\-]+([A-Z].*)$")
CAPTION = re.compile(r"^(Table|Figure)\s+([A-Za-z0-9]+(?:[-\u2013][A-Za-z0-9]+)*)(?:\s|:).*$")


def parse_text(source):
    """Every input line belongs to exactly one block; raw_text is lossless."""
    lines = source.splitlines(keepends=True)
    metadata = META.search(source)
    if not metadata:
        raise ValueError("Missing regulation/version header")
    page = None
    page_numbers = []
    markers = []
    for line in lines:
        marker = PAGE.fullmatch(line.strip())
        if marker:
            page = int(marker[1])
            markers.append(page)
        page_numbers.append(page)
    if not markers or markers != list(range(1, len(markers) + 1)):
        raise ValueError("Page markers must be consecutive, starting at 1")

    blocks = []
    annex = None
    part = None
    appendix = None
    current_clause = None
    seen = {}
    previous_number = {}
    active = None

    def start(index, kind, label=None, parent_id=None, flags=None):
        nonlocal active
        if active is not None:
            active["line_end"] = index
        active = {
            "id": f"b{len(blocks) + 1:06d}", "kind": kind,
            "label": label, "annex": annex, "part": part,
            "appendix": appendix, "parent_id": parent_id,
            "line_start": index + 1, "line_end": len(lines),
            "review_flags": flags or [],
        }
        blocks.append(active)
        return active

    start(0, "preamble")
    for index, original in enumerate(lines):
        text = original.strip()
        if not text or PAGE.fullmatch(text) or FOOTER.fullmatch(text):
            continue
        context = (annex, part, appendix)
        match = ANNEX.fullmatch(text)
        if match:
            # Annex headings normally increase. Do not reinterpret a backward
            # inline reference as a new document section.
            number = int(re.match(r"\d+", match[1])[0])
            if annex and number <= int(re.match(r"\d+", annex)[0]):
                active["review_flags"].append("ambiguous_annex_heading")
                continue
            annex, part, appendix = match[1], None, None
            current_clause = None
            start(index, "annex", f"Annex {annex}")
            continue
        match = SUBSECTION.fullmatch(text)
        if match:
            if match[1] == "Part":
                part, appendix = match[2], None
            else:
                appendix = match[2]
            current_clause = None
            start(index, "section", f"{match[1]} {match[2]}", flags=["check_section_boundary"])
            continue
        match = CAPTION.fullmatch(text)
        if match:
            start(index, match[1].lower(), f"{match[1]} {match[2]}",
                  current_clause, ["check_table_or_figure_extent"])
            continue
        match = NUMBER.fullmatch(text)
        if not match:
            continue
        label, dot, body = match.groups()
        flags = []
        # Numeric table rows and footnotes must not silently become clauses.
        tabular = bool(re.search(r"\S\s{3,}\S", text))
        if tabular or not re.match(r'[A-Z"\u201c(]', body):
            active["review_flags"].append("ambiguous_numbered_line")
            continue
        if active["kind"] in ("table", "figure") and "." not in label:
            active["review_flags"].append("ambiguous_number_in_table_or_figure")
            continue
        key = (*context, label)
        numbers = tuple(map(int, label.split(".")))
        if key in seen:
            active["review_flags"].append("duplicate_numbered_line")
            continue
        previous = previous_number.get(context)
        if previous and numbers <= previous:
            flags.append("numbering_moves_backwards")
        if not dot:
            flags.append("heading_without_terminal_dot")
        parent = seen.get((*context, label.rpartition(".")[0]))
        if "." in label and parent is None:
            flags.append("missing_parent_clause")
        block = start(index, "clause", label, parent, flags)
        seen[key] = block["id"]
        previous_number[context] = numbers
        current_clause = block["id"]

    for block in blocks:
        begin, end = block["line_start"] - 1, block["line_end"]
        selected = lines[begin:end]
        block["raw_text"] = "".join(selected)
        content = [(i, line) for i, line in enumerate(selected, begin)
                   if not PAGE.fullmatch(line.strip()) and not FOOTER.fullmatch(line.strip())]
        block["text"] = "".join(line for _, line in content).strip()
        block["pages"] = sorted({page_numbers[i] for i, line in content
                                  if line.strip() and page_numbers[i] is not None})
        block["review_flags"] = sorted(set(block["review_flags"]))
        if block["kind"] == "clause":
            # Rejected numeric candidates are retained and explicitly reviewable.
            block["paragraph"] = " / ".join(filter(None, [
                f"Annex {block['annex']}" if block["annex"] else None,
                f"Part {block['part']}" if block["part"] else None,
                f"Appendix {block['appendix']}" if block["appendix"] else None,
                block["label"],
            ]))

    assert "".join(block["raw_text"] for block in blocks) == source, "Source coverage failed"
    clauses = []
    for block in blocks:
        if not block["text"]:
            continue
        item = {
            "paragraph": block.get("paragraph", block["label"]),
            "pages": block["pages"], "text": block["text"],
        }
        if block["review_flags"]:
            item["review_flags"] = block["review_flags"]
        clauses.append(item)
    return {"regulation": metadata[1], "version": metadata[2], "clauses": clauses}


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=root / "text")
    parser.add_argument("--output", type=Path, default=root / "clauses")
    args = parser.parse_args()
    files = [args.input] if args.input.is_file() else sorted(args.input.rglob("*.txt"))
    if not files:
        parser.error("No input .txt files found")
    base = args.input.parent if args.input.is_file() else args.input
    failures = 0
    for source in files:
        try:
            # newline='' preserves the exact source line endings for coverage checks.
            with source.open(encoding="utf-8", newline="") as handle:
                result = parse_text(handle.read())
            target = args.output / source.relative_to(base).with_suffix(".json")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(target)
            print(f"OK {source.name}")
        except Exception as error:
            failures += 1
            print(f"FAILED {source.name}: {error}", file=sys.stderr)
    print(f"Processed {len(files) - failures}/{len(files)} files. Outputs require boundary review.")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
