import unittest
from locagent_service.label_mapping import changed_functions

class InsertionAttributionTests(unittest.TestCase):
    def test_class_attribute_inserted_before_function_does_not_change_function(self):
        base = "class DraggableBase:\n    def on_motion(self):\n        return 1\n"
        post = "class DraggableBase:\n    cids = property(lambda self: 1)\n\n    def on_motion(self):\n        return 1\n"
        result = changed_functions(base, post, [], [2, 3])
        self.assertEqual(result['base_functions'], [])
        self.assertEqual(result['new_unmapped_functions'], [])

    def test_trailing_blank_insertion_uses_patched_function_body(self):
        base = "def pytest_runtest_call(item):\n    run(item)\n\n\ndef next_hook():\n    pass\n"
        post = "def pytest_runtest_call(item):\n    run(item)\n\n    if item:\n        check(item)\n\ndef next_hook():\n    pass\n"
        result = changed_functions(base, post, [], [4, 5])
        self.assertEqual(result['base_functions'], ['pytest_runtest_call'])

    def test_deleted_and_new_functions_are_not_aliased(self):
        base = "def cached_eval():\n    return 1\n\nclass MarkEvaluator:\n    def _istrue(self):\n        return 1\n"
        post = "def compiled_eval():\n    return 2\n\nclass MarkEvaluator:\n    def _istrue(self):\n        return 2\n"
        result = changed_functions(base, post, [1, 2, 6], [1, 2, 6])
        self.assertEqual(result['base_functions'], ['MarkEvaluator._istrue', 'cached_eval'])
        self.assertEqual(result['new_unmapped_functions'], ['compiled_eval'])
