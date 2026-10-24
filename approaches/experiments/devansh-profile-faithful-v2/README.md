# devansh-profile-faithful-v2

Owner: Devansh. **devansh-profile-faithful with two generic precision fixes, every LLM answer regenerated from scratch.**
Method: [EXPLAIN.md](EXPLAIN.md); risk: `risk.json`.

Run (your own Anthropic credits): `bash approaches/experiments/devansh-profile-faithful-v2/run.sh` from the repo root.
Held-out case: `bash approaches/experiments/devansh-profile-faithful-v2/final.sh <case-id>`.

## Why

devansh-profile-faithful (platform F2 69.7%, P 43.5%) loses mostly on precision: 195 of 359 dev requirements match
nothing. An error analysis of its output, by citation category rather than by specific paragraph, found:

| prediction cited at | dev matched / submitted | holdout matched / submitted |
|---|---|---|
| numbered main-text paragraph | 143 / 254 | 49 / 129 |
| Annex paragraph | 20 / 63 | 0 / 77 |
| **Table / Figure / Appendix label** | **1 / 42** | **1 / 29** |

The experts' lists cite the numbered clause that imposes a table ("shall meet the requirements in Table 7"), and the
writer was also splitting each table cell into its own requirement. (Disclosure: the holdout column was printed during
the same analysis, so holdout-acpe is not fully unseen for this rule; see `risk.json`.) A second pattern: the same
limit stated in the main text, in a table and again in an appendix, which a one-to-one judge counts once at most.

## Method (changes vs devansh-profile-faithful)

1. **Fresh answers, no reused cache.** New `LLM_CACHE_DIR` env var in the toolkit (`corpus.py`); `run.sh` / `final.sh`
   point it at this folder's git-ignored `.cache/`. Profile, classifier, writer, ranker and merge were all generated
   for this experiment. Prompts were written once; the pipeline was run once and scored once (no iteration on dev).
2. **Skip table / figure / appendix clauses** as candidates (`filter.exclude_labels`, dev 1,599 -> 1,517 candidates).
   Annex paragraphs stay.
3. **Restatement merge** (`refine --merge-restatements`): per regulation, Claude groups items that state exactly the
   same obligation; the copy at the numbered main-text paragraph (else the earliest page) is kept. Written to be
   conservative (different values, categories, voltage systems, or a test pointer vs its details are not merged).

Ideas considered and not used: self-consistency voting and confidence-gated applicability (both are versions of the
earlier verifier / voting runs in HISTORY.md, which cut true positives as fast as false ones); dropping parent
clauses (no generic rule separated them from matched pointer clauses like "shall meet the requirements in Table 7").

## Results (2026-10-25, local requirement judge, scored once)

| case | version | submitted | TP | P | R | F1 | F2 |
|---|---|---|---|---|---|---|---|
| dev-rear-lamp | profile-faithful | 359 | 164 | 0.457 | 0.863 | 0.597 | 0.733 |
| dev-rear-lamp | **v2** | 334 | 161 | **0.482** | 0.847 | **0.615** | **0.736** |
| holdout-acpe | profile-faithful | 235 | 50 | 0.213 | 0.532 | 0.304 | **0.409** |
| holdout-acpe | **v2** | 177 | 45 | **0.254** | 0.479 | **0.332** | 0.407 |

Citation level (bench.py), F2 page / clause / regulation: dev 0.853 / 0.740 / 1.0 (was 0.845 / 0.744 / 1.0);
holdout 0.476 / 0.491 / 0.833 (was 0.455 / 0.478 / 0.833).

**Verdict: not adopted as the final.** Precision and F1 rose on both cases, but requirement F2 changed by +0.003 (dev)
and -0.002 (holdout). That is within run-to-run noise: regenerating every answer moves the holdout true positives by
about 5, and only 1 holdout true positive came from a table clause. The rule set before the run (better on both
cases) is not met on F2. The restatement merge dropped only 0 (dev) and 2 (holdout) items, so in practice it does
nothing. Expected platform score of `outputs/submission-dev-rear-lamp.json` (local minus ~3.7 points): F2 about 69.9%,
P about 44.5%, R about 81%. That is level with profile-faithful's 69.7%, which stays the recommended upload.

## Limitations

- One labelled case plus one holdout; differences of ±0.005 F2 cannot be told apart from LLM sampling noise.
- If a future answer key cites table rows, those requirements are now missing.
- Holdout precision is understated: R10 (EMC) is selected but absent from the holdout key (most holdout false positives).
- `config.json` keys `refine` and `llm_cache_dir` document the run; `run.sh` / `final.sh` pass them as flags / env.
