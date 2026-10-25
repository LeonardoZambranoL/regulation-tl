"""Hit rate per sureness band on the cases with an answer key, and the cut-off chosen by the pre-declared rule.

    python calibrate.py <ratings-dev.json> <judge-dev.json> <ratings-acpe.json> <judge-acpe.json>

judge-*.json: req_judge.py --out result for the same (unpruned) predictions file; only the matched ids are read.
Rule: drop bands <= c for the largest c whose removed items match < 12% (bumper F2 / 5) on every case.
"""

import json
import sys

BREAK_EVEN = 0.12


def main() -> int:
    cases = []
    for rp, jp in zip(sys.argv[1::2], sys.argv[2::2]):
        ratings = json.load(open(rp, encoding="utf-8"))
        matched = {p["submitted"] for p in json.load(open(jp, encoding="utf-8"))["pairs"]}
        cases.append((rp, ratings, matched))
    best = 0
    for rp, ratings, matched in cases:
        row = []
        for b in range(1, 6):
            ids = [i for i, v in ratings.items() if v == b]
            row.append(f"{b}: {sum(i in matched for i in ids)}/{len(ids)}")
        print(rp, " | ".join(row), f"| matched {len(matched)}")
    for c in range(1, 5):
        ok, parts = True, []
        for rp, ratings, matched in cases:
            ids = [i for i, v in ratings.items() if v <= c]
            h = sum(i in matched for i in ids)
            rate = h / len(ids) if ids else 0.0
            ok &= rate < BREAK_EVEN
            parts.append(f"{h}/{len(ids)} = {rate:.1%} (recall -{h})")
        print(f"drop <= {c}: " + "; ".join(parts) + ("  PASS" if ok else ""))
        if ok:
            best = c
    print(f"chosen cut-off: drop bands <= {best}" if best else "no cut-off passes: keep everything")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
