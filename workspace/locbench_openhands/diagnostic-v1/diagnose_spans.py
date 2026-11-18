from pathlib import Path
import sys,json
project=Path(__file__).resolve().parents[2]
engine=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108')
sys.path[:0]=[str(project),str(engine)]
from readonly_agent.core import Snapshot
from locagent_service.offline import offline_engine
p=project/'locbench_openhands/v1/cases/Delgan__loguru-1239';case=json.loads((p/'case.json').read_text());s=Snapshot(p/'source',case['source_files'])
with offline_engine():
 from dependency_graph.build_graph import build_graph
 g=build_graph(str(p/'source'),global_import=True)
 mismatches=[]
 for node,d in g.nodes(data=True):
  if d.get('type') not in ('function','class'):continue
  expected=s.files[node.partition(':')[0]].splitlines()[d['start_line']-1:d['end_line']]
  actual=d['code'].splitlines()
  if [x.strip() for x in expected]!=[x.strip() for x in actual]:mismatches.append({'node':node,'span':[d['start_line'],d['end_line']],'expected':expected,'actual':actual})
 print(json.dumps({'mismatches':mismatches},ensure_ascii=False,indent=2))
