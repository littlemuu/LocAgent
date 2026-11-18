"""Isolated static graph replay with reviewed engine and network/model guard."""
import contextlib,json,re,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'engine_adaptation/v4/engine')]
from experiments.cohort_preflight.entry import read,save,sha,load_entry,load_graph
from readonly_agent.core import FileTools,encoded,page,runtime_identity
from experiments.path_retrieval_v4.retriever import PathAwareRetriever
from locagent_service.offline import offline_engine
spec=read(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(exist_ok=False)
assert sha(spec['ledger'])==spec['ledger_sha256'] and runtime_identity()==spec['runtime_hash']
assert sha(ROOT/'experiments/path_retrieval_v4/retriever.py')==spec['retriever_sha256']
for f,h in spec['engine']['files'].items():assert sha(Path(spec['engine']['root'])/f)==h
rows=[]
with contextlib.redirect_stdout(sys.stderr),offline_engine():
 b=spec['binding'];value,snapshot=load_entry(b['entry'],b['entry_sha256']);assert snapshot.identity==spec['snapshot']
 graph,base,_=load_graph(value,snapshot);retriever=PathAwareRetriever(base)
 for i,q in enumerate(spec['queries']):
  tools=FileTools(snapshot,retriever);start=time.monotonic();raw,_=tools.render('locagent_retrieve',{'query':q['query'],'offset':0});elapsed=time.monotonic()-start
  first=tools.respond('locagent_retrieve',{'query':q['query'],'offset':0},4096);assert first==q['original_page'],'historical_page_mismatch'
  (out/f'query-{i}.txt').write_text(raw)
  candidates=re.findall(r'##Searching for entity `([^`]+)`',raw)
  meta=[]
  for rank,node in enumerate(candidates,1):
   d=graph.nodes[node];meta.append({'id':node,'rank':rank,'type':d['type'],'start_line':d.get('start_line'),'end_line':d.get('end_line'),'source_text_offset':raw.find('##Searching for entity `'+node+'`')})
  pages=[];offset=0
  while True:
   part=page(raw,offset,4096);assert part is not None and len(encoded(part))<=4096
   pages.append({'offset':offset,'next_offset':part['next_offset'],'encoded_bytes':len(encoded(part))})
   if part['next_offset'] is None:break
   assert part['next_offset']>offset;offset=part['next_offset']
   if len(pages)>2048:raise ValueError('page_count_guard')
  rows.append({'query':q['query'],'original_page_exact':True,'first_page':first,'raw_utf8_bytes':len(raw.encode()),'full_pages':pages,'candidate_order':meta,'seconds':elapsed,'query_source':q['query_source'],'original_turn':q['original_turn'],'has_prior_tool_evidence':q['has_prior_tool_evidence']})
save(out/'result.json',{'id':spec['id'],'snapshot':spec['snapshot'],'queries':rows,'real_requests':0,'gold_read':False,'network_guard_completed':True})
print(spec['id'],len(rows),'exact replay',flush=True)
