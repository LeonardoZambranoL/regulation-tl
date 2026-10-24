"""Recover validated extraction/review caches without changing frozen generation code.

Repeated source context is encoded once by reference, without truncation. Missing
decisions are repaired independently; insufficient-budget decisions remain explicit.
"""
import argparse
import json
import shutil
from pathlib import Path

import run
import run_splade
from client import Claude, BudgetStop, read, write, sha
from contracts import REVIEW, REVIEW_TASK
from sources import Sources


def compact(batch):
    contexts, lookup, rows = {}, {}, []
    for requirement in batch:
        row = dict(requirement)
        for field in ('source_context', 'section_context'):
            value = row.pop(field)
            key = json.dumps(value, sort_keys=True, ensure_ascii=False)
            if key not in lookup:
                ref = 'context-' + str(len(lookup) + 1)
                lookup[key] = ref
                contexts[ref] = value
            row[field + '_ref'] = lookup[key]
        rows.append(row)
    return {'requirements': rows, 'contexts': contexts}


def validate_decisions(decisions, ids, retained=None):
    if len(decisions) != len(ids) or {d['id'] for d in decisions} != set(ids):
        raise ValueError('Review must decide every requested requirement exactly once.')
    by_id = dict(retained or {}) | {d['id']: d for d in decisions}
    for d in decisions:
        target = d['duplicate_of']
        if not d['reason'].strip():
            raise ValueError('Review decision lacks reason.')
        if target and (d['decision'] != 'drop' or target == d['id'] or
                       target not in by_id or by_id[target]['decision'] != 'keep'):
            raise ValueError('Invalid duplicate target.')
    return {d['id']: d for d in decisions}


def finish(parent, out, budget, key_file):
    parent, out = Path(parent), Path(out)
    manifest = read(parent / 'manifest.json')
    if manifest['implementation_sha256'] != run_splade.implementation_hash():
        raise ValueError('Frozen generation code changed.')
    for name, digest in manifest['input_sha256'].items():
        if sha((parent / 'inputs' / name).read_bytes()) != digest:
            raise ValueError('Frozen input changed.')
    source = Sources()
    if source.fingerprint != manifest['source_sha256']:
        raise ValueError('Source corpus changed.')
    if out.exists():
        raise ValueError('Choose a new recovery directory.')
    out.mkdir(parents=True)
    shutil.copytree(parent / 'inputs', out / 'inputs')
    for name in ('profile.json', 'scope.json', 'targeted-plan.json', 'targeted-selection.json'):
        shutil.copy2(parent / name, out / name)
    cfg = manifest['config']
    packets, extractions, packet_hashes = [], [], {}
    for packet_id in read(parent / 'targeted-plan.json')['packets']:
        document_id, first = packet_id.rsplit(':P', 1)
        packet = source.packet(document_id, int(first), cfg['packet_pages'])
        path = parent / 'packets' / (packet_id.replace(':', '_') + '.json')
        result = read(path)
        run.validate_packet(result, packet)
        packet_hashes[packet_id] = sha(path.read_bytes())
        packets.append(packet)
        extractions.append((packet, result))
    manifest['recovery'] = {'parent_manifest_sha256': sha((parent / 'manifest.json').read_bytes()),
                            'script_sha256': sha(Path(__file__).read_bytes()),
                            'packet_sha256': packet_hashes,
                            'method': 'Reuse valid cached decisions; losslessly deduplicate repeated source contexts for missing reviews.',
                            'budget_usd': budget}
    write(out / 'manifest.json', manifest)
    write(out / 'status.json', {'status': 'running'})
    reqs, decisions, issues = run.assemble(extractions)
    ordered = sorted(reqs, key=lambda r: (r['source']['regulation'], r['source']['page'], r['text']))
    spec, profile = (out / 'inputs/spec.md').read_text(), read(out / 'profile.json')
    cached = Claude(parent.parent / '.api', cfg['model'], budget)
    cached.key = ''  # A cache miss must never send a request in this pass.
    client = Claude(parent.parent / '.api', cfg['model'], budget, key_file)
    verdicts, audit = {}, []
    for start in range(0, len(ordered), cfg['review_batch']):
        batch = ordered[start:start + cfg['review_batch']]
        payload = {'specification': spec, 'profile': profile, 'requirements': batch}
        valid = {}
        try:
            result = cached.ask(REVIEW_TASK, payload, REVIEW, max_tokens=8000)
        except RuntimeError as exc:
            if not str(exc).startswith('ANTHROPIC_API_KEY is absent'):
                raise
        else:
            ds = result['decisions']
            ids = {r['id'] for r in batch}
            if len({d['id'] for d in ds}) != len(ds) or any(d['id'] not in ids for d in ds):
                raise ValueError('Cached review contains duplicate or unexpected IDs.')
            valid = validate_decisions(ds, {d['id'] for d in ds})
        missing = [r for r in batch if r['id'] not in valid]
        if missing:
            # Both clients share the ledger. Reload after cache accounting before spending.
            client.events = read(client.ledger)
            data = {'specification': spec, 'profile': profile, **compact(missing)}
            task = REVIEW_TASK + '\nResolve source_context_ref and section_context_ref through contexts. These are lossless references. Only return decisions for the listed requirements.'
            try:
                result = client.ask(task, data, REVIEW, max_tokens=8000)
                valid.update(validate_decisions(result['decisions'], {r['id'] for r in missing}))
            except BudgetStop as exc:
                valid.update({r['id']: {'id': r['id'], 'decision': 'unresolved', 'duplicate_of': '',
                                       'reason': 'Review not completed within approved budget: ' + str(exc)} for r in missing})
            cached.events = read(cached.ledger)
        verdicts.update(valid)
        audit.append({'batch_start': start, 'cached': len(batch)-len(missing), 'requested': len(missing)})
        print(f'Reviewed/accounted {len(verdicts)}/{len(reqs)}; committed ${client.committed:.4f}', flush=True)
    client.events = read(client.ledger)
    write(out / 'recovery-audit.json', audit)
    report = run.finalize(out, 'targeted', manifest, source, packets, reqs, decisions, issues,
                          verdicts, {'shared_experiment_committed_usd': client.committed,
                                     'note': 'Generation cache costs retained; full accounting in outputs/costs.json.'})
    write(out / 'status.json', {'status': 'finished', 'committed_usd': client.committed,
                               'review_unresolved': report['review_unresolved']})
    print(json.dumps({'requirements': report['requirements'], 'review_unresolved': report['review_unresolved']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--budget-usd', required=True, type=float)
    parser.add_argument('--key-file', required=True)
    args = parser.parse_args()
    finish(args.parent, args.out, args.budget_usd, args.key_file)
