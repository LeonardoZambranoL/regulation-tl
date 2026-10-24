Case `dev-rear-lamp`. **Official columns** = the challenge's own scorer (tools/score_local.py) on a mock submission made of the top 190 pooled spec chunks: regulation and page precision / recall / F1, plus `req_R_max`, the ceiling on requirement recall from those chunks. Diagnostics: `R@k`/`MRR` = locate each expected requirement by its text; `page_R@100` = gold pages in the first 100 pooled pages; `reg_R@5` = gold regulations in the top 5. Other sizes N are in the .json.

| pipeline | chunks | reg_P | reg_R | reg_F1 | page_P | page_R | page_F1 | req_R_max | R@1 | R@10 | MRR | page_R@100 | reg_R@5 | fit s | query s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bm25-page | pdf/page | 0.231 | 0.750 | 0.353 | 0.153 | 0.547 | 0.239 | 0.553 | 0.684 | 0.958 | 0.784 | 0.321 | 0.750 | 2.5 | 1.6 |
| bm25 | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.165 | 0.377 | 0.230 | 0.400 | 0.795 | 0.979 | 0.872 | 0.321 | 0.500 | 1.2 | 3.0 |
| bm25+ bigrams | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.158 | 0.358 | 0.220 | 0.389 | 0.858 | 0.984 | 0.910 | 0.283 | 0.500 | 8.1 | 5.3 |
| bm25 (own PDF parser) | pdf/paragraph | 0.214 | 0.750 | 0.333 | 0.153 | 0.340 | 0.211 | 0.316 | 0.732 | 0.979 | 0.838 | 0.283 | 0.500 | 4.1 | 4.6 |
