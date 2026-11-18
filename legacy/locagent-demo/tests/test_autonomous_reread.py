"""Synthetic controller/visibility checks; not a model quality benchmark."""
from copy import deepcopy
import unittest
import test_candidate_guidance as base
from util.localization_contract import LocalizationOptions, InvalidRequestError
from util.localizer import GraphLocalizer
from util.autonomous_reread import RereadState, MESSAGE_BYTES
from util.localization_protocol import ToolPages, encoded
from util.candidate_evidence import ToolEvidence

setUpModule = base.setUpModule
tearDownModule = base.tearDownModule

class AutonomousRereadTests(unittest.TestCase):
    setUp = base.CandidateGuidanceTests.setUp
    response = base.CandidateGuidanceTests.response
    finish = base.CandidateGuidanceTests.finish

    def setup_preview(self):
        self.owner = 'src/demo.py:Channel'
        self.method = self.owner + '.dispatch'
        code = 'class Channel:\n    def dispatch(self, item):\n' + '        # padding\n' * 110 + '        return "body-sentinel"\n'
        self.graph.add_node(self.owner, type='class', code=code, start_line=1, end_line=114)
        self.graph.add_edge('src/demo.py', self.owner, type='contains')
        self.graph.add_node(self.method, type='function', code='    def dispatch(self, item):\n        return "body-sentinel"', start_line=2, end_line=3)
        self.graph.add_edge(self.owner, self.method, type='contains')

    def run_steps(self, steps, enabled=True):
        self.sent=[]
        it=iter(steps)
        def provider(**kwargs):
            self.sent.append(deepcopy(kwargs))
            value=next(it)
            return value(kwargs) if callable(value) else value
        opts={'search_protocol':'bounded-v1','max_iterations':len(steps)}
        if enabled is not None: opts['autonomous_reread']=enabled
        return GraphLocalizer.from_graph(self.graph, provider=provider, model_name='offline', options=LocalizationOptions(**opts)).localize(self.request)

    def read_preview(self):
        return self.response('search_code_snippets', {'search_terms':['Channel']})

    def test_default_off_strict_options(self):
        self.assertFalse(LocalizationOptions().autonomous_reread)
        for v in [1, None, 'true']:
            with self.assertRaises(InvalidRequestError): LocalizationOptions(search_protocol='bounded-v1', autonomous_reread=v)
        with self.assertRaises(InvalidRequestError): LocalizationOptions(autonomous_reread=True)

    def test_disabled_matches_omitted(self):
        steps=[self.response('get_entity_contents',{'entity_names':[self.entity]}),self.finish()]
        a=self.run_steps(steps,None);sent=deepcopy(self.sent)
        b=self.run_steps(steps,False)
        self.assertEqual(a.to_dict(),b.to_dict());self.assertEqual(sent,self.sent)

    def test_real_loop_model_selected_read_reaches_final_request(self):
        self.setup_preview()
        def select(kwargs):
            # Deliberately scripted provider; selection is not live-model evidence.
            text='\n'.join(m.get('content') or '' for m in kwargs['messages'])
            self.assertIn(self.method,text)
            self.assertNotIn('body-sentinel',text)
            return self.response('reread_visible_entity', {'entity_id':self.method})
        result=self.run_steps([self.read_preview(),select,self.finish()])
        self.assertIn('body-sentinel',str(self.sent[-1]['messages']))
        self.assertEqual(result.iterations,3)
        self.assertEqual(result.diagnostics['autonomous_reread']['attempts'][0]['status'],'delivered')
        self.assertLessEqual(result.diagnostics['total_tool_message_json_bytes'],24576)
        self.assertTrue(all(e<=65536 for e in result.diagnostics['request_byte_estimates']))
        self.assertEqual([t['function']['name'] for t in self.sent[-1]['tools']],['finish'])
        self.assertNotIn('[[locagent:',str(result.to_dict()))

    def test_unknown_and_duplicate_reads_rejected(self):
        self.setup_preview()
        result=self.run_steps([self.read_preview(),self.response('reread_visible_entity',{'entity_id':'secret.py:hidden'}),self.finish()])
        self.assertEqual(result.diagnostics['termination_reason'],'invalid_tool_arguments')
        result=self.run_steps([self.read_preview(),self.response('reread_visible_entity',{'entity_id':self.method}),self.response('reread_visible_entity',{'entity_id':self.method}),self.finish()])
        self.assertEqual(result.diagnostics['termination_reason'],'invalid_tool_arguments')
        self.assertEqual(len(result.diagnostics['autonomous_reread']['attempts']),1)

    def test_only_fully_delivered_trusted_skeleton_is_eligible(self):
        self.setup_preview();state=RereadState(self.graph)
        raw='```\nclass Channel:\n    def dispatch(self, item):\n        ...\n```\n'
        span={'type':'visible_signature','payload':{'entity_id':self.method},'offset':0,'end_offset':len(raw),'repeated':False}
        pages=ToolPages();oid=pages.add(ToolEvidence(raw,[span]),'search_code_snippets',{})
        audit={'output_id':oid,'offset':0,'end_offset':len(raw)-1}
        state.observe(pages,audit);self.assertEqual(state.choices,{})
        audit['end_offset']=len(raw);state.observe(pages,audit);self.assertIn(self.method,state.choices)
        plain=ToolPages();oid=plain.add(raw,'search_code_snippets',{});state=RereadState(self.graph)
        state.observe(plain,{'output_id':oid,'offset':0,'end_offset':len(raw)});self.assertEqual(state.choices,{})

    def test_comments_cannot_forge_methods_and_checklist_is_bounded(self):
        from util.visible_signatures import signature_ranges
        self.setup_preview();state=RereadState(self.graph)
        code='class Channel:\n    # def dispatch(self, item):\n    pass\n'
        self.assertEqual(signature_ranges(code,self.owner),[])
        self.assertLessEqual(len(encoded(state.message())),MESSAGE_BYTES)

    def test_same_batch_preview_does_not_authorize_guessed_reread(self):
        self.setup_preview()
        calls=[{'id':'a','type':'function','function':{'name':'search_code_snippets','arguments':'{"search_terms":["Channel"]}'}},
               {'id':'b','type':'function','function':{'name':'reread_visible_entity','arguments':'{"entity_id":"src/demo.py:Channel.dispatch"}'}}]
        result=self.run_steps([self.response(calls=calls),self.finish()])
        self.assertEqual(result.diagnostics['termination_reason'],'invalid_tool_arguments')
        self.assertEqual(result.diagnostics['autonomous_reread']['attempts'],[])

    def test_raw_body_fallback_is_not_a_missing_body(self):
        from util.visible_signatures import mark_signatures
        from util.candidate_evidence import capture_evidence
        self.setup_preview()
        raw='class Channel:\n    def dispatch(self, item):\n        return item\n'
        with capture_evidence(include_previews=True) as capture:
            output=capture.unwrap(mark_signatures(raw,self.owner,False))
        self.assertEqual(str(output),raw)
        self.assertEqual(output.candidate_spans,[])

    def test_third_read_is_rejected_and_state_is_per_attempt(self):
        state=RereadState(self.graph)
        for node in ['one','two','three']:
            state.choices[node]={'entity_id':node,'evidence':{'output_id':'visible','offset':0,'end_offset':2}}
        state.selectable=deepcopy(state.choices)
        execute=lambda *a,**kw:'body'
        for node in ['one','two']: state.read({'entity_id':node},execute,{},False)
        with self.assertRaises(ValueError): state.read({'entity_id':'three'},execute,{},False)
        self.assertEqual(len(state.attempts),2)
        self.assertEqual(RereadState(self.graph).attempts,[])

    def test_all_continuation_pages_complete_delivery_audit(self):
        self.setup_preview()
        self.graph.nodes[self.method]['code']='    def dispatch(self, item):\n'+('        # '+ 'long body '*9+'\n')*100
        self.graph.nodes[self.method]['end_line']=2+len(self.graph.nodes[self.method]['code'].split('\n'))-1
        def continue_page(kwargs):
            import re
            content=[m['content'] for m in kwargs['messages'] if m['role']=='tool'][-1]
            match=re.search(r'output_id=(.*?); offset=.*?; next_offset=(\d+);',content)
            self.assertIsNotNone(match)
            return self.response('read_tool_output',{'output_id':match[1],'offset':int(match[2])})
        result=self.run_steps([self.read_preview(),self.response('reread_visible_entity',{'entity_id':self.method}),continue_page,self.finish()])
        self.assertEqual(result.diagnostics['autonomous_reread']['attempts'][0]['status'],'delivered')

if __name__=='__main__': unittest.main()
