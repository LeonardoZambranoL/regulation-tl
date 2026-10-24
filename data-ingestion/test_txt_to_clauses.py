import unittest

from txt_to_clauses import parse_text


class ParserTests(unittest.TestCase):
    def parse(self, body):
        source = '=== PDF PAGE 1 ===\r\n\r\nUN R148 (version 1.6.0)\r\n' + body
        result = parse_text(source)
        self.assertEqual(set(result), {'regulation', 'version', 'clauses'})
        return result['clauses']

    def test_cross_page_clause_and_parent(self):
        blocks = self.parse('5. Requirements\n5.1. Begins here\n'
                            'UN R148, version 1.6.0 | page 1 of 2\n'
                            '=== PDF PAGE 2 ===\ncontinues here.\n5.2. Next clause\n')
        clause = next(b for b in blocks if b['paragraph'] == '5.1')
        self.assertEqual(clause['pages'], [1, 2])
        self.assertIn('continues here.', clause['text'])
        self.assertNotIn('PDF PAGE', clause['text'])

    def test_annex_numbering_and_inline_reference(self):
        blocks = self.parse('1. Scope\nAnnex 1.\nAnnex 6 Heat resistance\n'
                            '1. Test duration\nAnnex 3.and other conditions.\n'
                            '2. Acceptance\n')
        self.assertEqual([b['paragraph'] for b in blocks],
                         [None, '1', 'Annex 6', 'Annex 6 / 1', 'Annex 6 / 2'])

    def test_table_numeric_rows_are_retained(self):
        blocks = self.parse('5. Limits\nTable 1 Values\n1   20   30\n'
                            '5.1. Next obligation\n')
        table = next(b for b in blocks if b['paragraph'] == 'Table 1')
        self.assertIn('1   20   30', table['text'])
        self.assertTrue(table['review_flags'])
        self.assertIn('5.1', [b['paragraph'] for b in blocks])

    def test_duplicate_is_flagged_without_losing_text(self):
        blocks = self.parse('1. Scope\n1. Repeated label\n')
        self.assertIn('duplicate_numbered_line', blocks[-1]['review_flags'])
        self.assertIn('Repeated label', blocks[-1]['text'])

    def test_missing_page_rejected(self):
        with self.assertRaises(ValueError):
            self.parse('1. Scope\n=== PDF PAGE 3 ===\ncontinued\n')


if __name__ == '__main__':
    unittest.main()
