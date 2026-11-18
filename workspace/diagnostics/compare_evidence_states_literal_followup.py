"""Additional fair baseline: issue token search, then visible hit files, no oracle."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from diagnostics.compare_evidence_states import *
def main():
 original=read(OUT/'results.json');rows=[]
 declarations=[{'dataset':'webhook','query':'retry','case_file':'examples/crossfile/case.json'}, {'dataset':'document_access','query':'token','case_file':'development_suite/v1/cases/d03_access/case.json'}]
 save_new(OUT/'literal-followup-before.json',{'declarations':declarations,'posthoc':True,'reason':'Do not limit ordinary search to a long phrase or a recorded unsuccessful token; short literal words can also be extracted from the issue. Human-selected routes after initial comparison, not preregistered independent evaluation.','policy':'One short issue token; paginate search within original remaining budget, then read each distinct visible hit file once in lexical order.'})
 with no_network(OUT/'followup-profiles') as attempts:
  for d in declarations:
   state=next(s for s in original['states'] if s['dataset']==d['dataset']);ledger=ROOT/state['ledger'];q=calls(ledger)[0]['q'];assert d['query'] in q['messages'][1]['content']
   contract=read(ledger.parent/'retrieval/contract.json');s=snapshot(d['case_file'],contract['source_hashes']);route=Route(s,{},state['budget'])
   text=route.pages('search_text',{'query':d['query'],'offset':0})
   paths=sorted(set(re.findall(r'^([^:\n]+):\d+: ',text,re.M)))
   for path in paths:route.pages('read_file',{'path':path})
   rows.append(d|{'state_id':state['id'],'request_hash':state['request_hash'],'source':'literal in original issue','hit_files':paths,**route.result()})
  assert not attempts
 save_new(OUT/'literal-followup.json',{'routes':rows,'paid_requests':0,'network_attempts':0,'oracle_used':False,'posthoc_analyst_route':True})
 for r in rows:print(r['dataset'],r['query'],r['tool_calls'],r['json_bytes'],r['hit_files'],[f['name'] for f in r['complete_functions']])
if __name__=='__main__':main()
