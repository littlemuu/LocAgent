"""Evaluate identical frozen membership and queries, no model calls."""
from importlib.metadata import version as package_version
import json

from locagent_service.bailian_dataset import members
from locagent_service.bailian_experiment import metrics


def evaluate(manifest, journal, store):
    import bm25s
    import Stemmer
    from locagent_service.rag_postgres import BuildSpec
    from locagent_service.bailian_dataset import VERSION
    vectors={}
    with journal.db() as db:
        rows=journal.audit(db)
    if len(rows)!=len(journal.requests) or any(row[3]!='settled' for row in rows):
        raise ValueError('All planned responses must be settled before evaluation')
    for row,request in zip(rows,journal.requests):
        for ident,value in zip(request['ids'],json.loads(row[5])):
            vectors[ident]=value
    chunks=members({name:text.encode() for name,text in manifest['source_files'].items()})
    spec=BuildSpec(VERSION,1024,chunks)
    state=store.status(spec)
    if not state or state['state']!='ready':
        token=store.begin(spec)
        store.publish(spec,token,[vectors[ch.id] for ch in chunks])
    docs=manifest['documents']
    stemmer=Stemmer.Stemmer('english')
    retriever=bm25s.BM25(k1=1.5,b=0.75,method='lucene')
    retriever.index(bm25s.tokenize([doc['text'] for doc in docs],stemmer=stemmer,stopwords='en',show_progress=False),show_progress=False)
    rankings={name:{} for name in ('bm25','dense','hybrid')}
    for q in manifest['questions']:
        indices,scores=retriever.retrieve(bm25s.tokenize(q['text'],stemmer=stemmer,stopwords='en',show_progress=False),k=len(docs),show_progress=False)
        best={}
        for index,score in zip(indices[0],scores[0]):
            entity=docs[int(index)]['entity']
            if score>0:best[entity]=max(best.get(entity,0),float(score))
        lexical=sorted(best,key=lambda e:(-best[e],e))
        dense=[hit.chunk.path+':'+hit.chunk.entity for hit in store.query(spec,vectors[q['id']],len(docs))]
        fusion={}
        for ranking in (lexical,dense):
            for rank,entity in enumerate(ranking,1):fusion[entity]=fusion.get(entity,0)+1/(60+rank)
        hybrid=sorted(fusion,key=lambda e:(-fusion[e],e))
        for name,ranking in [('bm25',lexical),('dense',dense),('hybrid',hybrid)]:
            rankings[name][q['id']]=ranking
    return {'manifest_sha256':journal.identity,'build_identity':spec.identity,
            'package_versions':{name:package_version(name) for name in ('bm25s','PyStemmer','psycopg')},
            'rankings':rankings,'metrics':{name:{str(k):metrics(manifest['questions'],ranking,k) for k in (1,3,5)} for name,ranking in rankings.items()},
            'development_set_not_blind':True,'generation_calls':0}
