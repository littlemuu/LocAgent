"""Zero-paid-request gate. Inspect installed software and actual disposable containers.
No coding, localization, test patch application or harness scoring is performed.
"""
import importlib.metadata as md,inspect,json,logging,os,platform,subprocess,sys,time
from pathlib import Path
from unittest.mock import patch
from support import P,F,MIN_FREE,IDS,verify,load,sha,durable,check_free,free_bytes

def resources(container):
 row=json.loads(subprocess.check_output(['docker','inspect',container]))[0];h=row['HostConfig']
 return {'Memory':h['Memory'],'NanoCpus':h['NanoCpus'],'NetworkMode':h['NetworkMode'],'image_id':row['Image']}

def main():
 record={'status':'failed','at':time.time(),'API_calls':0,'harness_test_executions':0}
 try:
  record['bindings']=verify();assert platform.system()=='Linux' and platform.machine()=='x86_64'
  record['packages']={k:md.version(k) for k in ['openhands-sdk','swebench','bm25s','PyStemmer','pyarrow']}
  assert record['packages']=={'openhands-sdk':'1.62.0','swebench':'3.0.0','bm25s':'0.2.3','PyStemmer':'2.2.0.3','pyarrow':'18.0.0'},'installed_package_version_deviation'
  direct=json.loads(md.distribution('swebench').read_text('direct_url.json'))
  commit=direct['url'].rsplit('/',1)[-1];assert commit=='d83e1001739f4d96add351d9ec0d56f4594a0d82'
  assert direct['archive_info']['hashes']['sha256']=='c5be730adf22e403f3e350e1ea81810576a1443eda76ec98f39896d26c1cdcdf'
  record['harness_commit']=commit
  from locagent_e2e.common import CONFIG
  assert CONFIG['coding']['max_requests']==40 and CONFIG['locator']['max_requests']==4
  assert 'stuck_detection=False' in (F/'baseline/locagent_e2e/agent.py').read_text()
  record['cpu_count']=os.cpu_count();assert record['cpu_count']==16,'host_CPU_deviation'
  memory=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemTotal:')))*1024
  record['host_memory_bytes']=memory;assert 60*1024**3<=memory<=65*1024**3,'host_memory_deviation'
  assert not subprocess.check_output(['docker','ps','-aq'],text=True).strip(),'unexpected_existing_containers'
  record['free_bytes_before']=check_free();record['df']=subprocess.check_output(['df','-B1',str(P)],text=True)
  from locagent_e2e.driver import inspect_image
  cache=[]
  for old in load(P/'expected-cache.json')['images']:
   item=inspect_image('docker',old['image_name']);assert item['id']==old['id'],'preserved_cache_digest_deviation'
   cache.append(item)
  assert len(cache)==24;durable(P/'cache-before.json',{'images':cache,'at':time.time()})
  from locagent_e2e.sandbox import DockerSandbox
  manifest=load(F/'baseline/data/dev24/manifest.json');identifier=manifest['selection_order'][0]
  task=next(r for r in manifest['instances'] if r['instance_id']==identifier)
  from locagent_e2e.driver import image_name
  im=inspect_image('docker',image_name(identifier));box=DockerSandbox(im['id'],task['base_commit'])
  try:
   box.start();record['agent_container']=resources(box.name)
   assert tuple(record['agent_container'][k] for k in ['Memory','NanoCpus','NetworkMode'])==(6442450944,6000000000,'none'),'agent_container_resource_deviation'
  finally:box.close()
  # Exercise the unchanged evaluator's container builder under its original wrappers.
  # Replace only run_instance in this probe process to prevent tests/prediction execution.
  os.environ['LOCAGENT_EVAL_SCOPE']='dev24'
  import evaluation_adapter as ev
  import swebench.harness.run_evaluation as harness
  original_build=harness.build_container;signature=inspect.signature(original_build)
  record['harness_builder_signature']=str(signature)
  class ProbeDone(Exception):pass
  def probe(spec,pred,rm_image,force_rebuild,client,run_id,timeout):
   mapping={'test_spec':spec,'client':client,'run_id':'holdout-resource-probe','logger':logging.getLogger('resource-probe'),'nocache':False,'force_rebuild':False}
   kwargs={k:mapping[k] for k in signature.parameters if k in mapping}
   signature.bind(**kwargs)
   container=harness.build_container(**kwargs)
   try:record['harness_container']=resources(container.id)
   finally:container.remove(force=True)
   raise ProbeDone('resource_only_no_scoring')
  q=P/'preflight-fixture';q.mkdir(exist_ok=False);durable(q/'prediction.json',{'instance_id':identifier,'model_name_or_path':'resource-probe-not-an-experiment','model_patch':''})
  with patch.object(harness,'run_instance',probe):ev.evaluate(identifier,q/'prediction.json',q/'harness',formal=True)
  assert tuple(record['harness_container'][k] for k in ['Memory','NanoCpus','NetworkMode'])==(0,0,'bridge'),'harness_container_resource_deviation'
  assert not subprocess.check_output(['docker','ps','-aq'],text=True).strip(),'probe_left_containers'
  record.update(free_bytes=check_free(),status='passed',coding_budget=CONFIG['coding'],locator_budget=CONFIG['locator'],stuck_detection=False,at_completed=time.time())
 except Exception as e:
  record.update(status='failed',reason=type(e).__name__+': '+str(e)[:800],free_bytes=free_bytes())
 finally:
  durable(P/'remote-preflight.json',record);print(json.dumps(record,ensure_ascii=False))
 if record['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
