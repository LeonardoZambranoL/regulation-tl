# Technical explanation: data ingestion

Our ingestion pipeline transforms regulation PDFs into reusable, citation-aware text and clause records. An optional embedding and database path makes those same records searchable by semantic similarity. Document parsing is deterministic and does not use an LLM; embedding generation uses a dedicated embedding model.

The implementation is in [`data-ingestion`](../../data-ingestion). The stages are separated so downstream experiments can reuse the same source corpus without repeatedly extracting PDFs or generating vectors.

## Step 1 — Read the regulation PDFs

The input is the collection of regulation PDFs under `regulations/`. Each document represents a particular regulation version. `pdf_to_txt.py` discovers PDFs recursively in a stable filename order and preserves their relative directory structure in the output.

The official regulation index supplies version and title metadata to downstream retrieval. The clause parser also requires the regulation/version header in the extracted document itself. This prevents the pipeline from treating a page number as a citation without its regulation and version.

## Step 2 — Extract text while retaining page boundaries

[`pdf_to_txt.py`](../../data-ingestion/pdf_to_txt.py) uses `pypdf.PdfReader` in layout extraction mode. It extracts each page's existing text, retaining approximate spacing useful for reading tables, then inserts an explicit marker:

```text
=== PDF PAGE 24 ===
```

The result is a UTF-8 text file under `data-ingestion/text/`. These markers preserve PDF page positions independently of printed paragraph numbering and allow later clauses to be traced back to source pages.

Extraction completes before an existing output is replaced. A temporary file is written and then renamed, so a failed extraction leaves the prior text file intact. Errors are reported per PDF without stopping the rest of the batch. Empty pages produce review warnings; entirely unextractable documents fail conversion. The process returns a nonzero exit status for failures or empty-page warnings.

This stage does not perform OCR or interpret diagrams. Scanned content, mixed image/text pages and complex reading order still require review.

## Step 3 — Identify document structure and clause boundaries

[`txt_to_clauses.py`](../../data-ingestion/txt_to_clauses.py) reads the extracted text and identifies structure through deterministic patterns:

- Numbered paragraphs and subparagraphs.
- Annex headings.
- Parts and appendices.
- Table and figure captions.
- Preamble and introductory material.

The parser tracks the current annex, part and appendix so that restarted paragraph numbering remains distinguishable. For example, `Annex 3 / Appendix 2 / 5.2.2` is distinct from paragraph `5.2.2` in the main body.

Page breaks do not terminate clauses. A provision that continues onto another page remains one block with multiple associated page numbers. Table and figure captions establish separate blocks, with heuristics to avoid mistaking numeric rows or footnotes for legal paragraph headings.

During parsing, every input line is assigned to a block. An internal reconstruction check verifies that concatenating the blocks' raw text reproduces the original extracted text. This checks source-line coverage, not whether each inferred boundary is legally correct.

## Step 4 — Export citation-aware clause JSON and review flags

The parser writes one JSON document per input text file under `data-ingestion/clauses/`. Each document contains:

```text
regulation
version
clauses[]
  paragraph
  pages[]
  text
  review_flags[]  — when needed
```

Introductions can have a null paragraph. Numbered clauses include their annex/part/appendix context, while tables and headings retain their labels. Page markers and recognized repeating footers are removed from the exported clause text; their page information remains in `pages`.

Uncertain boundaries are explicitly flagged. Examples include duplicate numbering, numbering moving backwards, missing parent clauses, ambiguous annex headings, and uncertain table/figure extents. Suspicious numeric lines are retained in the source block rather than silently discarded.

The parser requires consecutive page markers starting at page 1 and a regulation/version header. JSON outputs are written through temporary files before replacement. The intermediate raw blocks and parent pointers are parsing internals; the exported JSON is the simpler clause representation above.

These records are draft structural splits. Flags support human or downstream review, and unflagged records are not guaranteed to be free of parsing errors. Experiment-specific citation repairs, such as those in Certi's loader, are separate from this shared ingestion stage.

## Step 5 — Generate clause embeddings when semantic retrieval is needed

[`embed_clauses.py`](../../data-ingestion/embed_clauses.py) turns clause records into vectors using the shared [`gemini_embedding.py`](../../data-ingestion/gemini_embedding.py) helper. The configured defaults are `gemini-embedding-2-preview` and 768 dimensions.

Each embedding input includes the regulation identifier, regulation title, normalized paragraph label and clause text. Files are read in sorted order and clauses retain their original order; concurrent requests write results back to their assigned positions. This stable ordering is essential for mapping vectors back to citations.

The helper calls Google's `embedContent` endpoint, checks vector dimensionality and finite values, rejects zero vectors, and normalizes each vector to unit length. Transient API/network failures have bounded retries. This stage requires an API key and incurs embedding costs; the earlier PDF and clause stages do not.

The output is a compressed NPZ containing float16 embeddings plus parallel arrays for regulation, version, first page and paragraph. The clause JSON remains the authority for full text and all pages. The current generator writes the completed archive after generation; it is not a per-clause resumable embedding cache.

## Step 6 — Validate and import the shared vector database

[`import_vectors.py`](../../data-ingestion/import_vectors.py) imports the existing NPZ and clause JSON into a local LanceDB table. Importing does not call an embedding API or require a key.

Before writing, it verifies vector shape, finite/nonzero values, metadata lengths and total clause counts. It then compares every vector's regulation, version, first page and normalized paragraph with the clause at the corresponding corpus position. A mismatch stops import.

Each database record stores:

- `clause_id`: JSON filename stem plus zero-based clause position.
- `vector_row`: the corresponding position in the embedding archive.
- Regulation, version, paragraph, all source pages and source text.
- The embedding, converted to float32 for storage.

The positional clause ID keeps repeated citation labels distinct. The database is stored at `data-ingestion/.cache/lancedb`, in table `clauses`. Its manifest records the model, dimensionality, row count and embedding source filename. The importer checks the stored row count and performs a vector-search sanity check. Existing tables are not overwritten unless `--replace` is explicitly supplied.

The supplied archive does not contain source-text hashes, so metadata checks cannot detect changed wording when citations and ordering remain identical. It also lacks complete historical embedding-prompt provenance. Matching metadata is therefore necessary, but not proof that arbitrary edited clause text corresponds to the existing vectors.

## Step 7 — Reuse the ingested corpus in downstream approaches

Experiments read the shared text, clause JSON or vector table without modifying them. Lexical retrieval can use the clause text directly. Semantic retrieval embeds a query with the same model and 768-dimensional configuration, then searches using cosine distance. The current shared table uses exact vector search rather than a configured approximate index.

Vector search returns candidate source records; it does not determine legal applicability or generate engineering requirements. Product-specific filtering, requirement extraction and model judgments belong to the downstream approaches.

The regulation-change experiment additionally caches new-document parsing by PDF SHA-256 and verifies its case PDFs against the provided manifest. That caching is implemented by the experiment's ingestion wrapper; the standalone shared extraction scripts themselves recompute their outputs when invoked.

## Reproducibility and limitations

The pipeline keeps document extraction, structural parsing, embedding generation and database import separate. This makes intermediate artifacts inspectable and lets experiments reuse expensive preparation work. Neither shared parsing nor vector import reads product answer keys.

The main limitations are PDF reading order, scanned or diagram-only content, complex table relationships, and heuristic clause boundaries. Page and source preservation make these issues traceable, but do not automatically resolve them. Any downstream result must still distinguish source retrieval from verified interpretation of the regulation.
