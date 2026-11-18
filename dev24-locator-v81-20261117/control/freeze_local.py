import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];old=ROOT/'locator-diagnostic-calibration-v8';new=ROOT/'locator-diagnostic-calibration-v8.1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=json.loads((old/'FREEZE.json').read_text());assert all(sha(old/p)==h for p,h in f['files'].items())
files=list(f['files'])+['tests/test_v81.py','tests/fixtures/sympy-21379-response-4.json']
actual={p:sha(new/p) for p in files};changed=[p for p in f['files'] if actual[p]!=f['files'][p]]
assert set(changed)=={'calibration/policy.py','tests/test_calibration.py'}
assert all(actual[p]==h for p,h in f['files'].items() if p.startswith('baseline/'))
binding=digest(actual)
freeze=dict(version='locator-diagnostic-calibration-v8.1',parent_v8_binding=f['v8_code_and_config_binding'],baseline_binding=f['baseline_binding'],config_sha256=f['config_sha256'],files=actual,v8_1_code_and_config_binding=binding,v8_code_and_config_binding=binding,hash_algorithm=f['hash_algorithm'],scope='Independent v8.1; inherited config/prompt unchanged; current locator-only live authorization is external to frozen runtime')
write(new/'FREEZE.json',freeze)
proof=dict(parent_v8_unchanged=True,changed_existing_files=changed,added_tests=files[-2:],unchanged_baseline_files=sum(p.startswith('baseline/') for p in f['files']),locator_py_unchanged=actual['calibration/locator.py']==f['files']['calibration/locator.py'],coding_retrieval_budget_harness_unchanged=True,config_and_prompt_inherited_from_v8=True,binding=binding,tests=dict(original=22,v8=22,new=11,total=55),v8_test_adjustment='Bare helper-name negative test now verifies no inferred full entity; other 21 tests unchanged',replay_scope='real provider final answer + synthetic source coverage; no API or quality score')
write(new/'delivery/V8.1-CHANGE-AUDIT.json',proof)
package=ROOT/'dev24-locator-v81-20261117';deploy=package/'frozen'
for p in files+['FREEZE.json']:
 target=deploy/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(new/p,target)
(deploy/'delivery').mkdir(exist_ok=True)
m=json.loads((new/'baseline/data/dev24/manifest.json').read_text())
auth=dict(approved=True,scope='dev24 C(v8.1) locator only once; explicit user authorization 2026-11-17',budget_cny=5,trial_ids=m['selection_order'],ids_sha256=m['ids_sha256'],v81_binding=binding,baseline_binding=f['baseline_binding'],concurrency=1,repetitions=1,automatic_retries=0,holdout=False,coding_agent=False,harness=False,stop_after='locator_precheck',delete_remote_credential=True,shutdown_mode='STOP_CHARGING')
write(package/'authorization.json',auth)
print(json.dumps(proof,ensure_ascii=False,indent=2))
