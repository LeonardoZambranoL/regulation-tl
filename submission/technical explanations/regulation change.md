# Technical explanation: regulation change impact

Our regulation change approach identifies how a new version of a regulation affects an existing set of requirements. It takes the old regulation, the new regulation, and the requirements extracted from the old version, then produces a traceable list of **modified, removed, and added requirements**. The implementation is in [`bonus/approaches/initial`](../../bonus/approaches/initial).

The central design is to examine the change from both directions: **check every existing requirement, and separately inspect every clause in the new regulation for new obligations**. This helps catch additions inside existing paragraphs as well as changes to requirements we already know about.

## Inputs and document preparation

The pipeline uses three inputs:

- The old regulation PDF and its parsed text and clauses.
- The new regulation PDF.
- An inventory of existing requirements, including their IDs and source citations.

It reuses the repository's shared parsing results for the old version. The new PDF passes through the shared PDF-to-text and text-to-clause tools. Each clause retains its paragraph label and page information so that later decisions can be traced back to the document. Parsed results are cached using the PDF's SHA-256 fingerprint.

Case configuration supplies the regulation, versions, and input paths. The development case compares UN R175 version 0.1.0 with 1.0.0; the held-out configuration compares UN R171 version 1.1.0 with 2.0.0.

## Pass 1: assess every existing requirement

For each requirement, the system locates its source in the old regulation and retrieves likely counterparts in the new version. Matching combines paragraph identifiers with lexical similarity: clauses are compared by their wording, without embedding-based retrieval. The review context includes up to five candidate new clauses, relevant parent provisions, and up to five explicitly referenced clauses from each version.

The system also searches sentences and list items across both documents. It retains two old and three new evidence blocks, with surrounding text and citations. This helps recover relevant wording when a PDF parser places part of an obligation in a neighboring block or table. Word-level comparisons expose changes to numbers, units, punctuation, conditions, and qualifiers.

Clearly unchanged requirements can be retained automatically. This shortcut requires matching source text after whitespace normalization, a unique counterpart, and checks on source pages, parser boundaries, parent clauses, and resolved references. The implementation also checks relevant changed definitions in R175 section 2. Missing, ambiguous, or changed dependencies trigger model review.

The remaining requirements are reviewed in batches of ten using the configured Claude model, `claude-sonnet-5-5`. The model classifies each requirement as:

- **Unchanged:** the obligation still applies without a substantive change.
- **Modified:** the obligation remains, but its content or applicability has changed.
- **Removed:** the obligation no longer applies in the new version.

The prompt asks the model to distinguish editorial changes and renumbering from changes in legal or technical meaning. For example, a changed applicability condition can modify a requirement even when its main action stays the same. Every old requirement must receive exactly one decision. Unchanged decisions remain in the audit record but are omitted from the submission.

## Pass 2: find newly introduced obligations

The second pass examines **every parsed clause in the new regulation**, in batches of six. It does not restrict inspection to paragraphs flagged by a text diff. Each new clause receives up to four candidate old clauses, selected by paragraph labels and wording similarity, together with parent context.

Claude extracts individual obligations and classifies each as `existing`, `modified_existing`, or `new`. Only obligations classified as `new` become additions in the final submission. Changes to known requirements are handled by the first pass.

This comparison considers the actor, action, object, applicability conditions, and procedure scope. Similar wording is not enough to establish that an obligation already existed: the same action required in a newly introduced test procedure may be a separate obligation. Genuine relocation or renumbering can still be recognized as continuity. When equivalence cannot be established, the prompt favors retaining the candidate as an addition and explaining the uncertainty.

To avoid bundling several requirements into one entry, the model inventories independent steps, operating cases, and actions or permissions. Each included unit must map to a distinct extracted obligation; excluded units need a reason. Conditions and exceptions stay attached to the obligation they qualify. Local validation checks these mappings, although it cannot prove that the model found every obligation in the source.

Added entries are deduplicated only when their normalized text and paragraph/page citation match. Identical wording at different citations is preserved because it may represent separate obligations.

## Auditability

The approach is **auditable**: it stores the LLM's stated rationale in `reason` fields alongside its decisions. The audit retains both the classifications and their explanations, including decisions to leave existing requirements unchanged and to classify extracted obligations as already existing. This lets reviewers inspect why a change was reported or why a candidate was not included in the submission.

The audit also preserves extracted obligations, clause alignments, source evidence, and citation normalizations. Reviewers can follow a decision back to the relevant regulation paragraphs and compare its rationale with the underlying text. When a detailed citation is normalized to a parent paragraph, the original citation remains available in the audit.

Deterministic checks verify requirement IDs, complete review coverage, and citations against the parsed clauses before submission. Together, the stored rationales and supporting evidence make individual decisions reviewable and help diagnose disagreements or missed changes.

## Future work: targeted recovery

We explored a subsequent recovery step that revisits selected decisions with broader document context and the existing requirement inventory. The idea is to recover missed additions, separate bundled obligations, and reconcile new-clause findings with changes to existing requirements. It preserves the original submission and produces a separate candidate with an auditable change report.

In our experiments, this additional review was quite expensive and did not improve the scores. Future work could make recovery more selective, focusing on decisions with conflicting evidence or unresolved links between the two passes to reduce the cost of additional review.

