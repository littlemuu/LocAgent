"""Suite-scoped one-use admission and durable case/arm gates. No key loading."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from readonly_agent.authority import Authority, Admission, private, save_new, current_plan
from readonly_agent.core import digest
from readonly_agent.journal import Ledger
from experiments.dev_compare.suite import candidate as base_candidate, hashes_under, PROJECT

ROOT = PROJECT/'authority-batches'
FROZEN = PROJECT/'development_suite/live-v3/manifest.json'


def candidate():
    # The live manifest binds the complete recomputed base, including sources,
    # scoring and runtime. Historical base manifests must never be rewritten.
    base=base_candidate()
    return {'version':1,'base_manifest':base,'base_manifest_hash':digest(base),
            'driver_hashes':hashes_under(Path(__file__).parent),
            'observability_auditor_sha256':hashlib.sha256((PROJECT/'experiments/retrieval_choice/audit.py').read_bytes()).hexdigest(),
            'authorization':'not_granted','transport':'explicit_suite_admission_only',
            'max_requests':48,'budget_micro_cny':102_000_000,
            'policy':{'arm_timeout_seconds':360,'sequential':True,'retry':False,
                      'resume':False,'case_cap_micro_cny':17_000_000,
                      'credential_source':'explicit_private_env_after_admission_and_tty_checks'}}


def validate_plan(plan):
    if plan != candidate():raise PermissionError('suite_sources_policy_or_driver_changed')


def frozen():
    plan=json.loads(FROZEN.read_text());validate_plan(plan);return plan


def clock():return datetime.now(timezone.utc)


class SuiteAuthority(Authority):
    def __init__(self,root=ROOT):super().__init__(root)

    def approve(self,plan,expected_hash,*,consent,currency,input_ceiling,output_ceiling,all_charges_included):
        if (digest(plan)!=expected_hash or consent!=f'APPROVE SUITE {expected_hash} CNY 102'
                or currency!='CNY' or input_ceiling!='2' or output_ceiling!='8'
                or all_charges_included is not True):raise PermissionError('exact_suite_and_price_consent_required')
        validate_plan(plan)
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True);private(self.root,True)
        folder=self.folder(expected_hash);folder.mkdir(mode=0o700,exist_ok=False)
        now=clock()
        record={'kind':'suite_grant','plan':plan,'plan_hash':expected_hash,'consent':consent,
                'currency':currency,'input_ceiling':input_ceiling,'output_ceiling':output_ceiling,
                'all_charges_included':True,'authority_root':str(self.root),'run_dir':str(folder/'run'),
                'approved_at':now.isoformat(),'expires_at':(now+timedelta(hours=24)).isoformat()}
        save_new(folder/'grant.json',record)

    def read(self,h,*,fresh=True):
        folder=self.folder(h);private(self.root,True);private(folder,True);private(folder/'grant.json')
        r=json.loads((folder/'grant.json').read_text())
        if (r['kind']!='suite_grant' or r['plan_hash']!=h or digest(r['plan'])!=h
                or r['authority_root']!=str(self.root) or r['run_dir']!=str(folder/'run')
                or r['consent']!=f'APPROVE SUITE {h} CNY 102' or r['currency']!='CNY'
                or r['input_ceiling']!='2' or r['output_ceiling']!='8' or r['all_charges_included'] is not True):
            raise PermissionError('suite_grant_binding_changed')
        if fresh:
            start,end=datetime.fromisoformat(r['approved_at']),datetime.fromisoformat(r['expires_at'])
            if not start<=clock()<end or end-start>timedelta(hours=24):raise PermissionError('suite_grant_expired')
            validate_plan(r['plan'])
        return r

    def claim(self,h):
        self.read(h)
        token=uuid4().hex
        save_new(self.folder(h)/'claim.json',{'suite_hash':h,'token':token})
        return SuiteAdmission(self,h,token)


class SuiteAdmission:
    def __init__(self,authority,h,token):self.authority,self.hash,self.token=authority,h,token

    def validate(self):
        r=self.authority.read(self.hash)
        path=self.authority.folder(self.hash)/'claim.json';private(path)
        if json.loads(path.read_text())!={'suite_hash':self.hash,'token':self.token}:
            raise PermissionError('suite_claim_mismatch')
        return r


class SuiteLedger:
    @classmethod
    def create(cls,admission):
        r=admission.validate();root=Path(r['run_dir']);root.mkdir(mode=0o700,exist_ok=False)
        path=root/'suite.sqlite'
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600);os.close(fd)
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('CREATE TABLE state(hash TEXT,owner TEXT,halted INTEGER,reason TEXT);'
              'CREATE TABLE cases(id TEXT PRIMARY KEY,seq INTEGER UNIQUE,status TEXT,hold INTEGER,cost INTEGER);'
              'CREATE TABLE arms(case_id TEXT,arm TEXT,seq INTEGER,status TEXT,elapsed REAL,failure TEXT,PRIMARY KEY(case_id,arm));')
            db.execute('INSERT INTO state VALUES(?,?,0,NULL)',(admission.hash,str(path)))
            for i,c in enumerate(r['plan']['base_manifest']['cases']):
                db.execute('INSERT INTO cases VALUES(?,?,?,0,0)',(c['id'],i,'not_run'))
                for j,arm in enumerate(c['arm_order']):
                    db.execute('INSERT INTO arms VALUES(?,?,?,?,NULL,NULL)',(c['id'],arm,j,'not_run'))
        fd=os.open(root,os.O_RDONLY);os.fsync(fd);os.close(fd)
        return cls(admission)

    def __init__(self,admission):
        self.admission=admission
        self.record=admission.validate()
        self.path=Path(self.record['run_dir'])/'suite.sqlite'
        private(self.path)

    def transaction(self):
        from contextlib import contextmanager
        @contextmanager
        def transaction():
            self.admission.validate()
            db=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=5)
            db.row_factory=sqlite3.Row
            try:
                db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
                state=db.execute('SELECT * FROM state').fetchone()
                if state is None or state['hash']!=self.admission.hash or state['owner']!=str(self.path):
                    raise PermissionError('suite_ledger_binding_changed')
                cases=db.execute('SELECT * FROM cases ORDER BY seq').fetchall()
                if [c['id'] for c in cases]!=[c['id'] for c in self.record['plan']['base_manifest']['cases']]:
                    raise PermissionError('suite_case_binding_changed')
                if sum(c['hold']+c['cost'] for c in cases)>102_000_000:raise PermissionError('suite_budget_corruption')
                yield db,state
                db.commit()
            except BaseException:
                db.rollback();raise
            finally:db.close()
        return transaction()

    def begin_case(self,identifier):
        with self.transaction() as (db,state):
            rows=db.execute('SELECT * FROM cases ORDER BY seq').fetchall()
            first=next((r for r in rows if r['status']!='completed'),None)
            if state['halted'] or first is None or first['id']!=identifier or first['status']!='not_run':
                raise PermissionError('suite_case_not_available')
            if sum(r['cost']+r['hold'] for r in rows)+17_000_000>102_000_000:
                raise PermissionError('suite_budget_exhausted')
            db.execute("UPDATE cases SET status='active',hold=17000000 WHERE id=?",(identifier,))

    def begin_arm(self,identifier,arm):
        with self.transaction() as (db,state):
            case=db.execute('SELECT * FROM cases WHERE id=?',(identifier,)).fetchone()
            rows=db.execute('SELECT * FROM arms WHERE case_id=? ORDER BY seq',(identifier,)).fetchall()
            first=next((r for r in rows if r['status']!='completed'),None)
            if state['halted'] or case['status']!='active' or first is None or first['arm']!=arm or first['status']!='not_run':
                raise PermissionError('suite_arm_not_available')
            db.execute("UPDATE arms SET status='running' WHERE case_id=? AND arm=?",(identifier,arm))

    def assert_active(self,identifier,arm=None):
        with self.transaction() as (db,state):
            case=db.execute('SELECT status FROM cases WHERE id=?',(identifier,)).fetchone()
            if state['halted'] or case is None or case['status']!='active':raise PermissionError('suite_stopped')
            if arm is not None:
                row=db.execute('SELECT status FROM arms WHERE case_id=? AND arm=?',(identifier,arm)).fetchone()
                if row is None or row['status']!='running':raise PermissionError('suite_arm_not_running')

    def finish_arm(self,identifier,arm,result,ledger,elapsed):
        summary=ledger.summary()
        with sqlite3.connect(ledger.path) as db:
            finished=db.execute('SELECT finished FROM arms WHERE name=?',(arm,)).fetchone()
        if (result.get('status')!='completed' or result.get('sdk_status')!='finished'
                or finished!=(1,) or summary['halted'] or summary['reserved_micro_cny']
                or not 1<=sum(c['arm']==arm for c in summary['calls'])<=4):
            raise RuntimeError('arm_not_cleanly_finished')
        with self.transaction() as (db,state):
            if state['halted']:raise PermissionError('suite_stopped')
            cur=db.execute("UPDATE arms SET status='completed',elapsed=? WHERE case_id=? AND arm=? AND status='running'",
                           (elapsed,identifier,arm))
            if cur.rowcount!=1:raise PermissionError('arm_not_running')

    def finish_case(self,identifier,ledger):
        summary=ledger.summary()
        if summary['halted'] or summary['reserved_micro_cny'] or len(summary['calls'])>8:
            raise RuntimeError('pair_not_cleanly_settled')
        with self.transaction() as (db,state):
            rows=db.execute('SELECT status FROM arms WHERE case_id=?',(identifier,)).fetchall()
            if state['halted'] or len(rows)!=2 or any(r['status']!='completed' for r in rows):
                raise PermissionError('pair_incomplete')
            cur=db.execute("UPDATE cases SET status='completed',hold=0,cost=? WHERE id=? AND status='active'",
                           (summary['spent_upper_micro_cny'],identifier))
            if cur.rowcount!=1:raise PermissionError('pair_not_active')

    def halt(self,reason,identifier=None,arm=None,elapsed=None):
        # Emergency persistence must work even after expiry/source changes.
        with sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('UPDATE state SET halted=1,reason=COALESCE(reason,?)',(reason,))
            db.execute("UPDATE cases SET status='failed' WHERE status='active'")
            db.execute("UPDATE arms SET status='failed',failure=?,elapsed=COALESCE(elapsed,?) WHERE status='running'",(reason,elapsed))

    def summary(self):return read_status(self.admission.authority,self.admission.hash)


class CaseAuthority(Authority):
    """Non-standalone child grants: every request rechecks the active suite arm."""
    def __init__(self,suite,identifier,arm=None):
        self.suite,self.identifier,self.arm=suite,identifier,arm
        record=suite.validate()
        self.item=next(c for c in record['plan']['base_manifest']['cases'] if c['id']==identifier)
        super().__init__(Path(record['run_dir'])/'children')

    def prepare(self):
        SuiteLedger(self.suite).assert_active(self.identifier)
        self.root.mkdir(mode=0o700,exist_ok=True);private(self.root,True)
        folder=self.folder(self.item['plan_hash']);folder.mkdir(mode=0o700,exist_ok=False)
        save_new(folder/'grant.json',{'kind':'suite_case_only','suite_hash':self.suite.hash,
            'case':self.identifier,'plan':self.item['plan'],'plan_hash':self.item['plan_hash'],
            'run_dir':str(folder/'run')})

    def read(self,h,*,fresh=True):
        # No standalone/expired/fresh=False escape from suite checks.
        self.suite.validate();SuiteLedger(self.suite).assert_active(self.identifier,self.arm)
        if h!=self.item['plan_hash']:raise PermissionError('wrong_suite_case')
        private(self.root,True);folder=self.folder(h);private(folder,True);private(folder/'grant.json')
        record=json.loads((folder/'grant.json').read_text())
        expected={'kind':'suite_case_only','suite_hash':self.suite.hash,'case':self.identifier,
                  'plan':self.item['plan'],'plan_hash':h,'run_dir':str(folder/'run')}
        if record!=expected:raise PermissionError('suite_case_grant_changed')
        current_plan(record['plan'])
        return record


def read_status(authority,h):
    record=authority.read(h,fresh=False)
    path=Path(record['run_dir'])/'suite.sqlite'
    if not path.exists():return {'status':'claimed_without_ledger' if (authority.folder(h)/'claim.json').exists() else 'not_started'}
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        state=dict(db.execute('SELECT * FROM state').fetchone())
        if state['hash']!=h or state['owner']!=str(path):raise PermissionError('status_binding_changed')
        cases=[dict(r) for r in db.execute('SELECT * FROM cases ORDER BY seq')]
        arms=[dict(r) for r in db.execute('SELECT * FROM arms ORDER BY case_id,seq')]
    requests=spent=pending=0
    pair_summaries=[]
    for item in record['plan']['base_manifest']['cases']:
        ledger_path=Path(record['run_dir'])/'children'/item['plan_hash']/'run/ledger.sqlite'
        if ledger_path.exists():
            summary=Ledger(ledger_path,item['plan_hash']).summary()
            requests+=len(summary['calls']);spent+=summary['spent_upper_micro_cny'];pending+=summary['reserved_micro_cny']
            pair_summaries.append({'case':item['id'],'budget':summary})
    return {'status':'halted' if state['halted'] else 'completed' if all(c['status']=='completed' for c in cases) else 'running',
            'execution_mode':json.loads((path.parent/'execution.json').read_text())['mode'] if (path.parent/'execution.json').exists() else 'unknown',
            'reason':state['reason'],'requests':requests,'spent_upper_micro_cny':spent,
            'request_pending_micro_cny':pending,'case_budget_hold_micro_cny':sum(c['hold'] for c in cases),
            'limit_micro_cny':102_000_000,'cases':cases,'arms':arms,'pair_budgets':pair_summaries}
