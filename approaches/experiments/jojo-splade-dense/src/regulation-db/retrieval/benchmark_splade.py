"""Paired development ablations; labels are used only after every ranking is frozen."""
import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

from benchmark import interleave
from hybrid import DEFAULT_INDEX, digest, metrics, page_keys, read_lines, validate_queries, write_json
from splade_pipeline import SparseDense, load_model, rerank


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--queries', type=Path, default=Path(__file__).with_name('dev-flows-embedded.jsonl'))
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error('Choose a new result path.')
    engine = SparseDense(DEFAULT_INDEX)
    queries = read_lines(a.queries)
    validate_queries(queries, engine.base)
    if any(q.get('split') != 'diagnostic' for q in queries):
        raise ValueError('This is a development-only benchmark.')
    ce = load_model('rerank')
    runs, union_runs, times = defaultdict(list), defaultdict(list), defaultdict(float)
    config = {'pools': [100, 300, 1000], 'rerank_heads': [50, 100, 200], 'rrf_k': 60,
              'budgets': [20, 50, 100, 200], 'rerank_pool': 300}
    encoding = 0.
    for q in queries:
        started = time.monotonic()
        sv = engine.query_vector(q['text'])
        encoding += time.monotonic() - started
        prefix = (q['group_id'], q['strategy'])
        for method in ['bm25', 'dense', 'rrf', 'hybrid']:
            start = time.monotonic()
            rows = engine.base.retrieve(q['text'], q['vector'], q['model'], method=method, pool=300, limit=300)
            key = (*prefix, 'baseline-' + method)
            runs[key].append(rows); times[key] += time.monotonic() - start
        for pool in config['pools']:
            for method in ['splade', 'rrf']:
                start = time.monotonic()
                rows, union = engine.retrieve(q['text'], q['vector'], q['model'], pool=pool,
                                              limit=2*pool, method=method, sparse_vector=sv)
                key = (*prefix, f'{method}-pool{pool}')
                runs[key].append(rows); union_runs[key].append(union); times[key] += time.monotonic() - start
                if method == 'rrf' and pool == config['rerank_pool']:
                    start_ce = time.monotonic()
                    ranked = rerank(q['text'], rows, ce, max(config['rerank_heads']))
                    by_id = {r['id']: r['cross_encoder'] for r in ranked if 'cross_encoder' in r}
                    ce_seconds = time.monotonic() - start_ce
                    for head in config['rerank_heads']:
                        reranked = sorted(rows[:head], key=lambda r: -by_id[r['id']]) + rows[head:]
                        ckey = (*prefix, f'rrf-pool{pool}-ce{head}')
                        runs[ckey].append(reranked); union_runs[ckey].append(union)
                        # A shared CE200 pass supplies smaller ablations; no fabricated independent timing.
                        times[ckey] += ce_seconds
        print('Rankings frozen:', q['id'], flush=True)
    # Persist label-free rankings before evaluating them.
    frozen = {'config': config, 'corpus': engine.base.manifest['fingerprint'],
              'sparse_model': engine.meta, 'cross_encoder': ce[3],
              'dense_model': engine.base.dense_meta,
              'query_sha256': digest(json.dumps([{k: q[k] for k in ['id','text']} for q in queries], sort_keys=True)),
              'runs': [{'group': k[0], 'strategy': k[1], 'flow': k[2], 'rankings': [[{field: row[field] for field in ['id','clause_id','regulation','version','page_start','page_end','score','cross_encoder'] if field in row} for row in ranking] for ranking in v]} for k,v in runs.items()]}
    write_json(a.out.with_suffix('.rankings.json'), frozen)
    results = []
    for key, rankings in runs.items():
        group, strategy, flow = key
        gold = next(q['relevant_pages'] for q in queries if (q['group_id'], q['strategy']) == (group,strategy))
        merged = interleave(rankings)
        union_pages = set(page_keys(interleave(union_runs[key]))) if key in union_runs else None
        relevant = {(r['regulation'], r['version'], r['page']) for r in gold}
        results.append({'group': group, 'strategy': strategy, 'flow': flow,
                        'query_count': len(rankings), 'seconds_excluding_encoding': times[key],
                        'candidate_union_page_recall': len(relevant & union_pages)/len(relevant) if union_pages is not None else None,
                        'budgets': {str(k): {**metrics(merged,gold,k),
                          'hits': len(set(page_keys(merged)[:k]) & relevant)} for k in config['budgets']}})
    report = {'status': 'development diagnostic; one product; no held-out validation',
              'config': config, 'sparse_model': engine.meta, 'cross_encoder': ce[3],
              'sparse_query_encoding_seconds': encoding,
              'timing_note': 'Dense query encoding excluded. CE50/100/200 share the measured CE200 pass; these are not independent timing measurements.',
              'metric_note': 'Versioned page navigation, full clause spans. Not requirement accuracy. Candidate union after best-window clause deduplication.',
              'results': results}
    write_json(a.out, report)
    for row in results:
        print(row['strategy'],row['flow'],{k:v['hits'] for k,v in row['budgets'].items()})


if __name__ == '__main__':
    main()
