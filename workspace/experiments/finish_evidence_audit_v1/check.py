"""Conservative source-visibility and mention checks. No gold/network/file access.

Graph lookups verify repository identity AFTER the run; a resolved ID is not proof
that the model knew its owner. Mention matches are review leads, never additions.
"""
import ast
import re
from readonly_agent.read_lines import source_lines

TOKEN = re.compile(r'(?u)(?:[^\W\d]|_)\w*(?:\.(?:[^\W\d]|_)\w*)*')


def mention_tokens(answer):
    # Avoid treating ordinary English words such as "copy" or "run" as symbols.
    selected = set()
    for block in re.findall(r'`([^`\n]+)`', answer):
        selected.update(TOKEN.findall(block))
    for m in TOKEN.finditer(answer):
        token = m.group()
        if '_' in token or '.' in token or re.match(r'\s*\(', answer[m.end():]):
            selected.add(token)
    return sorted(selected)


def symbol_pattern(symbol):
    return re.compile(r'(?<![\w])' + re.escape(symbol) + r'(?![\w])')


def entity_metadata(graph):
    result = {}
    for nid, data in graph.items():
        if data.get('type') not in ('function', 'class'):
            continue
        node = ast.parse(data['code']).body[0]
        body = node.body
        doc = body[0] if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str) else None
        implementation = body[1:] if doc else body
        result[nid] = {'path': nid.partition(':')[0], 'name': nid.partition(':')[2],
                       'start': data['start_line'], 'end': data['end_line'],
                       'body_start': data['start_line'] + implementation[0].lineno - 1 if implementation else None,
                       'kind': data['type']}
    return result


def observed_lines(tool, args, result, files):
    """Only rows delivered to the model, not requested end_line or unseen pages."""
    text = result.get('text', '')
    path = args.get('path') if tool == 'read_file' else None
    rows = []
    for raw in text.split('\n'):
        old = re.match(r'##Searching for entity `([^`]+)`', raw)
        new = re.match(r'#\d+ (.+?) \[', raw)
        if old or new:
            path = (old or new).group(1).partition(':')[0]
        if tool == 'search_text':
            match = re.match(r'(.+?\.py):(\d+): (.*)$', raw)
            if not match:
                continue
            current, number, content = match.group(1), int(match.group(2)), match.group(3)
        else:
            match = re.match(r'^\s*(\d+)(?: \| |: )(.*)$', raw)
            if not match or path is None:
                continue
            current, number, content = path, int(match.group(1)), match.group(2)
        if current not in files:
            continue
        lines = source_lines(files[current])
        if not 1 <= number <= len(lines):
            continue
        expected = lines[number - 1]
        # Legacy entity rendering removes initial indentation at the AST boundary.
        full = content == expected or tool == 'locagent_retrieve' and content.lstrip() == expected.lstrip()
        rows.append({'path': current, 'line': number, 'text': content, 'full_line': full})
    return rows


def inspect_entity(nid, meta, evidence):
    if nid not in meta:
        name = nid.partition(':')[2]
        return {'id': nid, 'exists_as_definition_id': False,
                'same_leaf_definitions': sorted(n for n, d in meta.items() if d['name'].split('.')[-1] == name.split('.')[-1])}
    data = meta[nid]; leaf = data['name'].split('.')[-1]
    observations = []; full_lines = set(); definition = False; exact = False
    pattern = symbol_pattern(leaf)
    for e in evidence:
        text = e['result'].get('text', '')
        qualified = bool(re.search(r'(?<![\w./:])' + re.escape(nid) + r'(?![\w.])', text))
        relevant = [r for r in e['lines'] if r['path'] == data['path']]
        references = [r for r in relevant if pattern.search(r['text'])]
        rows = [r for r in relevant if data['start'] <= r['line'] <= data['end']]
        full_lines.update(r['line'] for r in rows if r['full_line'])
        def_seen = any(r['line'] == data['start'] and re.search(r'\b(?:def|class)\s+'+re.escape(leaf)+r'\b', r['text']) for r in rows)
        definition |= def_seen; exact |= qualified
        if qualified or references or rows:
            observations.append({'tool_call_id': e['tool_call_id'], 'tool': e['tool'],
                                 'exact_id_visible': qualified, 'definition_line_visible': def_seen,
                                 'reference_lines': [{'line':r['line'],'text':r['text']} for r in references],
                                 'full_source_lines_inside_entity': [r['line'] for r in rows if r['full_line']]})
    start = data['body_start']
    complete = start is not None and all(n in full_lines for n in range(start, data['end']+1))
    return {'id':nid,'exists_as_definition_id':True, 'metadata':data,
            'exact_id_visible':exact,'definition_line_visible':definition,
            'body_start_visible':start in full_lines if start else None,
            'body_lines_all_visible':complete,'observations':observations,
            'qualification_note':'Repository graph verifies owner post hoc; bare leaf visibility alone does not prove the model knew its qualified ID.'}


def audit_finish(answer, meta, evidence):
    predictions = [inspect_entity(n,meta,evidence) for n in answer['entities']]
    tokens = mention_tokens(answer['answer']); mentions=[]
    for token in tokens:
        bare = token[5:] if token.startswith('self.') else token[4:] if token.startswith('cls.') else token
        exact = [n for n,d in meta.items() if d['name']==bare]
        matches = exact or [n for n,d in meta.items() if d['name'].endswith('.'+bare)]
        if not matches:
            continue
        candidates = [inspect_entity(n,meta,evidence) for n in sorted(matches)]
        observed = [c for c in candidates if c.get('exact_id_visible') or c.get('definition_line_visible') or
                    any(o['reference_lines'] for o in c.get('observations',[]))]
        mentions.append({'token':token,'repository_match_count':len(matches),
                         'ambiguous_repository_symbol':len(matches)>1,
                         'observed_candidates':observed,
                         'omitted_observed_candidates':[c['id'] for c in observed if c['id'] not in answer['entities']],
                         'review_only_not_required_additions':True})
    return {'predictions':predictions,'mentions':mentions,'slot_count':len(answer['entities']),
            'free_slots':5-len(answer['entities']),'answer_unchanged':True}
