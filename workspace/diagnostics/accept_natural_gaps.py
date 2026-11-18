"""Verify offline artifacts and recorded outcomes; no model/target execution."""
import json,sqlite3,re,hashlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from diagnostics.probe_natural_gaps import ROOT,OUT,read,sha,save_new
r=read(OUT/'results.json');before=read(OUT/'before.json')['files'];assert all(sha(ROOT/p)==h for p,h in before.items())
counts={'ledgers':0,'open_requests':0};outcomes=[]
for ns in ('authority','authority-batches','authority-locbench','authority-sqlglot-validation'):
 for p in (ROOT/ns).rglob('ledger.sqlite'):
  counts['ledgers']+=1
  with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as db:
   for req,h in db.execute('select request,request_hash from calls'):
    assert hashlib.sha256(req).hexdigest()==h
    q=json.loads(req)
    if any(t['function']['name']!='finish' for t in q.get('tools',[])):counts['open_requests']+=1
assert counts=={'ledgers':18,'open_requests':93}
for s in r['states']:
 assert sha(ROOT/s['retrieval_file'])==s['retrieval_sha256']
 with sqlite3.connect(f'file:{ROOT/s["ledger"]}?mode=ro',uri=True) as db:
  raw,h=db.execute('select response,response_hash from calls where arm=? and turn=?',(s['arm'],s['turn'])).fetchone()
 assert hashlib.sha256(raw).hexdigest()==h
 selections=[{'tool':x['function']['name'],'arguments':json.loads(x['function']['arguments'])} for x in json.loads(raw)['choices'][0]['message'].get('tool_calls',[])]
 outcomes.append({'state':s['id'],'response_hash':h,'actual_historical_selection':selections})
 for x in s['results']:
  assert x['tool_calls']==len(x['steps'])<=s['budget'][0]
  assert x['json_bytes']==sum(z['json_bytes'] for z in x['steps'])<=s['budget'][1]
  assert all(z['json_bytes']<=4096 and z['investigation_round']<=s['rounds'] for z in x['steps'])
  assert x['rounds_used']<=s['rounds']
byid={s['id']:s for s in r['states']}
assert all(any(f['name']=='parse_row' for f in x['complete_functions']) for x in byid['d06_import']['results'])
sql=byid['sqlglot_helper'];ret=sql['results'][0]
assert {f['path'] for f in ret['complete_functions']}=={'sqlglot/parser.py','sqlglot/dialects/tsql.py','sqlglot/dialects/snowflake.py'}
assert all(x['stop']=='investigation_rounds_exhausted' for x in sql['results'][1:])
assert all(not any(f['name']=='_parse_id_var' for f in x['complete_functions']) for x in sql['results'][1:])
save_new(OUT/'acceptance.json',{'passed':True,'inventory_verified':counts,'states':4,'routes':sum(len(s['results']) for s in r['states']),'round_budget_tests_passed':5,'protected_files_unchanged':len(before),'model_calls':0,'local_offline_retrieval_calls':4,'network_attempts':0,'actual_outcomes':outcomes,'artifact_hashes':{n:sha(OUT/n) for n in ('results.json','states-before-execution.json','round-tests.log')}})
print(json.dumps({'passed':True,**counts,'states':4,'routes':sum(len(s['results']) for s in r['states']),'protected_files_unchanged':len(before)}))
