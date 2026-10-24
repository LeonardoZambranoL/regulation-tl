# Comparison dashboard

One page that compares every experiment in `approaches/experiments/`:
**https://claude.ai/artifact/TEW2x5Fhkj8DHgtmfnLLTV**

It shows each approach's latest page F2 (bar chart), page precision vs recall (with equal-F2 curves), the standings
(what each approach does, page and regulation scores, gold pages missed, overfit risk and why) and every run ever
benchmarked. Its data is `leaderboard_rows.json` in this folder, built from `approaches/leaderboard.json`.

Access: anyone with the link can open it (owned by Devansh). To **update** it, ask Devansh for **edit** access
(Share menu). Without edit access, still do steps 1-4 and push: Devansh's
Claude uploads the new rows.

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
