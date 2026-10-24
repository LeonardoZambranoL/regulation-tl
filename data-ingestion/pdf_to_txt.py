"""Extract regulation PDFs into UTF-8 text, with page boundaries preserved."""

import argparse
import sys
from pathlib import Path

from pypdf import PdfReader


def main():
    project = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=project / "regulations")
    parser.add_argument("--output", type=Path, default=project / "data-ingestion" / "text")
    args = parser.parse_args()
    if not args.input.is_dir():
        parser.error(f"Input directory does not exist: {args.input}")
    pdfs = sorted(p for p in args.input.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    if not pdfs:
        parser.error(f"No PDFs found in {args.input}")

    failed = 0
    warned = 0
    for pdf in pdfs:
        try:
            with pdf.open("rb") as source:
                reader = PdfReader(source)
                if reader.is_encrypted and not reader.decrypt(""):
                    raise ValueError("PDF requires a password")
                pages = [page.extract_text(extraction_mode="layout").strip() for page in reader.pages]
            if not pages or not any(pages):
                raise ValueError("No extractable text; OCR may be required")
            empty = [str(i) for i, page in enumerate(pages, 1) if not page]
            if empty:
                warned += 1
                print(f"WARNING {pdf.name}: no text on pages {', '.join(empty)}; check for scans/diagrams", file=sys.stderr)
            target = args.output / pdf.relative_to(args.input).with_suffix(".txt")
            target.parent.mkdir(parents=True, exist_ok=True)
            # Complete extraction before replacing any existing output.
            temporary = target.with_suffix(".txt.tmp")
            try:
                text = "\n\n".join(
                    f"=== PDF PAGE {number} ===\n\n{page}"
                    for number, page in enumerate(pages, 1)
                )
                temporary.write_text(text + "\n", encoding="utf-8")
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            print(f"OK {pdf.name} -> {target} ({len(pages)} pages)")
        except Exception as error:
            failed += 1
            print(f"FAILED {pdf}: {error}", file=sys.stderr)

    print(f"Converted {len(pdfs) - failed}/{len(pdfs)} PDFs; {failed} failed; {warned} with empty-page warnings.")
    return 1 if failed or warned else 0


if __name__ == "__main__":
    sys.exit(main())
