"""Independent synthetic lexical shapes, provenance and delivery tests."""
import unittest
from util.visible_signatures import signature_ranges, mark_signatures
from util.candidate_evidence import capture_evidence
from util.autonomous_reread import RereadState, MESSAGE_BYTES, MAX_VISIBLE
from util.localization_protocol import ToolPages, encoded

class VisibleSignatureTests(unittest.TestCase):
    owner='x.py:Parcel'
    def names(self, source):
        return [x['entity_id'] for x in signature_ranges(source,self.owner)]

    def test_missing_final_body_and_unindented_ellipsis(self):
        source='class Parcel:\n    def alpha(self):\n...\n    def omega(self):\n'
        self.assertEqual(self.names(source),['x.py:Parcel.alpha','x.py:Parcel.omega'])
        for span in signature_ranges(source,self.owner):
            self.assertTrue(source[span['offset']:span['end_offset']].startswith('def '))
            self.assertTrue(source[span['offset']:span['end_offset']].endswith(':'))

    def test_async_multiline_decorated_unicode_defaults_and_annotations(self):
        source='class Parcel:\n    @decorate("def forged():")\n    async def 搬运(\n        self, value: dict[str, str] = {"x:y": "class F:"},\n    ) -> tuple[str, int]:\n...\n'
        spans=signature_ranges(source,self.owner)
        self.assertEqual([x['entity_id'] for x in spans],['x.py:Parcel.搬运'])
        self.assertTrue(source[spans[0]['offset']:spans[0]['end_offset']].startswith('async def'))

    def test_comments_strings_nested_scopes_and_duplicate_methods(self):
        source='class Parcel:\n    text = "def hidden():"\n    # def forged():\n    def outer(self):\n        def nested():\n            ...\n    class Inner:\n        def inner(self):\n            ...\n    def dup(self):\n        ...\n    def dup(self):\n        ...\n    def final(self):\n'
        self.assertEqual(self.names(source),['x.py:Parcel.outer','x.py:Parcel.final'])

    def test_triple_quoted_decoy_is_not_signature(self):
        source='class Parcel:\n    text = """\n    def injected(self):\n    """\n    def real(self):\n...\n'
        self.assertEqual(self.names(source),['x.py:Parcel.real'])

    def test_wrong_owner_incomplete_signature_and_resource_cap(self):
        self.assertEqual(self.names('class Other:\n    def x(self):\n'),[])
        self.assertEqual(self.names('class Parcel:\n    def x(\n'),[])
        self.assertEqual(self.names(' '*262145),[])

    def test_indented_nested_owner_and_tab_indent(self):
        source='    class Parcel:\n        def send(self):\n...\n'
        self.assertEqual(self.names(source),['x.py:Parcel.send'])
        source='class Parcel:\n\tdef send(self):\n...\n'
        self.assertEqual(self.names(source),['x.py:Parcel.send'])

    def make_state(self, source):
        import networkx as nx
        graph=nx.MultiDiGraph()
        for span in signature_ranges(source,self.owner):graph.add_node(span['entity_id'],type='function')
        with capture_evidence(include_previews=True) as capture:
            raw=capture.unwrap(mark_signatures(source,self.owner,True))
        pages=ToolPages();oid=pages.add(raw,'search',{})
        return RereadState(graph),pages,oid,raw

    def test_cross_page_signature_needs_all_bytes_without_gap(self):
        source='class Parcel:\n    def send(\n        self, package,\n    ):\n'
        state,pages,oid,raw=self.make_state(source)
        span=raw.candidate_spans[0];cut=span['offset']+10
        pages.audit=[{'output_id':oid,'offset':0,'end_offset':cut}]
        state.observe(pages,pages.audit[-1]);self.assertFalse(state.choices)
        pages.audit.append({'output_id':oid,'offset':cut+1,'end_offset':len(raw)})
        state.observe(pages,pages.audit[-1]);self.assertFalse(state.choices)
        pages.audit.append({'output_id':oid,'offset':cut,'end_offset':cut+1})
        state.observe(pages,pages.audit[-1]);self.assertIn('x.py:Parcel.send',state.choices)
        evidence=state.choices['x.py:Parcel.send']['evidence']
        self.assertEqual(str(raw)[evidence['offset']:evidence['end_offset']], 'def send(\n        self, package,\n    ):')

    def test_visible_first_method_does_not_require_hidden_tail(self):
        source='class Parcel:\n    def first(self):\n...\n    def second(self):\n'
        state,pages,oid,raw=self.make_state(source);span=raw.candidate_spans[0]
        pages.audit=[{'output_id':oid,'offset':0,'end_offset':span['end_offset']}]
        state.observe(pages,pages.audit[-1])
        self.assertEqual(list(state.choices),['x.py:Parcel.first'])

    def test_off_capture_keeps_exact_text_no_new_candidate_metadata(self):
        source='class Parcel:\n    def first(self):\n'
        with capture_evidence() as capture:
            raw=capture.unwrap(mark_signatures(source,self.owner,True))
        self.assertEqual(str(raw),source);self.assertEqual(raw.candidate_spans,[])

    def test_pool_and_message_caps_without_relevance_ranking(self):
        source='class Parcel:\n'+''.join('    def method_%03d(self):\n...\n'%i for i in range(300))
        state,pages,oid,raw=self.make_state(source)
        pages.audit=[{'output_id':oid,'offset':0,'end_offset':len(raw)}]
        state.observe(pages,pages.audit[-1])
        self.assertEqual(len(state.choices),MAX_VISIBLE)
        self.assertEqual(next(iter(state.choices)),'x.py:Parcel.method_044')
        self.assertLessEqual(len(encoded(state.message())),MESSAGE_BYTES)
        self.assertIn('omitted_count',state.message()['content'])

    def test_nested_json_escaping_counts_whole_message(self):
        import networkx as nx
        state=RereadState(nx.MultiDiGraph())
        for char in ['\\', '"', '界', '\n']:
            node=char*480+':C.f'
            state.choices[node]={'entity_id':node,'evidence':{}}
        self.assertLessEqual(len(encoded(state.message())),MESSAGE_BYTES)

if __name__=='__main__':unittest.main()
