# In plain words

Two different ways of choosing the rules (one judges rules one by one, the other reads whole sections and thinks)
vote. Where both chose the same paragraph, its requirements are kept; where only one did, a requirement is kept only if
the reviewer was fairly sure it is a real obligation (4 or 5 out of 5). Agreement is very reliable (8 of 10 agreed
paragraphs are the experts'), but dropping the disputed ones also lost real requirements, so it did not beat the best.

# Technical

1. Inputs: `devansh-writer-faithful-ranked` (A) and `devansh-deliberate-faithful-ranked` (B) predictions.
2. `combine.py`: keep A's requirements in paragraphs of A and B; elsewhere keep A's or B-only requirements with ranker
   confidence >= 4. No new LLM calls.
3. Dev: agreed paragraphs 99 (paragraph precision 0.80 vs 0.51); req F2 0.646 (P 0.516, R 0.689) vs best 0.696.
