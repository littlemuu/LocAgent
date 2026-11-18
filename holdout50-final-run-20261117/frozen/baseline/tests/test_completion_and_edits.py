import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from locagent_e2e.agent import run
from locagent_e2e.transport import ScriptedTransport
from locagent_e2e.completion import terminal_text
from readonly_agent.offline import no_network
from test_preparation import response,LocalFixture

def text_response(text='Implemented the change and ran the focused tests.'):
 r=response('finish',{},1);r['choices'][0]={'index':0,'finish_reason':'stop','message':{'role':'assistant','content':text}};return r
class SourceFixture(LocalFixture):
 def source_state(self):return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.glob('*.py')}
 def patch(self):return 'diff --git a/x.py b/x.py\n+changed\n' if (self.root/'x.py').exists() else ''
 def execute(self,command,timeout_seconds):
  if command=='write source':(self.root/'x.py').write_text('x=1\n')
  if command=='revert source':(self.root/'x.py').unlink()
  return {'exit_code':0,'stdout':'done'}
class CompletionTests(unittest.TestCase):
 def test_sdk_plain_text_finishes_once_and_exports_patch(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);src=root/'src';src.mkdir();t=ScriptedTransport([response('edit_file',{'operation':'create','path':'x.py','content':'x=1\n'},1),text_response()])
   with no_network(root/'profiles') as attempts:r=run(issue='fixture',output=root/'out',transport=t,sandbox=SourceFixture(src),scripted=True)
   self.assertEqual(attempts,[]);self.assertEqual(r['status'],'completed');self.assertEqual(r['requests'],2);self.assertEqual(r['finish_kind'],'plain_text_stop');self.assertEqual(r['first_source_edit_request'],1);self.assertFalse(r['empty_patch']);self.assertIsNone(r['technical_failure'])
 def test_terminal_edits_record_request_not_tool_index_and_revert_still_counts(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);src=root/'src';src.mkdir();t=ScriptedTransport([response('terminal',{'command':'inspect','timeout_seconds':1},1),response('terminal',{'command':'write source','timeout_seconds':1},2),response('terminal',{'command':'revert source','timeout_seconds':1},3),text_response()])
   with no_network(root/'profiles'):r=run(issue='fixture',output=root/'out',transport=t,sandbox=SourceFixture(src),scripted=True)
   self.assertTrue(r['empty_patch']);self.assertEqual(r['first_source_edit_request'],2);self.assertEqual([e['request'] for e in r['source_edit_events']],[2,3])
 def test_read_only_text_completion_is_empty_and_never_edited(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   with no_network(root/'profiles'):r=run(issue='fixture',output=root/'out',transport=ScriptedTransport([text_response('No source changes were made.')]),sandbox=SourceFixture(root),scripted=True)
   self.assertEqual(r['status'],'completed');self.assertTrue(r['empty_patch']);self.assertIsNone(r['first_source_edit_request'])
 def test_refusal_truncation_mixed_empty_and_bad_role_not_accepted(self):
  cases=[]
  for reason in ['length','content_filter','tool_calls']:
   r=text_response();r['choices'][0]['finish_reason']=reason;cases.append(r)
  for content in ['', '   ',None,[]]:cases.append(text_response(content))
  for field,val in [('refusal','refused'),('tool_calls',[{'id':'x'}]),('function_call',{'name':'x'}),('role','user')]:
   r=text_response();r['choices'][0]['message'][field]=val;cases.append(r)
  for r in cases:self.assertIsNone(terminal_text(r))
 def test_locator_plain_text_still_rejected(self):
  from locagent_e2e.baseline import CurrentRetriever
  from readonly_agent.core import Snapshot
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'a.py').write_text('def method(): return 1\n');snap=Snapshot(root,['a.py']);snap.e2e_source_root=root
   with no_network(root/'profiles'):r=run(issue='fixture',output=root/'out',transport=ScriptedTransport([text_response()]),locator=CurrentRetriever(snap),scripted=True)
   self.assertEqual(r['status'],'failed');self.assertIsNone(r['finished']);self.assertEqual(r['tool_calls'],0)
