"""Offline state/route audit. Saved retrieval only; static source; no model/credentials."""
import ast,hashlib,json,re,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.core import Snapshot,FileTools,encoded
from readonly_agent.offline import no_network
from readonly_agent.authority import save_new
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/evidence-states-v1'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def calls(p):
 with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as db:
  db.row_factory=sqlite3.Row;rows=[dict(r) for r in db.execute("select * from calls where arm='retrieval' order by turn")]
 for r in rows:
  assert hashlib.sha256(r['request']).hexdigest()==r['request_hash']
  assert hashlib.sha256(r['response']).hexdigest()==r['response_hash']
  r['q']=json.loads(r['request']);r['r']=json.loads(r['response'])
 return rows
def snapshot(cfgpath,expected):
 p=ROOT/cfgpath;c=read(p);s=Snapshot(p.parent/c['root'],c['source_files']);assert dict(s.hashes)==expected;return s
class SavedRetriever:
 def __init__(self,s,cache):self.snapshot_id=s.identity;self.cache=cache
 def retrieve(self,q):return self.cache[q]
def packet_coverage(p,name,args):
 text=p['text'];found={}
 if name=='locagent_retrieve':
  path=None
  for line in text.splitlines():
   head=re.match(r'^##Searching for entity `([^`]+)`',line)
   if head:path=head[1].partition(':')[0]
   hit=re.match(r'^\s*(\d+) \| (.*)$',line)
   if hit and path:found.setdefault(path,{})[int(hit[1])]=hit[2]
 elif name=='read_file':
  for line in text.splitlines():
   hit=re.match(r'^(\d+): (.*)$',line)
   if hit:found.setdefault(args['path'],{})[int(hit[1])]=hit[2]
 else:
  for line in text.splitlines():
   hit=re.match(r'^([^:]+):(\d+): (.*)$',line)
   if hit:found.setdefault(hit[1],{})[int(hit[2])]=hit[3]
 return found
class Route:
 def __init__(self,s,cache,budget):self.s=s;self.t=FileTools(s,SavedRetriever(s,cache));self.budget=budget;self.steps=[];self.used=0;self.cover={};self.stop=None
 def call(self,name,args):
  if len(self.steps)>=self.budget[0] or self.budget[1]-self.used<64:self.stop='budget';return None
  p=self.t.respond(name,args,min(4096,self.budget[1]-self.used))
  if p is None:self.stop='packet_does_not_fit';return None
  size=len(encoded(p));self.used+=size;assert self.used<=self.budget[1]
  for path,lines in packet_coverage(p,name,args).items():self.cover.setdefault(path,{}).update(lines)
  self.steps.append({'tool':name,'arguments':args.copy(),'json_bytes':size,'packet':p});return p
 def pages(self,name,args):
  alltext=''
  while True:
   p=self.call(name,args)
   if p is None:break
   alltext+=p['text'];nextkey='next_cursor' if name=='read_file' else 'next_offset'
   if p[nextkey] is None:break
   args=args|({'cursor':p[nextkey]} if name=='read_file' else {'offset':p[nextkey]})
  return alltext
 def result(self):
  complete=[]
  for path,source in self.s.files.items():
   lines=source.splitlines();seen=self.cover.get(path,{})
   for node in ast.walk(ast.parse(source)):
    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
     # LocAgent strips indentation on the function's first line only.
     if all(n in seen and (seen[n]==lines[n-1] or n==node.lineno and seen[n]==lines[n-1].lstrip()) for n in range(node.lineno,node.end_lineno+1)):
      complete.append({'path':path,'name':node.name,'start':node.lineno,'end':node.end_lineno})
  return {'tool_calls':len(self.steps),'json_bytes':self.used,'stop':self.stop,'complete_functions':complete,'evidence_files':sorted(self.cover),'steps':self.steps}
def main():
 OUT.mkdir(parents=True,exist_ok=False)
 protected={str(p.relative_to(ROOT)):sha(p) for ns in ['authority','authority-batches','authority-locbench','authority-sqlglot-validation','authority-choice-pair','readonly_agent','experiments','locbench_openhands','examples/crossfile','development_suite/v1'] for p in (ROOT/ns).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
 save_new(OUT/'before.json',{'files':protected})
 audit=read(ROOT/'verification/retrieval-choice-state-v1/results.json');caps=read(ROOT/'verification/locagent-capability-v1/results.json');datasets={}
 manifest=read(ROOT/'locbench_openhands/v5/manifest.json')
 for cid in ('Delgan__loguru-1239','tobymao__sqlglot-3417'):
  item=next(x for x in manifest['cases'] if x['id']==cid);s=snapshot(item['case_file'],item['plan']['source_hashes']);cache={};cache_sources={}
  for row in next(x for x in caps['cases'] if x['case']==cid)['queries']:
   raw=ROOT/row['raw_path'];assert sha(raw)==row['raw_sha256'];cache[row['query']]=raw.read_text();cache_sources[row['query']]={'file':row['raw_path'],'sha256':sha(raw)}
  datasets[cid]=(s,cache,cache_sources)
 for x in audit['positive_controls']:
  ledger=ROOT/x['ledger'];rows=calls(ledger);contract=read(ledger.parent/'retrieval/contract.json')
  cfg='examples/crossfile/case.json' if x['sample']=='webhook' else 'development_suite/v1/cases/d03_access/case.json'
  s=snapshot(cfg,contract['source_hashes']);cache={};sources={}
  for row in rows:
   for m in row['q']['messages']:
    if m['role']!='tool':continue
    cid=m['tool_call_id']
    fn=next((t['function'] for z in rows for t in z['r']['choices'][0]['message'].get('tool_calls',[]) if t['id']==cid),None)
    if fn and fn['name']=='locagent_retrieve':
     args=json.loads(fn['arguments']);p=json.loads(m['content']);assert p['next_offset'] is None
     cache[args['query']]=p['text'];sources[args['query']]={'ledger':x['ledger'],'request_hash':row['request_hash'],'tool_call_id':cid,'original_packet_json_bytes':len(encoded(p))}
  datasets[x['sample']]=(s,cache,sources)
 def state(id,cid,group,turn,query,queryorigin,routes,constructed=False):
  rs=calls(ROOT/group['ledger']);row=next(r for r in rs if r['turn']==turn);q=row['q'];notice=next(m['content'] for m in q['messages'] if m['role']=='user' and m['content'].startswith('CONTROLLER BUDGET'))
  b=re.search(r'available investigation calls: (\d+); available source-result bytes: (\d+)',notice)
  prior=[m for m in q['messages'] if m['role']=='tool'];joined='\n'.join(json.loads(m['content']).get('text','') for m in prior)
  if queryorigin=='issue_literal':assert query in q['messages'][1]['content']
  if queryorigin=='prior_tool':assert query in joined
  return {'id':id,'dataset':cid,'ledger':group['ledger'],'turn':turn,'request_hash':row['request_hash'],'state_kind':'constructed_symbol_only' if constructed else 'recorded_checkpoint','query':query,'query_origin':queryorigin,'budget':[int(b[1]),int(b[2])],'routes':routes,'prior_tool_text':joined,'issue':q['messages'][1]['content']}
 log=next(g for g in audit['groups'] if 'loguru' in g['case']);sql=next(g for g in audit['groups'] if g['stage']=='before_read_fix' and 'sqlglot' in g['case']);new=next(g for g in audit['groups'] if g['stage']=='after_read_fix')
 states=[state('loguru_problem_only',log['case'],log,1,'traceback','issue_literal',['literal_then_read','retrieve']),state('loguru_file_known',log['case'],log,2,'loguru/_better_exceptions.py','prior_tool',['read_known_file','retrieve']),state('sqlglot_problem_only',sql['case'],sql,1,'SET TAG','issue_literal',['literal_then_read','retrieve']),state('sqlglot_symbol_file_known',sql['case'],sql,2,'_parse_set_item_assignment','prior_tool',['read_known_definition','retrieve']),state('sqlglot_symbol_only_constructed',sql['case'],sql,2,'_parse_set_item_assignment','prior_tool',['literal_then_read','retrieve'],True),state('sqlglot_body_already_known',new['case'],new,3,'_parse_set_item_assignment','prior_tool',['reuse_prior','retrieve'])]
 for pos in audit['positive_controls']:
  query=next(iter(datasets[pos['sample']][1]));states.append(state(pos['sample']+'_crossfile',pos['sample'],pos,1,query,'recorded_model_query',['literal_same_query','recorded_literal_then_read','list_read_all','retrieve']))
 # Freeze routes before new local tool operations. No gold labels enter queries/routes.
 save_new(OUT/'states-before-probe.json',{'states':states,'routing':'literal_then_read: first exact def hit if present else first hit, read 40 lines from that visible hit; read_known_definition uses first exact def in prior evidence, 40 lines. Small repos list_read_all follows all visible allowlisted paths in lexical order. All pages consume shared remaining budget. No claim of optimal routing.'})
 results=[]
 with no_network(OUT/'profiles') as attempts:
  for st in states:
   s,cache,sources=datasets[st['dataset']];rows=[]
   for mode in st['routes']:
    route=Route(s,cache,st['budget']);query=st['query']
    if mode=='retrieve':route.pages('locagent_retrieve',{'query':query,'offset':0})
    elif mode=='reuse_prior':
     # Do not charge old evidence twice. Use actual packets only for coverage.
     original=next(r for r in calls(ROOT/st['ledger']) if r['turn']==st['turn'])
     for m in original['q']['messages']:
      if m['role']=='tool':
       # Read evidence path from the matching historical call.
       fn=next(t['function'] for z in original['q']['messages'] if z['role']=='assistant' for t in z.get('tool_calls',[]) if t['id']==m['tool_call_id'])
       for path,lines in packet_coverage(json.loads(m['content']),fn['name'],json.loads(fn['arguments'])).items():route.cover.setdefault(path,{}).update(lines)
    elif mode=='read_known_file':route.pages('read_file',{'path':query})
    elif mode=='list_read_all':
     listing=route.pages('list_files',{'offset':0})
     for path in listing.splitlines():
      if path in s.files:route.pages('read_file',{'path':path})
    else:
     text=st['prior_tool_text'] if mode=='read_known_definition' else route.pages('search_text',{'query':('webhook' if st['dataset']=='webhook' else 'share_token') if mode=='recorded_literal_then_read' else query,'offset':0})
     if mode!='literal_same_query':
      hits=re.findall(r'^([^:\n]+):(\d+): (.*)$',text,re.M)
      defs=[h for h in hits if re.search(r'\bdef '+re.escape(query)+r'\(',h[2])]
      h=(defs or hits)[0] if (defs or hits) else None
      if h:
       path,n,_=h;n=int(n);assert path in s.files
       route.pages('read_file',{'path':path,'start_line':n,'end_line':min(n+39,len(s.files[path].splitlines()))})
    rows.append({'route':mode,**route.result()})
   results.append({k:v for k,v in st.items() if k not in ('prior_tool_text','issue')}|{'cache_provenance':sources[st['query']],'results':rows})
  assert not attempts
 # Scoring strictly after probes; no reference paths/symbols used to choose routes.
 for st in results:
  if st['dataset'] not in ('webhook','document_access'):
   label=read(ROOT/'locbench_openhands/v5/scoring-only'/f"{st['dataset']}.json");gold=label['gold_entities'][0];span=label['mapping']['gold_mappings'][0]['strict_ast']
   for row in st['results']:row['reference_function_complete']=any(f['path']==gold.partition(':')[0] and f['start']==span['start_line'] and f['end']==span['end_line'] for f in row['complete_functions'])
 for p,h in protected.items():assert sha(ROOT/p)==h,p
 report={'states':results,'new_paid_requests':0,'new_locagent_engine_calls':0,'reused_retrieval_queries':len({(s['dataset'],s['query']) for s in states}),'network_attempts':len(attempts),'target_code_executed':False,'credentials_read':False,'historical_files_unchanged':len(protected),'limitations':'Human chosen exposed states/routes. Current repaired read interface used counterfactually on older checkpoints; no model turns replayed. Fixed 40-line heuristic not optimal. Bytes are full JSON evidence, not model tokens, total compute or prices. Retrieval cache matches frozen source; latency/index cost not measured. No causal inference.'}
 save_new(OUT/'results.json',report)
 for st in results:print(st['id'],[(r['route'],r['tool_calls'],r['json_bytes'],r.get('reference_function_complete'),len(r['complete_functions'])) for r in st['results']])
 print('protected',len(protected),'network',len(attempts))
if __name__=='__main__':main()
