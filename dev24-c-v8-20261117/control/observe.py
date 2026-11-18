import json,subprocess,time
from pathlib import Path
p=Path('/home/ubuntu/dev24-c-v8-20261117');seen=set()
while not (p/'run.exit').exists():
 try:
  ids=subprocess.check_output(['docker','ps','-q'],text=True).split()
  if ids:
   data=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True))
   for r in data:
    name=r['Name']
    if not name.startswith(('/locagent-e2e-','/sweb.eval.')) or r['Id'] in seen:continue
    seen.add(r['Id']);h=r['HostConfig'];row=dict(at=time.time(),name=name,image=r['Image'],Memory=h['Memory'],NanoCpus=h['NanoCpus'],NetworkMode=h['NetworkMode'])
    with (p/'resource-observations.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 except Exception as e:
  with (p/'resource-observations.jsonl').open('a') as f:f.write(json.dumps({'monitor_error':type(e).__name__,'at':time.time()})+'\n')
 time.sleep(10)
