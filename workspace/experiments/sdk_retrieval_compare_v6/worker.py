"""Source-only retrieval subprocess; no provider/credential or native agent route."""
import contextlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'engine_adaptation/v4/engine')]
from experiments.sdk_retrieval_compare_v6.guard import verify
from experiments.cohort_preflight.entry import read,load_graph
from readonly_agent.core import encoded
from locagent_service.offline import offline_engine

def main():
    m=json.load(sys.stdin)
    if set(m)!={'plan','query','arm','parent_pid','batch_parent_pid'}:raise PermissionError('retrieval_only_worker')
    os.kill(m['batch_parent_pid'],0)
    if os.getppid()!=m['parent_pid']:raise RuntimeError('parent_lost')
    with contextlib.redirect_stdout(sys.stderr),offline_engine():
        p=read(m['plan']);v,s,_=verify(p,p['cohort_execution']);_,base,_=load_graph(v,s)
        from experiments.sdk_retrieval_compare_v6.backends import select_retriever
        result={'text':select_retriever(base,s,m['arm']).retrieve(m['query']),'snapshot':s.identity}
    sys.stdout.buffer.write(encoded(result))
if __name__=='__main__':main()
