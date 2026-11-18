"""Separate authorization/ledger tests use temporary markers and synthetic raw bytes."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from locagent_service import followup as f
from locagent_service.sources import canonical, digest
from test_stage4_followup import plan, confirmation, raw


def bounded_plan():
    value = plan()
    value['config']['search_protocol'] = 'bounded-v1'
    value['experiment_id'] = f.BOUNDED_EXPERIMENT
    return value


class BoundedRoundTests(unittest.TestCase):
    def scope(self, root):
        p = bounded_plan()
        for name, value in [('BOUNDED_PLAN_HASH', digest(canonical(p))),
                            ('BOUNDED_AUTHORIZATION_PATH', Path(root)/'new-approval.json'),
                            ('AUTHORIZATION_PATH', Path(root)/'old-approval.json')]:
            context = patch.object(f, name, value)
            context.start()
            self.addCleanup(context.stop)
        return p

    def test_unreviewed_round_is_blocked_before_ledger_creation(self):
        p = bounded_plan()
        with tempfile.TemporaryDirectory() as tmp, patch.object(f, 'BOUNDED_PLAN_HASH', None):
            path = Path(tmp)/'budget.json'
            with self.assertRaises(ValueError):
                f.initialize_ledger(path, p, confirmation(p))
            self.assertFalse(path.exists())

    def test_new_scope_cannot_use_old_marker_and_second_directory_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.scope(tmp)
            old = Path(tmp)/'old-approval.json'
            old.write_bytes(b'previous consumed authorization evidence')
            path = Path(tmp)/'new-budget.json'
            f.initialize_ledger(path, p, confirmation(p))
            marker = json.loads((Path(tmp)/'new-approval.json').read_text())
            self.assertEqual(marker['plan_hash'], digest(canonical(p)))
            self.assertEqual(marker['ledger_path'], str(path))
            self.assertEqual(old.read_bytes(), b'previous consumed authorization evidence')
            with self.assertRaises(FileExistsError):
                f.initialize_ledger(Path(tmp)/'another-budget.json', p, confirmation(p))
            state = json.loads(path.read_text())
            with self.assertRaises(RuntimeError):
                f.validate_authorization(Path(tmp)/'copied-budget.json', state)
            self.assertEqual(state['calls'], [])

    def test_new_scope_requires_bounded_protocol_and_experiment_identity(self):
        for field, value in [('experiment_id', 'other'), ('config', plan()['config'])]:
            p = bounded_plan()
            p[field] = value
            with patch.object(f, 'BOUNDED_PLAN_HASH', digest(canonical(p))):
                with self.assertRaises(ValueError):
                    f.require_approval(p)

    def test_unknown_new_round_outcome_stops_without_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.scope(tmp)
            path = Path(tmp)/'budget.json'
            f.initialize_ledger(path, p, confirmation(p))
            calls = []
            def timeout(**kwargs):
                calls.append(1)
                raise TimeoutError('synthetic unknown')
            provider = f.SettlingBudgetProvider(path, 's0', p['config'], timeout)
            with self.assertRaises(TimeoutError):
                provider(messages=[])
            with self.assertRaises(RuntimeError):
                provider(messages=[])
            state = json.loads(path.read_text())
            self.assertEqual(len(calls), 1)
            self.assertEqual(state['reserved'], str(f.RESERVE))
            self.assertTrue(state['halted'])

    def test_new_round_hard_cap_reserves_before_synthetic_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.scope(tmp)
            path = Path(tmp)/'budget.json'
            f.initialize_ledger(path, p, confirmation(p))
            calls = []
            def response(**kwargs):
                calls.append(1)
                return raw(pt=500000, ct=1)
            # Three settled synthetic calls cost ~3 CNY, leaving insufficient room
            # for a full 2.101248 reservation. The fourth request must not be sent.
            for source in ['s0', 's1', 's2']:
                f.SettlingBudgetProvider(path, source, p['config'], response)(messages=[])
            with self.assertRaises(RuntimeError):
                f.SettlingBudgetProvider(path, 's3', p['config'], response)(messages=[])
            self.assertEqual(len(calls), 3)
            state = json.loads(path.read_text())
            self.assertTrue(state['halted'])
            self.assertEqual(state['stop_reason'], 'budget_exhausted')

    def test_scripted_finish_matches_protocol_without_changing_legacy(self):
        from locagent_service.offline import offline_engine
        from locagent_service.evaluate import scripted_provider
        with offline_engine():
            for protocol in ['legacy', 'bounded-v1']:
                provider = scripted_provider(protocol)
                provider(); provider()
                value = json.loads(provider().choices[0].message.tool_calls[0].function.arguments)
                if protocol == 'legacy':
                    self.assertIn('\nclass: Response\n', value['thought'])
                else:
                    self.assertEqual(set(value), {'files', 'entities'})
                    self.assertEqual(value['entities'], ['requests/models.py:Response.iter_content'])
