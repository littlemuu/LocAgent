"""One pair. CLI is offline-only; live requires an explicitly supplied Admission/key.

No credential lookup, environment loading, automatic approval, retry or resume.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path
from readonly_agent.authority import Admission
from readonly_agent.core import Limits, digest, encoded
from readonly_agent.journal import Ledger
from readonly_agent.offline import no_network
from experiments.cohort_preflight.entry import ROOT, read, save
from .guard import CohortAuthority, RehearsalAuthority, RehearsalAdmission, CohortWire, verify
from .fixtures import mock_transport
from .sdk_adapter import run_sdk_case

def run_pair(plan_path, admission, *, key=None, parent_alive=lambda:None):
    plan_path = Path(plan_path).resolve()
    plan = read(plan_path)
    rehearsal = plan['cohort_execution'] == 'rehearsal'
    expected = RehearsalAdmission if rehearsal else Admission
    if type(admission) is not expected or (rehearsal and key is not None):
        raise PermissionError('explicit_matching_admission_required')
    if not rehearsal and type(admission.authority) is not CohortAuthority:
        raise PermissionError('cohort_authority_required')
    record = admission.validate()
    if record['plan_hash'] != digest(plan):
        raise PermissionError('plan_changed_after_claim')
    value, snapshot, status = verify(plan, plan['cohort_execution'])
    output = Path(record['run_dir'])
    output.mkdir(exist_ok=False)
    ledger = Ledger.create(output/'ledger.sqlite', plan, admission=None if rehearsal else admission)
    admission.validate(ledger.path)
    request = {'plan':str(plan_path),'authority_root':str(admission.authority.root),
               'plan_hash':admission.plan_hash,'token':admission.token,'ledger':str(ledger.path),
               'parent_pid':os.getpid(), 'batch_parent_pid':os.getppid()}
    def worker(operation, **extra):
        parent_alive()
        admission.validate(ledger.path)
        with tempfile.TemporaryDirectory() as td:
            env={'PATH':os.defpath,'LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1',
                 'HF_DATASETS_OFFLINE':'1','MPLCONFIGDIR':td,'XDG_CACHE_HOME':td,
                 'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
            result = subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python',
                '-I','-B',str(ROOT/'experiments/cohort_five_paths_v2/worker.py')],
                input=encoded({**request,'operation':operation,**extra}),cwd=td,env=env,capture_output=True,timeout=300)
            if result.returncode:
                # Do not persist arbitrary stderr that might contain a future credential.
                raise RuntimeError('isolated_worker_failed')
            return json.loads(result.stdout)
    results = []
    started_arms = []
    try:
        with no_network(output/'profiles') as attempts:
            class Cache:
                snapshot_id=snapshot.identity
                def retrieve(self, query):
                    return worker('query',query=query)['text']
            for arm in plan['arm_order']:
                started_arms.append(arm)
                if arm == 'baseline':
                    native = worker('native', **({} if rehearsal else {'key':key}))
                    save(output/'native.json', native)
                    results.append({'arm':arm,'status':native['status']})
                else:
                    wire = CohortWire(ledger,'retrieval',admission,key,snapshot=snapshot,
                                      transport=mock_transport('retrieval',snapshot,value['issue']) if rehearsal else None, parent_alive=parent_alive)
                    sdk = run_sdk_case(snapshot=snapshot,issue=value['issue'],script=None,output_dir=output/'sdk',
                        limits=Limits(max_requests=4),retriever=Cache(),live=wire)
                    results.append({'arm':arm,'status':sdk['status']})
                    if sdk['status'] != 'completed':
                        raise RuntimeError('sdk_failed')
            if attempts:
                raise RuntimeError('unexpected_parent_network')
        outcome = {'status':'completed','results':results}
    except BaseException as error:
        # Even a failure before the next reservation consumes the whole pair.
        with ledger.transaction() as db:
            db.execute('UPDATE run SET halted=1,reason=COALESCE(reason,?)',(type(error).__name__,))
        outcome = {'status':'failed','failure':type(error).__name__,'results':results}
    finally:
        key = None
    with ledger.transaction() as db:
        started = db.execute('SELECT COUNT(*) FROM calls WHERE transport_started=1').fetchone()[0]
    outcome.update(mode='simulation' if rehearsal else 'live',case_id=value['case_id'],
        plan_hash=digest(plan),budget=ledger.summary(),quality_scored=False,
        real_transport_starts=0 if rehearsal else started,
        real_model_requests=0 if rehearsal else None,
        provider_receipt_not_proven_by_transport_start=True,
        mock_requests=started if rehearsal else 0,
        started_arms=started_arms, second_arm_not_started=len(started_arms)<2)
    save(output/'result.json',outcome)
    return outcome

def main():
    if len(sys.argv) != 3 or sys.argv[1] != '--rehearse':
        raise SystemExit('Only --rehearse PROPOSAL is available; no live CLI or credential discovery.')
    path = Path(sys.argv[2]).resolve()
    plan = read(path)
    verify(plan,'rehearsal')
    auth = RehearsalAuthority(path.parent/'rehearsal-authority')
    auth.prepare_fixture(plan)
    result = run_pair(path,auth.claim(digest(plan)))
    print({k:result[k] for k in ('status','mode','mock_requests','real_transport_starts')})

if __name__ == '__main__':
    main()
