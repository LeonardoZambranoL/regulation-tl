# In plain words

Takes our best list and adds what the second, section-reading agent found in paragraphs the best list skipped. It finds
more of the experts' requirements (84% instead of 77% on the practice product) but also adds many extras, so it is only
better if the scoring cares much more about finding everything than about avoiding extras.

# Technical

1. A = devansh-writer-faithful-ranked, B = devansh-deliberate-faithful-ranked predictions.
2. `combine.py`: A plus B's requirements from paragraphs not cited by A, then `refine.dedupe`. No new LLM calls.
3. Dev: 388 requirements, req P 0.412 / R 0.842 / F1 0.554 / F2 0.697 (A: 0.505 / 0.768 / 0.610 / 0.696);
   holdout-acpe F2 0.393 (A 0.407).
