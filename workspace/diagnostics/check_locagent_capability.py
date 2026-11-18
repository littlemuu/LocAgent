"""Provenance-bound offline capability check; reuse old queries, no target execution."""
import ast,hashlib,json,re,sqlite3,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.core import Snapshot,page,encoded,digest
from readonly_agent.bridge import LocAgentProcessRetriever
from readonly_agent.offline import no_network
from readonly_agent.authority import save_new
from experiments.locbench_batch.control import frozen
from experiments.sqlglot_validation.control import frozen as sql_frozen
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'verification/locagent-capability-v1'
OLD=ROOT/'verification/locbench-offline-diagnosis-v1'
OLD_RUN='eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83'
NEW_RUN='df07e7a25bad76c053d3f372b8b0b9fd0a883b03577aef53676781553f5c3277'
# Declared before any new retrieval. No oracle symbols in the primary query list.
QUERIES={
 'Delgan__loguru-1239':['traceback','RecursionError','Previous line repeated','recursion','repeated',
 'loguru/_better_exceptions.py','raising_recursion','tail_recursion'],
 'tobymao__sqlglot-3417':['SET TAG','SetItem','_parse_set_item','_parse_set_item_assignment','_parse_set','_parse_primary']}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def messages(identifier):
 records=[]
 for namespace,h in [('authority-locbench',OLD_RUN),('authority-sqlglot-validation',NEW_RUN)]:
  grant=read(ROOT/namespace/h/'grant.json')
  for c in grant['plan']['base_manifest']['cases']:
   if c['id']!=identifier:continue
   ledger=ROOT/namespace/h/'run/children'/c['plan_hash']/'run/ledger.sqlite'
   with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
    for arm,turn,request,rhash in db.execute('SELECT arm,turn,request,request_hash FROM calls ORDER BY id'):
     assert hashlib.sha256(request).hexdigest()==rhash
     req=json.loads(request)
     for index,m in enumerate(req['messages']):
      if m['role'] not in ('user','tool'):continue
      content=m.get('content','')
      if not isinstance(content,str):continue
      if m['role']=='tool':
       try:content=json.loads(content)['text']
       except (ValueError,KeyError,TypeError):continue
      records.append({'run':h,'ledger':str(ledger.relative_to(ROOT)),'arm':arm,'request_turn':turn,
        'message_index':index,'role':m['role'],'tool_call_id':m.get('tool_call_id'),'request_sha256':rhash,'text':content})
 return records

def provenance(query,records,issue):
 # Exact symbol boundaries prevent _parse_set falsely matching _parse_set_item.
 pattern=re.compile(r'(?<![\w])'+re.escape(query)+r'(?![\w])')
 found=[]
 for r in records:
  match=pattern.search(r['text'])
  if not match:continue
  # One earliest request for each arm/run/role; final-turn-only clues remain flagged.
  key=(r['run'],r['arm'],r['role'])
  if any((x['run'],x['arm'],x['role'])==key for x in found):continue
  found.append({k:v for k,v in r.items() if k!='text'} | {'excerpt':r['text'][max(0,match.start()-90):match.end()+130],
       'investigation_still_available':r['request_turn']<4})
 return {'literal_in_original_issue':query in issue,'seen_in_actual_received_messages':bool(found),
  'seen_while_investigation_open':any(x['investigation_still_available'] for x in found),'evidence':found}

def measure(raw,snapshot,label):
 gold=label['gold_entities'][0];path,_,qual=gold.partition(':');span=label['mapping']['gold_mappings'][0]['strict_ast'];start,end=span['start_line'],span['end_line']
 source=snapshot.files[path];lines=source.splitlines()
 node=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.lineno==start and n.end_lineno==end)
 expected=ast.get_source_segment(source,node).splitlines();assert len(expected)==end-start+1
 def coverage(text):
  covered=set()
  # Restrict numbered code to a result for the correct file; line numbers alone are insufficient.
  for chunk in re.split(r'(?=^##Searching for entity `)',text,flags=re.M):
   head=re.match(r'^##Searching for entity `([^`]+)`',chunk)
   if not head or head[1].partition(':')[0]!=path:continue
   for m in re.finditer(r'^\s*(\d+) \| (.*)$',chunk,re.M):
    n=int(m[1]);body=m[2]
    if start<=n<=end and body in (lines[n-1],expected[n-start]):covered.add(n)
  return {'matching_target_lines':sorted(covered),'complete':len(covered)==end-start+1}
 pages=[];spent=offset=0
 while True:
  p=page(raw,offset,min(4096,14336-spent))
  if p is None:break
  spent+=len(encoded(p));pages.append(p)
  if p['next_offset'] is None or 14336-spent<64:break
  offset=p['next_offset']
 ids=re.findall(r'^##Searching for entity `([^`]+)`',raw,re.M)
 first=pages[0]
 return {'ranked_entity_ids':ids,'gold_entity_rank':ids.index(gold)+1 if gold in ids else None,
  'raw_utf8_bytes':len(raw.encode()),'first_page_json_bytes':len(encoded(first)),
  'within_budget_json_bytes':spent,'pages_within_full_14336_budget':len(pages),
  'all_raw_text_fits_budget':pages[-1]['next_offset'] is None,'empty_result':raw=='No locations found.',
  'target_lines':[start,end],'target_body_raw':coverage(raw),'target_body_first_page':coverage(first['text']),
  'target_body_within_budget':coverage(''.join(p['text'] for p in pages)),
  'first_page':first,'pages':pages}

def main():
 plan=frozen();sql=sql_frozen();OUT.mkdir(parents=True,exist_ok=False)
 protected={}
 for name in ['authority','authority-batches','authority-locbench','authority-sqlglot-validation','locbench_openhands','locbench_live','sqlglot_read_validation','readonly_agent','experiments', 'verification/locbench-offline-diagnosis-v1','verification/retrieval-choice-hypotheses-v1']:
  for p in (ROOT/name).rglob('*'):
   if p.is_file() and '__pycache__' not in p.parts:protected[str(p.relative_to(ROOT))]=sha(p)
 save_new(OUT/'before.json',{'files':protected,'current_two_case_hash':digest(plan),'sqlglot_hash':digest(sql)})
 old_manifest=read(ROOT/'locbench_openhands/v4/manifest.json');old_code=read(ROOT/'verification/read-lines-repair-v1/before.json')['code']
 for path in ['readonly_agent/locagent.py','readonly_agent/bridge.py','readonly_agent/locagent_worker.py']:
  assert (ROOT/path).read_text()==old_code[path],path
 declarations=[]
 for item in plan['base_manifest']['cases']:
  cid=item['id'];cfg=read(ROOT/item['case_file']);olditem=next(c for c in old_manifest['cases'] if c['id']==cid)
  assert item['plan']['source_hashes']==olditem['plan']['source_hashes'] and item['plan']['locagent_engine']==olditem['plan']['locagent_engine']
  label_path=ROOT/'locbench_openhands/v5/scoring-only'/f'{cid}.json';assert sha(label_path)==sha(ROOT/'locbench_openhands/v4/scoring-only'/f'{cid}.json')
  records=messages(cid);title=cfg['issue'].splitlines()[0];queries=[title]+QUERIES[cid]
  rows=[]
  for q in queries:
   prov=provenance(q,records,cfg['issue']);assert prov['seen_in_actual_received_messages'],(cid,q)
   assert prov['literal_in_original_issue'] or prov['seen_while_investigation_open'],(cid,q,'too_late')
   rows.append({'query':q,'query_length':len(q),'origin':'exact_title' if q==title else 'issue_literal' if q in cfg['issue'] else 'prior_tool_evidence',
    'path_basename_clue_not_function_name':q in ('raising_recursion','tail_recursion'),'provenance':prov})
  declarations.append({'case':cid,'case_file':item['case_file'],'queries':rows,'issue_length':len(cfg['issue']),
    'full_issue_sha256':hashlib.sha256(cfg['issue'].encode()).hexdigest(),'title_is_exact_first_line':True,'title_length':len(title)})
 save_new(OUT/'queries-before-execution.json',{'selection':'analyst selected exposed development clues; no autonomous model claim','cases':declarations})
 results=[];reused=new=0
 with no_network(OUT/'profiles') as attempts,patch('readonly_agent.local_env.load_selected_key',side_effect=AssertionError('credential_read_forbidden')):
  for declaration in declarations:
   cid=declaration['case'];item=next(c for c in plan['base_manifest']['cases'] if c['id']==cid);casefile=ROOT/item['case_file'];cfg=read(casefile)
   snapshot=Snapshot(casefile.parent/cfg['root'],cfg['source_files']);assert dict(snapshot.hashes)==item['plan']['source_hashes']
   engine=Path(item['plan']['locagent_engine']['root']);retriever=LocAgentProcessRetriever(snapshot,python=engine/'.venv/bin/python',engine_root=engine)
   prior=read(OLD/cid/'results.json');assert prior['snapshot']==snapshot.identity
   label=read(ROOT/'locbench_openhands/v5/scoring-only'/f'{cid}.json')
   try:retriever.retrieve(cfg['issue'])
   except ValueError as e:assert str(e)=='invalid_query'
   else:raise AssertionError('full_issue_not_rejected')
   rows=[]
   for i,decl in enumerate(declaration['queries']):
    q=decl['query'];saved=next((x for x in prior['queries'] if x['query']==q),None)
    if saved:
     path=OLD/cid/saved['locagent_retrieve']['raw_file'];assert sha(path)==saved['locagent_retrieve']['raw_sha256'];raw=path.read_text();reused+=1
     origin={'reused':True,'raw_path':str(path.relative_to(ROOT)),'raw_sha256':sha(path)}
    else:
     raw=retriever.retrieve(q);path=OUT/(cid+'-'+str(i)+'.txt');path.write_text(raw);new+=1
     origin={'reused':False,'raw_path':str(path.relative_to(ROOT)),'raw_sha256':sha(path)}
    row=decl|origin|measure(raw,snapshot,label);rows.append(row)
    print(json.dumps({'case':cid,'query':q,'reused':origin['reused'],'rank':row['gold_entity_rank'],'raw_bytes':row['raw_utf8_bytes'],'page_bytes':row['first_page_json_bytes'],'full_body_first_page':row['target_body_first_page']['complete']},ensure_ascii=False),flush=True)
   # Preserve oracle results as a clearly separate control, never in the available-clue group.
   oracle=next(q for q in prior['queries'] if q['category']=='reference_oracle_symbol') if cid.startswith('Delgan') else next(q for q in prior['queries'] if q['category']=='reference_oracle_exact')
   opath=OLD/cid/oracle['locagent_retrieve']['raw_file'];assert sha(opath)==oracle['locagent_retrieve']['raw_sha256']
   symbol=label['gold_entities'][0].rsplit('.',1)[-1]
   result=declaration|{'snapshot':snapshot.identity,'label_sha256':sha(ROOT/'locbench_openhands/v5/scoring-only'/f'{cid}.json'),
    'full_original_issue_query':{'status':'interface_rejected','reason':'query exceeds 256 characters','retrieval_executed':False,'hit_or_rank':'not_evaluated'},
    'queries':rows,'reference_control':{'query':oracle['query'],'source':'reference_oracle_only','raw_path':str(opath.relative_to(ROOT)),
     'gold_simple_symbol_seen_in_prior_requests':provenance(symbol,messages(cid),cfg['issue']),**measure(opath.read_text(),snapshot,label)}}
   results.append(result)
  assert not attempts
 for path,h in protected.items():assert sha(ROOT/path)==h,path
 assert digest(frozen())==digest(plan) and digest(sql_frozen())==digest(sql)
 report={'cases':results,'reused_query_results':reused,'new_offline_retrievals':new,'full_issue_interface_rejections':2,
 'new_model_calls':0,'network_attempts_parent':len(attempts),'worker_guard':'existing isolated bridge with offline_engine network/model guard',
 'target_code_executed':False,'credentials_read':False,'retrieval_strategy_changed':False,'historical_files_unchanged':len(protected),
 'oracle_controls_excluded_from_discovery':True,'independent_test':False,'claims_autonomous_choice':False,
 'limitation':'Human-selected queries on exposed development cases; fresh per-query budget, not actual model behavior or counterfactual trajectory.'}
 save_new(OUT/'results.json',report)
 print(json.dumps({k:v for k,v in report.items() if k!='cases'},ensure_ascii=False))
if __name__=='__main__':main()
