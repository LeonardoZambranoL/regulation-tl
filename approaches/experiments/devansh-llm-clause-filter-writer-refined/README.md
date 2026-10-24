# devansh-llm-clause-filter-writer-refined

Owner: Devansh. **The current best (`devansh-llm-clause-filter-writer`) plus a verifier and duplicate removal, aimed
at the platform's one-to-one requirement judge.** See [EXPLAIN.md](EXPLAIN.md) for the method in plain words and
technically, `risk.json` for the declared overfit risk.

## Why

The platform pairs every submitted requirement with at most one expert requirement that states the same obligation
(same scope, condition, constraint), and scores precision and recall on those pairs. On the dev case 137 of the 181
unmatched writer requirements come from paragraphs the experts did not list, so extra items are the main loss.
Repeats can never be matched twice.

## Run (spends your own Anthropic credits; answers are cached)

```bash
bash approaches/experiments/devansh-llm-clause-filter-writer-refined/run.sh      # from the repo root
```

It refines both cases, benchmarks citations, judges the requirement level, rebuilds the dashboard data, then pulls,
commits this experiment and pushes.

## Results

In `results.json`, `approaches/req_scores.json` and the dashboards (requirement-level columns). Compare with
devansh-llm-clause-filter-writer: req F2 0.676 on dev, 0.390 on holdout-acpe.

## Limitations

- The verifier can drop real obligations (recall risk); the decision to adopt it is made on both cases.
- Requirement text comes from the writer; this step only removes items, it never rewrites them.
