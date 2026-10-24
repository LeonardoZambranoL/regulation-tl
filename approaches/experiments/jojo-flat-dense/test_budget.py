import unittest
from run_budgeted import segment_ceiling


class BudgetTests(unittest.TestCase):
    def test_resume_preserves_own_spend_and_excludes_other_runs(self):
        self.assertEqual(segment_ceiling(13, 1, 5, 17), 17)
        self.assertEqual(segment_ceiling(13, 4, 5, 17), 14)

    def test_shared_cap_and_exhaustion(self):
        self.assertEqual(segment_ceiling(16, 1, 5, 17), 17)
        with self.assertRaises(RuntimeError):
            segment_ceiling(12, 5, 5, 17)


if __name__ == '__main__':
    unittest.main()
