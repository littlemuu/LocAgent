"""Zero-API check: edits/tests/diff in a disposable original smoke container."""
from pathlib import Path
import json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from locagent_e2e.common import ROOT,rows,manifest,write_json
from locagent_e2e.driver import inspect_image,image_name
from locagent_e2e.sandbox import DockerSandbox
identifier=sys.argv[1] if len(sys.argv)>1 else manifest()['smoke_ids'][0]; task=next(r for r in rows() if r['instance_id']==identifier)
box=DockerSandbox(inspect_image('docker',image_name(identifier))['id'],task['base_commit'])
start=time.monotonic()
try:
 box.start()
 assert box.patch()=='', 'baseline must be clean before agent edits'
 created=box.file('create','locagent_smoke_fixture.py',content='def add(a,b):\n    return a+b\n')
 assert created['exit_code']==0,created
 edited=box.file('replace','locagent_smoke_fixture.py',old='return a+b',new='return a + b')
 assert edited['exit_code']==0,edited
 tested=box.execute("python -c 'from locagent_smoke_fixture import add; assert add(2,3)==5; print(\"fixture assertion passed\")'")
 assert tested['exit_code']==0,tested
 diff=box.patch();assert 'locagent_smoke_fixture.py' in diff and '+    return a + b' in diff
 write_json(ROOT/('verification/cloud-container-check-'+identifier+'.json'),{'status':'passed','id':identifier,'created':created,'edited':edited,'tested':tested,'patch_bytes':len(diff.encode()),'elapsed_seconds':time.monotonic()-start,'model_calls':0,'fixture_not_a_benchmark_prediction':True})
 print('Container edit, command/test, new-file patch export passed; 0 API calls.')
finally:box.close()
