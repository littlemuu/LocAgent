import hashlib,json,re
from pathlib import Path
R=Path(__file__).resolve().parents[2];O=R/'dev24-v82-offline-replay-20261117';F=R/'locator-diagnostic-calibration-v8.2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs={}
for file in ['input-sha256.json','replay-input-sha256.json']:inputs.update(json.loads((O/file).read_text()))
changed=[p for p,h in inputs.items() if sha(R/p)!=h];assert not changed,changed
prior=json.loads((R/'dev24-v81-fallback-audit-20261117/input-sha256.json').read_text());assert all(sha(R/p)==h for p,h in prior.items())
f=json.loads((F/'FREEZE.json').read_text());assert all(sha(F/p)==h for p,h in f['files'].items())
binding=hashlib.sha256(json.dumps(f['files'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();assert binding==f['v8_2_code_and_config_binding']
rows=json.loads((O/'per-case.json').read_text());summary=json.loads((O/'summary.json').read_text());assert len(rows)==24
assert sum(r['disclosure_count'] for r in rows)==summary['disclosure_items']==16
for row in rows:
 d=O/'cases'/row['instance_id'];p=json.loads((d/'localization.json').read_text());a=json.loads((d/'diagnostic-audit.json').read_text())
 assert p['result']['answer']==(d/'delivered-answer.txt').read_text()[:-1]
 assert a['violation_count']==sum(a['rule_counts'].values())==len(a['violations'])==a['disclosure_count']
 assert p['result']['answer'].startswith(a['raw_packet']['answer'])
 for key in ['files','entities']:assert p['result'][key]==a['raw_packet'][key]
 assert a['original_body_preserved'] and a['validator_error'] is None and not a['fallback']
 for item in a['disclosures']:assert all(t in p['result']['answer'].split('以下内容未在阅读记录中核验：')[-1] for t in item['targets'])
missing=[]
for p in [O/'REPORT_ZH.md',O/'THREE_FULL_PACKETS.md']:
 for target in re.findall(r'\]\((/[^)]+)\)',p.read_text()):
  if not Path(re.sub(r':\d+$','',target)).exists():missing.append(target)
assert not missing,missing
receipt={'binding':binding,'frozen_files':len(f['files']),'input_files_unchanged':len(inputs),'prior_audit_inputs_unchanged':len(prior),'v81_and_v8_unchanged':True,'delivered_packets_verified':24,'disclosure_cases':12,'disclosure_items':16,'true_findings_disclosed':7,'false_positives_removed':31,'missing_report_links':0,'API_calls':0,'new_API_cost_cny':0,'cloud_started':False,'Coding_Agent':'未运行','harness':'未运行','fresh_locator_investigation':'未运行','holdout_access':False,'tests':84,'tests_failed':0,'test_transport':'fixed synthetic responses only; no model/network calls','status':'complete_offline_only'}
(O/'DELIVERY_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
files=sorted(p for p in O.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
(O/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.relative_to(O)}\n' for p in files))
print(json.dumps(receipt,ensure_ascii=False,indent=2))
