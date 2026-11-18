"""Evidence-bound assembly and exact in-memory retrieval; no transport or DB writes."""
import hashlib
import json
import math
import sqlite3
import time
from pathlib import Path
from locagent_service import bailian_contract as c
from locagent_service.bailian_response import validate_response
from locagent_service.bailian_experiment import metrics

RANKING={'bm25':'lucene','k1':1.5,'b':0.75,'stemmer':'english','stopwords':'en',
         'lexical_candidates':'positive-score-only','entity_aggregation':'max-chunk-score',
         'dense':'exact-normalized-dot-fsum','tie_break':'entity-lexicographic',
         'hybrid':'RRF-positive-BM25-and-all-dense','rrf_k':60,'cutoffs':[1,3,5],
         'missing_query_score':0,'quality_pass_threshold':None}


def sha(raw):return hashlib.sha256(raw).hexdigest()


def verify_response(raw,binding,manifest_hash,request,ledger):
    if binding['manifest_sha256']!=manifest_hash or binding['request_sha256']!=request['sha256'] or sha(request['body'])!=request['sha256']:
        raise ValueError('Request or manifest binding mismatch')
    if binding['response_sha256']!=sha(raw) or binding['http_status']!=200:
        raise ValueError('Raw response binding mismatch')
    if ledger!=('settled',request['sha256'],sha(raw)):
        raise ValueError('Source ledger not settled or mismatched')
    values,tokens,audit=validate_response(raw,request['count'],200)
    return values,tokens


def load_response(folder,index,manifest,request):
    folder=Path(folder)
    names=['manifest.json','ledger.sqlite',f'response-{index:03d}.body.bin',f'response-{index:03d}.binding.json']
    if folder.is_symlink() or any((folder/name).is_symlink() for name in names):raise ValueError('Evidence symlink rejected')
    if (folder/'manifest.json').read_bytes()!=c.canonical(manifest):raise ValueError('Source manifest changed')
    raw=(folder/names[2]).read_bytes();binding=json.loads((folder/names[3]).read_bytes())
    with sqlite3.connect('file:'+str(folder/'ledger.sqlite')+'?mode=ro&immutable=1',uri=True) as db:
        row=db.execute('SELECT state,request_hash,response_hash FROM calls WHERE id=?',(index,)).fetchone()
    values,tokens=verify_response(raw,binding,sha(c.canonical(manifest)),request,row)
    return values,{'source_folder':str(folder),'request_index':index,'role':request['role'],
                   'ids':request['ids'],'binding':binding,'tokens':tokens}


def cached_request(source,target,doc,index):
    for field in ('endpoint','model','dimensions','document_parameters'):
        if source[field]!=target[field]:raise ValueError('Cached model/endpoint/role parameters mismatch')
    if source['document_parameters']!=c.request(['x'],'document')['parameters']:
        raise ValueError('Document/query cache isolation violated')
    if source['documents'][index]!=doc:raise ValueError('Cached input identity changed')
    body=c.canonical(c.request([doc['text']],'document'))
    return {'role':'document','ids':[doc['id']],'count':1,'body':body,'sha256':sha(body)}


def assemble(manifest,parts):
    expected={(role,row['id']) for role,field in [('document','documents'),('query','questions')] for row in manifest[field]}
    if len(expected)!=len(manifest['documents'])+len(manifest['questions']):raise ValueError('Duplicate planned input')
    result={}
    for role,ids,values in parts:
        if len(ids)!=len(values):raise ValueError('Missing response inputs')
        for ident,value in zip(ids,values):
            key=(role,ident)
            if key not in expected or key in result:raise ValueError('Unknown, duplicate or wrong-role input')
            if len(value)!=1024 or any(type(x) not in (int,float) or not math.isfinite(x) for x in value) or not math.isclose(math.hypot(*value),1.,rel_tol=1e-10):
                raise ValueError('Invalid normalized vector')
            result[key]=value
    if set(result)!=expected:raise ValueError('Incomplete frozen membership')
    return result


def dense_rank(docs,values,query):
    best={}
    for doc in docs:
        score=math.fsum(x*y for x,y in zip(values[('document',doc['id'])],query))
        best[doc['entity']]=max(best.get(doc['entity'],-math.inf),score)
    return sorted(best,key=lambda entity:(-best[entity],entity))


def fuse(lexical,dense):
    scores={}
    for ranking in (lexical,dense):
        for rank,entity in enumerate(ranking,1):scores[entity]=scores.get(entity,0)+1/(60+rank)
    return sorted(scores,key=lambda entity:(-scores[entity],entity))


def evaluate(manifest,values):
    import bm25s
    import Stemmer
    started=time.monotonic();docs=manifest['documents'];qs=manifest['questions']
    stemmer=Stemmer.Stemmer('english');retriever=bm25s.BM25(k1=1.5,b=0.75,method='lucene')
    retriever.index(bm25s.tokenize([d['text'] for d in docs],stemmer=stemmer,stopwords='en',show_progress=False),show_progress=False)
    build=time.monotonic()-started;rankings={name:{} for name in ('bm25','dense','hybrid')};times={};per_query={}
    for q in qs:
        t=time.monotonic()
        indices,scores=retriever.retrieve(bm25s.tokenize(q['text'],stemmer=stemmer,stopwords='en',show_progress=False),k=len(docs),show_progress=False)
        best={}
        for index,score in zip(indices[0],scores[0]):
            entity=docs[int(index)]['entity']
            if score>0:best[entity]=max(best.get(entity,0),float(score))
        lexical=sorted(best,key=lambda e:(-best[e],e));lex_time=time.monotonic()-t
        t=time.monotonic();dense=dense_rank(docs,values,values[('query',q['id'])]);dense_time=time.monotonic()-t
        t=time.monotonic();hybrid=fuse(lexical,dense);fusion_time=time.monotonic()-t
        times[q['id']]={'bm25_seconds':lex_time,'dense_seconds':dense_time,'rrf_fusion_only_seconds':fusion_time,'hybrid_total_seconds':lex_time+dense_time+fusion_time}
        per_query[q['id']]={}
        for name,ranking in [('bm25',lexical),('dense',dense),('hybrid',hybrid)]:
            rankings[name][q['id']]=ranking
            per_query[q['id']][name]={str(k):metrics([q],{q['id']:ranking},k) for k in (1,3,5)}
    return {'rankings':rankings,'per_query':per_query,'metrics':{name:{str(k):metrics(qs,ranking,k) for k in (1,3,5)} for name,ranking in rankings.items()},
            'timing':{'bm25_build_seconds':build,'per_query':times,'evaluation_total_seconds':time.monotonic()-started},
            'single_gold_hit_equals_recall':all(len(q['relevant_entities'])==1 for q in qs),
            'development_set_not_blind':True,'quality_pass_threshold':None,'generation_calls':0,
            'numeric_stability':'independent observation; previous frozen experiment remains inconclusive'}
