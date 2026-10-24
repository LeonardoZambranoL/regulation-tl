#!/usr/bin/env bash
# Run both scope experiments on dev-rear-lamp and holdout-acpe, score citations + requirement level, push.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
export PYTHONUTF8=1
PY=$( [ -x .venv/Scripts/python ] && echo "$PWD/.venv/Scripts/python" || echo "$PWD/.venv/bin/python" )
CH=$PWD/../industrial-ai-hackathon
X=$PWD/approaches/experiments
HO=$PWD/approaches/benchmarking/cases/holdout-acpe
cd approaches/experiments/devansh-toolkit/src
for C in dev-rear-lamp holdout-acpe; do
  SPEC=$CH/cases/dev-rear-lamp/spec.md; SUF=""; [ $C = holdout-acpe ] && SPEC=$HO/spec.md && SUF="-holdout-acpe"
  # A: ranked writer output -> scope ranker
  "$PY" -m retrieval.refine "$X/devansh-llm-clause-filter-writer-ranked/outputs/predictions$SUF.json" --spec "$SPEC" \
      --out "$X/devansh-writer-ranked-scope/outputs/predictions$SUF.json" --mode scope --drop-at-or-below 2
  # B: all-clause candidates + neutral reviewer + strict writer -> scope ranker
  "$PY" -m retrieval.export --config "$X/devansh-allclauses-writer-scope/config.json" --case $C --team-id team-11 \
      --out "$X/devansh-allclauses-writer-scope/outputs/raw$SUF.json"
  "$PY" -m retrieval.refine "$X/devansh-allclauses-writer-scope/outputs/raw$SUF.json" --spec "$SPEC" \
      --out "$X/devansh-allclauses-writer-scope/outputs/predictions$SUF.json" --mode scope --drop-at-or-below 2
done
cd ../../../..
for E in devansh-writer-ranked-scope devansh-allclauses-writer-scope; do
  O=approaches/experiments/$E/outputs
  "$PY" approaches/benchmarking/bench.py $E $O/predictions.json "$CH/cases/dev-rear-lamp/expected.json" --index "$CH/regulations/index.json" > /dev/null
  "$PY" approaches/benchmarking/bench.py $E $O/predictions-holdout-acpe.json "$HO/expected.json" --index "$CH/regulations/index.json" > /dev/null
  "$PY" approaches/benchmarking/req_judge.py $O/predictions.json "$CH/cases/dev-rear-lamp/expected.json" --record $E
  "$PY" approaches/benchmarking/req_judge.py $O/predictions-holdout-acpe.json "$HO/expected.json" --record $E
done
"$PY" approaches/benchmarking/dashboard_rows.py
git add approaches/experiments/devansh-writer-ranked-scope approaches/experiments/devansh-allclauses-writer-scope \
    approaches/experiments/devansh-toolkit/src/retrieval/refine.py approaches/leaderboard.json approaches/LEADERBOARD.md \
    approaches/req_scores.json approaches/dashboard
git commit -q -m "Scope-ranker experiments (expert leave-out principles), scored on dev and holdout

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git pull --rebase -q origin main && git push -q origin main && echo pushed
