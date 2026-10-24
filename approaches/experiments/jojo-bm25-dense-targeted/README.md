# jojo-bm25-dense-targeted

A no-training requirement-extraction workflow by Jojo. This is the **targeted** variant.
It derives atomic, source-cited engineering obligations from a product specification,
product image and the supplied base-version regulation PDFs.

## Method

1. Claude reads the specification and product image, recording facts, unknowns and search queries.
2. A shared scope pass examines the title and first three pages of every base regulation.
   Clearly incompatible regulations are excluded; conditional and uncertain ones are retained.
3. Union the top six BM25 and dense hits for each generated product query; follow resolved references to depth two and inspect at most 32 three-page packets, including opening pages of retained regulations. Deferred pages remain explicitly unreviewed.
4. Claude reads full source text, governing ancestor clauses and original images of main pages.
   Every machine-detected candidate must receive an included/excluded/unresolved decision.
5. The runner verifies candidate coverage, source pages and verbatim text quotes. One repair
   call is allowed for structural/evidence errors. It deduplicates identical text and reviews
   applicability, conditions and duplicates in batches of 35 requirements. If the cost
   ceiling stops review, remaining drafts are marked unresolved and excluded from submission.
6. The official validator and base-page checks run before the submission is frozen by SHA-256.

Both variants use the same prompts, source corpus and model (`claude-sonnet-5-5`).
Dense retrieval uses local CPU `BAAI/bge-small-en-v1.5` with FastEmbed 0.7.4,
384-dimensional normalized vectors and cosine similarity. BM25 uses SQLite FTS5.
There is **no weight fitting, no training and no RRF in this pipeline**. The included
standalone retrieval module exposes additional experiments; its fitting command is not called.

## Inputs and outputs

Inputs are only `cases/<case>/spec.md`, optional `exploded_view.png`, and source regulations.
The solver does not read `expected.json`. The separate evaluator reads gold only after freezing.
The development case was already known to the team, so this is not an independent blind test.

`outputs/predictions.json` is the frozen submission; `run-report.json` records coverage and
cost estimates. Benchmark results measure regulation/page citation coverage, **not semantic
requirement correctness**. A high page F2 is not proof of complete or correct requirements.

## Reproduce

Python 3.12 (tested with 3.12.14); resolved dependencies are in `requirements.txt`.
From this experiment directory, install dependencies and create the expected source layout:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
git clone https://github.com/Certivity/industrial-ai-hackathon.git src/industrial-ai-hackathon
cd src
../.venv/bin/python regulation-db/tools/build.py --repo industrial-ai-hackathon --out regulation-db/corpus --role all
../.venv/bin/python regulation-db/retrieval/hybrid.py build --role base
../.venv/bin/python regulation-db/retrieval/local_embed.py download
../.venv/bin/python regulation-db/retrieval/local_embed.py corpus
../.venv/bin/python regulation-db/workflows/run.py prepare --case-dir industrial-ai-hackathon/cases/dev-rear-lamp --out regulation-db/workflows/runs/reproduction --team-id YOUR_TEAM_ID --config ../config.json
../.venv/bin/python regulation-db/workflows/run.py run --out regulation-db/workflows/runs/reproduction --flow targeted --budget-usd 12 --key-file /PATH/OUTSIDE/REPO/TO/KEY
```

For a thorough-only run, the retrieval build/download/embedding commands may be skipped.
API requests transmit the product and selected regulation text/page images to Anthropic;
use authorized data and an external credential file. No secrets or API response caches are
included here. A shared durable ledger enforces the configured total ceiling across runs.
No automatic retries are made after a network outcome with uncertain billing.

The challenge checkout must match the source documents recorded in `run-metadata.json`;
updated source releases produce a different experiment. Regenerated SQLite fingerprints can
also differ by machine/path. The solver checks its own current source/input/code fingerprints.
The supplied model/embedding metadata identify the actual run. Model generation has no fixed
seed and may be nondeterministic; exact predictions are preserved for deterministic scoring.

From the regulation-tl repository root, benchmark the saved output:

```sh
python approaches/benchmarking/bench.py jojo-bm25-dense-targeted approaches/experiments/jojo-bm25-dense-targeted/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

Run structural/coverage/budget tests from `src`:

```sh
../.venv/bin/python -m unittest discover -s regulation-db/workflows -p test_workflows.py
```

## Limitations

Scope decisions use opening pages and can miss applicability. Ancestor labels and references
come from heuristic PDF parsing; unresolved references remain explicit. Visual evidence still
needs substantive checking. Candidate coverage does not prove semantic completeness.
Conditional design choices are preserved rather than assumed true. Review batches do not
prove global semantic deduplication. Legacy and successor approval routes can overlap.
The targeted variant intentionally leaves pages unreviewed. `coverage_complete=false` must
be respected. Neither variant is guaranteed to transfer to tomorrow's unseen product.
The old development-case examples and gold are excluded from solver inputs. Improvements
before this run addressed source-context loss and over-rejection of valid conditional duties;
no learned parameter was optimized on the reference answer.

## Budget, incomplete review and experiment scope

The user stopped the thorough baseline and authorized only completion of this targeted
variant, with USD 12 total for this workflow including earlier probes and the unfinished
baseline. Other concurrently running experiments have separate budgets. The 32-packet
limit was fixed before scoring for cost reasons. The targeted run reuses exact cached
responses; its standalone request-cost estimate differs from incremental spending and
from total development spending. `budget-accounting.json` records that distinction.

All 32 extraction packets completed, yielding 353 drafts. The final applicability review
completed for 280 drafts before the spending ceiling prevented the next request. The
remaining 73 drafts are explicitly unresolved, with `review_not_performed=true`, and
are excluded from predictions. Only retained, reviewed requirements are submitted.
This is a **budget-limited partial result**, not a fully reviewed or complete requirement set.
This fallback was implemented before the first score; it does not consult gold.

Review requests send each source page and ancestor clause once per batch, preserving
all requirement-to-source links. `resume_budgeted.py` isolates this workflow's remaining
budget while holding the shared API lock. Ambiguous request outcomes still fail closed.

Packet selection is capped in query order and is not balanced across queries. This can
miss relevant areas. There is no completed thorough-versus-targeted quality comparison.
See `BRIEFING.de.md` for the beginner-oriented workflow overview and next-case runbook.

The frozen partial output was assembled offline from exact saved responses with
`run.py run --flow targeted --cache-only`. This mode makes no HTTP requests, reads
no API key, and never writes the shared cost ledger. Missing final review responses
are explicitly deferred; missing profile/scope/extraction responses stop the run.
The initial paid run stopped at USD 11.909740 including earlier workflow attempts.

## Frozen development benchmark

Page precision is **0.3250**, recall **0.2453** (13 of 53 expected pages),
and F2 **0.2579**. Regulation precision is **0.2857**, recall **0.5000**
and F2 **0.4348**. The submission contains 233 requirements citing 40 distinct
pages from 7 regulations; 95 pages were examined during extraction.

`comparison.json` re-scores saved Devansh outputs read-only with this same evaluator:
`devansh-llm-classifier` scores **0.8442** page F2. The user's condition for
increasing spending was to beat Devansh's best score; this result does not meet it.
No further paid work was started. Total attributable development API cost is
**USD 11.909740**. The completed requests used by this partial output would cost
approximately **USD 4.806540** without the prior cached responses; this is not
a quote for a fully reviewed run. Other experiments are excluded.

The historical evaluator hash differs because Windows used CRLF line endings;
our checkout uses LF. The scorer content is otherwise identical, and read-only
rescoring confirms the comparison. The generated Markdown leaderboard therefore
places our run in a separate evaluator-hash table. No shared evaluator was changed.

This is substantially below the strongest existing approach. The capped,
query-ordered selection and incomplete final review are material limitations.
More spending alone is not demonstrated to fix the coverage gap. The full-scan
baseline was stopped and supplies no completed comparison score.
