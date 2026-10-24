Case `dev-rear-lamp`. **Official columns** = the challenge's own scorer (tools/score_local.py) on a mock submission made of the top 190 pooled spec chunks: regulation and page precision / recall / F1, plus `req_R_max`, the ceiling on requirement recall from those chunks. Diagnostics: `R@k`/`MRR` = locate each expected requirement by its text; `page_R@100` = gold pages in the first 100 pooled pages; `reg_R@5` = gold regulations in the top 5. Other sizes N are in the .json.

| pipeline | chunks | reg_P | reg_R | reg_F1 | page_P | page_R | page_F1 | req_R_max | R@1 | R@10 | MRR | page_R@100 | reg_R@5 | fit s | query s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bm25+ bigrams, clauses | select: rules | clauses/paragraph | 1.000 | 1.000 | 1.000 | 0.317 | 0.604 | 0.416 | 0.621 | 0.905 | 0.984 | 0.942 | 0.547 | 1.000 | 0.7 | 0.5 |
| bm25+ bigrams, clauses | select: llm | clauses/paragraph | 1.000 | 1.000 | 1.000 | 0.317 | 0.604 | 0.416 | 0.621 | 0.905 | 0.984 | 0.942 | 0.547 | 1.000 | 12.4 | 0.6 |
| rrf(bm25+ bigrams + tfidf-char), clauses | select: rules | clauses/paragraph | 1.000 | 1.000 | 1.000 | 0.308 | 0.604 | 0.408 | 0.600 | 0.895 | 0.989 | 0.933 | 0.604 | 1.000 | 3.9 | 20.3 |
| bm25+ bigrams, clauses | select: scope top 4 | clauses/paragraph | 0.500 | 0.500 | 0.500 | 0.333 | 0.453 | 0.384 | 0.526 | 0.505 | 0.537 | 0.519 | 0.547 | 0.500 | 0.6 | 0.3 |
| bm25+ bigrams, whole pages | select: rules | pdf/page | 1.000 | 1.000 | 1.000 | 0.226 | 0.811 | 0.354 | 0.811 | 0.821 | 0.979 | 0.886 | 0.604 | 1.000 | 11.3 | 0.2 |
| rrf(bm25plus_bigrams+tfidf_char) | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.200 | 0.472 | 0.281 | 0.500 | 0.832 | 0.979 | 0.893 | 0.283 | 0.500 | 85.1 | 175.4 |
| bm25 no title prefix | clauses/paragraph | 0.188 | 0.750 | 0.300 | 0.186 | 0.453 | 0.264 | 0.479 | 0.763 | 0.989 | 0.854 | 0.321 | 0.750 | 3.6 | 2.9 |
| tfidf-char3-5 | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.183 | 0.453 | 0.261 | 0.500 | 0.758 | 0.979 | 0.849 | 0.302 | 0.500 | 35.4 | 190.3 |
| score_fusion(bm25plus_bigrams+tfidf_word) | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.183 | 0.415 | 0.254 | 0.416 | 0.795 | 0.984 | 0.877 | 0.283 | 0.500 | 6.5 | 7.6 |
| rrf(bm25+bm25plus_bigrams+tfidf_word) | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.179 | 0.415 | 0.250 | 0.426 | 0.811 | 0.979 | 0.883 | 0.283 | 0.500 | 8.1 | 9.7 |
| bm25+ bigrams, whole pages | pdf/page | 0.286 | 1.000 | 0.444 | 0.158 | 0.566 | 0.247 | 0.621 | 0.753 | 0.958 | 0.841 | 0.321 | 0.500 | 6.2 | 1.4 |
| rrf(bm25plus_bigrams+tfidf_word) | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.174 | 0.396 | 0.241 | 0.416 | 0.832 | 0.979 | 0.893 | 0.302 | 0.500 | 7.2 | 6.9 |
| bm25-page | pdf/page | 0.231 | 0.750 | 0.353 | 0.153 | 0.547 | 0.239 | 0.553 | 0.684 | 0.958 | 0.784 | 0.321 | 0.750 | 2.5 | 1.6 |
| rrf(bm25plus_bigrams_page+bm25_page) | pdf/page | 0.286 | 1.000 | 0.444 | 0.153 | 0.547 | 0.239 | 0.553 | 0.716 | 0.963 | 0.814 | 0.340 | 0.750 | 3.5 | 1.9 |
| bm25 k1=1.5 b=0.9 (favour short clauses) | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.169 | 0.377 | 0.234 | 0.400 | 0.747 | 0.989 | 0.846 | 0.340 | 0.500 | 2.5 | 3.8 |
| bm25 | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.165 | 0.377 | 0.230 | 0.400 | 0.795 | 0.979 | 0.872 | 0.321 | 0.500 | 1.2 | 3.0 |
| bm25 k1=0.9 b=0.4 (BEIR/Anserini default) | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.156 | 0.377 | 0.221 | 0.389 | 0.821 | 0.979 | 0.887 | 0.302 | 0.500 | 3.8 | 4.2 |
| bm25+ bigrams | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.158 | 0.358 | 0.220 | 0.389 | 0.858 | 0.984 | 0.910 | 0.283 | 0.500 | 8.1 | 5.3 |
| tfidf-word | clauses/paragraph | 0.214 | 0.750 | 0.333 | 0.157 | 0.358 | 0.218 | 0.389 | 0.784 | 0.979 | 0.860 | 0.321 | 0.500 | 3.3 | 3.3 |
| bm25 (own PDF parser) | pdf/paragraph | 0.214 | 0.750 | 0.333 | 0.153 | 0.340 | 0.211 | 0.316 | 0.732 | 0.979 | 0.838 | 0.283 | 0.500 | 4.1 | 4.6 |
