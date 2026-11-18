"""Independent offline review: no production ledger/response/ranking/metric helpers.

Uses the frozen BM25 library/tokenizer, but direct score API, separate aggregation,
raw-vector parsing, RRF and Fraction macro metrics. Original artifacts read-only.
"""
from collections import Counter
from decimal import Decimal
from fractions import Fraction
import hashlib,importlib.metadata,json,math,socket
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/bailian-expanded50-20261016'
RUN=ROOT/'outputs/bailian-expanded-budget-runs/bailian-expanded50-78e24794-cap2-20261016-r01'
RESULT=ROOT/'outputs/bailian-expanded50-resumed-evaluation-20261016-r01'
OUT=ROOT/'outputs/bailian-expanded50-independent-review-20261016'
PIN='78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b'

def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()
def read(p):return json.loads(p.read_bytes())
def block(*a,**kw):raise RuntimeError('Independent review forbids network')


def audit_attempts(m):
    output={};states=[];fees=Decimal(0);held=Decimal(0);tokens=0
    audit=read(RESULT/'ledger-audit.json')
    assert all(sha((RUN/name).read_bytes())==h for name,h in audit['ledger_hashes'].items())
    for prefix,auth,field,start,end in [('', 'run.json','request',0,491),
                                       ('continuation-','continuation-authorization.json','batch_index',490,618)]:
        prev=sha((RUN/auth).read_bytes());attempts={}
        paths=sorted(RUN.glob(prefix+'event-*.json'))
        for seq,path in enumerate(paths):
            assert path.name==f'{prefix}event-{seq:06d}.json'
            record=read(path);assert record['sequence']==seq and record['previous']==prev
            prev=sha(canonical(record));event=record['data'];i=event[field]
            attempts.setdefault(i,[]).append(event)
        assert list(attempts)==list(range(start,end))
        for i,events in attempts.items():
            phases=[e['phase'] for e in events]
            assert phases[:3]==['reserved','dispatch','raw'] and len(phases)==4
            item=m['planned_requests'][i];reserve,dispatch,response,final=events
            assert reserve['n']==len(item['ids'])<=16
            request_hash=reserve['request_sha256'] if prefix else reserve['body_sha256']
            assert request_hash==item['body_sha256']==sha(canonical(item['body']))
            if prefix:assert reserve['physical_attempt_index']==i+1
            raw=(RUN/f'{prefix}body-{i:06d}.bin').read_bytes()
            assert sha(raw)==response['response_sha256']
            data=json.loads(raw)
            if final['phase']=='unknown':
                assert not prefix and i==490 and response['http_status']==403 and 'usage' not in data
                held+=Decimal(reserve['n']*131072)*Decimal('.125')/1000000
            else:
                assert final['phase']=='settled' and response['http_status']==200
                usage=data['usage'];n=usage['total_tokens']
                assert type(n) is int and 0<n<=len(item['ids'])*131072
                assert type(usage['prompt_tokens']) is int and usage['prompt_tokens']==n==final['tokens']
                fee=Decimal(n)*Decimal('.125')/1000000
                assert Decimal(final['cost_cny'])==fee and final['response_sha256']==sha(raw)
                assert i not in output
                entries=data['output']['embeddings'];indexed={}
                assert len(entries)==len(item['ids'])
                for entry in entries:
                    indices=[entry[k] for k in ('index','text_index') if k in entry]
                    assert indices and all(type(v) is int for v in indices) and len(set(indices))==1
                    index=indices[0];assert 0<=index<len(entries) and index not in indexed
                    vector=entry['embedding'];assert len(vector)==1024
                    assert all(type(v) in (int,float) and math.isfinite(v) for v in vector)
                    norm=math.hypot(*vector);assert math.isfinite(norm) and norm>0
                    indexed[index]=tuple(v/norm for v in vector)
                output[i]=[indexed[j] for j in range(len(entries))];fees+=fee;tokens+=n
            states.append((i,final['phase']))
    assert Counter(state for _,state in states)=={'settled':618,'unknown':1}
    assert Counter(i for i,_ in states)==Counter({i:2 if i==490 else 1 for i in range(618)})
    assert set(output)==set(range(618))
    assert fees==Decimal('0.227484') and held==Decimal('0.262144') and tokens==1819872
    # Replay the actual economic event order; every new reserve includes old hold.
    spent=Decimal(0);pending={};unknown={};peak=Decimal(0)
    for prefix,field in [('', 'request'),('continuation-','batch_index')]:
        for path in sorted(RUN.glob(prefix+'event-*.json')):
            e=read(path)['data'];key=(prefix,e[field])
            if e['phase']=='reserved':
                amount=Decimal(e['n']*131072)*Decimal('.125')/1000000
                exposure=spent+sum(pending.values(),Decimal(0))+sum(unknown.values(),Decimal(0))+amount
                assert exposure<=2;peak=max(peak,exposure);pending[key]=amount
            elif e['phase']=='settled':spent+=Decimal(e['cost_cny']);pending.pop(key)
            elif e['phase']=='unknown':unknown[key]=pending.pop(key)
    assert not pending and spent==fees and sum(unknown.values())==held
    return output,{'physical_attempts':len(states),'successes':len(output),'unknown':1,'validated_tokens':tokens,
                   'usage_cost_cny':str(fees),'unknown_reserved_cny':str(held),'upper_bound_cny':str(fees+held),
                   'peak_exposure_cny':str(peak),'cap_invariant_all_reservations':True,'only_retried_original_batch':490}


def collapse(entities,scores,positive=False):
    maximum={}
    for entity,score in zip(entities,scores):
        score=float(score);assert math.isfinite(score)
        if positive and score<=0:continue
        if entity not in maximum or score>maximum[entity]:maximum[entity]=score
    return sorted(maximum,key=lambda name:(-maximum[name],name))


def rank_without_gold(queries,snapshots,documents,members,vectors):
    import bm25s
    import Stemmer
    rankings={arm:{} for arm in ('bm25','dense','rrf60_dense2')};counts={}
    for query in queries:
        assert set(query)=={'id','text','repo','commit'}
        selected=snapshots[(query['repo'],query['commit'])]['document_ids']
        keys=[members[member] for member in selected]
        texts=[documents[key]['text'] for key in keys];entities=[text.partition('\n')[0] for text in texts]
        counts[query['id']]=len(selected)
        stem=Stemmer.Stemmer('english');index=bm25s.BM25(k1=1.5,b=.75,method='lucene')
        index.index(bm25s.tokenize(texts,stemmer=stem,stopwords='en',show_progress=False),show_progress=False)
        terms=bm25s.tokenize(query['text'],stemmer=stem,stopwords='en',return_ids=False,show_progress=False)[0]
        lexical=collapse(entities,index.get_scores(terms) if terms else [0.]*len(texts),True)
        qv=vectors[('query',query['id'])]
        cosine=[math.fsum(x*y for x,y in zip(qv,vectors[('document',key)])) for key in keys]
        dense=collapse(entities,cosine)
        fused={}
        for ranking,weight in ((lexical,1),(dense,2)):
            for pos,entity in enumerate(ranking,1):fused[entity]=fused.get(entity,0.)+weight/(60+pos)
        hybrid=sorted(fused,key=lambda name:(-fused[name],name))
        for arm,ranking in [('bm25',lexical),('dense',dense),('rrf60_dense2',hybrid)]:rankings[arm][query['id']]=ranking
    return rankings,counts


def exact_metrics(queries,rankings,scope):
    eligible=[q for q in queries if scope=='file' or q['function_primary_eligible']]
    result={}
    for k in (1,3,5):
        hits=0;recall=Fraction(0)
        for q in eligible:
            gold=set(q[scope+'_gold']);assert gold
            found=len(gold.intersection(rankings[q['id']][:k]));hits+=int(found>0);recall+=Fraction(found,len(gold))
        result[str(k)]={'hit':float(Fraction(hits,len(eligible))) if eligible else None,
                        'recall':float(recall/len(eligible)) if eligible else None,'denominator':len(eligible)}
    return result


def main():
    socket.socket.connect=block;socket.create_connection=block
    OUT.mkdir(mode=0o700)
    before={str(p):sha(p.read_bytes()) for folder in (RESULT,RUN,BASE/'frozen') for p in folder.iterdir() if p.is_file() and p.name!='lock'}
    raw=(BASE/'frozen/manifest.json').read_bytes();assert sha(raw)==PIN
    m=json.loads(raw);saved=read(RESULT/'results.json')
    assert m['policy']['metrics']=='fixed BM25,dense,RRF60 dense2:BM251; max entity; lexical ties; k1=1.5 b=.75 english; K1/3/5; multi-gold macro Hit and Recall distinct; partial function gold NA, file metric separate; missing results eligible=>0; report repo, symbol hint, gold multiplicity and query source/history certainty'
    assert m['package_versions']=={name:importlib.metadata.version(name) for name in m['package_versions']}
    assert len(m['queries'])==50 and sum(q['function_primary_eligible'] for q in m['queries'])==30
    raw_vectors,finances=audit_attempts(m);vectors={}
    for batch,item in enumerate(m['planned_requests']):
        expected=[m['unique_documents'][i]['text'] for i in item['ids']] if item['role']=='document' else [next(q['text'] for q in m['queries'] if q['id']==i) for i in item['ids']]
        assert item['body']['input']['texts']==expected and item['body']['model']==m['model']
        assert item['body']['parameters']==(m['document_parameters'] if item['role']=='document' else m['parameters'])
        for ident,vector in zip(item['ids'],raw_vectors[batch]):
            key=(item['role'],ident);assert key not in vectors;vectors[key]=vector
    assert Counter(role for role,_ in vectors)=={'document':9814,'query':50}
    members={}
    for key,doc in m['unique_documents'].items():
        assert sha(doc['text'].encode())==key
        for member in doc['members']:
            assert member not in members or members[member]==key;members[member]=key
    snapshots={(s['repo'],s['commit']):s for s in m['snapshots']};assert len(snapshots)==49
    for (repo,commit),snapshot in snapshots.items():
        cache=read(BASE/'snapshots'/(repo.replace('/','__')+'-'+commit+'.json'))
        assert [d['id'] for d in cache['documents']]==snapshot['document_ids']
        for d in cache['documents']:
            text=m['unique_documents'][members[d['id']]]['text']
            assert text==d['text'] and text.partition('\n')[0]==d['entity']
    clean=[{key:q[key] for key in ('id','text','repo','commit')} for q in m['queries']]
    functions,counts=rank_without_gold(clean,snapshots,m['unique_documents'],members,vectors)
    files={arm:{qid:list(dict.fromkeys(entity.split(':',1)[0] for entity in rows)) for qid,rows in byq.items()} for arm,byq in functions.items()}
    assert functions==saved['function_rankings'] and files==saved['file_rankings'] and counts==saved['candidate_counts']
    reports={arm:{'function_primary':exact_metrics(m['queries'],functions[arm],'function'),'file':exact_metrics(m['queries'],files[arm],'file')} for arm in functions}
    maxdiff=0.
    for arm in reports:
        for scope in reports[arm]:
            for k,values in reports[arm][scope].items():
                old=saved['metrics'][arm][scope][k];assert old['denominator']==values['denominator']
                for metric in ('hit','recall'):
                    diff=abs(old[metric]-values[metric]);maxdiff=max(maxdiff,diff);assert diff<1e-12
    for repo in m['by_repo']:
        qs=[q for q in m['queries'] if q['repo']==repo]
        for arm in functions:
            for scope,rankings,name in [('function',functions,'function_primary'),('file',files,'file')]:
                computed=exact_metrics(qs,rankings[arm],scope)
                for k,row in computed.items():
                    old=saved['by_repo'][repo][arm][name][k];assert row['denominator']==old['denominator']
                    for metric in ('hit','recall'):assert row[metric] is None and old[metric] is None or abs(row[metric]-old[metric])<1e-12
    assert all(sha(Path(p).read_bytes())==h for p,h in before.items())
    result={'review':'passed','manifest_sha256':PIN,'independent_reimplementation':True,
            'shared_dependency':'frozen bm25s/PyStemmer tokenizer and scoring implementation; direct get_scores API, no original ranking/metric/ledger helpers',
            'function_rank_lists_exact_match':150,'file_rank_lists_exact_match':150,
            'exact_fraction_metric_max_float_difference':maxdiff,'metrics':reports,
            'function_primary':30,'partial_NA':20,'file_denominator':50,'isolated_snapshots':49,'repositories':9,
            'document_vectors':9814,'query_vectors':50,'gold_removed_before_retrieval':True,
            'fixed_manifest_policy_verified':True,'finances':finances,'original_artifacts_unchanged':True,
            'network_requests':0,'script_sha256':sha(Path(__file__).read_bytes()),'input_hashes':before}
    (OUT/'review.json').write_bytes(canonical(result))
    print(json.dumps({k:v for k,v in result.items() if k not in ('input_hashes','metrics')},indent=2))

if __name__=='__main__':main()
