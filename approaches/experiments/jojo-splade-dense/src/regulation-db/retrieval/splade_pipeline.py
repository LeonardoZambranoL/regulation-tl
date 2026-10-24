"""Local SPLADE + dense RRF, bounded cross-encoder, resumable sparse index."""
import argparse
import hashlib
import importlib.metadata
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime
from fastembed import SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from tokenizers import Tokenizer

from hybrid import DEFAULT_INDEX, Retriever, digest, read_json, top_indices, write_json
from local_embed import CACHE, segments

SPARSE_MODEL = 'prithivida/Splade_PP_en_v1'
RERANK_MODEL = 'Xenova/ms-marco-MiniLM-L-6-v2'
VOCAB = 30522


def model_identity(model, name):
    h = hashlib.sha256()
    for p in sorted(model.model._model_dir.rglob('*')):
        if p.is_file() and p.suffix in {'.json', '.onnx', '.txt'}:
            h.update(str(p.relative_to(model.model._model_dir)).encode())
            with p.open('rb') as f:
                for block in iter(lambda: f.read(1024 * 1024), b''):
                    h.update(block)
    return f'{name}@{h.hexdigest()}:fastembed-{importlib.metadata.version("fastembed")}'


def load_model(kind, download=False, threads=4):
    onnxruntime.disable_telemetry_events()
    cls, name = (SparseTextEmbedding, SPARSE_MODEL) if kind == 'sparse' else (TextCrossEncoder, RERANK_MODEL)
    model = cls(model_name=name, cache_dir=str(CACHE), threads=threads, local_files_only=not download)
    tokenizer = Tokenizer.from_str(model.model.tokenizer.to_str())
    maximum = model.model.tokenizer.truncation['max_length']
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return model, tokenizer, maximum, model_identity(model, name)


def sparse_encode(texts, bundle):
    model, tok, maximum, _ = bundle
    groups = [segments(t, tok, maximum) for t in texts]
    vectors = iter(model.embed([s for g in groups for s in g], batch_size=4))
    result = []
    for group in groups:
        merged = {}
        for _ in group:
            v = next(vectors)
            for i, value in zip(v.indices, v.values):
                merged[int(i)] = max(merged.get(int(i), 0.), float(value))
        result.append(merged)
    return result


def build_sparse(index, max_batches=None):
    retriever = Retriever(index)
    out = Path(index) / 'splade'
    out.mkdir(exist_ok=True)
    bundle = load_model('sparse')
    manifest = {'corpus': retriever.manifest['fingerprint'], 'model': bundle[3],
                'pooling': 'max-overflow-v1', 'vocab': VOCAB}
    meta = out / 'manifest.json'
    if meta.exists() and read_json(meta) != manifest:
        raise ValueError('Sparse checkpoint belongs to a different corpus/model.')
    write_json(meta, manifest)
    # Each batch commits atomically. Interrupted batches can be recomputed safely.
    import sqlite3
    db = sqlite3.connect(out / 'checkpoint.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS vectors (id INTEGER PRIMARY KEY, vector TEXT NOT NULL)')
    done = {r[0] for r in db.execute('SELECT id FROM vectors')}
    order = sorted((i for i in range(len(retriever.chunks)) if i not in done),
                   key=lambda i: len(bundle[1].encode(retriever.chunks[i]['search_text']).ids))
    started = time.monotonic()
    for batch, start in enumerate(range(0, len(order), 32)):
        if max_batches is not None and batch >= max_batches:
            db.close()
            return {'complete': False, 'completed': len(done) + start, 'total': len(retriever.chunks)}
        ids = order[start:start + 32]
        vectors = sparse_encode([retriever.chunks[i]['search_text'] for i in ids], bundle)
        with db:
            db.executemany('INSERT INTO vectors VALUES (?,?)', [(i, json.dumps(v)) for i, v in zip(ids, vectors)])
        if batch % 8 == 0:
            print(f'SPLADE {len(done)+start+len(ids)}/{len(retriever.chunks)}; {time.monotonic()-started:.1f}s', flush=True)
    term, doc, value = [], [], []
    for i, raw in db.execute('SELECT id,vector FROM vectors ORDER BY id'):
        for t, v in json.loads(raw).items():
            term.append(int(t)); doc.append(i); value.append(v)
    db.close()
    order = np.argsort(term, kind='stable')
    terms = np.asarray(term, dtype=np.int32)[order]
    offsets = np.searchsorted(terms, np.arange(VOCAB + 1))
    temp = out / 'postings.tmp.npz'
    np.savez_compressed(temp, offsets=offsets, docs=np.asarray(doc, dtype=np.int32)[order],
                        values=np.asarray(value, dtype=np.float32)[order])
    temp.replace(out / 'postings.npz')
    write_json(out / 'complete.json', {**manifest, 'chunks': len(retriever.chunks), 'nonzero': len(term)})
    return read_json(out / 'complete.json')


class SparseDense:
    def __init__(self, index=DEFAULT_INDEX):
        self.base = Retriever(index)
        self.meta = read_json(Path(index) / 'splade/complete.json')
        if self.meta['corpus'] != self.base.manifest['fingerprint'] or self.meta['chunks'] != len(self.base.chunks):
            raise ValueError('Sparse corpus mismatch.')
        with np.load(Path(index) / 'splade/postings.npz', allow_pickle=False) as data:
            self.offsets, self.docs, self.values = (data[k] for k in ['offsets', 'docs', 'values'])
        if (len(self.offsets) != VOCAB + 1 or self.offsets[0] != 0 or
            self.offsets[-1] != len(self.docs) or len(self.docs) != len(self.values) or
            np.any(np.diff(self.offsets) < 0) or not np.isfinite(self.values).all() or
            np.any(self.values < 0) or np.any(self.docs < 0) or np.any(self.docs >= len(self.base.chunks))):
            raise ValueError('Invalid sparse postings.')
        self.bundle = None

    def query_vector(self, text):
        if self.bundle is None:
            self.bundle = load_model('sparse')
        if self.bundle[3] != self.meta['model']:
            raise ValueError('Sparse query model mismatch.')
        return sparse_encode([text], self.bundle)[0]

    def retrieve(self, text, vector, model, pool=300, limit=300, regulations=None,
                 method='rrf', sparse_vector=None, rrf_k=60):
        if vector is None or pool < 1 or limit < 1 or rrf_k <= 0 or method not in {'rrf', 'splade', 'dense'}:
            raise ValueError('Invalid retrieval configuration.')
        ids, _, dense = self.base.scores(text, vector, model, regulations)
        sparse = np.zeros(len(self.base.chunks), dtype=np.float64)
        q = self.query_vector(text) if sparse_vector is None else sparse_vector
        for t, weight in q.items():
            t = int(t)
            if not 0 <= t < VOCAB or not np.isfinite(weight) or weight < 0:
                raise ValueError('Invalid sparse query vector.')
            a, b = self.offsets[t:t + 2]
            np.add.at(sparse, self.docs[a:b], self.values[a:b] * weight)
        sparse = sparse[ids]
        stop = [int(i) for i in top_indices(sparse, pool) if sparse[i] > 0]
        dtop = list(map(int, top_indices(dense, pool)))
        rankings = [stop, dtop] if method == 'rrf' else [stop if method == 'splade' else dtop]
        scores, channels = {}, {}
        for channel, ranking in enumerate(rankings):
            for rank, i in enumerate(ranking, 1):
                scores[i] = scores.get(i, 0.) + 1 / (rrf_k + rank)
                channels.setdefault(i, []).append(channel)
        output, seen = [], set()
        for i in sorted(scores, key=lambda i: (-scores[i], int(ids[i]))):
            c = self.base.chunks[int(ids[i])]
            if c['clause_id'] in seen:
                continue
            seen.add(c['clause_id'])
            output.append({**c, 'score': scores[i], 'splade': float(sparse[i]),
                           'cosine': float(dense[i]), 'channels': channels[i]})
        return output[:limit], output


def rerank(text, candidates, bundle, head=100):
    """Reorder only the head; preserve the tail, never interpret scores as exclusions."""
    if head < 1:
        raise ValueError('Positive rerank head required.')
    model, tok, maximum, _ = bundle
    # Pair budget splits both sides; no silent truncation of a long specification.
    queries = segments(text, tok, min(160, maximum // 2))
    groups = [segments(c['search_text'], tok, maximum - 170) for c in candidates[:head]]
    if not groups:
        return list(candidates)
    flattened = [p for group in groups for p in group]
    scores = np.full(len(groups), -np.inf)
    for q in queries:
        values = np.asarray(list(model.rerank(q, flattened, batch_size=8)), dtype=float)
        if len(values) != len(flattened) or not np.isfinite(values).all():
            raise ValueError('Invalid cross-encoder scores.')
        offset = 0
        for i, group in enumerate(groups):
            scores[i] = max(scores[i], float(np.max(values[offset:offset+len(group)])))
            offset += len(group)
    ranked = sorted(enumerate(candidates[:head]), key=lambda x: (-scores[x[0]], x[0]))
    return [{**c, 'cross_encoder': float(scores[i])} for i, c in ranked] + candidates[head:]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['download', 'build', 'search'])
    p.add_argument('--index', type=Path, default=DEFAULT_INDEX)
    p.add_argument('--max-batches', type=int)
    p.add_argument('--query')
    p.add_argument('--pool', type=int, default=300)
    p.add_argument('--limit', type=int, default=20)
    p.add_argument('--rerank', type=int, default=0)
    p.add_argument('--out', type=Path)
    args = p.parse_args()
    if args.command == 'download':
        for kind in ['sparse', 'rerank']:
            print(load_model(kind, download=True)[3])
    elif args.command == 'build':
        print(json.dumps(build_sparse(args.index, args.max_batches)))
    else:
        if not args.query or args.pool < 1 or args.limit < 1 or args.rerank < 0:
            p.error('Provide query and valid positive limits.')
        from local_embed import load, encode
        enc, tok, maximum, identity = load(CACHE)
        v, _ = encode([args.query], enc, tok, maximum, query=True)
        engine = SparseDense(args.index)
        rows, union = engine.retrieve(args.query, v[0], identity, pool=args.pool, limit=2*args.pool)
        if args.rerank:
            rows = rerank(args.query, rows, load_model('rerank'), args.rerank)
        result = {'query': args.query, 'union_clauses': len(union), 'results': rows[:args.limit]}
        if args.out:
            write_json(args.out, result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
