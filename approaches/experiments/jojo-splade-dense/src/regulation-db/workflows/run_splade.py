"""SPLADE/dense targeted workflow using the existing Claude evidence checks."""
import hashlib
import sys
from pathlib import Path

import run as workflow
from client import write
from sources import ROOT

sys.path.insert(0, str(ROOT / 'regulation-db/retrieval'))
from benchmark import interleave
from hybrid import DEFAULT_INDEX
from local_embed import CACHE, encode, load
from splade_pipeline import SparseDense, load_model, rerank

BASE_HASH = workflow.implementation_hash
BASE_COMMON = workflow.common


def implementation_hash():
    h = hashlib.sha256(BASE_HASH().encode())
    for path in [Path(__file__), ROOT / 'regulation-db/retrieval/splade_pipeline.py',
                 ROOT / 'regulation-db/retrieval/local_embed.py', ROOT / 'regulation-db/retrieval/hybrid.py',
                 ROOT / 'regulation-db/retrieval/benchmark.py', ROOT / 'regulation-db/retrieval/plan_queries.py', ROOT / 'regulation-db/retrieval/prepare_dev.py']:
        h.update(path.read_bytes())
    return h.hexdigest()


def common(client, source, out, manifest):
    spec, profile, scope = BASE_COMMON(client, source, out, manifest)
    strategy = manifest['config'].get('query_strategy', 'facets')
    if strategy == 'full-spec':
        profile = {**profile, 'queries': [spec]}
    elif strategy == 'spec-functions':
        from prepare_dev import function_queries
        profile = {**profile, 'queries': function_queries(spec)}
    elif strategy == 'facets':
        from plan_queries import TASK, SCHEMA
        plan = client.ask(TASK, {'specification': spec}, SCHEMA, max_tokens=2400)
        if not 12 <= len(plan['queries']) <= 20:
            raise ValueError('Facet planner returned an out-of-range query count.')
        profile = {**profile, 'queries': [q['text'] for q in plan['queries']],
                   'query_rationales': plan['queries']}
        write(out / 'profile.json', profile)
    write(out / 'profile.json', profile)
    return spec, profile, scope


def targeted_packets(source, profile, scope, cfg, out):
    pool, head = cfg.get('sparse_pool', 300), cfg.get('cross_encoder_head', 0)
    if not isinstance(pool, int) or pool < 1 or not isinstance(head, int) or not 0 <= head <= 2*pool:
        raise ValueError('Invalid sparse pool or cross-encoder head.')
    engine = SparseDense(DEFAULT_INDEX)
    if sorted((d['document_id'], d['sha256']) for d in source.docs.values()) != sorted(
            (d['id'],d['sha256']) for d in engine.base.manifest['source_documents']):
        raise ValueError('Retrieval corpus is stale.')
    regs = {s['regulation'] for s in scope if s['decision'] != 'excluded'}
    encoder, tokenizer, maximum, identity = load(CACHE)
    vectors, _ = encode(profile['queries'],encoder,tokenizer,maximum,query=True)
    ce = load_model('rerank') if head else None
    rankings, audits = [], []
    for query, vector in zip(profile['queries'],vectors):
        rows, union = engine.retrieve(query,vector,identity,pool=pool,limit=2*pool,regulations=regs)
        if ce:
            rows = rerank(query,rows,ce,head)
        rankings.append(rows[:cfg['retrieval_per_query']])
        audits.append({'query':query,'union_clauses':len(union),
                       'selected': [r['id'] for r in rankings[-1]],
                       'deferred_clauses': [r['id'] for r in rows[cfg['retrieval_per_query']:]]})
    seed_ids = [r['clause_id'] for r in interleave(rankings)]
    expanded, unresolved = source.expand(seed_ids,regs,cfg['reference_depth'])
    initial = [(d['document_id'],p) for d in source.docs.values() if d['regulation'] in regs
               for p in range(1,min(3,d['page_count'])+1)]
    keys, selected, deferred = set(), [], []
    for did,page in dict.fromkeys(initial+expanded):
        first = 1+((page-1)//cfg['packet_pages'])*cfg['packet_pages']
        if (did,first) in keys:
            continue
        keys.add((did,first))
        packet = source.packet(did,first,cfg['packet_pages'])
        if len(selected)<cfg['target_packets']:
            selected.append(packet)
        else:
            deferred.append(packet['id'])
    write(out/'targeted-selection.json', {'retriever':'splade+dense-rrf-k60',
          'sparse_model':engine.meta,'dense_model':engine.base.dense_meta,
          'cross_encoder':ce[3] if ce else None,'cross_encoder_head':head,'pool':pool,
          'queries':audits,'seed_clauses':seed_ids,'selected_packets':[p['id'] for p in selected],
          'deferred_packets':deferred,'unresolved_reference_edges':unresolved,
          'note':'Deferred candidates/pages are unreviewed; ranking scores never establish non-applicability.'})
    return selected


if __name__ == '__main__':
    workflow.implementation_hash = implementation_hash
    workflow.targeted_packets = targeted_packets
    workflow.common = common
    workflow.main()
