"""Manually register real platform scores against immutable submission hashes. Never uploads."""
import argparse
import fcntl
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from client import read, write
from evaluate import frozen


def record(path, directory, value, note='', metric='platform-overall'):
    if not math.isfinite(value):
        raise ValueError('Score must be finite.')
    path, directory = Path(path), Path(directory)
    freeze, submission = frozen(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        events = read(path) if path.exists() else []
        events.append({'recorded_at': datetime.now(ZoneInfo('Europe/Berlin')).isoformat(),
                       'submission': str((directory / 'submission.json').resolve()),
                       'sha256': freeze['submission_sha256'], 'case_id': submission['case_id'],
                       'flow': freeze['flow'], 'metric': metric, 'score': value, 'note': note})
        write(path, events)
    same = [e for e in events if e['case_id'] == submission['case_id'] and e['metric'] == metric]
    return max(same, key=lambda e: e['score'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True, help='Directory containing submission.json and freeze.json')
    p.add_argument('--score', type=float, required=True)
    p.add_argument('--note', default='')
    p.add_argument('--metric', default='platform-overall')
    a = p.parse_args()
    try:
        best = record(a.ledger, a.run, a.score, a.note, a.metric)
        print(f"Best recorded score for this case/metric (higher is better): {best['score']}\n{best['submission']}\nSHA256: {best['sha256']}")
        print('Nothing was uploaded. Confirm the intended final file on the platform before its deadline.')
    except (ValueError, OSError) as exc:
        p.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
