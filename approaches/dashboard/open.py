"""Open the comparison dashboard in your default browser, always built from the latest results.

    python approaches/dashboard/open.py            # git pull, rebuild from approaches/leaderboard.json, open
    python approaches/dashboard/open.py --no-pull  # rebuild from what you have, open

The page is rebuilt locally into approaches/dashboard/.local/ (git-ignored), so it shows every pushed run even when the
person who pushed did not rebuild the committed dashboard.html, and it never leaves changes in your working copy.
"""

import subprocess
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / ".local"

if "--no-pull" not in sys.argv:
    result = subprocess.run(["git", "-C", str(HERE), "pull", "--ff-only", "-q"], capture_output=True, text=True)
    if result.returncode != 0:
        print("Could not pull (showing the results you have):", result.stderr.strip() or result.stdout.strip())

build = subprocess.run([sys.executable, str(HERE.parent / "benchmarking" / "dashboard_rows.py"),
                        "--out", str(LOCAL / "leaderboard_rows.json"), "--html-out", str(LOCAL / "dashboard.html")],
                       capture_output=True, text=True)
page = LOCAL / "dashboard.html"
if build.returncode != 0 or not page.is_file():
    print("Could not rebuild the dashboard, opening the committed copy:", build.stderr.strip())
    page = HERE / "dashboard.html"
webbrowser.open(page.as_uri())
print(f"Opened {page}")
