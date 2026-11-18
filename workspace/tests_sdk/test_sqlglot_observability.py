import json
import unittest
from experiments.sqlglot_validation.observability import check_reads

class SQLGlotEvidenceTests(unittest.TestCase):
    def fixture(self,text='1: alpha\n2: beta'):
        packet=json.dumps({'text':text,'start_line':1,'end_line':2,'start_column':0,'end_column':4,'next_cursor':None})
        args=json.dumps({'path':'a.py','start_line':1,'end_line':2})
        response={'choices':[{'message':{'tool_calls':[{'id':'read1','function':{'name':'read_file','arguments':args}}]}}]}
        calls=[{'status':'settled','request':json.dumps({'messages':[]}), 'response':json.dumps(response)},
               {'status':'settled','request':json.dumps({'messages':[{'role':'tool','tool_call_id':'read1','content':packet}]}),
                'response':json.dumps({'choices':[{'message':{}}]})}]
        events=[{'event':'sdk_event','data':{'kind':'ActionEvent','tool_call_id':'read1','id':'a1'}},
                {'event':'sdk_event','data':{'kind':'ObservationEvent','tool_call_id':'read1','action_id':'a1','tool_name':'read_file',
                 'observation':{'is_error':False,'content':[{'type':'text','text':packet}]}}}]
        reference={'gold_files':['a.py'],'mapping':{'gold_mappings':[{'label':'a.py:target','strict_ast':{'start_line':1,'end_line':2}}]}}
        return calls,events,{'a.py':'alpha\nbeta\n'},reference

    def test_archived_observation_is_not_model_delivery(self):
        calls,events,sources,reference=self.fixture()
        result=check_reads(calls,events,sources,reference)
        self.assertTrue(result['full_reference_body_entered_model_context'])
        self.assertIsNone(result['paging_protocol_valid'])
        calls[1]['request']=json.dumps({'messages':[]})
        result=check_reads(calls,events,sources,reference)
        self.assertTrue(result['read_calls'][0]['tool_succeeded'])
        self.assertFalse(result['full_reference_body_entered_model_context'])
        self.assertFalse(result['read_calls'][0]['in_immediate_next_model_request'])

    def test_wrong_source_text_is_not_reference_coverage(self):
        result=check_reads(*self.fixture('1: altered\n2: beta'))
        self.assertFalse(result['read_calls'][0]['line_evidence_matches_source'])
        self.assertFalse(result['full_reference_body_entered_model_context'])

    def test_no_read_file_marks_paging_unobserved(self):
        _,_,sources,reference=self.fixture()
        result=check_reads([],[],sources,reference)
        self.assertEqual(result['read_calls'],[])
        self.assertFalse(result['paging_observed'])
        self.assertIsNone(result['paging_protocol_valid'])
        self.assertFalse(result['full_reference_body_entered_model_context'])

if __name__=='__main__':unittest.main()
