"""Source-only retrieval over the existing validated entity graph/index.

No new index, gold, filesystem discovery, target imports, or model access.
Ranking uses entity identifiers, not source bodies. Preview omissions are explicit;
read_file remains the way to fetch complete source. Frozen v4 stays untouched.
"""
import ast
import json
import re
from pathlib import PurePosixPath

from experiments.path_retrieval_v4.retriever import is_path_query, path_candidates
from readonly_agent.core import encoded
from readonly_agent.read_lines import source_lines

VERSION = 'retrieval-evidence-v6'
PREVIEW_JSON_BYTES = 2800
NOTICE = ('Ranked source previews; omitted code is NOT shown. Offsets paginate previews only. '
          'Use read_file with each path and line range for complete source.\n')


def normalized(value):
    # Explicit identifier aliases only. Never equate digits and letters or edit paths.
    return value.casefold().strip('_')


def components(node):
    path, _, symbol = node.partition(':')
    pieces = list(PurePosixPath(path).parts)
    if pieces:
        pieces[-1] = PurePosixPath(pieces[-1]).stem
    pieces.extend(symbol.split('.') if symbol else [])
    return pieces


def prune_containers(rows, nodes):
    """Suppress broad containers when a narrower returned candidate covers part of it."""
    kept, omitted = [], []
    for row in rows:
        nid = row['id']; d = nodes[nid]
        if d['type'] in ('file', 'class'):
            children = [other['id'] for other in rows if other['id'] != nid
                        and other['id'].partition(':')[0] == nid.partition(':')[0]
                        and (d['type'] == 'file' and ':' in other['id']
                             or d['type'] == 'class' and other['id'].startswith(nid + '.'))]
            if children:
                omitted.append({'id': nid, 'reason': 'overlapping_container', 'covered_by': children})
                continue
        kept.append(row)
    return kept, omitted


def rank_candidates(query, nodes, lexical_ids, searchable_ids):
    """Deterministic component reranking with bounded positive BM25 fallback.

    Exact qualified names retain all file ambiguities. Complete identifier-component
    coverage wins over partial matches. Aliases do not rewrite displayed spellings.
    """
    eligible = {n for n in searchable_ids if n in nodes and nodes[n].get('type') in ('file', 'class', 'function')}
    if query in nodes and nodes[query].get('type') in ('file', 'class', 'function'):
        return [{'id': query, 'match': 'exact_id'}], []
    if is_path_query(query):
        rows = [{'id': r['path'], 'match': r['match']} for r in path_candidates(
            query, [n for n, d in nodes.items() if d.get('type') == 'file'])]
        return rows, []
    exact = sorted(n for n in eligible if ':' in n and n.partition(':')[2] == query)
    if exact:
        return [{'id': n, 'match': 'exact_qualified_name'} for n in exact[:5]], []
    terms = re.findall(r'[\w]+', query, re.UNICODE)
    terms = list(dict.fromkeys(normalized(t) for t in terms if normalized(t)))
    # Only short identifier-like queries receive supplemental component matches.
    use_components = 0 < len(terms) <= 6
    lex = {n: i for i, n in enumerate(dict.fromkeys(lexical_ids)) if n in eligible}
    scored = []
    for nid in sorted(eligible):
        parts = {normalized(t) for t in components(nid)}
        hits = sum(t in parts for t in terms) if use_components else 0
        leaf = normalized(nid.partition(':')[2].split('.')[-1]) if ':' in nid else ''
        leaf_hit = int(bool(leaf) and leaf in terms) if use_components else 0
        if nid not in lex and not (hits and leaf_hit):
            continue
        scored.append((nid, hits, leaf_hit))
    complete = [r for r in scored if use_components and r[1] == len(terms) and r[2]]
    pool = complete or scored
    pool.sort(key=lambda r: (-r[1], -r[2], lex.get(r[0], 10**9), r[0]))
    rows = [{'id': n, 'match': 'identifier_components' if hits and leaf else 'positive_bm25',
             'component_hits': hits, 'component_total': len(terms),
             'alias_rule': 'casefold_and_edge_underscores_only' if hits and leaf else None}
            for n, hits, leaf in pool]
    kept, omitted = prune_containers(rows, nodes)
    return kept[:5], omitted


def ast_entities(source):
    """Parse only, never import/execute. Physical source lines remain unchanged."""
    parser_source = source[1:] if source.startswith('\ufeff') else source
    tree = ast.parse(parser_source)
    result = {}
    def visit(node, prefix=''):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                result[(name, child.lineno, child.end_lineno)] = child
                visit(child, name + '.')
            else:
                visit(child, prefix)
    visit(tree)
    return tree, result


def doc_statement(node):
    if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
        return node.body[0]
    return None


class EvidenceRetriever:
    def __init__(self, base, snapshot):
        if base.snapshot_id != snapshot.identity:
            raise ValueError('retriever_snapshot_mismatch')
        self.base, self.snapshot = base, snapshot
        self.snapshot_id = snapshot.identity
        self.nodes = dict(base._graph.nodes(data=True))
        for nid, data in self.nodes.items():
            if data.get('type') == 'directory':
                continue
            path = nid.partition(':')[0]
            if path not in snapshot.files:
                raise ValueError('entity_outside_snapshot')
            if data.get('type') == 'file' and data.get('code') != snapshot.files[path]:
                raise ValueError('graph_source_content_mismatch')
        # Reuse the persisted corpus's search scope (including its test exclusions).
        self.searchable = tuple(json.loads(r['_node_content'])['text'] for r in base._lexical.corpus)
        self.parsed = {}
        self.last_audit = None

    def lexical(self, query):
        from plugins.location_tools.retriever.bm25_retriever import retrieve_nonempty
        from util.localizer import _ENGINE_LOCK
        if not _ENGINE_LOCK.acquire(blocking=False):
            raise RuntimeError('locagent_session_busy')
        original = self.base._lexical.similarity_top_k
        try:
            self.base._lexical.similarity_top_k = min(20, len(self.base._lexical.corpus))
            return [n.text for n in retrieve_nonempty(self.base._lexical, query) if n.score > 0]
        finally:
            self.base._lexical.similarity_top_k = original
            _ENGINE_LOCK.release()

    def preview(self, row, rank, seen):
        nid = row['id']; data = self.nodes[nid]; path, _, name = nid.partition(':')
        source = self.snapshot.files[path]; lines = source_lines(source)
        if path not in self.parsed:
            self.parsed[path] = ast_entities(source)
        tree, entities = self.parsed[path]
        start, end = (1, len(lines)) if data['type'] == 'file' else (data['start_line'], data['end_line'])
        node = tree if data['type'] == 'file' else entities.get((name, start, end))
        if node is None:
            raise ValueError('entity_ast_span_mismatch')
        doc = doc_statement(node)
        body = node.body[1:] if doc is not None else node.body
        impl = body[0].lineno if body else None
        header = (f'#{rank} {nid} [{row["match"]}]\n'
                  f'path={path}; lines={start}-{end}; implementation_start={impl}; '
                  f'read_file(path={json.dumps(path, ensure_ascii=False)}, start_line={start}, end_line={end})\n')
        if doc is not None:
            header += (f'Docstring lines {doc.lineno}-{doc.end_lineno}; preview prioritizes implementation. '
                       'read_file preserves complete text.\n')
        if row['match'].startswith('approximate_'):
            header += 'Approximate filename candidate, not a verified correction.\n'
        # Show a bounded signature then implementation head/tail, not an enormous docstring.
        signature_end = node.body[0].lineno - 1 if node.body else start
        signature = list(range(start, min(start + 2, signature_end, end) + 1)) if data['type'] != 'file' else []
        body_lines = list(range(impl, min(impl + 15, end) + 1)) if impl is not None else []
        tail = list(range(max(impl or start, end - 3), end + 1)) if impl is not None and end > impl + 15 else []
        selected = list(dict.fromkeys(signature + body_lines + tail))
        text = header; shown = []; cut = []; previous = None
        for number in selected:
            if (path, number) in seen:
                cut.append(number)
                continue
            original = lines[number - 1]
            short = original[:160]
            line = f'{number}: {short}' + (' … [line excerpt]' if len(original) > 160 else '') + '\n'
            gap = f'... lines {previous + 1}-{number - 1} omitted ...\n' if previous is not None and number > previous + 1 else ''
            candidate = text + gap + line
            if len(encoded({'text': candidate + 'Preview incomplete; read full range above.\n', 'next_offset': 999999})) > PREVIEW_JSON_BYTES:
                cut.extend(n for n in selected if n >= number)
                break
            text = candidate; shown.append(number); seen.add((path, number)); previous = number
        complete = shown == list(range(start, end + 1)) and all(len(lines[n-1]) <= 160 for n in shown)
        if not complete:
            text += 'Preview incomplete; omitted/overlapping lines remain available via read_file.\n'
        if not body:
            text += 'No non-docstring body statements.\n'
        return text, {'id': nid, 'rank': rank, 'match': row['match'], 'path': path,
                      'start_line': start, 'end_line': end, 'implementation_start': impl,
                      'shown_lines': shown, 'complete': complete,
                      'docstring_omitted': doc is not None and not all(n in shown for n in range(doc.lineno, doc.end_lineno + 1)),
                      'overlap_or_budget_omissions': cut}

    def retrieve(self, query):
        if not isinstance(query, str) or not 1 <= len(query) <= 256:
            raise ValueError('invalid_query')
        direct = query in self.nodes or is_path_query(query) or any(n.partition(':')[2] == query for n in self.searchable if ':' in n)
        lexical = [] if direct else self.lexical(query)
        rows, suppressed = rank_candidates(query, self.nodes, lexical, self.searchable)
        if not rows:
            self.last_audit = {'query': query, 'candidates': [], 'suppressed': suppressed}
            return 'No matching source paths (exact basename or bounded one-edit alternatives).' if is_path_query(query) else 'No locations found.'
        text = NOTICE; audit = []; seen = set()
        for rank, row in enumerate(rows, 1):
            snippet, record = self.preview(row, rank, seen)
            text += snippet + '\n'; audit.append(record)
        self.last_audit = {'query': query, 'candidates': audit, 'suppressed': suppressed,
                           'lexical_pool_size': len(lexical), 'renderer': VERSION}
        return text
