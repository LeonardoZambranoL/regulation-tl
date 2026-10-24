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

## Repo layout

```
regulations/          base-version PDFs of all 55 citeable regulations (UN_R48_base.pdf, ...)
data-ingestion/       PDF -> text (data-ingestion/text) -> clauses JSON (data-ingestion/clauses): see data-ingestion/README.md
retrieval/            plug-and-play retrieval lab: algorithms, configs, benchmark, leaderboard  -> retrieval/README.md
setup.sh / setup.ps1  one-command setup (venv + deps + clones the challenge repo next to this one)
requirements.txt      core deps (pymupdf, numpy); retrieval/requirements-neural.txt for the optional ML retrievers
```

Expected folder layout on your machine:

```
some-folder/
  regulation-tl/            this repo
  industrial-ai-hackathon/  the challenge repo (cases, schemas, scorer); setup clones it
```

## Quick start

```bash
git clone https://github.com/LeonardoZambranoL/regulation-tl.git && cd regulation-tl
./setup.sh --neural              # Windows: .\setup.ps1 -Neural   (drop the flag for a light, lexical-only install)
.venv/bin/python -m retrieval.bench --list                    # Windows: .venv\Scripts\python ...
.venv/bin/python -m retrieval.bench                           # benchmark every pipeline on the dev case
.venv/bin/python -m retrieval.bench --combo bm25plus_bigrams+dense_bge_small --rerank BAAI/bge-reranker-base
.venv/bin/python -m retrieval.search "stop lamp luminous intensity" --config hybrid_rrf
```

Commit new configs (`retrieval/configs/`) and the updated leaderboard (`retrieval/results/`) so everyone sees what was tried.

## Planned pipeline

```
spec.md + exploded view
  -> (1) regulation selection   LLM / rules on scope sections: which of the 55 regulations apply?
  -> (2) retrieval              multi-query, hybrid sparse+dense (+rerank) over data-ingestion clauses  <- retrieval/
  -> (3) requirement extraction LLM splits candidate paragraphs into one-obligation requirements, keeps citations
  -> (4) validate + score       tools/validate.py, tools/score_local.py, then upload
```

Current findings and the research menu of algorithms to try are in [retrieval/README.md](retrieval/README.md).
