"""Read-only verification of inputs; writes receipts only within the new audit directory."""
import collections,csv,hashlib,json,re
from pathlib import Path
O=Path(__file__).resolve().parent; R=O.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs=json.loads((O/'input-sha256.json').read_text())
changed=[p for p,h in inputs.items() if sha(R/p)!=h]
assert not changed,changed
frozen={}
for name in ['locator-diagnostic-calibration-v8','locator-diagnostic-calibration-v8.1']:
 d=R/name; f=json.loads((d/'FREEZE.json').read_text())
 mismatches=[p for p,h in f['files'].items() if sha(d/p)!=h]
 assert not mismatches,mismatches
 binding=hashlib.sha256(json.dumps(f['files'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
 assert binding==f['v8_code_and_config_binding']
 frozen[name]={'declared_files_verified':len(f['files']),'binding':binding,'mismatches':mismatches}
cs=json.loads((O/'cases.json').read_text()); vs=json.loads((O/'violations-reviewed.json').read_text())
assert len(cs)==24 and sum(c['fallback'] for c in cs)==20
assert len(vs)==55 and len({v['id'] for v in vs})==55
assert collections.Counter(v['classification'] for v in vs)=={'真违规':7,'误判':31,'边界':17}
assert len(list(csv.DictReader((O/'answer-paths.csv').open())))==24
assert len(list(csv.DictReader((O/'violations.csv').open())))==55
for c in cs:
 a=json.loads(Path(c['raw_audit_path']).read_text())
 assert a['raw_packet']==c['raw_packet']
 assert Path(c['raw_answer_path']).read_text()==a['raw_packet']['answer']+'\n'
 matched=False
 for p in c['raw_finish_wire_paths']:
  for choice in json.loads(Path(p).read_text())['choices']:
   for call in choice['message'].get('tool_calls',[]):
    if call['function']['name']=='finish':
     p=json.loads(call['function']['arguments'])['message'];p=json.loads(p) if isinstance(p,str) else p
     matched |= p==a['raw_packet']
 assert matched,c['instance_id']
 assert (O/'cases'/c['instance_id']/'audit.md').exists()
missing=[]
for p in O.rglob('*.md'):
 for target in re.findall(r'\]\((/[^)]+)\)',p.read_text()):
  path=re.sub(r':\d+$','',target)
  if not Path(path).exists():missing.append(path)
assert not missing,missing
receipt={'input_files_unchanged':len(inputs),'frozen':frozen,'provider_answers_verified':24,'violation_records':55,'case_pages':24,'broken_local_links':len(missing),'network_calls':0,'API_calls':0,'cloud_started':False,'locator_rerun':False,'Coding_Agent':'未运行','harness':'未运行','runtime_tests':'未运行','holdout_access':False,'verification':'Only local log/code parsing, hashes, output consistency; no frozen runtime imported or executed.'}
(O/'AUDIT_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
files=sorted(p for p in O.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
(O/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.relative_to(O)}\n' for p in files))
print(json.dumps(receipt,ensure_ascii=False,indent=2))
