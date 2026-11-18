import json,unittest
from tests_sdk import test_natural_choice as base
from experiments.natural_choice.run import execute,request,selected_tools,frozen,STORE
from readonly_agent.deepseek_wire import RawHTTP
from readonly_agent.core import encoded
class ProtocolTests(base.ChoicePairTests):
 def response(self,body,key,kw,calls):
  raw=self.fake(body,key,**kw);d=json.loads(raw.body);d['choices'][0]['message']['tool_calls']=[{'id':f'm{i}','type':'function','function':{'name':name,'arguments':json.dumps(args)}} for i,(name,args) in enumerate(calls)];return RawHTTP(200,encoded(d))
 def test_availability_only_and_exact_recorded_prefix(self):
  a=json.loads(request('baseline'));b=json.loads(request('retrieval'))
  self.assertEqual(a['messages'],b['messages']);self.assertEqual(a['tools'],[t for t in b['tools'] if t['function']['name']!='locagent_retrieve'])
  b['tools']=a['tools'];self.assertEqual(a,b)
 def test_autonomous_retrieval_optional_and_summary_preserved(self):
  admission=self.admit()
  def transport(body,key,**kw):
   offered={t['function']['name'] for t in json.loads(body)['tools']};name='locagent_retrieve' if 'locagent_retrieve' in offered else 'search_text'
   return self.response(body,key,kw,[(name,{'query':'_parse_id_var','summary':'Inspect identifier parsing'})])
  r=execute(admission,'offline',transport);self.assertEqual(r['status'],'completed');self.assertEqual([x['retrieval_selected'] for x in r['rows']],[False,True]);self.assertEqual(r['rows'][1]['chosen_tools'][0]['sdk_metadata']['summary'],'Inspect identifier parsing')
 def test_unavailable_retrieval_halts_baseline(self):
  def transport(body,key,**kw):return self.response(body,key,kw,[('locagent_retrieve',{'query':'x'})])
  r=execute(self.admit(),'offline',transport);self.assertEqual(r['status'],'halted');self.assertEqual(len(r['budget']['calls']),1)
 def test_thirteen_investigation_calls_rejected(self):
  def transport(body,key,**kw):return self.response(body,key,kw,[('search_text',{'query':'x'})]*13)
  r=execute(self.admit(),'offline',transport);self.assertEqual(r['status'],'halted');self.assertEqual(len(r['budget']['calls']),1)
 def test_twelve_calls_per_response_allowed_without_execution(self):
  def transport(body,key,**kw):return self.response(body,key,kw,[('search_text',{'query':'x','summary':'s'})]*12)
  r=execute(self.admit(),'offline',transport);self.assertEqual(r['status'],'completed');self.assertFalse(r['tool_execution']);self.assertEqual(len(r['rows'][0]['chosen_tools']),12)
 def test_early_finish_allowed_without_followup(self):
  def transport(body,key,**kw):return self.response(body,key,kw,[('finish',{'message':{'files':[],'entities':[],'answer':'Uncertain'}})])
  r=execute(self.admit(),'offline',transport);self.assertEqual(r['status'],'completed');self.assertEqual(len(r['budget']['calls']),2)
if __name__=='__main__':unittest.main()
