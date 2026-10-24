#!/usr/bin/env bash
# One-time setup (macOS / Linux / Git Bash). Usage: ./setup.sh          (lexical retrievers only)
#                                                   ./setup.sh --neural (also dense / hnsw / splade / rerank)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ../industrial-ai-hackathon ]; then
  git clone https://github.com/Certivity/industrial-ai-hackathon.git ../industrial-ai-hackathon
fi

PY=${PYTHON:-python3}
command -v "$PY" >/dev/null || PY=python
"$PY" -m venv .venv
if [ -f .venv/bin/python ]; then VPY=.venv/bin/python; else VPY=.venv/Scripts/python; fi
"$VPY" -m pip install -q --upgrade pip
"$VPY" -m pip install -q -r requirements.txt
if [ "${1:-}" = "--neural" ]; then
  "$VPY" -m pip install -q -r retrieval/requirements-neural.txt
fi
echo "Done. Try:  $VPY -m retrieval.bench --list"
