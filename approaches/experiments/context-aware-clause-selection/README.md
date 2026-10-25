# Context-aware clause selection with non-shall recovery

This independent A/B/C experiment tests whether better source-paragraph selection improves requirement-level F2 while
holding regulation discovery, the strict atomic writer, and the soft ranker fixed. It reuses those implementations
directly from `devansh-toolkit`; it does not fork their prompts or thresholds.

## Variants

| Variant | Candidate selection | Writer/ranker |
|---|---|---|
| A | Existing ranked submission, copied without inference | Existing strict writer + ranker output |
| B | Existing `shall|must` candidates with hierarchical contextual classification | Unchanged |
| C | B plus exhaustive generic non-`shall` normative discovery | Unchanged |

The fixed regulation selector is `combined`, identical to the current best pipeline. Context includes parent headings,
scope, relevant definitions, nearby clauses, resolved paragraph/annex references, and exact source provenance. Missing
references are logged, never fabricated. Conditional and uncertain obligations are retained for recall.

## Run

From the repository root, after placing your own `ANTHROPIC_API_KEY` in the git-ignored `.env`:

```powershell
.venv\Scripts\python -m pip install -r approaches\experiments\context-aware-clause-selection\requirements.txt
.venv\Scripts\python approaches\experiments\context-aware-clause-selection\run.py
```

That one command freezes A/B/C predictions for both cases, validates them, runs citation and requirement judges, then
writes per-item diagnostics and `evaluation/<case>/comparison.json`. Useful stage controls:

```powershell
# Gold-blind generation only
.venv\Scripts\python approaches\experiments\context-aware-clause-selection\run.py --stage infer

# Evaluation only; refuses predictions changed since the frozen manifest
.venv\Scripts\python approaches\experiments\context-aware-clause-selection\run.py --stage evaluate
```

Configuration lives in `config.json`: context depth, neighbor count, reference resolution, maximum context, recovery
families, model effort, and worker count are explicit. Contextual responses are cached under this experiment's ignored
`.cache/` by model, effort, complete prompt, and schema. Shared writer/ranker responses use their existing prompt-keyed
cache. Trace files record model IDs, prompt/config/source hashes, selected regulations and versions, unresolved
references, stage decisions, conditional/uncertain counts, cache hits, token usage for new calls, errors, and incomplete
processing. Provider pricing is not hard-coded, so monetary cost is reported unavailable; token counts are the durable
cost record. Cached runs reproduce the same files.

The experiment reads the clean clause-level JSON in `data-ingestion/clauses/`; it does not parse PDFs and does not
require PyMuPDF. The shared corpus loader imports PyMuPDF lazily only for experiments that explicitly request PDF input.

During inference, live progress bars cover product modeling, contextual-classification batches, strict-writer batches,
and soft-ranker batches. Each bar shows the cumulative estimated API cost and local cache hits. Per-stage tokens,
responses, cache hits, and estimated USD are written after every response to
`outputs/<case>/variant-<b|c>-costs.json` and copied into the trace. Before processing, the script prints the configured
model for every stage, and each progress bar repeats its model. All four stages use `claude-sonnet-5-5`. Estimates use
the public Sonnet 5.5 standard-mode rates recorded in `config.json` ($2/M input, $10/M output, $2.50/M cache write,
$0.10/M cache read, verified 2026-10-24),
and are estimates rather than invoices. Locally cached responses add $0 to the current run.

The post-freeze `req_judge.py` evaluator remains `claude-opus-5-5`, matching the repository's shared evaluator and
preserving comparability with the baseline scores. The startup model plan labels it separately from inference.

For a future case that has no cached Variant A baseline, run `--variants b c --cases <case-id>`; B and C accept any
case directory containing `spec.md`, while A intentionally means the existing frozen best baseline.

## Evaluation and diagnostics

The answer key is never passed to inference. Only after every selected prediction is frozen does evaluation call the
official validator, `bench.py`, and the one-to-one semantic `req_judge.py`. Diagnostics attribute misses to regulation
selection, candidate discovery, contextual rejection, writer omission, ranker removal, or possible partial/matcher
failure. Unmatched outputs are categorized conservatively; absence from gold is explicitly not proof of invalidity.

The generated comparison reports requirement P/R/F2 and count, page P/R/F2, clause P/R/F2, regulation recall,
conditional/uncertain counts, recovery matches, and gained/lost expected IDs. It directly identifies the highest
requirement-F2 variant. Holdout ACPE includes broader whole-regulation administrative obligations, so it is supporting
evidence rather than a like-for-like primary score.

## Status and limitations

Implementation is complete, but no inference or evaluation has been run in this change. Therefore no result or
adoption claim is made. Parsed clause hierarchy can miss visual headings and complex table inheritance. Reference
resolution currently handles explicit same-regulation paragraph and annex labels; external or ambiguous references
remain logged. The product model can use markdown evidence for an exploded view, but not inaccessible image pixels.

## Result history

No runs yet. Baseline reference: dev requirement P 0.474 / R 0.779 / F2 0.690; holdout P 0.265 / R 0.468 / F2
0.406. When results are produced, report page F2, clause F2, and regulation F2 against the previous run and current
leader, then update this section and `risk.json` before pushing.
