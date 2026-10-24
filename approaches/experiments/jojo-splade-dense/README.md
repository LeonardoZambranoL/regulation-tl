# Jojo: SPLADE + Dense, optional Cross-Encoder

This experiment retrieves source clauses from the base-version regulation corpus,
then uses Claude to extract evidence-backed atomic requirements from complete PDF
page packets. It preserves unresolved references and unreviewed candidates.
The known rear-lamp case is development data, not a blind test.

## Method

1. Freeze the product specification, image and corpus hashes.
2. Search version-scoped text windows with local SPLADE++ and BGE-small-en-v1.5.
3. Fuse the two rankings using equal-weight RRF, k=60; deduplicate clause windows.
4. Optionally rerank a bounded head using MS-MARCO MiniLM-L6, preserving the tail.
5. Merge product queries round-robin, expand source references and attach PDF
   images, neighboring pages and governing section context.
6. Claude checks applicability, conditions, evidence and duplicate candidates;
   mechanical validators check the result. Unreviewed sources remain explicit.
7. Freeze predictions before running the repository's unchanged benchmark.

`config.json` records the selected development configuration. `selection.json`
records its selection rule: page Recall@100, then nDCG@100 on the single development
case. `retrieval-comparison.json` contains all compared variants. This is exploratory
selection, not held-out performance. The internal leaderboard measures citations,
not semantic requirement accuracy. Cross-encoder scores never exclude obligations.

## Install and shared data

Python 3.12. From this experiment directory:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Set this to a checkout of Certivity/industrial-ai-hackathon containing the PDFs.
ln -s /absolute/path/to/industrial-ai-hackathon src/industrial-ai-hackathon
.venv/bin/python src/regulation-db/tools/build.py \
  --repo src/industrial-ai-hackathon --out src/regulation-db/corpus
.venv/bin/python src/regulation-db/retrieval/hybrid.py build
.venv/bin/python src/regulation-db/retrieval/local_embed.py download
.venv/bin/python src/regulation-db/retrieval/local_embed.py corpus
.venv/bin/python src/regulation-db/retrieval/splade_pipeline.py download
.venv/bin/python src/regulation-db/retrieval/splade_pipeline.py build
```

Alternatively link an existing source-only `corpus`, matching `retrieval/index`
and `retrieval/model-cache` at those paths. The runtime checks document hashes,
model identities and corpus fingerprints. The database records absolute PDF paths;
rebuild it after moving the source PDFs. Do not copy prior curated answers into
this corpus. No expected answers are used by indexing or inference.

Model downloads require network; retrieval itself runs locally. The dense and
sparse model revisions are identified by file hashes in the comparison. No random
sampling or model training is used; ranking ties follow corpus order. Source build
requires pypdf 6.x; its patch version can affect extraction and therefore hashes.

## Generate requirements

```sh
.venv/bin/python src/regulation-db/workflows/run_splade.py prepare \
  --case-dir src/industrial-ai-hackathon/cases/dev-rear-lamp \
  --out runs/new-case --team-id jojo-splade-dense --config config.json
.venv/bin/python src/regulation-db/workflows/run_splade.py run \
  --out runs/new-case --flow targeted --budget-usd 12 \
  --key-file /absolute/path/to/private-anthropic-key
```

This sends the product inputs and selected public regulation pages to Anthropic.
Never commit a key. The budget is cumulative across experiments sharing `runs/.api`.
Requests are cached and interrupted ambiguous requests retain their reservation.
Use a new run directory after source changes. Completed outputs are frozen by hash.
The full generation uses the model recorded in its manifest, currently
`claude-sonnet-5-5`. Local image/text and citation checks do not establish complete
legal applicability or completeness.

## Repository benchmark

Copy the frozen `runs/new-case/targeted/submission.json` to
`outputs/predictions.json`. From the repository root:

```sh
python approaches/benchmarking/bench.py jojo-splade-dense \
  approaches/experiments/jojo-splade-dense/outputs/predictions.json \
  ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json \
  --index ../industrial-ai-hackathon/regulations/index.json
```

Commit the experiment, preserved benchmark result and generated leaderboard together.
Pull and integrate the latest remote changes before every push. The source snapshot
is separate from other experiments so future edits do not alter this run's code.

## Measured result

Frozen development run: 395 requirements, 179 reviewed main pages. Page F2: 0.5752; page precision: 0.4070; page recall: 0.6415. Regulation F2: 0.6818. See `results.json` and `outputs/` for the immutable submission, source evidence, decisions, coverage and cost accounting.

Coverage complete: False. This measures citation coverage on the development case, not semantic correctness or held-out generalization. A truncated Claude output triggered one bounded retry with a 32,000-token output limit; completed identical requests were reused. Tests cover retry bounds, cache reuse and budget enforcement. New generation cost including truncated attempts: $11.1852; earlier query planning: $0.017024.


## Run history and review recovery

This is the first completed generation benchmark for this experiment. All 553 proposed requirements received a final decision: 395 keep, 64 drop and 94 unresolved. No requirement was marked unresolved because of budget exhaustion. The unresolved items are omitted from predictions and preserved in the review evidence. Coverage remains incomplete: 2,304 candidates were not reviewed and 282 candidate decisions remain unresolved.

| Run / comparison | Page F2 | Clause F2 | Regulation F2 |
| --- | --- | --- | --- |
| This SPLADE/dense run | 0.5752 | 0.4545 | 0.6818 |
| Earlier separate `jojo-bm25-dense-targeted` experiment | 0.2579 | not recorded | 0.4348 |
| Current leader `devansh-llm-clause-filter` at publication | 0.8442 | 0.6195 | 1.0000 |

The page gain over the earlier experiment is 0.3173, but its missing clause metric prevents a claim of a measured clause gain. This is not a controlled retriever-only comparison: other configuration and extraction differences are present. The current leader remains ahead on all three metrics.

One cached review batch omitted a single requirement ID. `finish_review.py` preserves valid decisions, checks the original generation/input/source hashes, and repairs missing decisions using lossless references to deduplicated source contexts. The original caches are unchanged. The recovery manifest binds the parent manifest, packet outputs and recovery code by hash. This finished within the enforced $12 ceiling; the later $13 authorization was not needed. The conservative shared ledger total is $11.841738, including reused responses; fresh generation cost is $11.185168, plus $0.017024 for earlier query planning.

Recovery command after a stopped generation (use a fresh output directory):

```sh
.venv/bin/python src/regulation-db/workflows/finish_review.py \
  --parent runs/new-case --out runs/recovered-case --budget-usd 12 \
  --key-file /absolute/path/to/private-anthropic-key
```

If the approved budget is exhausted, recovery explicitly marks remaining decisions unresolved and excludes them; it never presents them as approved. The completed run here had no such budget omissions. The local tests cover retrieval fusion/reranking, integration, bounded token retries, cache reuse, budget enforcement, lossless context round-tripping and invalid review decisions (13 tests passed).

Overfitting checklist: query strategy, pool size and reranking head were selected on the single labelled development case and are listed in `risk.json`. The solver never reads expected answers; the separate benchmark does. There is no hard-coded rear-lamp rule/allowlist, but transfer to another product is untested. No held-out robustness claim is made; risk remains **high**.
