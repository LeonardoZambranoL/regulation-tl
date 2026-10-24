"""Separate evaluator: reference answers are read here, never by the solver."""
import argparse
import json
import sys
from pathlib import Path

from client import read, sha, write
from sources import ROOT

sys.path.insert(0, str(ROOT / 'industrial-ai-hackathon/tools'))
from score_local import score


def frozen(directory):
    directory = Path(directory)
    freeze = read(directory / 'freeze.json')
    if sha((directory / 'submission.json').read_bytes()) != freeze['submission_sha256']:
        raise ValueError('Frozen submission was modified. Refusing to score or register it.')
    return freeze, read(directory / 'submission.json')


def compare(experiment, expected):
    experiment = Path(experiment)
    gold = read(expected)
    report = {'case_id': gold['case_id'], 'metric_scope': 'Official local regulation/page metrics only; semantic requirement score unavailable.',
              'reference_sha256': sha(Path(expected).read_bytes()), 'flows': {}}
    submissions = {}
    for flow in ['thorough', 'targeted']:
        freeze, submission = frozen(experiment / flow)
        if submission['case_id'] != gold['case_id']:
            raise ValueError('Reference case ID differs from submission case ID.')
        result = score(submission, gold)
        for metric in result.values():
            p, r = metric['precision'], metric['recall']
            metric['f2'] = 5 * p * r / (4 * p + r) if p + r else 0
        report['flows'][flow] = {'freeze': freeze, 'scores': result, 'run': read(experiment / flow / 'report.json')}
        submissions[flow] = submission
    pages = {flow: {(r['source']['regulation'], r['source']['version'], r['source']['page'])
                    for r in s['requirements']} for flow, s in submissions.items()}
    report['strict_page_set_difference'] = {'only_thorough': sorted(pages['thorough'] - pages['targeted']),
                                            'only_targeted': sorted(pages['targeted'] - pages['thorough']),
                                            'note': 'Literal citation pages, not semantic requirement differences.'}
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', type=Path, required=True)
    p.add_argument('--expected', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    try:
        result = compare(a.experiment, a.expected)
        write(a.out, result)
        for name, flow in result['flows'].items():
            m = flow['scores']['page_level']
            print(f"{name}: {flow['run']['requirements']} requirements; page precision={m['precision']:.1%}, "
                  f"recall={m['recall']:.1%}, F2={m['f2']:.1%}; "
                  f"standalone model estimate=${flow['run']['usage']['standalone_model_cost_estimate_usd']:.2f}")
    except (ValueError, OSError) as exc:
        p.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
