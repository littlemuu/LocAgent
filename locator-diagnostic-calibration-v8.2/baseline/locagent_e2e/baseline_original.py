import ast,re
NODE_TYPE_CLASS='class'
NODE_TYPE_FUNCTION='function'
class CodeAnalyzer(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.nodes = []
        self.node_name_stack = []
        self.node_type_stack = []

    def visit_ClassDef(self, node):
        class_name = node.name
        full_class_name = '.'.join(self.node_name_stack + [class_name])
        self.nodes.append({
            'name': full_class_name,
            'type': NODE_TYPE_CLASS,
            'code': self._get_source_segment(node),
            'start_line': node.lineno,
            'end_line': node.end_lineno,
        })

        self.node_name_stack.append(class_name)
        self.node_type_stack.append(NODE_TYPE_CLASS)
        self.generic_visit(node)
        self.node_name_stack.pop()
        self.node_type_stack.pop()

    def visit_FunctionDef(self, node):
        if self.node_type_stack and self.node_type_stack[-1] == NODE_TYPE_CLASS and node.name == '__init__':
            return
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_func(node)

    def _visit_func(self, node):
        function_name = node.name
        full_function_name = '.'.join(self.node_name_stack + [function_name])
        self.nodes.append({
            'name': full_function_name,
            'parent_type': self.node_type_stack[-1] if self.node_type_stack else None,
            'type': NODE_TYPE_FUNCTION,
            'code': self._get_source_segment(node),
            'start_line': node.lineno,
            'end_line': node.end_lineno,
        })

        self.node_name_stack.append(function_name)
        self.node_type_stack.append(NODE_TYPE_FUNCTION)
        self.generic_visit(node)
        self.node_name_stack.pop()
        self.node_type_stack.pop()

    def _get_source_segment(self, node):
        with open(self.filename, 'r') as file:
            source_code = file.read()
        return ast.get_source_segment(source_code, node)

def is_test_file(nid):
    # input node id (e.g., 'tests/_core.py:test') and output whether it belongs to a test file
    file_path = nid.split(':')[0]
    word_list = re.split(r" |_|\/", file_path.lower())  # split by ' ', '_', and '/'
    return any([word.startswith('test') for word in word_list])
