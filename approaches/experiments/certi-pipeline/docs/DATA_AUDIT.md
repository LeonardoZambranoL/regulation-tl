# Data Audit Report (`docs/DATA_AUDIT.md`)

## 1. Corpus & Index Summary
- **Index file**: `regulations/index.json` (56 regulations; 56 `base` versions, 36 `latest` versions)
- **Parsed clause JSONs**: `data-ingestion/clauses/*.json` (56 files, **26,769** total clause blocks)
- **Precomputed embeddings**: `data-ingestion/embeddings/gemini-embedding-2-preview_d768_n26769.npz` (shape `[26769, 768]`, dtype `float16`, 1:1 aligned with clause count: `True`)
- **Regulations in `index.json` missing from `data-ingestion/clauses/`**: `[]`
- **Regulations in `data-ingestion/clauses/` missing from `index.json`**: `[]`
- **Version role check**: Every parsed JSON file in `data-ingestion/clauses/` matches the `base` version `version_label` in `index.json` (`True`).

## 2. Schema of Parsed Clause Nodes
Each `data-ingestion/clauses/<REG>_base.json` file contains:
- `regulation` (`str`): e.g. `"UN R48"`
- `version` (`str`): base `version_label`, e.g. `"9.3.0"`
- `clauses` (`list[dict]`):
  - `paragraph` (`str | null`): clause label with slash-separated section/annex hierarchy, e.g. `"5.15"`, `"Annex 4 / 1.2"`, `"Annex 3 / Part B / 2.1"`, `"Table 1"`, `"Figure 1"`, or `null` for preamble blocks.
  - `pages` (`list[int]`): 1-based PDF page numbers spanned by the block (extracted from `=== PDF PAGE N ===` markers).
  - `text` (`str`): layout-preserved UTF-8 text (headers/footers stripped, multi-space tabular layout retained).
  - `review_flags` (`list[str]`, optional): parser boundary flags when present.

### Structural & Quality Counts Across All 56 Regulations
- **Total clause blocks**: 26,769
- **Preamble / `paragraph: null` blocks**: 56
- **Blocks missing `pages`**: 0
- **Multi-page blocks (`len(pages) > 1`)**: 1,435
- **Annex-prefixed blocks (`Annex ...`)**: 14,566
- **Standalone `Table N` blocks**: 292
- **Standalone `Figure N` blocks**: 575

### Parser Review Flags (`review_flags`)
| Flag | Count | Cause & Impact |
|---|---|---|
| `ambiguous_numbered_line` | 1,014 | Parser heuristic boundary or inline table/list numbering |
| `check_table_or_figure_extent` | 867 | Parser heuristic boundary or inline table/list numbering |
| `duplicate_numbered_line` | 556 | Parser heuristic boundary or inline table/list numbering |
| `missing_parent_clause` | 337 | Parser heuristic boundary or inline table/list numbering |
| `heading_without_terminal_dot` | 294 | Parser heuristic boundary or inline table/list numbering |
| `numbering_moves_backwards` | 153 | Parser heuristic boundary or inline table/list numbering |
| `ambiguous_annex_heading` | 152 | Parser heuristic boundary or inline table/list numbering |
| `ambiguous_number_in_table_or_figure` | 126 | Parser heuristic boundary or inline table/list numbering |
| `check_section_boundary` | 111 | Parser heuristic boundary or inline table/list numbering |

## 3. Page & Paragraph Convention Comparison vs. `dev-rear-lamp/expected.json`
- **Dev gold requirements**: 190 requirements across 4 regulations (`UN R148`: 63, `UN R48`: 56, `UN R150`: 39, `UN R10`: 32)
- **Page convention**: Both `data-ingestion/clauses/*.json` and `expected.json` use **1-based PDF page indices** (`page >= 1`).
- **Paragraph normalisation**: Official `score_local._paragraph_key()` normalises case, commas, colons, parentheses, and `/` separators (`"Annex 4 / 1.2"` -> `"annex 4 1.2"`, matching `"Annex 4, 1.2"`).
- **Exact match (normalized paragraph + `pages[0] == gold.page`)**: 165 / 190 (86.8%)
- **Paragraph match where `gold.page` is in `clause.pages[1:]` (multi-page clause)**: 0 / 190
- **Paragraph match where `gold.page` differs by 1 from `clause.pages`**: 0 / 190
- **Gold paragraph not a top-level block in `clauses/*.json` (merged into parent block)**: 25 / 190 (of which 2 have their parent paragraph in `clauses/*.json`)

### Root Cause of Unmatched Gold Paragraphs (Critical Finding!)
We identified three deterministic parser issues in `data-ingestion/txt_to_clauses.py` that explain all 25 unmatched gold paragraphs in `dev-rear-lamp`:
1. **False Annex Heading Match inside Tables (`UN_R150_base.json`)**: In `UN R150` page 14 (inside `Table 1`), a table row starts with `Annex 5   Shapes and dimensions: visual inspection   x x x`. Because `ANNEX` regex in `txt_to_clauses.py` matched `^Annex\s+(\d+[A-Z]?)[ :\-]+([A-Z].*)$` without checking for tabular spacing (`\S\s{3,}\S`), the parser jumped to `annex = '5'` on page 14! Then, because `txt_to_clauses.py` ignores any subsequent `Annex N` where `N <= 5` (`number <= int(annex)`), **real Annexes 1, 2, 3, and 4 (pages 19-32) were all mislabeled as `Annex 5 / ...`** in `UN_R150_base.json`! Similar false table-row Annex jumps occur in 11 other regulations (`UN_R104`, `UN_R107`, `UN_R10`, `UN_R116`, `UN_R161`, `UN_R162`, `UN_R163`, `UN_R40`, `UN_R42`, `UN_R51`, `UN_R62`).
2. **Tables Detached from Enclosing Paragraph (`Table N`)**: In `txt_to_clauses.py`, `Table 3` and `Table A6-1` are emitted with bare label `"Table 3"` / `"Table A6-1"` without their enclosing clause prefix (`5.1.4.4.1. Table 3` or `Annex 6 Part 6 3. Table A6-1`).
3. **Sub-clauses Merged into Parent Block (`ambiguous_numbered_line`)**: In `txt_to_clauses.py` (line 100), a numbered line is rejected and merged into the preceding block whenever the line contains 3+ consecutive spaces (`\S\s{3,}\S`) or starts with a lowercase letter (e.g., `3.1.` and `3.2.` inside `Annex 6 / Part 6 / 3`).

**Verification**: When we apply our deterministic Stage 0 Annex/Part/Table/Sub-clause repair (`certi/stages/stage0_load.py`), **190 / 190 (100.0%)** of `dev-rear-lamp` gold paragraphs and **94 / 94 (100.0%)** of `holdout-acpe` gold paragraphs match!

#### Unmatched Gold Paragraphs in `dev-rear-lamp`:
| Gold ID | Regulation | Gold Page | Gold Paragraph | Normalized Key | Parent Block in `clauses` |
|---|---|---|---|---|---|
| `G-0029` | UN R150 | 12 | `5.1.4.4.1. Table 3` | `5.1.4.4.1 table 3` | `5.1.4.4` |
| `G-0036` | UN R150 | 12 | `5.1.4.4.1. Table 3` | `5.1.4.4.1 table 3` | `5.1.4.4` |
| `G-0038` | UN R150 | 25 | `Annex 2 1.2` | `annex 2 1.2` | `None` |
| `G-0039` | UN R150 | 28 | `Annex 4 Part 1 1.2` | `annex 4 part 1 1.2` | `None` |
| `G-0042` | UN R150 | 28 | `Annex 4 Part 1 1.3` | `annex 4 part 1 1.3` | `None` |
| `G-0043` | UN R150 | 33 | `Annex 5 1.1` | `annex 5 1.1` | `None` |
| `G-0044` | UN R150 | 42 | `Annex 6 Part 1 3` | `annex 6 part 1 3` | `None` |
| `G-0045` | UN R150 | 42 | `Annex 6 Part 2 1.2` | `annex 6 part 2 1.2` | `None` |
| `G-0048` | UN R150 | 45 | `Annex 6 Part 4 1` | `annex 6 part 4 1` | `None` |
| `G-0049` | UN R150 | 45 | `Annex 6 Part 4 1` | `annex 6 part 4 1` | `None` |
| `G-0050` | UN R150 | 45 | `Annex 6 Part 4 3` | `annex 6 part 4 3` | `None` |
| `G-0051` | UN R150 | 45 | `Annex 6 Part 4 4.1` | `annex 6 part 4 4.1` | `None` |
| `G-0052` | UN R150 | 46 | `Annex 6 Part 6 3` | `annex 6 part 6 3` | `None` |
| `G-0053` | UN R150 | 46 | `Annex 6 Part 6 3. Table A6-1` | `annex 6 part 6 3 table a6-1` | `None` |
| `G-0152` | UN R10 | 98 | `Annex 9 3.1` | `annex 9 3.1` | `None` |
| `G-0153` | UN R10 | 98 | `Annex 9 3.1` | `annex 9 3.1` | `None` |
| `G-0154` | UN R10 | 98 | `Annex 9 3.1` | `annex 9 3.1` | `None` |
| `G-0155` | UN R10 | 98 | `Annex 9 3.1` | `annex 9 3.1` | `None` |
| `G-0157` | UN R10 | 108 | `Annex 10 2` | `annex 10 2` | `None` |
| `G-0158` | UN R10 | 108 | `Annex 10 2` | `annex 10 2` | `None` |
| `G-0228` | UN R148 | 35 | `Annex 3 1.2` | `annex 3 1.2` | `None` |
| `G-0229` | UN R148 | 35 | `Annex 3 1.2` | `annex 3 1.2` | `None` |
| `G-0230` | UN R148 | 47 | `Annex 8 1.2.1` | `annex 8 1.2.1` | `None` |
| `G-0232` | UN R148 | 47 | `Annex 8 1.2.2` | `annex 8 1.2.2` | `None` |
| `G-0234` | UN R148 | 47 | `Annex 8 2.1` | `annex 8 2.1` | `None` |

### Holdout Case (`holdout-acpe`, UN R175) Check
- **Holdout gold requirements**: 94
- **Exact paragraph match in `UN_R175_base.json`**: 94 / 94 (100.0%)
- **Merged into parent block in `UN_R175_base.json`**: 0 / 94

## 4. Fix / Normalisation Implemented in Stage 0 Loader
1. **Sub-clause Recovery (In-Memory Sub-splitting)**: When loading `data-ingestion/clauses/*.json` in Stage 0 (`certi/stages/stage0_load.py`), we scan every block's `raw_text`/`text` for embedded numbered sub-clauses (`^\s*(\d+(?:\.\d+)+)\.?\s+`) that were merged due to `ambiguous_numbered_line` spacing, and expose them both as sub-clause anchors with their exact paragraph numbers (inheriting the parent's `Annex / Part / Appendix` prefix and page number) AND keep parent context intact.
2. **Official Paragraph Formatting**: We strip `/` separators into standard comma/space format (`Annex 8, 2.1`) and verify with `score_local._paragraph_key`.
3. **1-Based Base Page Citation**: Every requirement strictly cites the `base` version's `version_label` from `index.json` and the 1-based PDF page.

## 5. Per-Regulation Clause Counts (Dev & Holdout Target Regulations Highlighted)
| Regulation | Base Version | Clauses | Null Para | Flagged | Page Range |
|---|---|---|---|---|---|
| UN GTR 9 | `0.3.0` | 630 | 1 | 117 | 1-131 |
| **UN R10** | `7.2.0` | 895 | 1 | 189 | 1-147 |
| UN R100 | `5.0.0` | 601 | 1 | 83 | 1-92 |
| UN R101 | `1.12.0` | 1110 | 1 | 74 | 1-103 |
| UN R102 | `0.0.0` | 214 | 1 | 7 | 1-17 |
| UN R103 | `0.3.0` | 128 | 1 | 20 | 1-12 |
| UN R104 | `0.9.0` | 169 | 1 | 9 | 1-14 |
| UN R107 | `11.1.0` | 1361 | 1 | 155 | 1-134 |
| UN R114 | `0.0.0` | 228 | 1 | 27 | 1-27 |
| UN R116 | `1.3.0` | 468 | 1 | 43 | 1-43 |
| UN R123 | `2.1.0` | 518 | 1 | 75 | 1-53 |
| UN R127 | `4.3.0` | 371 | 1 | 86 | 1-52 |
| UN R128 | `0.11.0` | 229 | 1 | 60 | 1-48 |
| UN R131 | `2.3.0` | 303 | 1 | 38 | 1-31 |
| UN R132 | `1.0.0` | 583 | 1 | 48 | 1-50 |
| UN R137 | `4.0.0` | 452 | 1 | 32 | 1-42 |
| UN R13H | `2.1.0` | 663 | 1 | 64 | 1-63 |
| **UN R148** | `1.6.0` | 424 | 1 | 60 | 1-48 |
| UN R149 | `1.6.0` | 750 | 1 | 136 | 1-84 |
| **UN R150** | `1.2.1` | 521 | 1 | 87 | 1-54 |
| UN R152 | `2.5.0` | 296 | 1 | 35 | 1-36 |
| UN R155 | `0.2.0` | 172 | 1 | 32 | 1-24 |
| UN R156 | `0.1.0` | 148 | 1 | 2 | 1-11 |
| UN R157 | `1.4.0` | 650 | 1 | 72 | 1-87 |
| UN R161 | `0.5.0` | 217 | 1 | 13 | 1-17 |
| UN R162 | `0.6.0` | 176 | 1 | 14 | 1-19 |
| UN R163 | `0.3.0` | 285 | 1 | 22 | 1-26 |
| UN R164 | `0.0.0` | 112 | 1 | 3 | 1-9 |
| UN R171 | `1.1.0` | 851 | 1 | 57 | 1-85 |
| UN R174 | `1.0.1` | 166 | 1 | 14 | 1-13 |
| **UN R175** | `0.1.0` | 189 | 1 | 12 | 1-17 |
| UN R19 | `4.10.0` | 430 | 1 | 39 | 1-48 |
| UN R23 | `0.22.0` | 164 | 1 | 18 | 1-17 |
| UN R26 | `4.0.0` | 216 | 1 | 8 | 1-17 |
| UN R3 | `2.17.0` | 203 | 1 | 18 | 1-26 |
| UN R32 | `0.1.0` | 102 | 1 | 25 | 1-16 |
| UN R37 | `3.48.0` | 258 | 1 | 15 | 1-26 |
| UN R38 | `0.19.0` | 184 | 1 | 17 | 1-16 |
| UN R39 | `2.1.0` | 182 | 1 | 18 | 1-13 |
| UN R40 | `1.1.0` | 338 | 1 | 41 | 1-31 |
| UN R42 | `0.2.0` | 100 | 1 | 7 | 1-8 |
| UN R43 | `1.12.0` | 1810 | 1 | 214 | 1-154 |
| **UN R48** | `9.3.0` | 1193 | 1 | 60 | 1-122 |
| UN R49 | `7.3.1` | 2000 | 1 | 317 | 1-363 |
| UN R51 | `3.10.0` | 585 | 1 | 91 | 1-67 |
| UN R53 | `4.0.0` | 551 | 1 | 43 | 1-45 |
| UN R6 | `2.0.0` | 215 | 1 | 8 | 1-25 |
| UN R62 | `1.0.0` | 77 | 1 | 15 | 1-8 |
| UN R64 | `3.1.0` | 175 | 1 | 13 | 1-14 |
| UN R67 | `4.2.0` | 1338 | 1 | 94 | 1-123 |
| UN R7 | `3.0.0` | 241 | 1 | 9 | 1-28 |
| UN R79 | `4.11.0` | 769 | 1 | 50 | 1-74 |
| UN R83 | `9.0.0` | 672 | 1 | 118 | 1-101 |
| UN R89 | `0.3.0` | 415 | 1 | 14 | 1-25 |
| UN R92 | `2.0.0` | 160 | 1 | 18 | 1-15 |
| UN R94 | `5.1.0` | 511 | 1 | 48 | 1-54 |
