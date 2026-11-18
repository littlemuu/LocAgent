"""Offline annotation only; never alters the original harness score."""
import hashlib,json,re
from pathlib import Path
P=Path(__file__).resolve().parents[1]
history=P.parent/'dev24-completion-20261117-v5/delivery/environment-observations.json'
data=json.loads(history.read_text())
case=P/'evidence/run/trial/psf__requests-2317/C/harness'
reports=list(case.rglob('report.json'));outputs=list(case.rglob('test_output.txt'))
if reports:
 r=json.loads(reports[0].read_text())['psf__requests-2317']
 text=outputs[0].read_text(errors='replace') if outputs else ''
 data['C']={'resolved':r['resolved'],'tests':{k:{s:len(ids) for s,ids in v.items()} for k,v in r.get('tests_status',{}).items()},'ssl_certificate_verify_failed':'CERTIFICATE_VERIFY_FAILED' in text,'pytest_summary':[line for line in text.splitlines() if re.search(r'=+ .*\b(?:passed|failed)\b.* in ',line)],'report_path':str(reports[0]),'test_output_path':str(outputs[0]) if outputs else None}
 data['C']['additional_patch_regression']={'test':'RequestsTestCase.test_basic_building','observed':"'NoneType' object has no attribute 'decode'" in text,'reason':'C additionally changed PreparedRequest.prepare_method to call to_native_string(method) before its None guard; original harness records None.decode AttributeError. This is separate from certificate failures.'}
else:data['C']={'status':'未评分或未运行','resolved':None}
data['historical_source']={'path':str(history),'sha256':hashlib.sha256(history.read_bytes()).hexdigest()}
data['policy']='Preserve original harness resolved scoring; no rerun, certificate change, or rescoring. Environment signals do not prove exclusive cause.'
(P/'delivery/environment-observations.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(data['C'],ensure_ascii=False))
