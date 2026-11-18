"""Compare old/new retrieval in an isolated static-source process; no target execution."""
import contextlib
import json
import re
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'engine_adaptation/v4/engine')]
from experiments.cohort_preflight.entry import read,save,sha,load_entry,load_graph
from readonly_agent.core import FileTools,encoded,page,runtime_identity
from experiments.path_retrieval_v4.retriever import PathAwareRetriever
from experiments.retrieval_evidence_v6.retriever import EvidenceRetriever
from locagent_service.offline import offline_engine


def load(spec_path):
    spec=read(spec_path)
    assert runtime_identity()==spec['runtime_hash']
    for field in ('ledger','additional_ledger','static_regression'):
        if field in spec:assert sha(spec[field])==spec[field+'_sha256']
    assert sha(ROOT/'experiments/path_retrieval_v4/retriever.py')==spec['retriever_sha256']
    assert sha(ROOT/'experiments/retrieval_evidence_v6/retriever.py')==spec['new_retriever_sha256']
    for f,h in spec['engine']['files'].items():assert sha(Path(spec['engine']['root'])/f)==h
    b=spec['binding'];value,snapshot=load_entry(b['entry'],b['entry_sha256'])
    assert snapshot.identity==spec['snapshot']
    graph,base,_=load_graph(value,snapshot)
    return spec,snapshot,base


def main():
    if sys.argv[1]=='--query':
        spec_path,query=sys.argv[2:]
        with contextlib.redirect_stdout(sys.stderr),offline_engine():
            spec,snapshot,base=load(spec_path)
            if query not in [q['query'] for q in spec['queries']]:raise ValueError('query_outside_offline_manifest')
            r=EvidenceRetriever(base,snapshot);text=r.retrieve(query)
        print(json.dumps({'snapshot':snapshot.identity,'text':text,'audit':r.last_audit},ensure_ascii=False))
        return
    spec_path,out_path=sys.argv[1:];out=Path(out_path);out.mkdir(exist_ok=False)
    rows=[]
    with contextlib.redirect_stdout(sys.stderr),offline_engine():
        spec,snapshot,base=load(spec_path);old=PathAwareRetriever(base);new=EvidenceRetriever(base,snapshot)
        for i,q in enumerate(spec['queries']):
            oldtext=old.retrieve(q['query']);oldpage=page(oldtext,0,4096)
            assert oldpage==q['original_page'],'historical_page_changed'
            tools=FileTools(snapshot,new);started=time.monotonic()
            text,_=tools.render('locagent_retrieve',{'query':q['query'],'offset':0})
            elapsed=time.monotonic()-started;first=tools.respond('locagent_retrieve',{'query':q['query'],'offset':0},4096)
            assert first==tools.respond('locagent_retrieve',{'query':q['query'],'offset':0},4096)
            pages=[];parts=[];offset=0
            while True:
                part=tools.respond('locagent_retrieve',{'query':q['query'],'offset':offset},4096)
                assert part is not None and len(encoded(part))<=4096
                parts.append(part['text']);pages.append({'offset':offset,'next_offset':part['next_offset'],'bytes':len(encoded(part))})
                if part['next_offset'] is None:break
                assert part['next_offset']>offset;offset=part['next_offset']
            assert ''.join(parts)==text
            audit=new.last_audit;seen=[]
            for c in audit['candidates']:
                seen.extend((c['path'],n) for n in c['shown_lines'])
            assert len(seen)==len(set(seen)),'duplicate_source_lines'
            primary=audit['candidates'][0] if audit['candidates'] else None
            visible=re.findall(r'^(\d+): ',first['text'],re.M)
            if primary and primary['implementation_start'] is not None:
                assert str(primary['implementation_start']) in visible,'primary_implementation_missing_first_page'
            (out/f'query-{i}-old.txt').write_text(oldtext)
            (out/f'query-{i}-new.txt').write_text(text)
            rows.append({'query':q['query'],'batch':q['batch'],'origin':q['query_source'],
                         'old_page_exact':True,'old_bytes':len(oldtext.encode()),'new_bytes':len(text.encode()),
                         'old_first_page':oldpage,'new_first_page':first,'old_candidates':re.findall(r'##Searching for entity `([^`]+)`',oldtext),
                         'new_audit':audit,'new_pages':pages,'seconds':elapsed,'no_duplicate_source_lines':True,
                         'primary_implementation_in_first_page':None if not primary or primary['implementation_start'] is None else True})
    save(out/'result.json',{'id':spec['id'],'snapshot':snapshot.identity,'rows':rows,'gold_read':False,'real_requests':0,'network_guard_completed':True})
    print(spec['id'],'offline old/new checks passed',flush=True)

if __name__=='__main__':main()
