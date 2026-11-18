"""Isolated evaluator entry: only this module reads selected dev test patches/labels."""
import json,os,time,subprocess,hashlib
from unittest.mock import patch
from pathlib import Path
from .common import ROOT,CONFIG,allow,write_json

def dataset_row(identifier):
 allow(identifier)
 source=ROOT/'data/dev24/content/evaluator.json'
 receipt=json.loads((ROOT/'data/dev24/content/receipt.json').read_text())
 if hashlib.sha256(source.read_bytes()).hexdigest()!=receipt['files']['evaluator.json']:raise PermissionError('evaluator_content_changed')
 rows=json.loads(source.read_text())
 # This file is independently checked to contain only the 24 exposed IDs.
 allowed={x['instance_id'] for x in json.loads((ROOT/'data/dev24/manifest.json').read_text())['instances']}
 if len(rows)!=24 or {r['instance_id'] for r in rows}!=allowed:raise PermissionError('evaluator_dataset_membership_changed')
 return next(r for r in rows if r['instance_id']==identifier)
def spec_for(identifier):
 from swebench.harness.test_spec.test_spec import make_test_spec
 spec=make_test_spec(dataset_row(identifier),namespace='swebench');spec.arch='x86_64';return spec

def evaluate(identifier,prediction,output,docker_host=None,formal=False):
 import docker
 from swebench.harness.run_evaluation import run_instance
 allow(identifier,smoke=not formal)
 output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True);spec=spec_for(identifier)
 pred=json.loads(Path(prediction).read_text());assert pred['instance_id']==identifier
 client=docker.DockerClient(base_url=docker_host) if docker_host else docker.from_env(timeout=1800)
 previous=Path.cwd();start=time.monotonic()
 try:
  os.chdir(output)
  # Each episode has its own output directory and run id; no shared evaluator cache.
  original_create=client.containers.create
  def isolated_create(*args,**kwargs):
   kwargs.update(network_disabled=True,mem_limit='6g',nano_cpus=6000000000,pids_limit=512,cap_drop=['ALL'],security_opt=['no-new-privileges'])
   return original_create(*args,**kwargs)
  import swebench.harness.run_evaluation as evaluation_module
  original_build=evaluation_module.build_container
  def base_checked_build(*args,**kwargs):
   container=original_build(*args,**kwargs);original_start=container.start
   def base_checked_start(*a,**k):
    original_start(*a,**k)
    base=dataset_row(identifier)['base_commit']
    for command in (['git','reset','--hard',base],['git','clean','-fd']):
     val=container.exec_run(command,workdir='/testbed',user='root')
     if val.exit_code:raise RuntimeError('evaluator_base_reset_failed')
    value=container.exec_run(['git','rev-parse','HEAD'],workdir='/testbed',user='root')
    if value.exit_code or value.output.decode().strip()!=base:raise RuntimeError('evaluator_base_mismatch')
   container.start=base_checked_start;return container
  with patch.object(client.containers,'create',isolated_create),patch.object(evaluation_module,'build_container',base_checked_build):
   result=run_instance(spec,pred,False,False,client,'smoke',timeout=1800)
  report=output/'logs/run_evaluation/smoke'/pred['model_name_or_path'].replace('/','__')/identifier/'report.json'
  if not report.is_file():raise RuntimeError('harness_no_report')
  value=json.loads(report.read_text());row=value[identifier]
  record={'status':'completed','resolved':row.get('resolved'),'elapsed_seconds':time.monotonic()-start,'report_path':str(report.relative_to(output)),'harness_commit':CONFIG['harness_commit'],'technical_failure':None}
 except Exception as e:
  record={'status':'failed','resolved':None,'elapsed_seconds':time.monotonic()-start,'technical_failure':type(e).__name__+': '+str(e)[:300]}
 finally:os.chdir(previous);client.close()
 write_json(output/'evaluation.json',record);return record

def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--id',required=True);p.add_argument('--prediction',required=True);p.add_argument('--output',required=True);p.add_argument('--docker-host');p.add_argument('--formal-development-scope',action='store_true');a=p.parse_args()
 result=evaluate(a.id,a.prediction,a.output,a.docker_host,a.formal_development_scope);print(json.dumps(result));raise SystemExit(0 if result['status']=='completed' else 1)
if __name__=='__main__':main()
