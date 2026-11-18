"""Fresh-environment checks, source-only dev regression, and deterministic manifests."""
import hashlib,json,os,sys,unittest,time
from pathlib import Path
from contextlib import redirect_stdout,redirect_stderr
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from project_paths import ROOT,path,deny_historical_io
historical_attempts=deny_historical_io()
# Holdout artifacts are never needed by any development operation.
def deny_holdout(event,args):
    if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes,os.PathLike)):
        p=Path(os.fsdecode(args[0])).absolute()
        if (ROOT/'freezes/holdout-v1')==p or (ROOT/'freezes/holdout-v1') in p.parents:
            if sys.argv[1]!='verify':raise PermissionError('holdout_not_available_to_development')
sys.addaudithook(deny_holdout)
from readonly_agent.offline import no_network

def dump(p,value):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def registry():
    value=json.loads(path('dev_registry').read_text());return value['cases'] if isinstance(value,dict) else value

def cases():
    from readonly_agent.core import Snapshot
    from experiments.sdk_hybrid_v8.corpus import Corpus
    for entry in registry():
        source=ROOT/entry['source_root']
        for name,expected in entry['sources'].items():
            assert sha((source/name).read_bytes())==expected,(entry['id'],name)
        snap=Snapshot(source,list(entry['sources']),hidden_python_paths=entry['hidden_python_paths'])
        assert snap.identity==entry['snapshot'],entry['id']
        yield entry,snap,Corpus(snap)

def regression(out):
    from readonly_agent.core import digest,Limits
    from experiments.sdk_hybrid_v8.config import RetrievalConfig
    from experiments.sdk_hybrid_v8.vectors import make_synthetic_cache
    from experiments.sdk_hybrid_v8.bridge import ProcessRetriever
    from experiments.sdk_hybrid_v8.sdk_adapter import run_offline
    from experiments.sdk_hybrid_v8.demo import response
    cfg=RetrievalConfig();rows=[]
    def vec(text):
        raw=hashlib.sha256(text.encode()).digest();return [1+raw[0],1+raw[1]]
    for entry,snapshot,corpus in cases():
        q=entry['issue'];cache=make_synthetic_cache(corpus,cfg,{d.id:vec(d.text) for d in corpus.documents},{q:vec(q)})
        r=ProcessRetriever(snapshot,cfg,python=sys.executable,cache=cache)
        # Scripted actions exercise the real SDK; no gold answers, quality claims, or model calls.
        script=[response('locagent_retrieve',{'query':q,'offset':0},'query'),response('finish',{'files':[],'entities':[],'answer':'Offline plumbing regression only; no prediction.'},'finish')]
        result=run_offline(snapshot=snapshot,issue=q,script=script,output_dir=out/entry['id'],retriever=r,limits=Limits(max_requests=3))
        assert result['status']=='completed',(entry['id'],result.get('failure'))
        assert result['worker_calls']==1 and result['network_attempts']==0
        audit=result['retrieval_audit'][0];assert audit['query_hash']==sha(q.encode())
        assert audit['membership']==len(corpus.documents) and audit['executed_mode']=='hybrid'
        events=[json.loads(x) for x in (out/entry['id']/'trace.jsonl').read_text().splitlines()]
        requests=[e for e in events if e['event']=='request']
        assert 'Retrieval mode: hybrid' in json.dumps(requests[1]['request']['messages'])
        row={'id':entry['id'],'status':'passed','chunks':len(corpus.documents),'duplicate_entities':sum(len(n['definitions'])>1 for n in corpus.nodes.values()),'query_characters':len(q),'query_utf8_bytes':len(q.encode()),'source_bytes':result['source_bytes'],'sdk_requests':result['requests'],'worker_calls':1,'evidence_in_next_request':True}
        rows.append(row);print(entry['id'],'passed',flush=True)
    assert len(rows)==37
    return {'cases':rows,'passed':len(rows),'quality_measured':False,'synthetic_vectors':True,'scripted_llm':True,'real_llm_requests':0,'real_embedding_requests':0}

def encode(out):
    prior=path('verification')/'regression/summary.json'
    proof=json.loads(prior.read_text());assert proof['status']=='passed' and proof['passed']==37
    target=path('freezes')/'encoding-dev37-v8.1';target.mkdir(parents=True,exist_ok=False)
    documents={};queries=[];memberships=0;rows=[]
    for entry,snap,corpus in cases():
        q=entry['issue'];queries.append({'id':entry['id'],'sha256':sha(q.encode()),'text':q,'utf8_bytes':len(q.encode())})
        for d in corpus.documents:
            h=sha(d.text.encode());item=documents.setdefault(h,{'sha256':h,'text':d.text,'utf8_bytes':len(d.text.encode()),'members':[]})
            item['members'].append({'case':entry['id'],'document_id':d.id,'definition_id':d.definition_id,'entity':d.entity,'start':d.start,'end':d.end,'part':d.part});memberships+=1
        rows.append({'id':entry['id'],'snapshot':snap.identity,'corpus':corpus.identity,'chunks':len(corpus.documents)})
    for name,values in [('documents.jsonl',[documents[h] for h in sorted(documents)]),('queries.jsonl',queries)]:
        (target/name).write_text(''.join(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n' for v in values))
    manifest={'version':'encoding-dev37-v8.1','status':'inputs_frozen_not_encoded','cases':rows,'unique_documents':len(documents),'document_memberships':memberships,'unique_queries':len({q['sha256'] for q in queries}),'document_utf8_bytes':sum(x['utf8_bytes'] for x in documents.values()),'max_document_utf8_bytes':max(x['utf8_bytes'] for x in documents.values()),'max_query_utf8_bytes':max(x['utf8_bytes'] for x in queries),'query_contract':'exact_utf8_max16000_v1','text_policy':'entity + newline + original function source; all span-bound definitions preserved; max12000 Unicode code points per source chunk','provider_binding':'unbound: this is a text-input freeze, not a provider cache; provider model, revision, dimension, instructions and token limits must be separately pinned before encoding','regression_sha256':sha(prior.read_bytes()),'registry_sha256':sha(path('dev_registry').read_bytes()),'files':{p.name:sha(p.read_bytes()) for p in sorted(target.glob('*.jsonl'))},'paid_calls':0}
    dump(target/'manifest.json',manifest);return manifest

def verify(out):
    manifest=json.loads((ROOT/'freezes/stage1-lock.json').read_text())
    for relative,expected in manifest['files'].items():
        assert sha((ROOT/relative).read_bytes())==expected,relative
    return {'verified_files':len(manifest['files']),'lock_sha256':sha((ROOT/'freezes/stage1-lock.json').read_bytes())}

def main():
    mode=sys.argv[1];out=path('verification')/mode;out.mkdir(parents=True,exist_ok=False)
    passed=False;summary={};start=time.monotonic()
    with (out/'run.log').open('w') as log,TemporaryDirectory(prefix='locagent-offline-') as td:
        with redirect_stdout(log),redirect_stderr(log),no_network(Path(td)/'profiles') as network:
            os.environ['V8_LEGACY_ROOT']=str(path('legacy_reference'));os.environ['V8_RETRIEVAL_PYTHON']=sys.executable
            if mode=='test':
                suite=unittest.defaultTestLoader.discover(str(path('tests')))
                r=unittest.TextTestRunner(verbosity=2,stream=log).run(suite)
                summary={'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors)};passed=r.wasSuccessful()
            else:summary=globals()[mode](out);passed=True
    summary.update(status='passed' if passed and not network and not historical_attempts else 'failed',network_attempts=len(network),historical_path_attempts=historical_attempts,elapsed_seconds=round(time.monotonic()-start,3),real_llm_requests=0,real_embedding_requests=0)
    dump(out/'summary.json',summary);print(json.dumps({k:v for k,v in summary.items() if k not in ('cases','files')},ensure_ascii=False));raise SystemExit(0 if summary['status']=='passed' else 1)
if __name__=='__main__':main()
