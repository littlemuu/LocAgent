"""Freeze explicitly selected development inputs; never import repository code."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

from readonly_agent.core import Snapshot, digest, safe_name
from readonly_agent.preparation import make_plan

PROJECT = Path(__file__).resolve().parents[2]
ENGINE = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108')
OLD = Path('/Users/xiaomu/Documents/Codex/2026-11-10/task')
LATEST = OLD / 'locbench-remaining-batch101-20261113'
ORIGINAL = Path('/Users/xiaomu/Documents/Codex/locagent-locbench-adapter-20261110')
ROOT = PROJECT / 'locbench_openhands/v5'
SELECTED = ('Delgan__loguru-1239', 'tobymao__sqlglot-3417')
QUERY = ('traceback', 'SetItem')  # Literal words in the issue, not scoring targets.
REVISION = 'c44cf3b74e07ca642cec841b471a9939907c12a7'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def git_hash(kind, data):
    return hashlib.sha1(kind.encode() + b' ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def verify_tree(tree):
    """Reconstruct every tree object, including root, from cached recursive API data."""
    require(tree.get('truncated') is False, 'truncated_git_tree')
    entries = tree['tree']
    require(len({e['path'] for e in entries}) == len(entries), 'duplicate_tree_path')
    for entry in entries:
        safe_name(entry['path'])
        require((entry['type'], entry['mode']) in
                {('blob', '100644'), ('blob', '100755'), ('tree', '040000')},
                'unsupported_git_entry')
    expected = {'': tree['sha'], **{e['path']: e['sha'] for e in entries if e['type'] == 'tree'}}
    for directory, wanted in expected.items():
        children = [e for e in entries if e['path'].rpartition('/')[0] == directory]
        require(all(e['path'].rpartition('/')[0] in expected for e in children), 'orphan_tree_entry')
        children.sort(key=lambda e: (e['path'].rsplit('/', 1)[-1] + ('/' if e['type'] == 'tree' else '')).encode())
        data = b''.join((e['mode'].lstrip('0') + ' ' + e['path'].rsplit('/', 1)[-1]).encode()
                        + b'\0' + bytes.fromhex(e['sha']) for e in children)
        require(git_hash('tree', data) == wanted, 'git_tree_object_mismatch')
    require(all(e['path'].rpartition('/')[0] in expected for e in entries), 'orphan_tree_entry')
    return {e['path']: e for e in entries if e['type'] == 'blob'}


def check_sources(source, tree, records, bundle, artifacts):
    blobs = verify_tree(tree)
    require({r['path'] for r in records} == set(blobs) and len(records) == len(blobs), 'incomplete_source_manifest')
    require({p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} == set(blobs),
            'source_inventory_changed')
    hashes = {}
    for record in records:
        name = safe_name(record['path'])
        path = source / name
        require(not any(p.is_symlink() for p in [path, *path.parents]), 'linked_source')
        data = path.read_bytes()
        require(len(data) == record['size'] == blobs[name]['size'], 'source_size_mismatch')
        require(git_hash('blob', data) == record['git_blob_sha1'] == blobs[name]['sha'], 'git_blob_mismatch')
        actual = hashlib.sha256(data).hexdigest()
        require(actual == record['sha256'] == artifacts['repo/' + name], 'source_sha256_mismatch')
        require(sha(bundle / 'repo' / name) == actual, 'registry_source_mismatch')
        hashes[name] = actual
    return hashes


def functions(text):
    found = {}
    def visit(node, prefix=''):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + child.name
                if not isinstance(child, ast.ClassDef):
                    found[name] = (child.lineno, child.end_lineno)
                visit(child, name + '.')
            else:
                visit(child, prefix)
    visit(ast.parse(text))
    return found


def response(name, args, number):
    return {'stop_reason': 'tool_use', 'content': [
        {'type': 'tool_use', 'id': f'fixture-{number}', 'name': name, 'input': args}]}


def scripts(paths, query):
    shared_start = response('list_files', {'offset': 0}, 1)
    shared_read = response('read_file', {'path': paths[0], 'start_line': 1}, 3)
    finish = response('finish', {'files': [], 'entities': [],
        'answer': 'Scripted connectivity fixture only; no model judgment or localization score.'}, 4)
    return {arm: [shared_start, response('locagent_retrieve' if arm == 'retrieval' else 'search_text',
                   {'query': query, 'offset': 0}, 2),
                  response('locagent_retrieve', {'query':paths[0], 'offset':0}, 3)
                  if arm == 'retrieval' else shared_read, finish]
            for arm in ('baseline', 'retrieval')}


def case_plan(snapshot, issue):
    plan = make_plan(snapshot, issue, ENGINE)
    plan.update(purpose='One already exposed LocBench development case; paired integration validation, not held-out evaluation.',
                public_pricing_checked_utc_date='2026-11-13')
    return plan


def freeze():
    ROOT.mkdir(parents=True, exist_ok=False)
    ready = read(LATEST / 'technical-ready-current-engine.json')
    cases = []
    evidence = {str(LATEST / name): sha(LATEST / name) for name in
                ('BATCH_RESULT.json', 'FINAL_VERIFICATION.json', 'stage-ledger-560.csv', 'technical-ready-current-engine.json')}
    for index, identifier in enumerate(SELECTED):
        row = next(r for r in ready if r['instance_id'] == identifier)
        require(row['original_local_split'] == 'development' and row.get('known_repository_exposure') is True,
                'only_previously_exposed_development_cases')
        registry = Path(row['registry']) / (row['source_id'] + '.json')
        registered = read(registry)
        batch = registry.parent.parent
        audit_path = batch / 'storage-audits' / (identifier + '.json')
        audit = read(audit_path)
        require(audit['storage_status'] == 'ready' and audit['all_git_blobs_verified'] and audit['git_tree_objects_verified'],
                'source_not_ready')
        require(sha(audit_path) == registered['preparation']['storage_audit_sha256'], 'audit_binding_changed')
        source = Path(audit['source_path'])
        snapshot_path = source.parent / 'manifest.json'
        storage = read(snapshot_path)
        require(sha(snapshot_path) == audit['storage_manifest_sha256'], 'storage_manifest_changed')
        tree_path = Path(audit['directory']) / 'evidence/git-tree.json'
        commit_path = tree_path.with_name('git-commit.json')
        tree, commit = read(tree_path), read(commit_path)
        task_path = batch / 'runtime-inputs' / identifier / 'task.json'
        task = read(task_path)
        original_task = ORIGINAL / 'inputs' / identifier / 'task.json'
        require(set(task) == {'instance_id', 'repo', 'base_commit', 'problem_statement'}, 'runtime_field_leak')
        require(task == registered['task'] == read(original_task), 'task_mapping_changed')
        require(task['base_commit'] == commit['sha'] == audit['base_commit'] == storage['base_commit'], 'commit_mismatch')
        require(commit['tree']['sha'] == tree['sha'] == audit['tree_sha'] == registered['preparation']['tree_sha'], 'tree_mismatch')
        require(registered['dataset']['dataset_revision'] == REVISION, 'dataset_revision_changed')
        bundle = registry.parent / registered['bundle']
        hashes = check_sources(source, tree, storage['files'], bundle, registered['artifacts'])
        paths = sorted(n for n in hashes if n.endswith('.py') and not any(p.startswith('.') for p in n.split('/')))
        require(len(paths) <= 512 and sum((source/n).stat().st_size for n in paths) <= 8*1024*1024,
                'existing_index_size_budget_exceeded')
        root = ROOT / 'cases' / identifier
        for name in paths:
            target = root / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source/name).read_bytes())
        snapshot = Snapshot(root / 'source', paths)
        require(dict(snapshot.hashes) == {n:hashes[n] for n in paths}, 'copied_source_changed')
        query = QUERY[index]
        require(query in task['problem_statement'], 'fixture_query_not_in_issue')
        save(root / 'task.json', task)
        case = {'root': 'source', 'source_files': paths, 'issue': task['problem_statement'], 'scripts': scripts(paths, query)}
        save(root / 'case.json', case)
        label_path = batch / 'scoring-only/labels' / (identifier + '.json')
        mapping_path = batch / 'scoring-only/mapping-audits' / (identifier + '.json')
        labels, mapping = read(label_path), read(mapping_path)
        require(all(labels[k] == task[k] for k in ('instance_id','repo','base_commit')), 'gold_task_mismatch')
        require(mapping['status'] == 'ready' and mapping['source_id'] == row['source_id'], 'mapping_not_ready')
        gold = list(dict.fromkeys(labels['edit_functions']))
        require(set(gold) == {r['label'] for r in mapping['gold_mappings']}, 'label_mapping_changed')
        for target in mapping['gold_mappings']:
            file, _, entity = target['label'].partition(':')
            require(file in snapshot.files, 'gold_outside_source_projection')
            require(functions(snapshot.files[file]).get(entity) ==
                    (target['strict_ast']['start_line'], target['strict_ast']['end_line']), 'gold_ast_span_mismatch')
        for check in mapping['patch_checks']:
            blob = git_hash('blob', (source / check['path']).read_bytes())
            require(blob == check['verified_blob'] and blob.startswith(check['patch_old_blob']), 'patch_base_mismatch')
        save(ROOT / 'scoring-only' / (identifier + '.json'), {
            'instance_id': identifier, 'base_commit': task['base_commit'], 'gold_entities': gold,
            'gold_files': list(dict.fromkeys(t.partition(':')[0] for t in gold)),
            'official_normalized_gold': [x[:-9] if x.endswith('.__init__') else x for x in gold],
            'mapping': mapping, 'labels_sha256': sha(label_path),
            'semantics': 'Changed functions in reference patch; not a unique root-cause oracle.'})
        for path in (registry, audit_path, snapshot_path, tree_path, commit_path, task_path, original_task, label_path, mapping_path):
            evidence[str(path)] = sha(path)
        save(root / 'source-audit.json', {'base_commit': task['base_commit'], 'tree_sha': tree['sha'],
            'full_repository_files_verified': len(hashes), 'all_git_blobs_rechecked': True,
            'all_git_tree_objects_rechecked': True, 'registry_source_rechecked': True,
            'all_source_sha256': hashes, 'python_projection_sha256': dict(snapshot.hashes),
            'projection': 'All non-hidden .py files, including tests/docs Python. No non-Python files exposed to either arm.',
            'provenance': 'Revalidated cached public HTTPS commit/tree evidence; no new remote attestation.'})
        cases.append({'id': identifier, 'repo': task['repo'], 'base_commit': task['base_commit'],
            'case_file': str((root/'case.json').relative_to(PROJECT)), 'plan': case_plan(snapshot, case['issue']),
            'arm_order': ['baseline','retrieval'] if index == 0 else ['retrieval','baseline'],
            'source_file_count': len(paths), 'source_bytes': sum(len(x.encode()) for x in snapshot.files.values()),
            'exposure': row, 'model_exposure': 'Prior model exposure not exhaustively established; treat as exposed development, never independent test.'})
    save(ROOT / 'upstream-evidence.json', evidence)
    manifest = {'version': 1, 'kind': 'locbench_exposed_development_integration', 'cases': cases,
        'dataset_revision': REVISION, 'authorization': 'not_granted', 'transport': 'offline_only',
        'suite_budget_micro_cny': 34_000_000, 'max_requests': 16, 'full_reservations_micro_cny': 33_816_576,
        'live_entrypoint_enabled': False, 'account_pricing_confirmed': False,
        'scoring_policy': 'Strict distinct exact top-5 file/entity precision/recall/F1/MRR; official-reference metrics separate. '
                          'Failure scores zero in planned denominator; not-run raw score null and reported explicitly. '
                          'Scripted fixtures never receive quality scores. Report raw predictions and normal finish.',
        'source_policy': 'Immutable non-hidden Python projection identical for both arms; no patch/gold metadata sent.',
        'autonomy_policy': 'Live proposal tool_choice auto during investigation, finish-only last turn. Never force or supplement retrieval.',
        'hashes': {str(p.relative_to(ROOT)): sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file()},
        'adapter_hashes': {str(p.relative_to(PROJECT)): sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}}
    save(ROOT / 'manifest.json', manifest)
    print(json.dumps({'frozen_hash': digest(manifest), 'cases': len(cases), 'live_calls': 0}))


def validate(root=ROOT):
    manifest = read(root / 'manifest.json')
    require(manifest['authorization'] == 'not_granted' and manifest['transport'] == 'offline_only'
            and manifest['live_entrypoint_enabled'] is False, 'offline_only')
    for name, expected in manifest['hashes'].items():
        require(sha(root/name) == expected, 'frozen_input_changed')
    for name, expected in manifest['adapter_hashes'].items():
        require(sha(PROJECT/name) == expected, 'adapter_changed')
    for item in manifest['cases']:
        path = PROJECT / item['case_file']
        case = read(path)
        snapshot = Snapshot(path.parent / case['root'], case['source_files'])
        require(case_plan(snapshot, case['issue']) == item['plan'], 'plan_or_runtime_changed')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['freeze','check'])
    args = parser.parse_args()
    if args.action == 'freeze':
        freeze()
    else:
        print(json.dumps({'status': 'unchanged', 'hash': digest(validate()), 'live_calls': 0}))
