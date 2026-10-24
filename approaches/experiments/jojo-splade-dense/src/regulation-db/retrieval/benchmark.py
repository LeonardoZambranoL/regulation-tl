"""Controlled flow comparisons with equal page budgets; no alpha fitting here."""
import argparse
from collections import defaultdict
import json
import time

from hybrid import (DEFAULT_INDEX, Retriever, digest, metrics, page_keys, read_json,
                    read_lines, validate_queries, write_json)


def interleave(rankings):
    """Round-robin query merge; no second score-fusion algorithm confounding the test."""
    seen, output = set(), []
    for rank in range(max(map(len, rankings), default=0)):
        for ranking in rankings:
            if rank < len(ranking) and ranking[rank]['clause_id'] not in seen:
                row = ranking[rank]
                seen.add(row['clause_id'])
                output.append(row)
    return output


def benchmark(retriever, queries, config):
    validate_queries(queries, retriever)
    pool = config['pool_per_query']
    if pool < 1 or not config['page_budgets'] or min(config['page_budgets']) < 1:
        raise ValueError('Positive pool and page budgets are required.')
    if any(q.get('split') != 'diagnostic' for q in queries):
        raise ValueError('This exploratory runner requires split=diagnostic; use fit for held-out evaluation.')
    groups = defaultdict(list)
    for q in queries:
        groups[(q['group_id'], q['strategy'])].append(q)
    results = []
    for (group, strategy), case_queries in sorted(groups.items()):
        gold = case_queries[0]['relevant_pages']
        if any(q['relevant_pages'] != gold for q in case_queries):
            raise ValueError('All subqueries for a product must share its case-level gold pages.')
        for flow in config['flows']:
            started = time.perf_counter()
            rankings = [retriever.retrieve(q['text'], q.get('vector'), q.get('model'),
                         method=flow['method'], alpha=flow.get('alpha', 0.5), pool=pool,
                         limit=pool, regulations=q.get('regulations')) for q in case_queries]
            merged = interleave(rankings)
            results.append({'group': group, 'strategy': strategy, 'flow': flow['name'],
                            'method': flow['method'], 'alpha': flow.get('alpha'),
                            'query_count': len(case_queries),
                            'retrieval_seconds_excluding_encoding': time.perf_counter() - started,
                            'ranked_clause_pool_page_recall': metrics(merged, gold, max(1, len(page_keys(merged))))['recall'],
                            'budgets': {str(k): {**metrics(merged, gold, k),
                                       'returned_pages': len(page_keys(merged)[:k])}
                                        for k in config['page_budgets']},
                            'ranked_pages': [{'regulation': r, 'version': v, 'page': p}
                                             for r, v, p in page_keys(merged)[:max(config['page_budgets'])]]})
    return {'status': 'development diagnostic; not a held-out generalization claim',
            'independent_product_groups': len({q['group_id'] for q in queries}),
            'index_fingerprint': retriever.manifest['fingerprint'],
            'embedding': retriever.dense_meta, 'config': config,
            'dataset_sha256': digest(json.dumps(queries, sort_keys=True)),
            'metric_scope': 'Strict versioned page retrieval; no semantic requirement or applicability score. '
                            'Full clause spans can over-credit relevance; query encoding excluded from timings.',
            'results': results}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index', default=DEFAULT_INDEX)
    p.add_argument('--queries', required=True)
    p.add_argument('--config', required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    retriever = Retriever(args.index)
    report = benchmark(retriever, read_lines(args.queries), read_json(args.config))
    write_json(args.out, report)
    for r in report['results']:
        print(r['strategy'], r['flow'], json.dumps(r['budgets']))


if __name__ == '__main__':
    main()
