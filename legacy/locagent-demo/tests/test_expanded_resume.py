import json,multiprocessing,os,socket,tempfile,unittest
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch
from locagent_service import bailian_expanded_runner as r
from locagent_service import bailian_expanded_resume as s

def plan(counts=(16,1)):
    out=[]
    for i,n in enumerate(counts):
        body=r.request([f'public text {i}-{j}' for j in range(n)],'document')
        out.append({'body':body,'body_sha256':r.sha(r.canonical(body)),'ids':[f'{i}-{j}' for j in range(n)],'role':'document'})
    return out

def raw(n,tokens=10):
    return r.canonical({'usage':{'prompt_tokens':tokens,'total_tokens':tokens},'output':{'embeddings':[{'text_index':i,'embedding':[1]+[0]*1023} for i in range(n)]}})

def kill_worker(directory,phase):
    ledger=s._AttemptLedger(directory,plan((1,)),{'offline':True})
    def transport(*args):
        with open(str(directory)+'-calls','ab',buffering=0) as f:f.write(b'1\n');os.fsync(f.fileno())
        return 200,raw(1)
    def check(at):
        if at==phase:os._exit(73)
    s._drive(ledger,transport,check)

class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name);self.p=plan();self.binding={'offline':True}
        self.network=patch.object(socket.socket,'connect',side_effect=AssertionError('network prohibited'));self.network.start()
        self.calls=0
    def tearDown(self):self.network.stop();self.tmp.cleanup()
    def ledger(self,**kw):return s._AttemptLedger(self.directory,self.p,self.binding,**kw)
    def fake(self,endpoint,body):
        self.calls+=1;self.assertEqual(endpoint,r.ENDPOINT)
        return 200,raw(len(json.loads(body)['input']['texts']))
    def test_base_unknown_never_released_and_restart_zero_send(self):
        result=s._drive(self.ledger(),self.fake)
        self.assertEqual(Decimal(result['spent_cny']),s.BASE_SPENT+r.cost(20))
        self.assertEqual(Decimal(result['unknown_cny']),s.BASE_UNKNOWN)
        self.assertEqual(result['inflight_cny'],'0')
        s._drive(self.ledger(),self.fake);self.assertEqual(self.calls,2)
    def test_cumulative_cap_includes_old_spent_and_unknown(self):
        with self.assertRaisesRegex(r.Halt,'cumulative_cap_exceeded'):
            s._drive(self.ledger(base_spent=Decimal('1.5')),self.fake)
        self.assertEqual(self.calls,0)
    def test_second_failure_is_terminal_no_automatic_retry(self):
        def bad(*args):self.calls+=1;return 403,b'{"code":"AllocationQuota.FreeTierOnly"}'
        with self.assertRaisesRegex(r.Halt,'continuation_invalid_response_held'):s._drive(self.ledger(),bad)
        with self.assertRaisesRegex(r.Halt,'continuation_unknown_stop_no_retry'):s._drive(self.ledger(),self.fake)
        self.assertEqual(self.calls,1)
        self.assertEqual(self.ledger().balance()['unknown'],s.BASE_UNKNOWN+Decimal('.262144'))
    def test_timeout_preserves_additional_reservation(self):
        def timeout(*args):self.calls+=1;raise TimeoutError('secret')
        with self.assertRaisesRegex(r.Halt,'continuation_transport_unknown'):s._drive(self.ledger(),timeout)
        self.assertEqual(self.ledger().balance()['unknown'],Decimal('.524288'))
    def test_physical_and_original_batch_indices(self):
        s._drive(self.ledger(),self.fake)
        ledger=self.ledger();reserved=[e['data'] for e in ledger.events if e['data']['phase']=='reserved']
        self.assertEqual([e['batch_index'] for e in reserved],[490,491])
        self.assertEqual([e['physical_attempt_index'] for e in reserved],[491,492])
    def test_unauthorized_run_zero_reads_or_calls(self):
        with patch.object(s,'spec') as spec:
            with self.assertRaisesRegex(r.Halt,'continuation_not_authorized'):s.run(approval_id=r.APPROVAL_ID)
            spec.assert_not_called()
    def test_fixed_frozen_scope_exact_128_and_2024_inputs(self):
        p,d,b,a=s.spec()
        self.assertEqual(d,r.RUN_DOMAIN/r.RUN_ID)
        self.assertEqual(len(p[490:]),128)
        self.assertEqual(sum(len(i['ids']) for i in p[490:] if i['role']=='document'),1974)
        self.assertEqual(sum(len(i['ids']) for i in p[490:] if i['role']=='query'),50)
        self.assertEqual(b['max_cumulative_physical_requests'],619)
    def test_auth_tamper_rejected(self):
        self.ledger();(self.directory/s.AUTH_NAME).write_bytes(b'{}')
        with self.assertRaisesRegex(r.Halt,'continuation_authorization_changed'):self.ledger()
    def test_raw_tamper_rejected(self):
        s._drive(self.ledger(),self.fake)
        (self.directory/'continuation-body-000490.bin').write_bytes(raw(16,11))
        with self.assertRaisesRegex(r.Halt,'continuation_raw_changed'):self.ledger()
    def test_usage_missing_or_over_limit_stops(self):
        for n,body in enumerate([b'{"usage":{}}',raw(16,16*r.TOKEN_LIMIT+1)]):
            sub=self.directory/str(n);sub.mkdir(mode=0o700)
            with self.assertRaisesRegex(r.Halt,'continuation_invalid_response_held'):
                s._drive(s._AttemptLedger(sub,self.p,self.binding),lambda *_:(200,body))
    def test_persist_failure_zero_send(self):
        original=r.persist
        def fail(path,body):
            if path.name=='continuation-event-000000.json':raise OSError('disk full')
            original(path,body)
        with patch.object(r,'persist',side_effect=fail),self.assertRaises(OSError):s._drive(self.ledger(),self.fake)
        self.assertEqual(self.calls,0)
    def test_process_crash_windows_never_replay(self):
        for phase in ('before_reserve','after_reserve','before_send','after_send','after_raw_file','before_settle','after_settle'):
            with self.subTest(phase=phase):
                directory=self.directory/phase;directory.mkdir(mode=0o700)
                proc=multiprocessing.get_context('fork').Process(target=kill_worker,args=(directory,phase));proc.start();proc.join(10)
                self.assertEqual(proc.exitcode,73)
                ledger=s._AttemptLedger(directory,plan((1,)),self.binding);calls=[]
                def fake(*args):calls.append(1);return 200,raw(1)
                if phase in ('before_reserve','before_settle','after_settle'):
                    s._drive(ledger,fake);self.assertEqual(len(calls),int(phase=='before_reserve'))
                else:
                    with self.assertRaisesRegex(r.Halt,'continuation_unknown_stop_no_retry'):s._drive(ledger,fake)
                    self.assertEqual(calls,[])
                f=Path(str(directory)+'-calls');original_calls=len(f.read_text().splitlines()) if f.exists() else 0
                self.assertLessEqual(original_calls+len(calls),1)

if __name__=='__main__':unittest.main()
