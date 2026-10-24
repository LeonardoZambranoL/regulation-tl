# Agentic RAG

Claude reads the product specification and chooses searches against the shared local vector database. Search results are regulation candidates. Claude must inspect the scope and opening clauses of every regulation it explicitly selects. Workers then assess every clause in those selected regulations, including clauses that were not vector-search hits. Independent verification checks the proposed requirements.

## Run

From the repository root with the virtual environment activated:

```powershell
python -m pip install -r approaches/experiments/agentic-rag/requirements.txt
python approaches/experiments/agentic-rag/run.py --dry-run
python approaches/experiments/agentic-rag/run.py
```

Set `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` in the repository `.env`, or copy this experiment's `.env.example` to `.env` in this folder. `GOOGLE_API_KEY` is accepted instead of `GEMINI_API_KEY`. Environment variables take precedence, then experiment `.env`, then repository `.env`. Gemini is needed only for new search-query embeddings; the corpus vectors already exist.

If the shared database is absent, run `python data-ingestion/import_vectors.py` first. The experiment reads `data-ingestion/.cache/lancedb`, table `clauses`, without changing it.

The existing vectors and all query embeddings use `gemini-embedding-2-preview` at 768 dimensions. The experiment does not rebuild vectors. It refuses to start if the database manifest names another model.

Default input: `../industrial-ai-hackathon/cases/dev-rear-lamp/spec.md`. Default team: `4TL`. Only the text specification is provided to agents.

```powershell
# Stop after agentic retrieval to inspect searches and the selected regulations.
python approaches/experiments/agentic-rag/run.py --retrieve-only

# Use another product and separate output directory.
python approaches/experiments/agentic-rag/run.py --spec path/to/spec.md --case-id example --output path/to/output
```

`--max-batches N` limits assessment for a smoke run, explicitly marks coverage incomplete, and exits nonzero for partial analysis. `--dry-run` checks the shared database and configuration without any API calls. `--db`, `--index`, `--config`, and `--team-id` are also supported. Keep different cases' outputs in separate directories.

## Method

1. Load the shared table's complete text and metadata, validate base regulation versions against the challenge index, and group records by regulation/version.
2. A Sonnet planning agent gets the spec and regulation catalogue. Its native `search_regulations` tool embeds the agent's plain query with `gemini-embedding-2-preview`, 768 dimensions. It calls the same `data-ingestion/gemini_embedding.py` helper as `embed_clauses.py`; there is no separate SDK or query prefix. The existing NPZ does not record its historical client implementation, so exact reproducibility of those already-created vectors remains uncertain. Never silently substitute another embedding model.
3. Each search compares its vector with all 26,769 clause vectors using exact cosine search. Results are grouped by regulation/version. A regulation's score is the average similarity of its three best clauses, preventing one regulation from occupying the whole result list merely by returning many clauses. Each query returns the 12 highest-scoring distinct candidates. At least four distinct searches are required.
4. Search results are not automatically scanned. The planner uses `inspect_regulation` to read the scope/opening clauses of plausible candidates, then returns explicit regulation/version selections with reasons and confidence. It cannot select an undiscovered or uninspected regulation. The planner has up to 18 tool calls over 12 rounds so it can search broadly and inspect a smaller set. Its prompt distinguishes direct product/installation rules from host-vehicle context and redundant predecessor regulations.
5. Assign every clause in every explicitly selected regulation exactly once, in batches of at most 12 clauses and 14,000 target characters (an oversized individual clause stays intact). Ten concurrent Sonnet workers receive the spec, targets, and up to 24,000 characters of parent/scope/neighbor context. Native `search_clauses` and `read_clause` tools let workers resolve references across the entire corpus. These context searches are lexical; the planning stage uses vector search. Each worker may propose only its own target clauses.
6. Sonnet verifies each proposed requirement, with its own context tools. Export only supported candidates. No requirement deduplication. Irrelevant and `needs_context` decisions are recorded but not automatically reassessed; verification receives proposed requirements only, matching the existing exhaustive experiment.
7. Validate predictions against the official schema and allowed sources. Preserve reasons, confidence, citations, exact evidence, tool traces, retry histories, and incomplete coverage in diagnostics.

Assessment and verification use a local snapshot of the exhaustive experiment engine and prompts, leaving that experiment unchanged. Each task can retry twice after the initial attempt, in addition to API and response-validation retries. Successful Claude responses and query vectors are cached under this experiment's `.cache`. Cache replay costs zero for that API; previously billed calls remain billed. Candidate regulations are unioned for planner inspection, but only explicit planner selections are scanned. Requirement records are never deduplicated.

## Models and costs

Defaults in `config.json`: Sonnet `claude-sonnet-5-5` for planning, assessment, and verification. Opus is rejected. Query model must match the corpus vectors: `gemini-embedding-2-preview`, 768 dimensions. The shared database manifest is checked before retrieval. If that model is unavailable to your API key, retrieval fails rather than silently mixing vector spaces.

Assessment and verification display progress and estimated Claude cost live. `costs.json` records planning, assessment, and verification usage using inherited `pricing.json` rates; these are estimates, not invoices. Gemini query embedding costs are additional and are **not priced**: `embedding-costs.json` reports request/cache counts with `estimated_usd: null`. Check provider billing for the combined total.

## Outputs

- `predictions.json`: official submission schema, without reasons or confidence.
- `diagnostics.json`: decisions, evidence, verification, errors, coverage of selected regulations, and Claude cost estimate.
- `retrieval.json`: query/tool history, hit IDs/distances, final planning summary, and all selected regulation/version pairs.
- `costs.json` and `embedding-costs.json`: cost/usage information for this invocation.

Coverage marked complete means all clauses in the retrieved regulations were assessed and verification tasks completed; it does not mean all regulations were retrieved or every uncertainty was resolved. Generous retrieval may select much of the corpus, limiting cost savings. Regulation discovery and verification can both reduce recall. Clause parsing and evidence page boundaries retain the source data's limitations.

## Validation and history

Dev `dev-rear-lamp` run (`0d47e3ab48644982884fa2b10ba142e9`): five semantic searches found 19 candidates; the planner inspected candidates and selected 6 regulations. Sonnet assessed all 2,746 selected clauses without errors and exported 571 supported requirements. Estimated Claude cost was $14.9809; Gemini query charges are additional and unpriced here.

- Page: precision 0.3333, recall 0.8302, F1 0.4757, F2 0.6395 (135 submitted pages).
- Clause: precision 0.1365, recall 0.6116, F1 0.2232, F2 0.3606 (74/121 expected clauses matched; 542 submitted).
- Regulation: precision 0.5000, recall 0.7500, F1 0.6000, F2 0.6818 (3/4 expected regulations matched; 6 submitted).

The non-embedding `agentic-regulation-screening` run scored page/clause/regulation F2 of 0.7005/0.3871/0.8000, so this run trails it by 0.0610/0.0265/0.1182 despite scanning fewer clauses. The current dev leader is `devansh-llm-clause-filter` at 0.8442/0.6195/1.0000, ahead by 0.2047/0.2589/0.3182. The result indicates that explicit RAG selection reduced work but lost one relevant regulation, while clause precision remained low. No holdout run exists, so there is no robust score. No gold file entered generation and no parameter was chosen from this score.
