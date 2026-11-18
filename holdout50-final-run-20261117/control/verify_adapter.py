"""Offline contract equivalence, no Docker daemon, tests, model or network calls."""
import importlib,json,os,sys,tempfile,types,hashlib
from pathlib import Path
from support import P,F,IDS,encoded,sha,load,durable,verify
from data_adapter import Dataset

def main():
 verify()
 os.environ['LOCAGENT_EVAL_SCOPE']='dev24'
 from locagent_e2e import evaluation as old
 import evaluation_adapter as new
 source=(F/'baseline/locagent_e2e/evaluation.py').read_text()
 adapted=(P/'control/evaluation_adapter.py').read_text()
 assert source[source.index('def spec_for('):]==adapted[adapted.index('def spec_for('):]
 manifest=load(F/'baseline/data/dev24/manifest.json')
 assert new.DATA.ids==[r['instance_id'] for r in manifest['instances']]
 cases=[]
 # Stubs intercept harness input construction and record exact call parameters.
 # They never execute test suites and return only a synthetic scoring fixture.
 capture={}
 class Containers:
  def create(self,*args,**kwargs):capture['container_create']={'args':args,'kwargs':kwargs};return None
 class Client:
  def __init__(self):self.containers=Containers()
  def close(self):pass
 def make_test_spec(row,**kwargs):
  capture['spec_input']={'row':row,'kwargs':kwargs}
  return types.SimpleNamespace(instance_id=row['instance_id'],arch=None)
 def run_instance(spec,pred,*args,**kwargs):
  capture['run_instance']={'instance_id':spec.instance_id,'arch':spec.arch,'prediction':pred,'positional':[args[0],args[1],'<docker_client>',args[3]],'kwargs':kwargs}
  args[2].containers.create('synthetic-image',command='synthetic-contract-check')
  q=Path('logs/run_evaluation')/args[3]/pred['model_name_or_path'].replace('/','__')/spec.instance_id
  q.mkdir(parents=True,exist_ok=True);(q/'report.json').write_text(json.dumps({spec.instance_id:{'resolved':False}}))
  return None
 modules={}
 for name in ['docker','swebench','swebench.harness','swebench.harness.run_evaluation','swebench.harness.test_spec','swebench.harness.test_spec.test_spec']:
  modules[name]=types.ModuleType(name);modules[name].__path__=[];sys.modules[name]=modules[name]
 for name,m in modules.items():
  if '.' in name:parent,key=name.rsplit('.',1);setattr(modules[parent],key,m)
 modules['docker'].from_env=lambda **kwargs:Client()
 modules['docker'].DockerClient=lambda **kwargs:Client()
 hm=modules['swebench.harness.run_evaluation'];hm.run_instance=run_instance;hm.build_container=lambda *a,**k:None
 modules['swebench.harness.test_spec.test_spec'].make_test_spec=make_test_spec
 with tempfile.TemporaryDirectory(prefix='holdout-adapter-contract-') as td:
  tmp=Path(td)
  for identifier in manifest['selection_order']:
   a=old.dataset_row(identifier);b=new.dataset_row(identifier)
   # Preserve dict insertion order too, not merely structural equality.
   aa=json.dumps(a,ensure_ascii=False).encode();bb=json.dumps(b,ensure_ascii=False).encode();assert aa==bb
   pred={'instance_id':identifier,'model_name_or_path':'contract-fixture','model_patch':''}
   (tmp/'prediction.json').write_text(json.dumps(pred));captures=[]
   for module in (old,new):
    capture.clear();result=module.evaluate(identifier,tmp/'prediction.json',tmp/'harness',formal=True)
    assert result['status']=='completed';captures.append(encoded(capture))
   assert captures[0]==captures[1],identifier
   cases.append({'instance_id':identifier,'data_row_bytes_equal':True,'data_row_sha256':hashlib.sha256(aa).hexdigest(),'harness_input_and_parameters_bytes_equal':True,'captured_input_sha256':hashlib.sha256(captures[0]).hexdigest()})
 h=Dataset('holdout50');assert sha(P/'data/ids.txt')==IDS and len(h.ids)==50
 for identifier in h.ids:
  try:new.DATA.allow(identifier)
  except PermissionError:pass
  else:raise AssertionError('dev24_scope_accepted_holdout')
 for d in (h,new.DATA):
  try:d.allow('not-authorized-instance')
  except PermissionError:pass
  else:raise AssertionError('scope_guard_failed')
 result={'status':'passed','dev24_cases':cases,'dev24_instance_collection_equal':True,'dev24_selection_order_equal':manifest['selection_order']==load(F/'baseline/data/dev24/manifest.json')['selection_order'],'evaluation_function_tail_byte_identical':True,'evaluation_function_tail_sha256':hashlib.sha256(source[source.index('def spec_for('):].encode()).hexdigest(),'holdout_count':len(h.ids),'holdout_ids_sha256':sha(P/'data/ids.txt'),'holdout_scoring_content_loaded':False,'real_harness_executions':0,'Docker_daemon_calls':0,'model_API_calls':0,'method':'Actual old/new dev24 dataset loaders; default JSON bytes including key order; identical spec_for/evaluate/main source; instrumented stub harness captures make_test_spec arguments, prediction, run_instance flags/timeout and original resource wrapper kwargs. No synthetic result is an experimental result.'}
 durable(P/'delivery/adapter-equivalence.json',result)
 print(json.dumps({k:v for k,v in result.items() if k!='dev24_cases'},ensure_ascii=False))
if __name__=='__main__':main()
