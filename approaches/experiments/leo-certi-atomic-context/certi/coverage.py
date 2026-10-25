"""Semantic shape checks run inside existing retry/caching boundaries."""
def validate_response(result, payload):
    if "clause_decisions" in result:
        rows = result["clause_decisions"]
        expected = {c["clause_id"] for c in payload["clauses"]}
        ids = [c["clause_id"] for c in rows]
        if set(ids) != expected or len(ids) != len(expected):
            raise ValueError("Return exactly one decision per assigned clause_id")
        for row in rows:
            mapped = []
            for unit in row["coverage"]:
                i = unit["obligation_index"]
                if not unit["source_unit"].strip():
                    raise ValueError("Coverage needs a source unit")
                if i == -1:
                    if not unit["exclusion_reason"].strip():
                        raise ValueError("Excluded source unit needs evidence/reason")
                elif 0 <= i < len(row["obligations"]):
                    mapped.append(i)
                else:
                    raise ValueError("Invalid obligation_index")
            if sorted(mapped) != list(range(len(row["obligations"]))):
                raise ValueError("Each included independent source unit must map to its own obligation, exactly once")
            if (row["status"] == "extracted") != bool(row["obligations"]):
                raise ValueError("Clause status disagrees with obligation inventory")
            if any(not o["text"].strip() or len(o["text"]) > 2000 for o in row["obligations"]):
                raise ValueError("Obligation text must contain 1-2000 characters")
    if "verdicts" in result:
        ids = [v["item_id"] for v in result["verdicts"]]
        wanted = {v["item_id"] for v in payload["candidates"]}
        if set(ids) != wanted or len(ids) != len(wanted):
            raise ValueError("Return exactly one verdict per candidate")
        for v in result["verdicts"]:
            if v["action"] in ("FIX", "SPLIT") and not v["repaired_items"]:
                raise ValueError("FIX/SPLIT requires repaired items")
            if any(not o["text"].strip() or len(o["text"]) > 2000 for o in v["repaired_items"]):
                raise ValueError("Repaired text must contain 1-2000 characters")
