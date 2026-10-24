"""Optional CPU encoder; only `download` accesses the network."""
import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime
from fastembed import TextEmbedding
from tokenizers import Tokenizer

from hybrid import DEFAULT_INDEX, digest, read_json, read_lines, unit_vectors, write_json

MODEL = 'BAAI/bge-small-en-v1.5'
CACHE = Path(__file__).resolve().parent / 'model-cache'


def load(cache, download=False, threads=4):
    onnxruntime.disable_telemetry_events()
    encoder = TextEmbedding(model_name=MODEL, cache_dir=str(cache), threads=threads,
                            local_files_only=not download)
    model_dir = encoder.model._model_dir
    files = sorted(p for p in model_dir.rglob('*') if p.is_file() and
                   (p.suffix in {'.json', '.onnx', '.txt'}))
    fingerprint = hashlib.sha256()
    for path in files:
        fingerprint.update(str(path.relative_to(model_dir)).encode())
        with path.open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                fingerprint.update(block)
    identity = (f'{MODEL}@{fingerprint.hexdigest()}:fastembed-'
                f'{importlib.metadata.version("fastembed")}:mean-overflow-v1')
    # Inspect untruncated token lengths. Long inputs are recursively split and pooled.
    tokenizer = Tokenizer.from_str(encoder.model.tokenizer.to_str())
    tokenizer.no_truncation()
    tokenizer.no_padding()
    max_tokens = encoder.model.tokenizer.truncation['max_length']
    return encoder, tokenizer, max_tokens, identity


def segments(text, tokenizer, max_tokens):
    if len(tokenizer.encode(text).ids) <= max_tokens:
        return [text]
    words = text.split()
    if len(words) > 1:
        mid = len(words) // 2
        left, right = ' '.join(words[:mid]), ' '.join(words[mid:])
    else:
        mid = len(text) // 2
        if mid == 0:
            raise ValueError('Tokenizer cannot encode a single character within context.')
        left, right = text[:mid], text[mid:]
    return segments(left, tokenizer, max_tokens) + segments(right, tokenizer, max_tokens)


def encode(texts, encoder, tokenizer, max_tokens, query=False):
    parts = [segments(t, tokenizer, max_tokens) for t in texts]
    flattened = [p for group in parts for p in group]
    method = encoder.query_embed if query else encoder.passage_embed
    vectors = list(method(flattened, batch_size=32))
    offset, output = 0, []
    for group in parts:
        # Pool all windows rather than silently discard the end of long source text.
        output.append(np.mean(vectors[offset:offset + len(group)], axis=0))
        offset += len(group)
    return unit_vectors(output), sum(len(group) > 1 for group in parts)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['download', 'corpus', 'query', 'dataset'])
    p.add_argument('--cache', type=Path, default=CACHE)
    p.add_argument('--index', type=Path, default=DEFAULT_INDEX)
    p.add_argument('--text')
    p.add_argument('--queries', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--threads', type=int, default=4)
    a = p.parse_args()
    if a.command in {'query', 'dataset'} and a.out is None:
        p.error('--out is required')
    if a.command == 'query' and not a.text:
        p.error('--text is required')
    if a.command == 'dataset' and a.queries is None:
        p.error('--queries is required')
    if a.out and a.out.exists():
        p.error('Output already exists; choose a new path.')
    if a.command == 'corpus' and ((a.index / 'dense.json').exists() or (a.index / 'dense.npy').exists()):
        p.error('Dense index already exists; choose a new index.')
    encoder, tokenizer, max_tokens, identity = load(a.cache, a.command == 'download', a.threads)
    if a.command == 'download':
        print(json.dumps({'model': identity, 'cache': str(a.cache), 'max_tokens': max_tokens}))
    elif a.command == 'corpus':
        chunks = read_lines(a.index / 'chunks.jsonl')
        # Similar sequence lengths avoid padding every short clause to the longest in a batch.
        order = sorted(range(len(chunks)), key=lambda i: len(tokenizer.encode(chunks[i]['search_text']).ids))
        vectors = np.zeros((len(chunks), encoder.embedding_size), dtype=np.float32)
        overflow = 0
        for start in range(0, len(chunks), 64):
            indices = order[start:start + 64]
            batch, n = encode([chunks[i]['search_text'] for i in indices], encoder, tokenizer, max_tokens)
            vectors[indices] = batch
            overflow += n
            if start % 1024 == 0:
                print(f'Embedded {min(start + 64, len(chunks))}/{len(chunks)}', file=sys.stderr, flush=True)
        np.save(a.index / 'dense.npy', vectors, allow_pickle=False)
        write_json(a.index / 'dense.json', {'model': identity, 'dimensions': len(vectors[0]),
                    'fingerprint': read_json(a.index / 'manifest.json')['fingerprint'],
                    'overflow_pooled_chunks': overflow, 'max_tokens': max_tokens})
        print(json.dumps({'chunks': len(vectors), 'overflow_pooled_chunks': overflow, 'model': identity}))
    elif a.command == 'query':
        vectors, overflow = encode([a.text], encoder, tokenizer, max_tokens, query=True)
        write_json(a.out, {'model': identity, 'text_sha256': digest(a.text), 'vector': vectors[0].tolist(),
                           'overflow_pooled_queries': overflow})
    else:
        queries = read_lines(a.queries)
        vectors, _ = encode([q['text'] for q in queries], encoder, tokenizer, max_tokens, query=True)
        with a.out.open('w') as f:
            for q, vector in zip(queries, vectors):
                f.write(json.dumps({**q, 'model': identity, 'text_sha256': digest(q['text']),
                                    'vector': vector.tolist()}, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
