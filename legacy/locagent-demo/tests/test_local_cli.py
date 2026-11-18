"""Local user workflow: real parser/graph/BM25, synthetic model HTTP only."""
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import pickle
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from locagent_service import local, public_authorization as auth, public_repo
from locagent_service.deepseek_http import RawHTTP
from locagent_service.sources import canonical, digest, load_manifest

CONFIG = {'endpoint': 'https://provider.example/chat/completions', 'model': 'stub-model',
    'response_models': ['stub-model'], 'credential_env': 'LOCAL_TEST_KEY', 'currency': 'USD',
    'input_per_million': '1', 'output_per_million': '2', 'budget': '0.01',
    'context_tokens': 1000, 'output_tokens': 100, 'max_calls': 3,
    'request_bytes': 200000, 'timeout_seconds': 10,
    'pricing_confirmation': 'Synthetic test prices only; never a paid approval'}
CODE = '\n'.join([
    'def sign_payload(value):',
    '    """Sign a payload for transport using a local test-only suffix."""',
    '    # Source evidence must preserve this exact original line.',
    '    return value + "-signed"', '',
    'def parse_payload(value):',
    '    """Parse the payload without signing it."""',
    '    return value.strip()', '',
    'def render_page(value):',
    '    """An unrelated rendering function."""',
    '    return "<p>" + value + "</p>"', '',
])


def archive():
    raw = CODE.encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        entry = tarfile.TarInfo('repo-commit/pkg.py')
        entry.size = len(raw)
        tar.addfile(entry, io.BytesIO(raw))
    oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    return buffer.getvalue(), {'pkg.py': oid}


def response(tool, arguments):
    return RawHTTP(200, canonical({'id': 'test-' + tool, 'model': 'stub-model',
        'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
            'role': 'assistant', 'content': None, 'tool_calls': [{
                'id': 'call-' + tool, 'type': 'function', 'function': {
                    'name': tool, 'arguments': json.dumps(arguments)}}]}}],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}))


def offline_model_child(root, identity, connection):
    # Spawned integration fixture; no CLI switch can select this transport.
    steps = iter([
        response('search_code_snippets', {'search_terms': ['sign_payload']}),
        response('get_entity_contents', {'entity_names': ['pkg.py:sign_payload']}),
        response('finish', {'files': ['pkg.py'], 'entities': ['pkg.py:sign_payload']}),
    ])
    with patch.object(auth, 'exchange', side_effect=lambda *_: next(steps)):
        local.child(root, identity, connection)


class LocalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='locagent-local-test-')
        self.root = Path(self.temp.name).resolve() / 'run'
        self.network = patch.object(auth, 'exchange', side_effect=AssertionError('No live transport'))
        self.network.start()

    def tearDown(self):
        self.network.stop()
        self.temp.cleanup()

    def prepare(self, **changes):
        with patch.object(public_repo, 'resolve', return_value='a' * 40), \
             patch.object(public_repo, 'download', return_value=archive()):
            return local.prepare_source('https://github.com/example/demo', 'Find sign_payload.',
                                 CONFIG | changes, self.root, ref='v1')

    def authorize(self):
        plan = local.read_json(self.root / 'plan.json')
        return auth.authorize(plan, digest(canonical(plan)))

    def test_prepare_builds_real_graph_without_authorization(self):
        preview = self.prepare()
        self.assertFalse(preview['authorized'])
        self.assertEqual(preview['paid_calls'], 0)
        self.assertEqual(preview['retrieval'], 'bm25')
        self.assertEqual(preview['full_reservation_all_calls'], '0.0036')
        with local.environment(self.root):
            plan = local.read_json(self.root / 'plan.json')
            manifest, bundle = load_manifest(plan['source_id'])
            self.assertEqual((bundle / 'repo/pkg.py').read_text(), CODE)
            self.assertEqual(manifest['task']['problem_statement'], 'Find sign_payload.')
            self.assertFalse((self.root / 'authority' / preview['plan_sha256']).exists())
        self.assertEqual((self.root.stat().st_mode & 0o777), 0o700)
        self.assertEqual(((self.root / 'plan.json').stat().st_mode & 0o777), 0o600)

    def test_real_graph_loop_stub_model_and_source_evidence(self):
        self.prepare()
        steps = iter([
            response('search_code_snippets', {'search_terms': ['sign_payload']}),
            response('get_entity_contents', {'entity_names': ['pkg.py:sign_payload']}),
            response('finish', {'files': ['pkg.py'], 'entities': ['pkg.py:sign_payload']}),
        ])
        requests = []
        def send(config, data, capacity):
            requests.append(json.loads(data))
            return next(steps)
        with local.environment(self.root, live=True):
            identity = self.authorize()
            report = local.execute(self.root, identity, raw_completion=send)
            state = auth.read_json(self.root / 'authority' / identity / 'ledger.json')
        self.assertEqual(report['status'], 'success')
        self.assertEqual(report['found_entities'], ['pkg.py:sign_payload'])
        self.assertEqual(len(requests), 3)
        self.assertTrue(state['finished'])
        self.assertTrue(all(c['status'] == 'settled' for c in state['calls']))
        ev = json.loads((self.root / 'evidence.json').read_text())
        fn = next(i for i in ev['items'] if i['kind'] == 'function')
        self.assertEqual(fn['start_line'], 1)
        self.assertEqual(fn['end_line'], 4)
        self.assertIn('preserve this exact original line', fn['snippet'])
        self.assertEqual(fn['url'], 'https://github.com/example/demo/blob/' + 'a' * 40 + '/pkg.py#L1-L4')
        result = json.loads((self.root / 'result.json').read_text())
        self.assertTrue(result['return_records'])
        self.assertFalse(result['local_run']['quality_evaluated'])
        with local.environment(self.root, live=True), self.assertRaises(auth.AuthorizationError):
            local.execute(self.root, identity, raw_completion=send)
        self.assertEqual(len(requests), 3)

    def test_unknown_response_keeps_reservation_and_no_retry(self):
        self.prepare()
        calls = []
        def send(*_):
            calls.append(1)
            raise TimeoutError('private provider details must not be printed')
        with local.environment(self.root, live=True):
            identity = self.authorize()
            with self.assertRaises(Exception):
                local.execute(self.root, identity, raw_completion=send)
            state = auth.read_json(self.root / 'authority' / identity / 'ledger.json')
            self.assertTrue(state['halted'])
            self.assertEqual(state['reserved'], '0.0012')
            self.assertEqual(state['calls'][0]['status'], 'outcome_unknown')
            with self.assertRaises(auth.AuthorizationError):
                local.execute(self.root, identity, raw_completion=send)
        self.assertEqual(calls, [1])
        self.assertFalse((self.root / 'result.json').exists())

    def test_paid_flag_is_required_before_reading_files(self):
        with self.assertRaisesRegex(local.LocalError, 'paid_confirmation_required'):
            local.run(self.root, 'a' * 64)

    def test_changed_plan_or_missing_credential_never_authorizes(self):
        preview = self.prepare()
        with patch.object(auth, 'authorize', side_effect=AssertionError('Cannot authorize')):
            with self.assertRaisesRegex(local.LocalError, 'plan_confirmation_mismatch'):
                local.run(self.root, '0' * 64, allow_paid=True)
            with patch.dict(os.environ, {'LOCAL_TEST_KEY': ''}):
                with self.assertRaisesRegex(local.LocalError, 'credential_environment_missing'):
                    local.run(self.root, preview['plan_sha256'], allow_paid=True)
        self.assertFalse((self.root / 'run-started.json').exists())

    def test_reused_directory_is_rejected(self):
        self.prepare()
        with self.assertRaises(FileExistsError):
            self.prepare()

    def test_edited_source_is_rejected_before_authorization(self):
        preview = self.prepare()
        with local.environment(self.root):
            plan = local.read_json(self.root / 'plan.json')
            _, bundle = load_manifest(plan['source_id'])
        (bundle / 'repo/pkg.py').write_text('changed')
        with patch.object(auth, 'authorize', side_effect=AssertionError('Cannot authorize')):
            with self.assertRaises(ValueError):
                local.run(self.root, preview['plan_sha256'], allow_paid=True)

    def test_url_question_and_pricing_validation_precede_download(self):
        with patch.object(public_repo, 'resolve', side_effect=AssertionError('No download')):
            for url, q in [('http://github.com/a/b', 'x'), ('https://github.com/a/b?token=secret', 'x'),
                           ('https://github.com/a/b', ' '), ('https://github.com/a/b', 'x' * 8001)]:
                with self.subTest(url=url, q=q[:20]), self.assertRaises(ValueError):
                    local.prepare_source(url, q, CONFIG, self.root)
            with self.assertRaisesRegex(local.LocalError, 'pricing_not_confirmed'):
                local.prepare_source('https://github.com/a/b', 'x', CONFIG | {'pricing_confirmation': 'REPLACE ME'}, self.root)
        self.assertFalse(self.root.exists())

    def test_linked_run_directory_rejected(self):
        target = Path(self.temp.name) / 'target'
        target.mkdir()
        link = Path(self.temp.name) / 'link'
        link.symlink_to(target)
        with self.assertRaisesRegex(local.LocalError, 'linked_run_directory'):
            local.prepare_source('https://github.com/a/b', 'x', CONFIG, link / 'run')

    def test_environment_restored(self):
        with patch.dict(os.environ, {'LOCAGENT_ALLOW_PAID': '1', 'HTTPS_PROXY': 'example'}):
            with local.environment(self.root):
                self.assertEqual(os.environ['LOCAGENT_ALLOW_PAID'], '0')
                self.assertNotIn('HTTPS_PROXY', os.environ)
            self.assertEqual(os.environ['LOCAGENT_ALLOW_PAID'], '1')
            self.assertEqual(os.environ['HTTPS_PROXY'], 'example')

    def test_cli_error_does_not_print_provider_exception(self):
        output = io.StringIO()
        with patch.object(local, 'prepare', side_effect=ValueError('SECRET-DO-NOT-PRINT')), \
             patch.object(Path, 'read_text', return_value='{}'), patch('sys.stderr', output):
            status = local.main(['prepare', 'https://github.com/a/b', 'x', '--provider-config', 'c.json', '--run-dir', str(self.root)])
        self.assertEqual(status, 2)
        self.assertNotIn('SECRET', output.getvalue())
        self.assertIn('local_validation_or_io_failed', output.getvalue())

    def test_demo_is_explicitly_synthetic(self):
        value = local.demo()
        self.assertEqual(value['mode'], 'synthetic-demo')
        self.assertEqual(value['paid_calls'], 0)
        self.assertEqual(value['result']['found_entities'], ['demo.py:render'])


    def test_spawned_run_and_duplicate_refusal_without_network(self):
        preview = self.prepare()
        with patch.dict(os.environ, {'LOCAL_TEST_KEY': 'synthetic-test-not-a-secret'}), \
             patch.object(local, 'child', offline_model_child):
            result = local.run(self.root, preview['plan_sha256'], allow_paid=True, timeout_seconds=90)
            self.assertEqual(result['state'], 'completed')
            self.assertEqual(result['status'], 'success')
            self.assertTrue((self.root / 'run.json').is_file())
            with self.assertRaisesRegex(local.LocalError, 'already_consumed_needs_review'):
                local.run(self.root, preview['plan_sha256'], allow_paid=True)

    def test_unicode_separators_are_not_source_newlines(self):
        import networkx as nx
        bundle = Path(self.temp.name).resolve() / 'evidence-bundle'
        (bundle / 'repo').mkdir(parents=True)
        code = '# comment with Unicode separators: \u2028 \u2029 \x85 \x0c\r\ndef target():\r\n    return 1\r\n'
        (bundle / 'repo/x.py').write_bytes(code.encode())
        graph = nx.MultiDiGraph()
        graph.add_node('x.py:target', type='function', start_line=2, end_line=3)
        (bundle / 'graph.pkl').write_bytes(pickle.dumps(graph))
        result = SimpleNamespace(found_files=[], found_entities=['x.py:target'], found_modules=[])
        value = local.evidence(result, {'task': {'repo': 'a/b', 'base_commit': 'a' * 40}}, bundle)
        self.assertEqual(value['items'][0]['snippet'], 'def target():\n    return 1')
        self.assertEqual(value['items'][0]['start_line'], 2)

    def test_supervisor_success_timeout_eof_interrupt_and_start_failure(self):
        for case in ('success', 'timeout', 'eof', 'interrupt', 'start_failed', 'partial_start_interrupt'):
            with self.subTest(case=case):
                context, process, receiver, sender = [MagicMock() for _ in range(4)]
                context.Pipe.return_value = (receiver, sender)
                context.Process.return_value = process
                process.pid = 42
                process.is_alive.return_value = False
                receiver.poll.return_value = True
                receiver.recv.return_value = {'state': 'completed'}
                expected = None
                if case == 'timeout':
                    receiver.poll.return_value = False
                    process.is_alive.return_value = True
                    expected = 'deadline_exceeded'
                elif case == 'eof':
                    receiver.recv.side_effect = EOFError()
                    expected = 'child_exited'
                elif case == 'interrupt':
                    receiver.poll.side_effect = KeyboardInterrupt()
                    process.is_alive.return_value = True
                    expected = 'interrupted'
                elif case == 'start_failed':
                    process.start.side_effect = OSError('private startup detail')
                    process.pid = None
                    expected = 'child_start_or_transport_failed'
                elif case == 'partial_start_interrupt':
                    process.start.side_effect = KeyboardInterrupt()
                    process.is_alive.return_value = True
                    expected = 'interrupted'
                with patch.object(local.multiprocessing, 'get_context', return_value=context):
                    value = local.supervise(local.child, ('unused', 'identity'), 1)
                self.assertEqual(value.get('code'), expected)
                sender.close.assert_called()
                receiver.close.assert_called_once()
                if case == 'start_failed':
                    process.join.assert_not_called()
                else:
                    process.join.assert_called()
                if case in ('timeout', 'interrupt', 'partial_start_interrupt'):
                    process.terminate.assert_called_once()
                    process.kill.assert_called_once()

    def test_prepare_uses_supervised_child_with_explicit_deadline(self):
        with patch.object(local, 'supervise', return_value={'state': 'prepared'}) as supervisor:
            value = local.prepare('https://github.com/a/b', 'question', CONFIG, str(self.root),
                                  ref='v1', timeout_seconds=12)
        self.assertEqual(value['state'], 'prepared')
        self.assertIs(supervisor.call_args.args[0], local.prepare_child)
        self.assertEqual(supervisor.call_args.args[2], 12)


if __name__ == '__main__':
    unittest.main()
