"""Frozen development-suite preparation. No live transport or credential loading."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from readonly_agent.authority import save_new
from readonly_agent.core import Snapshot, digest, validate_finish
from readonly_agent.journal import Ledger
from readonly_agent.preparation import make_plan
from readonly_agent.deepseek_wire import RESERVATION
from experiments.retrieval_choice.audit import audit

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT/'development_suite/v1'
FROZEN = PROJECT/'development_suite/v3/manifest.json'
ENGINE = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108')
IDS = ('d01_cache','d02_config','d03_access','d04_upload','d05_lease','d06_import')
CAP = 102_000_000


def hashes_under(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and p.suffix in ('.py','.json')
            and '__pycache__' not in p.parts and p.name != 'manifest.json'}


def candidate():
    rubrics = json.loads((ROOT/'evaluation/rubrics.json').read_text())
    assert [r['id'] for r in rubrics] == list(IDS)
    cases=[]
    for index, row in enumerate(rubrics):
        path=ROOT/'cases'/row['id']/'case.json'
        case=json.loads(path.read_text())
        snapshot=Snapshot(path.parent/case['root'],case['source_files'])
        for source in snapshot.files.values(): ast.parse(source)  # Never exec/import.
        assert len(row['answer_criteria']) == 4
        validate_finish({'files':row['gold_files'],'entities':row['gold_entities'],
                         'answer':'Static rubric membership check.'},snapshot)
        plan=make_plan(snapshot,case['issue'],ENGINE)
        cases.append({'id':row['id'],'title':row['title'],'case_file':str(path.relative_to(PROJECT)),
            'plan_hash':digest(plan),'plan':plan,'source_file_count':len(snapshot.files),
            'source_bytes':sum(len(s.encode()) for s in snapshot.files.values()),
            'arm_order':['baseline','retrieval'] if index%2==0 else ['retrieval','baseline'],
            'exposure':('Previously sent to the evaluated model in seven baseline requests across two halted batches; used for termination and answer-policy repair. '
                        if row['id']=='d01_cache' else 'No live evaluated-model exposure in the halted v1/v2 batches. ')
                       + 'Self-authored development task; author/scorer saw source and rubric. Not an independent test.'})
    return {'version':1,'kind':'development_paired_comparison','authorization':'not_granted',
        'transport':'offline_only','cases':cases,'suite_budget_micro_cny':CAP,
        'max_requests':48,'max_pair_budget_micro_cny':17_000_000,
        'full_reservations_micro_cny':6*8*RESERVATION,
        'revision':'v3: soft answer-length target, unchanged 2048 output tokens and 64 KiB raw receipt limit; v1 source, rubric and order preserved',
        'prior_batches':['d172860ae92d532c0ff60d6eded56b2d11de63a7672737076611c8be8610badb',
                         '4958a23e559dd53269cb04cebfb00cb5c1d73d527c29baf2fb6cc0fb0fc5dffd'],
        'source_and_rubric_hashes':hashes_under(ROOT),
        'orchestrator_hashes':hashes_under(Path(__file__).parent),
        'exclusions':{'greeting':'Prior live requests and protocol repairs; excluded.',
                      'crossfile_webhook':'Repeated live/offline use and tool-description tuning; excluded.',
                      'legacy_repository_cohorts':'Exposure not exhaustively audited; not imported or scored here. Old unanswered baseline is not evidence of advantage.'},
        'scoring':{'automatic':'Distinct exact file/entity precision, recall, F1 and reciprocal rank within submitted top 5; no substring match.',
                   'manual':'Four prewritten binary evidence criteria, one point each; freeze reviewer decisions and supporting answer/source excerpts before unblinding arm.',
                   'failure':'Failed/no finish receives zero in all-planned completion-adjusted localization and answer scores. Not-run remains explicit with null raw score; separately report planned denominator and reached pairs.',
                   'aggregation':'Per-case paired differences and macro means over all six planned tasks; also completed-pair descriptive results. No significance or generalization claim.',
                   'simulation':'Scripted runs are never scored as model quality.'},
        'stop_policy':'Sequential; any failed arm, unknown cost, timeout or changed binding halts entire suite; no automatic resume, retry, replacement or extra final response.',
        'latency':'Monotonic wall time around each isolated arm process, includes SDK/retriever startup; do not call it provider-only latency.',
        'sending':'Only shared system/controller prompts, question, tool schemas, prior model messages and allowlisted source evidence. Never rubric, gold, offline scripts, logs, other cases or credentials.',
        'startup':'Requires fresh user suite approval and live suite admission adapter with global stop behavior verified before paid execution; present CLI rejects live mode.'}


def validate():
    saved=json.loads(FROZEN.read_text())
    if saved != candidate(): raise ValueError('frozen_suite_changed')
    return saved


class BatchGuard:
    """Offline durable global envelope; pair reserves its full cap before work.

    It deliberately cannot authorize real transport. Existing per-pair Ledger
    independently enforces 4/arm, 8/pair, 17 CNY and unknown-reservation fencing.
    """
    @classmethod
    def create(cls,path,manifest):
        path=Path(path).resolve()
        if path.exists(): raise FileExistsError('fresh_suite_ledger_required')
        if manifest['transport']!='offline_only' or manifest['authorization']!='not_granted':
            raise PermissionError('offline_suite_only')
        import os
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('CREATE TABLE state(hash TEXT,owner TEXT,halted INTEGER,reason TEXT);'
                            'CREATE TABLE pairs(id TEXT PRIMARY KEY,seq INTEGER UNIQUE,status TEXT,cost INTEGER,requests INTEGER);')
            db.execute('INSERT INTO state VALUES(?,?,0,NULL)',(digest(manifest),str(path)))
        return cls(path,manifest)

    def __init__(self,path,manifest):self.path,self.manifest=Path(path).resolve(),manifest

    def start(self,identifier):
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            state=db.execute('SELECT * FROM state').fetchone()
            if state[:2]!=(digest(self.manifest),str(self.path)):raise ValueError('suite_binding_changed')
            rows=db.execute('SELECT id,status,cost,requests FROM pairs ORDER BY seq').fetchall()
            if state[2] or any(r[1]!='completed' for r in rows):raise RuntimeError('suite_stopped_or_pending')
            ids=[r['id'] for r in self.manifest['cases']]
            if len(rows)>=len(ids) or identifier!=ids[len(rows)]:raise ValueError('unexpected_or_duplicate_case')
            if sum(r[2] for r in rows)+17_000_000>self.manifest['suite_budget_micro_cny']:
                raise RuntimeError('suite_budget_exhausted')
            db.execute('INSERT INTO pairs VALUES(?,?,?,?,?)',(identifier,len(rows),'pending',17_000_000,8))

    def finish(self,identifier,summary):
        calls=summary['calls']
        if (not summary['simulation'] or summary['halted'] or summary['reserved_micro_cny']
                or not 1 <= len(calls) <= 8
                or not 0 <= summary['spent_upper_micro_cny'] <= 17_000_000
                or any(c['status']!='settled' for c in calls)):
            self.halt('pair_not_cleanly_settled');raise RuntimeError('pair_not_cleanly_settled')
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA synchronous=FULL')
            cursor=db.execute("UPDATE pairs SET status='completed',cost=?,requests=? WHERE id=? AND status='pending'",
                              (summary['spent_upper_micro_cny'],len(calls),identifier))
            if cursor.rowcount!=1:raise RuntimeError('pair_not_pending')

    def halt(self,reason):
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('UPDATE state SET halted=1,reason=COALESCE(reason,?)',(reason,))


def score_localization(result,rubric):
    def metric(kind):
        expected=set(rubric['gold_'+kind])
        # The production finish validator rejects invalid/duplicate/oversized lists.
        raw=result.get('answer',{}).get(kind,[]) if isinstance(result.get('answer'),dict) else []
        if (not isinstance(raw,list) or len(raw)>5 or any(not isinstance(p,str) for p in raw)
                or len(set(raw))!=len(raw)):
            raise ValueError('invalid_localization_submission')
        predicted=raw
        if result.get('status')!='completed':predicted=[]
        hits=len(set(predicted)&expected)
        precision=hits/len(predicted) if predicted else 0
        recall=hits/len(expected) if expected else 0
        return {'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0,
                'reciprocal_rank':next((1/(i+1) for i,p in enumerate(predicted) if p in expected),0),
                'hits':hits,'submitted':len(predicted),'gold':len(expected)}
    return {kind:metric(kind) for kind in ('files','entities')}


def replay(output):
    manifest=validate()
    output=Path(output).resolve();output.mkdir(mode=0o700,parents=True,exist_ok=False)
    guard=BatchGuard.create(output/'suite.sqlite',manifest)
    records=[]
    try:
        for item in manifest['cases']:
            validate();guard.start(item['id'])
            pair=output/item['id'];pair.mkdir(mode=0o700)
            save_new(pair/'proposal.json',item['plan'])
            ledger=Ledger.create(pair/'simulation.sqlite',item['plan'])
            for arm in item['arm_order']:
                start=time.perf_counter()
                try:
                    with (pair/(arm+'.log')).open('x') as log:
                        done=subprocess.run([sys.executable,'-B','-m','readonly_agent.prepare_run',
                            '--case',str(PROJECT/item['case_file']),'--output',str(pair),
                            '--locagent-python',str(ENGINE/'.venv/bin/python'), '--locagent-root',str(ENGINE),
                            '--arm',arm],cwd=PROJECT,stdout=log,stderr=subprocess.STDOUT,timeout=120,check=False)
                    if not (pair/arm/'result.json').is_file():raise RuntimeError('worker_missing_result')
                except BaseException as error:
                    records.append({'case':item['id'],'arm':arm,'simulation':True,'status':'failed',
                        'failure':type(error).__name__,'elapsed_wall_seconds':time.perf_counter()-start,
                        'quality_not_scored_reason':'scripted_fixture','live_calls':0})
                    raise
                elapsed=time.perf_counter()-start
                result=json.loads((pair/arm/'result.json').read_text())
                observation=audit(pair/'simulation.sqlite',pair/arm,arm)
                calls=[c for c in ledger.summary()['calls'] if c['arm']==arm]
                record={'case':item['id'],'arm':arm,'simulation':True,'elapsed_wall_seconds':elapsed,
                    'status':result['status'],'failure':result['failure'],'requests':result['requests'],
                    'tool_calls':result['tool_calls'],'source_bytes':result['source_bytes'],
                    'live_calls':result['live_calls'],'simulated_cost_upper_micro_cny':sum(c['cost'] or 0 for c in calls),
                    'observability':observation,'localization_score':None,'answer_score':None,
                    'quality_not_scored_reason':'scripted_fixture'}
                records.append(record);save_new(pair/(arm+'-measurement.json'),record)
                if done.returncode or result['status']!='completed':raise RuntimeError('arm_failed')
            guard.finish(item['id'],ledger.summary())
    except BaseException as error:
        guard.halt(type(error).__name__)
        reached={(r['case'],r['arm']) for r in records}
        not_run=[{'case':c['id'],'arm':arm,'status':'not_run','raw_score':None}
                 for c in manifest['cases'] for arm in c['arm_order'] if (c['id'],arm) not in reached]
        save_new(output/'interrupted.json',{'reason':type(error).__name__,'arm_records':records,'not_run':not_run})
        raise
    save_new(output/'measurements.json',{'suite_hash':digest(manifest),'simulation':True,'records':records,
                                       'live_calls':0,'claims_benefit':False})
    print(json.dumps({'suite_hash':digest(manifest),'cases':len(manifest['cases']),
                      'arms':len(records),'mock_requests':sum(r['requests'] for r in records),'live_calls':0}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['freeze','check','replay'])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    if args.live:raise PermissionError('development_suite_live_transport_not_enabled')
    if args.action=='freeze':
        manifest=candidate();FROZEN.parent.mkdir(mode=0o700,parents=True,exist_ok=False);save_new(FROZEN,manifest)
        print(json.dumps({'suite_hash':digest(manifest),'cases':len(manifest['cases']),'live_calls':0}))
    elif args.action=='check':
        print(json.dumps({'suite_hash':digest(validate()),'status':'unchanged','live_calls':0}))
    else:
        if args.output is None:parser.error('--output required')
        replay(args.output)


if __name__=='__main__':
    main()
