"""Open the comparison dashboard in your default browser (pulls the latest results first).

    python approaches/dashboard/open.py            # git pull, then open dashboard.html
    python approaches/dashboard/open.py --no-pull  # just open it
"""

import subprocess
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
page = HERE / "dashboard.html"

if "--no-pull" not in sys.argv:
    result = subprocess.run(["git", "-C", str(HERE), "pull", "--ff-only", "-q"], capture_output=True, text=True)
    if result.returncode != 0:
        print("Could not pull (showing the copy you have):", result.stderr.strip() or result.stdout.strip())
if not page.is_file():
    sys.exit(f"{page} not found: run python approaches/benchmarking/dashboard_rows.py first")
webbrowser.open(page.as_uri())
print(f"Opened {page}")
