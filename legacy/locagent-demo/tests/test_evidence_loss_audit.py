"""Evidence loss can be audited into a durable halt, never into continuation."""
from copy import deepcopy
from decimal import Decimal
import json,unittest
from pathlib import Path
from unittest.mock import patch
from locagent_service import phased as p
from locagent_service.sources import canonical
import test_settled_arm_isolation as fixtures

class EvidenceLossAuditTests(unittest.TestCase):
    setUp=fixtures.SettledArmIsolationTests.setUp
    approve=fixtures.SettledArmIsolationTests.approve
    initialize=fixtures.SettledArmIsolationTests.initialize
    transport=fixtures.SettledArmIsolationTests.transport
    success=fixtures.SettledArmIsolationTests.success
    publish_failure=fixtures.SettledArmIsolationTests.publish_failure
    fail_with_reaped_child=fixtures.SettledArmIsolationTests.fail_with_reaped_child
    executor=fixtures.SettledArmIsolationTests.executor
    answers=fixtures.SettledArmIsolationTests.answers
    report=fixtures.SettledArmIsolationTests.report

    def damaged_failure(self,kind,call_index=-1):
        self.initialize();captured={}
        def hook(point):
            if point=='protocol_failure_committed':
                state=p.read_json(self.path);call=state['calls'][call_index]
                body=p.response_store.directory(self.path)/call['raw_body_ref']['file']
                captured.update(path=body,raw=body.read_bytes(),index=call['index'])
                if kind=='missing':body.unlink()
                else:body.write_bytes(b'corrupt body fixture')
        with self.assertRaises(RuntimeError):
            p.run_phase(self.path,'initial-five',live=True,executor=self.executor({0:'old'}),hook=hook)
        state=p.read_json(self.path)
        self.assertEqual(state['status'],'running')  # Strict parent halt cannot certify missing evidence.
        self.assertEqual(len(state['calls']),2)
        return state,captured

    def assert_preserved_halt(self,before,after,audit):
        self.assertFalse(audit['recoverable'])
        self.assertEqual(audit['reason'],'response_evidence_invalid')
        self.assertEqual(after['status'],'halted');self.assertIsNone(after['active_run'])
        self.assertEqual(after['calls'],before['calls'])
        self.assertEqual(after['spent_cny'],before['spent_cny'])
        self.assertEqual(after['reserved_cny'],before['reserved_cny'])
        self.assertEqual(after['arms'][0]['protocol_failure'],before['arms'][0]['protocol_failure'])
        self.assertEqual(after['arms'][0]['terminal_sha256'],before['arms'][0]['terminal_sha256'])
        self.assertEqual(after['terminal_failure']['code'],'response_evidence_invalid')
        self.assertFalse(audit['executor_exit_confirmed'])

    def test_missing_last_protocol_body_audit_persists_halt(self):
        before,body=self.damaged_failure('missing')
        audit=p.audit_recovery(self.path);after=p.load_state(self.path,allow_body_errors=True)[0]
        self.assert_preserved_halt(before,after,audit)
        self.assertEqual(audit['body_evidence_errors'][0]['raw_body_ref'],before['calls'][-1]['raw_body_ref'])
        self.assertEqual(audit['prior_active_run'],before['active_run'])
        self.assertTrue(all(a['status']=='pending' for a in after['arms'][1:]))
        with self.assertRaises(RuntimeError):self.report()
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',live=True,executor=self.success)
        self.assertEqual(len(p.read_json(self.path)['calls']),2)

    def test_corrupt_last_protocol_body_audit_persists_halt(self):
        before,body=self.damaged_failure('corrupt')
        audit=p.audit_recovery(self.path);after=p.load_state(self.path,allow_body_errors=True)[0]
        self.assert_preserved_halt(before,after,audit)
        self.assertEqual(audit['body_evidence_errors'][0]['call_index'],1)
        with self.assertRaises(RuntimeError):p.load_state(self.path)

    def test_missing_earlier_body_does_not_reread_or_certify_it(self):
        before,body=self.damaged_failure('missing',0)
        audit=p.audit_recovery(self.path);after=p.load_state(self.path,allow_body_errors=True)[0]
        self.assert_preserved_halt(before,after,audit)
        self.assertEqual(audit['body_evidence_errors'][0]['call_index'],0)

    def test_restored_body_cannot_erase_nonrecoverable_stop(self):
        before,body=self.damaged_failure('missing')
        first=p.audit_recovery(self.path)
        second=p.audit_recovery(self.path)
        self.assertFalse(first['recoverable']);self.assertFalse(second['recoverable'])
        body['path'].write_bytes(body['raw'])
        state=p.load_state(self.path)[0];self.assertEqual(state['status'],'halted')
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])
        self.assertFalse(self.report()['quality_claim_allowed'])
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',live=True,executor=self.success)
        self.assertEqual(p.load_state(self.path)[0]['calls'],before['calls'])

    def test_audit_ledger_write_failure_never_claims_success(self):
        before,body=self.damaged_failure('missing');original=p.budget.save
        owner=p.owner_path(self.plan,'live');old_owner=owner.read_bytes();old_ledger=self.path.read_bytes()
        def fail(path,value):
            if Path(path)==self.path and value.get('stop_reason')=='response_evidence_invalid':
                raise OSError('unwritable ledger')
            return original(path,value)
        with patch.object(p.budget,'save',side_effect=fail),self.assertRaises(OSError):
            p.audit_recovery(self.path)
        self.assertEqual(self.path.read_bytes(),old_ledger);self.assertEqual(owner.read_bytes(),old_owner)
        self.assertEqual(p.read_json(self.path)['audits'],before['audits'])
        audit=p.audit_recovery(self.path)
        self.assert_preserved_halt(before,p.load_state(self.path,allow_body_errors=True)[0],audit)

    def test_audit_owner_write_failure_remains_explicit_until_retry(self):
        before,body=self.damaged_failure('corrupt');original=p.budget.save
        owner=p.owner_path(self.plan,'live')
        def fail(path,value):
            if Path(path)==owner and p.read_json(self.path).get('stop_reason')=='response_evidence_invalid':
                raise OSError('owner write')
            return original(path,value)
        with patch.object(p.budget,'save',side_effect=fail),self.assertRaises(OSError):
            p.audit_recovery(self.path)
        self.assertEqual(p.read_json(self.path)['status'],'halted')
        with self.assertRaises(RuntimeError):p.load_state(self.path,allow_body_errors=True)
        audit=p.audit_recovery(self.path)
        self.assert_preserved_halt(before,p.load_state(self.path,allow_body_errors=True)[0],audit)

    def test_missing_evidence_does_not_hide_corrupt_failure_proof(self):
        before,body=self.damaged_failure('missing')
        state=p.read_json(self.path);state['arms'][0]['terminal_sha256']='0'*64
        with p.budget.ledger_lock(self.path):p.commit(self.path,state)
        saved=self.path.read_bytes()
        with self.assertRaises(RuntimeError):p.audit_recovery(self.path)
        self.assertEqual(saved,self.path.read_bytes())

    def test_missing_evidence_does_not_hide_inconsistent_stored_usage(self):
        before,body=self.damaged_failure('missing')
        state=p.read_json(self.path);state['calls'][-1]['prompt_tokens']+=1
        with p.budget.ledger_lock(self.path):p.commit(self.path,state)
        saved=self.path.read_bytes()
        with self.assertRaises(RuntimeError):p.audit_recovery(self.path)
        self.assertEqual(saved,self.path.read_bytes())

    def test_unknown_call_after_safe_prefix_keeps_reserve_when_audited(self):
        self.initialize()
        def execute(path,index,token):
            if index==0:return self.fail_with_reaped_child(path,index,token,'old')
            with self.transport(lambda req:(_ for _ in ()).throw(TimeoutError('fixture'))):
                p.Provider(path,index,token)(messages=[])
        with self.assertRaises(Exception):p.run_phase(self.path,'initial-five',live=True,executor=execute)
        before=p.read_json(self.path);call=before['calls'][1]
        (p.response_store.directory(self.path)/call['raw_body_ref']['file']).unlink()
        audit=p.audit_recovery(self.path);after=p.load_state(self.path,allow_body_errors=True)[0]
        self.assert_preserved_halt(before,after,audit)
        self.assertEqual(Decimal(after['reserved_cny']),p.followup.RESERVE)
        self.assertEqual(after['arms'][1]['status'],'blocked')
        self.assertEqual(len(after['calls']),3)
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',live=True,executor=self.success)
