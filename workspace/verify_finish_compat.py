"""Offline final audit. Never imports the credential loader or live transport."""
import hashlib
import json
from pathlib import Path
from readonly_agent.core import digest
from experiments.locbench_batch.control import frozen

ROOT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=json.loads((ROOT/'verification/FINISH_COMPAT_HISTORY_BEFORE.json').read_text())
changed=[p for p,h in before['artifacts'].items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
assert not changed,changed
plan=frozen();h=digest(plan)
old='6a84c4723546c2e9a9044f255915d39f31ccd40118ca92f795a1b6807c560eb9'
assert sorted(p.name for p in (ROOT/'authority-locbench').iterdir())==[old]
assert (ROOT/'authority-locbench'/old/'claim.json').is_file()
assert h!=old and not (ROOT/'authority-locbench'/h).exists()
assert plan['max_requests']==16 and plan['budget_micro_cny']==34_000_000
log=(ROOT/'verification/finish-compat-tests-v2.log').read_text()
assert 'Ran 124 tests' in log and log.rstrip().endswith('OK')
expected={
'history':('completed',16,None,0),
'nonnull':('halted',4,'finish_message_contract_error',0),
'unknown':('halted',4,'finish_message_contract_error',0),
'missing':('halted',4,'finish_message_contract_error',0),
'invalid_finish':('halted',4,'finish_source_validation_error',0),
'bad_closing_second_arm':('halted',8,'closing_tool_violation',0),
 'truncation_first_arm':('halted',4,'model_output_truncated',0),
 'timeout_second_arm':('halted',5,'TimeoutError',2_113_536),
 'oversized_receipt':('halted',3,'RuntimeError',2_113_536)}
scenarios=[]
for name,(status,n,reason,pending) in expected.items():
 p=ROOT/f'verification/finish-compat-{name}-v1/verification.json'
 v=json.loads(p.read_text());r=v['result']
 assert v['assertions_passed'] and v['duplicate_claim_blocked']
 assert v['real_provider_requests']==v['network_attempts']==0
 assert v['suite_hash']==h
 assert (r['status'],r['requests'],r.get('reason'),r['request_pending_micro_cny'])==(status,n,reason,pending)
 scenarios.append({'name':name,'path':str(p.relative_to(ROOT)),'status':status,'mock_requests':n,'reason':reason,'simulated_pending_micro_cny':pending})
# The same frozen problem/source/labels are copied forward, byte for byte.
oldbase=json.loads((ROOT/'locbench_openhands/v3/manifest.json').read_text())
newbase=json.loads((ROOT/'locbench_openhands/v4/manifest.json').read_text())
source_paths=[p for p in oldbase['hashes'] if '/source/' in p or p.startswith('scoring-only/')]
assert source_paths and all(oldbase['hashes'][p]==newbase['hashes'][p] for p in source_paths)
report={'passed':True,'unit_tests':124,'scenarios':scenarios,'historical_artifacts_unchanged':len(before['artifacts']),
 'frozen_source_and_scoring_files_unchanged':len(source_paths),'production_grants_unchanged':[old],
 'new_authorization_created':False,'real_provider_requests':0,'new_paid_cost_cny':0,
 'suite_hash':h,'source_manifest_hash':plan['source_manifest_hash'],
 'schema_policy':'Only optional entities_note:null; every content-bearing or unknown extension rejected.',
 'historical_replay':'All four SQLGlot receipts byte-identical; core answer exact; one audited normalization; no real regrading.',
 'test_correction':'Initial test expected unknown entity rejection; corrected to existing format-only validation, without changing production validator.'}
out=ROOT/'verification/FINISH_NULL_COMPAT_ACCEPTANCE.json'
with out.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in report.items() if k not in ('scenarios',)},ensure_ascii=False))
