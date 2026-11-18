"""Frozen v4 loader; checks source/graph/index before any tool can use them."""
import contextlib,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];ENGINE=ROOT/'engine_adaptation/v4/engine'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(req):
 sys.path[:0]=[str(ROOT),str(ENGINE)]
 from readonly_agent.core import Snapshot,encoded
 from readonly_agent.locagent import LocAgentRetriever
 from locagent_service.offline import offline_engine
 assert req['case']=='tobymao__sqlglot-3417'
 manifest_path=ROOT/'engine_adaptation/v4/adapted-manifest.json'
 assert sha(manifest_path)==req['adapted_manifest_sha256']
 manifest=json.loads(manifest_path.read_text())
 assert all(sha(ENGINE/n)==h for n,h in manifest['engine']['files'].items())
 assert all(sha(ROOT/n)==h for n,h in manifest['harness_files'].items())
 item=next(x for x in manifest['cases'] if x['id']==req['case'])
 plan=json.loads((ROOT/'engine_adaptation/v4/plans'/ (req['case']+'.json')).read_text())
 expected_plan_hash=plan['plan_hash']
 assert expected_plan_hash==item['plan_hash']
 assert hashlib.sha256(encoded({k:v for k,v in plan.items() if k!='plan_hash'})).hexdigest()==expected_plan_hash
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
 return snapshot, graph, retriever, persisted, plan
