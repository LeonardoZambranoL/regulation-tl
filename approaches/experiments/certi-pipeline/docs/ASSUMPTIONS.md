# Assumptions & Design Decisions (`docs/ASSUMPTIONS.md`)

1. **Experiment Layout (`approaches/experiments/certi-pipeline/`)**:
   - Per team rules in `AGENTS.md` and user confirmation, all pipeline code, prompts, scripts, docs, tests, configs, and outputs live under `approaches/experiments/certi-pipeline/`.
   - Predictions are exported to `outputs/predictions.json` (for `dev-rear-lamp`) and `outputs/predictions-holdout-acpe.json` (for `holdout-acpe`) and evaluated via `approaches/benchmarking/bench.py`.
2. **Focus on Main Goal (`predictions.json`)**:
   - Per user confirmation, we focus 100% on the main-goal pipeline (`predictions.json` on `dev-rear-lamp` and `holdout-acpe`) and skip the Demo UI and optional sub-goal module for now.
3. **LLM Provider & Model Tiering**:
   - Anthropic Claude (`ANTHROPIC_API_KEY` from `.env`) is used for all LLM calls:
     - `claude-opus-5-5` for Stage 1 (Product Reader, multimodal vision + text) and Stage 2b (Regulation Gate verifier).
     - `claude-sonnet-5-5` for Stage 3/4 (Exhaustive Clause Extraction & Second-Pass Coverage) and Stage 5 (Bounded Batch Verification: faithfulness, atomicity, applicability).
   - Every LLM call uses structured JSON schema output (`output_config.format = json_schema`) and is deterministically cached on disk in `.cache/llm/` keyed by `sha256(model + prompt_version + rendered_input)`.
4. **Embeddings & Hybrid Retrieval**:
   - We use the precomputed `gemini-embedding-2-preview` (768-dim) vectors in `data-ingestion/embeddings/gemini-embedding-2-preview_d768_n26769.npz` combined with BM25+ (with bigrams) via Reciprocal Rank Fusion (RRF), plus cached query embeddings via `data-ingestion/gemini_embedding.py`.
5. **Deterministic Citation & Annex/Table Repair (Stage 0)**:
   - As documented in `docs/DATA_AUDIT.md`, `data-ingestion/txt_to_clauses.py` suffered from false `Annex N` matches inside table rows (e.g. `UN R150` page 14 `Table 1` had a row starting with `Annex 5   Shapes and dimensions...`, causing Annexes 1–4 to be mislabeled `Annex 5 / ...`), detached `Table N` labels, and sub-clauses merged into parent blocks due to multi-space indentation (`ambiguous_numbered_line`).
   - Stage 0 deterministically repairs Annex/Part/Appendix hierarchy across all 56 regulations, attaches `Table N` blocks to their enclosing paragraph citation (`<enclosing_paragraph>. Table N`), and exposes merged sub-clauses so 100% of gold paragraphs are reachable.
