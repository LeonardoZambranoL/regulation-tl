"""Claude JSON requests with durable caching and a shared conservative dollar ceiling."""
import base64
import hashlib
import json
import os
import time
import threading
from pathlib import Path

import requests
from jsonschema import validate

from contracts import SYSTEM

PRICES = {'claude-sonnet-5-5': (2.0, 10.0), 'claude-sonnet-4-6': (3.0, 15.0)}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def sha(value):
    return hashlib.sha256(value).hexdigest()


class BudgetStop(RuntimeError):
    pass


class IncompleteResponse(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(f'Incomplete Claude response ({reason}); cached for inspection, not accepted.')


class Claude:
    def __init__(self, root, model='claude-sonnet-5-5', budget=10, key_file=None):
        if model not in PRICES or budget <= 0:
            raise ValueError('Choose a priced model and a positive budget.')
        self.root, self.model, self.budget = Path(root), model, budget
        self.cache = self.root / 'responses'
        self.cache.mkdir(parents=True, exist_ok=True)
        self.ledger = self.root / 'api-ledger.json'
        self.key = Path(key_file).read_text().strip() if key_file else os.environ.get('ANTHROPIC_API_KEY', '')
        self.events = read(self.ledger) if self.ledger.exists() else {}
        self.calls = []
        self.lock = threading.RLock()

    @property
    def committed(self):
        with self.lock:
            return sum(e['cost'] for e in self.events.values())

    def ask(self, task, data, schema, images=(), max_tokens=12000):
        content = [{'type': 'text', 'text': task + '\nSOURCE DATA:\n' + json.dumps(data, ensure_ascii=False)}]
        for label, path in images:
            raw = Path(path).read_bytes()
            media = 'image/png' if raw[:8] == b'\x89PNG\r\n\x1a\n' else 'image/jpeg'
            content += [{'type': 'text', 'text': label},
                        {'type': 'image', 'source': {'type': 'base64', 'media_type': media,
                                                    'data': base64.b64encode(raw).decode()}}]
        body = {'model': self.model, 'max_tokens': max_tokens, 'system': SYSTEM,
                'messages': [{'role': 'user', 'content': content}],
                'output_config': {'format': {'type': 'json_schema', 'schema': schema}}}
        raw_body = json.dumps(body, ensure_ascii=False).encode()
        request_id = sha(raw_body)
        with self.lock:
            self.calls.append(request_id)
        path = self.cache / (request_id + '.json')
        if path.exists():
            response = read(path)
        else:
            if not self.key:
                raise RuntimeError('ANTHROPIC_API_KEY is absent. Set it locally or pass --key-file outside the repository.')
            if request_id in self.events:
                raise BudgetStop('A prior request has uncertain billing/outcome; inspect api-ledger.json before retrying.')
            in_rate, out_rate = PRICES[self.model]
            # Count the image/text input without generation, then reserve schema overhead + maximum output.
            try:
                counted = requests.post('https://api.anthropic.com/v1/messages/count_tokens',
                    headers={'x-api-key': self.key, 'anthropic-version': '2023-06-01'},
                    json={k: body[k] for k in ['model', 'system', 'messages']}, timeout=(20, 60))
            except requests.RequestException:
                raise RuntimeError('Input token counting failed; no generation sent.') from None
            if not counted.ok:
                raise RuntimeError(f'Input token counting HTTP {counted.status_code}; no generation sent.')
            input_upper = counted.json()['input_tokens'] + len(json.dumps(schema).encode()) + 8192
            reserve = (input_upper * in_rate + max_tokens * out_rate) / 1e6
            with self.lock:
                if self.committed + reserve > self.budget:
                    raise BudgetStop(f'Budget ceiling reached: ${self.committed:.3f} committed, next reserve ${reserve:.3f}.')
                if request_id in self.events:
                    raise BudgetStop('Request already in progress or unresolved; duplicate generation refused.')
                self.events[request_id] = {'status': 'reserved', 'cost': reserve, 'started_at': time.time(), 'model': self.model}
                write(self.ledger, self.events)
            started = time.monotonic()
            try:
                r = requests.post('https://api.anthropic.com/v1/messages',
                                  headers={'x-api-key': self.key, 'anthropic-version': '2023-06-01',
                                           'content-type': 'application/json'}, data=raw_body, timeout=(20, 240))
            except requests.RequestException:
                raise RuntimeError('Claude network outcome is uncertain; reservation retained. Resume does not retry blindly.') from None
            if not r.ok:
                # Never print the response body or request headers: neither is needed for authentication diagnostics.
                if r.status_code in {400, 401, 403, 404, 413, 429}:
                    with self.lock:
                        self.events.pop(request_id)
                        write(self.ledger, self.events)
                raise RuntimeError(f'Claude HTTP {r.status_code}; request stopped, no automatic paid retry.')
            response = r.json()
            response['_wall_seconds'] = time.monotonic() - started
            write(path, response)
        usage = response.get('usage', {})
        if any(not isinstance(usage.get(k), int) or usage[k] < 0 for k in ['input_tokens', 'output_tokens']):
            raise RuntimeError('Response lacks valid usage accounting; reservation retained.')
        in_rate, out_rate = PRICES[self.model]
        cost = (usage.get('input_tokens', 0) * in_rate + usage.get('output_tokens', 0) * out_rate +
                usage.get('cache_creation_input_tokens', 0) * in_rate * 1.25 +
                usage.get('cache_read_input_tokens', 0) * in_rate * 0.1) / 1e6
        with self.lock:
            self.events[request_id] = {'status': 'completed', 'cost': cost, 'usage': usage,
                                       'wall_seconds': response.get('_wall_seconds'), 'model': self.model}
            write(self.ledger, self.events)
        if response.get('stop_reason') not in {'end_turn', 'stop_sequence'}:
            raise IncompleteResponse(response.get('stop_reason'))
        text = ''.join(c.get('text', '') for c in response.get('content', []) if c.get('type') == 'text')
        result = json.loads(text)
        validate(result, schema)
        return result

    def usage_for(self, request_ids):
        events = [self.events[i] for i in set(request_ids)]
        return {'unique_model_calls': len(events), 'standalone_model_cost_estimate_usd': sum(e['cost'] for e in events),
                'model_seconds_sum': sum(e.get('wall_seconds') or 0 for e in events),
                'shared_experiment_committed_usd': self.committed}
