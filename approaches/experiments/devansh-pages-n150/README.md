# devansh-pages-n150

Owner: Devansh. **Rules-based regulation selection, then BM25+ (with bigrams) retrieval over whole PDF pages; cite the
top 150 pages.** No LLM in the loop (deterministic, free).

1. Regulation selection (`regselect`, method `combined`): R48, R148, R150, R10 on the dev case.
2. Corpus: our own PDF parser, one chunk per page of the selected regulations (`"source": "pdf", "granularity": "page"`).
3. Queries: generated from `spec.md` (product, each function, part, material row, part x product, whole spec),
   pooled with reciprocal rank fusion.
4. Output: top 150 pages, one requirement per page (page text, no paragraph).

N = 150 was chosen with `retrieval.export --sweep` on the dev case (F2 by size: 100 -> 0.513, **150 -> 0.580**,
190 -> 0.535, 300 -> 0.508). That is tuned on the only labelled case, so expect less on the held-out one.

## Run

```bash
cd approaches/experiments/devansh/src        # after ../setup.sh
../.venv/bin/python -m retrieval.export --config ../../devansh-pages-n150/config.json --out ../../devansh-pages-n150/outputs/predictions.json
cd ../../../..
python approaches/benchmarking/bench.py devansh-pages-n150 approaches/experiments/devansh-pages-n150/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

## Result (dev-rear-lamp, team bench)

| page P | page R | page F2 | reg F2 | requirements |
|---|---|---|---|---|
| 0.280 | 0.793 | **0.580** | 1.000 | 150 |

Useful as a no-LLM fallback; the LLM classifier beats it by a wide margin.
