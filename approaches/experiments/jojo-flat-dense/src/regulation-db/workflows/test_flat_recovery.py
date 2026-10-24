import unittest
from unittest.mock import Mock

from client import BudgetStop, IncompleteResponse
from run import extraction_request


class RecoveryTests(unittest.TestCase):
    def test_known_truncation_gets_one_larger_request(self):
        client = Mock()
        client.ask.side_effect = [IncompleteResponse('max_tokens'), {'requirements': []}]
        self.assertEqual(extraction_request(client, 'task', {}, []), {'requirements': []})
        self.assertEqual([c.kwargs['max_tokens'] for c in client.ask.call_args_list], [16000, 32000])

    def test_other_failures_are_not_retried(self):
        for error in [IncompleteResponse('refusal'), BudgetStop('cap'), RuntimeError('uncertain network outcome')]:
            client = Mock()
            client.ask.side_effect = error
            with self.assertRaises(type(error)):
                extraction_request(client, 'task', {}, [])
            self.assertEqual(client.ask.call_count, 1)

    def test_second_truncation_stops(self):
        client = Mock()
        client.ask.side_effect = IncompleteResponse('max_tokens')
        with self.assertRaises(IncompleteResponse):
            extraction_request(client, 'task', {}, [])
        self.assertEqual(client.ask.call_count, 2)


if __name__ == '__main__':
    unittest.main()
