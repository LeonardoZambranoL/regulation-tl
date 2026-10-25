"""Union of a teammate's submission (kept whole) with our items at paragraphs it does not cite.

    python combine.py <their.json> <ours.json> <out.json>

Our added items get ids "D-<original id>", so judge results show which of them matched.
"""

import json
import re
import sys


def pk(src: dict) -> tuple[str, str]:
    return src["regulation"], re.sub(r"[\s,]+", "", (src.get("paragraph") or "").lower()).rstrip(".")


def main() -> int:
    theirs, ours, out = sys.argv[1:4]
    a = json.load(open(theirs, encoding="utf-8"))
    b = json.load(open(ours, encoding="utf-8"))["requirements"]
    cited = {pk(r["source"]) for r in a["requirements"]}
    added = [{"id": "D-" + r["id"], "text": r["text"], "source": r["source"]} for r in b if pk(r["source"]) not in cited]
    reqs = [{k: r[k] for k in ("id", "text", "source")} for r in a["requirements"]] + added
    json.dump({**a, "requirements": reqs}, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"{len(a['requirements'])} + {len(added)} added = {len(reqs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
