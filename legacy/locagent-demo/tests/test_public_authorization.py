"""No credentials, no network: exact operator authorization with raw HTTP stubs."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from locagent_service import public_authorization as auth, budget, response_store
from locagent_service.deepseek_http import RawHTTP
from locagent_service.engine_binding import behavior_hashes
from locagent_service.models import CreateTask, replay_safe
from locagent_service.sources import canonical, digest, file_hashes, registry

CONFIG = {'endpoint': 'https://provider.example/chat/completions', 'model': 'stub-model',
    'response_models': ['stub-model'], 'credential_env': 'NEVER_READ_TEST_KEY', 'currency': 'USD',
    'input_per_million': '1', 'output_per_million': '2', 'budget': '0.0022',
    'context_tokens': 1000, 'output_tokens': 100, 'max_calls': 3,
    'request_bytes': 200000, 'timeout_seconds': 10,
    'pricing_confirmation': 'TEST ONLY: synthetic all-in peak prices; no real provider authorized'}


def raw_response(pt=10, ct=5):
    return RawHTTP(200, canonical({'id': 'stub-response', 'model': 'stub-model',
        'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
            'role': 'assistant', 'content': None, 'tool_calls': [{
                'id': 'finish-test', 'type': 'function', 'function': {
                    'name': 'finish', 'arguments': '{"files":[],"entities":[]}'}}]}}],
        'usage': {'prompt_tokens': pt, 'completion_tokens': ct, 'total_tokens': pt + ct}}))


def prepare_grant(config=None, manifest=None):
    root = registry()
    root.mkdir(parents=True, exist_ok=True)
    if manifest is None:
        bundle = root/'unit-bundle'
        bundle.mkdir(exist_ok=True)
        (bundle/'fixture.txt').write_text('No executable repository code')
        manifest = {'version': 2, 'bundle': bundle.name, 'task': {
            'repo': 'a/b', 'base_commit': 'a'*40, 'instance_id': 'unit',
            'problem_statement': 'Find serialize'},
            'config': {'provider': 'fake-only', 'model': 'offline-public-preview', 'max_calls': 3},
            'engine': behavior_hashes(Path(auth.__file__).resolve().parents[1]),
            'artifacts': file_hashes(bundle)}
    data = canonical(manifest)
    source = 'prepared-' + digest(data)
    (root/(source+'.json')).write_bytes(data)
    plan = auth.make_plan(source, CONFIG if config is None else config)
    identity = auth.authorize(plan, digest(canonical(plan)))
    request = CreateTask(source_id='github-v1', repository_url='https://github.com/a/b',
        ref='a'*40, problem_statement='Find serialize', authorization_id=identity,
        options={'max_iterations': plan['provider']['max_calls']}, max_attempts=1)
    return plan, request


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='public-auth-unit-')
        root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {
            'LOCAGENT_SOURCE_ROOT': str(root/'sources'), 'LOCAGENT_PUBLIC_ROOT': str(root/'sources'),
            'LOCAGENT_PUBLIC_AUTH_ROOT': str(root/'authority'), 'LOCAGENT_PUBLIC_LIVE': '1',
            'LOCAGENT_PUBLIC_PREVIEW': '1', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True'})
        self.environment.start()
        self.plan, self.request = prepare_grant()
        self.path = Path(auth.grant(self.request.authorization_id)[0]['ledger_path'])
        self.claim = SimpleNamespace(id=uuid4(), token=uuid4())
        # Any accidental use of the real transport is a test failure.
        self.real_exchange = auth.exchange
        self.transport = patch.object(auth, 'exchange', side_effect=AssertionError('Real transport forbidden'))
        self.transport.start()

    def tearDown(self):
        self.transport.stop()
        self.environment.stop()
        self.temp.cleanup()

    def provider(self, callback=None, report=lambda _: None):
        return auth.AuthorizedProvider(self.request, self.claim, report,
            raw_completion=callback or (lambda *_: raw_response()))

    def state(self):
        return auth.read_json(self.path)

    def test_default_disabled_and_legacy_switch_grants_nothing(self):
        with patch.dict(os.environ, {'LOCAGENT_PUBLIC_LIVE': '0', 'LOCAGENT_ALLOW_PAID': '1'}):
            with self.assertRaises(auth.AuthorizationError):
                auth.validate_request(self.request)
        self.assertEqual(self.state()['calls'], [])

    def test_exact_request_and_plan_binding(self):
        for changes in ({'problem_statement': 'different'}, {'ref': 'b'*40},
                        {'repository_url': 'https://github.com/a/c'},
                        {'options': {'max_iterations': 2}},
                        {'options': {'max_iterations': 3, 'suppress_repeats': False}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                auth.validate_request(CreateTask(**(self.request.model_dump() | changes)))
        for key, value in [('model', 'other'), ('endpoint', 'https://other.example/chat'),
                           ('budget', '100'), ('input_per_million', '2'), ('max_calls', 4)]:
            changed = copy.deepcopy(self.plan)
            changed['provider'][key] = value
            with self.assertRaises(ValueError):
                auth.authorize(changed, self.request.authorization_id)

    def test_authorization_exclusive_interrupted_and_relocated_fail_closed(self):
        with self.assertRaises(FileExistsError):
            auth.authorize(self.plan, self.request.authorization_id)
        self.path.unlink()
        with self.assertRaises(FileExistsError):
            auth.authorize(self.plan, self.request.authorization_id)
        with self.assertRaises(OSError):
            self.provider()
        other = Path(self.temp.name)/'other'
        other.mkdir(mode=0o700)
        with patch.dict(os.environ, {'LOCAGENT_PUBLIC_AUTH_ROOT': str(other)}):
            with self.assertRaises(ValueError):
                auth.authorize(self.plan, self.request.authorization_id)

    def test_private_root_and_symlink_are_rejected(self):
        root = auth.authority_root()
        root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.provider()
        root.chmod(0o700)
        linked = Path(self.temp.name)/'link'
        linked.symlink_to(root)
        with patch.dict(os.environ, {'LOCAGENT_PUBLIC_AUTH_ROOT': str(linked)}):
            with self.assertRaises(ValueError):
                self.provider()

    def test_reservation_is_durable_before_send_raw_before_settlement(self):
        def send(config, data, capacity):
            state = self.state()
            self.assertEqual(state['reserved'], str(auth.reserve(CONFIG)))
            self.assertEqual(state['calls'][0]['status'], 'reserved')
            self.assertTrue(self.path.with_name('inflight.json').exists())
            self.assertEqual(json.loads(data)['model'], 'stub-model')
            return raw_response()
        provider = self.provider(send)
        provider(messages=[{'role': 'user', 'content': 'x'}], model='evil', api_key='not-a-key')
        state = self.state()
        self.assertEqual(state['spent'], '0.00002')
        self.assertEqual(state['reserved'], '0')
        self.assertEqual(response_store.read(self.path, 0, state['calls'][0]['raw']), raw_response().body)
        provider.finish()
        self.assertTrue(self.state()['finished'])
        with self.assertRaises(ValueError):
            provider(messages=[])

    def test_duplicate_executor_cannot_rebind_even_same_claim(self):
        self.provider()
        with self.assertRaises(ValueError):
            self.provider()

    def test_concurrent_reservations_never_exceed_shared_budget(self):
        provider = self.provider(lambda *_: raw_response(1000, 100))
        def attempt(_):
            try:
                provider(messages=[])
                return True
            except auth.AuthorizationError:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(attempt, range(4)))
        self.assertEqual(sum(outcomes), 1)
        self.assertEqual(len(self.state()['calls']), 1)
        self.assertEqual(self.state()['spent'], '0.0012')

    def test_timeouts_disconnects_bad_usage_and_status_retain_full_reserve(self):
        # One independent grant per case; never reset a consumed ledger.
        cases = [TimeoutError(), ConnectionError(), RawHTTP(503, b'error'),
                 RawHTTP(200, b'{', False), RawHTTP(200, b'{"usage":{}}'),
                 raw_response(True, 5), raw_response(1001, 5)]
        for index, outcome in enumerate(cases):
            with self.subTest(index=index):
                config = dict(CONFIG, pricing_confirmation='Independent test case '+str(index))
                _, request = prepare_grant(config)
                calls=[]
                def send(*_):
                    calls.append(1)
                    if isinstance(outcome, Exception):
                        raise outcome
                    return outcome
                provider = auth.AuthorizedProvider(request, self.claim, lambda _: None, raw_completion=send)
                with self.assertRaises(Exception):
                    provider(messages=[])
                state = auth.read_json(provider.path)
                self.assertTrue(state['halted'])
                self.assertEqual(state['reserved'], str(auth.reserve(config)))
                self.assertEqual(state['calls'][0]['status'], 'outcome_unknown')
                with self.assertRaises(ValueError):
                    provider(messages=[])
                self.assertEqual(calls, [1])

    def test_post_reservation_claim_fence_prevents_send(self):
        calls=[]
        def report(values):
            if values['stage'] == 'provider_inflight':
                raise RuntimeError('Lost claim')
        provider = self.provider(lambda *_: calls.append(1), report)
        with self.assertRaises(RuntimeError):
            provider(messages=[])
        self.assertEqual(calls, [])
        self.assertTrue(self.state()['halted'])
        self.assertGreater(auth.money(self.state()['reserved']), 0)

    def test_disk_capacity_blocks_before_call(self):
        provider = self.provider()
        with patch.object(response_store, 'capacity', return_value=1):
            with self.assertRaises(ValueError):
                provider(messages=[])
        self.assertEqual(self.state()['calls'], [])

    def test_raw_write_failure_is_unknown_never_replayed(self):
        calls=[]
        provider = self.provider(lambda *_: (calls.append(1), raw_response())[1])
        with patch.object(response_store, 'persist', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                provider(messages=[])
        with self.assertRaises(ValueError):
            provider(messages=[])
        self.assertEqual(calls, [1])
        self.assertEqual(self.state()['calls'][0]['status'], 'outcome_unknown')

    def test_http_allow_paid_cannot_supply_authority(self):
        from fastapi.testclient import TestClient
        from locagent_service.api import create_app
        from locagent_service.config import Settings
        with patch('locagent_service.api.TaskStore') as store:
            with TestClient(create_app(Settings('postgresql://localhost/unit', 'public_preview_auth'))) as client:
                response = client.post('/tasks', json=self.request.model_dump(mode='json') | {'allow_paid': True})
                self.assertEqual(response.status_code, 422)
                store.return_value.create.assert_not_called()

    def test_low_price_and_high_precision_settle_without_rounding(self):
        for rate in ('0.1', '0.000000000001'):
            config = dict(CONFIG, input_per_million=rate, output_per_million=rate)
            _, request = prepare_grant(config)
            provider = auth.AuthorizedProvider(request, self.claim, lambda _: None,
                raw_completion=lambda *_: raw_response(1, 0))
            provider(messages=[])
            provider.finish()
            state = auth.read_json(provider.path)
            self.assertEqual(auth.money(state['spent']), auth.money(rate)/1000000)
            self.assertEqual(state['reserved'], '0')
            self.assertNotIn('E', state['spent'])

    def test_mock_transport_retains_partial_bytes_and_checks_truncation(self):
        import http.client
        # Patch the connection and credential lookup: no environment secret is read.
        original = self.real_exchange
        with patch.object(auth, 'PinnedHTTPS') as connection, \
             patch.object(auth.os.environ, 'get', return_value='synthetic-not-a-secret'):
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read1.side_effect = [b'first', http.client.IncompleteRead(b'partial')]
            result = original(CONFIG, b'{}', 100)
            self.assertEqual(result.body, b'firstpartial')
            self.assertFalse(result.complete)
            response.read1.side_effect = [b'abc', b'']
            response.getheader.return_value = '8'
            result = original(CONFIG, b'{}', 100)
            self.assertEqual(result.body, b'abc')
            self.assertFalse(result.complete)

    def test_tampered_raw_response_blocks_further_spend(self):
        provider = self.provider()
        provider(messages=[])
        state = self.state()
        body = response_store.directory(self.path)/state['calls'][0]['raw']['file']
        body.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            provider(messages=[])
        self.assertEqual(len(self.state()['calls']), 1)

    def test_replay_policy_defaults_closed_for_authorized_and_prepared(self):
        self.assertTrue(replay_safe({'source_id': 'github-v1'}))
        self.assertTrue(replay_safe({'source_id': 'demo-v1'}))
        self.assertFalse(replay_safe(self.request.model_dump()))
        self.assertFalse(replay_safe({'source_id': 'prepared-'+'a'*64}))


if __name__ == '__main__':
    unittest.main()
