# regulation-tl: team rules for every coding agent (and humans)

Read by Codex, Cursor, Copilot, Gemini, Claude Code (via CLAUDE.md) and other agents that follow AGENTS.md.
New here? Setup and the contribution flow are in [CONTRIBUTING.md](CONTRIBUTING.md).

Certivity hackathon: from a product spec to the UN Regulation requirements it must fulfil. See README.md.

## Git: always pull before you push

- Run `git pull` (or `git pull --rebase`) right before every `git push`, and before you start changing files.
- Re-read the repo's current structure after pulling (`ls`, `approaches/README.md`) and follow it; teammates push often.
- Never force-push. If a pull conflicts, resolve it keeping both sides' work; for `approaches/leaderboard.json` keep
  every run from both sides, then re-run `python approaches/benchmarking/dashboard_rows.py` and re-render the
  leaderboard by re-running the benchmark or keeping the newer `LEADERBOARD.md`.
- Enable the hooks once per clone: `git config core.hooksPath .githooks`. The pre-push hook refuses to push when the
  branch is behind `origin`, or when the push changes an experiment whose current dev result has no unseen-case run
  (see "Benchmark and dashboard").

## Credits: your own keys, your own experiments

- Run only **your own** experiments, with **your own** API keys (your git-ignored `.env`). Never run, re-run or
  re-benchmark-by-re-generating a teammate's experiment, and never use another person's key, even if one is lying
  around in a shared folder: each person pays for their own algorithm's runs.
- When a teammate's experiment lacks a score (e.g. no unseen-case run), leave it: tell them, do not run it for them.
- The shared automation spends nobody's credits: the GitHub Action and the dashboard sync only re-score predictions
  files that were already pushed (no model or API calls).

## Where things go

- Shared data, do not change without asking: `regulations/` (PDFs), `data-ingestion/` (text, clauses).
- Each person / variant works only in its own `approaches/experiments/<name>/` (lowercase). Do not edit someone else's
  experiment folder.
- Every experiment needs `README.md` (what it does, how it works, how to run, assumptions, limitations),
  `config.json` (`"name"` = one-line description), `risk.json` (overfitting declaration, see
  `approaches/dashboard/README.md`), **`EXPLAIN.md`** and `outputs/predictions.json`.
- `EXPLAIN.md` is what the dashboards' **Explain** button shows, in two sections:
  - `# In plain words`: 3-6 sentences anyone on the team understands, no jargon (say "a search engine that matches
    words" instead of "BM25", "Claude reads each rule and says yes or no" instead of "LLM classifier"): what goes in,
    what the method does step by step, what comes out, its main weakness.
  - `# Technical`: the exact method as numbered steps: models and versions, parameters, corpus, queries, fusion,
    filters, output size, dev scores and the overfit risk. Without this section the README's "Method" section is shown.
  Update both whenever the method changes.
- Shared tools: `approaches/benchmarking/bench.py` (scores + leaderboard), `approaches/benchmarking/dashboard_rows.py`
  (dashboard data).

## Shared vector database

- Importer: `data-ingestion/import_vectors.py`. Install dependencies with
  `python -m pip install -r data-ingestion/requirements-vectors.txt`, then run
  `python data-ingestion/import_vectors.py` from the repository root.
- Shared local LanceDB: `data-ingestion/.cache/lancedb`, table `clauses`. All experiments
  should reuse this table read-only. Keep experiment-specific derived data in their own caches.
- Source vectors: `data-ingestion/embeddings/gemini-embedding-2-preview_d768_n26769.npz`.
  Query vectors must use the same embedding model and 768 dimensions; use cosine distance.
- Each row stores `clause_id`, `vector_row`, `regulation`, `version`, `paragraph`, `pages`,
  `text`, and `vector`. Clause IDs use filename stem plus zero-based clause position;
  citation metadata alone is not unique. Preserve the original corpus order and text.
- Import verifies every row's citation mapping before writing. It cannot detect changed text
  with unchanged citations because the NPZ lacks source-text hashes.
- The database is git-ignored and rebuilt locally from shared source files. No API key or
  embedding call is needed for import. `--replace` intentionally rebuilds the shared table.
- See `data-ingestion/VECTOR_DB.md` for usage. Importing data does not produce benchmark predictions.

## Benchmark and dashboard (standard flow)

Every time your algorithm changes, score it on **both** cases (with your own pipeline and keys):

1. Dev case: `python approaches/benchmarking/bench.py <name> approaches/experiments/<name>/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json`
2. Unseen case (required): run your pipeline on `approaches/benchmarking/cases/holdout-acpe/`, write
   `outputs/predictions-holdout-acpe.json`, then
   `python approaches/benchmarking/bench.py <name> approaches/experiments/<name>/outputs/predictions-holdout-acpe.json approaches/benchmarking/cases/holdout-acpe/expected.json --index ../industrial-ai-hackathon/regulations/index.json`
3. `python approaches/benchmarking/check_unseen.py <name>` must say "up to date" (the pre-push hook runs it on the
   experiments your push changes and refuses the push otherwise).
4. `python approaches/benchmarking/dashboard_rows.py`
5. Pull, commit (experiment folder + `approaches/leaderboard.json`, `LEADERBOARD.md`, `dashboard/leaderboard_rows.json`), push.
6. Comparison dashboard: step 4 also rebuilds `approaches/dashboard/dashboard.html` (open it in a browser; commit it
   with the rest). The claude.ai copy (https://claude.ai/artifact/TEW2x5Fhkj8DHgtmfnLLTV) reads the
   `approaches/dashboard/leaderboard_rows.json` you pushed. A scheduled sync uploads it within about 5 minutes of the
   push, so every agent stops at the push; no dashboard access is needed.

**Ranking:** the main ranking is the **Robust score** = (dev page F2 + unseen-case clause recall) / 2
(`approaches/benchmarking/robust.py`), at the top of `LEADERBOARD.md` and on both dashboards. Approaches without an
unseen-case run rank below all that have one.

## Metrics we track (report all of them, every time)

`approaches/benchmarking/bench.py` records, per run, in `approaches/leaderboard.json`:

| level | compares | why it matters |
|---|---|---|
| **Page** P / R / F1 / **F2** (ranking metric) | distinct (regulation, version, page); a right paragraph also counts | the challenge's page level |
| **Clause** P / R / F1 / **F2** | distinct (regulation, version, paragraph), official normalisation | stricter: the right clause, not just the right page; closest offline proxy for the requirement level |
| **Regulation** P / R / F1 / F2 | distinct regulations | the challenge's regulation level |

When you report or push a result, state page F2, clause F2 and regulation F2, and how they compare with the
experiment's previous run and the current leader (`approaches/LEADERBOARD.md` or the dashboard). Always cite
paragraphs in predictions: a submission without `paragraph` scores 0 at clause level.

## Overfitting: consider it on every result

There is one labelled case (`dev-rear-lamp`); the final ranking uses a held-out case. Treat every dev score as
optimistic. Before you push any result, go through this checklist and record the answers in the experiment's
`risk.json` and README:

1. Was anything chosen by looking at dev scores or dev gold (sizes, thresholds, top-k, rules, keyword lists, prompt
   examples, which regulations to include)? List each in `risk.json` `tuned_on_dev`.
2. Does anything read `cases/*/expected.json` outside the benchmark? It must not (`uses_gold` must stay false).
3. Would the method work unchanged on a different product (e.g. a seat belt or a brake)? If it hard-codes rear-lamp
   facts, say so and set `level` to `high`.
4. Is the gain robust? Prefer a change that improves both page F2 and clause F2 over one that trades one for the other;
   prefer round default values over values picked by a sweep.
5. Run it on the unseen case too: `approaches/benchmarking/cases/holdout-acpe/` (a different product, ACPE
   driver-assistance software, R175 answer key). Write its predictions to `outputs/predictions-holdout-acpe.json`
   (`"case_id": "holdout-acpe"`) and benchmark them against `approaches/benchmarking/cases/holdout-acpe/expected.json`.
   Read its **recall** (precision is understated there). Never tune on it. A big drop from dev to holdout means
   overfitting; the dashboard shows both side by side.
6. Set `level` (`low` / `medium` / `high`) honestly. The dashboard shows it next to the score, and the team prefers
   the lower-risk approach when scores are close.

Never optimise against `expected.json` directly, never copy gold text or citations into prompts or code, and never
"fix" a score by editing results files: re-run the benchmark.

## Track everything

- Every run goes through `bench.py` (it appends to `approaches/leaderboard.json`; never edit that file by hand except
  to merge both sides of a conflict).
- Keep the experiment's latest `outputs/predictions.json` committed (the dashboard verifies it against the run).
- Keep a short history in the experiment README (or a `HISTORY.md`): what changed, page / clause / regulation F2,
  and the risk you declared.

## Dashboard updates on every commit and push

- On every push to `main`, the GitHub Action `.github/workflows/dashboard.yml` rebuilds `approaches/LEADERBOARD.md`,
  `approaches/dashboard/leaderboard_rows.json` and `dashboard.html` and commits them (`Rebuild dashboard ... [skip ci]`)
  when they changed. So after you push, `git pull` again before your next push (the pre-push hook enforces this).

- The `pre-commit` hook (enable once: `git config core.hooksPath .githooks`) rebuilds
  `approaches/dashboard/dashboard.html` and `leaderboard_rows.json` whenever benchmark results or experiment metadata
  are committed, and adds them to that commit, so every push carries an up-to-date dashboard.
- Without the hook, run `python approaches/benchmarking/dashboard_rows.py` yourself before committing.
- Everyone sees it with `python approaches/dashboard/open.py` (pulls, then opens it). The claude.ai copy syncs from
  `main` every 5 minutes.

## Secrets

API keys go in a git-ignored `.env` (repo root or the experiment folder), never in code, configs or commits. Check
`git diff --cached` for keys before committing.
