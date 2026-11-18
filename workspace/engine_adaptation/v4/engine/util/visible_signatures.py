"""Lexical signature ranges in renderer-produced class skeletons.

Tokenization does not require function bodies. Every extracted header is then
individually AST-validated. Comments/strings are never declaration tokens.
Only direct methods of the displayed owning class are included.
"""
import ast
import io
import tokenize
from collections import Counter


def signature_ranges(source, owner):
    if len(source) > 262144:
        return []
    try:
        tokens = []
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            tokens.append(token)
            if len(tokens) > 100000:
                return []
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    lines = source.split('\n')
    starts = [0]
    for line in lines[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    def offset(pos):
        return starts[pos[0]-1] + pos[1]
    declarations = []
    consumed = -1
    for i, token in enumerate(tokens):
        if i <= consumed or token.type != tokenize.NAME or token.string not in ('class', 'def'):
            continue
        start = token.start
        if token.string == 'def' and i and tokens[i-1].string == 'async':
            start = tokens[i-1].start
        # Declaration must begin the physical line, apart from indentation/async.
        if lines[start[0]-1][:start[1]].strip():
            continue
        depth = 0
        for j in range(i+1, len(tokens)):
            current = tokens[j]
            if current.type == tokenize.OP:
                if current.string in '([{': depth += 1
                elif current.string in ')]}': depth -= 1
                elif current.string == ':' and depth == 0:
                    lo, hi = offset(start), offset(current.end)
                    header = source[lo:hi]
                    try:
                        node = ast.parse(header + '\n    pass\n').body[0]
                    except (SyntaxError, ValueError, RecursionError):
                        break
                    if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        break
                    declarations.append((start[1], node, lo, hi))
                    consumed = j
                    break
            if current.type == tokenize.NEWLINE or depth < 0:
                break
    if not declarations or not isinstance(declarations[0][1], ast.ClassDef):
        return []
    outer = declarations[0]
    if outer[1].name != owner.rsplit(':', 1)[-1].rsplit('.', 1)[-1]:
        return []
    stack, found = [], []
    for column, node, lo, hi in declarations:
        while stack and column <= stack[-1][0]:
            stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and len(stack) == 1 and stack[0][1] is outer[1]:
            found.append({'entity_id': owner + '.' + node.name, 'offset': lo, 'end_offset': hi})
        stack.append((column, node))
    counts = Counter(item['entity_id'] for item in found)
    return [item for item in found if counts[item['entity_id']] == 1]


def mark_signatures(structure, owner, compressed):
    from util.candidate_evidence import _ACTIVE, mark_target
    capture = _ACTIVE.get()
    if capture is None or not capture.include_previews or not compressed:
        return structure
    ranges = signature_ranges(structure, owner)
    for item in reversed(ranges):
        lo, hi = item['offset'], item['end_offset']
        structure = structure[:lo] + mark_target(structure[lo:hi],
            {'entity_id': item['entity_id']}, 'visible_signature') + structure[hi:]
    return structure
