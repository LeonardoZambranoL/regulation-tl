# regulation-tl: Claude

@AGENTS.md

## Claude only: updating the comparison dashboard

You can upload the dashboard data yourself with the claude.ai Artifact tools, if the user has edit access to
https://claude.ai/artifact/TEW2x5Fhkj8DHgtmfnLLTV. Follow "For Claude: how to update the dashboard" in
`approaches/dashboard/README.md` exactly (upload `approaches/dashboard/leaderboard_rows.json` as an asset, point dataset
`runs` at it with `if_version`, delete the old asset, read the `check` document once). Always pull and run
`python approaches/benchmarking/dashboard_rows.py` first so the upload has everyone's runs.
