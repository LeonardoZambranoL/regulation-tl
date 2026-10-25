"""Read-only, same-regulation context for applicability and reference resolution."""
import re


def source_context(clause, corpus):
    clauses = corpus.regulations[clause.regulation].clauses
    label = (clause.paragraph or "").rstrip(". ")
    refs = set(re.findall(r"\b(?:paragraph|paragraphs|section)\s+(\d+(?:\.\d+)+)", clause.text, re.I))
    parents, referenced = [], []
    for other in clauses:
        if other.clause_id == clause.clause_id:
            continue
        p = (other.paragraph or "").rstrip(". ")
        entry = {"clause_id": other.clause_id, "paragraph": other.paragraph,
                 "page": other.page, "text": other.text}
        if p and label.startswith(p + "."):
            parents.append(entry)
        elif p in refs:
            referenced.append(entry)
    # No evidence truncation: expose omitted references explicitly.
    found = {x["paragraph"].rstrip(". ") for x in referenced}
    return {"parents": parents, "references": referenced[:8],
            "unresolved_or_omitted_references": sorted(refs - found) + [x["paragraph"] for x in referenced[8:]]}
