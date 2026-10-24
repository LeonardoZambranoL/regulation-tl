#!/usr/bin/env bash
# One-time setup for this experiment (macOS / Linux / Git Bash). Usage: ./setup.sh [--neural]
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(git rev-parse --show-toplevel)"
if [ ! -d "$ROOT/../industrial-ai-hackathon" ]; then
  git clone https://github.com/Certivity/industrial-ai-hackathon.git "$ROOT/../industrial-ai-hackathon"
fi
PY=${PYTHON:-python3}
command -v "$PY" >/dev/null || PY=python
"$PY" -m venv .venv
if [ -f .venv/bin/python ]; then VPY=.venv/bin/python; else VPY=.venv/Scripts/python; fi
"$VPY" -m pip install -q --upgrade pip
"$VPY" -m pip install -q -r requirements.txt
if [ "${1:-}" = "--neural" ]; then "$VPY" -m pip install -q -r src/retrieval/requirements-neural.txt; fi
echo "Done. Try:  cd src && ../$VPY -m retrieval.regselect"
