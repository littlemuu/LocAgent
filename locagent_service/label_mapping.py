"""Scoring-only AST attribution; never imported by preparation or model execution."""
import ast

RULE_VERSION = 'base-deletion-post-insertion-ast-v2'


def functions(source):
    result = {}
    def visit(node, scope=()):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = scope + (child.name,)
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = min([child.lineno] + [x.lineno for x in child.decorator_list])
                    result['.'.join(name)] = (start, child.end_lineno)
                visit(child, name)
            else:
                visit(child, scope)
    visit(ast.parse(source))
    return result


def changed_functions(base, patched, removed_lines, added_lines):
    """Deletions use base AST; insertions use patched AST and exact base name.

    No nearest-function or insertion-cursor heuristic. Entirely new callables are
    disclosed separately and cannot become base-function truth.
    """
    before, after = functions(base), functions(patched)
    affected, new = set(), set()
    def owner(inventory, line):
        candidates = [(end-start, name) for name, (start, end) in inventory.items()
                      if start <= line <= end]
        return min(candidates)[1] if candidates else None
    for line in removed_lines:
        name = owner(before, line)
        if name is not None:
            affected.add(name)
    for line in added_lines:
        name = owner(after, line)
        if name in before:
            affected.add(name)
        elif name is not None:
            new.add(name)
    return {'base_functions': sorted(affected), 'new_unmapped_functions': sorted(new),
            'rule_version': RULE_VERSION}
