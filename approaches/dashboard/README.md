# Comparison dashboard

One page that compares every experiment in `approaches/experiments/`, in two forms:

- **`approaches/dashboard/dashboard.html`**: for everyone. From the repo root run
  `python approaches/dashboard/open.py` (pulls, then opens it in your browser), or double-click the file.
  No account, server or setup; data is built into the file.
- **https://claude.ai/artifact/TEW2x5Fhkj8DHgtmfnLLTV**: the same view on claude.ai, synced from the repo.

`python approaches/benchmarking/dashboard_rows.py` rebuilds both `leaderboard_rows.json` and `dashboard.html`
(from `standalone_template.html`; edit the template, not the generated file).

It shows each approach's latest page F2 (bar chart), page precision vs recall (with equal-F2 curves), the standings
(what each approach does, page and regulation scores, gold pages missed, overfit risk and why) and every run ever
benchmarked. Its data is `leaderboard_rows.json` in this folder, built from `approaches/leaderboard.json`.

Access: anyone with the link can open it (owned by Devansh). **You do not need edit access:** a scheduled sync on
Devansh's machine pulls the repo every 5 minutes and uploads `leaderboard_rows.json` when it changed, so pushing your
benchmark results (step 4) is enough. The sync runs while Devansh's Claude app is open; otherwise on its next launch. Without edit access, still do steps 1-4 and push: Devansh's
Claude uploads the new rows.

## Scores shown

- **Req F2** (main ranking): the platform's requirement-level score (one to one with the experts' single-obligation
  requirements), estimated by `python approaches/benchmarking/req_judge.py <predictions> <expected.json> --record <name>`
  (Claude, your own key; stored in `approaches/req_scores.json` for that exact predictions file). Approaches without it
  follow, ranked by Robust. Only the top 6 are shown; "Show all approaches" brings the rest back, dimmed.
- **Robust** (second key): (dev page F2 + unseen-case clause recall) / 2, from
  `benchmarking/robust.py`. Needs a holdout-acpe run; approaches without one are listed after, by page F2.
  `python approaches/benchmarking/check_unseen.py` lists experiments missing an up-to-date unseen-case run.
- **Page** (precision, recall, F1, F2; ranking metric = page F2): from `bench.py` and the official scorer. A cited page
  counts if the page or its paragraph is right.
- **Clause** (precision, recall, F1, F2): recorded by `bench.py` for every run since it was added (and computed by
  `dashboard_rows.py` for older runs): distinct cited
  (regulation, version, paragraph) vs the gold paragraphs, with the official paragraph normalisation. Stricter than
  page level (a neighbouring paragraph on the right page does not count); citations without `paragraph` score 0. Shown
  only when `experiments/<name>/outputs/predictions.json` is exactly the file the run scored (same fingerprint), so keep
  your latest predictions file committed. Needs the challenge repo next to this one for the gold file.
- **Regulation** F2, **gold pages missed**, **overfit risk** (see risk.json below).

## How it stays connected (pull and push)

The dashboard is driven entirely by this folder in the repo:

| file | what it is | how it reaches the dashboard |
|---|---|---|
| `leaderboard_rows.json` | the data: every benchmark run (built from `approaches/leaderboard.json`) | sync uploads it when it changes |
| `index.html` | the dashboard page itself (charts, tables, the "Join and contribute" card) | sync publishes it when it changes |

A scheduled sync on Devansh's machine pulls `main` every 5 minutes (while his Claude app is open) and publishes
whatever changed. So everyone **pushes** results or page edits to the repo, and the dashboard **pulls** them. Nobody
needs edit access on claude.ai, and any coding agent works.

### Changing the dashboard page

Edit `approaches/dashboard/index.html` and push; it goes live within about 5 minutes. It is a page of the claude.ai
"Dashboard" artifact type, so keep its rules:
- Every number on the page comes from the dataset `runs` (or the `standings` calc), marked with `data-source` /
  `data-field` and filled inside `dash.onData`; no hard-coded figures.
- No external scripts, styles, fetches, iframes or forms; scripts use the `dash` and `d3` globals.
- Use the theme tokens (`var(--color-fg)`, `var(--color-panel)`, ...) so it works in light and dark.
- The sync reports the dashboard's own check after publishing; if your change breaks it, the old page stays in git
  history: revert your commit and push.

## Add your experiment (standard flow)

1. Create `approaches/experiments/<name>/` (lowercase, see `approaches/README.md`) with `README.md`, `config.json`
   (its `"name"` is the one-line description shown on the dashboard) and **`risk.json`** (below).
2. Write `outputs/predictions.json` in the submission format, then benchmark from the repo root:
   ```bash
   python approaches/benchmarking/bench.py <name> approaches/experiments/<name>/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
   ```
3. Rebuild the dashboard data (standard library only):
   ```bash
   python approaches/benchmarking/dashboard_rows.py
   ```
4. `git pull` (always before pushing), then commit your experiment folder, `approaches/leaderboard.json`,
   `approaches/LEADERBOARD.md` and `approaches/dashboard/leaderboard_rows.json`, and push.
5. Upload the rows to the dashboard (needs edit access): see "For Claude" below, or ask Claude
   "update the comparison dashboard".

## EXPLAIN.md: say what your approach does, in plain words

The dashboards' **Explain** button shows both parts of `approaches/experiments/<name>/EXPLAIN.md`:

```markdown
# In plain words
3-6 sentences anyone on the team understands, no jargon: what goes in, what it does, what comes out, main weakness.

# Technical
1. Numbered steps with models, parameters, corpus, queries, fusion, filters, output size.
2. Dev scores and overfit risk.
```

Fallbacks: plain text without headings counts as "In plain words"; without `# Technical` the README's "Method" /
"How it works" section is shown; without any `EXPLAIN.md`, a draft in `approaches/dashboard/explanations.json`
(marked as a draft).

## risk.json: declare how much you tuned on the dev case

There is only one labelled case (`dev-rear-lamp`), and the ranking is decided on a held-out case. Anything chosen by
looking at the dev gold (a size cut-off, rules written for this product, prompt examples) can look great here and fail
there. Declare it, so the team can prefer robust approaches when scores are close:

```json
{
  "level": "low | medium | high",
  "uses_llm": true,
  "deterministic": false,
  "uses_gold": false,
  "tuned_on_dev": ["what was chosen by looking at dev results or dev gold", "..."],
  "notes": "one or two sentences"
}
```

- `low`: nothing chosen from dev scores; generic method and prompts.
- `medium`: some choices informed by the dev product or its gold (rules, prompt wording), no thresholds fitted to it.
- `high`: thresholds or sizes fitted to dev scores, or anything that reads `expected.json`.

The dashboard adds automatic flags: an exact match of the gold set is `high`, a missing `risk.json` is `unknown`.

Ways to keep risk low: no cut-offs fitted by sweeping on dev scores (or report the sweep and pick a round default),
general rules over product-specific ones, and keep `expected.json` out of anything but the benchmark.

## For Claude: how to update the dashboard

Use the claude.ai Artifact tools (Claude Code / desktop). The dashboard is an Artifact of type "Dashboard"; its data is
a dataset `runs` whose source is an uploaded file.

1. Pull the repo; run steps 2-3 above if new runs exist.
2. Upload the file as an asset:
   `Artifact` publish with `url: "https://claude.ai/artifact/TEW2x5Fhkj8DHgtmfnLLTV"`,
   `file_path: "<repo>/approaches/dashboard/leaderboard_rows.json"`, `asset: true`.
   Note the returned `/_blob/<id>` url.
3. `ArtifactData` `get` collection `datasets`, doc `runs` (note its `version` and the old blob url).
4. `ArtifactData` `update` collection `datasets`, doc `runs`, `if_version` = that version, data:
   `{"source": {"kind": "file", "url": "/_blob/<new id>", "name": "leaderboard_rows.json"},
     "updated": {"at": "<ISO time>", "by": "<who>"}}`.
5. Delete the old asset: `Artifact` `delete` with the `url` and `path: "<old id>"`.
6. Read `data/users/me` doc `check` once; if it says `failed`, report what it lists.

Do not edit the page (`files/index.html`) unless asked; if you do, read it first and keep its data marks.
If you have no edit access the write is refused: say so and leave the upload to Devansh.

## Updated on every push

| what | updated by | when |
|---|---|---|
| `approaches/LEADERBOARD.md`, `leaderboard_rows.json`, `dashboard.html` in the repo | GitHub Action `.github/workflows/dashboard.yml` | every push to `main` that touches results, experiments or benchmark code (about a minute); it commits only when something changed |
| what `python approaches/dashboard/open.py` shows | rebuilt locally from the pulled `leaderboard.json` | every time you open it |
| the claude.ai dashboard | scheduled sync on Devansh's machine | every 5 minutes while his Claude app is open (claude.ai cannot be triggered by GitHub) |

## Troubleshooting: "my push does not show up"

- Check the repo's **Actions** tab on GitHub for the "Rebuild dashboard" run of your push.

- **Standalone view**: `python approaches/dashboard/open.py` rebuilds the page from `approaches/leaderboard.json` every
  time it opens (into the git-ignored `approaches/dashboard/.local/`), so a pushed `bench.py` run always appears after
  the pull, even if the committed `dashboard.html` was not rebuilt.
- **claude.ai view**: the sync resets its own clone to `origin/main` every 5 minutes (while Devansh's Claude app is
  open) and publishes when the data or page changed. Nothing shows if the run never reached `leaderboard.json`: check
  that you ran `bench.py` (not only your own scripts) and pushed `approaches/leaderboard.json`.
- Enable the hooks once (`git config core.hooksPath .githooks`) so your commits also carry a rebuilt `dashboard.html`.
