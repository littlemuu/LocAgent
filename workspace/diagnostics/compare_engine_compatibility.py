"""Reproducible small offline engine audit. Creates a new output directory only."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BATCH = Path('/Users/xiaomu/Documents/Codex/2026-11-10/task/locbench-remaining-batch134-20261113')
CURRENT = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    previous = {}
    def protect(path):
        assert path.is_file() and not path.is_symlink()
        previous[str(path)] = sha(path)
        return previous[str(path)]
    lock = json.loads((BATCH / 'ENGINE_LOCK.json').read_text())
    old = json.loads((ROOT / 'sqlglot_read_validation/v1/manifest.json').read_text())['base_manifest']['cases'][0]['plan']['locagent_engine']
    maps = {'current': old['files'], 'batch134': lock['engine']}
    roots = {'current': CURRENT, 'batch134': BATCH / 'runtime-engine'}
    engines = {}
    for name, files in maps.items():
        actual = {f: protect(roots[name] / f) for f in files}
        assert actual == files
        engines[name] = {'root': str(roots[name]), 'file_count': len(files),
                         'aggregate': hashlib.sha256(canonical(actual)).hexdigest(), 'files': actual}
    common = set(maps['current']) & set(maps['batch134'])
    changed = sorted(f for f in common if maps['current'][f] != maps['batch134'][f])
    differences = {'common_count': len(common), 'changed_shared': changed,
        'current_only': sorted(set(maps['current']) - set(maps['batch134'])),
        'batch_only': sorted(set(maps['batch134']) - set(maps['current']))}
    (out / 'diffs').mkdir()
    for name in changed:
        text = ''.join(difflib.unified_diff((CURRENT / name).read_text().splitlines(True),
            (roots['batch134'] / name).read_text().splitlines(True), fromfile='current/' + name,
            tofile='batch134/' + name))
        (out / 'diffs' / (name.replace('/', '__') + '.diff')).write_text(text)
    for p in (ROOT / 'readonly_agent').glob('*.py'):
        protect(p)
    for dirname in ('authority', 'authority-batches', 'authority-natural-choice', 'locbench_openhands',
                    'locbench_live', 'sqlglot_read_validation', 'natural_choice'):
        base = ROOT / dirname
        if base.is_dir():
            for p in base.rglob('*'):
                if p.is_file() and not p.is_symlink() and p.suffix in ('.json', '.jsonl', '.sqlite', '.md'):
                    protect(p)
    protect(BATCH / 'ENGINE_LOCK.json')
    protect(BATCH / 'technical-ready-current-engine.json')
    cases = []
    for row in json.loads((BATCH / 'technical-ready-current-engine.json').read_text()):
        if row['instance_id'] not in ('Delgan__loguru-1239', 'tobymao__sqlglot-3417'):
            continue
        path = Path(row['registry']) / (row['source_id'] + '.json')
        assert protect(path) == row['source_id'][9:]
        manifest = json.loads(path.read_text())
        bundle = Path(row['registry']) / manifest['bundle']
        assert manifest['engine'] == maps['batch134']
        assert set(manifest['artifacts']) == {p.relative_to(bundle).as_posix()
            for p in bundle.rglob('*') if p.is_file()}
        for name, expected in manifest['artifacts'].items():
            assert protect(bundle / name) == expected
        projection = {name[5:]: h for name, h in manifest['artifacts'].items()
            if name.startswith('repo/') and name.endswith('.py')
            and not any(p.startswith('.') for p in name[5:].split('/'))}
        hidden = [name for name in manifest['artifacts'] if name.startswith('repo/') and name.endswith('.py')
            and any(p.startswith('.') for p in name[5:].split('/'))]
        corpus = bundle / 'bm25' / row['instance_id'] / 'corpus.jsonl'
        chunks = [json.loads(line) for line in corpus.read_text().splitlines()]
        mismatched_paths = [i for i, c in enumerate(chunks) if c['file_path'] not in projection]
        invalid_spans = [i for i, c in enumerate(chunks) if type(c['start_line']) is not int
            or type(c['end_line']) is not int or c['start_line'] < 1 or c['end_line'] < c['start_line']]
        control = {k: manifest['preparation'].get(k) for k in ('engine_sha256', 'runtime', 'runtime_image', 'policy')}
        cases.append({'case': row['instance_id'], 'bundle': str(bundle), 'manifest': str(path),
            'commit': manifest['task']['base_commit'], 'source_hashes': projection,
            'source_count': len(projection), 'source_bytes': sum((bundle / 'repo' / name).stat().st_size for name in projection),
            'hidden_python': hidden, 'graph_sha256': manifest['artifacts']['graph.pkl'],
            'corpus_chunks': len(chunks), 'corpus_missing_source_paths': mismatched_paths,
            'corpus_invalid_spans': invalid_spans, 'preparation': control,
            'queries': (['_parse_id_var', '_parse_set_item_assignment', 'SET TAG']
                if 'sqlglot' in row['instance_id'] else ['traceback', 'loguru/_better_exceptions.py'])})
    preflight = {'engines': engines, 'differences': differences, 'cases': cases,
        'resources': {'free_disk_bytes': shutil.disk_usage(out).free,
            'physical_ram_bytes': os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE'),
            'worker_timeout_seconds': 120, 'worker_cpu_seconds': 90, 'workers_concurrent': 1},
        'query_provenance': 'Previously exposed developer cases; identifier/topic/path clues from prior actual traces. No labels or new tests read.',
        'model_requests': 0, 'target_code_execution': False, 'network': 'worker Python socket/model guards; scrubbed environment',
        'protected_before': previous}
    save(out / 'preflight.json', preflight)
    for case in [*cases, {'case': 'synthetic', 'queries': ['__init__', 'visible_task', 'core.py:Box.__init__']}]:
        for name in roots:
            request = {**case, 'engine': name, 'engine_root': str(roots[name])}
            with tempfile.TemporaryDirectory(prefix='engine-compat-worker-') as tmp:
                env = {'PATH': os.defpath, 'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
                    'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1', 'MPLCONFIGDIR': tmp,
                    'XDG_CACHE_HOME': tmp, 'TOKENIZERS_PARALLELISM': 'false',
                    'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}
                t = time.monotonic()
                run = subprocess.run([str(CURRENT / '.venv/bin/python'), '-I', '-B',
                    str(ROOT / 'diagnostics/engine_compatibility_worker.py')],
                    input=canonical(request), capture_output=True, cwd=tmp, env=env, timeout=120)
                stem = case['case'] + '-' + name
                (out / (stem + '.stderr')).write_bytes(run.stderr)
                save(out / (stem + '.execution.json'), {'exit_code': run.returncode,
                    'elapsed_seconds': time.monotonic() - t, 'stdout_bytes': len(run.stdout)})
                if run.returncode:
                    print(stem, 'FAILED', flush=True)
                    raise RuntimeError('worker_failed_inspect_saved_stderr')
                assert len(run.stdout) < 16 * 1024 * 1024
                save(out / (stem + '.json'), json.loads(run.stdout))
                print(stem, 'complete', flush=True)
    changed_history = [p for p, expected in previous.items() if sha(Path(p)) != expected]
    save(out / 'preservation.json', {'protected_count': len(previous), 'changed': changed_history})
    assert not changed_history
    print('protected', len(previous), 'unchanged', flush=True)


if __name__ == '__main__':
    main()
