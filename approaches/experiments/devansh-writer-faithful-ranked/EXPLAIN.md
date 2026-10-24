# In plain words

Same rules picked as our best approach, but the writer copies each obligation more faithfully. The previous writer
"helpfully" narrowed rules to our product: it turned "for M1 and N1 vehicles" into "for M1 vehicles", kept only half of
"two stop lamps of one kind and one of another", and once even wrote "reversing lamp" where the rule said
"retro-reflector". The scoring robot only counts a requirement when its scope, condition and values match the expert's,
so those near-misses scored zero. This writer keeps the regulation's own subject, scope, every value and every
alternative, and only splits where the regulation itself states separate obligations. Then the 1-5 ranker removes only
items that are certainly not obligations.

# Technical

1. Clause selection: identical to devansh-llm-clause-filter-writer (rules selection, opus 5.5 clause filter, shall-clauses).
2. Writer `write.PROMPTS["faithful"]`: the strict prompt without "keep only the parts that apply to this product",
   plus rule 7 (keep the regulation's scope, subject, values, units, conditions, exceptions, standards and alternatives;
   never narrow to the product's category or substitute its name) and rule 8 (split only where the regulation states
   separate obligations).
3. `refine --mode rank --drop-at-or-below 1` (dedupe + drop only "certainly not").
4. Scored with `bench.py` and `req_judge.py` on dev-rear-lamp and holdout-acpe.
