# devansh-faithful-plus-deliberate

Owner: Devansh. **Recall-first variant: the faithful list plus the deliberate agent's extra paragraphs.** Not the final:
same F2 on dev (0.697 vs 0.696) but lower F1 (0.554 vs 0.610) and lower on the unseen case (0.393 vs 0.407). Use it only
if the platform turns out to weigh recall far above precision. See [EXPLAIN.md](EXPLAIN.md).
Run: `python approaches/experiments/devansh-faithful-plus-deliberate/combine.py` (and `--suffix=-holdout-acpe`).
