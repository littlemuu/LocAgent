"""Offline hash freeze, exact B comparison and estimate from named v5 summary."""
import csv,difflib,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT.parent
sys.path[:0]=[str(ROOT),str(ROOT/'baseline'),str(ROOT/'baseline/runtime')]
from locagent_e2e.driver import config_binding
from locagent_e2e.common import CONFIG,digest
from locagent_e2e.locator_policy import SDK_SYSTEM
from experiments.sdk_finish_selfcheck_v7.finish_policy import SELF_CHECK_INSTRUCTION
from calibration.policy import INSTRUCTION
EXPECTED='a02c0341ebddeba3718d9d4a00e8485e35a62944f088cac982f6c817b7160036'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data):p.write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
assert config_binding()==EXPECTED
provenance=json.loads((ROOT/'delivery/baseline-provenance.json').read_text())
comparisons=[]
for rel in provenance['selected_files']:
    old=PROJECT/'cloud-checkpoint-20261117-v4/runtime'/rel;new=ROOT/'baseline'/rel
    assert old.read_bytes()==new.read_bytes(),rel
    comparisons.append(dict(path=rel,B_sha256=sha(old),C_dependency_sha256=sha(new),identical=True))
# Hash source freeze records without editing/re-serializing those records.
historical={str(p.relative_to(PROJECT)):sha(p) for p in [PROJECT/'cloud-checkpoint-20261117-v4/runtime/CHECKPOINT_FREEZE.json',PROJECT/'cloud-checkpoint-20261117-v4/runtime/CLOUD_FREEZE.json',PROJECT/'cloud-checkpoint-20261117-v4/runtime/FREEZE.json',PROJECT/'dev24-completion-20261117-v5/delivery/SHA256SUMS.json']}
config=dict(version='locator-diagnostic-calibration-v8',arm='C',baseline_binding=EXPECTED,
            execution_status='offline_acceptance_only_live_C_not_run',experiment=CONFIG,
            entrypoint='calibration.locator.run',packet_builder='calibration.locator.build_packet',
            coding_entrypoint='locagent_e2e.agent.run (byte-identical frozen copy)',
            retrieval='unchanged v6 identifier BM25 and source preview; v7 candidate format/selfcheck',
            locator_changes=dict(prompt_sha256=digest(SDK_SYSTEM+'\n'+SELF_CHECK_INSTRUCTION+'\n'+INSTRUCTION),
                                 coverage='delivered characters only; AST spans for completeness, not source evidence',
                                 finish='three sections; conservative hypotheses; invalid answer replaced locally; raw retained',
                                 body_read_priority='from request 2, unresolved read cursor or incomplete returned entity blocks further list/search/retrieve; read_file and finish retain availability',
                                 retry_requests=0,chain_completeness='unverified',
                                 candidate_lists='unchanged',tool_schema='unchanged'),
            immutable_runtime_observations=dict(coding={'Memory':6442450944,'NanoCpus':6000000000,'NetworkMode':'none'},
                                                harness={'Memory':0,'NanoCpus':0,'NetworkMode':'bridge'},stuck_detection=False),
            live_execution_authorized=False,holdout_access=False)
write(ROOT/'config.json',config)
changed=[dict(path='calibration/locator.py',purpose='only C locator SDK loop, evidence tracking and version-1 packet builder'),dict(path='calibration/policy.py',purpose='locator instructions, delivered evidence ledger and diagnostic calibration')]
write(ROOT/'delivery/B-C-COMPARISON.json',dict(baseline_binding=EXPECTED,baseline_files= comparisons,
    baseline_files_modified=0,new_locator_code=changed,new_config_sha256=sha(ROOT/'config.json'),
    historical_freezes_sha256=historical,tool_schema_comparison='actual SDK/wire equality tested',
    coding_contract_comparison='actual first request equality after replacing only localization_packet tested',
    harness_container_config_changed=False,hybrid_v8_imported=False))
# No repository-wide diff/search: named frozen agent vs C locator is the reviewable extraction diff.
b=(ROOT/'baseline/locagent_e2e/agent.py').read_text().splitlines(True)
c=(ROOT/'calibration/locator.py').read_text().splitlines(True)
(ROOT/'delivery/B-agent-to-C-locator.diff').write_text(''.join(difflib.unified_diff(b,c,fromfile='B/frozen/locagent_e2e/agent.py (UNCHANGED)',tofile='C/new/calibration/locator.py (locator-only extraction)')))
summary_path=PROJECT/'dev24-completion-20261117-v5/delivery/summary.json'
s=json.loads(summary_path.read_text());rows=[r for r in s['trial_rows'] if r['arm']=='B']
assert len(rows)==len({r['instance_id'] for r in rows})==24
keys=['requests','input_tokens','output_tokens','metered_cny','upper_cny']
parts={part:{k:sum(r[part][k] for r in rows) for k in keys} for part in ['coding_cost','localization_cost','total_cost']}
assert parts['total_cost']==s['arms']['B']['totals']
b_time=sum(r['total_seconds'] for r in rows);loc_time=sum(r['localization_seconds'] for r in rows)
a_time=s['arms']['A']['wall_seconds_including_locator']
overhead=s['combined_trial_wall_seconds']-a_time-b_time
scenarios=[]
for fraction,label in [(0,'B task timing only; no allocated shared image/cleanup overhead'),(.5,'half historical A+B shared overhead allocated to C'),(1,'all historical shared overhead allocated to C')]:
    seconds=b_time+fraction*overhead;cloud=seconds/3600*4.09
    scenarios.append(dict(assumption=label,seconds=seconds,minutes=seconds/60,cloud_cny_at_historical_quote=cloud,total_cny_same_API_mix=cloud+parts['total_cost']['metered_cny']))
estimate=dict(status='未运行',source=str(summary_path),source_sha256=sha(summary_path),method='sum 24 individual B rows; no A/B rerun',
    measured_B=parts,B_locator_seconds=loc_time,B_coding_and_evaluation_seconds=b_time-loc_time,B_total_seconds=b_time,
    historical_AB_shared_overhead_seconds=overhead,scenarios=scenarios,
    same_usage_all_peak_cache_miss_reference_cny=parts['total_cost']['upper_cny'],
    warning='Historical prices only; not current quote or bill, not a guaranteed upper bound for changed C token usage.',
    max_requests_unchanged=24*(40+4),unknowns=['C coding trajectories','prompt/output token changes','cache hits and time bands','image cache/download speed','host boot/setup','network traffic','stopped disk charges'],
    C_live_requests=0,C_resolve_rate='未运行',account_or_cloud_queried=False)
write(ROOT/'delivery/C-RUN-ESTIMATE.json',estimate)
with (ROOT/'delivery/B-measured-per-task.csv').open('w',newline='') as f:
    fields=['instance_id','coding_requests','locator_requests','input_tokens','output_tokens','metered_cny','upper_cny','coding_evaluation_seconds','locator_seconds','total_seconds']
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
    for r in rows:writer.writerow(dict(instance_id=r['instance_id'],coding_requests=r['coding_cost']['requests'],locator_requests=r['localization_cost']['requests'],**{k:r['total_cost'][k] for k in ['input_tokens','output_tokens','metered_cny','upper_cny']},coding_evaluation_seconds=r['wall_seconds'],locator_seconds=r['localization_seconds'],total_seconds=r['total_seconds']))
# Narrow, explicit directories in this NEW package only; no dataset discovery.
paths=[ROOT/'config.json']+[ROOT/'baseline'/s for s in provenance['selected_files']]
for directory in ['calibration','tests','scripts']:
    paths+=sorted((ROOT/directory).glob('*.py'))
files={str(p.relative_to(ROOT)):sha(p) for p in paths}
binding=digest(files)
write(ROOT/'FREEZE.json',dict(version=config['version'],baseline_binding=EXPECTED,config_sha256=sha(ROOT/'config.json'),
    v8_code_and_config_binding=binding,hash_algorithm='SHA256 canonical sorted compact UTF8 JSON of relative-path -> file SHA256 mapping',files=files,
    scope='new independent locator calibration; excludes generated reports/logs; historical freeze files read-only'))
print(json.dumps(dict(config_sha256=sha(ROOT/'config.json'),binding=binding,unchanged_baseline_files=len(comparisons),B_measured=parts,B_seconds=b_time,overhead_seconds=overhead,scenarios=scenarios),ensure_ascii=False,indent=2))
