# Contributing: set up, then pull, test, push

For everyone on the team, whatever coding agent you use (Claude Code, Codex, Cursor, Copilot, Gemini, or none).
The rules every agent follows are in [AGENTS.md](AGENTS.md); this page is the setup and the loop.

- Repo: https://github.com/LeonardoZambranoL/regulation-tl
- Challenge (cases, official tools): https://github.com/Certivity/industrial-ai-hackathon
- Comparison dashboard: `python approaches/dashboard/open.py` (pulls, then opens `approaches/dashboard/dashboard.html`
  in your browser; no account needed), or
  https://claude.ai/artifact/TEW2x5Fhkj8DHgtmfnLLTV (open to anyone with the link; it updates itself from the repo within about 5 minutes of your push)
- Leaderboard in the repo: [approaches/LEADERBOARD.md](approaches/LEADERBOARD.md)

## 1. Set up once

Clone both repos side by side (the benchmark expects `../industrial-ai-hackathon` next to this repo):

```bash
git clone https://github.com/LeonardoZambranoL/regulation-tl.git
git clone https://github.com/Certivity/industrial-ai-hackathon.git
cd regulation-tl
git config core.hooksPath .githooks          # pre-push check: refuses to push while you are behind origin
python -m pip install -r approaches/benchmarking/requirements.txt
```

Point your agent at the rules if it does not read them by itself:

| agent | reads automatically |
|---|---|
| Claude Code / Claude desktop | `CLAUDE.md` (imports `AGENTS.md`) |
| OpenAI Codex, Cursor, Aider, Zed, most others | `AGENTS.md` |
| Gemini CLI | `GEMINI.md` (imports `AGENTS.md`) |
| GitHub Copilot | `.github/copilot-instructions.md` |
| anything else | tell it: "follow AGENTS.md" |

API keys (for LLM steps) go in a git-ignored `.env`, never in commits.

## 2. The loop

```bash
git pull --rebase                            # always first
# work only in approaches/experiments/<your-name-or-variant>/  (README.md, config.json, risk.json, outputs/predictions.json)
python approaches/benchmarking/bench.py <name> approaches/experiments/<name>/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
python approaches/benchmarking/dashboard_rows.py
git pull --rebase                            # again, right before pushing
git add approaches && git commit -m "<name>: what changed"
git push
```

Then the dashboard updates itself: a scheduled sync pulls the repo every 5 minutes and uploads the pushed
`leaderboard_rows.json` (details in [approaches/dashboard/README.md](approaches/dashboard/README.md)). Nothing else to do.

## 3. What a good experiment folder has

- `README.md`: what it does and how it works, how to run it, assumptions, limitations.
- `config.json`: `"name"` is the one-line description shown on the dashboard.
- `EXPLAIN.md`: `# In plain words` (3-6 sentences, no jargon) and `# Technical` (exact method); both shown by the
  dashboards' Explain button.
- `risk.json`: what you tuned on the dev case (see [approaches/dashboard/README.md](approaches/dashboard/README.md)).
- `outputs/predictions.json`: submission format; `results.json` and `benchmark-results/` are written by the bench.

If a pull conflicts on `approaches/leaderboard.json`, keep every run from both sides, then re-run
`dashboard_rows.py`. Never force-push.
