# `retrieval/`: plug-and-play retrieval lab

Goal: given a product spec, find **every regulation paragraph that holds a requirement for it** (recall first), with a
citation (`regulation / version / page / paragraph`) we can paste straight into a submission. An LLM step then turns the
candidates into one-obligation-per-requirement text. This folder covers the retrieval half and lets anyone swap
algorithms and measure them on the worked example.

## Layout

```
retrieval/
  corpus.py        -> Chunk(regulation, version, page, paragraph, text). Two sources, picked per config:
                     "source": "clauses" (default) - the team's parse in data-ingestion/clauses (26.8k clauses,
                                                       183/190 dev-case gold citations reproduced)
                     "source": "pdf"               - parse the PDFs here, "granularity": "paragraph" (36.8k chunks,
                                                       187/190) or "page" (3k pages)
  retrievers/
    base.py        Retriever interface + @register + build(config)
    lexical.py     bm25 (okapi / BM25+ / bigrams), tfidf (word or char n-grams)        - numpy only
    neural.py      dense (any sentence-transformers model, exact cosine), hnsw (faiss), splade
    compose.py     rrf, score_fusion (hybrids), rerank (cross-encoder funnel over any first stage)
  pipeline.py      Pipeline(config): load corpus + build retriever; .search(), .pooled() (multi-query RRF), spec_queries()
  bench.py         benchmark configs/combos on cases/<case>/expected.json -> results/leaderboard_<case>.md
  search.py        print top hits for a query or a spec, to eyeball results
  oracle.py        ceiling experiments: what perfect regulation selection / filtering would be worth
  configs/*.json   one pipeline per file; add yours here
  results/         committed leaderboards, so everyone sees what has been tried
```

## Run it

```bash
./setup.sh --neural          # or .\setup.ps1 -Neural on Windows; drop the flag for lexical-only (no torch)
.venv/bin/python -m retrieval.bench --list                         # (Windows: .venv\Scripts\python)
.venv/bin/python -m retrieval.bench                                # every config in configs/
.venv/bin/python -m retrieval.bench retrieval/configs/bm25.json    # just one
.venv/bin/python -m retrieval.bench --combo bm25plus_bigrams+dense_bge_small                # hybrid, no JSON needed
.venv/bin/python -m retrieval.bench --combo bm25+dense_bge_small --fusion score_fusion --weights 1,0.5
.venv/bin/python -m retrieval.bench --combo bm25+dense_bge_small --rerank BAAI/bge-reranker-base --save
.venv/bin/python -m retrieval.search "stop lamp luminous intensity" --config hybrid_rrf -k 10
.venv/bin/python -m retrieval.search --spec ../industrial-ai-hackathon/cases/dev-rear-lamp/spec.md -k 40
```

**Speed:** lexical configs run in seconds. Dense/hnsw/hybrid/splade/rerank configs first embed the whole corpus once:
about **75-100 min on a laptop CPU**, about 1-3 min on a GPU (Colab works: clone, `pip install -r requirements.txt -r
retrieval/requirements-neural.txt`, run the bench). The embeddings are then cached in `.cache/`, and every config using
the same model reuses them.

The challenge repo must sit next to this one (`../industrial-ai-hackathon`, `setup` clones it) or pass `--challenge-dir`.
Parsed chunks and embeddings are cached in `.cache/` (git-ignored), so only the first run of a model is slow.
`--save` writes the combo into `configs/` so you can commit it; the leaderboard merges rows across runs, so commit
`results/` after a run to share your numbers.

## What the benchmark measures

**Read the official columns first:** they are what the challenge scores. Diagnostics explain *why* a pipeline scores
the way it does.

| task | how | columns | maps to the challenge's |
|---|---|---|---|
| **official** | spec -> pooled queries -> top **N** chunks become a mock submission (one requirement per chunk, cited at page + paragraph), scored with the challenge's own `tools/score_local.py` | `reg_P/R/F1`, `page_P/R/F1` | regulation level and page level, computed exactly like theirs (default N = 190, the size of the dev gold set; N = 100 and 400 are in the .json, `--sizes` to change) |
| | | `req_R_max` | ceiling of the **requirement-level recall** (platform-only, LLM-judged): share of gold requirements whose paragraph or page is among the N chunks. An LLM writing requirements from these chunks cannot find more than this |
| **locate** | each expected requirement's text as a query | `R@1`, `R@10`, `MRR` | none directly: "once an LLM has drafted a requirement, can we find its citation?" |
| **spec** | same pooled spec queries, without a size cut | `page_R@100`, `reg_R@5` | recall-only views: gold pages in the first 100 pooled pages, gold regulations in the top 5 |

How to read them:
- **Precision is cheap to lose.** A pipeline that cites 14 regulations when 4 are right gets reg_P about 0.2 however good its
  recall is. Regulation selection (LLM or rules) mostly moves `reg_P`, `page_P` and the requirement-level precision.
- **Recall is capped by retrieval.** `req_R_max` and `page_R` are the hard ceilings for anything downstream, so improve
  these first, then filter for precision.
- `locate` is easy for lexical methods because gold requirements are near-verbatim regulation text. For the rear lamp
  the gold uses R48/R148/R150/R10. Text similarity also ranks R7/R23/R53 high (older lamp regulations that R148 replaced),
  and R10 (EMC) is only reachable through "LED modules on PCB", i.e. through reasoning, not similarity.

## Results so far

See [`results/leaderboard_dev-rear-lamp.md`](results/leaderboard_dev-rear-lamp.md) (regenerated by every bench run).
All lexical (no-embedding) pipelines, N = 190 chunks (2026-10-24), sorted by page F1:

| pipeline | chunks | reg P / R / F1 | page P / R / F1 | req_R_max | locate MRR | time |
|---|---|---|---|---|---|---|
| **rrf(bm25+ bigrams + tfidf-char)** | clauses | 0.21 / 0.75 / 0.33 | **0.20 / 0.47 / 0.28** | 0.50 | 0.89 | slow (~4 min) |
| bm25, no title prefix | clauses | 0.19 / 0.75 / 0.30 | 0.19 / 0.45 / 0.26 | 0.48 | 0.85 | 3 s |
| tfidf-char 3-5 | clauses | 0.21 / 0.75 / 0.33 | 0.18 / 0.45 / 0.26 | 0.50 | 0.85 | slow (~4 min) |
| score_fusion(bm25+ bigrams + tfidf-word) | clauses | 0.21 / 0.75 / 0.33 | 0.18 / 0.42 / 0.25 | 0.42 | 0.88 | 7 s |
| **bm25+ bigrams, whole pages** | pdf pages | **0.29 / 1.00 / 0.44** | 0.16 / 0.57 / 0.25 | **0.62** | 0.84 | 6 s |
| rrf(bm25 pages + bm25+ bigram pages) | pdf pages | 0.29 / 1.00 / 0.44 | 0.15 / 0.55 / 0.24 | 0.55 | 0.81 | 4 s |
| bm25 (default k1=1.2, b=0.75) | clauses | 0.21 / 0.75 / 0.33 | 0.17 / 0.38 / 0.23 | 0.40 | 0.87 | 3 s |
| bm25+ bigrams | clauses | 0.21 / 0.75 / 0.33 | 0.16 / 0.36 / 0.22 | 0.39 | **0.91** | 8 s |
| tfidf-word | clauses | 0.21 / 0.75 / 0.33 | 0.16 / 0.36 / 0.22 | 0.39 | 0.86 | 3 s |

Full table with all columns: [`results/leaderboard_dev-rear-lamp.md`](results/leaderboard_dev-rear-lamp.md).

Takeaways:
- **Different winners for different jobs.** For finding the cited paragraph of a drafted requirement, use **bm25+ bigrams
  on clauses** (MRR 0.91). For coverage from the spec, use **whole pages with bm25+ bigrams**: the only pipeline that
  finds all 4 gold regulations, with 62% of gold requirements reachable. Character n-grams help clause-level spec recall
  (+10 points page recall when fused).
- Precision is the weak spot everywhere: about 14 regulations are cited for 4 gold ones (reg_P 0.2-0.3). Nothing in pure
  retrieval fixes that; regulation selection does.
- BM25 parameter tuning (k1/b) and the title prefix move results by only 1-3 points. Not worth more time.
- The next wins are query-side (LLM query expansion / HyDE: turn the spec into requirement-like queries) and regulation
  selection, not a better index.
- Dense / hnsw / hybrid (with dense): configs are ready and will use the team's precomputed embeddings once they are in
  the repo. SPLADE and cross-encoder rerank need a GPU or about 1 h of CPU; not run yet.

## Where accuracy is lost (oracle experiments) and the plan to fix it

`python -m retrieval.oracle [--config NAME]` cheats with the gold answer to price each pipeline stage before we build it
(dev case, bm25+ bigrams on clauses, N = 190):

| stage | reg F1 | page P / R / F1 | req_R_max |
|---|---|---|---|
| A  retrieval only (today) | 0.33 | 0.16 / 0.36 / 0.22 | 0.39 |
| B  + perfect regulation selection | **1.00** | 0.31 / 0.60 / **0.41** | 0.64 |
| D  + perfect regs, only "shall" clauses | 1.00 | 0.29 / 0.57 / 0.39 | 0.62 |
| E  perfect regs + **every** "shall" clause, no retrieval (1,223 clauses) | 1.00 | 0.20 / **1.00** / 0.34 | **1.00** |

What this shows:
1. **Regulation selection is the biggest single lever**: it doubles page F1 and makes reg F1 perfect.
2. **Once the regulations are right, search is no longer the problem.** 99% of gold requirements contain "shall", and
   *all* of them are among the 1,223 "shall" clauses of the 4 regulations. The task becomes **choosing about 190 of
   about 1,200 clauses**: a classification problem, not retrieval.
3. Gold sits in predictable sections: approval markings (R148 §3, R150 §3), general technical requirements
   (R148 §4, R150 §4-5), lamp-specific specs and installation (R48 §5 general + §6.x for each lamp present on the
   product), EMC for electronic sub-assemblies (R10 §6 + Annexes 9/10), and a few test annexes.

Proposed pipeline, in order of value:

| # | step | how | expected gain |
|---|---|---|---|
| 1 | **Regulation selection** | LLM reads the spec + each regulation's title and Scope (§1) and returns the applicable ones, with rules: lighting device -> R48 installation; one device regulation per function (R148 signalling lamps, R150 retro-reflectors, ...); any electronics (LEDs, PCB) -> R10 EMC; follow "UN Regulation No. X" cross-references in the selected ones | reg F1 0.33 -> ~1.0, page F1 about x2 |
| 2 | **Section selection** | LLM picks relevant sections from each selected regulation's heading tree (e.g. R48 §6.7 reversing lamp yes, §6.2 dipped-beam headlamp no) | cuts 1,200 -> a few hundred candidates without losing recall |
| 3 | **Clause classifier** | per candidate "shall" clause: does it apply to this product? A small/cheap LLM (batched), or retrieval scores as a prior | precision: the key step for the requirement-level score |
| 4 | **Split into obligations** | one engineering obligation per requirement, near-verbatim wording (gold texts are almost verbatim, e.g. "Every device ..." -> "The device ..."), keep the clause's page + paragraph | requirement-level match rate |
| 5 | **Query expansion (HyDE)** | if we stay retrieval-first: LLM writes requirement-like queries per part/function; `locate` shows these find their paragraph about 98% of the time in the top 10 | recall when steps 1-2 miss something |
| 6 | **Size the output** | submit roughly gold-sized lists (about 150-250 for a product like this); every extra non-matching requirement costs precision | balances P/R |

Cheap guaranteed points: always fill `paragraph` (a page counts if page **or** paragraph is right), cite the **base**
version, and never cite the latest version's pages.

## Add an algorithm

```python
# retrieval/retrievers/my_algo.py, then import it in retrievers/__init__.py
from .base import Hit, Retriever, register

@register("my_algo")
class MyAlgo(Retriever):
    def fit(self, chunks):            # chunks: list[Chunk]; self.params holds the config keys
        ...
        return self
    def search(self, query, k=100):   # best first
        return [Hit(chunk_id, score), ...]
```

Then `configs/my_algo.json`: `{"name": "...", "source": "clauses", "retriever": {"type": "my_algo", ...}}`.
Any registered type can be nested inside `rrf` / `score_fusion` / `rerank`.

## Research menu: what to try and why

Implemented (✅) or next candidates (⬜), with sources.

| | method | family | why it fits this problem |
|---|---|---|---|
| ✅ | **BM25 / BM25+** | sparse lexical | Regulation text is exact-term heavy; proven, near-free baseline (Robertson & Jones). BM25+ fixes under-scoring of long paragraphs. |
| ✅ | **TF-IDF char n-grams** | sparse lexical | Robust to PDF hyphenation/spelling variants ("retro-reflector" / "retroreflector"). Slow in pure numpy. |
| ✅ | **Dense bi-encoder** (bge, e5, gte, nomic, Qwen3-Embedding) | dense | Catches paraphrase ("braking indication" ↔ "stop lamp"). Exact search = recall 1.0 for the embedding (ANCE: Xiong et al. 2020). |
| ✅ | **HNSW** (faiss) | ANN index | The standard graph ANN for high recall (Malkov & Yashunin; Wang et al. VLDB 2021 survey). Only needed at scale; here it measures the ANN-vs-exact gap. |
| ✅ | **SPLADE** | learned sparse | Term expansion + inverted-index precision; strong for high-recall retrieval (Yang, SIGIR 2024; code: github.com/eugene-yang/LSR-for-TAR). |
| ✅ | **RRF / score fusion hybrid** | fusion | Sparse and dense fail on different queries; RRF (Cormack et al. 2009, k=60) is the robust default. Legal-retrieval studies find RRF hybrids best on aggregate. |
| ✅ | **Cross-encoder rerank** (bge-reranker, mxbai, ms-marco MiniLM) | multi-stage | Raises precision at the top of the list; recall stays capped by the first stage, so keep `candidates` high. |
| ✅ | **Multi-query pooling** (`Pipeline.pooled`) | query side | One query per function/part/material, fused: no single query covers a whole product. |
| ✅ | **Title-prefixed chunks** | contextual | Each chunk is indexed with its regulation title; a cheap form of Anthropic's "contextual retrieval". |
| ⬜ | **BGE-M3** (dense + sparse + multi-vector in one model) | hybrid model | One model gives all three signals; 8k context fits whole pages. |
| ⬜ | **ColBERTv2 / PLAID** (e.g. via `pylate`) | late interaction | Token-level matching; strong recall/precision balance (Stetina et al. 2024). |
| ⬜ | **LLM query expansion / HyDE** | query side | Have an LLM write the hypothetical requirement text ("The stop lamp shall …") and search with that. It bridges spec vocabulary to regulation vocabulary, and `locate` shows that requirement-like queries are found almost perfectly. Likely the biggest win. |
| ⬜ | **LLM regulation selection** | routing | Pick the applicable regulations first (scope sections, product category), then retrieve inside them. Fixes the R7/R23-vs-R148 confusion and finds R10-style "indirect" regulations. |
| ⬜ | **Scope / cross-reference expansion** | structure | Pull in paragraphs a hit refers to ("as defined in paragraph 3.3.4.2", "UN Regulation No. 48 …"). |
| ⬜ | **Full contextual retrieval** | contextual | Prepend an LLM-written situating sentence per chunk (Anthropic). Reported to work best combined with BM25 + rerank. |
| ⬜ | **DARTH / adaptive nprobe, Filtered-DiskANN** | ANN control | Recall-targeted ANN or metadata-filtered ANN. Only relevant if the corpus grows far beyond ~37k chunks. |

References: Malkov & Yashunin, *HNSW*, TPAMI 2018 · Wang et al., graph ANN survey, VLDB 2021 · Gollapudi et al., *Filtered-DiskANN*, WWW 2023 ·
Chatzakis et al., *DARTH*, SIGMOD 2025 · Kazakovtsev et al., adaptive IVF, BDCC 2025 · Yang, *SPLADE for high recall*, SIGIR 2024 ·
Xiong et al., *ANCE*, 2020 · Stetina et al., *DaReCzech retrieval study*, 2024 · Robertson & Jones, *Simple, proven approaches to text retrieval* ·
Tank, *How can disparate retrieval methods work together*, 2025 · Cormack et al., *Reciprocal Rank Fusion*, SIGIR 2009.
