"""Offline budget protocol tests: no real transport, credentials or old ledger access."""
from copy import deepcopy
from decimal import Decimal
import json
import multiprocessing
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from locagent_service import bailian_expanded_runner as runner


class Crash(BaseException):
    pass


def plan(sizes=(2, 1)):
    result = []
    for i, count in enumerate(sizes):
        body = runner.request([f'public source {i}-{j}' for j in range(count)], 'document')
        result.append({'body': body, 'body_sha256': runner.sha(runner.canonical(body)),
                       'ids': [f'{i}-{j}' for j in range(count)], 'role': 'document'})
    return result


def response(n, tokens=10):
    return runner.canonical({'usage': {'prompt_tokens': tokens, 'total_tokens': tokens},
                             'output': {'embeddings': [
                                 {'text_index': i, 'embedding': [1] + [0] * 1023} for i in range(n)]}})


class Fake:
    def __init__(self, tokens=10, mutate=None, status=200):
        self.calls = 0
        self.tokens, self.mutate, self.status = tokens, mutate, status

    def __call__(self, endpoint, raw):
        self.calls += 1
        assert endpoint == runner.ENDPOINT
        data = json.loads(response(len(json.loads(raw)['input']['texts']), self.tokens))
        if self.mutate:
            self.mutate(data)
        return self.status, runner.canonical(data)


def subprocess_crash(directory, phase):
    p = plan((1,))
    def transport(endpoint, raw):
        with open(str(directory) + '-calls', 'ab', buffering=0) as stream:
            stream.write(b'call\n')
            os.fsync(stream.fileno())
        return 200, response(1)
    def checkpoint(current):
        if current == phase:
            os._exit(71)
    runner._execute_journal(p, directory, runner.approval(p, '2'), transport, checkpoint=checkpoint)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name) / 'run'
        self.p = plan()
        self.binding = runner.approval(self.p, '2')
        self.net = patch.object(socket.socket, 'connect', side_effect=AssertionError('network prohibited'))
        self.net.start()

    def tearDown(self):
        self.net.stop()
        self.tmp.cleanup()

    def execute(self, fake=None, **kwargs):
        return runner._execute_journal(self.p, self.directory, self.binding, fake or Fake(), **kwargs)

    def journal(self):
        return runner.Journal(self.directory, self.p, self.binding)

    def test_success_releases_difference_and_restart_is_idempotent(self):
        fake = Fake()
        result = self.execute(fake)
        self.assertEqual(fake.calls, 2)
        self.assertEqual(Decimal(result['spent_cny']), runner.cost(20))
        self.assertEqual(Decimal(result['unknown_cny']), 0)
        self.assertEqual(Decimal(result['inflight_cny']), 0)
        self.execute(fake)
        self.assertEqual(fake.calls, 2)
        self.assertEqual(len(self.journal().events), 8)

    def test_release_allows_next_batch_that_full_reservation_would_block(self):
        self.binding = runner.approval(self.p, '0.03277')
        result = self.execute()
        self.assertEqual(result['requests_settled'], 2)

    def test_cap_refusal_makes_zero_calls(self):
        self.binding = runner.approval(self.p, '0.032767999')
        fake = Fake()
        with self.assertRaisesRegex(runner.Halt, 'cap_exceeded'):
            self.execute(fake)
        self.assertEqual(fake.calls, 0)
        self.assertEqual(self.journal().rows, {})

    def test_cap_counts_spent_before_next_reservation(self):
        self.binding = runner.approval(self.p, '0.04')
        fake = Fake(tokens=2 * runner.TOKEN_LIMIT)
        with self.assertRaisesRegex(runner.Halt, 'cap_exceeded'):
            self.execute(fake)
        self.assertEqual(fake.calls, 1)
        self.assertEqual(self.journal().balance()['spent'], Decimal('.032768'))

    def test_transport_error_preserves_hold_and_stops_restart(self):
        calls = []
        def transport(*args):
            calls.append(1)
            raise TimeoutError('secret should never be emitted')
        for _ in range(2):
            with self.assertRaises(runner.Halt) as exc:
                self.execute(transport)
            self.assertNotIn('secret', str(exc.exception))
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.journal().balance()['unknown'], Decimal('.032768'))

    def test_usage_variants_are_not_zero_or_refunded(self):
        mutations = [lambda d: d.pop('usage'),
                     lambda d: d['usage'].pop('prompt_tokens'),
                     *[lambda d, v=v: d['usage'].update(total_tokens=v, prompt_tokens=v)
                       for v in (0, -1, True, '10', 10.0, 262145)],
                     lambda d: d['usage'].update(prompt_tokens=11)]
        for i, mutation in enumerate(mutations):
            with self.subTest(i=i):
                self.directory = Path(self.tmp.name) / f'bad-{i}'
                fake = Fake(mutate=mutation)
                with self.assertRaisesRegex(runner.Halt, 'invalid_response_held'):
                    self.execute(fake)
                with self.assertRaisesRegex(runner.Halt, 'unknown_held_stop'):
                    self.execute(fake)
                self.assertEqual(fake.calls, 1)
                self.assertEqual(self.journal().balance()['unknown'], Decimal('.032768'))

    def test_nan_infinity_duplicate_json_keys_http_error_fail_closed(self):
        bodies = [response(2).replace(b'"total_tokens":10', b'"total_tokens":NaN'),
                  response(2).replace(b'"total_tokens":10', b'"total_tokens":Infinity'),
                  response(2).replace(b'"total_tokens":10', b'"total_tokens":10,"total_tokens":10')]
        for i, body in enumerate(bodies):
            self.directory = Path(self.tmp.name) / f'json-{i}'
            with self.assertRaisesRegex(runner.Halt, 'invalid_response_held'):
                self.execute(lambda *_: (200, body))
        self.directory = Path(self.tmp.name) / 'http-error'
        fake = Fake(status=429)
        with self.assertRaisesRegex(runner.Halt, 'invalid_response_held'):
            self.execute(fake)
        self.assertEqual(fake.calls, 1)

    def test_raw_size_and_status_types_held(self):
        for i, pair in enumerate([(200, b'x' * (runner.MAX_BODY + 1)), (True, response(2)), (200, 'text')]):
            self.directory = Path(self.tmp.name) / f'limit-{i}'
            with self.assertRaisesRegex(runner.Halt, 'response_limit_or_type_held'):
                self.execute(lambda *_: pair)
            self.assertEqual(self.journal().balance()['unknown'], Decimal('.032768'))

    def test_raw_durable_before_settlement(self):
        def checkpoint(phase):
            if phase == 'before_settle':
                journal = self.journal()
                row = journal.rows[0]
                self.assertEqual(row['state'], 'raw')
                self.assertEqual(row['raw_hash'], runner.sha(runner.secure_read(self.directory / 'body-000000.bin')))
                self.assertEqual(journal.balance()['inflight'], Decimal('.032768'))
                raise Crash()
        fake = Fake()
        with self.assertRaises(Crash):
            self.execute(fake, checkpoint=checkpoint)
        self.execute(fake)
        self.assertEqual(fake.calls, 2)  # request 0 settled from raw; only request 1 sent

    def test_actual_process_crash_windows_never_resend(self):
        phases = ('before_reserve', 'after_reserve', 'before_send', 'after_send',
                  'after_raw_file', 'before_settle', 'after_settle')
        for phase in phases:
            with self.subTest(phase=phase):
                directory = Path(self.tmp.name) / phase
                process = multiprocessing.get_context('fork').Process(target=subprocess_crash, args=(directory, phase))
                process.start()
                process.join(10)
                self.assertEqual(process.exitcode, 71)
                p = plan((1,))
                fake = Fake()
                if phase in ('before_reserve', 'before_settle', 'after_settle'):
                    runner._execute_journal(p, directory, runner.approval(p, '2'), fake)
                    self.assertEqual(fake.calls, int(phase == 'before_reserve'))
                else:
                    with self.assertRaisesRegex(runner.Halt, 'unknown_held_stop'):
                        runner._execute_journal(p, directory, runner.approval(p, '2'), fake)
                    self.assertEqual(fake.calls, 0)
                call_file = Path(str(directory) + '-calls')
                original_calls = len(call_file.read_text().splitlines()) if call_file.exists() else 0
                self.assertLessEqual(original_calls + fake.calls, 1)

    def test_lock_blocks_second_executor(self):
        fake = Fake()
        with runner.locked(self.directory):
            with self.assertRaisesRegex(runner.Halt, 'concurrent_run'):
                self.execute(fake)
        self.assertEqual(fake.calls, 0)

    def test_cap_fee_manifest_engine_tampering(self):
        for key, value in [('rate_cny_per_million', '0'), ('manifest_sha256', 'f' * 64),
                           ('tokens_per_input', 1), ('max_batch', 20), ('engine_hashes', {})]:
            with self.subTest(key=key):
                bad = deepcopy(self.binding)
                bad[key] = value
                fake = Fake()
                with self.assertRaisesRegex(runner.Halt, 'approval_binding_changed'):
                    runner._execute_journal(self.p, self.directory, bad, fake)
                self.assertEqual(fake.calls, 0)
        self.execute()
        fake = Fake()
        with self.assertRaisesRegex(runner.Halt, 'run_binding_changed'):
            runner._execute_journal(self.p, self.directory, runner.approval(self.p, '3'), fake)
        self.assertEqual(fake.calls, 0)

    def test_disk_cap_tamper_stops(self):
        self.execute()
        path = self.directory / 'run.json'
        data = json.loads(path.read_bytes())
        data['cap_cny'] = '200'
        path.write_bytes(runner.canonical(data))
        with self.assertRaisesRegex(runner.Halt, 'run_binding_changed'):
            self.execute()

    def test_request_plan_mutation_stops_before_transport(self):
        self.p[0]['body']['input']['texts'][0] = 'changed'
        fake = Fake()
        with self.assertRaisesRegex(runner.Halt, 'request_binding_mismatch'):
            self.execute(fake)
        self.assertEqual(fake.calls, 0)

    def test_raw_tamper_stops(self):
        self.execute()
        (self.directory / 'body-000000.bin').write_bytes(response(2, 11))
        with self.assertRaisesRegex(runner.Halt, 'raw_binding_changed'):
            self.execute()

    def test_journal_partial_write_stops(self):
        self.execute()
        (self.directory / 'event-000008.json').write_bytes(b'{')
        (self.directory / 'event-000008.json').chmod(0o600)
        with self.assertRaisesRegex(runner.Halt, 'invalid_json'):
            self.execute()

    def test_persistence_failure_never_sends(self):
        fake = Fake()
        original = runner.persist
        def fail_reservation(path, raw):
            if path.name == 'event-000000.json':
                raise OSError('simulated disk full')
            return original(path, raw)
        with patch.object(runner, 'persist', side_effect=fail_reservation):
            with self.assertRaises(OSError):
                self.execute(fake)
        self.assertEqual(fake.calls, 0)

    def test_symlink_and_permissions_fail(self):
        target = Path(self.tmp.name) / 'target'
        target.mkdir(mode=0o700)
        self.directory.symlink_to(target)
        with self.assertRaisesRegex(runner.Halt, 'symlink_run_path'):
            self.execute()
        self.directory.unlink()
        self.execute()
        (self.directory / 'body-000000.bin').chmod(0o644)
        with self.assertRaisesRegex(runner.Halt, 'unsafe_artifact'):
            self.execute()

    def test_live_mode_and_bad_caps_rejected(self):
        with self.assertRaisesRegex(runner.Halt, 'live_execution_not_enabled'):
            runner.approval(self.p, '2', purpose='live')
        for cap in ('NaN', 'Infinity', '-1', '0', 2, True, '0.00000000001'):
            with self.subTest(cap=cap), self.assertRaises(runner.Halt):
                runner.approval(self.p, cap)

    def test_manifest_tampering(self):
        target = Path(self.tmp.name) / 'manifest.json'
        target.write_bytes(b'{}')
        with self.assertRaisesRegex(runner.Halt, 'manifest_hash_mismatch'):
            runner.load_plan(target, Path(self.tmp.name))

    def test_storage_failure_windows_never_resend(self):
        for name in ('event-000001.json', 'body-000000.bin', 'event-000002.json', 'event-000003.json'):
            with self.subTest(name=name):
                self.directory = Path(self.tmp.name) / name.replace('.', '-')
                fake = Fake()
                original = runner.persist
                def failure(path, raw):
                    if path.name == name:
                        raise OSError('simulated fsync/write failure')
                    return original(path, raw)
                with patch.object(runner, 'persist', side_effect=failure):
                    with self.assertRaises(OSError):
                        self.execute(fake)
                calls = fake.calls
                if name == 'event-000003.json':
                    self.execute(fake)  # raw binding durable: settle, send only second request
                    self.assertEqual(fake.calls, calls + 1)
                else:
                    with self.assertRaisesRegex(runner.Halt, 'unknown_held_stop'):
                        self.execute(fake)
                    self.assertEqual(fake.calls, calls)

    def test_settlement_and_chain_tamper_stops(self):
        self.execute()
        path = self.directory / 'event-000003.json'
        record = json.loads(path.read_bytes())
        record['data']['cost_cny'] = '0'
        path.write_bytes(runner.canonical(record))
        fake = Fake()
        with self.assertRaisesRegex(runner.Halt, 'settlement_changed'):
            self.execute(fake)
        self.assertEqual(fake.calls, 0)

    def test_invalid_vectors_remain_held(self):
        fake = Fake(mutate=lambda d: d['output']['embeddings'][0].update(embedding=[0] * 1024))
        with self.assertRaisesRegex(runner.Halt, 'invalid_response_held'):
            self.execute(fake)
        self.assertEqual(self.journal().balance()['unknown'], Decimal('.032768'))

    def test_batch_over_limit_rejected_before_transport(self):
        p = plan((17,))
        fake = Fake()
        with self.assertRaisesRegex(runner.Halt, 'invalid_batch'):
            runner._execute_journal(p, self.directory, runner.approval(p, '2'), fake)
        self.assertEqual(fake.calls, 0)

    def test_caller_mutation_cannot_change_frozen_dispatch(self):
        expected = [runner.canonical(item['body']) for item in self.p]
        sent = []
        def transport(endpoint, raw):
            sent.append(raw)
            self.p[-1]['body']['input']['texts'][0] = 'mutation from caller'
            self.binding['cap_cny'] = '100'
            return 200, response(len(json.loads(raw)['input']['texts']))
        result = self.execute(transport)
        self.assertEqual(sent, expected)
        self.assertEqual(result['cap_cny'], '2')


if __name__ == '__main__':
    unittest.main()
