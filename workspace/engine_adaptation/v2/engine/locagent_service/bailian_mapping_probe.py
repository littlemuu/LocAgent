"""One approved batch and two independent single-input controls; no retries."""
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

APPROVAL='Sentinel_4ced60ecff3c8191ad4bdceb94302de3'
FOLDER=ROOT/'outputs/bailian-mapping-probe-20261015'
PLAN=ROOT/'outputs/bailian-mapping-probe-manifest.json'
LOCK=ROOT/'outputs/bailian-mapping-probe-20261015.lock'
OLD=Decimal('0.540672'); NEW=Decimal('0.065536'); TOTAL=Decimal('0.606208')
METHOD={'version':'normalized-explicit-index-pairwise-v1','min_same_cosine':0.99999,
        'max_same_abs_difference':0.001,'min_same_minus_cross_cosine':0.01,
        'on_uncertainty':'report inconclusive; never relax thresholds or send extra requests'}
ENTITIES=('src/itsdangerous/encoding.py:want_bytes','src/itsdangerous/signer.py:Signer.derive_key')


def protected():
    expected=json.loads((ROOT/'outputs/bailian-index-adapter-offline/protected-after.json').read_bytes())
    for path,digest in expected.items():
        p=Path(path)
        if p.is_symlink() or sha(p.read_bytes())!=digest:raise ValueError('Protected evidence changed')
    counts=[]
    for folder,n in [('bailian-live-20261015',16),('bailian-recovery-once-20261015',16),('bailian-single-diagnostic-20261015',1)]:
        with sqlite3.connect('file:'+str(ROOT/'outputs'/folder/'ledger.sqlite')+'?mode=ro&immutable=1',uri=True) as db:
            if db.execute('SELECT n,state FROM calls').fetchall()!=[(n,'unknown')]:raise ValueError('Old reservation changed')
            if db.execute('SELECT state FROM run').fetchall()!=[('halted',)]:raise ValueError('Old run changed')
        counts.append(n)
    if sum(c.reservation(n) for n in counts)!=OLD or c.reservation(4)!=NEW or OLD+NEW!=TOTAL or TOTAL>c.CAP:
        raise ValueError('Budget differs from approval')
    return expected


def requests(m):
    result=[]
    a,b=m['documents']
    for selected in ([a,b],[a],[b]):
        body=c.canonical(c.request([row['text'] for row in selected],'document'))
        result.append({'role':'document','ids':[row['id'] for row in selected],
                       'body':body,'sha256':sha(body),'count':len(selected)})
    return result


def expected_manifest():
    hashes=protected()
    old=json.loads((ROOT/'outputs/bailian-frozen-manifest.json').read_bytes());validate_dataset(old)
    docs=[]
    for entity in ENTITIES:
        selected=[row for row in old['documents'] if row['entity']==entity]
        if len(selected)!=1:raise ValueError('Ambiguous frozen input')
        docs.append(selected[0])
    if docs[0]['text']==docs[1]['text']:raise ValueError('Distinct inputs required')
    engines=engine_hashes();engines['locagent_service/bailian_mapping_probe.py']=sha(Path(__file__).read_bytes())
    m={'version':1,'approval':APPROVAL,'repo':old['repo'],'commit':old['commit'],
       'endpoint':c.endpoint(WORKSPACE,ORIGIN),'model':c.MODEL,'dimensions':1024,
       'document_parameters':c.request(['x'],'document')['parameters'],'documents':docs,'questions':[],
       'protected_hashes':hashes,'engine_files':engines,'comparison':METHOD,
       'old_unknown_cny':str(OLD),'new_max_reserved_cny':str(NEW),'combined_cap_cny':str(TOTAL),
       'max_requests':3,'max_input_items':4,'retry_count':0,'request_order':['A+B','A','B']}
    m['request_hashes']=[r['sha256'] for r in requests(m)]
    return m


def prepare():
    if LOCK.exists() or FOLDER.exists():raise ValueError('Probe already started')
    m=expected_manifest()
    with PLAN.open('xb') as f:f.write(c.canonical(m));f.flush();os.fsync(f.fileno())
    return {'manifest_sha256':sha(c.canonical(m)),'entities':ENTITIES,'comparison':METHOD,'combined_cap_cny':str(TOTAL)}


def validate():
    if any(p.is_symlink() for p in (ROOT,ROOT/'outputs',PLAN,FOLDER,LOCK)):raise ValueError('Unsafe path')
    m=json.loads(PLAN.read_bytes())
    if m!=expected_manifest():raise ValueError('Frozen probe or code changed')
    reqs=requests(m)
    if [r['count'] for r in reqs]!=[2,1,1]:raise ValueError('Request scope changed')
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
        if OLD+c.reservation(inputs)>TOTAL:raise ValueError('Combined budget exceeded')
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
        report={'step':index,'transport_invocations':int(invoked),'old_unknown_cny':str(OLD),
                'combined_retained_cny':str(OLD+c.reservation(inputs)),'journal':j.report()}
        j.write_once(f'step-{index:03d}.report.json',c.canonical(report))
        return report


def compare(batch,singles):
    if len(batch)!=2 or len(singles)!=2:raise ValueError('Two independent controls required')
    for v in (*batch,*singles):
        if len(v)!=1024 or not all(type(x) in (int,float) and math.isfinite(x) for x in v) or not math.isclose(math.hypot(*v),1.,rel_tol=1e-10):
            raise ValueError('Validated normalized vectors required')
    metrics=[]
    for i in range(2):
        for k in range(2):
            a,b=batch[i],singles[k]
            metrics.append({'batch_index':i,'single_input':('A','B')[k],
                            'cosine':math.fsum(x*y for x,y in zip(a,b)),
                            'max_abs_difference':max(abs(x-y) for x,y in zip(a,b)),
                            'l2_difference':math.hypot(*(x-y for x,y in zip(a,b)))})
    passed=all(metrics[i*2+i]['cosine']>=METHOD['min_same_cosine'] and
               metrics[i*2+i]['max_abs_difference']<=METHOD['max_same_abs_difference'] and
               metrics[i*2+i]['cosine']-metrics[i*2+1-i]['cosine']>=METHOD['min_same_minus_cross_cosine']
               for i in range(2))
    return {'result':'this_pair_passed' if passed else 'inconclusive','metrics':metrics,'frozen_method':METHOD}


if __name__=='__main__':
    import sys
    if sys.argv[1:]==['prepare']:print(json.dumps(prepare()))
    elif len(sys.argv)==3 and sys.argv[1]=='step':print(json.dumps(step(int(sys.argv[2]))))
    else:raise SystemExit('Use prepare or step 0|1|2')
