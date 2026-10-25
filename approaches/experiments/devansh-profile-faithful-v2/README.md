# devansh-profile-faithful-v2 (FINAL, platform F2 72.7%)

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

**Local verdict (before upload): not adopted.** Precision and F1 rose on both cases, but local requirement F2 changed by
only +0.003 (dev) and -0.002 (holdout), which is within run-to-run noise. The restatement merge dropped only 0 (dev) and
2 (holdout) items, so in practice it does nothing; the gain comes from skipping table / figure / appendix clauses.

## Platform score (uploaded 2026-10-25 00:57 CEST, dev rear lamp): NEW BEST, now the FINAL

Requirements P **47.6%** / R **83.7%** / F1 **60.7%** / F2 **72.7%** (profile-faithful: P 43.5 / R 82.1 / F1 56.8 /
F2 69.7). Pages P 61.7% / R 94.3% / F1 74.6%; regulations 100%. The platform improved on precision AND recall, by more
than the local judge predicted: the local judge read 0.9 points high this time (0.736 vs 72.7%) against 3.7 points
before, so its gap is not constant and small local differences should not decide adoption. Upload:
`outputs/submission-dev-rear-lamp.json`. Held-out case: `bash approaches/experiments/devansh-profile-faithful-v2/final.sh <case-id>`.
Caveat: on holdout-acpe the local judge shows no F2 gain (0.407 vs 0.409), with higher precision and lower recall.

## Held-out case: heldout-front-bumper (2026-10-25)

`bash approaches/experiments/devansh-profile-faithful-v2/final.sh heldout-front-bumper` -> **upload
`outputs/submission-heldout-front-bumper.json`** (301 requirements, team-11, validate --strict OK). Regulations
selected: UN R48 (166 requirements), R10 (62), GTR 9 (39), R127 (25), R42 (9); R13H was selected but kept no
requirement. The ranker was less sure than on dev (ratings 1/2/3/4/5: 64/151/83/57/15), with 5 restatements merged.
No answer key, so no score.

## Limitations

- One labelled case plus one holdout; differences of ±0.005 F2 cannot be told apart from LLM sampling noise.
- If a future answer key cites table rows, those requirements are now missing.
- Holdout precision is understated: R10 (EMC) is selected but absent from the holdout key (most holdout false positives).
- `config.json` keys `refine` and `llm_cache_dir` document the run; `run.sh` / `final.sh` pass them as flags / env.
