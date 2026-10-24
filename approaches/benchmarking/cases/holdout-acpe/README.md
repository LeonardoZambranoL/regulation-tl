# holdout-acpe: a second, unseen test case (generalisation check)

The only official labelled case is `dev-rear-lamp`, and every approach has been developed while looking at it. This
case checks whether an approach also works on a **completely different product**: an Acceleration Control for Pedal
Error (ACPE) system, i.e. driver-assistance software with sensors, not a lamp.

- `spec.md`: written by Devansh's Claude in the same style as the dev spec, describing the product only (what it is,
  vehicle category, functions, parts, materials). It was written without reading the answer key's requirement texts.
- `expected.json`: the 94 expert requirements from the challenge's sub-goal example
  (`industrial-ai-hackathon/subgoal/dev/requirements_old.json`), all from **UN R175** (ACPE). They were derived from the
  "old" R175 PDF, which is byte-identical to the R175 **base** version (0.1.0) in `regulations/index.json`, so pages and
  paragraphs line up with our corpus. Converted to the submission format with `version: "0.1.0"`.

## How to read the scores

- **Recall is the meaningful number** (page, clause and regulation recall): did the approach find the R175 obligations?
- **Precision is understated**: the answer key covers R175 only, but a real ACPE product would arguably also need, for
  example, EMC (R10) and cyber security / software update rules (R155, R156). Citing those lowers precision here
  although it may be right.
- The answer key covers R175 as a whole regulation (including administrative paragraphs), so it is not product-specific
  in the way the dev gold is.

## Rules for using it

- Never tune an approach on this case (that would turn it into a second dev case). Run, score, report; if you change
  something because of a score here, declare it in `risk.json`.
- Benchmark: `python approaches/benchmarking/bench.py <name> <predictions for holdout-acpe> approaches/benchmarking/cases/holdout-acpe/expected.json --index ../industrial-ai-hackathon/regulations/index.json`
  (predictions need `"case_id": "holdout-acpe"`).
