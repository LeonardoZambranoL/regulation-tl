import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from client import Claude, BudgetStop, BudgetCeilingReached, CacheMiss, read
from contracts import obj, S
from run import validate_packet, assemble, normalize, implementation_hash
from client import write, sha
from evaluate import frozen
from scoreboard import record
from run import common, review_payload, review
from sources import Sources
from jsonschema import validate, ValidationError
import resume_budgeted


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code, self.ok = body, status, status == 200
    def json(self):
        return self.body


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = self.root / 'test.key'
        self.key.write_text('synthetic-not-a-real-key')
        self.client = Claude(self.root / 'api', key_file=self.key)
        self.schema = obj(answer=S)
        self.response = Response({'stop_reason': 'end_turn', 'usage': {'input_tokens': 100, 'output_tokens': 50},
                                  'content': [{'type': 'text', 'text': '{"answer":"ok"}'}]})

    def test_cache_is_content_addressed_and_not_billed_twice(self):
        with patch('client.requests.post', side_effect=[Response({'input_tokens': 100}), self.response]) as api:
            self.assertEqual(self.client.ask('task', {'spec': 'a'}, self.schema), {'answer': 'ok'})
            first = self.client.committed
            self.assertEqual(self.client.ask('task', {'spec': 'a'}, self.schema), {'answer': 'ok'})
            self.assertEqual(self.client.committed, first)
            self.assertEqual(api.call_count, 2)
        self.assertNotIn('synthetic-not-a-real-key', self.client.ledger.read_text())
        self.assertNotIn('synthetic-not-a-real-key', next(self.client.cache.glob('*.json')).read_text())

    def test_budget_stops_before_paid_generation(self):
        self.client.budget = 0.00001
        with patch('client.requests.post', return_value=Response({'input_tokens': 100})) as api:
            with self.assertRaises(BudgetStop):
                self.client.ask('task', {}, self.schema)
            self.assertEqual(api.call_count, 1)
            self.assertIn('count_tokens', api.call_args.args[0])

    def test_offline_replay_never_calls_network_or_rewrites_shared_ledger(self):
        with patch('client.requests.post', side_effect=[Response({'input_tokens': 100}), self.response]):
            self.client.ask('task', {'spec': 'a'}, self.schema)
        offline = Claude(self.root / 'api', key_file=self.root / 'nonexistent.key', cache_only=True)
        before = offline.ledger.read_bytes()
        with patch('client.requests.post', side_effect=AssertionError('Network forbidden')):
            self.assertEqual(offline.ask('task', {'spec': 'a'}, self.schema), {'answer': 'ok'})
            with self.assertRaises(CacheMiss):
                offline.ask('missing', {}, self.schema)
        self.assertEqual(offline.ledger.read_bytes(), before)
        self.assertEqual(offline.usage_for(offline.calls)['unique_model_calls'], 1)

    def test_ambiguous_timeout_is_not_retried_or_forgotten(self):
        with patch('client.requests.post', side_effect=[Response({'input_tokens': 100}), requests.Timeout()]):
            with self.assertRaises(RuntimeError):
                self.client.ask('task', {}, self.schema)
        self.assertGreater(self.client.committed, 0)
        with patch('client.requests.post') as api:
            with self.assertRaises(BudgetStop):
                self.client.ask('task', {}, self.schema)
            api.assert_not_called()

    def test_auth_error_releases_reservation_without_echoing_error_body(self):
        with patch('client.requests.post', side_effect=[Response({'input_tokens': 100}), Response({'secret': 'hidden'}, 401)]):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 401'):
                self.client.ask('task', {}, self.schema)
        self.assertEqual(self.client.committed, 0)

    def test_truncated_response_not_accepted_as_submission(self):
        self.response.body['stop_reason'] = 'max_tokens'
        with patch('client.requests.post', side_effect=[Response({'input_tokens': 100}), self.response]):
            with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
                self.client.ask('task', {}, self.schema)
        self.assertGreater(self.client.committed, 0)


class WorkflowIntegrationTest(unittest.TestCase):
    def test_independent_budget_preserves_prior_costs_after_failure_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / 'experiment'
            out.mkdir()
            ledger = root / '.api/api-ledger.json'
            write(ledger, {'earlier': {'cost': 15}})
            argv = ['resume', '--out', str(out), '--prior-cost-usd', '11', '--total-budget-usd', '12']
            def failed_run(path, flow, ceiling, key):
                self.assertEqual(ceiling, 16)
                write(ledger, {'earlier': {'cost': 15}, 'new': {'cost': .3}})
                raise RuntimeError('test stop')
            with patch('sys.argv', argv), patch.object(resume_budgeted, 'run', side_effect=failed_run):
                with self.assertRaisesRegex(RuntimeError, 'test stop'):
                    resume_budgeted.main()
            self.assertAlmostEqual(read(out / 'attributed-budget.json')['attributed_workflow_total_usd'], 11.3)
            with patch('sys.argv', argv), patch.object(resume_budgeted, 'run') as resumed:
                resume_budgeted.main()
                self.assertAlmostEqual(resumed.call_args.args[2], 16)

    def test_review_deduplicates_evidence_without_losing_links(self):
        req = {'id': 'a', 'text': 'limit', 'source': {'regulation': 'R', 'version': '1', 'page': 3},
               'source_context': 'Full source text', 'section_context': [
                   {'page': 1, 'paragraph': '1', 'text': 'Condition applies'}]}
        payload = review_payload([req, {**req, 'id': 'b'}])
        self.assertEqual(len(payload['source_pages']), 1)
        self.assertEqual(len(payload['ancestor_context']), 1)
        self.assertEqual(payload['source_pages'][0]['text'], req['source_context'])
        self.assertEqual(payload['ancestor_context'][0]['text'], req['section_context'][0]['text'])
        for row in payload['requirements']:
            self.assertEqual(row['ancestor_context_ids'], [payload['ancestor_context'][0]['id']])
        with self.assertRaises(ValueError):
            review_payload([req, {**req, 'source_context': 'Conflicting text'}])

    def test_distant_section_conditions_follow_child_clauses(self):
        source = Sources.__new__(Sources)
        source.by_document = {'doc': [
            {'clause_id': 'a', 'paragraph': '7', 'page_start': 2, 'text': '7. Only during charging'},
            {'clause_id': 'z', 'paragraph': '7', 'page_start': 1, 'text': '7. Spurious earlier paragraph label'},
            {'clause_id': 'b', 'paragraph': '7.10', 'page_start': 8, 'text': '7.10. Emissions'},
            {'clause_id': 'c', 'paragraph': '7.10.1', 'page_start': 9, 'text': '7.10.1. Limit 63'},
            {'clause_id': 'd', 'paragraph': '70', 'page_start': 1, 'text': '70. Unrelated'},
            {'clause_id': 'e', 'paragraph': 'Annex 7', 'page_start': 20, 'text': 'Annex 7. Test'}]}
        parents = source.ancestors('doc', [9])
        self.assertEqual([p['paragraph'] for p in parents], ['7', '7.10'])
        self.assertIn('Only during charging', parents[0]['text'])

    def test_scope_contract_requires_all_regulations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'inputs').mkdir()
            (root / 'inputs/spec.md').write_text('Synthetic product')
            class Source:
                by_reg = {'UN R1': [], 'UN R2': []}
                def catalog_packet(self, batch):
                    return [{'regulation': r} for r in batch]
            class Client:
                def ask(self, task, data, schema, *args, **kwargs):
                    if 'regulations' not in data:
                        return {'facts': [{'fact': 'product', 'evidence': 'spec'}], 'unknowns': [], 'queries': ['product']}
                    decision = {'decision': 'excluded', 'reason': 'Synthetic scope reason', 'evidence_pages': []}
                    with self_test.assertRaises(ValidationError):
                        validate({'UN R1': decision}, schema)
                    result = {r: dict(decision) for r in Source.by_reg}
                    validate(result, schema)
                    return result
            self_test = self
            _, _, scope = common(Client(), Source(), root, {})
            self.assertEqual({s['regulation'] for s in scope}, set(Source.by_reg))
            self.assertTrue(all(s['decision'] == 'uncertain' for s in scope))

    def test_scorebook_keeps_cases_separate_and_rejects_modified_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def output(name, case):
                out = root / name
                write(out / 'submission.json', {'case_id': case, 'requirements': []})
                write(out / 'freeze.json', {'flow': name, 'submission_sha256': sha((out / 'submission.json').read_bytes())})
                return out
            old = output('old', 'case-a')
            new = output('new', 'case-b')
            alternative = output('alternative', 'case-b')
            ledger = root / 'scores.json'
            record(ledger, old, 99)
            self.assertEqual(record(ledger, new, 40)['score'], 40)
            self.assertEqual(record(ledger, alternative, 30)['score'], 40)
            (new / 'submission.json').write_text('{}')
            with self.assertRaises(ValueError):
                frozen(new)
            with self.assertRaises(ValueError):
                record(ledger, old, float('nan'))


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.packet = {'id': 'doc:P1', 'regulation': 'UN R1', 'version': '1', 'main_pages': [1],
                       'pages': [{'page': 1, 'text': 'The red lamp shall withstand 12 V.'}],
                       'owned_candidates': [{'candidate_id': 'c1'}]}
        self.result = {'requirements': [{'key': 'q1', 'text': 'The red lamp shall withstand 12 V.',
                         'page': 1, 'paragraph': '1', 'quote': 'shall withstand 12 V',
                         'evidence_type': 'text', 'candidate_ids': ['c1']}],
                       'decisions': [{'candidate_id': 'c1', 'decision': 'included',
                                      'reason': 'Applies to the specified lamp.', 'requirement_keys': ['q1']}],
                       'issues': []}

    def test_source_evidence_and_candidate_link_pass(self):
        validate_packet(self.result, self.packet)
        reqs, ledger, _ = assemble([(self.packet, self.result)])
        self.assertEqual(ledger[0]['requirement_ids'], [reqs[0]['id']])

    def test_wrong_page_and_invented_quote_rejected(self):
        for field, value in [('page', 99), ('quote', 'shall withstand 24 V')]:
            modified = copy.deepcopy(self.result)
            modified['requirements'][0][field] = value
            with self.assertRaises(ValueError):
                validate_packet(modified, self.packet)

    def test_silent_candidate_omission_rejected(self):
        self.result['decisions'] = []
        with self.assertRaises(ValueError):
            validate_packet(self.result, self.packet)

    def test_image_evidence_requires_actual_image(self):
        self.result['requirements'][0]['evidence_type'] = 'image'
        with self.assertRaises(ValueError):
            validate_packet(self.result, self.packet, has_images=False)

    def test_dedup_preserves_provenance_links(self):
        second = copy.deepcopy(self.packet)
        second['id'] = 'doc:P2'
        result = copy.deepcopy(self.result)
        result['decisions'][0]['candidate_id'] = 'c2'
        reqs, ledger, _ = assemble([(self.packet, self.result), (second, result)])
        self.assertEqual(len(reqs), 1)
        self.assertEqual(ledger[0]['requirement_ids'], ledger[1]['requirement_ids'])

    def test_code_fingerprint_is_stable(self):
        self.assertEqual(implementation_hash(), implementation_hash())


class ReviewBudgetTest(unittest.TestCase):
    def test_budget_defers_unchecked_drafts_and_uncertain_billing_still_fails(self):
        reqs = [{'id': str(i), 'text': 'Duty', 'source': {'regulation': 'UN R7',
                 'version': '1', 'page': i + 1}, 'source_context': 'Source'} for i in range(3)]
        kept = {'decisions': [{'id': '0', 'decision': 'keep', 'reason': 'Supported.', 'duplicate_of': ''}]}
        with patch('client.Claude.ask', side_effect=[kept, BudgetCeilingReached('Cap')]) as ask:
            verdicts = review(Claude.__new__(Claude), reqs, 'spec', {}, {'review_batch': 1})
            self.assertEqual(ask.call_count, 2)
            self.assertEqual(verdicts['0']['decision'], 'keep')
            for rid in ['1', '2']:
                self.assertEqual(verdicts[rid]['decision'], 'unresolved')
                self.assertTrue(verdicts[rid]['review_not_performed'])
        with patch('client.Claude.ask', side_effect=BudgetStop('Uncertain billing')):
            with self.assertRaises(BudgetStop):
                review(Claude.__new__(Claude), reqs, 'spec', {}, {'review_batch': 1})


if __name__ == '__main__':
    unittest.main()
