"""Reviewed offline boundary regressions against the candidate engine."""
import json,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CODE=r'''
import sys,json,copy,importlib.metadata
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root),str(root/'engine_adaptation/v3/engine')]
from locagent_service.offline import offline_engine
with offline_engine():
 from readonly_agent.core import Snapshot,FileTools
 from readonly_agent.locagent import LocAgentRetriever
 from readonly_agent.bridge import LocAgentProcessRetriever
 from dependency_graph.build_graph import build_graph
 source=root/'engine_adaptation/v3/fixture'
 names=[str(p.relative_to(source)) for p in source.rglob('*.py')]
 snap=Snapshot(source,names,hidden_python_paths=['.ci/helper.py','.ci/display_test.py'])
 graph=build_graph(str(source),global_import=True)
 expected={'.ci/helper.py:Box.__init__','.ci/helper.py:Box.__init__.nested','pkg.github/visible.py:visible'}
 assert expected<=set(graph)
 assert 'Found file `.ci/display_test.py`' in LocAgentRetriever(snap,graph).retrieve('.ci/display_test.py')
 assert not any(d['type']=='invokes' and '.__init__' in b for a,b,d in graph.edges(data=True))
 good=LocAgentRetriever(snap,graph).retrieve('.ci/helper.py:Box.__init__')
 wire=LocAgentProcessRetriever(snap,python=sys.executable,engine_root=root/'engine_adaptation/v3/engine').retrieve('.ci/helper.py:Box.__init__')
 assert good==wire and '中' in wire and '\r\n' in wire
 for mutation,reason in [('body','graph_entity_content_mismatch'),('entity','graph_missing_source_entities'),('file','graph_missing_source_files')]:
  bad=copy.deepcopy(graph)
  if mutation=='body':bad.nodes['.ci/helper.py:Box.__init__']['code']='forged'
  elif mutation=='entity':bad.remove_node('.ci/helper.py:Box.__init__.nested')
  else:bad.remove_node('pkg.github/visible.py')
  try:LocAgentRetriever(snap,bad)
  except ValueError as e:assert str(e)==reason,(str(e),reason)
  else:raise AssertionError(mutation)
 packet=FileTools(snap).respond('read_file',{'path':'.ci/helper.py','start_line':4,'end_line':4},4096)
 assert packet['text']=='4:             return "中"\n'
 print(json.dumps({'status':'passed','checks':['constructor_and_nested_ids','non_hidden_dot_directory','no_fuzzy_constructor_calls','CRLF_exact_AST','IPC_hidden_CRLF_roundtrip','forged_body_rejected','missing_entity_rejected','missing_file_rejected','line_evidence'], 'python':sys.version,'packages':{p:importlib.metadata.version(p) for p in ['networkx','bm25s','llama-index-core','llama-index-retrievers-bm25','tree-sitter']}}))
'''
def main():
 with tempfile.TemporaryDirectory() as tmp:
  script=Path(tmp)/'probe.py';script.write_text(CODE)
  env={'PATH':os.defpath,'HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1','LITELLM_LOCAL_MODEL_COST_MAP':'True','MPLCONFIGDIR':tmp,'XDG_CACHE_HOME':tmp}
  run=subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python','-I','-B',str(script),str(ROOT)],env=env,cwd=tmp,capture_output=True,timeout=60)
  out=ROOT/'engine_adaptation/v3';(out/'boundary.stderr').write_bytes(run.stderr)
  if run.returncode:raise RuntimeError(run.stderr.decode()[-1800:])
  data=json.loads(run.stdout);(out/'boundary-results.json').write_text(json.dumps(data,indent=2));print(json.dumps(data))
if __name__=='__main__':main()
