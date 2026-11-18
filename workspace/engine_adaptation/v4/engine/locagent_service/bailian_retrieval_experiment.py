"""Approved 32-document/10-query exploratory retrieval; immutable source evidence, no retries."""
from decimal import Decimal
import fcntl
import json
import math
import os
from pathlib import Path
import sqlite3

from locagent_service import bailian_contract as c
from locagent_service.bailian_live import ROOT, Journal, engine_hashes, sha, exchange, ORIGIN, WORKSPACE
from locagent_service.bailian_dataset import validate_dataset
from locagent_service.bailian_config import load_env_file

APPROVAL='Sentinel_8f31b18ee4c88191b87d0e23ea87a835'
FOLDER=ROOT/'outputs/bailian-retrieval-20261016'
PLAN=ROOT/'outputs/bailian-retrieval-manifest.json'
LOCK=ROOT/'outputs/bailian-retrieval-20261016.lock'
OLD=Decimal('0.622592'); NEW=Decimal('0.655360'); TOTAL=Decimal('1.277952')
from importlib.metadata import version
from locagent_service.bailian_memory_evaluation import RANKING,cached_request,load_response,assemble,evaluate
CACHE=ROOT/'outputs/bailian-mapping-controls-20261015'
SOURCE_MANIFEST_HASH='1ea1d3b244615e14395d07e5dfe09b2696d64dffddebf916cc289657b0e56511'


def combined(inputs,old=OLD):
    if old!=OLD or type(inputs) is not int or not 0<=inputs<=40:raise ValueError('Approved cumulative budget mismatch')
    total=old+(c.reservation(inputs) if inputs else Decimal(0))
    if total>TOTAL:raise ValueError('Approved cumulative cap exceeded')
    return total


def protected():
    baseline=json.loads((ROOT/'outputs/bailian-transport-diagnostics-offline/protected-after.json').read_bytes())
    for path,digest in baseline.items():
        if sha(Path(path).read_bytes())!=digest:raise ValueError('Earlier protected evidence changed')
    expected_rows={'bailian-live-20261015':[(16,'unknown')],
                   'bailian-recovery-once-20261015':[(16,'unknown')],
                   'bailian-single-diagnostic-20261015':[(1,'unknown')],
                   'bailian-mapping-probe-20261015':[(2,'settled'),(1,'unknown')],
                   'bailian-mapping-controls-20261015':[(1,'settled'),(1,'settled')]}
    allrows=[];paths=[]
    for folder,expected in expected_rows.items():
        directory=ROOT/'outputs'/folder
        with sqlite3.connect('file:'+str(directory/'ledger.sqlite')+'?mode=ro&immutable=1',uri=True) as db:
            rows=db.execute('SELECT n,state FROM calls ORDER BY id').fetchall()
        if rows!=expected:raise ValueError('Historical ledger changed')
        allrows.extend(rows);paths.extend(p for p in directory.iterdir() if p.is_file())
        paths.append(directory.with_suffix('.lock'))
    for name in ('bailian-frozen-manifest.json','bailian-recovery-once-manifest.json','bailian-single-diagnostic-manifest.json','bailian-mapping-probe-manifest.json','bailian-mapping-controls-manifest.json'):
        paths.append(ROOT/'outputs'/name)
    paths.append(Path('/home/lenovo/projects/LocAgent/README.md'))
    if sum(c.reservation(n) for n,state in allrows)!=OLD or sum(c.reservation(n) for n,state in allrows if state=='unknown')!=Decimal('0.557056'):
        raise ValueError('Historical budget mismatch')
    if sha((CACHE/'manifest.json').read_bytes())!=SOURCE_MANIFEST_HASH:raise ValueError('Wrong cache source')
    if c.reservation(40)!=NEW or combined(40)!=TOTAL:raise ValueError('New budget mismatch')
    if any(p.is_symlink() for p in paths):raise ValueError('Unsafe evidence path')
    return {str(p):sha(p.read_bytes()) for p in paths}


def cached(m):
    source=json.loads((CACHE/'manifest.json').read_bytes());parts=[];descriptors=[]
    for index,doc in enumerate(source['documents']):
        if doc not in m['documents']:raise ValueError('Cache input outside frozen dataset')
        request=cached_request(source,m,doc,index)
        vectors,descriptor=load_response(CACHE,index,source,request)
        parts.append(('document',request['ids'],vectors));descriptors.append(descriptor)
    if len(descriptors)!=2 or len({d['ids'][0] for d in descriptors})!=2:raise ValueError('Expected exactly two distinct cached documents')
    return parts,descriptors


def requests(m):
    cache_ids={d['ids'][0] for d in m['cached_sources']}
    docs=[d for d in m['documents'] if d['id'] not in cache_ids]
    result=[]
    for role,selected in [('document',docs[:16]),('document',docs[16:]),('query',m['questions'])]:
        body=c.canonical(c.request([row['text'] for row in selected],role))
        result.append({'role':role,'ids':[row['id'] for row in selected],'body':body,'sha256':sha(body),'count':len(selected)})
    return result


def expected_manifest():
    hashes=protected()
    old=json.loads((ROOT/'outputs/bailian-frozen-manifest.json').read_bytes());validate_dataset(old)
    engines=engine_hashes()
    for name in ('bailian_retrieval_experiment.py','bailian_memory_evaluation.py'):
        engines['locagent_service/'+name]=sha((ROOT/'locagent_service'/name).read_bytes())
    m={k:old[k] for k in ('repo','commit','endpoint','model','dimensions','document_parameters','parameters','documents','questions','source_files','git_blobs','chunker','selection','preprocessing')}
    if m['endpoint']!=c.endpoint(WORKSPACE,ORIGIN) or m['model']!=c.MODEL or m['dimensions']!=1024 or m['document_parameters']!=c.request(['x'],'document')['parameters'] or m['parameters']!=c.request(['x'],'query')['parameters']:
        raise ValueError('Frozen recipient or role configuration mismatch')
    m.update(version=1,approval=APPROVAL,protected_hashes=hashes,engine_files=engines,ranking=RANKING,
             old_retained_cny=str(OLD),old_unknown_cny='0.557056',new_max_reserved_cny=str(NEW),combined_cap_cny=str(TOTAL),
             max_requests=3,max_input_items=40,retry_count=0,request_order=['16 documents','14 documents','10 queries'],
             evaluation='exploratory-manual-development-set-not-blind',numeric_stability='independent observation; old experiment remains inconclusive',
             package_versions={name:version(name) for name in ('bm25s','PyStemmer','numpy')})
    _,m['cached_sources']=cached(m)
    m['request_hashes']=[x['sha256'] for x in requests(m)]
    return m


def prepare():
    if LOCK.exists() or FOLDER.exists():raise ValueError('Probe already started')
    m=expected_manifest()
    with PLAN.open('xb') as f:f.write(c.canonical(m));f.flush();os.fsync(f.fileno())
    return {'manifest_sha256':sha(c.canonical(m)),'documents':len(m['documents']),'queries':len(m['questions']),'cached_documents':2,'new_batch_sizes':[16,14,10],'combined_cap_cny':str(TOTAL)}


def validate():
    if any(p.is_symlink() for p in (ROOT,ROOT/'outputs',PLAN,FOLDER,LOCK)):raise ValueError('Unsafe path')
    m=json.loads(PLAN.read_bytes())
    if m!=expected_manifest():raise ValueError('Frozen probe or code changed')
    reqs=requests(m)
    if [r['count'] for r in reqs]!=[16,14,10]:raise ValueError('Request scope changed')
    return m,reqs


def step(index):
    if type(index) is not int or index not in (0,1,2):raise ValueError('Outside approved request sequence')
    m,reqs=validate()
    binding=c.canonical({'approval':APPROVAL,'manifest_sha256':sha(c.canonical(m))})
    if index==0:
        if FOLDER.exists():raise ValueError('No reset permitted')
        fd=os.open(LOCK,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600)
    else:fd=os.open(LOCK,os.O_RDWR|os.O_NOFOLLOW)
    with os.fdopen(fd,'r+b') as held:
        fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if index==0:
            held.write(binding);held.flush();os.fsync(held.fileno())
            parent=os.open(LOCK.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(parent)
            finally:os.close(parent)
        elif held.read()!=binding:raise ValueError('Authority marker mismatch')
        j=Journal(FOLDER,m,reqs,create=index==0,approval=APPROVAL)
        with j.db() as db:
            rows=j.audit(db)
            if len(rows)!=index or any(row[3]!='settled' for row in rows) or db.execute('SELECT state FROM run').fetchone()!=('active',):
                raise ValueError('Prior request unresolved or step consumed')
        inputs=sum(row[2] for row in rows)+reqs[index]['count']
        if combined(inputs)>TOTAL:raise ValueError('Combined budget exceeded')
        # Persistent intent refuses repeat even if interrupted before Journal reserve.
        j.write_once(f'step-{index:03d}.intent.json',c.canonical({'request_sha256':reqs[index]['sha256']}))
        config=load_env_file(ROOT/'.env.bailian.local')
        if c.endpoint(config.get('DASHSCOPE_WORKSPACE_ID'),config.get('DASHSCOPE_API_HOST'))!=m['endpoint']:
            raise ValueError('Configured recipient changed')
        invoked=False
        def once(body):
            nonlocal invoked
            if invoked or body!=reqs[index]['body']:raise ValueError('Replay refused')
            invoked=True
            return exchange(body,config)
        try:j.step(index,once)
        except ValueError:pass
        finally:config.clear()
        protected()
        report={'step':index,'transport_invocations':int(invoked),'old_retained_cny':str(OLD),
                'combined_retained_cny':str(combined(inputs)),'journal':j.report()}
        j.write_once(f'step-{index:03d}.report.json',c.canonical(report))
        return report


def finish():
    m,reqs=validate();parts,descriptors=cached(m)
    j=Journal(FOLDER,m,reqs,approval=APPROVAL)
    with j.db() as db:
        rows=j.audit(db)
    if len(rows)!=3 or any(row[3]!='settled' for row in rows):raise ValueError('All three fresh responses required')
    for index,request in enumerate(reqs):
        vectors,source=load_response(FOLDER,index,m,request)
        parts.append((request['role'],request['ids'],vectors));descriptors.append(source)
    values=assemble(m,parts)
    result={'manifest_sha256':j.identity,'source_inventory':descriptors,'accounting':j.report(),
            'old_retained_cny':str(OLD),'combined_retained_cny':str(combined(40)),
            'old_unknown_cny':'0.557056','provider_actual_charge':'unknown; estimate is not billing',
            'retrieval':evaluate(m,values)}
    protected()
    j.write_once('results.json',c.canonical(result))
    with j.db() as db:db.execute("UPDATE run SET state='completed'")
    j.write_once('completed.json',c.canonical({'manifest_sha256':j.identity,'new_calls':3,'no_more_calls':True}))
    return {'metrics':result['retrieval']['metrics'],'combined_retained_cny':str(combined(40)),'new_usage_cost_estimate_cny':result['accounting']['settled_usage_cost_cny'],'state':'completed'}


if __name__=='__main__':
    import sys
    if sys.argv[1:]==['prepare']:print(json.dumps(prepare()))
    elif len(sys.argv)==3 and sys.argv[1]=='step':print(json.dumps(step(int(sys.argv[2]))))
    elif sys.argv[1:]==['finish']:print(json.dumps(finish()))
    else:raise SystemExit('Use prepare, step 0|1|2, or finish')
