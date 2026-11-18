"""Audit saved live receipts; no transport, keys, or returned tool execution."""
import json,hashlib,sqlite3,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.natural_choice.run import frozen,request,STORE
from readonly_agent.core import digest
from readonly_agent.authority import save_new,now
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/natural-choice-live-v1'
p=json.loads((OUT/'preflight.json').read_text());h=digest(frozen());assert h==p['plan_hash']
changed=[n for n,v in p['files_before'].items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=v];assert not changed
run=STORE/h/'run';r=json.loads((run/'result.json').read_text());assert r['status']=='completed' and r['tool_execution'] is False
assert json.loads((run/'execution.json').read_text())['mode']=='live'
with sqlite3.connect(f'file:{run/"ledger.sqlite"}?mode=ro',uri=True) as d:
 d.row_factory=sqlite3.Row;calls=[dict(c) for c in d.execute('select * from calls order by id')]
assert len(calls)==2
receipts=[]
for c in calls:
 assert c['request']==request(c['arm']) and c['status']=='settled' and c['http_status']==200 and c['transport_started']==1
 assert hashlib.sha256(c['request']).hexdigest()==c['request_hash'] and hashlib.sha256(c['response']).hexdigest()==c['response_hash']
 receipts.append({k:c[k] for k in ('id','arm','request_hash','response_hash','http_status','status','cost')})
assert r['budget']['spent_upper_micro_cny']==sum(x['cost'] for x in receipts)==18070 and r['budget']['reserved_micro_cny']==0
q=json.loads(request('retrieval'));seen=[]
for token in ('SET_REQUIRES_ASSIGNMENT_DELIMITER','SET_TRIE','_parse_id_var'):
 sources=[]
 for i,m in enumerate(q['messages']):
  if m['role']=='tool':
   text=json.loads(m['content'])['text']
   matches=[l for l in text.splitlines() if re.search(r'(?<!\w)'+re.escape(token)+r'(?!\w)',l)]
   if matches:sources.append({'message_index':i,'tool_call_id':m['tool_call_id'],'matching_lines':matches})
 seen.append({'symbol':token,'already_in_received_tool_evidence':bool(sources),'sources':sources})
report={'checked_at':now().isoformat(),'plan_hash':h,'actual_requests':2,'completed_arms':2,'receipts':receipts,'cost_upper_cny':0.01807,'provider_account_billing_reconciled':False,'remaining_reservations':0,'historical_files_unchanged':len(p['files_before']),'tools_executed':0,'followup_requests':0,'automatic_retries':0,'locagent_selection_when_available':False,'baseline_cannot_select_retrieval_by_design':True,'selected_symbol_provenance':seen,'request_only_not_answer_quality':True}
save_new(OUT/'acceptance.json',report)
print(json.dumps({k:v for k,v in report.items() if k not in ('receipts','selected_symbol_provenance')},ensure_ascii=False))
print([(x['symbol'],x['already_in_received_tool_evidence']) for x in seen])
