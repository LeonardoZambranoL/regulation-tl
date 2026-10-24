"""Product-independent, hash-bound catalogue over the shared clauses and vectors."""
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(text):
    return ' '.join(text.split())


def load(repo):
    repo = Path(repo)
    paths = sorted((repo / 'data-ingestion/clauses').glob('*.json'))
    embedding = repo / 'data-ingestion/embeddings/gemini-embedding-2-preview_d768_n26769.npz'
    stamp = {'clauses': {p.name: digest(p.read_bytes()) for p in paths},
             'embedding_sha256': digest(embedding.read_bytes()), 'catalog_code': digest(Path(__file__).read_bytes())}
    rows = []
    for path in paths:
        doc = json.loads(path.read_text())
        for c in doc['clauses']:
            if not c['text'].strip() or not c['pages']:
                continue
            rows.append({'id': f'C{len(rows):05}', 'regulation': doc['regulation'], 'version': doc['version'],
                         'pages': c['pages'], 'paragraph': (c['paragraph'] or '').replace(' / ', ' '),
                         'text': c['text'].replace('\r\n', '\n'), 'review_flags': c.get('review_flags', [])})
    with np.load(embedding, allow_pickle=False) as data:
        vectors = data['embeddings'].astype(np.float32)
        for field, actual in [('regulations', [r['regulation'] for r in rows]),
                              ('versions', [r['version'] for r in rows]),
                              ('pages', [r['pages'][0] for r in rows]),
                              ('paragraphs', [r['paragraph'] for r in rows])]:
            if not np.array_equal(data[field], np.array(actual)):
                raise ValueError('Embedding alignment mismatch: ' + field)
    norms = np.linalg.norm(vectors, axis=1)
    if vectors.shape != (len(rows), 768) or not np.isfinite(vectors).all() or np.any(norms < 1e-8):
        raise ValueError('Invalid embedding matrix')
    vectors /= norms[:, None]
    by_reg = defaultdict(list)
    for r in rows:
        by_reg[r['regulation']].append(r)
    for regrows in by_reg.values():
        labels = defaultdict(list)
        for r in regrows:
            if r['paragraph']:
                labels[r['paragraph'].rstrip('.')].append(r['id'])
        for r in regrows:
            p = r['paragraph'].rstrip('.')
            ancestors = [a['id'] for a in regrows if a['paragraph'] and a['id'] != r['id'] and
                         (p.startswith(a['paragraph'].rstrip('.') + '.') or
                          p.startswith(a['paragraph'].rstrip('.') + ' '))]
            references = re.findall(r'\bparagraphs?\s+(\d+(?:\.\d+)+)', r['text'], re.I)
            r['ancestors'] = ancestors
            r['references'] = sorted({i for label in references for i in labels.get(label, []) if i != r['id']})
            r['unresolved_references'] = [label for label in references if label not in labels]
            r['source_sha256'] = digest(json.dumps(r, sort_keys=True).encode())
    stamp['fingerprint'] = digest(json.dumps(stamp, sort_keys=True).encode())
    stamp['records'] = len(rows)
    stamp['embedding_model'] = 'gemini-embedding-2-preview'
    stamp['embedding_alignment'] = 'All regulation/version/first-page/paragraph fields match; upstream NPZ has no text hashes.'
    return rows, vectors, stamp


STOP = set('the and for with from that this shall must are has have was were any all their they which into not can may its a an of to in on or as is be by at it'.split())


def tokens(text):
    return [w for w in re.findall(r'[a-z][a-z0-9]+', text.lower()) if w not in STOP]


def priority(rows, vectors, spec):
    """Lexical source seeds -> existing Gemini document vectors; no cross-model query vector."""
    terms = set(tokens(spec))
    counts = [Counter(tokens(r['text'])) for r in rows]
    df = Counter(t for c in counts for t in c if t in terms)
    lexical = np.array([sum((1 + np.log(c[t])) * np.log(1 + len(rows)/(1 + df[t])) for t in terms if c[t]) /
                        np.sqrt(max(20, sum(c.values()))) for c in counts])
    seeds = np.argsort(-lexical, kind='stable')[:8]
    dense = (vectors @ vectors[seeds].T).max(axis=1)
    fused = np.zeros(len(rows))
    for scores in (lexical, dense):
        order = np.argsort(-scores, kind='stable')
        fused[order] += 1 / (60 + np.arange(1, len(rows)+1))
    return fused, {'method': 'lexical-seeded Gemini document similarity + RRF k60; ordering only',
                   'seed_ids': [rows[i]['id'] for i in seeds], 'query_embedding_api_calls': 0}


def context_for(batch, by_id):
    ids = {r['id'] for r in batch}
    refs = {i for r in batch for i in r['ancestors'] + r['references']} - ids
    return [by_id[i] for i in sorted(refs)]


def batches(rows, size=24, max_chars=60000):
    batch, length = [], 0
    for r in rows:
        if batch and (len(batch) >= size or length + len(r['text']) > max_chars):
            yield batch
            batch, length = [], 0
        batch.append(r)
        length += len(r['text'])
    if batch:
        yield batch
