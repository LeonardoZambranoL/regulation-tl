# In plain words

The same checklist picks the rulebooks (4 of 55). Then a search engine, a smarter Ctrl+F that scores how well the
words of a page match the words of the product description, ranks every page of those rulebooks. The 150 best-matching
pages are handed in. No AI reads anything, so it is free and gives the same answer every time. But matching words cannot
tell which rules really apply, and the number 150 was chosen by trying sizes on the practice case, so it may not carry
over to a new product.

# Technical

1. Regulation selection: `regselect` `combined` (rules + supersession + vehicle-category filters): R48, R148, R150, R10.
2. Corpus: own PyMuPDF parser, one chunk per PDF page of the selected regulations, regulation title prefixed.
3. Queries: `spec_queries()` builds about 25 from `spec.md` (product, functions, parts, material rows, part x product,
   whole spec).
4. Retriever: BM25+ (k1 1.2, b 0.75, delta 1) over unigrams + bigrams with stop words removed; each query's top 400
   fused with reciprocal rank fusion (k0 60).
5. Output: top N = 150 pages, one requirement per page, no paragraph. N chosen by `export --sweep` on dev (F2 peak),
   hence overfit risk high. Dev: page P 0.28 / R 0.79 / F2 0.580, clause F2 0 (no paragraphs).
