"""Only task-owned Docker containers execute agent commands; no host shell tools."""
import json,subprocess,time,uuid,os
from pathlib import Path
from .common import CONFIG,write_json
class DockerSandbox:
 def __init__(self,image,base_commit,docker='docker',record=None):
  self.docker=docker;self.image=image;self.base=base_commit;self.name='locagent-e2e-'+uuid.uuid4().hex[:14];self.record=record;self.started=False
 def cli(self,args,*,input=None,timeout=120):
  return subprocess.run([self.docker,*args],input=input,capture_output=True,timeout=timeout,check=False)
 def start(self):
  p=self.cli(['run','-d','--name',self.name,'--label','locagent.e2e=dev24','--platform','linux/amd64','--network','none','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','512','--memory','6g','--cpus','6','--entrypoint','/bin/bash',self.image,'-c','sleep infinity'])
  if p.returncode:raise RuntimeError('container_start_failed: '+p.stderr.decode(errors='replace')[:600])
  self.started=True
  reset=self.exec_raw(['git','reset','--hard',self.base])
  if reset.returncode:self.close();raise RuntimeError('base_commit_unavailable_in_image')
  clean=self.exec_raw(['git','clean','-fd'])
  if clean.returncode:self.close();raise RuntimeError('base_cleanup_failed')
  p=self.exec_raw(['git','rev-parse','HEAD']);actual=p.stdout.decode().strip()
  if p.returncode or actual!=self.base:self.close();raise RuntimeError('image_base_commit_mismatch')
  # Keep only base source; remove all repository history/remotes before agent access.
  original=self.exec_raw(['git','archive',self.base]);tracked=self.exec_raw(['git','ls-files','-z'])
  if original.returncode or tracked.returncode:raise RuntimeError('base_export_failed')
  self.clean_archive=original.stdout
  for args in [['rm','-rf','--','/testbed/.git'],['git','init'],['git','config','user.name','LocAgent smoke'],['git','config','user.email','offline@example.invalid']]:
   if self.exec_raw(args).returncode:raise RuntimeError('history_sanitization_failed')
  if self.exec_raw(['git','add','-f','--pathspec-from-file=-','--pathspec-file-nul'],input=tracked.stdout).returncode:raise RuntimeError('baseline_index_failed')
  if self.exec_raw(['git','-c','core.hooksPath=/dev/null','commit','-m','Isolated base source']).returncode:raise RuntimeError('baseline_commit_failed')
  self.base=self.exec_raw(['git','rev-parse','HEAD']).stdout.decode().strip()
  return self
 def exec_raw(self,args,*,input=None,timeout=120):
  return self.cli(['exec','-i','-w','/testbed',self.name,*args],input=input,timeout=timeout)
 def execute(self,command,timeout_seconds=120):
  start=time.monotonic()
  p=self.exec_raw(['/usr/bin/timeout','--signal=KILL',str(min(timeout_seconds,120)),'/bin/bash','-lc','source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && '+command],timeout=min(timeout_seconds,120)+10)
  return {'exit_code':p.returncode,'stdout':p.stdout.decode(errors='replace'),'stderr':p.stderr.decode(errors='replace'),'elapsed_seconds':time.monotonic()-start}
 def file(self,operation,path,content=None,old=None,new=None):
  # Interpreter runs only fixed editor code; values arrive as JSON stdin, not shell interpolation.
  script='''import json,pathlib,sys
v=json.load(sys.stdin);root=pathlib.Path('/testbed');p=(root/v['path']).resolve()
if not p.is_relative_to(root) or '.git' in p.relative_to(root).parts:raise ValueError('path_outside_repository')
if v['operation']=='view':
 data=p.read_text();print(''.join(str(i)+': '+line for i,line in enumerate(data.splitlines(keepends=True),1)))
elif v['operation']=='create':
 if p.exists():raise ValueError('file_exists')
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(v['content']);print('created')
elif v['operation']=='replace':
 data=p.read_text();old=v['old']
 if not old or data.count(old)!=1:raise ValueError('replacement_must_match_exactly_once')
 p.write_text(data.replace(old,v['new'],1));print('replaced')
else:raise ValueError('invalid_operation')
'''.replace("p.is_relative_to(root)","(p==root or root in p.parents)")
  payload=json.dumps({'operation':operation,'path':path,'content':content,'old':old,'new':new}).encode()
  p=self.exec_raw(['/opt/miniconda3/bin/python','-c',script],input=payload)
  return {'exit_code':p.returncode,'stdout':p.stdout.decode(errors='replace'),'stderr':p.stderr.decode(errors='replace')}
 def patch(self):
  p=self.exec_raw(['git','-c','core.hooksPath=/dev/null','add','-N','.'])
  if p.returncode:raise RuntimeError('git_intent_to_add_failed')
  p=self.exec_raw(['git','-c','core.hooksPath=/dev/null','diff','--binary','--no-ext-diff',self.base,'--','.'])
  if p.returncode or len(p.stdout)>4*1024*1024:raise RuntimeError('patch_export_failed')
  return p.stdout.decode('utf-8')
 def source_archive(self):
  # Exact git-tracked base source, not evaluator labels or another trial's edits.
  return self.clean_archive
 def close(self):
  if self.started:self.cli(['rm','-f',self.name],timeout=30);self.started=False
