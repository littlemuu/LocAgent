"""Read-only production manifest-gate check in scrubbed offline subprocesses."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'verification/engine-compatibility-v1'


def main():
    pre = json.loads((OUT / 'preflight.json').read_text())
    worker = '''import json,sys,os
from pathlib import Path
r=json.load(sys.stdin)
sys.path.insert(0,r['engine_root'])
os.environ['LOCAGENT_SOURCE_ROOT']=r['registry']
from locagent_service.offline import offline_engine
with offline_engine():
 from locagent_service.sources import load_manifest
 try:
  m,b=load_manifest(r['source_id'])
  result={'accepted':True,'bundle':str(b)}
 except Exception as e:
  result={'accepted':False,'error_type':type(e).__name__,'reason':str(e)}
print(json.dumps(result))
'''
    rows = []
    for c in pre['cases']:
        for name, engine in pre['engines'].items():
            with tempfile.TemporaryDirectory(prefix='manifest-gate-probe-') as tmp:
                script = Path(tmp) / 'probe.py'
                script.write_text(worker)
                req = {'engine_root': engine['root'], 'registry': str(Path(c['manifest']).parent),
                       'source_id': Path(c['manifest']).stem}
                run = subprocess.run([str(Path(pre['engines']['current']['root']) / '.venv/bin/python'),
                    '-I', '-B', str(script)], input=json.dumps(req).encode(), cwd=tmp,
                    env={'PATH': os.defpath, 'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
                         'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'MPLCONFIGDIR': tmp, 'XDG_CACHE_HOME': tmp},
                    capture_output=True, timeout=45, check=True)
                rows.append({'case': c['case'], 'engine': name, 'result': json.loads(run.stdout)})
    frozen = json.loads((ROOT / 'locbench_openhands/v5/manifest.json').read_text())
    same = []
    for c in pre['cases']:
        item = next(x for x in frozen['cases'] if x['id'] == c['case'])
        same.append({'case': c['case'], 'python_hashes_equal_frozen_openhands':
                     item['plan']['source_hashes'] == c['source_hashes']})
    value = {'rows': rows, 'frozen_projection_check': same, 'model_requests': 0,
             'scope': 'Unmodified load_manifest; no weakening or production configuration changes.'}
    with (OUT / 'manifest-gate-probe.json').open('x') as f:
        json.dump(value, f, indent=2)
    print(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()
