import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from readonly_agent.core import Snapshot,Limits,encoded
from readonly_agent.offline import no_network

class ReadLinesSDKTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.guard=no_network(cls.root/'profiles');cls.attempts=cls.guard.__enter__()
        from readonly_agent.openhands_tools import ToolSession,register_readonly_tools,ReadAction
        from openhands.sdk.tool import resolve_tool
        cls.session_type=ToolSession;cls.register=staticmethod(register_readonly_tools);cls.resolve=staticmethod(resolve_tool);cls.action=ReadAction
    @classmethod
    def tearDownClass(cls):cls.guard.__exit__(None,None,None);cls.tmp.cleanup()
    def setUp(self):
        (self.root/'a.py').write_text('hello\n'+'中😀"\\\t'*1000+'\nlast\n')
        self.snapshot=Snapshot(self.root,['a.py'])
    def tools(self,session):return {t.name:t for spec in self.register(session) for t in self.resolve(spec,None)}
    def test_wire_schema_exposes_lines_and_string_cursor_never_offset(self):
        tool=self.tools(self.session_type(self.snapshot))['read_file'];schema=tool.to_openai_tool()['function']['parameters']
        self.assertNotIn('offset',schema['properties']);self.assertIn('start_line',schema['properties']);self.assertIn('cursor',schema['properties'])
        for args in ({'offset':5969},{'start_line':0},{'start_line':True},{'cursor':5969}):
            with self.assertRaises(ValueError):self.action(path='a.py',**args)
    def test_real_executor_reports_original_line_numbers(self):
        tool=self.tools(self.session_type(self.snapshot))['read_file']
        r=json.loads(tool(self.action(path='a.py',start_line=3,end_line=3)).text)
        self.assertEqual(r['text'],'3: last\n');self.assertEqual(r['start_line'],3)
    def test_duplicate_paging_is_stable_and_charged_each_time(self):
        s=self.session_type(self.snapshot);tool=self.tools(s)['read_file'];a=json.loads(tool(self.action(path='a.py',start_line=2)).text)
        self.assertIsNotNone(a['next_cursor']);action=self.action(path='a.py',cursor=a['next_cursor'])
        before=s.used;b=tool(action);c=tool(action)
        self.assertEqual(b.text,c.text);self.assertEqual(s.used-before,len(b.text.encode())*2)
    def test_source_budget_exhaustion_and_closure_no_further_reads(self):
        s=self.session_type(self.snapshot,limits=Limits(source_bytes=300,page_bytes=300));tool=self.tools(s)['read_file']
        r=tool(self.action(path='a.py',start_line=2));self.assertLessEqual(s.used,300);self.assertTrue(s.closed)
        before=(s.used,s.calls);again=tool(self.action(path='a.py',start_line=1));self.assertTrue(again.is_error);self.assertEqual((s.used,s.calls),before)
    def test_tiny_budget_returns_no_source_or_cursor(self):
        s=self.session_type(self.snapshot,limits=Limits(source_bytes=1));tool=self.tools(s)['read_file']
        r=tool(self.action(path='a.py'));self.assertTrue(r.is_error);self.assertEqual(s.used,0);self.assertTrue(s.closed)
        self.assertEqual(s.tools.line_reader.issued,{})
    def test_wrong_range_or_cursor_is_an_error_not_a_wrong_page(self):
        s=self.session_type(self.snapshot);tool=self.tools(s)['read_file']
        for args in ({'start_line':999},{'cursor':'not-issued'},{'start_line':3,'end_line':1}):
            r=tool(self.action(path='a.py',**args));self.assertTrue(r.is_error);self.assertNotIn('hello',r.text)
    def test_both_groups_return_identical_read_evidence(self):
        class R:
            snapshot_id=self.snapshot.identity
            def retrieve(self,q):raise AssertionError('must not force retrieval')
        a=self.tools(self.session_type(self.snapshot))['read_file'];b=self.tools(self.session_type(self.snapshot,retriever=R()))['read_file']
        self.assertEqual(a.to_openai_tool(),b.to_openai_tool())
        action=self.action(path='a.py',start_line=3,end_line=3);self.assertEqual(a(action).text,b(action).text)

if __name__=='__main__':unittest.main()
