"""Offline v4 build or explicit v3 index revalidation; source code is never executed."""
import contextlib,hashlib,json,resource,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'engine_adaptation/v4/engine')]
from readonly_agent.core import Snapshot,encoded
from readonly_agent.locagent import LocAgentRetriever
from locagent_service.offline import offline_engine
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 req=json.load(sys.stdin);out=Path(req['output']);out.mkdir(exist_ok=False)
 resource.setrlimit(resource.RLIMIT_CPU,(90,90))
 resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,256*1024**2))
 with contextlib.redirect_stdout(sys.stderr),offline_engine(),tempfile.TemporaryDirectory() as tmp:
  from dependency_graph.build_graph import build_graph
  from plugins.location_tools.retriever.bm25_retriever import build_retriever_from_persist_dir,retrieve_nonempty
  import networkx as nx
  snapshot=Snapshot(req['source_root'],list(req['sources']),hidden_python_paths=req['hidden_python_paths'])
  assert dict(snapshot.hashes)==req['sources']
  bom=[n for n,s in snapshot.files.items() if s.startswith('\ufeff')]
  if req.get('reuse'):
   old=Path(req['reuse']);att=json.loads(Path(req['attestation']).read_text())
   assert att['exit_code']==0
   assert all(sha(old/n)==h for n,h in att['artifacts'].items())
   assert not bom, 'BOM sources require fresh construction'
   data=json.loads((old/'graph.json').read_text())
   assert data['schema']=='locagent-source-graph-v1'
   graph=nx.MultiDiGraph()
   for n,d in data['nodes']:graph.add_node(n,**d)
   for a,b,k,d in data['edges']:graph.add_edge(a,b,key=k,**d)
   mode='revalidated_v3_index';index=old/'entity-bm25'
  else:
   root=Path(tmp)
   for n,text in snapshot.files.items():
    p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.encode())
   graph=build_graph(str(root),global_import=True)
   (out/'graph.json').write_bytes(encoded({'schema':'locagent-source-graph-v1',
    'nodes':[[n,d] for n,d in graph.nodes(data=True)],'edges':[[a,b,k,d] for a,b,k,d in graph.edges(keys=True,data=True)]}))
   mode='rebuilt_v4';index=out/'entity-bm25'
  retriever=LocAgentRetriever(snapshot,graph)
  if mode=='rebuilt_v4':retriever._lexical.persist(str(index))
  loaded=build_retriever_from_persist_dir(str(index))
  texts=lambda corpus:[json.loads(v['_node_content'])['text'] for v in corpus]
  assert texts(loaded.corpus)==texts(retriever._lexical.corpus)
  ids=lambda r:[v.node.text for v in retrieve_nonempty(r,'__init__')]
  assert ids(loaded)==ids(retriever._lexical)
  hidden=[]
  for n in req['hidden_python_paths']:
   assert 'Found file `'+n+'`' in retriever.retrieve(n);hidden.append(n)
  for n in bom:assert graph.nodes[n]['code']==snapshot.files[n]
  if req['id']=='synthetic':
   from readonly_agent.bridge import LocAgentProcessRetriever
   from readonly_agent.core import FileTools
   bridge=LocAgentProcessRetriever(snapshot,python=sys.executable,engine_root=ROOT/'engine_adaptation/v4/engine')
   text=bridge.retrieve('bom_crlf.py:café')
   assert text==retriever.retrieve('bom_crlf.py:café') and '中' in text
   assert graph.nodes['bom_crlf.py:café']['start_line']==1
   assert graph.nodes['bom_crlf.py:café']['code']=='def café():\r\n    return "中\ufeff"'
   assert FileTools(snapshot).respond('read_file',{'path':'bom_crlf.py','start_line':1,'end_line':1},4096)['text'].startswith('1: \ufeffdef café')
   assert any(b.startswith('target.py') and d['type']=='imports' for a,b,d in graph.edges(data=True) if a=='bom_import.py')
  result={'id':req['id'],'status':'ready','mode':mode,'snapshot':snapshot.identity,'bom_files':bom,
   'nodes':len(graph),'files':len(snapshot.files),'index_directory':str(index),'hidden_queries_verified':hidden,
   'persisted_corpus_and_query_equal':True,'model_calls':0}
  (out/'result.json').write_bytes(encoded(result))
 print(json.dumps(result))
if __name__=='__main__':main()
