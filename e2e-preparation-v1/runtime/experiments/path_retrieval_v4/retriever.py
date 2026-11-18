"""Augment a validated graph retriever for single Python filename/path queries.

No filesystem discovery, gold labels, confusable-character rewrite, or query
expansion. Near matches are candidates, never a corrected answer. Other queries
retain the frozen entity BM25 behavior.
"""
import json
import re
from pathlib import PurePosixPath


def one_edit(a, b):
    """One insertion/deletion/substitution (not unrestricted fuzzy matching)."""
    if a == b:
        return False
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), len(a))
    return a[i:] == b[i + 1:]


def is_path_query(query):
    # A narrow filename-query route; prose, symbols, and unsafe paths stay out.
    if not isinstance(query, str) or not 1 <= len(query) <= 512:
        return False
    if (not re.fullmatch(r'[\w./-]+\.py', query) or query.startswith('/')
            or any(x in ('', '.', '..') or x.startswith('.') for x in query.split('/'))):
        return False
    return True


def path_candidates(query, files, limit=5):
    if not is_path_query(query):
        return []
    q = PurePosixPath(query)
    rows = []
    for path in sorted(files):
        p = PurePosixPath(path)
        if p.name == q.name:
            kind = 'exact_path' if path == query else 'exact_basename'
        elif (p.suffix == '.py' and min(len(p.stem), len(q.stem)) >= 8
              and one_edit(p.stem, q.stem)):
            kind = 'approximate_basename_one_edit'
        else:
            continue
        # Parent paths only break filename ties; directory-only nodes never rank.
        common = sum(a == b for a, b in zip(reversed(p.parts[:-1]), reversed(q.parts[:-1])))
        rows.append({'path': path, 'match': kind, 'parent_components_matching': common})
    order = {'exact_path': 0, 'exact_basename': 1, 'approximate_basename_one_edit': 2}
    rows.sort(key=lambda r: (order[r['match']], -r['parent_components_matching'], r['path']))
    return rows[:limit]


class PathAwareRetriever:
    def __init__(self, base):
        self.base = base
        self.snapshot_id = base.snapshot_id
        self.files = tuple(n for n, d in base._graph.nodes(data=True) if d.get('type') == 'file')

    def retrieve(self, query):
        # Preserve exact entity queries and the previous graph renderer.
        if query in self.base._graph:
            return self.base.retrieve(query)
        candidates = path_candidates(query, self.files)
        if not candidates:
            if is_path_query(query):
                return 'No matching source paths (exact basename or bounded one-edit alternatives).'
            return self.base.retrieve(query)
        from util.localizer import _ENGINE_LOCK, _graph_session
        if not _ENGINE_LOCK.acquire(blocking=False):
            raise RuntimeError('locagent_session_busy')
        try:
            task = {'instance_id': 'readonly-' + self.snapshot_id[:16],
                    'repo': 'source/snapshot', 'base_commit': self.snapshot_id,
                    'problem_statement': ''}
            with _graph_session(self.base._graph, task, None, self.base._lexical) as ops:
                text = ops.get_entity_contents([r['path'] for r in candidates])
            header = ('Source-path candidates (exact spelling preserved; approximate matches are '
                      'unverified alternatives, not corrections):\n'
                      + json.dumps(candidates, ensure_ascii=False, separators=(',', ':')) + '\n')
            return header + text
        finally:
            _ENGINE_LOCK.release()
