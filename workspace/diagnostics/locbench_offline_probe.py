"""Read-only development diagnosis using unchanged reviewed tools, no target execution."""
import argparse,ast,hashlib,json,re,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.core import Snapshot,FileTools,page,encoded
from readonly_agent.bridge import LocAgentProcessRetriever
from readonly_agent.offline import no_network
from experiments.locbench_batch.control import frozen

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'verification/locbench-offline-diagnosis-v1'
QUERIES={
 'Delgan__loguru-1239':[
 ('issue_title','Add unit tests for traceback formatting of RecursionError'),
 ('issue_literal','traceback'),('issue_literal','RecursionError'),('observed_query','recursion'),
 ('observed_query','Previous line repeated'),('observed_query','repeated'),
 ('analyst_issue_rephrase','format exception'),
 ('observed_file_exact','loguru/_better_exceptions.py'),
 ('reference_oracle_symbol','_format_list'),
 ('reference_oracle_exact','loguru/_better_exceptions.py:ExceptionFormatter._format_list')],
 'tobymao__sqlglot-3417':[
 ('issue_title','SET TAG identifier containing dots is parsed as Command'),
 ('observed_query','SET TAG'),('observed_query','SetItem'),
 ('observed_query','_parse_set_item'),('observed_query','_parse_set_item_assignment'),
 ('observed_query','_parse_alter_table_set'),
 ('reference_oracle_exact','sqlglot/parser.py:Parser._parse_set_item_assignment')]
}

def main(identifier):
 plan=frozen();item=next(c for c in plan['base_manifest']['cases'] if c['id']==identifier)
 target=OUT/identifier;target.mkdir(parents=True,exist_ok=False)
 path=ROOT/item['case_file'];case=json.loads(path.read_text());snapshot=Snapshot(path.parent/case['root'],case['source_files'])
 assert dict(snapshot.hashes)==item['plan']['source_hashes']
 labels=json.loads((ROOT/'locbench_openhands/v4/scoring-only'/f'{identifier}.json').read_text());gold=labels['gold_entities'][0]
 gp,_,qualified=gold.partition(':');simple=qualified.rsplit('.',1)[-1]
 evidence_line='result = []' if identifier.startswith('Delgan') else 'left = self._parse_primary() or self._parse_id_var()'
 engine=Path(item['plan']['locagent_engine']['root'])
 retriever=LocAgentProcessRetriever(snapshot,python=engine/'.venv/bin/python',engine_root=engine)
 tools=FileTools(snapshot,retriever);rows=[]
 with no_network(target/'profiles') as attempts:
  # Full issue cannot be sent through either current query interface; no silent shortening.
  rejected={}
  for name in ('search_text','locagent_retrieve'):
   try:tools.render(name,{'query':case['issue'],'offset':0})
   except ValueError as e:rejected[name]=str(e)
   else:raise AssertionError('full_issue_should_exceed_current_query_limit')
  assert set(rejected)=={'search_text','locagent_retrieve'}
  for i,(category,query) in enumerate(QUERIES[identifier]):
   row={'category':category,'query':query,'query_length':len(query)}
   for name in ('search_text','locagent_retrieve'):
    start=time.perf_counter();raw,_=tools.render(name,{'query':query,'offset':0});elapsed=time.perf_counter()-start
    first=page(raw,0,4096);parts=[];offset=0;spent=0
    while True:
     result=page(raw,offset,min(4096,14336-spent))
     if result is None:break
     size=len(encoded(result));spent+=size;parts.append(result)
     if result['next_offset'] is None or 14336-spent<64:break
     offset=result['next_offset']
    text=''.join(p['text'] for p in parts)
    filename=f'{i:02d}-{name}.txt';(target/filename).write_text(raw)
    ids=re.findall(r'^##Searching for entity `([^`]+)`',raw,re.M)
    lines=raw.splitlines() if name=='search_text' else []
    row[name]={'elapsed_seconds':elapsed,'raw_file':filename,'raw_sha256':hashlib.sha256(raw.encode()).hexdigest(),
      'raw_bytes':len(raw.encode()),'ranked_entity_ids':ids,'gold_entity_rank':ids.index(gold)+1 if gold in ids else None,
      'literal_hit_count':len(lines),'gold_file_literal_hits':[l for l in lines if l.startswith(gp+':')],
      'first_page':first,'pages_in_full_14336_budget':len(parts),'all_text_delivered_with_full_budget':parts[-1]['next_offset'] is None,
      'gold_def_in_first_page':f'def {simple}(' in first['text'],
      'gold_def_with_full_budget':f'def {simple}(' in text,
      'key_body_line_in_first_page':evidence_line in first['text'],
      'key_body_line_with_full_budget':evidence_line in text}
   rows.append(row)
   print(identifier,query,json.dumps({n:{k:v for k,v in row[n].items() if k in ('ranked_entity_ids','gold_entity_rank','literal_hit_count','gold_def_in_first_page','key_body_line_in_first_page')} for n in ('search_text','locagent_retrieve')}),flush=True)
  assert not attempts
 report={'case':identifier,'snapshot':snapshot.identity,'issue_length':len(case['issue']),
  'full_issue_query_rejected':rejected,'gold':gold,'queries':rows,'network_attempts':len(attempts),
  'paid_calls':0,'target_code_executed':False,'credential_read':False,
  'query_policy':'Predeclared before execution; issue words/observed actions separated from post-hoc reference oracle probes. Not autonomous model behavior.',
  'budget_policy':'Each query evaluated alone with fresh full 14336 source-byte budget; not a replay of a live remaining budget.'}
 with (target/'results.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('case',choices=QUERIES);main(p.parse_args().case)
