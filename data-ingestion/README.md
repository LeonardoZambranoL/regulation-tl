# PDF text extraction

For the shared local vector database, see [VECTOR_DB.md](VECTOR_DB.md). Import with
`python data-ingestion/import_vectors.py` after installing `data-ingestion/requirements-vectors.txt`.

From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r data-ingestion/requirements.txt
.\.venv\Scripts\python.exe data-ingestion/pdf_to_txt.py
```

Reads all PDFs under `regulations` and writes matching UTF-8 `.txt` files under
`data-ingestion/text`, preserving relative folders. Defaults work from any working
directory. Use `--input PATH --output PATH` to choose different folders.

Uses layout extraction to retain approximate table spacing and separates pages
with explicit markers such as `=== PDF PAGE 24 ===`. Rerunning replaces matching text files only
after extraction succeeds. Errors are reported per PDF and do not stop the batch.
Exit code 1 means failures or empty-page warnings; 0 means a clean conversion.

This extracts existing PDF text; it does not perform OCR or describe diagrams.
Scans need OCR first. Pages without text are reported for review (they may simply
be blank or contain diagrams). Mixed pages containing both text and scanned
content still need manual review. PDF reading order and complex tables may need
cleanup. If conversion fails, any previous output for that PDF remains unchanged.

## Split text into clauses

```powershell
.\.venv\Scripts\python.exe data-ingestion/txt_to_clauses.py
```

Reads `text/` and writes one JSON per file to `clauses/`. No LLM or extra dependencies.
Each file has `regulation`, `version`, and `clauses`. Each entry has `paragraph`,
`pages`, and `text`; uncertain splits also have `review_flags`.
Introductions have a null paragraph; tables and headings retain their labels.
Page breaks do not end clauses. Annex names distinguish restarted numbering.
These are draft splits; check tables and flagged entries against the source.

Use `--input PATH` for a single file or folder and `--output PATH` to change the output.
