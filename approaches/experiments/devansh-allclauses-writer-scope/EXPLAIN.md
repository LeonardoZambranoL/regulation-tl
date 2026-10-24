# In plain words

Four loops, each fixing one kind of loss. 1) The checklist picks the rulebooks. 2) Claude reads every rule in them, also those without the word "shall", so obligations written as plain specifications are not missed. 3) A writer turns each kept rule into single obligations. 4) Claude rates each one for whether an expert would list it, with five general rules of what experts leave out, and removes the 1-2s. Weakness: reading every rule costs more, and the five rules come from studying our mistakes on the practice product.

# Technical

1. `export` with candidates `all`, neutral reviewer prompt, strict writer (rules selection).
2. `refine --mode scope --drop-at-or-below 2`
3. Scope ranker (`refine.SCOPE`): `claude-opus-5-5`, effort medium, rates 1-5 whether an expert would list the item;
   leave-out principles: conditional variants for features the spec does not state, conformity-of-production and approval-process rules, pure cross-references, lab-procedure steps without a result, and functions of the vehicle rather than the product; drop 1-2 (the prompt's own definition), dedupe first.
4. Scored with `bench.py` and `req_judge.py` on dev-rear-lamp and holdout-acpe.
