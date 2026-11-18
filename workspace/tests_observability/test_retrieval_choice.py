from copy import deepcopy
import json
import unittest

from experiments.retrieval_choice.audit import analyze_records
from readonly_agent.live_run import pilot, run_pair
from readonly_agent.core import digest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path


class RetrievalChoiceTests(unittest.TestCase):
    def setUp(self):
        self.body=json.dumps({'text':'### Search Result:\nFound function `pkg/retry.py:schedule_retry`.\nreturn job', 'next_offset':None})
        self.args=json.dumps({'query':'retry','offset':0})
        call={'id':'r1','function':{'name':'locagent_retrieve','arguments':self.args}}
        self.calls=[{'request':{'tools':[{'function':{'name':'locagent_retrieve'}}], 'tool_choice':'auto','messages':[]},
                     'response':{'choices':[{'message':{'tool_calls':[call]}}]}},
                    {'request':{'tools':[], 'tool_choice':'auto', 'messages':[{'role':'tool','tool_call_id':'r1','content':self.body}]},
                     'response':{'choices':[]}}]
        self.events=[{'kind':'ActionEvent','id':'a1','tool_call_id':'r1','tool_name':'locagent_retrieve',
                      'tool_call':{'name':'locagent_retrieve','arguments':self.args}},
                     {'kind':'ObservationEvent','tool_call_id':'r1','tool_name':'locagent_retrieve','action_id':'a1',
                      'observation':{'is_error':False,'content':[{'type':'text','text':self.body}]}},
                     {'kind':'ActionEvent','id':'a2','tool_call_id':'f1','tool_name':'finish','action':{'kind':'FinishAction'}},
                     {'kind':'ObservationEvent','tool_call_id':'f1','tool_name':'finish','action_id':'a2','observation':{'is_error':False}}]
        self.result={'status':'completed','sdk_status':'finished','answer':{'files':['pkg/retry.py']}}

    def report(self,simulation=True):
        return analyze_records(self.calls,self.events,self.result,simulation=simulation)

    def test_scripted_chain_is_not_autonomous_evidence(self):
        report=self.report()
        self.assertTrue(report['all_invocations_verified'])
        self.assertFalse(report['live_auto_selection_observed'])
        self.assertEqual(report['invocations'][0]['selection_category'],'scripted_fixture')

    def test_live_auto_and_forced_are_separate_categories(self):
        self.assertTrue(self.report(False)['live_auto_selection_observed'])
        self.calls[0]['request']['tool_choice']={'type':'function','function':{'name':'locagent_retrieve'}}
        report=self.report(False)
        self.assertFalse(report['live_auto_selection_observed'])
        self.assertEqual(report['invocations'][0]['selection_category'],'live_forced_tool_policy')

    def test_saved_observation_alone_is_not_context_delivery(self):
        self.calls[1]['request']['messages']=[]
        self.assertFalse(self.report()['all_invocations_verified'])

    def test_wrong_call_id_or_changed_evidence_is_rejected(self):
        for field,value in [('tool_call_id','other'),('content','rewritten')]:
            original=deepcopy(self.calls)
            self.calls[1]['request']['messages'][0][field]=value
            self.assertFalse(self.report()['all_invocations_verified'])
            self.calls=original

    def test_observation_must_match_action_and_succeed(self):
        self.events[1]['action_id']='wrong'
        self.assertFalse(self.report()['all_invocations_verified'])
        self.events[1]['action_id']='a1'
        self.events[1]['observation']['is_error']=True
        self.assertFalse(self.report()['all_invocations_verified'])

    def test_no_retrieval_is_recorded_without_calling_it_success(self):
        self.calls[0]['response']['choices']=[]
        report=self.report(False)
        self.assertEqual(report['outcome'],'not_selected')
        self.assertTrue(report['normal_finish'])
        self.assertFalse(report['all_invocations_verified'])

    def test_incomplete_receipt_is_not_claimed_as_no_tool_selection(self):
        self.calls[0]['response']=None
        self.calls[0]['response_evidence_issue']='receipt_unsettled_or_incomplete'
        self.result={'status':'failed','sdk_status':'error','answer':None}
        report=self.report(False)
        self.assertEqual(report['outcome'],'incomplete_response_evidence')
        self.assertEqual(report['response_evidence_issues'],[{'request_number':1,'reason':'receipt_unsettled_or_incomplete'}])
        self.assertFalse(report['normal_finish'])
        self.assertFalse(report['all_invocations_verified'])

    def test_partial_tool_arguments_remain_unverified_evidence(self):
        self.calls[0]['response']['choices'][0]['message']['tool_calls'][0]['function']['arguments']='{"query":'
        report=self.report(False)
        self.assertEqual(report['outcome'],'incomplete_response_evidence')
        self.assertFalse(report['live_auto_selection_observed'])
        self.assertEqual(report['response_evidence_issues'][0]['reason'],'unparseable_retrieval_arguments')

    def test_normal_finish_requires_sdk_event_and_completed_result(self):
        self.events=self.events[:-1]
        self.assertFalse(self.report()['normal_finish'])

    def test_partial_page_is_reported_without_overclaiming_coverage(self):
        body=json.dumps({'text':'### Search Result:\nFound file `pkg/retry.py`.\npartial','next_offset':50})
        self.events[1]['observation']['content'][0]['text']=body
        self.calls[1]['request']['messages'][0]['content']=body
        report=self.report()
        self.assertTrue(report['invocations'][0]['pagination_remaining'])
        self.assertFalse(report['claims_retrieval_benefit'])


class CrossfileCaseTests(unittest.TestCase):
    def test_fixed_case_allowlist_excludes_scripts_and_annotations(self):
        snapshot,issue,plan=pilot('crossfile')
        self.assertEqual(len(snapshot.files),10)
        self.assertTrue(all(p.startswith('dispatch/') and p.endswith('.py') for p in snapshot.files))
        self.assertNotIn('locagent',issue.lower())
        self.assertEqual(plan['authorization'],'not_granted')
        self.assertNotEqual(plan['snapshot'],pilot('greeting')[2]['snapshot'])
        with self.assertRaises(PermissionError):
            pilot('../../arbitrary')

    def test_wrong_case_cannot_consume_grant_or_prompt_for_key(self):
        _,_,plan=pilot('crossfile')
        with TemporaryDirectory() as directory, \
             patch('readonly_agent.live_run.Authority') as authority, \
             patch('readonly_agent.live_run.getpass.getpass') as key_prompt:
            authority.return_value.read.return_value={'plan':plan}
            authority.return_value.folder.return_value=Path(directory)
            with self.assertRaises(PermissionError):
                run_pair(digest(plan),live=True,prompt_api_key=True,case_name='greeting')
            authority.return_value.claim.assert_not_called()
            key_prompt.assert_not_called()
