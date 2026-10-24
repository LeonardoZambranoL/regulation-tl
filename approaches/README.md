# Approach experiments

Test and rank approaches here. Each experiment gets its own folder under
`experiments/` with its code,
dependency manifest/lockfile, configuration, prompts, and README with setup and
run commands. Record runtime/model versions and seeds. Do not commit secrets or
virtual environments. Shared data may be referenced; document paths and versions.

```text
approaches/
  benchmarking/
    bench.py                       # Shared evaluator; Python 3.12+, jsonschema
    requirements.txt               # Benchmark dependencies
    challenge_tools/               # Official scorer, validator, schemas, and license
  leaderboard.json                 # Score history: one object per run
  LEADERBOARD.md                    # Generated ranking
  experiments/
    001-example/
      README.md
      requirements.txt               # Or another dependency manifest + lockfile
      src/
      config.json
      outputs/predictions.json
      results.json                   # Latest benchmark result
      benchmark-results/<run-id>.json # Preserved result for every run
```

Use a unique lowercase experiment name with letters, digits, hyphens, or
underscores, starting with a letter or digit. The name identifies its folder
under `approaches/experiments/`.
Create a new experiment for each meaningful variant.

Each approach must include its own `README.md` explaining **what it does and how
it works**: its objective, the method or pipeline, key design choices, inputs and
outputs, and how to install dependencies and run it. Include any assumptions or
limitations so others can understand and reproduce the approach.

## Benchmark saved predictions

Run from the repository root:

```powershell
python -m pip install -r approaches/benchmarking/requirements.txt
python approaches/benchmarking/bench.py 001-example approaches/experiments/001-example/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json
```

Inputs: **approach name**, **prediction JSON path**, **gold/sample JSON path**.
Relative input paths resolve from the current working directory. Outputs always
land under approaches/. No retrieval, experiment code, or models are run.
The official challenge scorer is bundled in `benchmarking/challenge_tools/score_local.py`,
so the original challenge checkout is not needed at runtime.

Both files must pass the official challenge validator. They require a JSON object
with team_id, case_id, and requirements (bare lists are not accepted):

```json
{
  "team_id": "my-team",
  "case_id": "dev-rear-lamp",
  "requirements": [
    {
      "id": "R-1",
      "text": "The requirement text.",
      "source": {
        "regulation": "UN R48",
        "version": "9.3.0",
        "page": 12,
        "paragraph": "6.7.4.1"
      }
    }
  ]
}
```

Each requirement needs a unique nonempty id, nonblank text (at most 2000
characters), and a source with nonempty regulation and version strings and a
positive integer page. Paragraph is an optional string, not null. Files are
limited to 5 MiB and 5000 requirements by the official tool. Text and IDs are
validated but not scored. Empty predictions score zero; empty gold is rejected.
Prediction and gold case_id must match.

Both files are validated before any score is saved. To also check regulation
names and version labels against the challenge index, append:

```powershell
--index ../industrial-ai-hackathon/regulations/index.json
```

Without --index, schema and duplicate-ID checks still run; the CLI reports that
regulation/version membership was not checked. Results record validation status,
validator/schema checksums, and the optional index checksum.

## Scores

Calls the unmodified challenge `score_local.py` tool, then adds F2 to its results:

- Regulation: compares distinct regulation names.
- Page: compares distinct (regulation, version, page) citations. A matching
  normalized paragraph in the same regulation/version also counts, even if the
  page differs. Precision counts correct submitted pages; recall counts covered
  gold pages. Duplicate citations do not inflate counts.

Paragraph normalization ignores case, common punctuation, whitespace, and leading
labels such as paragraph. Internal number separators remain significant.

**F2 = 5 * precision * recall / (4 * precision + recall)**, or zero when the
denominator is zero. Scores range from 0 to 1 and emphasize recall.

This evaluates citation coverage, **not semantic correctness of requirement
text**. A correct citation does not prove its requirement text is correct.

## Results and leaderboard

Each successful run prints JSON and automatically:

1. Saves the latest result to `experiments/<name>/results.json`.
2. Preserves that run in `experiments/<name>/benchmark-results/<run-id>.json`.
3. Appends the result to `leaderboard.json`, retaining previous runs.
4. Generates [LEADERBOARD.md](LEADERBOARD.md) from the JSON history.

Results include a run ID, UTC timestamp, input paths and SHA-256 fingerprints,
evaluator version, scorer checksum, ranking metric, and
metrics.page_level/metrics.regulation_level with the official precision, recall,
F1, n_submitted, n_expected, n_matched fields, plus F2.

The leaderboard shows the **latest run per approach** for each gold solution and
evaluator version. **Regulations matched** shows the number of correctly cited
distinct regulations out of the gold total (for example, `4/4`). This count does
not penalize extra regulations; regulation F2 accounts for those through precision.
The count comes from `metrics.regulation_level.n_matched` and `n_expected` in the
saved JSON. **Regulations included** shows the total number of distinct regulations
cited by the approach (`n_submitted`), including incorrect ones. For example,
`4/4` matched with `6` included means all four expected regulations were found,
plus two extra regulations.

Approaches are grouped by gold solution and
evaluator version, ranked by **page F2**, then regulation F2, descending. Equal
scores share a rank. Different gold fingerprints/evaluator versions get separate
tables. JSON whitespace and object-key order do not affect fingerprints; list
order and input values do.

Commit history, individual results, and the generated leaderboard together. Run
benchmarks sequentially in a shared checkout. Invalid input exits without adding
a score; record failed experiment findings in the experiment README.
