from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from locagent_e2e.common import ROOT,rows,write_json
from locagent_e2e.driver import image_name
from locagent_e2e.sandbox import DockerSandbox
from locagent_e2e.coding_tools import Session
results=[]
for identifier in ['sympy__sympy-21379','astropy__astropy-14182']:
 task=next(r for r in rows() if r['instance_id']==identifier);box=DockerSandbox(image_name(identifier),task['base_commit'])
 try:
  box.start();assert box.source_state()=={} and box.patch()==''
  session=Session(box);session.request_sequence=2
  session.execute('terminal',{'command':"printf 'x=1\\n' > locagent_tracking_fixture.py",'timeout_seconds':10})
  assert session.first_source_edit_request==2,session.audit
  session.request_sequence=3;session.execute('terminal',{'command':'rm locagent_tracking_fixture.py','timeout_seconds':10})
  assert box.source_state()=={} and box.patch()==''
  assert session.first_source_edit_request==2 and len(session.source_edit_events)==2
  results.append({'id':identifier,'status':'passed','first_source_edit_request':2,'empty_after_revert':True,'model_requests':0})
 finally:box.close()
write_json(ROOT/'verification/source-tracking-containers.json',{'status':'passed','results':results});print(results)
