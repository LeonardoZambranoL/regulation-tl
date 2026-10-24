# Architecture Overview (`docs/ARCHITECTURE.md`)

```mermaid
flowchart TD
    A["Input: spec.md + exploded_view.png"] --> S0["Stage 0: Load & Deterministic Citation Repair\n(56 Regulations, 26,769 Clauses, Annex/Table/Sub-clause Fix)"]
    S0 --> S1["Stage 1: Product Reader (claude-opus-5-5)\nParts, Functions, Vehicle Categories, Electronics/ESA"]
    S1 --> S2["Stage 2: Hybrid Regulation Gate\nBM25+ Bigrams + Gemini 768-d RRF + Domain/Supersession/Category Rules + Opus Verifier"]
    S2 --> S3["Stage 3: Exhaustive Clause Extractor (claude-sonnet-5-5)\nDocument-order batches with parent context"]
    S3 --> S4["Stage 4: Clause Coverage Ledger & Second-Pass Auditor\n100% clause accounting per gated regulation"]
    S4 --> S5["Stage 5: Bounded Verification\nPure-code citation_check + Faithfulness/Atomicity/Applicability + Dedup"]
    S5 --> S6["Stage 6: Verbatim Clause Submission Output\npredictions.json (official validate.py) + requirements_rich.json"]
```

## Module Responsibilities

- [`certi/stages/stage0_load.py`](../certi/stages/stage0_load.py): Loads `data-ingestion/clauses/*.json` and `regulations/index.json`; deterministically repairs false tabular `Annex N` transitions, attaches `Table N` captions to their enclosing paragraphs, and extracts verbatim sub-clause text (`sub_paragraph_texts`).
- [`certi/llm.py`](../certi/llm.py): Thread-safe, disk-cached Anthropic Messages API (`output_config.format = json_schema`) and Gemini Embedding client keyed by `sha256(model + prompt_version + rendered_input)`.
- [`certi/retrieval.py`](../certi/retrieval.py): Hybrid BM25+ (with bigrams) and precomputed `gemini-embedding-2-preview` (768-d) retriever combined via Reciprocal Rank Fusion (`k0=60`) with deterministic tie-breaking (`np.lexsort`).
- [`certi/stages/stage1_product_reader.py`](../certi/stages/stage1_product_reader.py): Multimodal spec + drawing inventory.
- [`certi/stages/stage2_gate.py`](../certi/stages/stage2_gate.py): Hybrid candidate selection, supersession/category filtering, and Claude Opus gate verification (`runs/<id>/gate.json`).
- [`certi/stages/stage3_extract.py`](../certi/stages/stage3_extract.py): Exhaustive document-order clause extraction and Stage 4 coverage ledger (`runs/<id>/stage4_ledger.json`).
- [`certi/stages/stage5_verify.py`](../certi/stages/stage5_verify.py): Pure-code citation check/repair, batched bounded LLM verifier (`KEEP | FIX | SPLIT | DROP`), verbatim clause projection, and official `validate.py` verification.
