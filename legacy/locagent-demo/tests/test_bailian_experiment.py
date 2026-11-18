import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from locagent_service import bailian_config as config
from locagent_service import bailian_contract as contract
from locagent_service.bailian_experiment import Ledger, freeze, metrics


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / '.env.bailian.local'
        self.path.write_text('DASHSCOPE_API_KEY=synthetic-test-only\nDASHSCOPE_WORKSPACE_ID=example\nDASHSCOPE_API_HOST=https://example.cn-beijing.maas.aliyuncs.com\n')
        self.path.chmod(0o600)

    def test_private_loader_does_not_export(self):
        with patch.dict(os.environ, {}, clear=True):
            values = config.load_env_file(self.path)
            self.assertTrue(all(config.presence(values).values()))
            self.assertNotIn('DASHSCOPE_API_KEY', os.environ)
            self.assertNotIn('synthetic-test-only', json.dumps(config.presence(values)))

    def test_reject_world_readable_and_symlink(self):
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            config.load_env_file(self.path)
        self.path.chmod(0o600)
        link = self.path.with_name('link')
        link.symlink_to(self.path)
        with self.assertRaises(OSError):
            config.load_env_file(link)

    def test_duplicate_unknown_and_malformed(self):
        for text in ['DASHSCOPE_API_KEY=a\nDASHSCOPE_API_KEY=b', 'OTHER=x',
                     'DASHSCOPE_API_KEY="unterminated', 'DASHSCOPE_API_KEY="a\nb"']:
            self.path.write_text(text)
            with self.assertRaises(ValueError):
                config.load_env_file(self.path)

    def test_no_interpolation(self):
        self.path.write_text('DASHSCOPE_API_KEY=${NOT_A_SECRET}\n')
        self.assertEqual(config.load_env_file(self.path)['DASHSCOPE_API_KEY'], '${NOT_A_SECRET}')

    def test_blank_example_and_wrong_host(self):
        self.assertFalse(any(config.presence({}).values()))
        values = config.load_env_file(self.path)
        values['DASHSCOPE_API_HOST'] = 'https://wrong.example'
        self.assertFalse(config.presence(values)['beijing_host_matches_workspace'])


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'ledger.sqlite'
        self.docs = [{'id': 'd1', 'entity': 'module.target', 'path': 'source.py', 'text': 'def target(): pass'}]
        self.questions = [{'id': 'q1', 'text': 'Where is the operation implemented?', 'relevant_entities': ['module.target']}]
        self.manifest = self.freeze()
        self.ledger = Ledger(self.path, self.manifest)
        self.key = next(iter(self.ledger.inputs))

    def freeze(self):
        return freeze(self.docs, self.questions, workspace='example', api_host='https://example.cn-beijing.maas.aliyuncs.com',
                      chunker={'name': 'python-ast-lines-v2', 'max_chars': 2000}, engine_hash='a' * 64)

    def fake(self, body):
        return 200, json.dumps({'output': {'embeddings': [{'text_index': 0, 'embedding': [1.] + [0.] * 1023}]},
                                'usage': {'total_tokens': 10, 'prompt_tokens': 10}}).encode()

    def test_settlement_hashes_usage_and_cache_restart(self):
        result = self.ledger.execute_fake(self.key, self.fake)
        reloaded = Ledger(self.path, self.manifest)
        self.assertEqual(result, reloaded.execute_fake(self.key, lambda _: self.fail('No repeat request')))
        with reloaded.connection() as db:
            row = db.execute('SELECT request_hash,response_hash,tokens,state FROM calls').fetchone()
        self.assertEqual(row, (hashlib.sha256(contract.canonical(self.ledger.inputs[self.key])).hexdigest(),
                               hashlib.sha256(self.fake(b'')[1]).hexdigest(), 10, 'settled'))
        report = reloaded.accounting()
        self.assertEqual(report['retained_full_reservation_cny'], '0.016384')
        self.assertEqual(report['settled_usage_cny'], '0.00000125')
        self.assertEqual(report['unresolved_count'], 0)

    def test_plan_tampering_blocks_request(self):
        with self.ledger.connection() as db:
            db.execute('UPDATE plan SET hash=?', ('b' * 64,))
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            self.ledger.execute_fake(self.key, lambda _: self.fail('No request'))

    def test_metrics_denominator_keeps_failed_questions(self):
        questions = [{'id': 'a', 'relevant_entities': ['one', 'two']},
                     {'id': 'b', 'relevant_entities': ['three']}]
        result = metrics(questions, {'a': ['one', 'one', 'other']}, 2)
        self.assertEqual(result, {'question_count': 2, 'hit_at_k': 0.5, 'macro_recall_at_k': 0.25})

    def test_unknown_no_retry_after_restart(self):
        calls = []
        def fail(body):
            calls.append(1)
            raise TimeoutError('synthetic sensitive message')
        with self.assertRaisesRegex(ValueError, '^Embedding outcome unknown; automatic replay prohibited$'):
            self.ledger.execute_fake(self.key, fail)
        with self.assertRaisesRegex(ValueError, 'cannot be replayed'):
            Ledger(self.path, self.manifest).execute_fake(self.key, fail)
        self.assertEqual(len(calls), 1)

    def test_crash_reservation_not_replayed(self):
        def interrupt(body):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.ledger.execute_fake(self.key, interrupt)
        with self.assertRaisesRegex(ValueError, 'cannot be replayed'):
            Ledger(self.path, self.manifest).execute_fake(self.key, self.fake)

    def test_concurrent_one_transport(self):
        entered, release = threading.Event(), threading.Event()
        def waiting(body):
            entered.set()
            if not release.wait(5):
                raise TimeoutError()
            return self.fake(body)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            task = pool.submit(self.ledger.execute_fake, self.key, waiting)
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaisesRegex(ValueError, 'cannot be replayed'):
                    Ledger(self.path, self.manifest).execute_fake(self.key, self.fake)
            finally:
                release.set()
            task.result(5)

    def test_wrong_status_or_body_keeps_reservation(self):
        with self.assertRaises(ValueError):
            self.ledger.execute_fake(self.key, lambda _: (429, b'{"message":"do not log"}'))
        with self.ledger.connection() as db:
            self.assertEqual(db.execute('SELECT state FROM calls').fetchone()[0], 'unknown')

    def test_manifest_cannot_rebind_ledger(self):
        self.questions[0]['text'] = 'Which code handles this operation?'
        with self.assertRaisesRegex(ValueError, 'another manifest'):
            Ledger(self.path, self.freeze())

    def test_changed_contract_rejected(self):
        data = json.loads(self.manifest)
        data['model'] = 'other-model'
        with self.assertRaisesRegex(ValueError, 'frozen contract'):
            Ledger(self.path, contract.canonical(data))

    def test_unknown_input_rejected_before_transport(self):
        with self.assertRaisesRegex(ValueError, 'not in frozen manifest'):
            self.ledger.execute_fake('foreign', lambda _: self.fail('No network'))

    def test_freeze_detaches_inputs_and_rejects_leaked_labels(self):
        before = self.manifest
        self.questions[0]['text'] = 'Where is target implemented?'
        self.assertEqual(before, self.manifest)
        with self.assertRaisesRegex(ValueError, 'symbol name'):
            self.freeze()

    def test_freeze_rejects_foreign_labels_and_budget(self):
        self.questions[0]['relevant_entities'] = ['foreign']
        with self.assertRaisesRegex(ValueError, 'relevance labels'):
            self.freeze()
        self.questions[0]['relevant_entities'] = ['module.target']
        self.docs = [dict(self.docs[0], id=str(i)) for i in range(61)]
        with self.assertRaisesRegex(ValueError, 'exceeds CNY 1'):
            self.freeze()


if __name__ == '__main__':
    unittest.main()
