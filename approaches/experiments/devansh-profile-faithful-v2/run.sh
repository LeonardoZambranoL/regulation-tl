#!/usr/bin/env bash
# profile-faithful v2 on both cases (fresh LLM answers in this folder's own .cache), then score citations + requirement level.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
export PYTHONUTF8=1
PY=$( [ -x .venv/Scripts/python ] && echo "$PWD/.venv/Scripts/python" || echo "$PWD/.venv/bin/python" )
CH=$PWD/../industrial-ai-hackathon; HO=$PWD/approaches/benchmarking/cases/holdout-acpe
E=devansh-profile-faithful-v2; O=$PWD/approaches/experiments/$E/outputs
# v2's own cache: no answer of an earlier experiment (profile, classifier, writer, ranker) is reused
export LLM_CACHE_DIR=$PWD/approaches/experiments/$E/.cache
cd approaches/experiments/devansh-toolkit/src
for C in dev-rear-lamp holdout-acpe; do
  SUF=""; [ $C = holdout-acpe ] && SUF="-holdout-acpe"
  "$PY" -m retrieval.export --config ../../$E/config.json --case $C --team-id team-11 --out "$O/raw$SUF.json"
  "$PY" -m retrieval.refine "$O/raw$SUF.json" --spec "$O/spec-with-profile-$C.md" --out "$O/predictions$SUF.json" \
    --mode rank --drop-at-or-below 1 --merge-restatements
done
cd ../../../..
if [ "${SCORE:-1}" = 1 ]; then
  "$PY" approaches/benchmarking/bench.py $E "$O/predictions.json" "$CH/cases/dev-rear-lamp/expected.json" --index "$CH/regulations/index.json" > /dev/null
  "$PY" approaches/benchmarking/bench.py $E "$O/predictions-holdout-acpe.json" "$HO/expected.json" --index "$CH/regulations/index.json" > /dev/null
  "$PY" approaches/benchmarking/req_judge.py "$O/predictions.json" "$CH/cases/dev-rear-lamp/expected.json" --record $E
  "$PY" approaches/benchmarking/req_judge.py "$O/predictions-holdout-acpe.json" "$HO/expected.json" --record $E
  "$PY" approaches/benchmarking/dashboard_rows.py
fi
