"""No-training thorough and targeted requirement workflows. Solver never loads reference answers."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from client import Claude, BudgetStop, IncompleteResponse, read, write, sha
from contracts import (PROFILE, SCOPE, EXTRACTION, REVIEW, PROFILE_TASK, SCOPE_TASK,
                       EXTRACT_TASK, REVIEW_TASK, obj)
from sources import Sources, ROOT, DB

DEFAULTS = {'model': 'claude-sonnet-5-5', 'packet_pages': 3, 'target_packets': 40,
            'reference_depth': 2, 'retrieval_per_query': 6, 'review_batch': 35,
            'workers': 3, 'training': False, 'automatic_upload': False}


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).split()).casefold()


def implementation_hash():
    h = hashlib.sha256()
    for name in ['run.py', 'client.py', 'contracts.py', 'sources.py']:
        h.update(Path(__file__).with_name(name).read_bytes())
    return h.hexdigest()


def prepare(case_dir, out, team_id, config=None):
    case_dir, out = Path(case_dir), Path(out)
    if out.exists():
        raise ValueError('Choose a new experiment directory; existing runs are immutable inputs.')
    spec = case_dir / 'spec.md'
    if not spec.is_file():
        raise ValueError('Case directory must contain spec.md.')
    cfg = {**DEFAULTS, **(read(config) if config else {})}
    if cfg.get('training') is not False or cfg.get('automatic_upload') is not False:
        raise ValueError('This runner has no training or automatic upload mode.')
    if any(not isinstance(cfg[k], int) or cfg[k] < 1 for k in ['packet_pages', 'target_packets', 'retrieval_per_query', 'review_batch', 'workers']):
        raise ValueError('Positive integer packet/retrieval/review limits are required.')
    source = Sources()
    # Verify tomorrow's catalog against the indexed base PDFs; fail rather than silently use an old corpus.
    catalog = read(ROOT / 'industrial-ai-hackathon/regulations/index.json')
    expected = {(r['regulation'], v['version_label'], f['sha256']) for r in catalog
                for v in r['versions'] if v['role'] == 'base' for f in v['files']}
    actual = {(d['regulation'], d['version'], d['sha256']) for d in source.docs.values()}
    if expected != actual:
        raise ValueError('Source corpus differs from current regulation index. Rebuild source corpus before preparing the new case.')
    out.mkdir(parents=True)
    inputs = out / 'inputs'
    inputs.mkdir()
    shutil.copyfile(spec, inputs / 'spec.md')
    files = ['spec.md']
    image = case_dir / 'exploded_view.png'
    if image.exists():
        shutil.copyfile(image, inputs / image.name)
        files.append(image.name)
    manifest = {'case_id': case_dir.name, 'team_id': team_id, 'source_sha256': source.fingerprint,
                'input_sha256': {name: sha((inputs / name).read_bytes()) for name in files},
                'config': cfg, 'implementation_sha256': implementation_hash(),
                'prepared_at': time.time(), 'reference_answer_access': False,
                'note': 'Only explicitly whitelisted product inputs copied. Known development case is not a blind benchmark.'}
    write(out / 'manifest.json', manifest)
    write(out / 'status.json', {'status': 'prepared', 'briefing': 'Inputs frozen. Ready for profile and scope assessment.'})
    return manifest


def validate_packet(result, packet, has_images=True):
    candidates = {c['candidate_id']: c for c in packet['owned_candidates']}
    decisions = {d['candidate_id']: d for d in result['decisions']}
    if len(decisions) != len(result['decisions']) or set(decisions) != set(candidates):
        raise ValueError('Each owned candidate must have exactly one decision.')
    reqs = {r['key']: r for r in result['requirements']}
    if len(reqs) != len(result['requirements']) or any(not key for key in reqs):
        raise ValueError('Requirement keys must be nonempty and unique within a packet.')
    pages = {p['page']: p['text'] for p in packet['pages']}
    for r in reqs.values():
        if not r['text'].strip() or len(r['text']) > 2000 or r['page'] not in pages:
            raise ValueError('Requirement text/page outside contract.')
        if not r['quote'].strip():
            raise ValueError('Every requirement needs source evidence.')
        if r['evidence_type'] == 'text' and normalize(r['quote']) not in normalize(pages[r['page']]):
            raise ValueError(f"Verbatim source quote missing on claimed page for {r['key']}.")
        if r['evidence_type'] == 'image' and (not has_images or r['page'] not in packet['main_pages']):
            raise ValueError('Image evidence requires an attached source-page raster.')
        if not set(r['candidate_ids']) <= set(candidates):
            raise ValueError('Unknown supporting candidate ID.')
    for d in decisions.values():
        if not d['reason'].strip() or not set(d['requirement_keys']) <= set(reqs):
            raise ValueError('Candidate decision has missing reason or unknown requirement key.')
        if d['decision'] == 'included' and not d['requirement_keys']:
            raise ValueError('Included candidate has no requirement.')
        if d['decision'] != 'included' and d['requirement_keys']:
            raise ValueError('Non-included candidate links to requirements.')
    return result


def common(client, source, out, manifest):
    spec = (out / 'inputs/spec.md').read_text()
    image = out / 'inputs/exploded_view.png'
    profile = client.ask(PROFILE_TASK, {'specification': spec}, PROFILE,
                         [('PRODUCT IMAGE', image)] if image.exists() else [], max_tokens=6000)
    if not profile['queries'] or not profile['facts']:
        raise ValueError('Product profile has no facts or retrieval queries.')
    write(out / 'profile.json', profile)
    regs = sorted(source.by_reg)
    decisions = []
    for start in range(0, len(regs), 7):
        batch = regs[start:start + 7]
        # Required named properties enforce coverage during generation, not just afterwards.
        item_schema = SCOPE['properties']['decisions']['items']
        fields = {k: v for k, v in item_schema['properties'].items() if k != 'regulation'}
        schema = obj(**{reg: obj(**fields) for reg in batch})
        result = client.ask(SCOPE_TASK + '\nReturn one named property for each supplied regulation ID.',
                            {'specification': spec, 'profile': profile,
                             'regulations': source.catalog_packet(batch)}, schema, max_tokens=6000)
        items = [{'regulation': reg, **decision} for reg, decision in result.items()]
        if len(items) != len(batch) or {r['regulation'] for r in items} != set(batch):
            raise ValueError('Scope response must cover every supplied regulation exactly once.')
        for r in items:
            if not r['reason'].strip():
                raise ValueError('Scope decision lacks a reason.')
            if r['decision'] == 'excluded' and (not r['evidence_pages'] or any(p not in {1, 2, 3} for p in r['evidence_pages'])):
                r['decision'] = 'uncertain'
                r['reason'] += ' Exclusion evidence was insufficient; retained for examination.'
        decisions.extend(items)
        print(f"Scope checked: {len(decisions)}/{len(regs)} regulations", flush=True)
    write(out / 'scope.json', decisions)
    return spec, profile, decisions


def targeted_packets(source, profile, scope, cfg, out):
    sys.path.insert(0, str(ROOT / 'regulation-db/retrieval'))
    from hybrid import Retriever, DEFAULT_INDEX
    from local_embed import load, encode, CACHE
    retriever = Retriever(DEFAULT_INDEX)
    source_docs = sorted((d['document_id'], d['sha256']) for d in source.docs.values())
    indexed_docs = sorted((d['id'], d['sha256']) for d in retriever.manifest['source_documents'])
    if source_docs != indexed_docs:
        raise ValueError('Retrieval index is stale. Rebuild it before targeted retrieval.')
    regs = {s['regulation'] for s in scope if s['decision'] != 'excluded'}
    encoder, tokenizer, limit, identity = load(CACHE)
    vectors, _ = encode(profile['queries'], encoder, tokenizer, limit, query=True)
    seed_ids = []
    for query, vector in zip(profile['queries'], vectors):
        for method in ['bm25', 'dense']:
            hits = retriever.retrieve(query, vector, identity, method=method, pool=100,
                                      limit=cfg['retrieval_per_query'], regulations=regs)
            seed_ids.extend(r['clause_id'] for r in hits)
    expanded, unresolved = source.expand(list(dict.fromkeys(seed_ids)), regs, cfg['reference_depth'])
    initial = [(d['document_id'], p) for d in source.docs.values() if d['regulation'] in regs
               for p in range(1, min(3, d['page_count']) + 1)]
    packet_keys, selected, deferred = set(), [], []
    for did, page in list(dict.fromkeys(initial + expanded)):
        first = 1 + ((page - 1) // cfg['packet_pages']) * cfg['packet_pages']
        key = (did, first)
        if key in packet_keys:
            continue
        packet_keys.add(key)
        packet = source.packet(did, first, cfg['packet_pages'])
        if len(selected) < cfg['target_packets']:
            selected.append(packet)
        else:
            deferred.append(packet['id'])
    write(out / 'targeted-selection.json', {'seed_clauses': list(dict.fromkeys(seed_ids)),
          'selected_packets': [p['id'] for p in selected], 'deferred_packets': deferred,
          'unresolved_reference_edges': unresolved,
          'note': 'Unseen pages are unreviewed, never automatically excluded. No learned weights.'})
    return selected


def extract(client, source, out, spec, profile, scope, packets, cfg):
    # PDFium is not thread-safe. Render sequentially, use concurrency only for independent HTTP requests.
    prepared_images = {p['id']: source.images(p, out) for p in packets}
    def one(packet):
        data = {'specification': spec, 'profile': profile,
                'scope': next(s for s in scope if s['regulation'] == packet['regulation']), 'packet': packet}
        images = prepared_images[packet['id']]
        result = extraction_request(client, EXTRACT_TASK, data, images)
        try:
            validate_packet(result, packet)
        except ValueError as exc:
            result = extraction_request(client, EXTRACT_TASK + '\nREPAIR THE STRUCTURAL/EVIDENCE ERROR: ' + str(exc),
                                        {**data, 'previous_output': result}, images)
            validate_packet(result, packet)
        write(out / 'packets' / (packet['id'].replace(':', '_') + '.json'), result)
        return packet, result
    results = []
    with ThreadPoolExecutor(max_workers=cfg['workers']) as pool:
        for start in range(0, len(packets), cfg['workers']):
            for result in pool.map(one, packets[start:start + cfg['workers']]):
                results.append(result)
                print(f"Source packets checked: {len(results)}/{len(packets)}; committed ${client.committed:.2f}", flush=True)
    return results


def extraction_request(client, task, data, images):
    try:
        return client.ask(task, data, EXTRACTION, images, max_tokens=16000)
    except IncompleteResponse as exc:
        if exc.reason != 'max_tokens':
            raise
        # The prior response and its usage were received and cached. Only this known
        # truncation gets one larger request, under the same cumulative dollar cap.
        return client.ask(task, data, EXTRACTION, images, max_tokens=32000)


def assemble(extractions):
    reqs, decisions, issues, seen = [], [], [], {}
    for packet, result in extractions:
        keys = {}
        for row in result['requirements']:
            identity = (packet['regulation'], packet['version'], normalize(row['text']))
            if identity in seen:
                rid = seen[identity]
            else:
                rid = f'R-{len(reqs) + 1:04}'
                seen[identity] = rid
                page_text = next(p['text'] for p in packet['pages'] if p['page'] == row['page'])
                reqs.append({'id': rid, 'text': row['text'],
                             'source': {'regulation': packet['regulation'], 'version': packet['version'],
                                        'page': row['page'], 'paragraph': row['paragraph']},
                             'quote': row['quote'], 'evidence_type': row['evidence_type'],
                             'section_context': packet.get('section_context', []),
                             'source_context': page_text, 'packet': packet['id']})
            keys[row['key']] = rid
        for d in result['decisions']:
            decisions.append({k: v for k, v in d.items() if k != 'requirement_keys'} |
                             {'requirement_ids': sorted({keys[key] for key in d['requirement_keys']})})
        issues.extend(result['issues'])
    return reqs, decisions, issues


def review(client, reqs, spec, profile, cfg):
    verdicts = {}
    # Group within a regulation; retain original numbering to keep provenance stable.
    ordered = sorted(reqs, key=lambda r: (r['source']['regulation'], r['source']['page'], r['text']))
    for start in range(0, len(ordered), cfg['review_batch']):
        batch = ordered[start:start + cfg['review_batch']]
        result = client.ask(REVIEW_TASK, {'specification': spec, 'profile': profile, 'requirements': batch}, REVIEW, max_tokens=8000)
        ds = result['decisions']
        ids = {r['id'] for r in batch}
        if len(ds) != len(ids) or {d['id'] for d in ds} != ids:
            raise ValueError('Review must decide every requirement exactly once.')
        by_id = {d['id']: d for d in ds}
        for d in ds:
            if not d['reason'].strip():
                raise ValueError('Review decision lacks reason.')
            target = d['duplicate_of']
            if target and (d['decision'] != 'drop' or target == d['id'] or target not in ids or by_id[target]['decision'] != 'keep'):
                raise ValueError('Duplicate must point directly to a retained requirement in this review batch.')
        verdicts.update(by_id)
    return verdicts


def finalize(out, flow, manifest, source, packets, reqs, decisions, issues, verdicts, usage):
    directory = out / flow
    directory.mkdir(exist_ok=True)
    kept = {rid for rid, d in verdicts.items() if d['decision'] == 'keep'}
    submission = {'team_id': manifest['team_id'], 'case_id': manifest['case_id'],
                  'requirements': [{k: r[k] for k in ['id', 'text', 'source']} for r in reqs if r['id'] in kept]}
    scope = read(out / 'scope.json')
    selected = {s['regulation'] for s in scope if s['decision'] != 'excluded'}
    expected_candidates = {cid for cid, c in source.candidates.items() if source.docs[c['document_id']]['regulation'] in selected}
    ledger = {d['candidate_id']: d for d in decisions}
    for d in ledger.values():
        if d['decision'] == 'included':
            retained = {rid if rid in kept else verdicts[rid]['duplicate_of'] for rid in d['requirement_ids']}
            d['requirement_ids'] = sorted(retained & kept)
            if not d['requirement_ids']:
                d['decision'] = 'unresolved'
                d['reason'] += ' Linked requirements were dropped or unresolved in final review.'
    missing = sorted(expected_candidates - set(ledger))
    for cid in missing:
        ledger[cid] = {'candidate_id': cid, 'decision': 'unreviewed', 'reason': 'Outside this flow selection.', 'requirement_ids': []}
    covered_pages = {(p['document_id'], n) for p in packets for n in p['main_pages']}
    expected_pages = {key for key in source.pages if source.docs[key[0]]['regulation'] in selected}
    unresolved = [d for d in ledger.values() if d['decision'] in {'unresolved', 'unreviewed'}]
    report = {'flow': flow, 'requirements': len(submission['requirements']), 'selected_regulations': sorted(selected),
              'pages_reviewed': len(covered_pages), 'pages_in_selected_regulations': len(expected_pages),
              'candidate_decisions': len(decisions), 'candidate_unreviewed': len(missing),
              'candidate_unresolved': sum(d['decision'] == 'unresolved' for d in ledger.values()),
              'review_unresolved': sum(d['decision'] == 'unresolved' for d in verdicts.values()),
              'source_issues': issues, 'scope_uncertain': [s for s in scope if s['decision'] == 'uncertain'],
              'coverage_complete': not unresolved and covered_pages == expected_pages and not issues and
                                   all(s['decision'] != 'uncertain' for s in scope) and
                                   all(d['decision'] != 'unresolved' for d in verdicts.values()),
              'usage': usage, 'training': False,
              'limitation': 'Automated source and applicability review; structural checks do not prove legal/semantic correctness.'}
    # Use the competition's validator, without importing its scoring or expected-answer code.
    sys.path.insert(0, str(ROOT / 'industrial-ai-hackathon/tools'))
    import validate as official
    problems = official.validate(submission, index=official.load_index(ROOT / 'industrial-ai-hackathon/regulations/index.json'), strict=True)
    if problems:
        raise ValueError('Official schema validation failed: ' + '; '.join(map(str, problems)))
    for r in submission['requirements']:
        s = r['source']
        if not any(d['version'] == s['version'] and 1 <= s['page'] <= d['page_count'] for d in source.by_reg[s['regulation']]):
            raise ValueError('Submission citation is not in the base source corpus.')
    write(directory / 'submission.json', submission)
    write(directory / 'report.json', report)
    write(directory / 'review.json', verdicts)
    write(directory / 'source-evidence.json', reqs)
    (directory / 'coverage.jsonl').write_text(''.join(json.dumps(d) + '\n' for d in ledger.values()))
    freeze = {'submission_sha256': sha((directory / 'submission.json').read_bytes()),
              'manifest_sha256': sha((out / 'manifest.json').read_bytes()), 'flow': flow,
              'case_id': manifest['case_id'], 'requirements': len(submission['requirements']),
              'schema_valid': True, 'coverage_complete': report['coverage_complete'], 'frozen_at': time.time()}
    write(directory / 'freeze.json', freeze)
    return report


def run(out, flow, budget, key_file, max_packets=None):
    out = Path(out)
    manifest = read(out / 'manifest.json')
    cfg = manifest['config']
    if manifest['implementation_sha256'] != implementation_hash():
        raise ValueError('Implementation changed since prepare. Prepare a new experiment instead of mixing code versions.')
    for name, expected in manifest['input_sha256'].items():
        if sha((out / 'inputs' / name).read_bytes()) != expected:
            raise ValueError('Frozen product input changed.')
    source = Sources()
    if source.fingerprint != manifest['source_sha256']:
        raise ValueError('Source database changed since preparation.')
    client = Claude(out.parent / '.api', cfg['model'], budget, key_file)
    started = time.monotonic()
    write(out / 'status.json', {'status': 'running', 'flow': flow, 'started_at': time.time()})
    spec, profile, scope = common(client, source, out, manifest)
    common_calls = list(client.calls)
    regs = {s['regulation'] for s in scope if s['decision'] != 'excluded'}
    if not regs:
        raise ValueError('Scope selected no regulations; inspect before producing an empty submission.')
    flows = ['thorough', 'targeted'] if flow == 'both' else [flow]
    for name in flows:
        if (out / name / 'freeze.json').exists():
            print(f'{name}: already frozen; unchanged', flush=True)
            continue
        call_start = len(client.calls)
        packets = source.packets(regs, count=cfg['packet_pages']) if name == 'thorough' else targeted_packets(source, profile, scope, cfg, out)
        write(out / (name + '-plan.json'), {'packets': [p['id'] for p in packets], 'count': len(packets),
              'pages': sum(len(p['main_pages']) for p in packets)})
        print(f'{name}: {len(packets)} source packets planned', flush=True)
        if max_packets:
            packets = packets[:max_packets]
        extracted = extract(client, source, out, spec, profile, scope, packets, cfg)
        if max_packets:
            write(out / 'status.json', {'status': 'pilot_only', 'packets': len(extracted), 'committed_usd': client.committed,
                                       'briefing': 'Pilot checked; no complete submission claimed. Resume without --max-packets.'})
            return
        reqs, decisions, issues = assemble(extracted)
        verdicts = review(client, reqs, spec, profile, cfg)
        report = finalize(out, name, manifest, source, packets, reqs, decisions, issues, verdicts,
                          client.usage_for(common_calls + client.calls[call_start:]))
        report['elapsed_this_invocation_seconds'] = time.monotonic() - started
        write(out / name / 'report.json', report)
        print(f"{name}: frozen {report['requirements']} requirements; coverage_complete={report['coverage_complete']}", flush=True)
    write(out / 'status.json', {'status': 'finished', 'committed_usd': client.committed,
                               'briefing': 'Requested outputs frozen. Review coverage reports before submission.'})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest='command', required=True)
    prep = sp.add_parser('prepare')
    prep.add_argument('--case-dir', type=Path, required=True)
    prep.add_argument('--out', type=Path, required=True)
    prep.add_argument('--team-id', required=True)
    prep.add_argument('--config', type=Path)
    go = sp.add_parser('run')
    go.add_argument('--out', type=Path, required=True)
    go.add_argument('--flow', choices=['thorough', 'targeted', 'both'], default='both')
    go.add_argument('--budget-usd', type=float, default=10)
    go.add_argument('--key-file', type=Path)
    go.add_argument('--max-packets', type=int, help='Pilot only; never freezes a partial output as a full run')
    args = p.parse_args()
    try:
        if args.command == 'prepare':
            print(json.dumps(prepare(args.case_dir, args.out, args.team_id, args.config), indent=2))
        else:
            shared = args.out.parent / '.api'
            shared.mkdir(exist_ok=True, parents=True)
            with (shared / '.run.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    run(args.out, args.flow, args.budget_usd, args.key_file, args.max_packets)
                except Exception as exc:
                    write(args.out / 'status.json', {'status': 'stopped', 'reason': str(exc),
                                                    'briefing': 'Progress cached. No incomplete final output is presented as complete.'})
                    raise
    except (ValueError, RuntimeError, OSError) as exc:
        p.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
