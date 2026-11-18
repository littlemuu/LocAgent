import copy,json,sqlite3,unittest
from pathlib import Path
from tests_sdk.test_choice_pair_v2 import ChoicePairTests
from experiments.choice_pair_v2.run import selected_tools,request,execute
from readonly_agent.deepseek_wire import RawHTTP
from readonly_agent.core import encoded
OLD=Path('authority-choice-pair/64dee9be8533dd47b3543e0d17b7e20c87ed5faf57e1a5c15a197c1c3f4f18b9/run/ledger.sqlite')
def archived():
 with sqlite3.connect(f'file:{OLD}?mode=ro',uri=True) as db:return json.loads(db.execute('SELECT response FROM calls WHERE id=1').fetchone()[0])
class AdapterTests(unittest.TestCase):
 def setUp(self):self.raw=archived();self.tools=json.loads(request('baseline'))['tools']
 def one(self,name,args):
  r=copy.deepcopy(self.raw);r['choices'][0]['message']['tool_calls']=[{'id':'test1','type':'function','function':{'name':name,'arguments':json.dumps(args)}}];return r
 def test_archived_real_response_and_no_mutation(self):
  before=copy.deepcopy(self.raw);rows=selected_tools(self.raw,self.tools)
  self.assertEqual([r['name'] for r in rows],['read_file','search_text']);self.assertEqual(self.raw,before)
  for r in rows:self.assertNotIn('summary',r['arguments']);self.assertEqual(r['sdk_metadata']['summary'],r['wire_arguments']['summary'])
 def test_all_actions_with_and_without_summary(self):
  for name,args in [('read_file',{'path':'x.py','start_line':1}),('search_text',{'query':'symbol'}),('locagent_retrieve',{'query':'symbol'}),('list_files',{}),('finish',{'message':{'files':[],'entities':[],'answer':'Unknown','entities_note':None}})]:
   for meta in ({},{'summary':''},{'summary':'说明 Unicode'}):
    with self.subTest(name=name,meta=meta):
     r=selected_tools(self.one(name,args|meta),self.tools)[0];self.assertEqual(r['sdk_metadata'],meta);self.assertEqual(r['wire_arguments'],args|meta)
 def test_invalid_helpers_unknown_and_types(self):
  for args in ({'query':'x','summary':None},{'query':'x','summary':{}},{'query':'x','security_risk':'LOW'},{'query':'x','extra':None},{'query':1},{'query':'x','offset':True},{'query':'x'*257},{'summary':'missing query'}):
   with self.subTest(args=args),self.assertRaises(Exception):selected_tools(self.one('search_text',args),self.tools)
 def test_read_invalid_and_finish_invalid(self):
  for name,args in [('read_file',{'path':'x','start_line':'1'}),('read_file',{'path':'x','offset':0}),('read_file',{'path':{}}),('finish',{'message':{'files':[],'entities':[],'answer':'x','extra':'data'}}),('finish',{'message':{'files':[],'entities':[],'answer':'x'},'summary':None})]:
   with self.subTest(name=name,args=args),self.assertRaises(Exception):selected_tools(self.one(name,args),self.tools)
 def test_unadvertised_summary_rejected(self):
  t=copy.deepcopy(self.tools)
  for tool in t:tool['function']['parameters']['properties'].pop('summary',None)
  with self.assertRaises(ValueError):selected_tools(self.raw,t)
 def test_second_invalid_call_no_partial_acceptance(self):
  self.raw['choices'][0]['message']['tool_calls'][1]['function']['arguments']='{"query":"x","extra":null}'
  with self.assertRaises(Exception):selected_tools(self.raw,self.tools)
 def test_truncated_duplicate_unknown(self):
  for mode in ('truncated','duplicate','unknown'):
   r=copy.deepcopy(self.raw)
   if mode=='truncated':r['choices'][0]['finish_reason']='length'
   elif mode=='duplicate':r['choices'][0]['message']['tool_calls'][0]['function']['arguments']='{"path":"a","path":"b"}'
   else:r['choices'][0]['message']['tool_calls'][0]['function']['name']='shell'
   with self.subTest(mode=mode),self.assertRaises(Exception):selected_tools(r,self.tools)
class RealReceiptReplay(ChoicePairTests):
 def test_archived_pair_offline(self):
  a=self.admit();original=archived()
  def replay(body,key,**kw):
   kw['ledger'].start_transport(kw['reservation'],body,kw['admission']);return RawHTTP(200,encoded(original))
  r=execute(a,'offline',replay)
  self.assertEqual(r['status'],'completed');self.assertEqual(len(r['rows']),2)
  self.assertTrue(all(len(row['chosen_tools'])==2 for row in r['rows']))
  self.assertEqual(r['budget']['reserved_micro_cny'],0)
if __name__=='__main__':unittest.main()
