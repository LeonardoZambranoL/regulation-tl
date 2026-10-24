#!/usr/bin/env bash
# Faithful writer + ranker on dev-rear-lamp and holdout-acpe; score citations + requirement level; push.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
export PYTHONUTF8=1
PY=$( [ -x .venv/Scripts/python ] && echo "$PWD/.venv/Scripts/python" || echo "$PWD/.venv/bin/python" )
CH=$PWD/../industrial-ai-hackathon; HO=$PWD/approaches/benchmarking/cases/holdout-acpe
E=devansh-deliberate-faithful-ranked; O=$PWD/approaches/experiments/$E/outputs
cd approaches/experiments/devansh-toolkit/src
for C in dev-rear-lamp holdout-acpe; do
  SPEC=$CH/cases/dev-rear-lamp/spec.md; SUF=""; [ $C = holdout-acpe ] && SPEC=$HO/spec.md && SUF="-holdout-acpe"
  "$PY" -m retrieval.export --config ../../$E/config.json --case $C --team-id team-11 --out "$O/raw$SUF.json"
  "$PY" -m retrieval.refine "$O/raw$SUF.json" --spec "$SPEC" --out "$O/predictions$SUF.json" --mode rank --drop-at-or-below 1
done
cd ../../../..
"$PY" approaches/benchmarking/bench.py $E $O/predictions.json "$CH/cases/dev-rear-lamp/expected.json" --index "$CH/regulations/index.json" > /dev/null
"$PY" approaches/benchmarking/bench.py $E $O/predictions-holdout-acpe.json "$HO/expected.json" --index "$CH/regulations/index.json" > /dev/null
"$PY" approaches/benchmarking/req_judge.py $O/predictions.json "$CH/cases/dev-rear-lamp/expected.json" --record $E
"$PY" approaches/benchmarking/req_judge.py $O/predictions-holdout-acpe.json "$HO/expected.json" --record $E
"$PY" approaches/benchmarking/dashboard_rows.py
git add approaches/experiments/$E approaches/experiments/devansh-toolkit/src/retrieval/deliberate.py approaches/experiments/devansh-toolkit/src/retrieval/export.py approaches/leaderboard.json \
    approaches/LEADERBOARD.md approaches/req_scores.json approaches/dashboard
git commit -q -m "$E: deliberate section-by-section clause selection + faithful writer + ranker, scored on dev and holdout

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git pull --rebase -q origin main && git push -q origin main && echo pushed
