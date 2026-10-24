# regulation-tl: Industrial AI Hackathon (Certivity)

Our solution for the [Certivity challenge](https://github.com/Certivity/industrial-ai-hackathon): **from a product
specification (and/or an exploded view) to every requirement it must fulfil under UN Regulations**, each one citing the
regulation, version and page (and ideally the paragraph).

## The challenge in short

- **Main goal (scored):** the input is `cases/<case>/spec.md` + `exploded_view.png`. The output is a JSON list of
  requirements, one engineering obligation each, with `source: {regulation, version, page, paragraph}`. Cite the
  **base** version.
  Scored on recall and precision at three levels: regulations, pages (page *or* paragraph right is enough), and
  requirements (LLM-matched on the platform).
- **Sub-goal (optional):** given requirements from an old regulation version plus the new version, output which ones are
  `modified` / `removed` / `added`, with a reason.
- Worked example: `dev-rear-lamp` (190 expected requirements from UN R48, R148, R150, R10). The **held-out case is
  released Sunday morning** (`git pull` in the challenge repo). **The last valid upload counts**, not the best one.
- Validate before uploading: `python ../industrial-ai-hackathon/tools/validate.py out.json`; local regulation/page
  score: `python ../industrial-ai-hackathon/tools/score_local.py out.json`.

## How we are scored (from the challenge README)

| level | what is compared | how | offline? |
|---|---|---|---|
| **Regulations** | distinct regulations we cite vs the gold set | precision = right ones / ours, recall = right ones / gold | yes: `tools/score_local.py` |
| **Pages** | distinct (regulation, **base** version, page) we cite | a page counts if the **page OR the paragraph** is right (so always give `paragraph`; page off by one is forgiven when the paragraph is right). Paragraphs compare by meaning: `Annex 8, 2.1.` == `annex 8 2.1`, but `5.4.2.3` != `5.4.23` | yes: `tools/score_local.py` (platform uses full page ranges, so it can differ slightly) |
| **Requirements** (primary) | each of our requirements matched 1:1 to a gold one stating the same obligation (scope, condition, constraint) | precision = share of ours that match, recall = share of gold we found; judged by an LLM | **platform only** |
| UI | | judged by the jury | secondary |
| Sub-goal | flagged requirement changes | recall of flagged requirements + accuracy of the stated change | platform |

So: **precision and recall both count**. Citing extra regulations or pages, or padding with non-matching requirements,
costs precision. Write one engineering obligation per requirement. Upload limit: 5 per hour per challenge.
`approaches/benchmarking/bench.py` scores saved predictions with the official scorer (plus F2) and keeps the internal
leaderboard: see [approaches/README.md](approaches/README.md).

## Repo layout

```
regulations/          base-version PDFs of all 55 citeable regulations (UN_R48_base.pdf, ...)
data-ingestion/       PDF -> text (data-ingestion/text) -> clauses JSON (data-ingestion/clauses): see data-ingestion/README.md
approaches/           internal competition: shared benchmark + leaderboard, one folder per experiment
  benchmarking/       bench.py: official scorer + F2, validator, schemas
  LEADERBOARD.md      generated ranking (page F2, then regulation F2)
  experiments/<name>/ each person's / variant's code, config, predictions and results (see approaches/README.md)
  dashboard/          data + how-to for the comparison dashboard (risk.json, refresh steps)
```

Expected folder layout on your machine:

```
some-folder/
  regulation-tl/            this repo
  industrial-ai-hackathon/  the challenge repo (cases, schemas, scorer)
```

Score an experiment's predictions on the internal leaderboard (from the repo root):

```bash
python approaches/benchmarking/bench.py <experiment> approaches/experiments/<experiment>/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

New here: [CONTRIBUTING.md](CONTRIBUTING.md) (setup for any coding agent, then pull, test, push).
Team rules for every agent (pull before push, folder ownership, overfitting, secrets): [AGENTS.md](AGENTS.md).
Comparison dashboard: `python approaches/dashboard/open.py` (pulls, then opens it in your browser)
(claude.ai copy: https://claude.ai/artifact/TEW2x5Fhkj8DHgtmfnLLTV) ([how to update it](approaches/dashboard/README.md)).

Do not commit secrets: API keys go in a git-ignored `.env` (see `.gitignore`).
