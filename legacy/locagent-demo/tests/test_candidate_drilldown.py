"""Offline scripted reachability and recorded-delivery checks, NOT model efficacy."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import networkx as nx
import test_candidate_guidance as base
from util.autonomous_reread import RereadState, MESSAGE_BYTES
from util.candidate_drilldown import CandidateDrilldownState
from util.candidate_evidence import ToolEvidence
from util.localization_contract import LocalizationOptions, InvalidRequestError
from util.localizer import GraphLocalizer
from util.localization_protocol import ToolPages, encoded

setUpModule = base.setUpModule
tearDownModule = base.tearDownModule

class CandidateDrilldownTests(unittest.TestCase):
    setUp = base.CandidateGuidanceTests.setUp
    response = base.CandidateGuidanceTests.response
    finish = base.CandidateGuidanceTests.finish
    add_function = base.CandidateGuidanceTests.add_function

    def run_steps(self, steps, enabled=True, suppress=False):
        self.sent=[]
        values=iter(steps)
        def provider(**kwargs):
            self.sent.append(deepcopy(kwargs))
            value=next(values)
            try:
                return value(kwargs) if callable(value) else value
            except Exception:
                import traceback
                traceback.print_exc()
                raise
        options={'max_iterations':len(steps),'search_protocol':'bounded-v1','suppress_repeats':suppress}
        if enabled is not None: options['candidate_drilldown']=enabled
        return GraphLocalizer.from_graph(self.graph, provider=provider, model_name='offline',
            options=LocalizationOptions(**options)).localize(self.request)

    def test_option_strict_default_and_legacy(self):
        self.assertFalse(LocalizationOptions().candidate_drilldown)
        for value in [1,None,'true']:
            with self.assertRaises(InvalidRequestError):
                LocalizationOptions(search_protocol='bounded-v1',candidate_drilldown=value)
        with self.assertRaises(InvalidRequestError): LocalizationOptions(candidate_drilldown=True)

    def test_disabled_identical_to_omitted(self):
        steps=[self.response('search_code_snippets',{'search_terms':['render']}),self.finish()]
        a=self.run_steps(steps,None); sent=deepcopy(self.sent)
        b=self.run_steps(steps,False)
        self.assertEqual(sent,self.sent);self.assertEqual(a.to_dict(),b.to_dict())

    def setup_candidates(self):
        self.first='src/demo.py:Channel.dispatch'
        self.second='src/other.py:Other.dispatch'
        self.helper='src/demo.py:Channel.deliver'
        self.add_function(self.first,'def dispatch(self):\n    return self.deliver()')
        self.add_function(self.second,'def dispatch(self):\n    return None')
        for i in range(3): self.add_function(f'src/extra{i}.py:Extra.dispatch','def dispatch(self):\n    pass')
        self.add_function(self.helper,'def deliver(self):\n    return "helper-body-sentinel"')

    def test_scripted_candidate_body_then_call_search(self):
        self.setup_candidates()
        def choose(kwargs):
            text=str(kwargs['messages'])
            self.assertIn(self.first,text)
            self.assertNotIn('self.deliver()',text)
            self.assertNotIn('helper-body-sentinel',text)
            return self.response('reread_visible_entity',{'entity_id':self.first})
        def follow(kwargs):
            self.assertIn('self.deliver()',str(kwargs['messages']))
            return self.response('search_code_snippets',{'search_terms':['deliver']})
        result=self.run_steps([self.response('search_code_snippets',{'search_terms':['dispatch']}),choose,follow,self.finish()])
        self.assertIn('helper-body-sentinel',str(self.sent[-1]['messages']))
        self.assertEqual(result.diagnostics['autonomous_reread']['attempts'][0]['status'],'delivered')
        self.assertEqual(result.iterations,4)
        self.assertTrue(all(x<=65536 for x in result.diagnostics['request_byte_estimates']))
        self.assertLessEqual(result.diagnostics['total_tool_message_json_bytes'],24576)
        self.assertEqual([t['function']['name'] for t in self.sent[-1]['tools']],['finish'])

    def test_repeat_suppression_is_not_reported_as_body_delivery(self):
        self.setup_candidates()
        # A long already-delivered body makes the existing repeat notice shorter.
        self.graph.nodes[self.first]['code'] += '\n' + '    # already seen padding\n' * 30
        self.graph.nodes[self.first]['end_line'] = 33
        r=self.run_steps([self.response('get_entity_contents',{'entity_names':[self.first]}),
                          self.response('reread_visible_entity',{'entity_id':self.first}),self.finish()],suppress=True)
        attempt=r.diagnostics['autonomous_reread']['attempts'][0]
        self.assertEqual(attempt['returned_content'],'repeat_notice')
        self.assertEqual(attempt['status'],'repeat_notice_delivered')
        self.assertLessEqual(r.diagnostics['candidate_drilldown']['combined_delivery_bytes'],24576)

    def test_same_turn_guessed_selection_rejected(self):
        self.setup_candidates()
        calls=[{'id':'a','type':'function','function':{'name':'search_code_snippets','arguments':json.dumps({'search_terms':['dispatch']})}},
               {'id':'b','type':'function','function':{'name':'reread_visible_entity','arguments':json.dumps({'entity_id':self.first})}}]
        r=self.run_steps([self.response(calls=calls),self.finish()])
        self.assertEqual(r.diagnostics['termination_reason'],'invalid_tool_arguments')
        self.assertEqual(r.diagnostics['autonomous_reread']['attempts'],[])

    def test_provenance_partial_gap_repeat_and_types(self):
        self.setup_candidates()
        state=CandidateDrilldownState(self.graph)
        span={'type':'function','payload':{'entities':[self.first]},'offset':2,'end_offset':8,'repeated':False}
        pages=ToolPages();oid=pages.add(ToolEvidence('0123456789',[span]),'search_code_snippets',{})
        pages.audit=[{'output_id':oid,'offset':0,'end_offset':4},{'output_id':oid,'offset':5,'end_offset':9}]
        state.observe(pages,pages.audit[-1]);self.assertEqual(state.choices,{})
        pages.audit.append({'output_id':oid,'offset':4,'end_offset':5})
        state.observe(pages,pages.audit[-1]);self.assertIn(self.first,state.choices)
        for kind,repeated in [('class',False),('file',False),('function',True)]:
            pages.outputs[oid]['candidate_spans']=[{**span,'type':kind,'repeated':repeated}]
            state=CandidateDrilldownState(self.graph);state.observe(pages,pages.audit[-1]);self.assertEqual(state.choices,{})
        pages.outputs[oid]['candidate_spans']=[]
        state.observe(pages,pages.audit[-1]);self.assertEqual(state.choices,{})
        self.assertLessEqual(len(encoded(state.message())),MESSAGE_BYTES)

    def test_unknown_duplicate_and_shared_two_attempt_limit(self):
        self.setup_candidates();state=CandidateDrilldownState(self.graph)
        for node in [self.first,self.second,self.helper]:
            state.choices[node]={'entity_id':node,'evidence':{'output_id':'x','offset':0,'end_offset':1}}
        state.selectable=deepcopy(state.choices)
        execute=lambda *a,**k:'body'
        with self.assertRaises(ValueError):state.read({'entity_id':'unknown'},execute,{},False)
        state.read({'entity_id':self.first},execute,{},False)
        with self.assertRaises(ValueError):state.read({'entity_id':self.first},execute,{},False)
        state.read({'entity_id':self.second},execute,{},False)
        with self.assertRaises(ValueError):state.read({'entity_id':self.helper},execute,{},False)

    def test_recorded_7220_visibility_and_no_remaining_opportunity(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/candidate_drilldown_7220.json').read_text())
        graph=nx.DiGraph()
        for span in fixture['output']['candidate_spans']:
            for node in span['payload'].get('entities',[]):graph.add_node(node,type='function')
        pages=SimpleNamespace(outputs={'output-3':fixture['output']},audit=[fixture['audit']])
        baseline=RereadState(graph);baseline.observe(pages,fixture['audit'])
        state=CandidateDrilldownState(graph);state.observe(pages,fixture['audit'])
        node='src/_pytest/nodes.py:Node.repr_failure'
        self.assertEqual(baseline.choices,{})
        self.assertIn(node,state.choices)
        self.assertNotIn('src/_pytest/nodes.py:Collector.repr_failure',state.choices)
        self.assertEqual(fixture['historical_attempts'],[])
        self.assertEqual(fixture['final_tools'],['finish'])
        self.assertIn('No retrieval rounds remain',state.message(final=True)['content'])
        self.assertEqual(state.attempts,[])  # Visibility replay is NOT a model selection.

    def test_7220_scripted_body_reachability_is_separate_counterfactual(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/candidate_drilldown_7220.json').read_text())
        self.first='src/_pytest/nodes.py:Node.repr_failure'
        self.helper='src/_pytest/nodes.py:Node._repr_failure_py'
        for node,data in fixture['nodes'].items():
            self.add_function(node,data['code']);self.graph.nodes[node].update(data)
        self.add_function('src/other.py:Other.repr_failure','def repr_failure(self):\n    pass')
        for i in range(3): self.add_function(f'src/extra{i}.py:Extra.repr_failure','def repr_failure(self):\n    pass')
        def choose(kwargs):
            self.assertNotIn('return self._repr_failure_py',str(kwargs['messages']))
            return self.response('reread_visible_entity',{'entity_id':self.first})
        def follow(kwargs):
            self.assertIn('return self._repr_failure_py',str(kwargs['messages']))
            return self.response('get_entity_contents',{'entity_names':[self.helper]})
        r=self.run_steps([self.response('search_code_snippets',{'search_terms':['repr_failure']}),choose,follow,self.finish()])
        self.assertIn('os.getcwd()',str(self.sent[-1]['messages']))
        self.assertEqual(r.diagnostics['autonomous_reread']['attempts'][0]['status'],'delivered')
        self.assertEqual(r.iterations,4)  # Chosen synthetic budget, not old 3-round run.

if __name__=='__main__':unittest.main()
