"""Manifest-bound SDK integration for offline verification only; no live transport."""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from experiments.cohort_preflight.entry import ROOT,read,sha


class OfflineProcessRetriever:
    def __init__(self, spec_path, spec_hash):
        self.spec_path=Path(spec_path).resolve();self.spec_hash=spec_hash
        if sha(self.spec_path)!=spec_hash:raise ValueError('offline_spec_changed')
        spec=read(self.spec_path);self.snapshot_id=spec['snapshot']
        self.queries={q['query'] for q in spec['queries']}

    def retrieve(self,query):
        if sha(self.spec_path)!=self.spec_hash:raise ValueError('offline_spec_changed')
        if query not in self.queries:raise ValueError('query_outside_offline_manifest')
        with tempfile.TemporaryDirectory() as td:
            env={'PATH':os.defpath,'LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1',
                 'MPLCONFIGDIR':td,'XDG_CACHE_HOME':td,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
            p=subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python','-I','-B',
                              str(ROOT/'experiments/retrieval_evidence_v6/worker.py'),'--query',str(self.spec_path),query],
                             cwd=td,env=env,capture_output=True,timeout=300)
            if p.returncode:raise RuntimeError('isolated_offline_retrieval_failed')
            data=json.loads(p.stdout)
        if data['snapshot']!=self.snapshot_id:raise ValueError('retrieval_snapshot_changed')
        return data['text']
