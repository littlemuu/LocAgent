"""Parent admission and durable remaining-17-pair budget. No credential discovery."""
import json,os,sqlite3
from pathlib import Path
from datetime import datetime,timedelta,timezone
from contextlib import contextmanager
from uuid import uuid4
from readonly_agent.authority import private,save_new
from readonly_agent.core import digest
from experiments.cohort_preflight.entry import ROOT,read,sha
from .guard import IDS,source_hashes,verify

from .cumulative import NEW_MICRO_CNY,CASE_HOLD,verify_prior,check_totals

def now():return datetime.now(timezone.utc)

def validate(plan, *, check_case_material=True):
    if (set(plan)!= {'version','mode','cases','sources','max_requests','budget_micro_cny','authorization','scoring_hash','design_hash','prior_usage','cumulative_request_limit','cumulative_micro_cny_limit'}
        or plan['version']!=1 or plan['mode'] not in ('live','rehearsal') or plan['authorization']!='not_granted'
        or plan['max_requests']!=136 or plan['budget_micro_cny']!=NEW_MICRO_CNY or plan['cumulative_request_limit']!=344 or plan['cumulative_micro_cny_limit']!=630000000 or plan['sources']!=source_hashes()
        or plan['scoring_hash']!=sha(ROOT/'experiments/eval_preflight/scoring.py')
        or plan['design_hash']!=sha(ROOT/'verification/remaining17-v5-preparation/proposal.json')
        or tuple(c['id'] for c in plan['cases'])!=IDS):raise PermissionError('batch_binding_changed')
    verify_prior(plan['prior_usage'])
    for i,c in enumerate(plan['cases']):
        if set(c)!= {'id','plan','hash'} or digest(c['plan'])!=c['hash']:raise PermissionError('case_hash_changed')
        p=c['plan']
        if check_case_material:
            verify(p,plan['mode'])
        order=['baseline','retrieval'] if i%2==0 else ['retrieval','baseline']
        if p['cohort_binding']['case_id']!=c['id'] or p.get('arm_order')!=order:raise PermissionError('case_order_changed')

class Parent:
    def __init__(self,root):
        self.root=Path(root).absolute()
        if self.root!=self.root.resolve():raise PermissionError('canonical_parent_required')
    def prepare(self,plan,*,consent=None,currency=None,input_ceiling=None,output_ceiling=None,all_charges_included=False):
        validate(plan);h=digest(plan)
        if plan['mode']=='live' and (consent!=f'APPROVE REMAINING17V5 {h} NEW136 NEWCNY289 TOTAL344 TOTALCNY630' or currency!='CNY' or input_ceiling!='2' or output_ceiling!='8' or all_charges_included is not True):
            raise PermissionError('explicit_batch_and_account_approval_required')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=False)
        save_new(self.root/'grant.json',{'kind':'remaining17-v5-case-'+plan['mode'],'plan':plan,'hash':h,'root':str(self.root),'expires':(now()+timedelta(hours=24)).isoformat(),'approved':now().isoformat(),'pricing':{'currency':currency,'input_ceiling':input_ceiling,'output_ceiling':output_ceiling,'all_charges_included':all_charges_included} if plan['mode']=='live' else None,'consent':consent if plan['mode']=='live' else 'OFFLINE FIXTURE ONLY'})
        return h
    def record(self):
        private(self.root,True);private(self.root/'grant.json');r=read(self.root/'grant.json');p=r['plan']
        if r['root']!=str(self.root) or r['hash']!=digest(p) or r['kind']!='remaining17-v5-case-'+p['mode']:raise PermissionError('parent_record_changed')
        if p['mode']=='live' and r['consent']!=f"APPROVE REMAINING17V5 {r['hash']} NEW136 NEWCNY289 TOTAL344 TOTALCNY630":raise PermissionError('consent_changed')
        if p['mode']=='live' and r.get('pricing')!={'currency':'CNY','input_ceiling':'2','output_ceiling':'8','all_charges_included':True}:raise PermissionError('account_confirmation_changed')
        start,end=datetime.fromisoformat(r['approved']),datetime.fromisoformat(r['expires'])
        if not start<=now()<end or end-start>timedelta(hours=24):raise PermissionError('parent_expired')
        # All cases are fully checked at preparation; each active child is fully
        # rechecked by CohortAuthority/CohortWire before use. Other cases' source
        # bytes need not be reloaded at every parent ledger transaction. Retain
        # complete frozen-plan/code/prior-usage/budget validation on every read.
        validate(p,check_case_material=False);return r
    def claim(self):
        r=self.record();token=uuid4().hex
        save_new(self.root/'claim.json',{'hash':r['hash'],'token':token})
        return token
    def check(self,token):
        r=self.record();private(self.root/'claim.json')
        if read(self.root/'claim.json')!={'hash':r['hash'],'token':token}:raise PermissionError('parent_claim_changed')
        return r

class BatchLedger:
    @classmethod
    def create(cls,parent,token):
        r=parent.check(token);run=parent.root/'run';run.mkdir(mode=0o700,exist_ok=False)
        save_new(run/'binding.json',{'root':str(parent.root),'token':token,'hash':r['hash']})
        p=run/'batch.sqlite';fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600);os.close(fd)
        with sqlite3.connect(p) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('CREATE TABLE state(owner TEXT,hash TEXT,halted INTEGER,reason TEXT);CREATE TABLE cases(id TEXT PRIMARY KEY,seq INTEGER,status TEXT,hold INTEGER,cost INTEGER,requests INTEGER);')
            db.execute('INSERT INTO state VALUES(?,?,0,NULL)',(str(p),r['hash']))
            db.executemany('INSERT INTO cases VALUES(?,?,?,0,0,0)',[(c['id'],i,'not_started') for i,c in enumerate(r['plan']['cases'])])
        return cls(parent,token)
    def __init__(self,parent,token):self.parent,self.token,self.path=parent,token,parent.root/'run/batch.sqlite'
    @contextmanager
    def tx(self):
        r=self.parent.check(self.token);private(self.path)
        db=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True);db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE');s=db.execute('SELECT * FROM state').fetchone();rows=db.execute('SELECT * FROM cases ORDER BY seq').fetchall()
            if s['owner']!=str(self.path) or s['hash']!=r['hash'] or [x['id'] for x in rows]!=list(IDS):raise PermissionError('batch_storage_changed')
            if any(x['status'] not in ('not_started','active','completed','failed') or x['hold'] not in (0,CASE_HOLD) or not 0<=x['cost']<=CASE_HOLD or not 0<=x['requests']<=8 for x in rows):raise PermissionError('batch_state_invalid')
            if sum(x['hold']+x['cost'] for x in rows)>NEW_MICRO_CNY or sum(x['requests'] for x in rows)>136:raise PermissionError('batch_budget_invalid')
            check_totals(sum(x['hold']+x['cost'] for x in rows),sum(x['requests'] for x in rows))
            yield db,s,rows
            db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
    def begin(self,id):
        with self.tx() as (db,s,rows):
            first=next((x for x in rows if x['status']!='completed'),None)
            if s['halted'] or first is None or first['id']!=id or first['status']!='not_started':raise PermissionError('case_not_available')
            if sum(x['hold']+x['cost'] for x in rows)+CASE_HOLD>NEW_MICRO_CNY:raise PermissionError('batch_budget_exhausted')
            db.execute("UPDATE cases SET status='active',hold=? WHERE id=?",(CASE_HOLD,id))
    def active(self,id):
        with self.tx() as (db,s,rows):
            if s['halted'] or next(x for x in rows if x['id']==id)['status']!='active':raise PermissionError('parent_not_active')
    def finish(self,id,ledger):
        r=self.parent.check(self.token);item=next(c for c in r['plan']['cases'] if c['id']==id)
        expected=self.parent.root/'run/children'/id
        if r['plan']['mode']=='live':expected=expected/item['hash']
        expected=expected/'run/ledger.sqlite'
        if ledger.path!=expected or ledger.plan_hash!=item['hash']:raise PermissionError('wrong_child_ledger')
        summary=ledger.summary()
        with ledger.transaction() as db:
            arms=db.execute('SELECT name,finished FROM arms').fetchall()
        if summary['halted'] or summary['reserved_micro_cny'] or sorted((x[0],x[1]) for x in arms)!=[('baseline',1),('retrieval',1)] or not 2<=len(summary['calls'])<=8:raise RuntimeError('case_not_finished')
        with self.tx() as (db,s,rows):
            if s['halted']:raise PermissionError('batch_halted')
            c=db.execute("UPDATE cases SET status='completed',hold=0,cost=?,requests=? WHERE id=? AND status='active'",(summary['spent_upper_micro_cny'],len(summary['calls']),id))
            if c.rowcount!=1:raise PermissionError('case_not_active')
    def halt(self,reason):
        with sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True) as db:
            db.execute('PRAGMA synchronous=FULL');db.execute('UPDATE state SET halted=1,reason=COALESCE(reason,?)',(reason,));db.execute("UPDATE cases SET status='failed' WHERE status='active'")
    def summary(self):
        with self.tx() as (db,s,rows):return {'halted':bool(s['halted']),'reason':s['reason'],'cases':[dict(x) for x in rows],'case_hold_micro_cny':sum(x['hold'] for x in rows),'settled_cost_micro_cny':sum(x['cost'] for x in rows),'completed_case_requests':sum(x['requests'] for x in rows)}

    def audit_summary(self):
        """Read expired/stopped records without granting any execution permission."""
        private(self.path);private(self.parent.root/'grant.json')
        r=read(self.parent.root/'grant.json')
        if r['hash']!=digest(r['plan']) or r['root']!=str(self.parent.root):raise PermissionError('audit_binding_changed')
        with sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            states=db.execute('SELECT * FROM state').fetchall()
            rows=db.execute('SELECT * FROM cases ORDER BY seq').fetchall()
        if len(states)!=1 or states[0]['owner']!=str(self.path) or states[0]['hash']!=r['hash'] or [x['id'] for x in rows]!=list(IDS):raise PermissionError('audit_storage_changed')
        s=states[0]
        return {'halted':bool(s['halted']),'reason':s['reason'],'cases':[dict(x) for x in rows],
                'case_hold_micro_cny':sum(x['hold'] for x in rows),'settled_cost_micro_cny':sum(x['cost'] for x in rows),
                'completed_case_requests':sum(x['requests'] for x in rows),'audit_only':True}

def check_child(root,plan):
    root=Path(root).absolute();run=root.parents[1]
    b=read(run/'binding.json');parent=Parent(b['root']);r=parent.check(b['token'])
    if run!=parent.root/'run' or b['hash']!=r['hash']:raise PermissionError('parent_binding_changed')
    id=plan['cohort_binding']['case_id'];item=next(c for c in r['plan']['cases'] if c['id']==id)
    if root!=run/'children'/id or digest(plan)!=item['hash']:raise PermissionError('wrong_parent_child')
    BatchLedger(parent,b['token']).active(id)
