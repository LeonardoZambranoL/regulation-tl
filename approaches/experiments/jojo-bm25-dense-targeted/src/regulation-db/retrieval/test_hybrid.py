"""Synthetic vectors test the algorithm, not semantic retrieval quality."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import numpy as np

from hybrid import (Retriever, build, digest, evaluate, fit, import_dense, metrics,
                    normalize, read_lines, unit_vectors, validate_queries)
from benchmark import benchmark, interleave
from prepare_dev import function_queries


class HybridTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db, self.index = self.root / 'source.sqlite', self.root / 'index'
        with sqlite3.connect(self.db) as c:
            c.executescript('''
              CREATE TABLE documents(document_id TEXT,regulation TEXT,version TEXT,role TEXT,title TEXT,sha256 TEXT,pdf_path TEXT);
              CREATE TABLE clauses(clause_id TEXT,document_id TEXT,paragraph TEXT,kind TEXT,page_start INTEGER,page_end INTEGER,text TEXT);
            ''')
            c.executemany('INSERT INTO documents VALUES (?,?,?,?,?,?,?)', [
                ('base', 'UN R1', '1', 'base', 'Vehicle requirements', 'basehash', 'base.pdf'),
                ('latest', 'UN R1', '2', 'latest', 'Vehicle requirements', 'newhash', 'latest.pdf')])
            c.executemany('INSERT INTO clauses VALUES (?,?,?,?,?,?,?)', [
                ('lamp', 'base', '1', 'clause', 1, 1, 'The rear lamp shall emit red light.'),
                ('brake', 'base', '2', 'clause', 2, 2, 'The brake shall stop the vehicle.'),
                ('tyre', 'base', '3', 'clause', 3, 3, 'The tyre shall withstand pressure.'),
                ('new-lamp', 'latest', '1', 'clause', 1, 1, 'The rear lamp latest latest rear lamp.')])
        build(self.db, self.index)
        self.vectors_path = self.root / 'vectors.jsonl'
        self.rows = [{**{k: c[k] for k in ['id', 'text_sha256']},
                      'vector': {'lamp': [1, 0], 'brake': [0, 1], 'tyre': [-1, 0]}[c['clause_id']]}
                     for c in read_lines(self.index / 'chunks.jsonl')]
        self.save_vectors()
        import_dense(self.index, self.vectors_path, 'synthetic-v1')
        self.r = Retriever(self.index)
        self.addCleanup(self.r.lexical.close)

    def save_vectors(self):
        self.vectors_path.write_text(''.join(json.dumps(r) + '\n' for r in self.rows))

    def queries(self):
        return [{'id': split, 'group_id': split + '-product', 'split': split,
                 'text': 'rear lamp ' + split, 'text_sha256': digest('rear lamp ' + split),
                 'vector': [0, 1], 'model': 'synthetic-v1',
                 'relevant_pages': [{'regulation': 'UN R1', 'version': '1', 'page': 1}]}
                for split in ['train', 'validation', 'test']]

    def test_default_role_and_source_immutable(self):
        self.assertTrue(all(c['role'] == 'base' for c in self.r.chunks))
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM clauses').fetchone()[0], 4)
        self.assertEqual(self.r.manifest['chunks'], 3)

    def test_bm25_direction_and_literal_query(self):
        result = self.r.retrieve('rear lamp " ) NOT impossible', method='bm25')
        self.assertEqual(result[0]['clause_id'], 'lamp')
        self.assertGreater(result[0]['bm25'], 0)

    def test_dense_and_alpha_endpoints(self):
        for alpha, expected in [(0, 'brake'), (1, 'lamp')]:
            result = self.r.retrieve('rear lamp', [0, 1], 'synthetic-v1', alpha=alpha)
            self.assertEqual(result[0]['clause_id'], expected)

    def test_union_rescores_both_modalities(self):
        result = self.r.retrieve('rear lamp', [0.6, 0.8], 'synthetic-v1', pool=1, limit=1, alpha=1)
        self.assertEqual(result[0]['clause_id'], 'lamp')
        self.assertAlmostEqual(result[0]['cosine'], 0.6, places=5)

    def test_rrf_baseline(self):
        result = self.r.retrieve('rear lamp', [1, 0], 'synthetic-v1', method='rrf')
        self.assertEqual(result[0]['clause_id'], 'lamp')
        self.assertAlmostEqual(result[0]['score'], 2 / 61)

    def test_filtered_empty_bm25(self):
        self.assertEqual(self.r.retrieve('unknownzzz', method='bm25'), [])
        self.assertEqual(self.r.retrieve('unknownzzz', [1, 0], 'synthetic-v1', alpha=1), [])
        with self.assertRaises(ValueError):
            self.r.retrieve('lamp', method='bm25', regulations=['UN R99'])

    def test_bad_vectors_and_model(self):
        for vector in [[0, 0], [float('nan'), 1], [1, 2, 3]]:
            with self.assertRaises(ValueError):
                self.r.retrieve('lamp', vector, 'synthetic-v1')
        with self.assertRaises(ValueError):
            self.r.retrieve('lamp', [1, 0], 'other')
        with self.assertRaises(ValueError):
            self.r.retrieve('lamp')

    def test_import_wrong_ids_and_hash(self):
        for change in ['id', 'text_sha256']:
            other = self.root / ('index-' + change)
            build(self.db, other)
            rows = copy.deepcopy(self.rows)
            rows[0][change] = 'wrong'
            self.vectors_path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
            with self.assertRaises(ValueError):
                import_dense(other, self.vectors_path, 'synthetic-v1')

    def test_no_silent_dense_overwrite(self):
        with self.assertRaises(ValueError):
            import_dense(self.index, self.vectors_path, 'other-model')

    def test_normalization_constant_and_negative_cosine(self):
        np.testing.assert_array_equal(normalize(np.array([4., 4.])), [0, 0])
        np.testing.assert_array_equal(normalize(np.array([-1., 0., 1.])), [0, 0.5, 1])
        np.testing.assert_allclose(unit_vectors([[3, 4]]), [[0.6, 0.8]])

    def test_weight_learning_and_held_out_baselines(self):
        result = fit(self.r, self.queries(), pool=3, k=1, steps=10)
        self.assertGreater(result['alpha'], 0)
        self.assertEqual(result['held_out_test']['hybrid']['mean']['recall'], 1)
        self.assertEqual(result['held_out_test']['dense']['mean']['recall'], 0)
        self.assertEqual(set(result['held_out_test']), {'bm25', 'dense', 'rrf', 'hybrid'})

    def test_test_labels_cannot_affect_weight(self):
        queries = self.queries()
        first = fit(self.r, queries, pool=3, k=1, steps=10)['alpha']
        queries[2]['relevant_pages'][0]['page'] = 2
        self.assertEqual(first, fit(self.r, queries, pool=3, k=1, steps=10)['alpha'])

    def test_reject_case_leakage_and_single_case(self):
        queries = self.queries()
        queries[1]['group_id'] = queries[0]['group_id']
        with self.assertRaises(ValueError):
            fit(self.r, queries)
        with self.assertRaises(ValueError):
            fit(self.r, self.queries()[:1])

    def test_reject_query_leakage_and_stale_embedding(self):
        queries = self.queries()
        queries[1]['text'] = queries[0]['text']
        with self.assertRaises(ValueError):
            validate_queries(queries, self.r, True)
        queries[1]['text_sha256'] = queries[0]['text_sha256']
        with self.assertRaises(ValueError):
            validate_queries(queries, self.r, True)

    def test_page_metrics_version_and_duplicate_aware(self):
        row = {'regulation': 'UN R1', 'version': '1', 'page_start': 1, 'page_end': 1}
        gold = [{'regulation': 'UN R1', 'version': '1', 'page': 1}]
        self.assertEqual(metrics([row, row], gold, 2)['recall'], 1)
        self.assertEqual(metrics([dict(row, version='2')], gold, 2)['recall'], 0)
        self.assertEqual(metrics([], gold, 2)['recall'], 0)

    def test_overlapping_windows_and_dedup(self):
        other = self.root / 'small-chunks'
        build(self.db, other, words=4, overlap=1)
        retriever = Retriever(other)
        self.addCleanup(retriever.lexical.close)
        chunks = [c for c in retriever.chunks if c['clause_id'] == 'lamp']
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0]['text'].split()[-1], chunks[1]['text'].split()[0])
        results = retriever.retrieve('rear lamp light', method='bm25')
        self.assertEqual(len(results), len({r['clause_id'] for r in results}))

    def test_multiquery_merge_preserves_rank_and_deduplicates(self):
        a, b, c = [{'clause_id': name} for name in ['a', 'b', 'c']]
        self.assertEqual(interleave([[a, b], [a, c]]), [a, b, c])

    def test_spec_decomposition_uses_input_only(self):
        spec = '## Product Type\nLamp\n## Vehicle Category\nM1\n## Function\n- Braking\n- Reversing\n'
        queries = function_queries(spec)
        self.assertEqual(len(queries), 2)
        self.assertIn('Braking', queries[0])
        self.assertIn('M1', queries[1])

    def test_benchmark_equal_page_budget(self):
        q = self.queries()[0]
        q.update(split='diagnostic', strategy='full-spec')
        report = benchmark(self.r, [q], {'pool_per_query': 3, 'page_budgets': [1],
                           'flows': [{'name': 'bm25', 'method': 'bm25'},
                                     {'name': 'dense', 'method': 'dense'}]})
        self.assertEqual(len(report['results']), 2)
        self.assertTrue(all(r['budgets']['1']['returned_pages'] == 1 for r in report['results']))


if __name__ == '__main__':
    unittest.main()
