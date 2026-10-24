# regulation-tl: team rules for Claude (and humans)

Certivity hackathon: from a product spec to the UN Regulation requirements it must fulfil. See README.md.

## Git: always pull before you push

- Run `git pull` (or `git pull --rebase`) right before every `git push`, and before you start changing files.
- Re-read the repo's current structure after pulling (`ls`, `approaches/README.md`) and follow it; teammates push often.
- Never force-push. If a pull conflicts, resolve it keeping both sides' work; for `approaches/leaderboard.json` keep
  every run from both sides, then re-run `python approaches/benchmarking/dashboard_rows.py` and re-render the
  leaderboard by re-running the benchmark or keeping the newer `LEADERBOARD.md`.
- Optional safety net: `git config core.hooksPath .githooks` enables a pre-push hook that refuses to push when the
  branch is behind `origin`.

## Where things go

- Shared data, do not change without asking: `regulations/` (PDFs), `data-ingestion/` (text, clauses).
- Each person / variant works only in its own `approaches/experiments/<name>/` (lowercase). Do not edit someone else's
  experiment folder.
- Every experiment needs `README.md` (what it does, how it works, how to run, assumptions, limitations),
  `config.json` (`"name"` = one-line description), `risk.json` (overfitting declaration, see
  `approaches/dashboard/README.md`) and `outputs/predictions.json`.
- Shared tools: `approaches/benchmarking/bench.py` (scores + leaderboard), `approaches/benchmarking/dashboard_rows.py`
  (dashboard data).

## Benchmark and dashboard (standard flow)

1. `python approaches/benchmarking/bench.py <name> approaches/experiments/<name>/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json`
2. `python approaches/benchmarking/dashboard_rows.py`
3. Pull, commit (experiment folder + `approaches/leaderboard.json`, `LEADERBOARD.md`, `dashboard/leaderboard_rows.json`), push.
4. Update the comparison dashboard (https://claude.ai/artifact/TEW2x5Fhkj8DHgtmfnLLTV) following
   "For Claude: how to update the dashboard" in `approaches/dashboard/README.md`.

## Avoid overfitting

There is one labelled case; the ranking uses a held-out one. Do not tune thresholds or sizes on dev scores without
declaring it in `risk.json`; never read `expected.json` outside the benchmark. Prefer general rules and prompts.

## Secrets

API keys go in a git-ignored `.env` (repo root or the experiment folder), never in code, configs or commits. Check
`git diff --cached` for keys before committing.
