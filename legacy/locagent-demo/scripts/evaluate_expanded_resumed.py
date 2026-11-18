"""Offline audit and scoring of original successes plus explicitly resumed attempts."""
import collections,importlib.metadata,json,math,socket,sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from locagent_service import bailian_expanded_resume as s
from locagent_service import bailian_expanded_runner as r
from locagent_service.bailian_response import validate_response
from offline_bailian_rrf import entity_ranking,rrf
from evaluate_expanded_live import metrics,blocked
OUT=ROOT/'outputs/bailian-expanded50-resumed-evaluation-20261016-r01'


def main():
    socket.socket.connect=blocked;socket.create_connection=blocked
    plan,directory,binding,base=s.spec()
    if not (directory/s.AUTH_NAME).is_file():raise RuntimeError('No continuation evidence')
    OUT.mkdir(mode=0o700)
    m=json.loads(r.FROZEN.read_bytes())
    protected=json.loads((ROOT/'outputs/bailian-expanded-live-preflight-20261016/audit.json').read_bytes())['protected_hashes']
    assert all(r.sha(Path(p).read_bytes())==h for p,h in protected.items())
    with r.locked(directory):
        ledger=s._AttemptLedger(directory,plan[490:],binding,original_names=base['ledger_hashes'])
        # No recover: audit never changes budget or attempts.
        states=dict(collections.Counter(row['state'] for row in ledger.rows.values()))
        totals=ledger.balance();physical=sum(e['data']['phase']=='dispatch' for e in ledger.events)
        new_tokens=sum(row.get('tokens',0) for row in ledger.rows.values())
        ledger_hashes={p.name:r.sha(p.read_bytes()) for p in directory.iterdir() if p.is_file() and p.name!='lock'}
        result={'status':'complete' if states=={'settled':128} else 'stopped_incomplete','run_id':r.RUN_ID,
                'manifest_sha256':r.MANIFEST_SHA,'resume_approval_id':s.RESUME_APPROVAL,
                'new_requests':physical,'cumulative_physical_requests':491+physical,
                'original_success_batches':490,'continuation_states':states,'original_failed_attempt_unknown_retained':True,
                'original_usage_tokens':base['actual_tokens_validated'],'continuation_usage_tokens':new_tokens,
                'total_validated_usage_tokens':base['actual_tokens_validated']+new_tokens,
                'new_usage_cost_cny':str(totals['spent']-s.BASE_SPENT),
                **{k+'_cny':str(v) for k,v in totals.items()},
                'remaining_reserved_cny':str(totals['unknown']+totals['inflight']),
                'cumulative_run_cost_upper_bound_cny':str(sum(totals.values())),
                'cumulative_cap_cny':'2','old_historical_held_cny':'1.277952',
                'combined_upper_bound_cny':str(Decimal('1.277952')+sum(totals.values())),
                'cost_basis':'provider usage x fixed rate, no invoice/free-credit reconciliation',
                'ledger_hashes':ledger_hashes,'original_ledger_unchanged':True,'protected_files_unchanged':len(protected),
                'resume_engine_sha256':binding['resume_engine_sha256'],'evaluation_script_sha256':r.sha(Path(__file__).read_bytes())}
        (OUT/'ledger-audit.json').write_bytes(r.canonical(result))
        if result['status']!='complete':
            print(json.dumps({k:v for k,v in result.items() if k!='ledger_hashes'},indent=2));return
        vectors={};sources=[]
        for i,item in enumerate(plan):
            if i<490:
                name=f'body-{i:06d}.bin';status=200
            else:
                name=f'continuation-body-{i:06d}.bin';status=ledger.rows[i]['http_status']
            raw=r.secure_read(directory/name)
            assert r.sha(raw)==ledger_hashes[name]
            values,tokens,_=validate_response(raw,len(item['ids']),status)
            if i>=490:assert tokens==ledger.rows[i]['tokens']
            for ident,value in zip(item['ids'],values):
                key=(item['role'],ident);assert key not in vectors;vectors[key]=value
            sources.append({'original_batch':i,'role':item['role'],'inputs':len(item['ids']),
                            'request_sha256':item['body_sha256'],'response_file':name,'response_sha256':r.sha(raw),'usage_tokens':tokens})
    assert len(vectors)==9864
    import bm25s
    import Stemmer
    assert m['package_versions']=={name:importlib.metadata.version(name) for name in m['package_versions']}
    members={}
    for key,doc in m['unique_documents'].items():
        for member in doc['members']:
            assert member not in members or members[member]==key
            members[member]=key
    snaps={(snap['repo'],snap['commit']):snap for snap in m['snapshots']}
    functions={name:{} for name in ('bm25','dense','rrf60_dense2')};files={name:{} for name in functions};counts={}
    for q in m['queries']:
        snap=snaps[(q['repo'],q['commit'])];docs=[];keys=[]
        for member in snap['document_ids']:
            key=members[member];text=m['unique_documents'][key]['text'];keys.append(key)
            docs.append({'entity':text.split('\n',1)[0],'text':text})
        counts[q['id']]=len(docs)
        stemmer=Stemmer.Stemmer('english');bm=bm25s.BM25(k1=1.5,b=.75,method='lucene')
        bm.index(bm25s.tokenize([d['text'] for d in docs],stemmer=stemmer,stopwords='en',show_progress=False),show_progress=False)
        ids,scores=bm.retrieve(bm25s.tokenize(q['text'],stemmer=stemmer,stopwords='en',show_progress=False),k=len(docs),show_progress=False)
        ordered=[0.]*len(docs)
        for i,score in zip(ids[0],scores[0]):ordered[int(i)]=float(score)
        lexical,_=entity_ranking(docs,ordered,True)
        query=vectors[('query',q['id'])]
        dense,_=entity_ranking(docs,[math.fsum(a*b for a,b in zip(query,vectors[('document',key)])) for key in keys])
        hybrid,_=rrf(lexical,dense,k=60,bm25_weight=1,dense_weight=2)
        for name,ranking in [('bm25',lexical),('dense',dense),('rrf60_dense2',hybrid)]:
            functions[name][q['id']]=ranking;files[name][q['id']]=list(dict.fromkeys(e.split(':',1)[0] for e in ranking))
    old_bm=json.loads((ROOT/'outputs/bailian-expanded50-live-evaluation-20261016-r01/bm25-only-results.json').read_bytes())
    assert functions['bm25']==old_bm['function_rankings'] and files['bm25']==old_bm['file_rankings']
    qs=m['queries']
    reports={name:{'function_primary':metrics(qs,functions[name],'function'),'file':metrics(qs,files[name],'file')} for name in functions}
    by_repo={repo:{name:{'function_primary':metrics([q for q in qs if q['repo']==repo],functions[name],'function'),
                        'file':metrics([q for q in qs if q['repo']==repo],files[name],'file')} for name in functions} for repo in m['by_repo']}
    assert reports['bm25']==old_bm['bm25']
    assert all(r.sha((directory/name).read_bytes())==h for name,h in ledger_hashes.items())
    assert all(r.sha(Path(p).read_bytes())==h for p,h in protected.items())
    assert s.baseline()==base
    scored={'status':'complete','manifest_sha256':r.MANIFEST_SHA,'metrics':reports,'by_repo':by_repo,
            'function_primary_denominator':30,'function_partial_NA':20,'file_denominator':50,
            'function_rankings':functions,'file_rankings':files,'candidate_counts':counts,'vector_sources':sources,
            'vectors_reused':7840,'new_vectors':2024,'total_document_vectors':9814,'total_query_vectors':50,
            'original_bm25_rankings_exact_match':True,'network_requests_during_scoring':0,
            'ledger_audit_sha256':r.sha((OUT/'ledger-audit.json').read_bytes()),
            'evaluation_script_sha256':r.sha(Path(__file__).read_bytes()),
            'parameters':'BM25 lucene1.5/.75 English positive-only; dense exact cosine; max entity; RRF60 dense2/BM251; lexical ties; file best function projection'}
    (OUT/'results.json').write_bytes(r.canonical(scored))
    print(json.dumps({'audit':{k:v for k,v in result.items() if k!='ledger_hashes'},'metrics':reports,'output':str(OUT)},indent=2))

if __name__=='__main__':main()
