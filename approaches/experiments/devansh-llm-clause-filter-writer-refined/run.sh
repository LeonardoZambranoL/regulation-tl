#!/usr/bin/env bash
# Refine the writer's output on both cases, score citations + requirement level, rebuild dashboard data, push.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
export PYTHONUTF8=1
PY=${PY:-$( [ -x .venv/Scripts/python ] && echo .venv/Scripts/python || ([ -x .venv/bin/python ] && echo .venv/bin/python) || echo python )}
E=devansh-llm-clause-filter-writer-refined
W=approaches/experiments/devansh-llm-clause-filter-writer/outputs
O=approaches/experiments/$E/outputs
CH=../industrial-ai-hackathon
cd approaches/experiments/devansh-toolkit/src
"../../../../$PY" -m retrieval.refine "../../../../$W/predictions.json" --spec "../../../../$CH/cases/dev-rear-lamp/spec.md" --out "../../../../$O/predictions.json"
"../../../../$PY" -m retrieval.refine "../../../../$W/predictions-holdout-acpe.json" --spec ../../../benchmarking/cases/holdout-acpe/spec.md --out "../../../../$O/predictions-holdout-acpe.json"
cd ../../../..
"$PY" approaches/benchmarking/bench.py $E $O/predictions.json $CH/cases/dev-rear-lamp/expected.json --index $CH/regulations/index.json > /dev/null
"$PY" approaches/benchmarking/bench.py $E $O/predictions-holdout-acpe.json approaches/benchmarking/cases/holdout-acpe/expected.json --index $CH/regulations/index.json > /dev/null
"$PY" approaches/benchmarking/req_judge.py $O/predictions.json $CH/cases/dev-rear-lamp/expected.json --record $E
"$PY" approaches/benchmarking/req_judge.py $O/predictions-holdout-acpe.json approaches/benchmarking/cases/holdout-acpe/expected.json --record $E
"$PY" approaches/benchmarking/dashboard_rows.py
git add approaches/experiments/$E approaches/experiments/devansh-toolkit/src/retrieval/refine.py approaches/leaderboard.json approaches/LEADERBOARD.md approaches/req_scores.json approaches/dashboard
git commit -q -m "$E: verifier + dedupe on the writer output, scored on dev and holdout

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git pull --rebase -q origin main && git push -q origin main && echo "pushed"
