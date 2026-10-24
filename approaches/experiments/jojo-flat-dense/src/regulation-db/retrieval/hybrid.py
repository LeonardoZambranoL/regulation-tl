"""Version-scoped BM25 + dense score fusion. No network or generative model calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / 'regulation-db/corpus/regulations.sqlite'
DEFAULT_INDEX = ROOT / 'regulation-db/retrieval/index'
NORMALIZATION = 'minmax-full-eligible-pool-v1'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def readonly(path):
    con = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def build(db, out, role='base', words=180, overlap=30):
    if words <= overlap or overlap < 0:
        raise ValueError('Require words > overlap >= 0.')
    if out.exists():
        raise ValueError('Index already exists; choose a new directory.')
    with readonly(db) as source:
        docs = [dict(r) for r in source.execute('SELECT * FROM documents WHERE role=? ORDER BY document_id', (role,))]
        clauses = source.execute('''SELECT c.*,d.regulation,d.version,d.role,d.title,d.pdf_path
          FROM clauses c JOIN documents d USING(document_id) WHERE d.role=? ORDER BY c.clause_id''', (role,)).fetchall()
    if not docs or not clauses:
        raise ValueError('No documents/clauses for requested role.')
    chunks = []
    for row in clauses:
        c = dict(row)
        tokens = c.pop('text').split()
        for start in range(0, len(tokens), words - overlap):
            text = ' '.join(tokens[start:start + words])
            # Same representation for both retrievers, with version retained in metadata.
            search_text = f"{c['regulation']} | {c['title']} | {c['paragraph']}\n{text}"
            chunks.append({**c, 'id': f"{c['clause_id']}:W{start:06}", 'text': text,
                           'search_text': search_text, 'text_sha256': digest(search_text)})
            if start + words >= len(tokens):
                break
    out.mkdir(parents=True)
    with sqlite3.connect(out / 'lexical.sqlite') as index:
        index.execute('CREATE VIRTUAL TABLE search USING fts5(text)')
        index.executemany('INSERT INTO search(rowid,text) VALUES (?,?)',
                          [(i + 1, c['search_text']) for i, c in enumerate(chunks)])
    with (out / 'chunks.jsonl').open('w') as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
    manifest = {'format': 1, 'role': role, 'words': words, 'overlap': overlap,
                'documents': len(docs), 'chunks': len(chunks),
                'source_documents': [{'id': d['document_id'], 'sha256': d['sha256']} for d in docs],
                'fingerprint': digest('\n'.join(c['id'] + ':' + c['text_sha256'] for c in chunks))}
    write_json(out / 'manifest.json', manifest)
    return manifest


def unit_vectors(values):
    a = np.asarray(values, dtype=np.float32)
    if a.ndim != 2 or a.shape[1] == 0 or not np.isfinite(a).all():
        raise ValueError('Vectors must be a finite, rectangular matrix.')
    norms = np.linalg.norm(a.astype(np.float64), axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError('Zero vectors are not valid embeddings.')
    return (a / norms).astype(np.float32)


def import_dense(index, path, model):
    if not model.strip():
        raise ValueError('Provide a nonempty embedding model/revision identifier.')
    if (index / 'dense.json').exists() or (index / 'dense.npy').exists():
        raise ValueError('Dense index exists; use a fresh index to change embeddings.')
    chunks = read_lines(index / 'chunks.jsonl')
    rows = read_lines(path)
    by_id = {r['id']: r for r in rows}
    if len(by_id) != len(rows) or set(by_id) != {c['id'] for c in chunks}:
        raise ValueError('Embedding IDs must cover every chunk exactly once, with no extras.')
    for c in chunks:
        if by_id[c['id']].get('text_sha256') != c['text_sha256']:
            raise ValueError(f"Text hash mismatch: {c['id']}")
    vectors = unit_vectors([by_id[c['id']]['vector'] for c in chunks])
    np.save(index / 'dense.npy', vectors, allow_pickle=False)
    meta = {'model': model, 'dimensions': vectors.shape[1],
            'fingerprint': read_json(index / 'manifest.json')['fingerprint']}
    write_json(index / 'dense.json', meta)
    return meta


def normalize(scores):
    low, high = float(np.min(scores)), float(np.max(scores))
    return (scores - low) / (high - low) if high > low else np.zeros_like(scores)


def top_indices(scores, count):
    # Stable corpus order provides deterministic ties across systems.
    return np.argsort(-scores, kind='stable')[:count]


class Retriever:
    def __init__(self, index):
        self.index = Path(index)
        self.manifest = read_json(self.index / 'manifest.json')
        self.chunks = read_lines(self.index / 'chunks.jsonl')
        actual = digest('\n'.join(c['id'] + ':' + digest(c['search_text']) for c in self.chunks))
        if actual != self.manifest['fingerprint']:
            raise ValueError('Chunk manifest fingerprint mismatch.')
        self.lexical = readonly(self.index / 'lexical.sqlite')
        self.dense = self.dense_meta = None
        if (self.index / 'dense.json').exists():
            self.dense_meta = read_json(self.index / 'dense.json')
            self.dense = np.load(self.index / 'dense.npy', mmap_mode='r', allow_pickle=False)
            if (self.dense_meta['fingerprint'] != self.manifest['fingerprint'] or
                    self.dense.shape != (len(self.chunks), self.dense_meta['dimensions']) or
                    not np.isfinite(self.dense).all()):
                raise ValueError('Dense index does not match corpus.')

    def scores(self, query, vector=None, model=None, regulations=None):
        ids = np.array([i for i, c in enumerate(self.chunks)
                        if not regulations or c['regulation'] in regulations], dtype=int)
        if not len(ids):
            raise ValueError('No chunks match regulation filter.')
        terms = list(dict.fromkeys(re.findall(r'\w+', query.lower(), re.UNICODE)))
        if not terms:
            raise ValueError('Query must contain searchable text.')
        raw = np.zeros(len(self.chunks), dtype=np.float64)
        # OR, not AND: long specs must not require every word in each source block.
        match = ' OR '.join('"' + t + '"' for t in terms)
        for row in self.lexical.execute('SELECT rowid,bm25(search) AS score FROM search WHERE search MATCH ?', (match,)):
            raw[row['rowid'] - 1] = -row['score']  # SQLite BM25 is negative, lower is better.
        dense = np.zeros(len(ids), dtype=np.float64)
        if vector is not None:
            if self.dense is None:
                raise ValueError('Import real dense embeddings before hybrid retrieval.')
            if model != self.dense_meta['model']:
                raise ValueError('Query and corpus embedding model identifiers must match.')
            q = unit_vectors([vector])[0]
            if len(q) != self.dense.shape[1]:
                raise ValueError('Query embedding dimension mismatch.')
            dense = np.asarray(self.dense[ids] @ q, dtype=np.float64)
        return ids, raw[ids], dense

    def retrieve(self, query, vector=None, model=None, method='hybrid', alpha=0.5,
                 pool=100, limit=20, regulations=None):
        if not 0 <= alpha <= 1 or pool < 1 or limit < 1 or limit > pool:
            raise ValueError('Require alpha in [0,1] and 1 <= limit <= pool.')
        if method != 'bm25' and vector is None:
            raise ValueError('Dense, hybrid and RRF require a query embedding.')
        ids, bm, dn = self.scores(query, vector, model, regulations)
        btop = [int(i) for i in top_indices(bm, pool) if bm[i] > 0]
        dtop = list(map(int, top_indices(dn, pool))) if vector is not None else []
        if method == 'bm25':
            selected, scores = btop, bm
        elif method == 'dense':
            selected, scores = dtop, dn
        else:
            selected = sorted(set(btop) | set(dtop))
            if method == 'hybrid':
                # Both modalities scored for EVERY union candidate, including cross-list misses.
                scores = alpha * normalize(bm) + (1 - alpha) * normalize(dn)
                if alpha == 1:
                    selected = btop
                elif alpha == 0:
                    selected = dtop
            elif method == 'rrf':
                scores = np.zeros(len(ids))
                for ranking in [btop, dtop]:
                    for rank, i in enumerate(ranking, 1):
                        scores[i] += 1 / (60 + rank)
            else:
                raise ValueError('Unknown retrieval method.')
        ordered = sorted(selected, key=lambda i: (-float(scores[i]), int(ids[i])))
        results, seen = [], set()
        for i in ordered:
            chunk = self.chunks[int(ids[i])]
            if chunk['clause_id'] in seen:
                continue
            seen.add(chunk['clause_id'])
            results.append({**chunk, 'score': float(scores[i]), 'bm25': float(bm[i]),
                            'cosine': float(dn[i]) if vector is not None else None})
            if len(results) == limit:
                break
        return results


def page_keys(results):
    # Unique (document, PDF page) in rank order. Full spans are conservative navigation aids.
    seen, output = set(), []
    for r in results:
        for page in range(r['page_start'], r['page_end'] + 1):
            key = (r['regulation'], r['version'], page)
            if key not in seen:
                seen.add(key)
                output.append(key)
    return output


def metrics(results, relevant, k):
    if k < 1:
        raise ValueError('Page budget k must be positive.')
    gold = {(r['regulation'], r['version'], r['page']) for r in relevant}
    if not gold:
        raise ValueError('Each evaluation query needs at least one relevant source page.')
    retrieved = page_keys(results)[:k]
    hits = [int(key in gold) for key in retrieved]
    recall = sum(hits) / len(gold)
    precision = sum(hits) / len(retrieved) if retrieved else 0.0
    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(gold))))
    return {'recall': recall, 'precision': precision,
            'f2': 5 * precision * recall / (4 * precision + recall) if precision + recall else 0.0,
            'ndcg': dcg / ideal}


def validate_queries(queries, retriever, split_required=False):
    ids, groups, texts = set(), {}, {}
    pages = {(c['regulation'], c['version'], p) for c in retriever.chunks
             for p in range(c['page_start'], c['page_end'] + 1)}
    for q in queries:
        if q['id'] in ids or not q['text'].strip():
            raise ValueError('Duplicate query ID or empty query.')
        ids.add(q['id'])
        if 'vector' in q and q.get('text_sha256') != digest(q['text']):
            raise ValueError('Query embedding text hash mismatch.')
        gold = {(r['regulation'], r['version'], r['page']) for r in q['relevant_pages']}
        if not gold or not gold <= pages:
            raise ValueError('Relevant pages are empty or absent from this version-scoped index.')
        if split_required:
            split, group = q['split'], q['group_id']
            if split not in {'train', 'validation', 'test'} or not group:
                raise ValueError('Require group_id and train/validation/test split.')
            if group in groups and groups[group] != split:
                raise ValueError('Product/case group leaks between splits.')
            text_key = ' '.join(q['text'].lower().split())
            if text_key in texts and texts[text_key] != split:
                raise ValueError('Identical query text leaks between splits.')
            groups[group], texts[text_key] = split, split
    if split_required and set(groups.values()) != {'train', 'validation', 'test'}:
        raise ValueError('Need independent product/case groups in train, validation AND test.')


def evaluate(retriever, queries, method, alpha=0.5, pool=100, k=20):
    if not queries:
        raise ValueError('No queries to evaluate.')
    if k < 1 or pool < 1:
        raise ValueError('Page budget and candidate pool must be positive.')
    per_query = []
    for q in queries:
        result = retriever.retrieve(q['text'], q.get('vector'), q.get('model'), method,
                                    alpha, pool, pool, q.get('regulations'))
        per_query.append({'id': q['id'], **metrics(result, q['relevant_pages'], k)})
    return {'mean': {key: sum(r[key] for r in per_query) / len(per_query)
                     for key in ['recall', 'precision', 'f2', 'ndcg']}, 'queries': per_query}


def fit(retriever, queries, pool=100, k=20, objective='recall', steps=20):
    validate_queries(queries, retriever, split_required=True)
    if steps < 1:
        raise ValueError('steps must be positive.')
    if objective not in {'recall', 'ndcg', 'f2'}:
        raise ValueError('Unknown training objective.')
    if retriever.dense_meta is None:
        raise ValueError('Training requires imported corpus embeddings.')
    train = [q for q in queries if q['split'] == 'train']
    validation = [q for q in queries if q['split'] == 'validation']
    test = [q for q in queries if q['split'] == 'test']
    # One scalar, directly optimized for the desired ranking metric. No neural gate needed.
    grid = []
    for step in range(steps + 1):
        alpha = step / steps
        score = evaluate(retriever, train, 'hybrid', alpha, pool, k)['mean'][objective]
        grid.append({'alpha': alpha, 'train_objective': score})
    best = max(r['train_objective'] for r in grid)
    finalists = [r for r in grid if math.isclose(r['train_objective'], best, abs_tol=1e-12)]
    for row in finalists:
        row['validation_objective'] = evaluate(retriever, validation, 'hybrid', row['alpha'], pool, k)['mean'][objective]
    chosen = max(finalists, key=lambda r: (r['validation_objective'], -abs(r['alpha'] - 0.5)))
    alpha = chosen['alpha']
    return {'format': 1, 'alpha': alpha, 'alpha_meaning': 'BM25 weight; dense weight is 1-alpha',
            'normalization': NORMALIZATION, 'index_fingerprint': retriever.manifest['fingerprint'],
            'embedding_model': retriever.dense_meta['model'], 'role': retriever.manifest['role'],
            'pool': pool, 'k_pages': k, 'objective': objective, 'grid': grid,
            'groups': {s: sorted({q['group_id'] for q in queries if q['split'] == s})
                       for s in ['train', 'validation', 'test']},
            'query_data_sha256': digest(json.dumps(queries, sort_keys=True)),
            'held_out_test': {m: evaluate(retriever, test, m, alpha, pool, k)
                              for m in ['bm25', 'dense', 'rrf', 'hybrid']}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build')
    b.add_argument('--db', type=Path, default=DEFAULT_DB)
    b.add_argument('--index', type=Path, default=DEFAULT_INDEX)
    b.add_argument('--role', choices=['base', 'latest'], default='base')
    b.add_argument('--words', type=int, default=180)
    b.add_argument('--overlap', type=int, default=30)
    d = sub.add_parser('import-dense')
    d.add_argument('--index', type=Path, default=DEFAULT_INDEX)
    d.add_argument('--vectors', type=Path, required=True)
    d.add_argument('--model', required=True)
    s = sub.add_parser('search')
    s.add_argument('--index', type=Path, default=DEFAULT_INDEX)
    s.add_argument('--query', required=True)
    s.add_argument('--embedding', type=Path, help='JSON: text_sha256 (query), model, vector')
    s.add_argument('--method', choices=['bm25', 'dense', 'rrf', 'hybrid'], default='hybrid')
    s.add_argument('--alpha', type=float, default=0.5)
    s.add_argument('--weights', type=Path)
    s.add_argument('--pool', type=int, default=100)
    s.add_argument('--limit', type=int, default=20)
    s.add_argument('--reg', action='append')
    for name in ['fit', 'evaluate']:
        e = sub.add_parser(name)
        e.add_argument('--index', type=Path, default=DEFAULT_INDEX)
        e.add_argument('--queries', type=Path, required=True)
        e.add_argument('--out', type=Path, required=True)
        e.add_argument('--pool', type=int, default=100)
        e.add_argument('--k', type=int, default=20)
        if name == 'fit':
            e.add_argument('--objective', choices=['recall', 'ndcg', 'f2'], default='recall')
            e.add_argument('--steps', type=int, default=20)
        else:
            e.add_argument('--method', choices=['bm25', 'dense', 'rrf', 'hybrid'], default='bm25')
            e.add_argument('--alpha', type=float, default=0.5)
    a = p.parse_args()
    try:
        if a.command == 'build':
            result = build(a.db, a.index, a.role, a.words, a.overlap)
        elif a.command == 'import-dense':
            result = import_dense(a.index, a.vectors, a.model)
        else:
            retriever = Retriever(a.index)
            if a.command == 'search':
                embedding = read_json(a.embedding) if a.embedding else {}
                if embedding and embedding.get('text_sha256') != digest(a.query):
                    raise ValueError('Query embedding text hash mismatch.')
                if a.weights:
                    weights = read_json(a.weights)
                    if (weights['index_fingerprint'] != retriever.manifest['fingerprint'] or
                            weights['normalization'] != NORMALIZATION or
                            not retriever.dense_meta or weights['embedding_model'] != retriever.dense_meta['model']):
                        raise ValueError('Weights are incompatible with this corpus/model/normalization.')
                    a.alpha, a.pool = weights['alpha'], weights['pool']
                result = {'method': a.method, 'alpha': a.alpha if a.method == 'hybrid' else None,
                          'weight_status': 'learned' if a.weights else 'untrained/manual',
                          'results': retriever.retrieve(a.query, embedding.get('vector'), embedding.get('model'),
                                        a.method, a.alpha, a.pool, a.limit, a.reg)}
            else:
                queries = read_lines(a.queries)
                validate_queries(queries, retriever)
                result = (fit(retriever, queries, a.pool, a.k, a.objective, a.steps) if a.command == 'fit'
                          else evaluate(retriever, queries, a.method, a.alpha, a.pool, a.k))
                write_json(a.out, result)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        p.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
