"""Fixed-source catalogue, exhaustive selected-regulation assessment and independent verification."""
import argparse
import json
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from catalog import load, digest, normalized, priority, context_for, batches
from client import Claude, BudgetStop, read, write
from prompts import SCOPE, SCOPE_TASK, EXTRACT, EXTRACT_TASK, VERIFY, VERIFY_TASK


def exact_decisions(result, ids):
    ds = result['decisions']
    if len(ds) != len(ids) or {d['id'] for d in ds} != set(ids):
        raise ValueError('Missing, duplicate or unexpected decision IDs')
    if any(not d['reason'].strip() for d in ds):
        raise ValueError('Decision missing reason')
    return ds


def profiles(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[r['regulation']].append(r)
    result = []
    for reg, records in groups.items():
        selected = [r for i, r in enumerate(records) if i < 5 or r['paragraph'] == '1' or
                    r['paragraph'].startswith('1.') or 'combines the provisions' in r['text'].lower()]
        result.append({'regulation': reg, 'sources': selected})
    return result


def ask_checked(client, task, payload, schema, ids, max_tokens):
    try:
        result = client.ask(task, payload, schema, max_tokens=max_tokens)
    except BudgetStop as exc:
        if 'uncertain billing/outcome' not in str(exc):
            raise
        # Explicit single recovery: keep the original reservation AND charge this
        # distinct replacement request. An ambiguous replacement is never retried.
        result = client.ask(task + '\nRECOVERY: an earlier request was interrupted; its full cost reservation is retained.',
                            payload, schema, max_tokens=max_tokens)
    try:
        return exact_decisions(result, ids)
    except ValueError as exc:
        result = client.ask(task + '\nCorrect the structural error: ' + str(exc),
                            payload | {'previous_output': result}, schema, max_tokens=max_tokens)
        return exact_decisions(result, ids)


def run(args):
    started = time.monotonic()
    repo, out = Path(args.repo), Path(args.out)
    if (out / 'freeze.json').exists():
        raise ValueError('Frozen output exists; choose a new run directory')
    out.mkdir(parents=True, exist_ok=True)
    spec = Path(args.spec).read_text()
    rows, vectors, stamp = load(repo)
    by_id = {r['id']: r for r in rows}
    cache_dir = Path(__file__).resolve().parents[1] / '.cache'
    write(cache_dir / (stamp['fingerprint'] + '.catalog.json'), rows)
    write(out / 'catalog-manifest.json', stamp)
    config = {'model': 'claude-sonnet-5-5', 'batch_size': 24, 'batch_chars': 60000, 'workers': 4,
              'page_cap': None, 'cross_encoder': False, 'scope_uncertain_included': True,
              'budget_usd': args.budget_usd, 'case_id': args.case_id, 'image_used': False,
              'spec_sha256': digest(spec.encode()), 'catalog_fingerprint': stamp['fingerprint'],
              'implementation': {p.name: digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob('*.py'))}}
    write(out / 'run-manifest.json', config)
    client = Claude(args.api_cache, config['model'], args.budget_usd, args.key_file)
    before = client.committed
    score, ranking = priority(rows, vectors, spec)
    write(out / 'ranking.json', ranking | {'all_ids': [rows[i]['id'] for i in sorted(range(len(rows)), key=lambda i: -score[i])]})
    catalog_profiles = profiles(rows)
    scope = client.ask(SCOPE_TASK, {'specification': spec, 'regulations': catalog_profiles}, SCOPE, max_tokens=12000)
    ds = scope['decisions']
    if len(ds) != len(catalog_profiles) or {d['regulation'] for d in ds} != {p['regulation'] for p in catalog_profiles}:
        raise ValueError('Scope must decide every regulation exactly once')
    for d in ds:
        profile = next(p for p in catalog_profiles if p['regulation'] == d['regulation'])
        if not d['quote'].strip() or not any(normalized(d['quote']) in normalized(r['text']) for r in profile['sources']):
            raise ValueError('Scope quote absent from its supplied source: ' + d['regulation'])
    write(out / 'scope.json', scope)
    selected = {d['regulation'] for d in ds if d['decision'] != 'exclude'}
    # Semantic scores prioritize regulation processing; every clause within selected regulations is visited.
    reg_priority = {reg: max(score[i] for i,r in enumerate(rows) if r['regulation']==reg) for reg in selected}
    ordered = [r for reg in sorted(selected, key=lambda reg: -reg_priority[reg]) for r in rows if r['regulation']==reg]
    print(f'{args.case_id}: {len(selected)} regulations, {len(ordered)} source clauses; no page cap', flush=True)
    decisions, proposals, errors = [], [], []
    # Reserve part of the authorized ceiling for the independent verification.
    client.budget = max(client.committed, args.budget_usd - 1.5)
    def assess(batch):
        payload = {'specification': spec, 'targets': batch, 'context': context_for(batch, by_id)}
        try:
            result = ask_checked(client, EXTRACT_TASK, payload, EXTRACT, {r['id'] for r in batch}, 12000)
        except (ValueError, RuntimeError) as exc:
            errors.append(str(exc))
            result = [{'id': r['id'], 'decision': 'unresolved', 'reason': str(exc), 'requirements': []} for r in batch]
        return batch, result

    def assessed():
        pending = list(batches(ordered))
        with ThreadPoolExecutor(max_workers=4) as pool:
            for start in range(0, len(pending), 4):
                yield from pool.map(assess, pending[start:start+4])

    for batch, result in assessed():
        for d in result:
            source = by_id[d['id']]
            if d['decision'] != 'relevant' and d['requirements']:
                raise ValueError('Requirements emitted for a non-relevant clause')
            for candidate in d['requirements']:
                if not candidate['quote'].strip() or normalized(candidate['quote']) not in normalized(source['text']) or not 0 < len(candidate['text']) <= 1800:
                    d['decision'] = 'unresolved'
                    errors.append('Invalid requirement text/quote for ' + d['id'])
                    break
            if d['decision'] == 'relevant':
                for candidate in d['requirements']:
                    proposals.append(candidate | {'id': f'P{len(proposals):05}', 'source_id': d['id']})
            decisions.append(d)
        write(out / 'assessment.json', decisions)
        write(out / 'proposals.json', proposals)
        print(f'Assessed {len(decisions)}/{len(ordered)} clauses; {len(proposals)} proposals; shared ${client.committed:.4f}', flush=True)
    verdicts = []
    client.budget = args.budget_usd
    # Keep complete source/context once per batch, referenced by proposal source_id.
    def verify(batch):
        sources = [by_id[cid] for cid in dict.fromkeys(p['source_id'] for p in batch)]
        payload = {'specification': spec, 'requirements': batch, 'sources': sources, 'context': context_for(sources, by_id)}
        try:
            result = ask_checked(client, VERIFY_TASK, payload, VERIFY, {p['id'] for p in batch}, 8000)
        except (ValueError, RuntimeError) as exc:
            errors.append(str(exc))
            result = [{'id': p['id'], 'decision': 'unresolved', 'reason': str(exc)} for p in batch]
        return result

    def verified():
        pending = [proposals[start:start+24] for start in range(0,len(proposals),24)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            for start in range(0,len(pending),4):
                yield from pool.map(verify,pending[start:start+4])

    for result in verified():
        verdicts.extend(result)
        write(out / 'verification.json', verdicts)
        print(f'Verified {len(verdicts)}/{len(proposals)} proposals; shared ${client.committed:.4f}', flush=True)
    keep = {v['id'] for v in verdicts if v['decision']=='keep'}
    requirements, seen = [], set()
    evidence = []
    for p in proposals:
        if p['id'] not in keep:
            continue
        r = by_id[p['source_id']]
        identity = (r['regulation'], r['version'], r['paragraph'], normalized(p['text']))
        if identity in seen:
            continue
        seen.add(identity)
        source = {'regulation': r['regulation'], 'version': r['version'], 'page': r['pages'][0], 'paragraph': r['paragraph']}
        requirements.append({'id': p['id'], 'text': p['text'], 'source': source})
        evidence.append(p | {'source': source, 'all_clause_pages': r['pages'], 'source_sha256': r['source_sha256']})
    submission = {'team_id': 'jojo-static-embeddings', 'case_id': args.case_id, 'requirements': requirements}
    # Import only validator; inference never opens reference answers.
    import sys
    sys.path.insert(0, str(repo / 'approaches/benchmarking'))
    from challenge_tools.validate import validate, load_index
    problems = validate(submission, index=load_index(Path(args.index)))
    if problems:
        raise ValueError(str(problems))
    write(out / 'predictions.json', submission)
    write(out / 'evidence.json', evidence)
    counts = Counter(d['decision'] for d in decisions)
    report = {'case_id': args.case_id, 'selected_regulations': sorted(selected), 'all_corpus_clauses': len(rows),
              'selected_clauses': len(ordered), 'assessed_clauses': len(decisions), 'assessment_counts': dict(counts),
              'proposals': len(proposals), 'verified_proposals': len(verdicts), 'requirements': len(requirements),
              'verification_counts': dict(Counter(v['decision'] for v in verdicts)), 'errors': errors,
              'coverage_complete': len(decisions)==len(ordered) and len(verdicts)==len(proposals) and
                                   not errors and not counts['unresolved'] and all(d['decision']!='uncertain' for d in ds) and
                                   all(v['decision']!='unresolved' for v in verdicts),
              'elapsed_seconds': time.monotonic()-started,
              'limitations': ['Text-only draft clause splits; figures and ambiguous tables may remain unresolved.',
                             'First source page is cited for multi-page clauses; exact quote-to-page mapping is unavailable.',
                             'Scope filtering can miss applicable regulations; all include/uncertain clauses are assessed.',
                             'Source catalogue is structurally reusable; it is not an expert-approved legal requirement catalogue.']}
    write(out / 'report.json', report)
    write(out / 'costs.json', {'shared_before_usd': before, 'shared_after_usd': client.committed,
                             'new_cost_usd': client.committed-before, 'enforced_ceiling_usd': args.budget_usd,
                             'uncertain_requests': sum(v['status']!='completed' for v in client.events.values())})
    write(out / 'freeze.json', {'predictions_sha256': digest((out/'predictions.json').read_bytes()),
                                'manifest_sha256': digest((out/'run-manifest.json').read_bytes()),
                                'schema_valid': True, 'coverage_complete': report['coverage_complete']})
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'spec', 'case-id', 'out', 'index', 'api-cache', 'key-file'):
        ap.add_argument('--'+name, required=True)
    ap.add_argument('--budget-usd', type=float, required=True)
    run(ap.parse_args())
