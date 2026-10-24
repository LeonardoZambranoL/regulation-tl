# Gold self-check

This experiment verifies the benchmark by using the official `dev-rear-lamp`
sample solution as both the prediction and the gold answer. It is a sanity check,
not a retrieval or requirement-extraction approach.

## How it works

1. The benchmark reads the same `expected.json` file for both inputs.
2. The official challenge validator checks both inputs, including regulation names
   and versions when the regulation index is supplied.
3. The official local scorer compares their regulation and page citations.
4. The benchmark calculates F2, saves the results, and updates the leaderboard.

Identical inputs should produce precision, recall, F1, and F2 of **1.0** at both
levels. The recorded run matched all **4 regulations** and **53 distinct page
citations**.

## Setup and run

Requires Python 3.12+ and the challenge repository next to this repository.
Run these commands from the `regulation-tl` repository root:

```powershell
python -m pip install -r approaches/benchmarking/requirements.txt
python approaches/benchmarking/bench.py gold-self-check ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

This experiment uses the shared benchmark implementation and dependencies; it
requires no separate code, model, or configuration.

## Outputs

- [results.json](results.json): latest run, including scores and input fingerprints.
- `benchmark-results/<run-id>.json`: individual saved runs.
- [Score history](../../leaderboard.json): all benchmark runs.
- [Leaderboard](../../LEADERBOARD.md): generated rankings.

Rerunning appends a new history entry and updates this experiment's latest result.

## Limitations

The perfect score is expected because the gold answer is supplied as the
prediction. It does not measure performance on unseen inputs or verify semantic
requirement matching. This check confirms the identical-input scoring path; it
does not establish correctness for every possible prediction.
