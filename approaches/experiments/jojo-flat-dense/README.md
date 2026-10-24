# Flat / brute force + Anthropic

This independent experiment scans every dense document vector for every query,
then uses Claude to check the selected original source pages and produce atomic,
evidence-backed requirements. It is a baseline for the known `dev-rear-lamp` case.
No ANN graph, sparse retrieval, score fusion, reranker, training or fitted weight
is used by this variant.

## Method

1. Freeze the product specification, product image and source corpus fingerprints.
2. Claude profiles the product and assesses each regulation using its opening pages.
3. Encode the profile's search queries with the existing local BGE-small-en-v1.5
   encoder. Anthropic is used for interpretation and generation; BGE supplies vectors.
4. Compute cosine similarity against **all 31,056 normalized, 384-dimensional
   vectors**, in blocks of 8,192. The matrix occupies 47,702,016 bytes. Scope filtering
   happens after the full scan. Sort exactly, breaking ties by corpus order, and
   deduplicate clause windows before taking six clauses per query.
5. Merge query results round-robin, follow source references to depth two, and select
   up to 32 three-page packets, including opening pages and governing context.
6. Claude reads source text and PDF page images, extracts obligations, checks
   applicability/evidence and reviews duplicates. Unreviewed candidates and unresolved
   references remain explicit. Freeze the schema-validated predictions before scoring.
7. Run the unchanged TL repository citation benchmark and regenerate dashboard rows.

The inherited hybrid retriever already calculated dense dot products exhaustively.
This experiment makes Flat a standalone retriever, removes lexical scoring entirely,
and scans all vectors before scope filtering. It is **not** an HNSW-versus-Flat speed
comparison. Round-robin query merging also differs from the original BM25+dense
workflow's sequential union, so end-to-end differences do not isolate index type.

The extraction model is `claude-sonnet-5-5`. Exact model-file hashes, Python and NumPy
versions are in `retrieval-verification.json`; pinned dependencies are included.
Flat retrieval has no random sampling. LLM generation is not deterministic.

## Reproduce

Use Python 3.12. From this experiment folder:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
ln -s /absolute/path/to/industrial-ai-hackathon src/industrial-ai-hackathon
ln -s /absolute/path/to/regulation-db/corpus src/regulation-db/corpus
ln -s /absolute/path/to/regulation-db/retrieval/index src/regulation-db/retrieval/index
ln -s /absolute/path/to/regulation-db/retrieval/model-cache src/regulation-db/retrieval/model-cache
.venv/bin/python -m unittest discover -s src/regulation-db/retrieval -p test_flat.py -v
.venv/bin/python verify_flat.py
.venv/bin/python -m unittest discover -s src/regulation-db/workflows -p test_flat_recovery.py -v
.venv/bin/python src/regulation-db/workflows/run_flat.py prepare \
  --case-dir src/industrial-ai-hackathon/cases/dev-rear-lamp \
  --out runs/flat32 --team-id jojo-flat-dense --config config.json
.venv/bin/python run_budgeted.py --out runs/flat32 \
  --key-file /absolute/path/to/private-anthropic-key \
  --additional-usd 5 --shared-ceiling-usd 17
```

Shared data must be the source-only corpus and matching BGE index; inference never
reads `expected.json` or previous submissions. The corpus contains absolute PDF
paths, which must remain accessible. Symlinks, model caches, API keys, and virtual
environments are not committed. Source/index creation is described in the existing
`jojo-splade-dense` experiment and the workspace `regulation-db/retrieval/README.md`.

This run uses its own inputs, manifest, configuration, selection, outputs and scores.
Identical Claude requests reuse the shared response cache. The launcher waits for
the shared ledger lock and records a maximum **$5 incremental cost**, also respecting
the $17 shared ceiling. It preserves the $5 experiment allowance across restarts and excludes unrelated
experiments’ spending between locked run segments. Cached
requests are included in the standalone cost estimate but do not incur new spend.
The completed workspace run is `regulation-db/workflows/runs/dev-flat32-v2`.
The first attempt stopped on a confirmed `max_tokens` response; `attempt-v1/`
preserves its manifest, failure and original client/extraction code. The repair
reuses successful cached requests and raises the extraction output limit from
16,000 to 32,000 only after a confirmed truncated response, once per request.
Refusals, budget stops and uncertain network outcomes are never retried this way.
The v2 run inherits v1’s recorded spend, so the $5 limit covers both attempts.

After completion copy the frozen `targeted/submission.json` to
`outputs/predictions.json`. From the TL repository root:

```sh
python approaches/benchmarking/bench.py jojo-flat-dense \
  approaches/experiments/jojo-flat-dense/outputs/predictions.json \
  ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json \
  --index ../industrial-ai-hackathon/regulations/index.json
python approaches/benchmarking/dashboard_rows.py
```

## Validation and limits

Three retrieval unit tests cover exhaustive ranking, duplicate windows, deterministic ties,
scope filtering (including empty scope), and incompatible/invalid embeddings.
Three recovery tests cover bounded retries and refusal/budget/network stop behavior.
Two budget tests verify that prior attempt costs and the shared ceiling remain enforced.
An independent per-vector dot-product oracle agrees on all top-100 clause IDs for
three real-corpus queries. Measured scans including sorting/deduplication took
5.3–8.5 ms on this machine, excluding query encoding and index loading. These are
three smoke measurements, not a throughput study.

The official benchmark measures regulation/page citation coverage, including its
paragraph-match allowance. It does not measure semantic requirement correctness.
Only one development case exists. `risk.json` declares medium overfit risk because
the inherited workflow was developed on this product; no Flat hyperparameters are
selected by a gold-score sweep. Exhaustive vector scoring does not imply exhaustive
regulatory coverage: scope selection and the 32-packet reading budget can miss duties.

The repository’s scheduled sync imports pushed dashboard data approximately every
15 minutes while its owner’s Claude app is open. This experiment publishes the
benchmark rows and the generated standalone dashboard through the normal Git flow.
A successful push is not itself evidence that the remote sync has completed.

## Measured result — 2026-10-24

The completed run froze **268 requirements**, after reviewing 32 packets / 96 main
source pages. All eight targeted unit tests passed, as did the official schema and
regulation-version validation. Benchmark run: `a108a047718d466cba252f4066646c15`.

| Metric | Flat | BM25+dense targeted |
|---|---:|---:|
| Page precision | 0.3556 | 0.3250 |
| Page recall | 0.3019 | 0.2453 |
| Page F2 | 0.3113 | 0.2579 |
| Regulation F2 | 0.6250 | 0.4348 |

Both rows use the same gold fingerprint and evaluator
`official-local-f2-v1-6de0fe1e0763`. Other historical runs have a different scorer
checksum; the generated Markdown leaderboard keeps those groups separate.
This single-case improvement does not establish general superiority of Flat.
Flat covered 16 of 53 expected pages and cited 8 regulations, of which 3 match
the expected set of 4. Coverage remains incomplete; no score-driven retuning followed.

Additional estimated API spend was **$3.757066**, including the truncated first
attempt and its repair, below the authorized $5 limit. The estimated standalone
model cost, including reused cached requests, was **$6.621438**. Unrelated experiments’
spending between the two locked segments is excluded from the additional cost.
Evidence, scope, review decisions, coverage, input/code fingerprints and budget
accounting are preserved in `outputs/audit/`; no API keys or raw API cache is included.

The dashboard’s stricter paragraph citation F2 is **0.2639**
(precision 0.1705, recall 0.3058). This is still
a citation metric, not semantic requirement matching.
