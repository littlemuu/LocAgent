"""Read only selected dev24 v5 result/locator logs; do not read holdout."""
import hashlib,json,tarfile
from pathlib import Path
P=Path(__file__).resolve().parents[1];R=P.parent;D=R/'dev24-completion-20261117-v5/delivery'
s=json.loads((D/'summary.json').read_text());a=json.loads((P/'authorization.json').read_text());ids=a['trial_ids']
assert s['code_binding']==a['baseline_binding']
assert [r['instance_id'] for r in s['trial_rows'] if r['arm']=='A']==ids
assert [r['instance_id'] for r in s['trial_rows'] if r['arm']=='B']==ids
sources={};records=[]
for filename in ['first8-evidence-v4.tar.gz','remaining16-evidence-v5.tar.gz']:
 path=D/filename;sources[filename]=hashlib.sha256(path.read_bytes()).hexdigest()
 with tarfile.open(path) as t:
  for m in t.getmembers():
   matches=[i for i in ids if ('/trial/'+i+'/locator/result.json') in '/'+m.name]
   if not m.isfile() or not matches:continue
   ident=matches[0];r=json.load(t.extractfile(m));target=P/'history/B-locator'/ident/'result.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
   errors=[{'index':n,'arguments':x['arguments'],'error':x['result']['error'],'error_type':x['result'].get('error_type')} for n,x in enumerate(r['tool_audit'],1) if x['tool']=='read_file' and isinstance(x['result'],dict) and 'error' in x['result']]
   records.append({'instance_id':ident,'read_file_error_count':len(errors),'errors':errors,'archive':filename,'member':m.name})
assert len(records)==24
records.sort(key=lambda x:ids.index(x['instance_id']))
(P/'history').mkdir(exist_ok=True)
(P/'history/v5-summary.json').write_bytes((D/'summary.json').read_bytes())
(P/'history/B-read-file-errors.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
(P/'history/provenance.json').write_text(json.dumps({'archives_sha256':sources,'summary_sha256':hashlib.sha256((D/'summary.json').read_bytes()).hexdigest(),'ids_in_v5_order':ids,'A_B_rerun':False},indent=2)+'\n')
print(json.dumps({'A_resolved':s['arms']['A']['resolved'],'B_resolved':s['arms']['B']['resolved'],'B_read_file_errors':sum(x['read_file_error_count'] for x in records),'affected':[x['instance_id'] for x in records if x['read_file_error_count']]},ensure_ascii=False))
