"""Wait for the shared API lock, then enforce a per-experiment incremental ceiling."""
import argparse
import fcntl
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).parent / 'src/regulation-db/workflows'))
import run_flat
from client import read, write


def segment_ceiling(committed, previous_spend, additional_limit, shared_limit):
    remaining = additional_limit - previous_spend
    if remaining <= 0:
        raise RuntimeError('The experiment incremental budget is exhausted.')
    return min(shared_limit, committed + remaining)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--key-file', type=Path)
    p.add_argument('--additional-usd', type=float, default=5)
    p.add_argument('--shared-ceiling-usd', type=float, default=17)
    a = p.parse_args()
    if a.additional_usd <= 0 or a.shared_ceiling_usd <= 0:
        p.error('Budgets must be positive.')
    shared = a.out.parent / '.api'
    shared.mkdir(parents=True, exist_ok=True)
    print('Waiting for shared API ledger lock; this run has its own output and budget.', flush=True)
    with (shared / '.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        events = read(shared / 'api-ledger.json') if (shared / 'api-ledger.json').exists() else {}
        committed = sum(e['cost'] for e in events.values())
        budget_file = a.out / 'incremental-budget.json'
        if budget_file.exists():
            budget = read(budget_file)
        else:
            budget = {'initial_committed_usd': committed, 'additional_limit_usd': a.additional_usd,
                      'started_at': time.time()}
        prior = budget.get('incremental_committed_usd', 0)
        budget['effective_shared_ceiling_usd'] = segment_ceiling(
            committed, prior, budget['additional_limit_usd'], a.shared_ceiling_usd)
        segment = {'initial_shared_committed_usd': committed, 'previous_experiment_spend_usd': prior,
                   'started_at': time.time(), 'ceiling_usd': budget['effective_shared_ceiling_usd']}
        budget.setdefault('segments', []).append(segment)
        write(budget_file, budget)
        run_flat.workflow.implementation_hash = run_flat.implementation_hash
        run_flat.workflow.targeted_packets = run_flat.targeted_packets
        print(f"Acquired lock: initial ${committed:.3f}, ceiling ${budget['effective_shared_ceiling_usd']:.3f}", flush=True)
        try:
            run_flat.workflow.run(a.out, 'targeted', budget['effective_shared_ceiling_usd'], a.key_file)
        except Exception as exc:
            write(a.out / 'status.json', {'status': 'stopped', 'reason': str(exc)})
            raise
        finally:
            events = read(shared / 'api-ledger.json') if (shared / 'api-ledger.json').exists() else {}
            segment['incremental_committed_usd'] = sum(e['cost'] for e in events.values()) - committed
            budget['incremental_committed_usd'] = prior + segment['incremental_committed_usd']
            write(budget_file, budget)


if __name__ == '__main__':
    main()
