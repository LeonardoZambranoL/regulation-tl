"""Resume one workflow with an independent total cap while sharing paid-response caches."""
import argparse
import fcntl
import math
from pathlib import Path
import time

from client import read, write
from run import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--prior-cost-usd', type=float, required=True)
    parser.add_argument('--total-budget-usd', type=float, required=True)
    args = parser.parse_args()
    if not all(math.isfinite(v) for v in [args.prior_cost_usd, args.total_budget_usd]) or not 0 <= args.prior_cost_usd <= args.total_budget_usd:
        parser.error('Prior costs must be between zero and the authorized total budget.')
    shared = args.out.parent / '.api'
    state_path = args.out / 'attributed-budget.json'
    shared.mkdir(parents=True, exist_ok=True)
    print('Waiting for shared API lock; no requests sent while waiting.', flush=True)
    with (shared / '.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(state_path) if state_path.exists() else {
            'prior_workflow_cost_usd': args.prior_cost_usd,
            'workflow_total_ceiling_usd': args.total_budget_usd,
            'subsequent_workflow_cost_usd': 0, 'invocations': []}
        if state['prior_workflow_cost_usd'] != args.prior_cost_usd or state['workflow_total_ceiling_usd'] != args.total_budget_usd:
            raise ValueError('Budget identity differs from the saved authorization.')
        before = sum(e['cost'] for e in read(shared / 'api-ledger.json').values())
        remaining = state['workflow_total_ceiling_usd'] - state['prior_workflow_cost_usd'] - state['subsequent_workflow_cost_usd']
        if remaining <= 0:
            raise ValueError('This workflow has no authorized budget remaining.')
        record = {'shared_before_usd': before, 'remaining_workflow_usd': remaining,
                  'effective_shared_ceiling_usd': before + remaining, 'started_at': time.time()}
        state['invocations'].append(record)
        write(state_path, state)
        print(f"Remaining for this workflow: ${remaining:.6f}", flush=True)
        try:
            run(args.out, 'targeted', before + remaining, args.key_file)
        except Exception as exc:
            write(args.out / 'status.json', {'status': 'stopped', 'reason': str(exc)})
            raise
        finally:
            after = sum(e['cost'] for e in read(shared / 'api-ledger.json').values())
            record['shared_after_usd'] = after
            record['incremental_committed_usd'] = max(0, after - before)
            state['subsequent_workflow_cost_usd'] += record['incremental_committed_usd']
            state['attributed_workflow_total_usd'] = state['prior_workflow_cost_usd'] + state['subsequent_workflow_cost_usd']
            write(state_path, state)


if __name__ == '__main__':
    main()
