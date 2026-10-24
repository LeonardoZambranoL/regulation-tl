# devansh-llm-clause-filter-writer-ranked

Owner: Devansh. **The best writer output with a soft final check: Claude rates each requirement 1-5 and only the
"certainly not" ones (and repeats) are removed.** Follow-up to devansh-llm-clause-filter-writer-refined, whose hard
yes/no verifier lost as many real matches as false ones. Method: [EXPLAIN.md](EXPLAIN.md); risk: `risk.json`.

## Run (spends your own Anthropic credits; cached)

```bash
bash approaches/experiments/devansh-llm-clause-filter-writer-ranked/run.sh      # from the repo root
```

## Results

See `results.json`, `approaches/req_scores.json`, the dashboards and HISTORY.md in devansh-toolkit.
Baseline (writer): requirement F2 0.676 dev, 0.390 holdout-acpe.

## Limitations

- Even a 1 rating can be wrong; the cut-off is not tuned on any case.
- Removes items only; never rewrites them.
