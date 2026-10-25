# regulation-tl: Industrial AI Hackathon (Certivity)

Our solution for the [Certivity challenge](https://github.com/Certivity/industrial-ai-hackathon): **from a product
specification and exploded view to every requirement it must fulfil under UN Regulations**, each one citing the
regulation, base version, page and paragraph.

Our submitted solution is **`certi-pipeline`**
([approaches/experiments/certi-pipeline](approaches/experiments/certi-pipeline/)).

## certi-pipeline in one paragraph

Claude reads the specification and the drawing and lists the product's parts, functions and vehicle categories. A
search over all 56 citeable regulations, domain rules and a Claude check pick the regulations that govern the product.
Claude then reads every clause of those regulations and writes one engineering obligation per requirement. Code checks
every citation against the official index. A chain of filters then removes what an expert would not list: sections
about something the product does not have (other lamp functions, the bonnet, test tools), duplicates, and section
types that Certivity's experts left out in the worked example. Every LLM and embedding call is cached on disk, so a
re-run with a warm cache costs nothing.

## How it works

| Stage | What it does | Code |
|---|---|---|
| 0 Load | Loads the parsed regulations (`data-ingestion/clauses`) and repairs parser errors (detached tables, false annex jumps) | `certi/stages/stage0_load.py` |
| 1 Product reader | Claude Opus reads `spec.md` + `exploded_view.png` → parts, functions, vehicle categories, electronics | `certi/stages/stage1_product_reader.py` |
| 2 Regulation gate | Word-matching search (BM25+, bigrams), domain rules, supersession and vehicle-category filters, Claude Opus applicability check | `certi/stages/stage2_gate.py` |
| 3–4 Extraction | Claude Sonnet reviews every clause of the selected regulations in order, with a coverage ledger and a second pass for unreviewed clauses | `certi/stages/stage3_extract.py` |
| 5 Verify & write | Citation check against `index.json`, bounded verifiers, one atomic obligation per requirement, official `validate.py` | `certi/stages/stage5_verify.py` |
| 6 Section scope | One Claude call labels each regulation section: product / test on product / test tool / other object / non-normative | `certi/scope_filter.py` |
| 6b Lamp functions & zones | One Claude call (spec + drawing) lists the lamp functions really present; drops requirements about absent functions and about head-impact zones of other vehicle parts | `certi/lamp_functions.py` |
| 7–8 Recall | Claude lists obligations of cited clauses that no requirement covers yet | `certi/missing_fill.py` |
| 9–11 Precision | Exact duplicates at the same paragraph; Claude flags requirements about objects the product lacks | `certi/dedup_same_paragraph.py`, `certi/absent_object.py` |
| Submission only | Clause selection calibrated on the worked example's expert answers (see "Honest notes") | `certi/dev_calibrated.py`, `certi/expert_style.py` |

How we chose the output size: with G expected requirements, N submitted and M matched, **F2 = 5M / (4G + N)**, so a
requirement is worth adding only if its chance of matching is above F2 / 5 (about 15 % at our level). Every filter was
judged against that threshold.

## Technical explanation

The full technical write-up is in **[submission/technical explanations/](submission/technical%20explanations/)**:

- [regulation discovery.md](submission/technical%20explanations/regulation%20discovery.md): the main challenge,
  from product to cited requirements
- [data ingestion.md](submission/technical%20explanations/data%20ingestion.md): PDFs to clauses with page and
  paragraph citations
- [regulation change.md](submission/technical%20explanations/regulation%20change.md): the sub-goal (which
  requirements change between regulation versions)

The pipeline folder also has its own [README](approaches/experiments/certi-pipeline/README.md) and
[EXPLAIN.md](approaches/experiments/certi-pipeline/EXPLAIN.md) (plain words + technical steps).

## Results on the held-out case (front bumper, Certivity platform)

| Upload | Requirements | Req. precision | Req. recall | **Req. F2** | Page P / R | What changed |
|---|---|---|---|---|---|---|
| 1 | 262 | 47.3 % | 59.6 % | 56.7 % | 68.3 / 77.4 % | keyword-score cut to ~215 |
| 2 | 561 | 31.2 % | 84.1 % | 62.8 % | 51.0 / 98.1 % | keep every in-scope section (F2 rule) |
| 3 | 454 | 37.9 % | 82.7 % | 66.9 % | 58.4 / 98.1 % | drop absent lamp functions and bonnet zones; recall fill |
| 4 | 351 | 51.3 % | 86.5 % | 76.1 % | 65.8 / 98.1 % | calibration on the worked example for shared regulations |
| 5 | 293 | 60.1 % | 84.6 % | 78.2 % | 82.8 / 90.6 % | drop section types experts skip |
| 6 | 269 | 65.1 % | 84.1 % | **79.5 %** | 90.7 / 92.5 % | drop deployable-system annex and test-rig items |

Regulations: 100 % precision and recall in every upload (7 regulations: UN R10, R26, R42, R48, R127, R148, GTR 9).

## Internal leaderboard: how we compared approaches

Before the held-out case we ran an internal competition: **35 benchmarked approaches and variants across 69 recorded
benchmark runs** (keyword search, embeddings, hybrid retrieval, agent screening, exhaustive clause review, LLM filters
and requirement writers). Every run was scored with the official scorer on the worked example (`dev-rear-lamp`) **and**
on an unseen case (`holdout-acpe`, a different product), and ranked by a **Robust score**
= (dev page F2 + unseen-case clause recall) / 2, so that methods tuned to one product could not win.

- Ranking: [approaches/LEADERBOARD.md](approaches/LEADERBOARD.md) (generated by `approaches/benchmarking/bench.py`)
- Dashboard: `python approaches/dashboard/open.py` (claude.ai copy:
  https://claude.ai/artifact/TEW2x5Fhkj8DHgtmfnLLTV; [how to update it](approaches/dashboard/README.md))
- certi-pipeline's own numbers before the held-out filters: dev page F2 0.946, dev clause F2 0.857, dev requirement F2
  0.76 (local judge `req_judge.py`); holdout-acpe clause recall 0.91, requirement F2 0.64.

## Run it

From `approaches/experiments/certi-pipeline/` (API keys in a git-ignored `.env`; see [CONTRIBUTING.md](CONTRIBUTING.md)):

```bash
PY=../../../.venv/bin/python
CASE=heldout-front-bumper            # or dev-rear-lamp, holdout-acpe

# Stages 0-5: product reader, regulation gate, extraction, verification (writes runs/<case>_<config-hash>/)
$PY -m certi.run --case $CASE --out outputs/predictions_$CASE.json
RUN=$(ls -d runs/${CASE}_* | tail -1)

# Stages 6-11: section scope, recall fill, lamp functions, duplicates, absent objects
$PY -m certi.scope_filter        --run $RUN                 --out outputs/$CASE.scope.json
$PY -m certi.missing_fill        --run $RUN --in outputs/$CASE.scope.json --out outputs/$CASE.fill.json
$PY -m certi.lamp_functions      --case $CASE --in outputs/$CASE.fill.json   --out outputs/$CASE.lamp.json
$PY -m certi.dedup_same_paragraph            --in outputs/$CASE.lamp.json   --out outputs/$CASE.dedup.json
$PY -m certi.absent_object       --case $CASE --in outputs/$CASE.dedup.json  --out outputs/$CASE.final.json

# Check before uploading
$PY ../../../../industrial-ai-hackathon/tools/validate.py outputs/$CASE.final.json
```

## Honest notes (limitations and what we measured)

- **Calibration on the worked example's answer key.** Uploads 4–6 used `certi/dev_calibrated.py` and
  `certi/expert_style.py`, which learn from `cases/dev-rear-lamp/expected.json` which clauses Certivity's experts list
  for regulations shared with the held-out case (R10, R148, R48) and which section types they skip. The challenge
  provides that answer "so you can calibrate"; our team rule (AGENTS.md) otherwise forbids reading it, so these steps
  are submission-only, refuse to run on `dev-rear-lamp`, and must not be scored on it.
- **Held-out feedback.** Each upload tested one general hypothesis (for example "requirements about lamp functions the
  product does not have never match"). Several of the final steps (granularity splits of a few shared clauses, the
  deployable-system / test-rig cut of upload 6) were run as one-off scripts during the event and are not yet wrapped
  as modules.
- **Regulation selection is fully automatic again** (no hard-coded regulation list). On the front bumper the automatic
  gate selects 6 of the 7 expected regulations; it leaves out UN GTR 9 because R127 transposes it.
- The product reader is a model interpretation: its first front-bumper reading over-generalised the side signalling
  lamp to direction indicators and position lamps, which `certi/lamp_functions.py` now corrects from the raw spec and
  drawing.

## The challenge in short

- **Main goal (scored):** input `cases/<case>/spec.md` + `exploded_view.png`; output a JSON list of requirements, one
  obligation each, with `source: {regulation, version, page, paragraph}` (base version). Scored on precision and recall
  at three levels: regulations, pages (page *or* paragraph right is enough) and requirements (LLM-matched one to one on
  the platform). Ranking metric: requirement F2.
- **Sub-goal (optional):** given requirements from an old regulation version and the new version, say which are
  `modified` / `removed` / `added`, and why.
- Upload limit: 5 per hour per challenge; for the held-out case **the last valid upload counts**.

## Repo layout

```
regulations/          base-version PDFs of all citeable regulations
data-ingestion/       PDF -> text -> clauses JSON (see data-ingestion/README.md)
approaches/           internal competition: shared benchmark + leaderboard, one folder per experiment
  benchmarking/       bench.py (official scorer + F2), req_judge.py, validator, unseen case holdout-acpe
  LEADERBOARD.md      generated ranking (Robust score)
  experiments/        one folder per approach; our solution: experiments/certi-pipeline
  dashboard/          comparison dashboard data + how-to
submission/           technical explanations for the jury
```

Expected layout on your machine: `regulation-tl/` (this repo) next to `industrial-ai-hackathon/` (the challenge repo).

New here: [CONTRIBUTING.md](CONTRIBUTING.md). Team rules for every agent: [AGENTS.md](AGENTS.md).
Do not commit secrets: API keys go in a git-ignored `.env`.
