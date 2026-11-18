import ast
import unittest
from readonly_agent.locagent import source_entity_segments


class BomSegments(unittest.TestCase):
    def test_bom_at_first_line_keeps_spans_and_crlf_unicode(self):
        for end in ('\n', '\r\n'):
            source=f'def café():{end}    return "中\\ufeff"{end}'
            self.assertEqual(source_entity_segments('\ufeff'+source), source_entity_segments(source))
            segments=source_entity_segments('\ufeff'+source)
            self.assertEqual(list(segments), [('function','café',1,2)])
            self.assertEqual(next(iter(segments.values())),source.rstrip('\r\n'))

    def test_internal_bom_in_string_is_not_deleted(self):
        source='def f():\n    return "\ufeff"\n'
        self.assertIn('\ufeff', next(iter(source_entity_segments('\ufeff'+source).values())))

    def test_only_one_initial_signature_is_accepted(self):
        for source in ['\ufeff\ufeffdef f():\n    pass\n', '\n\ufeffdef f():\n    pass\n']:
            with self.assertRaises(SyntaxError):source_entity_segments(source)

    def test_plain_source_segment_matches_ast(self):
        source='@decorate\nclass A:\n    def __init__(self):\n        self.x = "é"\n'
        tree=ast.parse(source)
        segments=source_entity_segments(source)
        self.assertEqual(segments[('class','A',2,4)],ast.get_source_segment(source,tree.body[0]))
