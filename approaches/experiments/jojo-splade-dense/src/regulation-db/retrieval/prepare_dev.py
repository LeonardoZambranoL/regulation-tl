"""Explicit diagnostic-only adapter. Never run as part of source index creation."""
import json
import re
from pathlib import Path

from hybrid import ROOT, write_json


def function_queries(spec):
    """Derive queries solely from the supplied spec, without reading expected answers."""
    sections = {}
    for block in re.split(r'^##\s+', spec, flags=re.M)[1:]:
        title, _, body = block.partition('\n')
        sections[title.strip().lower()] = body.strip()
    context = sections.get('product type', '') + '\n' + sections.get('vehicle category', '')
    queries = []
    for name in ['function', 'main parts']:
        for line in sections.get(name, '').splitlines():
            if line.startswith('- '):
                queries.append(context + '\nFind applicable engineering requirements for: ' + line[2:])
    if sections.get('materials'):
        queries.append(context + '\n' + sections['materials'])
    return list(dict.fromkeys(queries)) or [spec]


def main():
    out = Path(__file__).resolve().parent
    case_dir = ROOT / 'industrial-ai-hackathon/cases/dev-rear-lamp'
    spec = (case_dir / 'spec.md').read_text()
    # Queries are frozen before the expected answer is opened.
    strategies = {'full-spec': [spec], 'spec-functions': function_queries(spec)}
    gold = json.loads((case_dir / 'expected.json').read_text())
    relevant = sorted({(r['source']['regulation'], r['source']['version'], r['source']['page'])
                       for r in gold['requirements']})
    rows = []
    for strategy, queries in strategies.items():
        for i, text in enumerate(queries):
            rows.append({'id': f'dev-rear-lamp:{strategy}:{i}', 'group_id': 'dev-rear-lamp',
                         'split': 'diagnostic', 'strategy': strategy, 'text': text,
                         'relevant_pages': [{'regulation': r, 'version': v, 'page': p}
                                            for r, v, p in relevant]})
    (out / 'dev-flows.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    write_json(out / 'flow-config.json', {
        'pool_per_query': 300, 'page_budgets': [20, 50, 100, 200],
        'flows': [{'name': 'bm25', 'method': 'bm25'}, {'name': 'dense', 'method': 'dense'},
                  {'name': 'rrf-k60', 'method': 'rrf'},
                  {'name': 'score-fusion-0.5', 'method': 'hybrid', 'alpha': 0.5}]})


if __name__ == '__main__':
    main()
