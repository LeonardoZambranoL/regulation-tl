# Certi Deterministic 6-Stage Pipeline (`certi-pipeline`)

## In plain words

Given a product specification (text) and/or an exploded-view engineering drawing, this pipeline identifies every UN Regulation engineering requirement the product must fulfil and cites the exact regulation, base version, PDF page, and paragraph.
1. **Stage 0 (Load & Citation Repair)**: Loads the 56 pre-parsed UN Regulations (`data-ingestion/clauses/*.json`) and deterministically repairs parser anomalies (false `Annex 5` table-row jumps in `UN_R150_base.json`, detached `Table N` labels, and multi-space sub-clauses).
2. **Stage 1 (Product Reader)**: Claude Opus reads the spec and exploded-view drawing in a single structured call to inventory all product parts, functions, vehicle categories, and electronic sub-assemblies (ESAs).
3. **Stage 2 (Regulation Gate)**: Combines hybrid search (BM25+ with bigrams + 768-d Gemini embeddings via Reciprocal Rank Fusion), product-neutral domain rules, supersession/consolidation checks (`UN R148`/`R149`/`R150`), and a Claude Opus Gate verifier to select the governing UN Regulations.
4. **Stage 3 & 4 (Exhaustive Extraction & Coverage Ledger)**: Claude Sonnet scans every clause of the selected regulations in document order, tracks a 100% clause coverage ledger, and runs a Second-Pass completeness auditor on any unreviewed clauses.
5. **Stage 5 & 6 (Bounded Verifiers & Atomic Obligation Output)**: Pure-code citation verification repairs/validates every paragraph and page against `index.json`, bounded Claude Sonnet verifiers filter out inapplicable or unsupported clauses, and the final `outputs/predictions.json` emits individual atomic engineering obligations ("The [component] shall ..."), preserving all distinct obligations per paragraph for 1-to-1 requirement matching, validated by the official `validate.py`.

## How to Run (5 Commands)

From `approaches/experiments/certi-pipeline/`:

```bash
# 1. Audit parsed regulation data and verify 100% gold paragraph reachability
../../../.venv/bin/python scripts/inspect_data.py

# 2. Run unit tests (Stage 0 repair, citation check, deduplication, official schema)
../../../.venv/bin/python -m unittest discover -s tests -p "test_*.py" -v

# 3. Run pipeline on dev-rear-lamp -> outputs/predictions.json
../../../.venv/bin/python -m certi.run --case dev-rear-lamp --out outputs/predictions.json

# 4. Run pipeline on unseen holdout-acpe -> outputs/predictions-holdout-acpe.json
../../../.venv/bin/python -m certi.run --case holdout-acpe --out outputs/predictions-holdout-acpe.json

# 5. Evaluate and update the shared leaderboard (from repo root)
../../../.venv/bin/python scripts/eval_main.py outputs/predictions.json --case dev-rear-lamp
```

## Assumptions & Limitations

- See [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md) and [docs/DATA_AUDIT.md](docs/DATA_AUDIT.md).
- All LLM and embedding calls are deterministically cached on disk under `.cache/` keyed by `sha256(model + prompt_version + rendered_input)`. Reroofing with warm cache makes zero API calls.
