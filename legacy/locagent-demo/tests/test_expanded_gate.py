"""Frozen-entry and wire-adapter negative tests. All sockets prohibited."""
import json
from pathlib import Path
import socket
import shutil
import tempfile
import unittest
from unittest.mock import patch

from locagent_service import bailian_expanded_runner as r
from locagent_service.bailian_expanded_transport import PinnedHTTPS, HOST, PATH


class Crash(BaseException):
    pass


class FrozenGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.domain = Path(self.tmp.name)
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('no network'))
        self.network.start()

    def tearDown(self):
        self.network.stop()
        self.tmp.cleanup()

    def test_public_gate_denies_even_correct_claims_without_creating_run(self):
        before = r.RUN_DOMAIN.exists()
        with self.assertRaisesRegex(r.Halt, 'real_execution_not_authorized'):
            r.execute()
        self.assertEqual(r.RUN_DOMAIN.exists(), before)

    def test_public_gate_has_no_plan_binding_transport_domain_injection(self):
        for kw in ({'plan': []}, {'binding': {}}, {'transport': lambda *_: None}, {'domain': self.domain}):
            with self.subTest(kw=list(kw)), self.assertRaises(TypeError):
                r.execute(**kw)

    def test_approved_public_gate_pins_identity_cap_directory_transport(self):
        from locagent_service import bailian_expanded_transport as t
        domain=self.domain/'authority'
        marker=object()
        with patch.object(r,'RUN_DOMAIN',domain), patch.object(t,'PinnedHTTPS',return_value=marker) as transport, patch.object(r,'_execute_journal',return_value={'mock':True}) as core:
            self.assertEqual(r.execute(approval_id=r.APPROVAL_ID),{'mock':True})
            transport.assert_called_once_with(approval_id=r.APPROVAL_ID)
            args=core.call_args.args
            self.assertEqual(len(args[0]),618)
            self.assertEqual(args[1],domain/r.RUN_ID)
            self.assertEqual(args[2]['purpose'],'approved-live')
            self.assertEqual(args[2]['cap_cny'],'2')
            self.assertEqual(args[2]['approval_id'],r.APPROVAL_ID)
            self.assertIs(args[3],marker)

    def test_wrong_approval_never_reads_credentials(self):
        from locagent_service import bailian_expanded_transport as t
        with patch.object(t,'PinnedHTTPS') as transport:
            with self.assertRaisesRegex(r.Halt,'real_execution_not_authorized'):
                r.execute(approval_id='not-approved')
            transport.assert_not_called()

    def test_new_id_cap_other_directory_and_alias_rejected_zero_dispatch(self):
        destination = self.domain / r.RUN_ID
        claims = [{'run_id': r.RUN_ID.replace('r01', 'r02')}, {'cap': '3'},
                  {'directory': self.domain / 'other'},
                  {'directory': str(self.domain) + '/./' + r.RUN_ID},
                  {'directory': str(self.domain) + '/x/../' + r.RUN_ID},
                  {'directory': r.RUN_ID}, {'manifest': '/tmp/copied-manifest.json'}]
        calls = []
        for claim in claims:
            with self.subTest(claim=claim), self.assertRaises(r.Halt):
                r._offline_frozen_acceptance(self.domain, lambda *_: calls.append(1), **claim)
        self.assertEqual(calls, [])
        self.assertFalse(destination.exists())

    def test_public_other_output_directory_rejected(self):
        with self.assertRaisesRegex(r.Halt, 'noncanonical_run_directory'):
            r.execute(directory=self.domain / r.RUN_ID)

    def test_domain_symlink_alias_rejected(self):
        alias = self.domain / 'alias'
        alias.symlink_to(self.domain, target_is_directory=True)
        with self.assertRaisesRegex(r.Halt, 'noncanonical_domain'):
            r._offline_frozen_acceptance(alias, lambda *_: self.fail('sent'))

    def test_manifest_corruption_rejected_before_dispatch(self):
        original = Path.read_bytes
        def bad(path):
            return b'{}' if path == r.FROZEN else original(path)
        with patch.object(Path, 'read_bytes', bad):
            with self.assertRaisesRegex(r.Halt, 'manifest_hash_mismatch'):
                r._offline_frozen_acceptance(self.domain, lambda *_: self.fail('sent'))

    def test_same_run_lock_covers_entrypoint(self):
        with r.locked(self.domain / r.RUN_ID):
            with self.assertRaisesRegex(r.Halt, 'concurrent_run'):
                r._offline_frozen_acceptance(self.domain, lambda *_: self.fail('sent'))

    def test_gate_unknown_restart_no_send(self):
        def crash(phase):
            if phase == 'before_send':
                raise Crash()
        with self.assertRaises(Crash):
            r._offline_frozen_acceptance(self.domain, lambda *_: self.fail('sent'), checkpoint=crash)
        with self.assertRaisesRegex(r.Halt, 'unknown_held_stop'):
            r._offline_frozen_acceptance(self.domain, lambda *_: self.fail('resent'))
        metadata = json.loads((self.domain / r.RUN_ID / 'run.json').read_bytes())
        self.assertEqual(metadata['run_id'], r.RUN_ID)
        self.assertEqual(metadata['ledger_directory'], str(self.domain / r.RUN_ID))
        self.assertEqual(metadata['cap_cny'], '2')
        self.assertEqual(metadata['purpose'], 'offline-test')

    def test_copied_same_run_ledger_cannot_change_budget_domain(self):
        def crash(phase):
            if phase == 'after_reserve':
                raise Crash()
        with self.assertRaises(Crash):
            r._offline_frozen_acceptance(self.domain, lambda *_: self.fail('sent'), checkpoint=crash)
        other = self.domain / 'different-domain'
        other.mkdir(mode=0o700)
        shutil.copytree(self.domain / r.RUN_ID, other / r.RUN_ID)
        with self.assertRaisesRegex(r.Halt, 'run_binding_changed'):
            r._offline_frozen_acceptance(other, lambda *_: self.fail('resent'))


class WireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = PinnedHTTPS()
        cls.body = r.canonical(r.load_plan(r.FROZEN, r.ROOT)[0]['body'])

    def setUp(self):
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('no network'))
        self.network.start()
        self.requests = []
        self.connections = []

    def tearDown(self):
        self.network.stop()

    def factory(self, *, status=200, body=b'raw bytes', encoding='identity', error=None):
        outer = self
        class Response:
            def __init__(self):
                self.status = status
            def getheader(self, key, default=None):
                return encoding if key == 'Content-Encoding' else default
            def read(self, limit):
                outer.assertEqual(limit, r.MAX_BODY + 1)
                return body[:limit]
        class Connection:
            def __init__(self, host, **kw):
                outer.connections.append(self)
                outer.assertEqual(host, HOST)
                outer.assertEqual(kw['port'], 443)
                outer.assertTrue(kw['context'].check_hostname)
                outer.assertGreater(kw['context'].verify_mode, 0)
                self.closed = False
            def request(self, method, path, *, body, headers):
                outer.requests.append((method, path, body))
                outer.assertEqual(headers['Authorization'], 'Bearer dummy-offline-token')
                if error:
                    raise error
            def getresponse(self):
                return Response()
            def close(self):
                self.closed = True
        return Connection

    def exchange(self, factory, endpoint=r.ENDPOINT, body=None, token='dummy-offline-token'):
        return self.adapter._exchange_for_review(endpoint, body or self.body, token, connection_factory=factory)

    def test_public_transport_always_disabled(self):
        with self.assertRaisesRegex(r.Halt, 'real_transport_not_authorized'):
            self.adapter(r.ENDPOINT, self.body)

    def test_approved_wire_uses_only_existing_config_and_fixed_https(self):
        from locagent_service import bailian_config as config
        from locagent_service import bailian_expanded_transport as t
        values={'DASHSCOPE_API_KEY':'dummy-offline-token','DASHSCOPE_WORKSPACE_ID':'ws-8t0i3jte6m9op4ad','DASHSCOPE_API_HOST':'https://'+HOST}
        with patch.object(config,'load_env_file',return_value=values) as loader, patch.object(t.http.client,'HTTPSConnection',self.factory()):
            adapter=PinnedHTTPS(approval_id=r.APPROVAL_ID)
            self.assertEqual(adapter(r.ENDPOINT,self.body),(200,b'raw bytes'))
            loader.assert_called_once_with(r.ROOT/'.env.bailian.local')
        self.assertEqual(len(self.requests),1)

    def test_wrong_existing_host_configuration_rejected_before_connection(self):
        from locagent_service import bailian_config as config
        with patch.object(config,'load_env_file',return_value={'DASHSCOPE_API_KEY':'dummy-offline-token'}):
            with self.assertRaisesRegex(r.Halt,'existing_private_credentials_unavailable_or_mismatched'):
                PinnedHTTPS(approval_id=r.APPROVAL_ID)

    def test_exact_body_tls_host_path_and_raw_preserved(self):
        result = self.exchange(self.factory())
        self.assertEqual(result, (200, b'raw bytes'))
        self.assertEqual(self.requests, [('POST', PATH, self.body)])
        self.assertTrue(self.connections[0].closed)

    def test_redirect_http_error_never_follow_or_retry(self):
        for status in (301, 302, 307, 308, 401, 429, 500):
            count = len(self.requests)
            result = self.exchange(self.factory(status=status))
            self.assertEqual(result[0], status)
            self.assertEqual(len(self.requests), count + 1)

    def test_error_redacted_single_attempt(self):
        with self.assertRaisesRegex(r.Halt, '^transport_exchange_failed$') as caught:
            self.exchange(self.factory(error=TimeoutError('dummy-offline-token')))
        self.assertNotIn('dummy-offline-token', str(caught.exception))
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(self.connections[0].closed)

    def test_mutated_model_instruct_endpoint_blocked_before_connection(self):
        changed = json.loads(self.body)
        changed['model'] = 'other'
        for endpoint, body in [('http://127.0.0.1', self.body),
                               (r.ENDPOINT + '?x=1', self.body),
                               (r.ENDPOINT, r.canonical(changed))]:
            with self.assertRaisesRegex(r.Halt, 'transport_request_not_frozen'):
                self.exchange(self.factory(), endpoint, body)
        self.assertEqual(self.connections, [])
        for field, value in (('dimension', 768), ('instruct', 'different instruction')):
            changed = json.loads(self.body)
            changed['parameters'][field] = value
            with self.assertRaisesRegex(r.Halt, 'transport_request_not_frozen'):
                self.exchange(self.factory(), body=r.canonical(changed))
        self.assertEqual(self.connections, [])

    def test_body_limit_encoding_and_header_injection(self):
        with self.assertRaisesRegex(r.Halt, 'transport_exchange_failed'):
            self.exchange(self.factory(body=b'x' * (r.MAX_BODY + 1)))
        with self.assertRaisesRegex(r.Halt, 'transport_exchange_failed'):
            self.exchange(self.factory(encoding='gzip'))
        count = len(self.connections)
        with self.assertRaisesRegex(r.Halt, 'invalid_credential_format'):
            self.exchange(self.factory(), token='fake\r\nInjected: header')
        self.assertEqual(len(self.connections), count)


if __name__ == '__main__':
    unittest.main()
