"""Read-only local acceptance for the unapproved two-request replay proposal."""
import json,hashlib,sqlite3,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.natural_choice.run import frozen,request,STORE,FROZEN
from readonly_agent.authority import save_new
from readonly_agent.core import digest
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/natural-choice-prep-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
plan=frozen();h=digest(plan);assert not STORE.exists()
p=json.loads((OUT/'checkpoint-provenance.json').read_text());ledger=ROOT/p['ledger']
with sqlite3.connect(f'file:{ledger}?mode=ro',uri=True) as db:old=db.execute('select request from calls where arm=? and turn=?',(p['arm'],p['turn'])).fetchone()[0]
assert old==request('retrieval')
a=json.loads(request('baseline'));b=json.loads(old);b['tools']=[t for t in b['tools'] if t['function']['name']!='locagent_retrieve'];assert a==b
assert plan['max_requests_total']==2 and plan['max_requests_per_arm']==1
assert plan['full_reservations_micro_cny']==4227072<plan['budget_micro_cny']==5000000
before=json.loads((ROOT/'verification/natural-gaps-v1/before.json').read_text())['files'];assert all(sha(ROOT/n)==v for n,v in before.items())
assert 'Ran 18 tests' in (OUT/'offline-tests.log').read_text() and '\nOK\n' in (OUT/'offline-tests.log').read_text()
report={'passed':True,'plan_hash':h,'frozen_plan_sha256':sha(FROZEN),'production_authority_created':False,'model_requests':0,'credentials_read':False,'raw_recorded_retrieval_payload_identical':True,'only_baseline_change':'remove locagent_retrieve from tool list','prior_calls':4,'prior_evidence_bytes':5346,'remaining_calls':12,'remaining_evidence_bytes':8990,'remaining_investigation_responses':1,'requests_per_arm':1,'requests_total':2,'budget_cny':5,'full_reservations_cny':4.227072,'offline_tests_passed':18,'historical_files_unchanged':len(before),'pricing_public_checked_date':'2026-11-14','pricing_source':'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/','public_model_reference':'DeepSeek-V4.1-Flash-1017','peak_input_cache_miss_cny_per_million':2,'peak_output_cny_per_million':8,'account_price_check':'pending_before_user_authorized_launch','wire_bytes':{arm:len(request(arm)) for arm in ('baseline','retrieval')},'tool_results_will_not_be_executed':True,'final_followup_requests':0}
save_new(OUT/'acceptance.json',report);print(json.dumps(report,ensure_ascii=False))
