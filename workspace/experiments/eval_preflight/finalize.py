"""Freeze the pre-evaluation audit and conditional pilot proposal; no approval."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'verification/eval-preflight-v2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,x):
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2)
def main():
 a=read(OUT/'acceptance.json');c=read(OUT/'cohort-semantic-audit.json');v4=read(ROOT/'engine_adaptation/v4/adapted-manifest.json')
 assert a['sdk_pair_completed'] and a['native_connectivity_finished'] and a['cache_hash_tamper_blocked']
 assert all(sha(ROOT/'engine_adaptation/v4/engine'/n)==h for n,h in v4['engine']['files'].items())
 assert all(sha(ROOT/n)==h for n,h in v4['harness_files'].items())
 before=read(ROOT/'verification/engine-compatibility-v1/preflight.json')['protected_before']
 changed=[p for p,h in before.items() if sha(Path(p))!=h]
 expected={'bridge.py','core.py','locagent.py','locagent_worker.py','openhands_replay.py','preparation.py'}
 assert {Path(p).name for p in changed}==expected
 assert all(Path(p).parent==ROOT/'readonly_agent' for p in changed)
 sample=c['next_review_sample']['ids']
 save(OUT/'semantic-review-template.json',{'seed':c['next_review_sample']['seed'],'development_only':True,
  'stages':['Freeze selected tasks before looking at labels/results.','Read issue + fixed base source; write an initial localization rationale without patch or run outputs.',
   'Reveal reference patch/labels in scoring-only context; check exact base spans, relevant changes, newly added symbols and alternative valid locations.',
   'Record title/body/patch mismatch, external-link dependence, ambiguity and exposure; use a second independent reviewer and adjudicate disagreements before eligibility.'],
  'rows':[{'id':i,'reviewer':None,'initial_rationale':None,'reference_consistency':None,'alternative_valid_locations':None,
   'semantic_decision':'pending','exposure_decision':'pending','adjudication':None} for i in sample],
  'not_blind_review_claimed':True,'no_promotion_from_dev_to_holdout':True})
 save(OUT/'conditional-live-proposal.json',{'status':'not_executable_pending_offline_gates_and_fresh_consent',
  'case':'tobymao__sqlglot-3417','exposed_development_only':True,
  'intended_system_pair':['locally_modified_LocAgent_bounded_v1','OpenHands_with_v4_cached_LocAgent'],
  'distinct_verified_control_pair':['OpenHands_basic_file_tools','OpenHands_basic_plus_cached_LocAgent'],
  'model':'deepseek-flash','family_reference_only':'DeepSeek-V4.1-Flash-1017','endpoint':'https://api.deepseek.com/chat/completions',
  'temperature':0,'thinking':'disabled','max_output_tokens':2048,'max_requests_per_arm':4,'max_requests_total':8,
  'reserve_final_request_for_finish':True,'max_tool_calls_per_arm':16,'source_response_json_bytes_per_arm':14336,'page_response_json_bytes':4096,
  'source_snapshot':v4['cases'][next(i for i,r in enumerate(v4['cases']) if r['id']=='tobymao__sqlglot-3417')]['source_snapshot'],
  'budget_cny':17,'historical_assumption_input_cny_per_million':2,'historical_assumption_output_cny_per_million':8,
  'reservation_micro_cny_per_request':2113536,'eight_request_reservation_micro_cny':16908288,
  'prices_currently_verified':False,'account_price_verified':False,'approval':False,
  'send':['issue','system/task instructions','tool schemas','selected source evidence','that arm conversation history'],
  'do_not_send':['reference labels','reference patch','semantic review notes','other tasks','keys or environment files'],
  'blocking_gates':['Define whether comparing complete agent systems or retrieval availability; do not conflate.',
   'Connect and validate the native source-body retrieval backend or explicitly redefine and rename the baseline.',
   'Align page/total source accounting, cumulative tool cap, output top-k and wire output-token/closing policy.',
   'Bind both systems to one durable admission/budget/timeout/no-repeat path and freeze a new executable manifest.',
   'Review development-task semantic scope, verify current account prices and obtain approval for the precise data/destination/budget.'],
  'retry':False,'parallel_model_calls':False,'start_order_policy':'freeze before run; one pair cannot establish order-independent benefit'})
 files=[p for p in (ROOT/'experiments/eval_preflight').glob('*.py')]+[ROOT/'tests/test_eval_metrics.py',ROOT/'tests_sdk/test_preparation.py']
 save(OUT/'execution-lock.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in files},'engine_hash':v4['engine']['hash'],
  'harness_files':v4['harness_files'],'adapted_manifest_sha256':sha(ROOT/'engine_adaptation/v4/adapted-manifest.json'),
  'run_proposal_hash':a['plan_hash'],'metrics_version':'localization-metrics-v1'})
 save(OUT/'observed-tests.json',{'metric_unit_tests':{'command':'.venv-openhands/bin/python -B -m unittest discover -s tests -p test_eval_metrics.py','passed':10},
  'budget_wire_regression':{'command':'.venv-openhands/bin/python -B -m unittest discover -s tests_sdk -p test_preparation.py','passed':18},
  'sdk_pair_mock_requests':8,'native_loop_mock_responses':4,'earlier_v1_additional_sdk_mocks':8,'earlier_v1_native_mocks':4,
  'real_model_requests':0,'quality_scores_generated':False})
 save(OUT/'preservation.json',{'v4_engine_and_harness_unchanged':True,'legacy_protected_non_harness_files_unchanged':len(before)-len(changed),
  'prior_six_adaptation_changes_not_new_this_round':changed,'historical_results_not_rescored':True})
 print('Frozen preflight; scientific/live readiness remains blocked, not approved.')
if __name__=='__main__':main()
