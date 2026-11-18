import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from readonly_agent.core import Snapshot,Limits
from readonly_agent.preparation import make_plan,PreparationSession
from readonly_agent.journal import Ledger
from readonly_agent.offline import no_network
from experiments.eval_preflight.common_contract import SharedWire,raw_payload,FINISH,ContractError
from experiments.cohort_preflight.sdk_adapter import run_sdk_case

class LongIssueTests(unittest.TestCase):
    def test_full_long_issue_reaches_mock_wire_without_truncation(self):
        with TemporaryDirectory() as td:
            root=Path(td).resolve();(root/'x.py').write_text('def x():\n    return 1\n')
            snapshot=Snapshot(root,['x.py']);issue='Synthetic long issue. '+'中文 abc '*2000
            self.assertGreater(len(issue.encode()),8192)
            with no_network(root/'profiles'):
                ledger=Ledger.create(root/'ledger.sqlite',make_plan(snapshot,issue))
                with patch('readonly_agent.preparation.BudgetedWire',lambda led,arm:SharedWire(led,arm,snapshot)):
                    session=PreparationSession(ledger,'baseline')
                script=[{'stop_reason':'tool_use','content':[{'type':'tool_use','id':'end','name':'finish',
                    'input':{'files':[],'entities':[],'answer':'synthetic'}}]}]
                result=run_sdk_case(snapshot=snapshot,issue=issue,script=script,output_dir=root/'output',
                    limits=Limits(max_requests=4),preparation=session)
                self.assertEqual(result['status'],'completed',result)
                self.assertTrue(any(m['content']==issue for m in session.wire.requests[0]['messages']))
                self.assertEqual(len(session.wire.requests),1)

    def test_native_common_request_cap_rejects_oversize(self):
        with self.assertRaises(ContractError):raw_payload([{'role':'user','content':'x'*65536}],[FINISH],closing=False)

    def test_cohort_cannot_enable_old_live_session(self):
        with self.assertRaises(PermissionError):
            run_sdk_case(snapshot=None,issue='x',script=None,output_dir=None,live=object())
if __name__=='__main__':unittest.main()
