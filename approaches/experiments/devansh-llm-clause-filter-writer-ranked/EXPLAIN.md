# In plain words

The current best approach plus a gentle final check. After the writer turns each kept rule into single obligations,
a second Claude reviewer rates every item from 1 ("certainly not a real obligation for this product") to 5
("certainly is"). Only the items it is sure are wrong (rated 1) and exact repeats are removed; everything it is unsure
about stays. The earlier, hard yes/no version removed too many real obligations; this version only cuts what it is
confident about.

# Technical

1. Input: `devansh-llm-clause-filter-writer` predictions.
2. Dedupe (`refine.dedupe`): normalised-text repeats per regulation, Jaccard >= 0.9 within a paragraph.
3. Ranker (`refine.rank`): `claude-opus-5-5`, effort medium, structured output `{id, confidence 1-5}`, batches of 30
   sorted by regulation and page, product-neutral criteria (missing function or variant, definition, authority
   procedure, test-procedure step, repeat -> low; construction, markings, values, tests, installation, EMC,
   manufacturer documents -> high). Unrated items count as 5.
4. Keep every item rated 2-5 (cut-off fixed in advance). `outputs/*-refine-report.json` lists the rating histogram and
   how many items other cut-offs would keep, for information only.
5. Scored with `bench.py` and `req_judge.py` on dev-rear-lamp and holdout-acpe; adopted only if requirement F2 improves
   on both.
