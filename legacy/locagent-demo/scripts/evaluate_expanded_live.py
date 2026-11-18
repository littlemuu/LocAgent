"""Read-only real-ledger audit, then frozen offline retrieval metrics. Never sends."""
import collections
from decimal import Decimal
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from locagent_service import bailian_expanded_runner as r
from locagent_service.bailian_response import validate_response
from offline_bailian_rrf import entity_ranking,rrf

OUT=ROOT/'outputs/bailian-expanded50-live-evaluation-20261016-r01'


def blocked(*a,**k):raise RuntimeError('offline evaluation prohibits network')


def metrics(qs,rankings,kind):
    eligible=[q for q in qs if kind=='file' or q['function_primary_eligible']]
    result={}
    for k in (1,3,5):
        hits=[];recalls=[]
        for q in eligible:
            gold=set(q[kind+'_gold']);got=set(rankings[q['id']][:k]);n=len(gold&got)
            assert gold
            hits.append(int(n>0));recalls.append(n/len(gold))
        result[str(k)]={'hit':sum(hits)/len(eligible) if eligible else None,'recall':sum(recalls)/len(eligible) if eligible else None,'denominator':len(eligible)}
    return result


def main():
    socket.socket.connect=blocked;socket.create_connection=blocked
    OUT.mkdir(mode=0o700)
    manifest=json.loads(r.FROZEN.read_bytes())
    plan,directory,binding,identity=r._fixed_spec(r.RUN_DOMAIN)
    identity.update(approval_id=r.APPROVAL_ID,approved_date='2026-10-16')
    binding.update(identity,purpose='approved-live')
    protected=json.loads((ROOT/'outputs/bailian-expanded50-20261016/protected-before.json').read_bytes())
    assert all(r.sha(Path(p).read_bytes())==h for p,h in protected.items())
    # Fixed existing ledger only; do not run recover or mutate budget during audit.
    assert directory.is_dir() and (directory/'run.json').is_file()
    with r.locked(directory):
        journal=r.Journal(directory,plan,binding)
        balance=journal.balance()
        counts=dict(collections.Counter(row['state'] for row in journal.rows.values()))
        events=[event['data'] for event in journal.events]
        spent_tokens=sum(row.get('tokens',0) for row in journal.rows.values())
        status='complete' if counts=={'settled':618} else 'stopped_incomplete'
        ledger_hashes={p.name:r.sha(p.read_bytes()) for p in directory.iterdir() if p.is_file() and p.name!='lock'}
        audit={'status':status,'run_id':r.RUN_ID,'approval_id':r.APPROVAL_ID,'manifest_sha256':r.MANIFEST_SHA,
               'endpoint':r.ENDPOINT,'model':manifest['model'],'dimensions':1024,'request_limit':618,
               'dispatch_events':sum(e['phase']=='dispatch' for e in events),'http_responses':sum(e['phase']=='raw' for e in events),
               'states':counts,'actual_tokens_validated':spent_tokens,
               **{key+'_cny':str(value) for key,value in balance.items()},
               'remaining_reserved_cny':str(balance['unknown']+balance['inflight']),
               'new_run_charge_upper_bound_cny':str(sum(balance.values())),
               'approved_cap_cny':'2','old_held_cny':'1.277952','old_unknown_cny':'0.557056',
               'combined_old_held_plus_new_upper_bound_cny':str(Decimal('1.277952')+sum(balance.values())),
               'budget_source':'validated provider usage x fixed .125 CNY per million; not invoice reconciliation',
               'protected_historical_files_unchanged':len(protected),'ledger_hashes':ledger_hashes,
               'engine_hashes':r.engine_identity(),'evaluation_script_sha256':r.sha(Path(__file__).read_bytes())}
        (OUT/'ledger-audit.json').write_bytes(r.canonical(audit))
        if status!='complete':
            print(json.dumps({k:v for k,v in audit.items() if k!='ledger_hashes'},indent=2));return
        vectors={}
        for i,item in enumerate(plan):
            raw=r.secure_read(directory/f'body-{i:06d}.bin')
            values,tokens,_=validate_response(raw,len(item['ids']),journal.rows[i]['http_status'])
            assert tokens==journal.rows[i]['tokens']
            for ident,value in zip(item['ids'],values):vectors[(item['role'],ident)]=value
    assert len(vectors)==9864
    import bm25s
    import Stemmer
    assert manifest['package_versions']=={name:importlib.metadata.version(name) for name in manifest['package_versions']}
    members={}
    for key,doc in manifest['unique_documents'].items():
        for member in doc['members']:
            assert member not in members or members[member]==key
            members[member]=key
    snapshots={(s['repo'],s['commit']):s for s in manifest['snapshots']}
    fn={name:{} for name in ('bm25','dense','rrf60_dense2')}
    file={name:{} for name in fn}
    candidate_counts={}
    # One fixed snapshot per query; no gold-file filtering or score-based tuning.
    for q in manifest['queries']:
        snap=snapshots[(q['repo'],q['commit'])]
        docs=[];keys=[]
        for member in snap['document_ids']:
            key=members[member];text=manifest['unique_documents'][key]['text'];entity=text.split('\n',1)[0]
            docs.append({'entity':entity,'text':text,'path':entity.split(':',1)[0]});keys.append(key)
        candidate_counts[q['id']]=len(docs)
        stemmer=Stemmer.Stemmer('english')
        bm=bm25s.BM25(k1=1.5,b=.75,method='lucene')
        bm.index(bm25s.tokenize([d['text'] for d in docs],stemmer=stemmer,stopwords='en',show_progress=False),show_progress=False)
        ids,scores=bm.retrieve(bm25s.tokenize(q['text'],stemmer=stemmer,stopwords='en',show_progress=False),k=len(docs),show_progress=False)
        ordered=[0.]*len(docs)
        for i,score in zip(ids[0],scores[0]):ordered[int(i)]=float(score)
        lexical,_=entity_ranking(docs,ordered,True)
        query=vectors[('query',q['id'])]
        dense,_=entity_ranking(docs,[math.fsum(a*b for a,b in zip(query,vectors[('document',key)])) for key in keys])
        hybrid,_=rrf(lexical,dense,k=60,bm25_weight=1,dense_weight=2)
        for name,ranking in [('bm25',lexical),('dense',dense),('rrf60_dense2',hybrid)]:
            fn[name][q['id']]=ranking
            file[name][q['id']]=list(dict.fromkeys(entity.split(':',1)[0] for entity in ranking))
    qs=manifest['queries']
    reports={name:{'function_primary':metrics(qs,fn[name],'function'),'file':metrics(qs,file[name],'file')}
             for name in fn}
    strata={repo:{name:{'function_primary':metrics([q for q in qs if q['repo']==repo],fn[name],'function'),
                      'file':metrics([q for q in qs if q['repo']==repo],file[name],'file')} for name in fn}
            for repo in manifest['by_repo']}
    assert all(r.sha(Path(p).read_bytes())==h for p,h in protected.items())
    assert all(r.sha((directory/p).read_bytes())==h for p,h in ledger_hashes.items())
    result={'manifest_sha256':r.MANIFEST_SHA,'function_primary_denominator':30,'function_partial_NA':20,
            'file_denominator':50,'metrics':reports,'by_repo':strata,'candidate_counts':candidate_counts,
            'function_rankings':fn,'file_rankings':file,'ledger_audit_sha256':r.sha((OUT/'ledger-audit.json').read_bytes()),
            'evaluation_script_sha256':r.sha(Path(__file__).read_bytes()),'network_requests_during_scoring':0,
            'file_projection':'best ranked function per file','gold_limitation':'static patch overlap proxy, not causal truth',
            'parameters':'BM25 lucene1.5/.75 english positive-only; dense exact cosine max-entity; RRF60 dense2/BM251; lexical ties'}
    (OUT/'results.json').write_bytes(r.canonical(result))
    print(json.dumps({'audit':{k:v for k,v in audit.items() if k!='ledger_hashes'},'metrics':reports,'output':str(OUT)},indent=2))


if __name__=='__main__':main()
