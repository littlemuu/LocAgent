"""Bounded local IPC to the reviewed LocAgent environment; no shell invocation."""
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from .core import encoded


class LocAgentProcessRetriever:
    def __init__(self, snapshot, *, python, engine_root):
        self.snapshot_id = snapshot.identity
        self._sources = dict(snapshot.files)
        self._hidden_python_paths = list(snapshot.hidden_python_paths)
        self.python = str(Path(python).absolute())
        self.engine_root = str(Path(engine_root).resolve(strict=True))
        if not (Path(self.engine_root) / 'util/localizer.py').is_file():
            raise ValueError('reviewed_locagent_installation_required')

    def retrieve(self, query):
        if not isinstance(query, str) or not 1 <= len(query) <= 256:
            raise ValueError('invalid_query')
        request = encoded({'snapshot': self.snapshot_id, 'sources': self._sources, 'query': query,
                           'hidden_python_paths': self._hidden_python_paths})
        worker = Path(__file__).with_name('locagent_worker.py')
        with TemporaryDirectory(prefix='locagent-ipc-') as temporary:
            environment = {'PATH': os.defpath, 'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
                           'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
                           'MPLCONFIGDIR': temporary, 'XDG_CACHE_HOME': temporary,
                           'TOKENIZERS_PARALLELISM': 'false'}
            completed = subprocess.run([self.python, '-I', '-B', str(worker), self.engine_root],
                input=request, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=temporary, env=environment, timeout=45, check=False)
        if completed.returncode != 0 or len(completed.stdout) > 4 * 1024 * 1024:
            raise RuntimeError('locagent_worker_failed')
        result = json.loads(completed.stdout)
        if (set(result) != {'snapshot', 'text'} or result['snapshot'] != self.snapshot_id
                or not isinstance(result['text'], str)):
            raise ValueError('invalid_worker_response')
        return result['text']
