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
| 25 | `devansh-deliberate-faithful-ranked` | agent reads each section whole (thinking, effort high) and picks exact clauses; faithful writer; ranker | | | | | | paragraph P 0.553 / R 0.736 (classifier 0.508 / 0.785); req F2 dev 0.635, holdout 0.337: not adopted |
| 26 | `devansh-agreement-combo` | keep paragraphs both selectors picked; one-selector ones only if ranker >= 4 | | | | | | agreed paragraphs 80% right, but req F2 dev 0.646, holdout 0.378: not adopted |
| 27 | `devansh-faithful-plus-deliberate` | faithful list + deliberate agent's extra paragraphs (recall-first) | | | | | | req dev P 0.412 / R 0.842 / F1 0.554 / F2 0.697, holdout F2 0.393: not the final |
| 28 | **FINAL = `devansh-writer-faithful-ranked`** | clean submission file + `final.sh <case>` for the held-out case | | | | | | req dev P 0.505 / R 0.768 / F1 0.610 / F2 0.696; holdout 0.407 |
| 29 | **FINAL = `devansh-profile-faithful`** | product profile from spec + exploded-view image used by every step; implicit-obligation candidates (108/121 expert paragraphs reachable vs 98); faithful writer; ranker | | | | | | req dev P 0.457 / R 0.863 / F2 **0.733** (164 TP vs 146), holdout F2 **0.409** (50 TP vs 43); F1 slightly lower |
| 30 | platform uploads | profile-faithful vs faithful on the real judge | | | | | | **profile: F2 69.7%** (P 43.5, R 82.1, F1 56.8); faithful: F2 65.8% (P 47.8, R 72.6, F1 57.6); ranked writer earlier 62.5%. Local judge ~3.7 pts high, consistent |
| 31 | `devansh-profile-faithful-v2` (not adopted) | profile-faithful minus clauses cited at Table / Figure / Appendix labels (error analysis: 2 of 71 such predictions matched, experts cite the numbered clause that refers to the table) + conservative restatement merge; every LLM answer regenerated in its own cache (LLM_CACHE_DIR), run once, scored once | | | | | | req dev P 0.482 / R 0.847 / F1 0.615 / F2 **0.736** (161 TP / 334); holdout P 0.254 / R 0.479 / F1 0.332 / F2 0.407 (45 TP / 177). P and F1 up on both, F2 +0.003 dev / -0.002 holdout: inside run-to-run noise, so the pre-declared 'better on both' rule is not met. Page F2 0.853 / 0.476 (was 0.845 / 0.455). Merge dropped only 0-2 items: too conservative to matter |
| 32 | platform upload v2 -> **FINAL = `devansh-profile-faithful-v2`** | v2 submission on the real judge | | | | | | **F2 72.7%** (P 47.6, R 83.7, F1 60.7) vs profile-faithful 69.7% (P 43.5, R 82.1). Precision and recall both up. Local judge read only 0.9 pts high this time (was 3.7): its gap varies, so do not reject small local differences |
| 33 | v2 on heldout-front-bumper (platform) | the 371-item raw file was uploaded, not the 301-item submission | | | | | | req P 24.0 / R 42.8 / F1 30.7 / F2 37.0; pages P 42.0 / R 54.7; regulations P 100 / R 71.4 (2 of 7 missed by the keyword rules) |
| 34 | `devansh-profile-faithful-v3` | regulations = keyword rules + Claude's picks limited to regulations on the product itself (`union_component`); rest = v2, v2's cache shared | | | | | | dev / ACPE: same regulations as v2, so identical (req F2 0.736 / 0.407). Bumper: + R26, R148 -> 460 requirements (v2 301). Unrestricted Claude picks would add R155/R156 on ACPE and 7 whole-vehicle regulations on the bumper |
| 35 | v3 bumper upload (platform) | 460 requirements, regulations = the expected 7 | | | | | | req P 33.9 / R 75.0 / F1 46.7 / F2 **60.4** (v2 raw 37.0); pages P 51.0 / R 94.3; regulations 100 / 100 |
| 36 | v4: regulation override | `export --regulations` cites only a known list; candidates unchanged when the automatic picks cover it | | | | | | bumper: identical to v3 (R13H gave none); dev / ACPE untouched |
| 37 | v4: skip rationale part | drop items before a regulation's 'II. Text of the Regulation' heading (GTR 9 only) | | | | | | dev / ACPE identical; bumper -14 (GTR 9 explanatory paragraphs with old values) |
| 38 | v4: merge duplicate pairs (adopted) | cross-regulation pairs (Jaccard >= 0.5) + parent / sub-clause pairs, Claude confirms same / general, keeps the device regulation's copy | | | | | | dev P 0.482 -> 0.488, R 0.847 -> 0.853, F2 0.736 -> **0.742**; ACPE identical; bumper -16 (13 GTR 9 <-> R127, 3 R48 <-> R148 colours) |
| 39 | v4: subject check (adopted) | Claude names each item's subject: has / possible / absent; drop absent only | | | | | | dev / ACPE 0 absent (identical); bumper -10 (R127 headform HIC limits, colours of lamps the bumper lacks) |
| 40 | v4: marking re-split (rejected) | marking clauses rewritten: one requirement per marking and per object | | | | | | dev +14 items, 0 new matches (F2 0.727); ACPE -1 match (0.398) |
| 41 | **`devansh-profile-faithful-v4`** | v3 + override + rationale + pairs + subject | | | | | | dev F2 0.742 (v3 0.736), ACPE 0.407 (same); bumper 460 -> 424; expected platform F2 ~62 if the removals were unmatched, ~57 if the 13 GTR 9 / R127 duplicates were expected twice |
| 42 | v4 bumper upload (platform) | 424 requirements | | | | | | req P 34.4 / R 70.2 / F1 46.2 / F2 **58.1** (v3 60.4): ~10 of 36 removals were correct; one expert page lost (GTR 9 rationale pp. 4-18 or R127 p. 36). Experts likely list GTR 9 and R127 copies of the same obligation. **v3 stays the final bumper upload**; no v5 (zero-cost options carry more downside than upside) |

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
