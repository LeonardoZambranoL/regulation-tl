# In plain words

The current best list, checked once more against how expert compliance engineers write such lists. Claude rates every requirement 1-5 for whether an expert would include it, using five general rules of what experts leave out: options the product description never mentions ("where the lamp has an adjustable intensity..."), factory-production and approval paperwork, rules that only point to other sections, steps of lab procedures, and jobs of the vehicle rather than the product. Items rated 1-2 are removed. Weakness: the five rules were found by studying our own mistakes on the practice product.

# Technical

1. Input: devansh-llm-clause-filter-writer-ranked predictions.
2. `refine --mode scope --drop-at-or-below 2`
3. Scope ranker (`refine.SCOPE`): `claude-opus-5-5`, effort medium, rates 1-5 whether an expert would list the item;
   leave-out principles: conditional variants for features the spec does not state, conformity-of-production and approval-process rules, pure cross-references, lab-procedure steps without a result, and functions of the vehicle rather than the product; drop 1-2 (the prompt's own definition), dedupe first.
4. Scored with `bench.py` and `req_judge.py` on dev-rear-lamp and holdout-acpe.
