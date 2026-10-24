# devansh-llm-clause-filter-writer-ranked

Owner: Devansh. **The best writer output with a soft final check: Claude rates each requirement 1-5 and only the
"certainly not" ones (and repeats) are removed.** Follow-up to devansh-llm-clause-filter-writer-refined, whose hard
yes/no verifier lost as many real matches as false ones. Method: [EXPLAIN.md](EXPLAIN.md); risk: `risk.json`.

## Run (spends your own Anthropic credits; cached)

```bash
bash approaches/experiments/devansh-llm-clause-filter-writer-ranked/run.sh      # from the repo root
```

## Results (2026-10-24): adopted, then superseded by [devansh-writer-faithful-ranked](../devansh-writer-faithful-ranked/)

| local requirement judge | requirements | P | R | F1 | F2 |
|---|---|---|---|---|---|
| dev, writer (baseline) | 328 | 0.448 | 0.774 | 0.567 | 0.676 |
| **dev, writer + ranker** | **312** | **0.474** | **0.779** | **0.590** | **0.690** |
| holdout-acpe, writer (baseline) | 188 | 0.234 | 0.468 | | 0.390 |
| **holdout-acpe, writer + ranker** | **166** | **0.265** | 0.468 | 0.338 | **0.406** |

Ratings (dev): 1: 12, 2: 90, 3: 54, 4: 101, 5: 67; only the twelve 1s and four repeats were dropped, without losing a
match. Better on both cases, so this is the file to upload: `outputs/predictions.json` (validate first). Other cut-offs
are listed in `outputs/*-refine-report.json` but were not scored, to avoid choosing one on the answer key.


See `results.json`, `approaches/req_scores.json`, the dashboards and HISTORY.md in devansh-toolkit.
Baseline (writer): requirement F2 0.676 dev, 0.390 holdout-acpe.

## Limitations

- Even a 1 rating can be wrong; the cut-off is not tuned on any case.
- Removes items only; never rewrites them.
