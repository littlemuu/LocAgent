"""Natural recorded evidence gaps. Local static tools, exact budgets including rounds."""
import json,re,sqlite3,hashlib,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from diagnostics.compare_evidence_states import Route,packet_coverage,snapshot,sha,read,ROOT
from readonly_agent.authority import save_new
from readonly_agent.bridge import LocAgentProcessRetriever
from readonly_agent.offline import no_network
OUT=ROOT/'verification/natural-gaps-v1'
BATCH='34246247d2f59a8626aae8338b92f1183904874835f9fcc63b41f3775848f56e'
def record(p,arm,turn):
 with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as db:
  req,h=db.execute('select request,request_hash from calls where arm=? and turn=?',(arm,turn)).fetchone()
 assert hashlib.sha256(req).hexdigest()==h
 return json.loads(req),h
class BoundedRoute(Route):
 def __init__(self,s,cache,budget,rounds):super().__init__(s,cache,budget);self.round=1;self.maxrounds=rounds;self.chunks={};self.blocked=[]
 def call(self,name,args):
  if self.round>self.maxrounds:
   self.stop='investigation_rounds_exhausted';self.blocked.append({'tool':name,'arguments':args,'requires_round':self.round});return None
  p=super().call(name,args)
  if p is not None:
   self.steps[-1]['investigation_round']=self.round
   key=(name,args.get('path',args.get('query','')));self.chunks.setdefault(key,[]).append(p['text'])
   for path,lines in packet_coverage({'text':''.join(self.chunks[key])},name,args).items():self.cover.setdefault(path,{}).update(lines)
  return p
 def pages(self,name,args):
  text=''
  while True:
   p=self.call(name,args)
   if p is None:return text
   text+=p['text'];key='next_cursor' if name=='read_file' else 'next_offset'
   if p[key] is None:return text
   self.round+=1;args=args|({'cursor':p[key]} if name=='read_file' else {'offset':p[key]})
 def result(self):return super().result()|{'rounds_used':max((s['investigation_round'] for s in self.steps),default=0),'max_investigation_rounds':self.maxrounds,'blocked_followups':self.blocked}
def main():
 OUT.mkdir(parents=True,exist_ok=False)
 inventory=read('/tmp/natural-state-candidates.json');save_new(OUT/'inventory.json',inventory)
 protected={str(p.relative_to(ROOT)):sha(p) for ns in ['authority','authority-batches','authority-locbench','authority-sqlglot-validation','authority-choice-pair','readonly_agent','experiments','locbench_openhands','examples/crossfile','development_suite/v1','verification/evidence-states-v1'] for p in (ROOT/ns).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
 save_new(OUT/'before.json',{'files':protected})
 batch=read(ROOT/'authority-batches'/BATCH/'grant.json')['plan'];audit=read(ROOT/'verification/retrieval-choice-state-v1/results.json')
 states=[]
 for cid,query,turn in [('d06_import','parse_row',2),('d03_access','audit',2)]:
  c=next(c for c in batch['base_manifest']['cases'] if c['id']==cid)
  states.append({'id':cid,'query':query,'turn':turn,'arm':'retrieval','ledger':f"authority-batches/{BATCH}/run/children/{c['plan_hash']}/run/ledger.sqlite",'case_file':c['case_file'],'plan':c['plan']})
 web=audit['positive_controls'][0];webplan=read(ROOT/'authority/5cb8a59ad54ba444acf50b9015236b396645254094b493e3a3cbee60decdf8b2/grant.json')['plan']
 states.append({'id':'webhook_identity','query':'delivery_key','turn':3,'arm':'retrieval','ledger':web['ledger'],'case_file':'examples/crossfile/case.json','plan':webplan})
 sql=next(g for g in audit['groups'] if g['stage']=='after_read_fix')
 sqlplan=read(ROOT/'authority-sqlglot-validation/df07e7a25bad76c053d3f372b8b0b9fd0a883b03577aef53676781553f5c3277/grant.json')['plan']['base_manifest']['cases'][0]
 states.append({'id':'sqlglot_helper','query':'_parse_id_var','turn':3,'arm':'retrieval','ledger':sql['ledger'],'case_file':sqlplan['case_file'],'plan':sqlplan['plan']})
 for st in states:
  q,h=record(ROOT/st['ledger'],st['arm'],st['turn']);st['request_hash']=h
  notice=next(m['content'] for m in q['messages'] if m['role']=='user' and m['content'].startswith('CONTROLLER BUDGET'))
  b=re.search(r'available investigation calls: (\d+); available source-result bytes: (\d+)',notice);rr=re.search(r'After this response at most (\d+) further investigation',notice)
  st['budget']=[int(b[1]),int(b[2])];st['rounds']=1+int(rr[1]);st['notice']=notice
  texts=[];evidence=[]
  for i,m in enumerate(q['messages']):
   if m['role'] not in ('tool','user'):continue
   text=json.loads(m['content']).get('text','') if m['role']=='tool' else m['content']
   if m['role']=='tool':texts.append(text)
   if re.search(r'(?<!\w)'+re.escape(st['query'])+r'(?!\w)',text):evidence.append({'message_index':i,'role':m['role'],'tool_call_id':m.get('tool_call_id'),'matching_lines':[l for l in text.splitlines() if st['query'] in l]})
  assert evidence;st['evidence']=evidence;joined='\n'.join(texts)
  st['symbol_definition_seen']=bool(re.search(r'\bdef '+re.escape(st['query'])+r'\s*\(',joined))
  st['symbol_import_seen']=any(re.search(r'\bfrom\s+[.\w]+\s+import\b',l) and st['query'] in l for l in joined.splitlines())
  if st['id'] in ('d06_import','sqlglot_helper'):assert not st['symbol_definition_seen'] and not st['symbol_import_seen']
  if st['id']=='d06_import':
   assert 'imports/parser.py' in joined;st['location_hint']='imports/parser.py listed and contains invoice matching lines; plausible file, no explicit symbol mapping';st['hint_path']='imports/parser.py'
   st['routes']=['retrieve','search_definition_then_read','read_visible_hint']
  elif st['id']=='d03_access':
   assert 'record_access' not in joined and 'docs/audit.py' not in joined;st['location_hint']='audit topic only in original issue; access and shares evidence received';st['routes']=['retrieve','search_topic_then_read_hits']
  elif st['id']=='webhook_identity':
   assert 'from .identity import delivery_key' in joined and 'dispatch/identity.py' in joined;st['location_hint']='explicit relative import and listed path';st['hint_path']='dispatch/identity.py';st['routes']=['retrieve','read_visible_hint']
  else:
   assert 'self._parse_id_var()' in joined;st['location_hint']='call through self in sqlglot/parser.py, definition might be in class/base or override; no definition line';st['routes']=['retrieve','search_definition_then_read','read_caller_file_prefix'];st['hint_path']='sqlglot/parser.py'
  # Bind reviewed engine and source before running any new retrieval.
  e=st['plan']['locagent_engine'];engine=Path(e['root'])
  for path,expected in e['files'].items():assert sha(engine/path)==expected,(str(engine),path)
  st['snapshot']=snapshot(st['case_file'],st['plan']['source_hashes']).identity
 save_new(OUT/'states-before-execution.json',{'states':states,'selection':'Post-hoc human choice from real received messages, not labels; no hidden test data or altered messages','round_policy':'All dependent continuation/search-to-read steps require another investigation response; independent known-path reads may share a response. Model not run.','route_policy':'Search exact def prefix for known symbols; first visible def; read 40 lines from hit. Topic search reads all visible hit files in next round. Hint route reads whole visible/plausible file with pagination. One response per page when cursor needed.'})
 results=[]
 with no_network(OUT/'profiles') as attempts,patch('readonly_agent.local_env.load_selected_key',side_effect=AssertionError('credentials_forbidden')):
  for st in states:
   s=snapshot(st['case_file'],st['plan']['source_hashes']);e=Path(st['plan']['locagent_engine']['root'])
   retriever=LocAgentProcessRetriever(s,python=e/'.venv/bin/python',engine_root=e)
   raw=retriever.retrieve(st['query']);rawpath=OUT/(st['id']+'-retrieval.txt');rawpath.write_text(raw)
   cache={st['query']:raw};rows=[]
   for mode in st['routes']:
    route=BoundedRoute(s,cache,st['budget'],st['rounds'])
    if mode=='retrieve':route.pages('locagent_retrieve',{'query':st['query'],'offset':0})
    elif mode in ('read_visible_hint','read_caller_file_prefix'):route.pages('read_file',{'path':st['hint_path']})
    else:
     query=st['query'] if mode=='search_topic_then_read_hits' else 'def '+st['query']+'('
     # Only the first returned page can guide the next turn; no hidden full result.
     p=route.call('search_text',{'query':query,'offset':0});hits=re.findall(r'^([^:\n]+):(\d+): (.*)$',p['text'],re.M) if p else []
     route.round+=1
     if mode=='search_topic_then_read_hits':
      phase=route.round
      for path in sorted({h[0] for h in hits}):route.round=phase;route.pages('read_file',{'path':path})
     elif hits:
      path,n,_=hits[0];n=int(n);route.pages('read_file',{'path':path,'start_line':n,'end_line':min(n+39,len(s.files[path].splitlines()))})
    rows.append({'route':mode,**route.result()})
   results.append({k:v for k,v in st.items() if k!='plan'}|{'retrieval_file':str(rawpath.relative_to(ROOT)),'retrieval_sha256':sha(rawpath),'retrieval_raw_bytes':len(raw.encode()),'entity_order':re.findall(r'^##Searching for entity `([^`]+)`',raw,re.M),'results':rows})
   print(st['id'], 'budget',st['budget'],'rounds',st['rounds'],[(r['route'],r['tool_calls'],r['json_bytes'],r['rounds_used'],r['stop'],[f['name'] for f in r['complete_functions']]) for r in rows],flush=True)
  assert not attempts
 for p,h in protected.items():assert sha(ROOT/p)==h,p
 save_new(OUT/'results.json',{'states':results,'new_model_calls':0,'new_local_retrieval_calls':len(states),'network_attempts':len(attempts),'credentials_read':False,'target_code_executed':False,'historical_files_unchanged':len(protected),'limitations':'Exposed development tasks, analyst-selected traces/routes; heuristic inventory not exhaustive symbol resolution. First-hit and 40-line read are not optimal. Source bytes not token/cost/latency. Old live read protocol replaced by current repaired reader only in offline counterfactual. No model replay or causal effect.'})
if __name__=='__main__':main()
