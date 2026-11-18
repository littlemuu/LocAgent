"""Frozen BM25-only baseline after halted real run. Never fabricate dense results."""
import json
from pathlib import Path
import socket
import sys
import importlib.metadata
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from locagent_service import bailian_expanded_runner as r
from evaluate_expanded_live import metrics,OUT,blocked
from offline_bailian_rrf import entity_ranking


def main():
    socket.socket.connect=blocked;socket.create_connection=blocked
    r.load_plan(r.FROZEN,ROOT)
    m=json.loads(r.FROZEN.read_bytes())
    import bm25s
    import Stemmer
    assert m['package_versions']=={name:importlib.metadata.version(name) for name in m['package_versions']}
    members={member:key for key,doc in m['unique_documents'].items() for member in doc['members']}
    snaps={(s['repo'],s['commit']):s for s in m['snapshots']}
    fn={};files={};counts={}
    for q in m['queries']:
        texts=[m['unique_documents'][members[i]]['text'] for i in snaps[(q['repo'],q['commit'])]['document_ids']]
        docs=[{'entity':t.split('\n',1)[0],'text':t} for t in texts]
        counts[q['id']]=len(docs)
        stemmer=Stemmer.Stemmer('english');bm=bm25s.BM25(k1=1.5,b=.75,method='lucene')
        bm.index(bm25s.tokenize(texts,stemmer=stemmer,stopwords='en',show_progress=False),show_progress=False)
        ids,scores=bm.retrieve(bm25s.tokenize(q['text'],stemmer=stemmer,stopwords='en',show_progress=False),k=len(docs),show_progress=False)
        ordered=[0.]*len(docs)
        for i,score in zip(ids[0],scores[0]):ordered[int(i)]=float(score)
        ranking,_=entity_ranking(docs,ordered,True)
        fn[q['id']]=ranking;files[q['id']]=list(dict.fromkeys(e.split(':',1)[0] for e in ranking))
    result={'experiment_status':'halted_real_embedding_incomplete','manifest_sha256':r.MANIFEST_SHA,
            'bm25':{'function_primary':metrics(m['queries'],fn,'function'),'file':metrics(m['queries'],files,'file')},
            'dense':None,'rrf60_dense2':None,'reason':'query vectors absent and document corpus incomplete; no comparable dense/RRF scores',
            'candidate_counts':counts,'function_rankings':fn,'file_rankings':files,
            'function_primary_denominator':30,'function_partial_NA':20,'file_denominator':50,
            'script_sha256':r.sha(Path(__file__).read_bytes()),'metrics_script_sha256':r.sha((ROOT/'scripts/evaluate_expanded_live.py').read_bytes()),
            'network_requests':0,'parameters':'BM25 lucene k1=1.5 b=.75 English stemming positive-only; max entity; lexical ties; file best function projection'}
    with (OUT/'bm25-only-results.json').open('xb') as f:f.write(r.canonical(result))
    print(json.dumps({k:result[k] for k in ('experiment_status','bm25','dense','rrf60_dense2','reason')},indent=2))

if __name__=='__main__':main()
