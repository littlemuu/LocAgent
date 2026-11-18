import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from locagent_service import bailian_contract as c
from locagent_service.bailian_live import Journal, batches, exchange, HOST, ORIGIN, WORKSPACE


class LiveSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.manifest={'documents':[{'id':'d1','text':'public code'}], 'questions':[{'id':'q1','text':'public question'}]}
        self.requests=batches(self.manifest)
        self.folder=Path(self.tmp.name)/'authority'
        self.journal=Journal(self.folder,self.manifest,self.requests,create=True)

    def fake(self,body):
        n=len(json.loads(body)['input']['texts'])
        return 200,c.canonical({'usage':{'prompt_tokens':7,'total_tokens':7},'output':{'embeddings':[
            {'text_index':i,'embedding':[1.]+[0.]*1023} for i in range(n)]}})

    def test_no_replay_and_reservation_retained(self):
        self.journal.step(0,self.fake)
        again=Journal(self.folder,self.manifest,self.requests)
        again.step(0,lambda _:self.fail('No repeated request'))
        report=again.report()
        self.assertEqual(report['retained_full_reservation_cny'],'0.016384')
        self.assertEqual(report['calls'][0]['state'],'settled')
        audit=json.loads((self.folder/'response-000.audit.json').read_text())
        self.assertEqual(audit['usage']['total_tokens'],7)
        self.assertEqual(len(audit['vectors'][0]),1024)

    def test_any_unknown_halts_all_future_inputs(self):
        with self.assertRaises(ValueError):self.journal.step(0,lambda _: (401,b'{"secret":"never persist this"}'))
        again=Journal(self.folder,self.manifest,self.requests)
        for index in (0,1):
            with self.assertRaisesRegex(ValueError,'no further requests'):
                again.step(index,lambda _:self.fail('No request'))
        self.assertNotIn('never persist',json.dumps(again.report()))
        self.assertEqual(again.report()['calls'][0]['http_status'],401)
        audit=json.loads((self.folder/'response-000.audit.json').read_text())
        self.assertEqual(audit['failure']['path'],'$http_status')
        self.assertNotIn('never persist',json.dumps(audit))

    def test_exception_and_interrupt_halt(self):
        def crash(body):raise KeyboardInterrupt()
        with self.assertRaisesRegex(ValueError,'Run halted'):self.journal.step(0,crash)
        with self.assertRaises(ValueError):self.journal.step(1,self.fake)

    def test_partial_inflight_reservation_blocks_restart(self):
        with self.journal.db() as db:
            db.execute("INSERT INTO calls(id,request_hash,n,state) VALUES (0,?,1,'reserved')",(self.requests[0]['sha256'],))
        with self.assertRaisesRegex(ValueError,'uncertain'):self.journal.step(0,self.fake)

    def test_no_reinitialize_existing_authority(self):
        with self.assertRaises(FileExistsError):Journal(self.folder,self.manifest,self.requests,create=True)

    def test_changed_manifest_or_inode_rejected(self):
        with self.assertRaises(ValueError):Journal(self.folder,dict(self.manifest,changed=True),self.requests)
        path=self.folder/'ledger.sqlite'
        raw=path.read_bytes();path.rename(self.folder/'old.sqlite');path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'binding mismatch'):Journal(self.folder,self.manifest,self.requests)

    def test_sequence_and_ledger_hash_guard(self):
        with self.assertRaises(ValueError):self.journal.step(1,self.fake)
        with self.journal.db() as db:db.execute("UPDATE run SET manifest_hash='changed'")
        with self.assertRaises(ValueError):self.journal.step(0,self.fake)

    def test_response_missing_usage_wrong_dimension_or_model_stops(self):
        for mutate in [lambda d:d.pop('usage'),lambda d:d['output']['embeddings'][0].update(embedding=[1.]),lambda d:d.update(model='wrong')]:
            folder=Path(self.tmp.name)/str(id(mutate))
            j=Journal(folder,self.manifest,self.requests,create=True)
            data=json.loads(self.fake(b'{"input":{"texts":["a"]}}')[1]);mutate(data)
            with self.assertRaises(ValueError):j.step(0,lambda _: (200,c.canonical(data)))
            self.assertEqual(j.report()['calls'][0]['diagnostic'],'response_invalid')

    def test_pretransport_budget_cap(self):
        manifest={'documents':[{'id':str(i),'text':str(i)} for i in range(62)],'questions':[]}
        requests=batches(manifest);j=Journal(Path(self.tmp.name)/'cap',manifest,requests,create=True)
        for index in range(3):j.step(index,self.fake)
        with self.assertRaisesRegex(ValueError,'Budget exceeded'):j.step(3,lambda _:self.fail('No overbudget call'))

    def test_http_origin_path_and_redirect_not_followed(self):
        conn=Mock();response=conn.getresponse.return_value
        response.status=302;response.getheader.return_value='0';response.read.return_value=b'redirect'
        factory=Mock(return_value=conn)
        result=exchange(b'{}',{'DASHSCOPE_API_KEY':'synthetic-only','DASHSCOPE_WORKSPACE_ID':WORKSPACE,'DASHSCOPE_API_HOST':ORIGIN},connection_factory=factory)
        self.assertEqual(result,(302,b'redirect'));conn.request.assert_called_once()
        self.assertEqual(factory.call_args.args[0],HOST)
        self.assertEqual(conn.request.call_args.args[:2],('POST',c.PATH))
        conn.close.assert_called_once()

    def test_http_exception_no_retry_and_close(self):
        conn=Mock();conn.request.side_effect=TimeoutError()
        from locagent_service.bailian_transport_diagnostics import TransportFailure
        with self.assertRaises(TransportFailure):
            exchange(b'{}',{'DASHSCOPE_API_KEY':'synthetic-only','DASHSCOPE_WORKSPACE_ID':WORKSPACE,'DASHSCOPE_API_HOST':ORIGIN},connection_factory=lambda *a,**k:conn)
        conn.request.assert_called_once();conn.close.assert_called_once()

    def test_mixed_host_rejected_before_connection(self):
        with self.assertRaises(ValueError):
            exchange(b'{}',{'DASHSCOPE_API_KEY':'synthetic-only','DASHSCOPE_WORKSPACE_ID':WORKSPACE,'DASHSCOPE_API_HOST':ORIGIN+'/compatible-mode/v1'},connection_factory=lambda *a,**k:self.fail('No connect'))


if __name__=='__main__':unittest.main()
