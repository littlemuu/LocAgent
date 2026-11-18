"""Offline subprocess adapter for the existing OpenHands readonly tool interface."""
import json,os,subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from readonly_agent.core import encoded,digest
from .corpus import Corpus
from .vectors import CachedDense

class RetrievalFailed(RuntimeError):pass

class ProcessRetriever:
    def __init__(self,snapshot,config,*,python,cache=None,timeout=45):
        if type(timeout) not in (int,float) or not 0<timeout<=300:raise ValueError('invalid_worker_timeout')
        self.snapshot_id=snapshot.identity;self.config=config;self.python=str(Path(python).absolute());self.timeout=timeout
        self.sources=dict(snapshot.files);self.hidden=list(snapshot.hidden_python_paths)
        self.cache=json.loads(encoded(cache)) if cache is not None else None
        self.cache_hash=digest(self.cache) if self.cache is not None else None
        corpus=Corpus(snapshot,config.max_chars);self.corpus_id=corpus.identity
        if cache is not None:CachedDense(self.cache,corpus,config,self.cache_hash)
        if config.mode!='body_bm25' and cache is None:raise ValueError('dense_cache_required')
        self.audits=[];self.failure=None;self.worker_calls=0
    def retrieve(self,query):
        if self.failure:raise RetrievalFailed('retriever_already_failed')
        if not isinstance(query,str) or not 1<=len(query)<=256 or not query.strip():raise ValueError('invalid_query')
        q={'snapshot':self.snapshot_id,'sources':self.sources,'hidden_python_paths':self.hidden,'config':self.config.to_dict(),'cache':self.cache,'cache_hash':self.cache_hash,'query':query}
        body=encoded(q)
        if len(body)>128*1024*1024:raise ValueError('oversized_worker_input')
        try:
            with TemporaryDirectory(prefix='hybrid-v8-ipc-') as td:
                env={'PATH':os.defpath,'DO_NOT_TRACK':'1','LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1','MPLCONFIGDIR':td,'XDG_CACHE_HOME':td,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
                self.worker_calls+=1
                run=subprocess.run([self.python,'-I','-B',str(Path(__file__).with_name('worker.py'))],input=body,capture_output=True,cwd=td,env=env,timeout=self.timeout)
            if len(run.stdout)>4*1024*1024:raise ValueError('oversized_worker_result')
            data=json.loads(run.stdout)
            if run.returncode:
                self.failure={'type':data.get('error_type','WorkerError'),'reason':data.get('error','worker_failed')}
                raise RetrievalFailed(self.failure['reason'])
            if set(data)!={'snapshot','text','audit','network_attempts'} or data['snapshot']!=self.snapshot_id or not isinstance(data['text'],str) or data['network_attempts']!=0:raise ValueError('invalid_worker_response')
            audit=data['audit']
            if audit['snapshot']!=self.snapshot_id or audit['corpus']!=self.corpus_id or audit['config_hash']!=self.config.identity or audit['index_hash']!=self.cache_hash:raise ValueError('worker_binding_changed')
            self.audits.append(audit);return data['text']
        except Exception as exc:
            if self.failure is None:self.failure={'type':type(exc).__name__,'reason':'offline_retrieval_failed'}
            raise RetrievalFailed(self.failure['reason']) from None
