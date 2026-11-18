"""Project behavior inputs bound by prepared sources and phased plans.

Conservative package closure: include all Python modules (also __init__) in the
execution/index/scoring packages, not a fragile handpicked import list. Include
non-Python prompt and parser programs explicitly. New/deleted names change the
manifest. Credentials, datasets, generated results and bytecode are excluded.
"""
from pathlib import Path
from locagent_service.sources import digest

PACKAGE_ROOTS = (
    'locagent_service', 'util', 'plugins', 'dependency_graph', 'repo_index',
)
RESOURCE_RULES = (
    ('util/prompts', '*.j2'),
    ('repo_index/codeblocks/parser/queries', '*.scm'),
    ('locagent_service/migrations', '*.sql'),
)
EXPLICIT_FILES = (
    'evaluation/eval_metric.py',
    'requirements.txt', 'requirements-cpu.txt', 'requirements-service.txt',
    'requirements-runtime.txt',
)
POLICY = 'locagent-project-behavior-v1'


def behavior_hashes(root):
    """Bind contents AND the recursive filename set; refuse links/escaped paths."""
    root = Path(root).resolve()
    names = set(EXPLICIT_FILES)
    for directory in PACKAGE_ROOTS:
        folder = root / directory
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError('Missing or linked behavior package: ' + directory)
        for p in folder.rglob('*'):
            if p.is_symlink():
                raise ValueError('Behavior package cannot contain symlinks')
            if p.is_file() and p.suffix == '.py':
                names.add(p.relative_to(root).as_posix())
    for directory, pattern in RESOURCE_RULES:
        names.update(p.relative_to(root).as_posix() for p in (root/directory).rglob(pattern))
    result = {}
    for name in sorted(names):
        path = root/name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('Missing, linked or escaped behavior input: ' + name)
        result[name] = digest(path.read_bytes())
    return result
