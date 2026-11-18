import hashlib,json,shutil
from pathlib import Path
P=Path(__file__).resolve().parents[1];R=P.parent;src=R/'locator-diagnostic-calibration-v8.2';dst=P/'frozen'
f=json.loads((src/'FREEZE.json').read_text())
for p,h in f['files'].items():
 assert hashlib.sha256((src/p).read_bytes()).hexdigest()==h,p
 t=dst/p;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/p,t)
shutil.copyfile(src/'FREEZE.json',dst/'FREEZE.json');(dst/'delivery').mkdir(exist_ok=True)
# Evaluator-only labels remain separate and are never passed to locator/coding.
evalpath=R/'dev24-c-v8-20261117/frozen/baseline/data/dev24/content/evaluator.json'
receipt=json.loads((dst/'baseline/data/dev24/content/receipt.json').read_text())
assert hashlib.sha256(evalpath.read_bytes()).hexdigest()==receipt['files']['evaluator.json']
shutil.copyfile(evalpath,dst/'baseline/data/dev24/content/evaluator.json')
m=json.loads((dst/'baseline/data/dev24/manifest.json').read_text())
a={'approved':True,'scope':'User-authorized dev24 C(v8.2) complete once; current request supersedes prior offline-only scope without modifying frozen files','v82_binding':f['v8_2_code_and_config_binding'],'baseline_binding':f['baseline_binding'],'budget_cny':15,'trial_ids':m['selection_order'],'ids_sha256':m['ids_sha256'],'arm_order':['C'],'concurrency':1,'repetitions':1,'automatic_retries':0,'max_trial_episodes':24,'holdout':False,'retain_image_cache':True,'delete_remote_credential':True,'shutdown_mode':'STOP_CHARGING','A_B_rerun':False,'stop_after':'report'}
(P/'authorization.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
shutil.copyfile(R/'dev24-locator-v81-20261117/known_hosts',P/'known_hosts')
print('Verified v8.2; prepared independent deployment copy and current authorization.')
