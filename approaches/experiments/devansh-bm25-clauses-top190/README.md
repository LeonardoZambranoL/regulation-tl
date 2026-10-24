# devansh-bm25-clauses-top190

Owner: Devansh. **Rules pick the regulations, BM25+ (with bigrams) ranks their clauses from spec queries, cite the top
190 clauses.** No LLM (deterministic, free). The retrieval baseline the other Devansh experiments are compared with.
(Named `devansh` until it was renamed for clarity; history kept.)

## How it works

1. Regulation selection (`regselect`, method `combined` = rules): spec keywords map to regulation families (lamp ->
   R48 installation, stop / position / reversing lamp -> R148, retro-reflector -> R150, LEDs / PCB -> R10 EMC, about 30
   more families), then supersession and vehicle-category filters. Dev case: R48, R148, R150, R10.
2. Corpus: the team's `data-ingestion/clauses` (one chunk per clause) of the selected regulations only.
3. Queries from `spec.md`: the product, each function, each part, each material row, part x product, the whole spec;
   each searched with BM25+ (bigrams), results fused with reciprocal rank fusion.
4. Output: the top 190 clauses, one requirement each (clause text, cited at its first page + paragraph).

Inputs: the case's `spec.md`. Output: `outputs/predictions.json`. Config: `config.json`.
Code: `../devansh-toolkit/src/retrieval` (shared by all Devansh experiments).

## Run

```bash
cd approaches/experiments/devansh-toolkit/src      # after ../setup.sh
../.venv/bin/python -m retrieval.export --config ../../devansh-bm25-clauses-top190/config.json --out ../../devansh-bm25-clauses-top190/outputs/predictions.json
cd ../../../..
python approaches/benchmarking/bench.py devansh-bm25-clauses-top190 approaches/experiments/devansh-bm25-clauses-top190/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

## Result (dev-rear-lamp, team bench)

| page P | page R | page F2 | clause F2 | reg F2 | requirements |
|---|---|---|---|---|---|
| 0.317 | 0.604 | 0.511 | 0.148 | 1.000 | 190 |

## Assumptions and limitations

- 190 = the size of the dev gold set (declared in `risk.json`); the rules were written while looking at the dev product.
- Text similarity cannot tell which of the selected regulations' clauses apply; precision stays around 0.3.
  `devansh-llm-clause-filter` replaces the ranking with an LLM decision per clause and scores much higher.
