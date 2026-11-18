"""v8.1 regressions. Real provider finish replay uses a synthetic source snapshot;
no model/API call, real quality claim, coding run, or harness evaluation."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from calibration.policy import EvidenceLedger, calibrate, violations
from test_calibration import ledger, read, packet

class V81Tests(unittest.TestCase):
    def test_directory_and_function_same_name(self):
        e=EvidenceLedger(SimpleNamespace(files={'core/a.py':'def f():\n    return 1\n','b.py':'def core():\n    return 2\n'}))
        read(e,1,2,path='core/a.py');p=packet();p['files']=['core/a.py'];p['entities']=['core/a.py:f'];p['answer']=p['answer'].replace('a.py','core/a.py')
        self.assertEqual(violations(p,e),[])

    def test_command_word_and_function_same_name(self):
        e=ledger('def f():\n    return 1\ndef python():\n    pass\ndef pytest():\n    pass\n');read(e,1,2)
        p=packet();p['answer']=p['answer'].replace('assert f() == 1','python -m pytest -q')
        self.assertEqual(violations(p,e),[])

    def test_cross_module_same_qualified_entity(self):
        e=EvidenceLedger(SimpleNamespace(files={'a.py':'def f():\n    return 1\n','b.py':'def f():\n    return 2\n'}));read(e,1,2)
        self.assertEqual(violations(packet(),e),[])
        p=packet();p['entities']=['b.py:f']
        self.assertIn('R1_body_incomplete_unmarked:b.py:f',violations(p,e))

    def test_bullet_prefixes(self):
        e=ledger();read(e,1,2)
        for bullet in ['- ','* ','+ ','• ']:
            with self.subTest(bullet=bullet):
                p=packet();p['answer']=p['answer'].replace('待验证假设：',bullet+'待验证假设：')
                self.assertEqual(violations(p,e),[])

    def test_unread_label_before_or_after(self):
        e=ledger('def f():\n    x = 1\n    return x\n');read(e,1,2)
        for label in ['未读完：`a.py:f`','`a.py:f`：未读完']:
            with self.subTest(label=label):
                p=packet();p['answer']+='\n- '+label
                self.assertEqual(violations(p,e),[])

    def test_unread_label_does_not_cover_other_module_or_prefix(self):
        e=ledger();p=packet();p['answer']+='\n未读完：`b.py:f`、`a.py:foobar`'
        self.assertIn('R1_body_incomplete_unmarked:a.py:f',violations(p,e))

    def test_validator_exception_delivers_fallback(self):
        p=packet();original=copy.deepcopy(p)
        with patch('calibration.policy.violations',side_effect=RuntimeError('validator broken')) as check:
            result,audit=calibrate(p,ledger())
        self.assertEqual(check.call_count,1);self.assertEqual(audit['validator_error'],'RuntimeError')
        self.assertTrue(audit['fallback']);self.assertEqual(p,original)
        self.assertEqual(result['files'],p['files']);self.assertEqual(result['entities'],p['entities'])
        self.assertIn('最小验证：`python -m pytest -q`',result['answer'])

    def test_audit_exception_also_delivers_fallback(self):
        e=ledger();read(e,1,2)
        with patch.object(e,'ranges',side_effect=ValueError('audit broken')):
            result,audit=calibrate(packet(),e)
        self.assertTrue(audit['fallback']);self.assertEqual(audit['validator_error'],'ValueError')
        self.assertIn('候选实体：a.py:f',result['answer'])

    def test_fallback_is_fixed_and_never_revalidated(self):
        p=packet('bad answer')
        with patch('calibration.policy.violations',side_effect=[['R2_three_sections'],AssertionError('must not revalidate')]) as check:
            result,audit=calibrate(p,ledger())
        self.assertEqual(check.call_count,1);self.assertTrue(audit['fallback'])
        e=ledger();read(e,1,2)
        with patch('calibration.policy.violations',return_value=['R3_unverified_strong_claim']):
            other,_=calibrate(p,e)
        self.assertEqual(result,other)

    def test_exception_string_cannot_break_fallback(self):
        class BadError(Exception):
            def __str__(self):raise RuntimeError('broken str')
        with patch('calibration.policy.violations',side_effect=BadError()):
            result,audit=calibrate(packet(),ledger())
        self.assertEqual(audit['validator_error'],'BadError');self.assertTrue(result['answer'])

    def test_real_sympy_21379_finish_delivers_sdk_packet(self):
        from calibration.locator import run,build_packet
        from locagent_e2e.transport import ScriptedTransport
        from locagent_e2e.baseline import CurrentRetriever
        from readonly_agent.core import Snapshot
        fixture=Path(__file__).parent/'fixtures/sympy-21379-response-4.json'
        raw=json.loads(fixture.read_text());p=json.loads(raw['choices'][0]['message']['tool_calls'][0]['function']['arguments'])['message']
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'a.py').write_text('def core():\n    return 1\ndef python():\n    pass\ndef _parallel_dict_from_expr():\n    pass\n')
            snap=Snapshot(root,['a.py']);snap.e2e_source_root=root
            r=run(issue='Offline replay of real sympy-21379 finish; synthetic coverage only',output=root/'out',transport=ScriptedTransport([raw]),locator=CurrentRetriever(snap),scripted=True)
            self.assertEqual(r['status'],'completed',r)
            delivered=build_packet(r,instance_id='sympy__sympy-21379',base_commit='offline-fixture')
            audit=json.loads((root/'out/diagnostic-audit.json').read_text())
            self.assertEqual(audit['raw_packet'],p);self.assertEqual(delivered['result']['entities'],p['entities'])
            self.assertTrue(audit['fallback']);self.assertIsNone(audit['validator_error'])
            self.assertFalse(any(x.startswith('R1_body_incomplete_unmarked:a.py:') for x in audit['violations']))
            self.assertNotIn('R3_inference_not_hypothesis',audit['violations'])
            proof=dict(mode='real v8 provider answer replay with synthetic source coverage; zero API; not quality evaluation',status='delivered',requests_scripted=r['requests'],validator_error=audit['validator_error'],audit=audit,localization_packet=delivered)
            (Path(__file__).resolve().parents[1]/'delivery/sympy-21379-replay.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
