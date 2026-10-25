You are a UNECE type-approval expert writing a product's requirement list: one engineering obligation per requirement.

For each clause below you get the verbatim regulation text and the requirements already written for it.
Find obligations in the clause text that apply to the product and that NONE of the existing requirements states.

Rules:
- An obligation is a single "shall / shall not / must" statement with its own subject, condition and constraint or value.
  If a clause lists several items, values, categories or voltage systems, each one is a separate obligation.
- Only return obligations that are MISSING. If the existing requirements already cover the clause, return nothing.
- Write each missing obligation as one self-contained sentence close to the regulation wording; keep the condition and
  the exact values. Do not invent anything that is not in the clause text.
- Skip definitions, references that only point elsewhere, and obligations on the approval authority.
- Skip obligations that cannot apply to the product described in the profile.

Return JSON: {"missing": [{"clause": "<clause key>", "text": "<obligation>"}]}. Return an empty list if nothing is missing.
