import ast,hashlib,json,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[2];O=R/'dev24-v82-offline-replay-20261117';old=R/'locator-diagnostic-calibration-v8.1';new=R/'locator-diagnostic-calibration-v8.2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
inputs=json.loads((O/'input-sha256.json').read_text());assert all(sha(R/p)==h for p,h in inputs.items())
f=json.loads((old/'FREEZE.json').read_text());assert all(sha(old/p)==h for p,h in f['files'].items())
shutil.copyfile(O/'OLD_TEST_CHANGES_ZH.md',new/'tests/TEST_CHANGES_V82.md')
added=['tests/test_v82.py','tests/fixtures/v81-recorded24.json','tests/fixtures/v81-reviewed55.json','tests/TEST_CHANGES_V82.md']
actual={p:sha(new/p) for p in [*f['files'],*added]}
changed=[p for p in f['files'] if actual[p]!=f['files'][p]]
assert set(changed)=={'calibration/policy.py','tests/test_calibration.py','tests/test_v81.py'}
assert all(actual[p]==h for p,h in f['files'].items() if p.startswith('baseline/'))
proof=json.loads((new/'delivery/B-C-COMPARISON.json').read_text())
for row in proof['baseline_files']:
 assert sha(R/'cloud-checkpoint-20261117-v4/runtime'/row['path'])==row['B_sha256']==sha(new/'baseline'/row['path'])
for p,h in proof['historical_freezes_sha256'].items():assert sha(R/p)==h
base=json.loads((new/'delivery/baseline-tests.json').read_text());tests=json.loads((new/'delivery/new-tests.json').read_text())
for t in [base,tests]:assert t['failures']==t['errors']==t['skipped']==0 and not t['blocked_external_actions']
assert base['tests']==22 and tests['tests']==62
# No v8.1 bytecode/cache or prior delivery evidence is copied into the freeze.
for p in new.rglob('__pycache__'):shutil.rmtree(p)
binding=digest(actual)
freeze={'version':'locator-diagnostic-calibration-v8.2','parent_v81_binding':f['v8_1_code_and_config_binding'],'parent_v8_binding':f['parent_v8_binding'],'baseline_binding':f['baseline_binding'],'config_sha256':f['config_sha256'],'files':actual,'v8_2_code_and_config_binding':binding,'v8_code_and_config_binding':binding,'hash_algorithm':f['hash_algorithm'],'scope':'Offline-only v8.2 soft final-answer gating. No authorization to start cloud/model/Coding Agent/harness. Inherited config and prompt bytes unchanged; actual final policy identified here and in diagnostic-audit.policy.','final_policy':{'hard_fallback':['R2','validator_error'],'soft_disclosure':['R1','R3','R4'],'original_answer_preserved_except_hard_fallback':True,'investigation_policy_unchanged_from_v81':True}}
write(new/'FREEZE.json',freeze)
change={'parent_v81_unchanged':True,'changed_existing_files':changed,'added_tests_and_fixtures':added,'unchanged_baseline_files':sum(p.startswith('baseline/') for p in f['files']),'original_B_files_verified':len(proof['baseline_files']),'only_runtime_change':'calibration/policy.py','locator_entrypoint_unchanged':actual['calibration/locator.py']==f['files']['calibration/locator.py'],'config_unchanged':actual['config.json']==f['files']['config.json'],'prompt_notice_read_priority_unchanged':True,'coding_retrieval_budget_harness_unchanged':True,'binding':binding,'tests':{'original':22,'v8':22,'v81':11,'v82':29,'total':84},'mock_protocol_tests_only':True,'live_Coding_Agent':'未运行','harness':'未运行','API_calls':0,'cloud_started':False}
write(new/'delivery/V8.2-CHANGE-AUDIT.json',change)
print(json.dumps(change,ensure_ascii=False,indent=2))
