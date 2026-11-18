"""Read-only cloud preflight plus offline tests; no credentials or API required."""
import importlib.metadata,json,platform,subprocess,sys,time
from pathlib import Path
from run_locator import verify,validate,PACKAGE
result=dict(at=time.time(),freeze=verify(),scope=validate(PACKAGE/'authorization.json')['scope'],platform=platform.system(),architecture=platform.machine())
if result['platform']!='Linux' or result['architecture']!='x86_64':raise RuntimeError('requires_cloud_linux_x86')
result['sdk_version']=importlib.metadata.version('openhands-sdk')
if result['sdk_version']!='1.62.0':raise RuntimeError('sdk_version_changed')
result['containers_before']=subprocess.check_output(['docker','ps','-aq'],text=True).split()
if result['containers_before']:raise RuntimeError('existing_containers_require_review')
result['tests']={}
for mode in ['baseline','new']:
 p=subprocess.run([sys.executable,str(PACKAGE/'frozen/scripts/run_offline.py'),mode],capture_output=True,text=True)
 (PACKAGE/f'preflight-{mode}.log').write_text(p.stdout+p.stderr)
 if p.returncode:raise RuntimeError('offline_tests_failed:'+mode)
 result['tests'][mode]=json.loads((PACKAGE/f'frozen/delivery/{mode}-tests.json').read_text())
if result['tests']['baseline']['tests']!=22 or result['tests']['new']['tests']!=33:raise RuntimeError('test_count_changed')
result.update(status='passed',API_calls=0,coding_agent='未运行',harness='未运行')
(PACKAGE/'preflight.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
