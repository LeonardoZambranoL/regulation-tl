# Static clause catalogue with shared Gemini embeddings

This experiment reuses the fixed shared regulation corpus and its existing vectors.
It removes the previous 60-page-packet cutoff and the generic cross-encoder. Every
clause in every included or uncertain regulation is assessed, followed by an
independent verification of each proposed obligation. Neither inference nor
catalogue construction reads reference answers.

## Method

1. Load `data-ingestion/clauses/*.json` in the shared loader's sorted order. Check
   **every** regulation, version, first page and normalized paragraph against
   `data-ingestion/embeddings/gemini-embedding-2-preview_d768_n26769.npz`.
   Reject alignment failures, zero vectors and nonfinite values. Normalize the
   supplied 26,769 vectors (768 dimensions, float16 storage) in float32.
2. Build a product-independent source catalogue with ancestor clauses, resolvable
   within-regulation paragraph references, unresolved references and source hashes.
   Save this reusable representation under `.cache/`. No paid corpus embedding or
   model training occurs. Full source and embedding fingerprints bind each run.
3. Rank source passages lexically against the product specification, take eight
   source seeds, and use their existing Gemini document vectors for maximum cosine
   similarity. Fuse lexical and semantic ranks with RRF k=60. This is **document
   similarity expansion**, not direct Gemini query embedding. No vectors from
   incompatible models are compared and no Google API call is made. This ranking
   only orders work; it never discards a clause.
4. Claude Sonnet `claude-sonnet-5-5` reads the product and source-derived profiles
   for every regulation. Require one include/exclude/uncertain decision per
   regulation and a mechanically validated quote from its supplied profile.
   Explicit source consolidation evidence can avoid duplicate alternative routes.
   There is no product-specific regulation allowlist. Uncertain regulations remain.
5. Assess **all** clauses in selected regulations, in source order within each
   regulation, in batches of at most 24 records / 60,000 target characters. A
   single oversized clause is kept whole; context is not silently truncated.
   Four concurrent requests share one locked cost ledger. Every target receives
   relevant/irrelevant/unresolved, and relevant targets can emit several atomic
   requirements. Ancestors and explicit references are attached once per batch.
6. Validate exact source quotations and maximum requirement length. Independently
   verify proposals in batches of 24 with their complete source records and context.
   Only kept proposals enter predictions. Remove only exact same-source/text
   duplicates; preserve conditions and distinct obligations. Export provenance,
   decisions, missing coverage, cost accounting and immutable output hashes.

The catalogue contains reusable **source clauses**, not a fully expert-approved
catalogue of legal requirements. Product-independent semantic extraction of all
26,769 clauses would require an additional project and budget. This implementation
reuses the supplied structural extraction and caches exact model requests.

## Setup and run

Python 3.12; from this experiment directory:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python src/run.py \
  --repo /absolute/path/to/regulation-tl \
  --spec /absolute/path/to/case/spec.md --case-id dev-rear-lamp \
  --out runs/new-run \
  --index /absolute/path/to/industrial-ai-hackathon/regulations/index.json \
  --api-cache /private/path/to/shared-api-cache \
  --key-file /private/path/to/anthropic-key --budget-usd 29
```

The ceiling is cumulative for the supplied API cache, including earlier runs and
ambiguous request reservations. The development run enforces $21, leaving room
under the approved $29 shared ceiling for the unseen case. The initial unseen passes used the earlier $23 and $26 ceilings. Their budget-limited reports are retained separately, and the final continuation reuses successful cached requests under the $29 ceiling. The $26 pass left 192 source clauses unresolved solely for lack of budget. Extraction reserves
$1.50 by default for verification (`--verification-reserve-usd` makes this allocation explicit without changing the overall ceiling). Budget failures remain explicitly unresolved;
they never become approved requirements. Exact cached requests cost nothing new.
A bounded retry handles truncated output or malformed decision IDs. An interrupted
request may be recovered once under a distinct cache key while retaining the full
original reservation; an ambiguous replacement is not retried blindly.

To resume an unfrozen interrupted run use the same arguments; unchanged requests
are cached. After implementation changes use a new output directory. Frozen runs
are not overwritten. Product specifications and selected public regulation text
are sent to Anthropic. Images are not used by this text-only variant.

## Benchmark and validation

Freeze both the development and unseen-case outputs before scoring them. Use the
same source and settings for `approaches/benchmarking/cases/holdout-acpe/spec.md`.
Publish its predictions separately as `outputs/predictions-holdout-acpe.json`.
Run the repository's `approaches/benchmarking/bench.py` for each case and regenerate
the dashboard with both gold paths. Only those evaluation tools open gold files.

Local tests cover lossless batching, context deduplication, ranking without
exclusion, incomplete/duplicate decisions, cached retries and budget enforcement.
The official schema validator checks predictions against the regulation index.
These structural checks do not establish legal correctness.

## Limitations and overfitting

- Shared clause splits are drafts. Tables, diagrams and ambiguous extraction may
  need PDF review. A multi-page clause is cited at its first page; its full page
  span is retained in evidence, but no exact quote-to-page alignment is available.
- Scope filtering remains a possible recall bottleneck. A valid scope quotation
  does not prove the model's applicability reasoning is correct.
- The NPZ metadata establishes clause identity/order but contains no upstream text
  hashes. Its original embedding-input text cannot be independently proven from
  that file. The current file and clause text hashes are recorded for future runs.
- Paragraph references are resolved conservatively within the same regulation;
  implicit, annex-specific and cross-regulation links may remain unresolved.
- Architectural decisions follow inspection of a previous development result.
  Risk is **high**. No thresholds are tuned on this new run and no rules are
  tuned on the unseen case. This is not an isolated embedding-model comparison.

The shared LanceDB importer was published while these frozen-source runs were already executing. This variant reads the identical NPZ directly; it does not write to the shared vector database. Changing the storage backend was deferred to preserve the running experiment.

## Results

Both final predictions were frozen before any new benchmark was read. No inference changes were made after these scores. Scores measure citation coverage, not correctness of requirement text.

| Case | Level | Precision | Recall | F1 | F2 |
| --- | --- | ---: | ---: | ---: | ---: |
| Development | page | 0.590361 | 0.943396 | 0.726249 | 0.842619 |
| Development | clause | 0.326733 | 0.818182 | 0.466981 | 0.628971 |
| Development | regulation | 0.800000 | 1.000000 | 0.888889 | 0.952381 |
| Holdout ACPE | page | 0.101266 | 1.000000 | 0.183908 | 0.360360 |
| Holdout ACPE | clause | 0.137931 | 0.701754 | 0.230548 | 0.386100 |
| Holdout ACPE | regulation | 0.250000 | 1.000000 | 0.400000 | 0.625000 |

**Robust score: 0.772187; rank 4 at publication preparation.** The current Robust leader, `devansh-dynregex-llm-clause-filter`, has 0.804533 (dev page F2 0.766962, clause F2 0.5613, regulation F2 shown below; holdout clause recall 0.842105). Our unseen clause recall is 40/57 = 0.701754 despite complete budget coverage. The held-out gold only covers R175, so precision and F2 there are understated when other regulations are legitimately included. The 1.000000 page recall saturates and does not mean complete clause coverage.

| Development comparison | Page F2 | Clause F2 | Regulation F2 |
| --- | ---: | ---: | ---: |
| jojo-splade-dense | 0.575213 | 0.454545 | 0.681818 |
| devansh-llm-clause-filter | 0.844156 | 0.619469 | 1.000000 |
| devansh-dynregex-llm-clause-filter | 0.766962 | 0.561283 | 0.909091 |
| jojo-static-embeddings | 0.842619 | 0.628971 | 0.952381 |

The previous SPLADE/dense variant had no held-out result, so a previous Robust score is unavailable. The new development result improves both page and clause F2 over that variant; page F2 remains slightly below the development leader, while clause F2 is higher. This is a whole-workflow comparison, not evidence that changing the embedding model alone caused the gain.

**Coverage remains incomplete:** development assessed all 3,478 scoped clauses, with 190 unresolved clause decisions; 500 proposals became 412 keep, 35 drop, 53 unresolved. Holdout assessed all 1,404 clauses, with 108 unresolved clause decisions; 575 proposals became 510 keep, 27 drop, 38 unresolved. Two exact duplicates are removed, leaving 508 held-out requirements. Two development clauses and one held-out clause failed quote/text validation. No final decision is unresolved solely because of the budget. Unresolved proposals are excluded from predictions, not silently approved.

### Run history

| Frozen run | Budget cap | Page F2 | Clause F2 | Regulation F2 | Note |
| --- | ---: | ---: | ---: | ---: | --- |
| holdout-v1 | $23 | 0.727273 | 0.600601 | 0.833333 | Budget-limited intermediate; retained for audit, high risk |
| holdout-v2 | $26 | 0.392157 | 0.398406 | 0.714286 | Budget-limited intermediate; retained for audit, high risk |
| dev-v2 | $21 | 0.842619 | 0.628971 | 0.952381 | Final; high declared risk |
| holdout-v3 | $29 | 0.360360 | 0.386100 | 0.625000 | Final; high declared risk |

### Cost

Total shared ledger: **$25.674174 completed + $0.151672 uncertain reservation = $25.825846**, under the authorized $29 total ceiling. Remaining conservative allowance: $3.174154. Increment above the previous $11.841738 ledger baseline: $13.984108. This includes abandoned/budget-limited attempts and preserves the reservation for an interrupted request; it is not a provider invoice. No embedding API calls. OpenAI subscription usage is not converted to dollars here.



The development source snapshot is preserved in `outputs/dev/source-code/` and matches its original manifest. The current runner adds only an explicit verification-reservation CLI setting and validation; the default remains $1.50. Inference prompts, scope rules, source construction, ranking and assessment/verification settings are identical across cases. This budget-interface adjustment was made before reading either new benchmark result.
