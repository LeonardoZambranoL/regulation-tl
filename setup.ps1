# One-time setup (Windows PowerShell). Usage: .\setup.ps1            (lexical retrievers only)
#                                             .\setup.ps1 -Neural    (also dense / hnsw / splade / rerank)
param([switch]$Neural)
Set-Location $PSScriptRoot

if (-not (Test-Path ..\industrial-ai-hackathon)) {
    git clone https://github.com/Certivity/industrial-ai-hackathon.git ..\industrial-ai-hackathon
}
python -m venv .venv
.\.venv\Scripts\python -m pip install -q --upgrade pip
.\.venv\Scripts\python -m pip install -q -r requirements.txt
if ($Neural) { .\.venv\Scripts\python -m pip install -q -r retrieval\requirements-neural.txt }
Write-Output "Done. Try:  .\.venv\Scripts\python -m retrieval.bench --list"
