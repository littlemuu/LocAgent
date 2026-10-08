"""Build immutable graph/BM25 artifacts from a local exact Git commit, offline."""
import argparse
from copy import deepcopy
import io
import json
from pathlib import Path
import pickle
import subprocess
import tarfile
from uuid import uuid4

from locagent_service.sources import registry,canonical,digest,file_hashes,load_manifest
from locagent_service.budget import LIVE_CONFIG
from locagent_service.offline import offline_engine
from util.localization_contract import LocalizationRequest


def prepare(repo, sample):
    raw=json.loads(Path(sample).read_text())
    task=LocalizationRequest(**{key:raw[key] for key in (
        'instance_id','repo','base_commit','problem_statement')}).as_task()
    commit=subprocess.check_output(['git','-C',str(repo),'rev-parse',task['base_commit']+'^{commit}'],
                                   text=True).strip()
    if commit!=task['base_commit']:
        raise ValueError('Exact commit required')
    bundle=registry()/('bundle-'+uuid4().hex)
    snapshot=bundle/'repo'
    snapshot.mkdir(parents=True)
    archive=subprocess.check_output(['git','-C',str(repo),'archive','--format=tar',commit])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if not (member.isfile() or member.isdir()):
                raise ValueError('Only ordinary repository files/directories are supported')
        tar.extractall(snapshot,filter='data')
    config={**LIVE_CONFIG, 'top_k':5,'global_import':True,'fuzzy_search':True,
            'chunk_size':500,'min_chunk_size':100,'max_chunk_size':2000,
            'hard_token_limit':2000,'max_chunks':200}
    with offline_engine():
        import networkx as nx
        from dependency_graph.build_graph import build_graph
        from plugins.location_tools.retriever.bm25_retriever import build_code_retriever_from_repo
        graph=build_graph(str(snapshot),global_import=True,fuzzy_search=True)
        if '/' in graph:
            graph=nx.relabel_nodes(graph,{'/':'.'})
        (bundle/'graph.pkl').write_bytes(pickle.dumps(graph))
        build_code_retriever_from_repo(str(snapshot),
            persist_path=str(bundle/'bm25'/task['instance_id']),similarity_top_k=5)
    base=Path(__file__).resolve().parents[1]
    names=['util/localizer.py','util/localization_engine.py','util/return_trace.py',
           'dependency_graph/build_graph.py','plugins/location_tools/repo_ops/repo_ops.py',
           'util/prompts/pipelines/auto_search_prompt.py']
    (bundle/'environment.txt').write_bytes(subprocess.check_output(
        [str(base/'.venv/bin/python'),'-m','pip','freeze']))
    manifest={'version':2,'bundle':bundle.name,'task':task,'config':config,
              'dataset':{k:raw.get(k) for k in ('dataset','dataset_revision','split','local_role')},
              'artifacts':file_hashes(bundle),
              'engine':{n:digest((base/n).read_bytes()) for n in names}}
    data=canonical(manifest)
    source_id='prepared-'+digest(data)
    target=registry()/(source_id+'.json')
    with target.open('xb') as stream:stream.write(data)
    print(json.dumps({'source_id':source_id,'manifest':str(target),
                      'commit':commit,'nodes':len(graph),'edges':graph.number_of_edges()}))
    return source_id


def derive_source(source_id):
    """Reuse verified immutable artifacts; preserve the legacy manifest byte for byte."""
    manifest, _ = load_manifest(source_id)
    manifest = deepcopy(manifest)
    manifest.update(version=2, parent_source_id=source_id)
    manifest['config'].pop('max_input_tokens', None)
    manifest['config'].update(LIVE_CONFIG)
    data = canonical(manifest)
    derived = 'prepared-' + digest(data)
    target = registry() / (derived + '.json')
    with target.open('xb') as stream:
        stream.write(data)
    print(json.dumps({'source_id': derived, 'manifest': str(target),
                      'parent_source_id': source_id}))
    return derived


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--repo')
    group.add_argument('--from-source')
    parser.add_argument('--sample')
    args=parser.parse_args()
    if args.from_source:
        if args.sample:parser.error('--sample only applies to --repo')
        derive_source(args.from_source)
    else:
        if not args.sample:parser.error('--repo requires --sample')
        prepare(args.repo,args.sample)
