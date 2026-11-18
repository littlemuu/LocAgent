"""No model calls. Check frozen selection, public/evaluator separation and local runtime."""
import argparse,hashlib,json,os,platform,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from locagent_e2e.common import ROOT,manifest,CONFIG,write_json
from locagent_e2e.driver import inspect_image,image_name
p=argparse.ArgumentParser();p.add_argument('--docker',default='docker');p.add_argument('--output',type=Path,required=True);p.add_argument('--cloud',action='store_true');a=p.parse_args()
m=manifest();public=json.loads((ROOT/'data/dev24/content/public.json').read_text());receipt=json.loads((ROOT/'data/dev24/content/receipt.json').read_text())
for name,h in receipt['files'].items():assert hashlib.sha256((ROOT/'data/dev24/content'/name).read_bytes()).hexdigest()==h
assert {r['instance_id'] for r in public}=={r['instance_id'] for r in m['instances']}
assert all(set(r)=={'instance_id','repo','base_commit','problem_statement'} for r in public)
assert len(m['instances'])==24 and m['holdout_overlap_count']==0
assert hashlib.sha256((ROOT/'data/dev24/ids.txt').read_bytes()).hexdigest()==m['ids_sha256']
if a.cloud:assert platform.system()=='Linux' and platform.machine()=='x86_64'
import importlib.metadata as md
versions={p:md.version(p) for p in ('openhands-sdk','swebench','bm25s','PyStemmer','numpy','scipy','datasets','pyarrow')}
assert versions['openhands-sdk']=='1.62.0' and versions['swebench']=='3.0.0'
subprocess.run([sys.executable,'-m','pip','check'],check=True)
from locagent_e2e.evaluation import spec_for
for i in m['smoke_ids']:assert spec_for(i).instance_image_key==image_name(i)
images=[inspect_image(a.docker,image_name(i)) for i in m['smoke_ids']]
result={'status':'passed','host_architecture':platform.machine(),'cloud_x86_verified':platform.system()=='Linux' and platform.machine()=='x86_64','versions':versions,'public_rows':24,'holdout_overlap':0,'holdout_content_accessed':False,'smoke_images':images,'model_requests':0}
write_json(a.output,result);print(json.dumps(result))
