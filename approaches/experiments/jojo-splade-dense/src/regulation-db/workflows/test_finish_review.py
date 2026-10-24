import unittest
from finish_review import compact, validate_decisions


class RecoveryTests(unittest.TestCase):
    def test_context_round_trip_is_lossless(self):
        rows = [{'id': str(i), 'source_context': 'Exact source including 12.5 ± 0.2',
                 'section_context': [{'paragraph': '6.1', 'text': 'Only if condition applies'}]}
                for i in range(3)]
        payload = compact(rows)
        self.assertEqual(len(payload['contexts']), 2)
        restored = []
        for row in payload['requirements']:
            result = dict(row)
            for field in ('source_context', 'section_context'):
                result[field] = payload['contexts'][result.pop(field + '_ref')]
            restored.append(result)
        self.assertEqual(restored, rows)

    def test_missing_and_invalid_duplicate_rejected(self):
        keep = {'id': 'a', 'decision': 'keep', 'duplicate_of': '', 'reason': 'Evidence'}
        with self.assertRaises(ValueError):
            validate_decisions([keep], {'a', 'b'})
        with self.assertRaises(ValueError):
            validate_decisions([dict(keep, decision='drop', duplicate_of='b')], {'a'})
        self.assertEqual(validate_decisions([keep], {'a'}), {'a': keep})


if __name__ == '__main__':
    unittest.main()
