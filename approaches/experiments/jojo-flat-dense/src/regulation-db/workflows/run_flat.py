"""Flat dense targeted workflow using the existing Claude evidence checks."""
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
from flat import FlatRetriever

BASE_HASH = workflow.implementation_hash
BASE_COMMON = workflow.common


def implementation_hash():
    h = hashlib.sha256(BASE_HASH().encode())
    for path in [Path(__file__), ROOT / 'regulation-db/retrieval/flat.py',
                 ROOT / 'regulation-db/retrieval/local_embed.py', ROOT / 'regulation-db/retrieval/hybrid.py',
                 ROOT / 'regulation-db/retrieval/benchmark.py']:
        h.update(path.read_bytes())
    return h.hexdigest()


def targeted_packets(source, profile, scope, cfg, out):
    engine = FlatRetriever(DEFAULT_INDEX, cfg.get('scan_block_size', 8192))
    if sorted((d['document_id'], d['sha256']) for d in source.docs.values()) != sorted(
            (d['id'], d['sha256']) for d in engine.manifest['source_documents']):
        raise ValueError('Retrieval corpus is stale.')
    regs = {s['regulation'] for s in scope if s['decision'] != 'excluded'}
    encoder, tokenizer, maximum, identity = load(CACHE)
    vectors, _ = encode(profile['queries'], encoder, tokenizer, maximum, query=True)
    rankings, audits = [], []
    for query, vector in zip(profile['queries'], vectors):
        rows = engine.retrieve(query, vector, identity,
                               limit=cfg['retrieval_per_query'], regulations=regs)
        rankings.append(rows)
        audits.append({'query': query, **engine.last_scan,
                       'selected': [r['id'] for r in rows]})
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
    write(out/'targeted-selection.json', {'retriever':'flat-exact-cosine',
          'dense_model':engine.dense_meta, 'corpus_fingerprint':engine.manifest['fingerprint'],
          'scan_block_size':engine.block_size, 'query_merge':'round-robin',
          'queries':audits,'seed_clauses':seed_ids,'selected_packets':[p['id'] for p in selected],
          'deferred_packets':deferred,'unresolved_reference_edges':unresolved,
          'note':'Deferred candidates/pages are unreviewed; ranking scores never establish non-applicability.'})
    return selected


if __name__ == '__main__':
    workflow.implementation_hash = implementation_hash
    workflow.targeted_packets = targeted_packets
    workflow.main()
