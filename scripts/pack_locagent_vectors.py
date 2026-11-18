#!/usr/bin/env python3
"""Read-only transfer of existing LocAgent evidence. Standard library, no network.
Never imports project code, resumes a run, generates vectors, or reads env files.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

PIN = '78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b'
CORE = (
    'outputs/bailian-expanded50-20261016/frozen/manifest.json',
    'outputs/bailian-expanded-budget-runs/bailian-expanded50-78e24794-cap2-20261016-r01/run.json',
    'outputs/bailian-expanded-budget-runs/bailian-expanded50-78e24794-cap2-20261016-r01/continuation-authorization.json',
    'outputs/bailian-expanded50-resumed-evaluation-20261016-r01/results.json',
    'outputs/bailian-expanded50-resumed-evaluation-20261016-r01/ledger-audit.json',
)
PATTERNS = (
    'outputs/bailian*',
    'docs/BAILIAN*',
    'locagent_service/bailian_*.py',
    'locagent_service/rag_offline.py',
    'scripts/*expanded*.py',
    'scripts/offline_bailian_rrf.py',
    'requirements*.txt',
    'pyproject.toml',
    'uv.lock',
)


def excluded(path):
    for part in path.parts:
        low = part.lower()
        if (low.startswith('.env') or low in {'.git', '.venv', '__pycache__', 'provider.local.json'}
                or low.endswith(('.pem', '.key'))):
            return True
    return False


def collect(root):
    selected, skipped = {}, []
    for pattern in PATTERNS:
        for top in sorted(root.glob(pattern)):
            if top.is_symlink():
                raise ValueError('Refusing symbolic link: ' + str(top.relative_to(root)))
            members = [top] if top.is_file() else sorted(top.rglob('*'))
            for path in members:
                relative = path.relative_to(root)
                if excluded(relative):
                    skipped.append(str(relative))
                    continue
                if path.is_symlink():
                    raise ValueError('Refusing symbolic link: ' + str(relative))
                if path.is_dir():
                    continue
                if not stat.S_ISREG(path.lstat().st_mode):
                    raise ValueError('Refusing non-regular file: ' + str(relative))
                selected[str(relative)] = path
    return selected, sorted(set(skipped))


def pack(root, output):
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Select an existing real workspace directory')
    root = root.resolve()
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Output already exists; will not overwrite')
    # Keep output outside the source tree to avoid recursive/self inclusion.
    if root == output.resolve() or root in output.resolve().parents:
        raise ValueError('Output must be outside the source workspace')
    selected, skipped = collect(root)
    if not any(name.startswith('outputs/bailian') for name in selected):
        raise ValueError('No historical outputs/bailian* files found; no archive created')
    records = {}
    # Mode x never overwrites. An interrupted archive is retained for diagnosis.
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=1, allowZip64=True) as archive:
        for name, path in sorted(selected.items()):
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as source:
                before = os.fstat(source.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError('Source is no longer a regular file: ' + name)
                digest, size = hashlib.sha256(), 0
                with archive.open(name, 'w', force_zip64=True) as target:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        size += len(chunk)
                        target.write(chunk)
                after = os.fstat(source.fileno())
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or size != before.st_size:
                    raise ValueError('Source changed while copying: ' + name)
                records[name] = {'sha256': digest.hexdigest(), 'bytes': size}
        actual = records.get(CORE[0], {}).get('sha256')
        manifest = {
            'format': 'locagent-vector-evidence-transfer-v1',
            'purpose': 'transport integrity only; not vector authenticity or reuse approval',
            'source_root': str(root), 'files': records,
            'missing_core_files': [name for name in CORE if name not in records],
            'excluded_names': skipped, 'expanded_manifest_expected_sha256': PIN,
            'expanded_manifest_actual_sha256': actual,
            'expanded_manifest_matches_historical_pin': actual == PIN,
            'source_files_modified': False, 'network_calls': 0,
        }
        archive.writestr('TRANSFER_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    digest = hashlib.sha256()
    with output.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'archive': str(output), 'sha256': digest.hexdigest(), 'files': len(records),
            'missing_core_files': manifest['missing_core_files'],
            'expanded_manifest_matches_historical_pin': actual == PIN,
            'note': 'Transfer completed; vector provenance and reuse still require offline verification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/home/lenovo/projects/LocAgent-rag-preview')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(pack(args.root, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
