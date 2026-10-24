# One-time setup for this experiment (Windows PowerShell). Usage: .\setup.ps1 [-Neural]
param([switch]$Neural)
Set-Location $PSScriptRoot
$root = (git rev-parse --show-toplevel)
if (-not (Test-Path "$root\..\industrial-ai-hackathon")) {
    git clone https://github.com/Certivity/industrial-ai-hackathon.git "$root\..\industrial-ai-hackathon"
}
python -m venv .venv
.\.venv\Scripts\python -m pip install -q --upgrade pip
.\.venv\Scripts\python -m pip install -q -r requirements.txt
if ($Neural) { .\.venv\Scripts\python -m pip install -q -r src\retrieval\requirements-neural.txt }
Write-Output "Done. Try:  cd src; ..\.venv\Scripts\python -m retrieval.regselect"
