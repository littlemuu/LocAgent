"""Strict source-only entry boundary. No scoring files are read by this module."""
import hashlib,json
from pathlib import Path
from readonly_agent.core import Snapshot,digest,encoded,safe_name
ROOT=Path(__file__).resolve().parents[2]
FIELDS={'version','case_id','repo','base_commit','issue','issue_hash','source_plan','source_plan_sha256',
        'source_snapshot','parent_manifest_sha256','entity_index','entity_attestation','entity_attestation_sha256',
        'validation_attestation','validation_attestation_sha256','v4_manifest_sha256'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def checked_file(path,expected):
    p=Path(path)
    if p!=p.resolve() or not p.is_file() or sha(p)!=expected:
        raise ValueError('file_binding_changed')
    return p
def save(path,value):
    with Path(path).open('xb') as f:f.write(encoded(value))
def validate_entry(value):
    if not isinstance(value,dict) or set(value)!=FIELDS or value['version']!=1:
        raise ValueError('unexpected_runtime_entry_fields')
    safe_name(value['case_id'])
    if '/' in value['case_id'] or not isinstance(value['issue'],str) or digest(value['issue'])!=value['issue_hash']:
        raise ValueError('invalid_case_or_issue')
    if not isinstance(value['repo'],str) or len(value['base_commit'])!=40:
        raise ValueError('invalid_repository_binding')
    return value
def load_entry(path,expected_hash,*,check_engine=True):
    value=validate_entry(read(checked_file(path,expected_hash)))
    mp=ROOT/'engine_adaptation/v4/adapted-manifest.json'
    manifest=read(checked_file(mp,value['v4_manifest_sha256']))
    item=next((r for r in manifest['cases'] if r['id']==value['case_id']),None)
    if item is None:raise ValueError('unknown_case')
    if check_engine:
        for n,h in manifest['engine']['files'].items():checked_file(ROOT/'engine_adaptation/v4/engine'/n,h)
        for n,h in manifest['harness_files'].items():checked_file(ROOT/n,h)
    plan=read(checked_file(value['source_plan'],value['source_plan_sha256']))
    if (plan['id']!=value['case_id'] or plan['commit']!=value['base_commit']
            or plan['plan_hash']!=item['plan_hash']
            or digest({k:v for k,v in plan.items() if k!='plan_hash'})!=plan['plan_hash']):
        raise ValueError('source_plan_mismatch')
    snapshot=Snapshot(plan['source_root'],list(plan['sources']),hidden_python_paths=plan['hidden_python_paths'])
    if dict(snapshot.hashes)!=plan['sources'] or snapshot.identity!=value['source_snapshot'] or snapshot.identity!=item['source_snapshot']:
        raise ValueError('source_changed')
    if value['entity_index']!=item['index_directory'] or value['entity_attestation']!=item['index_attestation']:
        raise ValueError('cross_case_index')
    att=read(checked_file(value['entity_attestation'],value['entity_attestation_sha256']))
    base=Path(value['entity_index']).parent
    for n,h in att['artifacts'].items():
        safe_name(n);checked_file(base/n,h)
    val=read(checked_file(value['validation_attestation'],value['validation_attestation_sha256']))
    if val['id']!=value['case_id'] or val['plan_hash']!=plan['plan_hash'] or val['result']['snapshot']!=snapshot.identity:
        raise ValueError('validation_attestation_mismatch')
    return value,snapshot

def load_graph(value,snapshot):
    import networkx as nx
    from readonly_agent.locagent import LocAgentRetriever
    from plugins.location_tools.retriever.bm25_retriever import build_retriever_from_persist_dir
    raw=read(Path(value['entity_index']).parent/'graph.json')
    if raw['schema']!='locagent-source-graph-v1':raise ValueError('invalid_graph_schema')
    graph=nx.MultiDiGraph()
    for n,d in raw['nodes']:graph.add_node(n,**d)
    for a,b,k,d in raw['edges']:graph.add_edge(a,b,key=k,**d)
    retriever=LocAgentRetriever(snapshot,graph)
    persisted=build_retriever_from_persist_dir(value['entity_index'])
    corpus=lambda r:[json.loads(x['_node_content'])['text'] for x in r.corpus]
    if corpus(persisted)!=corpus(retriever._lexical):raise ValueError('entity_corpus_mismatch')
    retriever._lexical=persisted
    return graph,retriever,persisted
