# Devansh's experiment log

What was tried, in order, what changed, and what it scored on `dev-rear-lamp`. Newest at the bottom. Scores marked
**team bench** come from `approaches/benchmarking/bench.py` (official scorer + F2, recorded in `approaches/leaderboard.json`);
the others from this folder's own `src/retrieval/bench.py` / `oracle.py` with the same official scorer.

Glossary: *page P/R* = precision/recall of cited (regulation, version, page), where a right paragraph also counts;
*F2* = 5PR / (4P + R), recall-weighted, the team's ranking metric; *req_R_max* = share of gold requirements whose page
or paragraph we cite, a ceiling for the platform's requirement-level recall.

## 2026-10-24

| # | experiment / config | change | page P | page R | page F1 | page F2 | reg F1 | verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | `bm25` (clauses, N=190) | baseline: BM25 over the team's clauses, spec -> pooled queries | 0.165 | 0.377 | 0.230 | 0.30 | 0.33 | starting point |
| 2 | `bm25plus_bigrams` | BM25+ with bigrams | 0.158 | 0.358 | 0.220 | 0.29 | 0.33 | best at locating a known requirement (MRR 0.91), not better from the spec |
| 3 | `bm25_page` / `bm25plus_bigrams_page` | whole PDF pages instead of clauses | 0.158 | 0.566 | 0.247 | 0.37 | 0.44 | more recall per citation |
| 4 | k1/b tuning, no title prefix, tf-idf word/char, RRF and score fusion of lexical methods | 10 variants | 0.15-0.20 | 0.36-0.47 | 0.22-0.28 | | 0.30-0.33 | +/-3 points: the index is not the bottleneck |
| 5 | `oracle.py` | perfect regulation selection (cheating) | 0.31 | 0.60 | 0.41 | | 1.00 | selection is the biggest lever |
| 6 | `oracle.py` | perfect regs + every "shall" clause | 0.20 | 1.00 | 0.34 | | 1.00 | all gold requirements are among about 1,200 clauses: the task becomes classification |
| 7 | `regselect` methods | rules / LLM / retrieval vote / scope-BM25 | | | | | 1.00 / 1.00 / 0.75 / 0.50 | rules and LLM both pick exactly R48, R148, R150, R10 |
| 8 | **`devansh`** (team bench) | rules selection + bm25+ bigrams on clauses, N=190 | 0.317 | 0.604 | 0.416 | **0.511** | 1.00 | first leaderboard entry |
| 9 | `export --sweep` | submission size under F2 | | | | 0.43-0.58 | | pages peak at N=150; clauses flat at 0.52-0.54 from N=190 to 1000 |
| 10 | **`devansh-pages-n150`** (team bench) | selection + bm25+ bigrams on whole pages, N=150 | 0.280 | 0.793 | 0.414 | **0.580** | 1.00 | best without an LLM |
| 11 | **`devansh-llm-classifier`** (team bench) | selection + Claude (opus 5.5, effort medium) keeps / drops each of 1,240 "shall" clauses | 0.542 | 0.981 | 0.698 | **0.844** | 1.00 | big jump: classification beats retrieval |
| 12 | `risk.json` for all three | declared what each one tuned on the dev case: devansh medium, devansh-pages-n150 **high** (N fitted by sweep), devansh-llm-classifier medium | | | | | | shown on the dashboard; prefer the lower-risk approach when scores are close |
| 13 | clause-level F2 (all approaches, `dashboard_rows.py`) | stricter metric: cited paragraphs vs gold paragraphs | | | | | | llm-classifier 0.619 (98/121 gold clauses), devansh 0.148, pages-n150 0 (cites no paragraphs) |

Not run yet: dense / HNSW / hybrid-with-dense (waiting for shared embeddings; CPU encoding takes 75-100 min), SPLADE,
cross-encoder rerank.

## Lessons

- Fix *which regulations* first; then *which clauses*; search quality matters least.
- Under F2, recall dominates: whole pages and an inclusive classifier both win by covering more gold pages.
- Everything is tuned on one labelled case. Prefer general rules / prompts over size cut-offs tuned to it.

## Next

1. Raise classifier precision (308 kept vs 190 gold): effort high, a second verification pass, annex handling.
2. Split kept clauses into single obligations (the platform's requirement-level score).
3. LLM regulation selection as the default once the held-out spec is out (less hand-tuned than the rules).
