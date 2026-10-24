#!/usr/bin/env bash
# Produce the submission file for any case with profile-faithful v2 (profile from spec + image, implicit obligations without
# table / figure / appendix clauses, faithful writer, ranker, restatement merge), clean and validated.
#   bash approaches/experiments/devansh-profile-faithful-v2/final.sh <case-id>      (default dev-rear-lamp)
# The case's spec.md is taken from ../industrial-ai-hackathon/cases/<case-id>/ (git pull there first on Sunday) or
# approaches/benchmarking/cases/<case-id>/. Output: approaches/experiments/devansh-profile-faithful-v2/outputs/
# submission-<case-id>.json. Spends your own Anthropic credits (ANTHROPIC_API_KEY or .env); answers are cached in this folder's own .cache.
set -euo pipefail
CASE=${1:-dev-rear-lamp}
cd "$(git rev-parse --show-toplevel)"
export PYTHONUTF8=1
PY=$( [ -x .venv/Scripts/python ] && echo "$PWD/.venv/Scripts/python" || echo "$PWD/.venv/bin/python" )
CH=$PWD/../industrial-ai-hackathon
SPEC=$CH/cases/$CASE/spec.md; [ -f "$SPEC" ] || SPEC=$PWD/approaches/benchmarking/cases/$CASE/spec.md
O=$PWD/approaches/experiments/devansh-profile-faithful-v2/outputs
export LLM_CACHE_DIR=$PWD/approaches/experiments/devansh-profile-faithful-v2/.cache
cd approaches/experiments/devansh-toolkit/src
"$PY" -m retrieval.export --config ../../devansh-profile-faithful-v2/config.json --case "$CASE" --team-id team-11 --out "$O/raw-$CASE.json"
"$PY" -m retrieval.refine "$O/raw-$CASE.json" --spec "$O/spec-with-profile-$CASE.md" --out "$O/ranked-$CASE.json" --mode rank --drop-at-or-below 1 --merge-restatements
cd ../../../..
"$PY" - "$O/ranked-$CASE.json" "$O/submission-$CASE.json" <<'PYEOF'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
reqs = []
for i, r in enumerate(doc["requirements"], 1):
    src = {k: r["source"][k] for k in ("regulation", "version", "page", "paragraph") if r["source"].get(k) not in (None, "")}
    reqs.append({"id": f"R-{i:04d}", "text": r["text"][:2000], "source": src})
json.dump({"team_id": "team-11", "case_id": doc["case_id"], "requirements": reqs},
          open(sys.argv[2], "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"{len(reqs)} requirements -> {sys.argv[2]}")
PYEOF
"$PY" "$CH/tools/validate.py" "$O/submission-$CASE.json" --index "$CH/regulations/index.json" --strict
