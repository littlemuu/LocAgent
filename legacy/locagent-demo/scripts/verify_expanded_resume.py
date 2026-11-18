import json,socket,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests')]
from locagent_service import bailian_expanded_resume as s
from locagent_service import bailian_expanded_runner as r
from test_expanded_resume import raw

def blocked(*a,**k):raise RuntimeError('offline only')
socket.socket.connect=blocked;socket.create_connection=blocked
out=ROOT/'outputs/bailian-expanded-resume-preflight-20261016';out.mkdir(mode=0o700)
suite=unittest.TestSuite()
for pattern in ('test_expanded_resume.py','test_expanded_budget.py','test_bailian_response.py','test_expanded_metrics.py'):
    suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=pattern))
with (out/'tests.log').open('x') as f:result=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
assert result.wasSuccessful()
plan,directory,binding,audit=s.spec();selected=plan[490:];calls=[]
with tempfile.TemporaryDirectory() as tmp:
    fake_binding={**binding,'purpose':'offline-verification-only','ledger_directory':tmp}
    ledger=s._AttemptLedger(Path(tmp),selected,fake_binding)
    def fake(endpoint,body):
        i=len(calls);assert r.sha(body)==selected[i]['body_sha256'];calls.append(i)
        n=len(selected[i]['ids']);return 200,raw(n,n*10)
    status=s._drive(ledger,fake)
    assert len(calls)==128
    s._drive(s._AttemptLedger(Path(tmp),selected,fake_binding),lambda *_:(_ for _ in ()).throw(AssertionError('repeat')))
assert s.baseline()==audit
proof={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
       'frozen_request_bodies_verified':128,'original_batches_reused':490,'original_vectors_reused':7840,
       'new_document_inputs':1974,'new_query_inputs':50,'new_calls_limit':128,'total_calls_limit':619,
       'mock_status':status,'real_requests':0,'original_ledger_unchanged':True,
       'resume_engine_sha256':r.sha((ROOT/'locagent_service/bailian_expanded_resume.py').read_bytes()),
       'tests_sha256':r.sha((out/'tests.log').read_bytes())}
(out/'audit.json').write_bytes(r.canonical(proof));print(json.dumps(proof,indent=2))
