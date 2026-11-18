"""Build source-only, offline adaptation indexes in a new destination."""
import contextlib, hashlib, json, resource, sys, ast
from pathlib import Path
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'engine_adaptation/v1/engine')]
from readonly_agent.core import Snapshot, encoded
from readonly_agent.locagent import LocAgentRetriever
from locagent_service.offline import offline_engine

def main():
    req=json.load(sys.stdin); out=Path(req['output']);out.mkdir(exist_ok=False)
    resource.setrlimit(resource.RLIMIT_CPU,(90,90))
    resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,256*1024**2))
    with contextlib.redirect_stdout(sys.stderr),offline_engine(),tempfile.TemporaryDirectory() as tmp:
        from dependency_graph.build_graph import build_graph
        root=Path(tmp)
        for name,h in req['sources'].items():
            data=(Path(req['source_root'])/name).read_bytes()
            assert hashlib.sha256(data).hexdigest()==h
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        snapshot=Snapshot(root,list(req['sources']),hidden_python_paths=req['hidden_python_paths'])
        graph=build_graph(str(root),global_import=True)
        retriever=LocAgentRetriever(snapshot,graph)
        expected=set();syntax=[]
        from readonly_agent.locagent import source_entity_segments
        for name,text in snapshot.files.items():
            try:
                for kind,qualified,start,end in source_entity_segments(text):expected.add(name+':'+qualified)
            except SyntaxError:syntax.append(name)
        missing=sorted(expected-set(graph))
        graph_files={n for n,d in graph.nodes(data=True) if d.get('type')=='file'}
        absent=sorted(set(snapshot.files)-graph_files)
        assert not missing and not absent, (missing[:5],absent[:5])
        # JSON and numeric BM25 files, never pickle; source integrity is separately bound.
        (out/'graph.json').write_bytes(encoded({'schema':'locagent-source-graph-v1',
            'nodes':[[n,d] for n,d in graph.nodes(data=True)],
            'edges':[[a,b,k,d] for a,b,k,d in graph.edges(keys=True,data=True)]}))
        retriever._lexical.persist(str(out/'entity-bm25'))
        query=req.get('query')
        response=retriever.retrieve(query) if query else None
        result={'status':'ready' if not syntax else 'syntax_review_required','files':len(snapshot.files),
            'nodes':len(graph),'edges':graph.number_of_edges(),'snapshot':snapshot.identity,
            'missing_entities':missing,'missing_files':absent,'syntax_errors':syntax,
            'query':query,'response':response,'model_calls':0}
        (out/'result.json').write_bytes(encoded(result))
    print(json.dumps({k:v for k,v in result.items() if k!='response'}))

if __name__=='__main__':main()
