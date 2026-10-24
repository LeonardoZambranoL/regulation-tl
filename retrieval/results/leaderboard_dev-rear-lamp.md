Case `dev-rear-lamp`. locate: R@k / MRR per expected requirement. spec: page recall within the first N pooled pages, regulation recall within the top N regulations.

| pipeline | chunks | R@1 | R@5 | R@10 | R@50 | MRR | page_R@25 | page_R@50 | page_R@100 | page_R@200 | reg_R@3 | reg_R@5 | reg_R@10 | fit s | query s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bm25 | clauses/paragraph | 0.795 | 0.953 | 0.979 | 0.995 | 0.872 | 0.057 | 0.094 | 0.321 | 0.528 | 0.250 | 0.500 | 0.750 | 3.9 | 4.8 |
| bm25-page | pdf/page | 0.684 | 0.911 | 0.958 | 1.000 | 0.784 | 0.113 | 0.208 | 0.321 | 0.566 | 0.500 | 0.750 | 0.750 | 2.9 | 1.5 |
| bm25 (own PDF parser) | pdf/paragraph | 0.732 | 0.942 | 0.979 | 0.989 | 0.838 | 0.075 | 0.170 | 0.283 | 0.547 | 0.500 | 0.500 | 0.750 | 3.6 | 5.5 |
| bm25+ bigrams | clauses/paragraph | 0.858 | 0.958 | 0.984 | 1.000 | 0.910 | 0.038 | 0.094 | 0.283 | 0.509 | 0.250 | 0.500 | 0.750 | 7.1 | 6.4 |
