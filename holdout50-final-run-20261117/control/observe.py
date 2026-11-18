"""Record actual resources without exposing any task results to the monitor."""
import json,subprocess,time
from support import P,durable
seen=set()
while not (P/'run.exit').exists():
 try:
  ids=subprocess.check_output(['docker','ps','-q'],text=True).split()
  if ids:
   for r in json.loads(subprocess.check_output(['docker','inspect',*ids])):
    if r['Id'] in seen:continue
    if not r['Name'].startswith(('/locagent-e2e-','/sweb.eval.')):continue
    seen.add(r['Id']);h=r['HostConfig'];actual=(h['Memory'],h['NanoCpus'],h['NetworkMode'])
    expected=(6442450944,6000000000,'none') if r['Name'].startswith('/locagent-e2e-') else (0,0,'bridge')
    row={'at':time.time(),'container_id':r['Id'],'name':r['Name'],'image':r['Image'],'Memory':h['Memory'],'NanoCpus':h['NanoCpus'],'NetworkMode':h['NetworkMode'],'matches_frozen_observation':actual==expected}
    with (P/'resource-observations.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    if actual!=expected:durable(P/'RESOURCE_DEVIATION.json',row)
 except Exception as e:
  with (P/'observer-errors.jsonl').open('a') as f:f.write(json.dumps({'at':time.time(),'error':type(e).__name__})+'\n')
 time.sleep(1)
