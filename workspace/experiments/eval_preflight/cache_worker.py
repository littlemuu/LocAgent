"""Frozen source-only cache bridge / native loop connectivity. Offline only."""
import contextlib,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];ENGINE=ROOT/'engine_adaptation/v4/engine'
sys.path[:0]=[str(ROOT),str(ENGINE)]
from readonly_agent.core import Snapshot,encoded
from readonly_agent.locagent import LocAgentRetriever
from locagent_service.offline import offline_engine
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 req=json.load(sys.stdin)
 assert req['case']=='tobymao__sqlglot-3417'
 manifest_path=ROOT/'engine_adaptation/v4/adapted-manifest.json'
 assert sha(manifest_path)==req['adapted_manifest_sha256']
 manifest=json.loads(manifest_path.read_text())
 assert all(sha(ENGINE/n)==h for n,h in manifest['engine']['files'].items())
 assert all(sha(ROOT/n)==h for n,h in manifest['harness_files'].items())
 item=next(x for x in manifest['cases'] if x['id']==req['case'])
 plan=json.loads((ROOT/'engine_adaptation/v4/plans'/ (req['case']+'.json')).read_text())
 assert plan['plan_hash']==item['plan_hash']
 snapshot=Snapshot(plan['source_root'],list(plan['sources']),hidden_python_paths=plan['hidden_python_paths'])
 assert dict(snapshot.hashes)==plan['sources'] and snapshot.identity==req['snapshot']==item['source_snapshot']
 att=Path(item['index_attestation']);assert sha(att)==req['attestation_sha256']
 artifacts=json.loads(att.read_text())['artifacts'];index=Path(item['index_directory']);graph_path=index.parent/'graph.json'
 assert all(sha(index.parent/n)==h for n,h in artifacts.items())
 with contextlib.redirect_stdout(sys.stderr),offline_engine():
  import networkx as nx
  from plugins.location_tools.retriever.bm25_retriever import build_retriever_from_persist_dir
  raw=json.loads(graph_path.read_text());assert raw['schema']=='locagent-source-graph-v1'
  graph=nx.MultiDiGraph()
  for n,d in raw['nodes']:graph.add_node(n,**d)
  for a,b,k,d in raw['edges']:graph.add_edge(a,b,key=k,**d)
  retriever=LocAgentRetriever(snapshot,graph);persisted=build_retriever_from_persist_dir(str(index))
  corpus=lambda r:[json.loads(v['_node_content'])['text'] for v in r.corpus]
  assert corpus(persisted)==corpus(retriever._lexical);retriever._lexical=persisted
  if req['mode']=='query':
   query=req['query'];assert isinstance(query,str) and 1<=len(query)<=256
   result={'snapshot':snapshot.identity,'text':retriever.retrieve(query),'cache_loaded':True}
  else:
   from util.localizer import GraphLocalizer
   from util.localization_contract import LocalizationRequest,LocalizationOptions
   from litellm import ModelResponse
   calls=[];path=sorted(snapshot.files)[0]
   def provider(**kw):
    assert len(calls)<4;calls.append(kw)
    name='finish' if len(calls)==4 else 'get_entity_contents'
    args={'files':[],'entities':[]} if name=='finish' else {'entity_names':[path]}
    return ModelResponse(choices=[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
      'tool_calls':[{'id':'mock'+str(len(calls)),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}],
      usage={'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100})
   engine=GraphLocalizer.from_graph(graph,provider=provider,model_name='deepseek-flash',
    options=LocalizationOptions(max_iterations=4,search_protocol='bounded-v1'),module_retriever=persisted)
   output=engine.localize(LocalizationRequest(req['case'],'tobymao/sqlglot',plan['commit'],req['issue']))
   result={'native_result':output.to_dict(),'requests':calls,'cache_loaded':True,'simulation':True,'quality':None,
    'limitations':['source-body BM25 not connected','native protocol budgets not equivalent to OpenHands','no live transport/admission in this probe']}
 sys.stdout.buffer.write(encoded(result))
if __name__=='__main__':main()
