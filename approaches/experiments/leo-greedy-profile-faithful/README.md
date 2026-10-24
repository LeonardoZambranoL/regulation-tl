# leo-greedy-profile-faithful

Owner: Leo. This is a greedy variation of devansh-profile-faithful-v2. It inherits v2's product profile, combined
regulation selection and Table / Figure / Appendix candidate exclusions. If any remaining seed clause makes a page
relevant, it expands to every parsed clause touching that page and emits exactly one requirement per distinct clause.
The expanded page can therefore include a table-labelled clause even though table labels cannot seed page selection.

See [EXPLAIN.md](EXPLAIN.md) for the precise method and `risk.json` for the overfitting declaration.

## Run

From PowerShell at the repository root, after installing `approaches/experiments/devansh-toolkit/requirements.txt` and
supplying your own `ANTHROPIC_API_KEY` in a git-ignored `.env`:

```powershell
python approaches/experiments/leo-greedy-profile-faithful/run.py
```

By default, the run processes only dev-rear-lamp. Pass --case holdout-acpe to run the ACPE holdout case, or --case both
to run both. Each case writes predictions plus a page-expansion report. The runner uses Claude Sonnet 5.5 and a
Sonnet-specific cache, then benchmarks selected cases unless --skip-benchmark is supplied. It prints elapsed time and
live API token usage/cost after each Claude response, then a final total. Cost uses Sonnet 5.5 standard global list
rates; responses served by a fallback model may have a different price.

The v2 rank/drop and restatement merge are omitted because either can remove entries and violate one output per
expanded clause. The exporter fails instead of silently truncating if expansion exceeds the official 5,000-requirement
limit.

## Results

Not run yet. The checked-in outputs/predictions.json is an empty, schema-shaped placeholder and must be replaced by a
real run before reporting results or pushing this experiment. The v2 Table / Figure / Appendix exclusion was selected
from error analysis that also examined holdout citations; this variant inherits that declared holdout exposure from
v2. Whole-page expansion may also put those labels back into the output once another clause on their page is selected.

The displayed price basis is Anthropic's [Claude Sonnet 5.5 API pricing](https://www.anthropic.com/claude-sonnet-5-5):
$2/MTok input, $10/MTok output, $0.10/MTok cache reads, and $2.50/MTok cache writes. The runner reports API token
usage for calls made in the current process; cached responses do not add spend.

When results exist, record page F2, clause F2 and regulation F2 for both cases here, along with comparison to this
experiment's previous run and the current leader.
