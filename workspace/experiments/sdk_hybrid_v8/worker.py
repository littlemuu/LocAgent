"""One offline retrieval per process; stdin JSON only, no credentials or provider."""
import contextlib,json,sys
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from readonly_agent.core import Snapshot,encoded,safe_name
from readonly_agent.offline import no_network

def main():
    raw=sys.stdin.buffer.read(128*1024*1024+1)
    if len(raw)>128*1024*1024:raise ValueError('oversized_worker_input')
    q=json.loads(raw)
    if set(q)!={'sources','hidden_python_paths','snapshot','config','cache','cache_hash','query'}:raise ValueError('invalid_worker_fields')
    with TemporaryDirectory(prefix='hybrid-v8-source-') as td:
        root=Path(td);source=root/'source';source.mkdir()
        for name,text in q['sources'].items():
            safe_name(name)
            if not isinstance(text,str):raise ValueError('invalid_source')
            p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.encode())
        snapshot=Snapshot(source,list(q['sources']),hidden_python_paths=q['hidden_python_paths'])
        if snapshot.identity!=q['snapshot']:raise ValueError('worker_snapshot_mismatch')
        with contextlib.redirect_stdout(sys.stderr),no_network(root/'profiles') as attempts:
            from experiments.sdk_hybrid_v8.config import RetrievalConfig
            from experiments.sdk_hybrid_v8.retriever import HybridRetriever
            r=HybridRetriever(snapshot,RetrievalConfig(**q['config']),cache=q['cache'],cache_hash=q['cache_hash'])
            text=r.retrieve(q['query'])
        result={'snapshot':snapshot.identity,'text':text,'audit':r.last_audit,'network_attempts':len(attempts)}
    output=encoded(result)
    if len(output)>4*1024*1024:raise ValueError('oversized_worker_result')
    sys.stdout.buffer.write(output)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        sys.stdout.buffer.write(encoded({'error_type':type(exc).__name__,'error':str(exc) if isinstance(exc,ValueError) else 'retrieval_worker_failed'}))
        raise SystemExit(1)
