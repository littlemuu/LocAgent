"""Hash-addressed operator-prepared sources. HTTP never accepts repo/index paths."""
import hashlib
import json
import os
from pathlib import Path

from util.localization_contract import LocalizationRequest, LocalizationOptions


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()


def registry():
    return Path(os.environ.get('LOCAGENT_SOURCE_ROOT','outputs/stage4/sources')).resolve()


def file_hashes(directory):
    result={}
    for p in sorted(directory.rglob('*')):
        if p.is_symlink():
            raise ValueError('Prepared artifacts must not contain symlinks')
        if p.is_file():
            result[p.relative_to(directory).as_posix()]=digest(p.read_bytes())
    return result


def load_manifest(source_id):
    if not source_id.startswith('prepared-') or len(source_id)!=73:
        raise ValueError('Invalid prepared source ID')
    data=(registry()/(source_id+'.json')).read_bytes()
    if digest(data)!=source_id[9:]:
        raise ValueError('Manifest hash mismatch')
    manifest=json.loads(data)
    bundle=(registry()/manifest['bundle']).resolve()
    if not bundle.is_relative_to(registry()):
        raise ValueError('Bundle escapes registry')
    if file_hashes(bundle)!=manifest['artifacts']:
        raise ValueError('Prepared artifacts changed')
    # Check the implementation used to build/execute this manifest is unchanged.
    base=Path(__file__).resolve().parents[1]
    if any(digest((base/name).read_bytes())!=sha for name,sha in manifest['engine'].items()):
        raise ValueError('Engine changed; prepare a new manifest/experiment')
    return manifest,bundle


def validate_source(request):
    if request.source_id=='demo-v1':
        return
    manifest,_=load_manifest(request.source_id)
    if (request.problem_statement!=manifest['task']['problem_statement']
        or request.options.max_iterations!=manifest['config']['max_calls']
        or request.max_attempts!=1 or request.demo_scenario.value!='success'):
        raise ValueError('Prepared task must match its fixed manifest and single-attempt policy')


def localize_prepared(request, provider):
    import pickle
    from dependency_graph import RepoEntitySearcher
    from plugins.location_tools.retriever.bm25_retriever import build_module_retriever_from_graph
    from util.localizer import GraphLocalizer
    validate_source(request)
    manifest,bundle=load_manifest(request.source_id)
    with (bundle/'graph.pkl').open('rb') as stream:
        graph=pickle.load(stream)  # Only our own trusted, hashed build artifacts.
    retriever=build_module_retriever_from_graph(
        entity_searcher=RepoEntitySearcher(graph),similarity_top_k=manifest['config']['top_k'])
    engine=GraphLocalizer.from_graph(graph,provider=provider,
        model_name=manifest['config']['model'],
        options=LocalizationOptions(**request.options.model_dump()),
        bm25_index_dir=bundle/'bm25',module_retriever=retriever)
    return engine.localize(LocalizationRequest(**manifest['task']))


def localize(request):
    if request.source_id=='demo-v1':
        from locagent_service.fixture import localize_demo
        return localize_demo(request)
    from locagent_service.budget import BudgetProvider
    manifest,_=load_manifest(request.source_id)
    return localize_prepared(request,BudgetProvider.from_env(request.source_id,manifest['config'],
        arm=request.options.suppress_repeats))
