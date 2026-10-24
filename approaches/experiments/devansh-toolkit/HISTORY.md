# Devansh's experiment log

Names: `devansh-toolkit` = shared code (not ranked); `devansh-bm25-clauses-top190`, `devansh-bm25-pages-top150`,
`devansh-llm-clause-filter` = ranked experiments. Older rows use the names they had then.

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
| 8 | **`devansh-bm25-clauses-top190`** (team bench, first named `devansh`) | rules selection + bm25+ bigrams on clauses, N=190 | 0.317 | 0.604 | 0.416 | **0.511** | 1.00 | first leaderboard entry |
| 9 | `export --sweep` | submission size under F2 | | | | 0.43-0.58 | | pages peak at N=150; clauses flat at 0.52-0.54 from N=190 to 1000 |
| 10 | **`devansh-bm25-pages-top150`** (team bench) | selection + bm25+ bigrams on whole pages, N=150 | 0.280 | 0.793 | 0.414 | **0.580** | 1.00 | best without an LLM |
| 11 | **`devansh-llm-clause-filter`** (team bench) | selection + Claude (opus 5.5, effort medium) keeps / drops each of 1,240 "shall" clauses | 0.542 | 0.981 | 0.698 | **0.844** | 1.00 | big jump: classification beats retrieval |
| 12 | `risk.json` for all three | declared what each one tuned on the dev case: devansh-bm25-clauses-top190 medium, devansh-bm25-pages-top150 **high** (N fitted by sweep), devansh-llm-clause-filter medium | | | | | | shown on the dashboard; prefer the lower-risk approach when scores are close |
| 13 | clause-level F2 (all approaches, `dashboard_rows.py`) | stricter metric: cited paragraphs vs gold paragraphs | | | | | | llm-clause-filter 0.619 (98/121 gold clauses), bm25-clauses-top190 0.148, bm25-pages-top150 0 (cites no paragraphs) |
| 14 | re-benchmarked all three under the shared evaluator id (line-ending fix in bench.py) | bench.py now records clause level | | | | | | same scores; one table with everyone's runs |
| 15 | renamed for clarity | `devansh` -> code in `devansh-toolkit` + run in `devansh-bm25-clauses-top190`; `devansh-pages-n150` -> `devansh-bm25-pages-top150`; `devansh-llm-classifier` -> `devansh-llm-clause-filter` (history migrated, run ids unchanged) | | | | | | |
| 16 | plain-language explanations | EXPLAIN.md for all three; Explain buttons on both dashboards | | | | | | |
| 17 | **`devansh-llm-clause-filter-multiagent`** (team bench) | same rules selection; agents A (strict) + B (completeness auditor) review all 1,240 clauses, C adjudicates the 141 disagreements (kept 46) -> 354 | 0.500 | 0.981 | | **0.823** | 1.00 | recall unchanged, precision down: the extra 46 were not in the gold set |
| 18 | **`devansh-dynregex-llm-clause-filter`** (team bench) | Claude writes regexes from the spec only (no hand rules) -> 8 regulations (all 4 gold + R128, R149, R37, R43); one agent over 2,600 clauses -> 397 | 0.409 | 0.981 | | **0.767** | 0.80 | same recall with no hand-written rules; agent rejected R37 / R43 but kept R128 / R149 clauses (reg P 0.67) |
| 19 | **`devansh-dynregex-llm-clause-filter-multiagent`** (team bench) | dynamic regex + three agents (A 397, B 676 yes, 281 disputed, C kept 51) -> 447 | 0.364 | 0.981 | | **0.732** | 0.80 | lowest precision of the LLM variants |
| 20 | analysis | why multi-agent cannot raise recall | | | | | | 23 of 121 gold clauses (19%) are not "shall" candidates at all (5 not even parsed): clause recall is capped at 0.81 before any agent reads anything. Next: widen candidates (clauses without shall/must, table rows, parent context) |
| 21 | **`devansh-llm-clause-filter-writer-refined`** | writer + product-neutral verifier + dedupe (328 -> 191 requirements) | | | | | | req F2 dev 0.568 (writer 0.676), holdout 0.361 (0.390); req P 0.448 -> 0.565 but R 0.774 -> 0.568, F1 unchanged: not adopted |
| 22 | **`devansh-llm-clause-filter-writer-ranked`** | writer + ranker (Claude rates 1-5, drop only the 1s; cut-off fixed in advance) + dedupe | | | | | | req F2 dev 0.676 -> **0.690**, holdout 0.390 -> **0.406**; precision up, no match lost: **adopted, new best** |
| 23 | `devansh-writer-ranked-scope`, `devansh-allclauses-writer-scope` | scope ranker with five expert leave-out principles (drop 1-2) on the best output / on wide candidates + writer | | | | | | req F2 dev 0.549 / 0.533, holdout 0.371 / 0.350 (best 0.690 / 0.406): cut too many real matches, **not adopted** |
| 24 | **`devansh-writer-faithful-ranked`** | writer keeps the regulation's own scope, subject, values and alternatives (no narrowing to the product) + ranker | | | | | | req F2 dev **0.696** (P 0.505, R 0.768), holdout **0.407**; clause F2 dev 0.619 -> 0.708: **adopted, new best** |

Not run yet: dense / HNSW / hybrid-with-dense (waiting for shared embeddings; CPU encoding takes 75-100 min), SPLADE,
cross-encoder rerank.

## 2026-10-24: shared Gemini vector database (em_ experiments)

New retriever `shared_db` (team LanceDB, `gemini-embedding-2-preview` 768d, query embeddings cached) and candidate mode
`shall+db` (shall clauses + the database's 300 closest non-shall clauses). Dev page F2 / unseen clause recall:

| em_ experiment | base | em_ |
|---|---|---|
| em_devansh-dense-clauses-top190 | 0.511 / 0.789 | 0.405 / 0.632 |
| em_devansh-dense-pages-top150 | 0.580 / not run | 0.483 / 0.035 |
| em_devansh-llm-clause-filter | 0.844 / 0.737 | 0.828 / 0.754 |
| em_devansh-dynregex-llm-clause-filter | 0.767 / 0.842 | 0.761 / 0.842 |
| em_devansh-dynregex-neutral (base: dynregex-allclauses-neutral; shall + 300 db instead of all clauses) | 0.694 / 0.860 | 0.813 / 0.789 |

Lesson: as a ranker the Gemini embeddings are worse than BM25+ here; as a candidate widener they lift clause recall
(dev 0.81 -> 0.84 / 0.86) at a small precision cost, so Robust scores barely move. Replacing "judge every clause" with "shall + 300 database
clauses" (neutral prompt) raises precision a lot (dev page F2 0.694 -> 0.813) for some recall: Robust 0.777 -> 0.801.

## 2026-10-24: requirement writer (the platform's requirement level)

Platform score of the uploaded devansh-llm-clause-filter file: requirements P 0.334 / R 0.542 / F2 0.482 (pages R 0.98,
regulations 1.0). Cause: one raw clause per requirement, while the experts list single obligations, matched one to one.
New `retrieval/write.py` rewrites each kept clause into 0..n one-sentence obligations; new local judge
`approaches/benchmarking/req_judge.py` (reproduces the platform within one match). Dev req F2: raw 0.487, writer 0.604,
strict writer **0.676** (devansh-llm-clause-filter-writer). Remaining error is mostly clause selection.

## Lessons

- Fix *which regulations* first; then *which clauses*; search quality matters least.
- Under F2, recall dominates: whole pages and an inclusive classifier both win by covering more gold pages.
- Everything is tuned on one labelled case. Prefer general rules / prompts over size cut-offs tuned to it.

## Next

1. Raise classifier precision (308 kept vs 190 gold): effort high, a second verification pass, annex handling.
2. Split kept clauses into single obligations (the platform's requirement-level score).
3. LLM regulation selection as the default once the held-out spec is out (less hand-tuned than the rules).
