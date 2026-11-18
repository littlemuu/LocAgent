"""Reproducible synthetic end-to-end SDK exercise. Output must be a new directory."""
import argparse,json
from pathlib import Path
from readonly_agent.core import Snapshot,encoded
from .config import RetrievalConfig
from .corpus import Corpus
from .vectors import make_synthetic_cache
from .bridge import ProcessRetriever
from .sdk_adapter import run_offline

QUERY='remove stale cache entries'
FILES={'cache.py':'def purge_cache(entries):\n    """Remove stale cache entries."""\n    return {k: v for k, v in entries.items() if v is not None}\n\ndef reset_state(state):\n    return {}\n','render.py':'def render_value(value):\n    return str(value)\n'}
def response(name,args,identifier='call'):
    return {'stop_reason':'tool_use','content':[{'type':'tool_use','id':identifier,'name':name,'input':args}]}
def fixture(root,config):
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    for path,text in FILES.items():(root/path).write_text(text)
    snapshot=Snapshot(root,list(FILES));corpus=Corpus(snapshot,config.max_chars)
    vectors={d.id:([1.,0.] if d.entity.endswith(':purge_cache') else [0.,1.]) for d in corpus.documents}
    cache=make_synthetic_cache(corpus,config,vectors,{QUERY:[1.,0.]})
    return snapshot,cache

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--retrieval-python',required=True);args=p.parse_args()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    config=RetrievalConfig();snapshot,cache=fixture(out/'source',config)
    retriever=ProcessRetriever(snapshot,config,python=args.retrieval_python,cache=cache)
    script=[response('locagent_retrieve',{'query':QUERY,'offset':0},'search'),response('read_file',{'path':'cache.py','start_line':1,'end_line':4},'read'),response('finish',{'files':['cache.py'],'entities':['cache.py:purge_cache'],'answer':'Synthetic protocol fixture: inspect purge_cache; this is not a model quality result.'},'finish')]
    result=run_offline(snapshot=snapshot,issue=QUERY,script=script,output_dir=out/'sdk',retriever=retriever)
    assert result['status']=='completed' and result['worker_calls']==1 and result['retrieval_audit'][0]['executed_mode']=='hybrid'
    events=[json.loads(line) for line in (out/'sdk/trace.jsonl').read_text().splitlines()]
    requests=[e for e in events if e['event']=='request']
    assert 'cache.py:purge_cache' in json.dumps(requests[1]['request']['messages'])
    summary={'status':'completed','actual_sdk_dispatch':True,'hybrid_evidence_in_next_request':True,'synthetic_embeddings_only':True,'scripted_llm':True,'quality_measured':False,'real_llm_requests':0,'real_embedding_requests':0,'source_bytes':result['source_bytes'],'worker_calls':result['worker_calls'],'sdk_requests':result['requests']}
    (out/'acceptance.json').write_bytes(encoded(summary));print(json.dumps(summary))
if __name__=='__main__':main()
