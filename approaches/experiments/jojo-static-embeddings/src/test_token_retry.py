import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from client import Claude, BudgetStop
from contracts import obj, S

class Response:
    ok=True
    def __init__(self,body): self.body=body
    def json(self): return self.body

def completion(stop):
    return Response({'stop_reason':stop,'usage':{'input_tokens':100,'output_tokens':100},
                     'content':[{'type':'text','text':'{"answer":"ok"}'}]})

class TokenRetryTest(unittest.TestCase):
    def run_case(self, stop='end_turn', budget=10):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name); key=root/'key';key.write_text('test-placeholder')
        return Claude(root/'api',key_file=key,budget=budget)

    def test_bounded_retry_and_cache_reuse(self):
        client=self.run_case()
        with patch('client.requests.post',side_effect=[Response({'input_tokens':100}),completion('max_tokens'),Response({'input_tokens':100}),completion('end_turn')]) as api:
            self.assertEqual(client.ask('task',{},obj(answer=S)),{'answer':'ok'})
            self.assertEqual(api.call_count,4)
        with patch('client.requests.post') as api:
            self.assertEqual(client.ask('task',{},obj(answer=S)),{'answer':'ok'})
            api.assert_not_called()
        self.assertEqual(len(client.events),2)
        self.assertAlmostEqual(client.committed,.0024)

    def test_no_unbounded_retry(self):
        client=self.run_case()
        with patch('client.requests.post',side_effect=[Response({'input_tokens':100}),completion('max_tokens'),Response({'input_tokens':100}),completion('max_tokens')]) as api:
            with self.assertRaisesRegex(RuntimeError,'Incomplete'):
                client.ask('task',{},obj(answer=S))
            self.assertEqual(api.call_count,4)

    def test_larger_retry_respects_budget(self):
        client=self.run_case(budget=.2)
        with patch('client.requests.post',side_effect=[Response({'input_tokens':100}),completion('max_tokens'),Response({'input_tokens':100})]) as api:
            with self.assertRaises(BudgetStop): client.ask('task',{},obj(answer=S))
            self.assertEqual(api.call_count,3)

if __name__=='__main__': unittest.main()
