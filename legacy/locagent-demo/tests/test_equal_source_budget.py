"""Offline scheduling/budget controls, not evidence of model localization gains."""
from copy import deepcopy
from itertools import product
import json
import unittest
from unittest.mock import patch

import test_candidate_drilldown as fixture
from util.localization_contract import LocalizationOptions, InvalidRequestError
from util.localizer import GraphLocalizer
from util import localization_protocol as protocol

setUpModule = fixture.setUpModule
tearDownModule = fixture.tearDownModule


class EqualSourceBudgetTests(unittest.TestCase):
    setUp = fixture.CandidateDrilldownTests.setUp
    response = fixture.CandidateDrilldownTests.response
    finish = fixture.CandidateDrilldownTests.finish
    add_function = fixture.CandidateDrilldownTests.add_function
    setup_candidates = fixture.CandidateDrilldownTests.setup_candidates

    def run_graph(self, steps, equal=True, drill=True, guidance=False, reread=False):
        self.sent = []
        values = iter(steps)
        def provider(**kw):
            self.sent.append(deepcopy(kw))
            value = next(values)
            return value(kw) if callable(value) else value
        options = dict(max_iterations=len(steps), search_protocol='bounded-v1',
                       candidate_drilldown=drill, candidate_guidance=guidance,
                       autonomous_reread=reread)
        if equal is not None:
            options['equal_source_budget'] = equal
        return GraphLocalizer.from_graph(
            self.graph, provider=provider, model_name='offline',
            options=LocalizationOptions(**options)).localize(self.request)

    def run_budget(self, *, equal, guidance=False, reread=False, drill=False,
                   maximum=5, steps=None, raw='x' * 30000):
        self.sent, self.executed = [], []
        if steps is None:
            calls = [{'id': f'c{i}', 'type': 'function', 'function': {
                'name': 'get_entity_contents', 'arguments': '{}'}} for i in range(4)]
            steps = [self.response(calls=calls), self.finish()]
        values = iter(steps)
        def provider(**kw):
            self.sent.append(deepcopy(kw))
            return next(values)
        def execute(code, **kw):
            self.executed.append(code)
            return raw
        return protocol.run_bounded_search(
            'offline', [{'role': 'system', 'content': 'offline'}],
            provider=provider, execute_tool=execute, tools=[],
            max_iteration_num=maximum, suppress_repeats=False,
            validate_finish=lambda p: protocol.validate_locations(p, self.graph),
            candidate_graph=self.graph if guidance else None,
            reread_graph=self.graph if reread or drill else None,
            candidate_drilldown=drill, equal_source_budget=equal)

    def test_strict_opt_in_and_protocol_validation(self):
        self.assertFalse(LocalizationOptions().equal_source_budget)
        for bad in (None, 1, 'true'):
            with self.assertRaises(InvalidRequestError):
                LocalizationOptions(search_protocol='bounded-v1', equal_source_budget=bad)
        with self.assertRaises(InvalidRequestError):
            LocalizationOptions(equal_source_budget=True)

    def test_explicit_false_matches_omitted_requests_and_results(self):
        steps = [self.response('search_code_snippets', {'search_terms': ['render']}), self.finish()]
        a = self.run_graph(steps, equal=None)
        sent = deepcopy(self.sent)
        b = self.run_graph(steps, equal=False)
        self.assertEqual(sent, self.sent)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertNotIn('source_budget', b.diagnostics)

    def test_all_feature_combinations_have_identical_source_space(self):
        reference = None
        for guidance, mode in product((False, True), ('off', 'reread', 'drilldown')):
            with self.subTest(guidance=guidance, mode=mode):
                run = self.run_budget(equal=True, guidance=guidance,
                                      reread=mode == 'reread', drill=mode == 'drilldown')
                d = run.trajectory['diagnostics']
                budget = d['source_budget']
                self.assertEqual(budget['source_message_allowance_bytes'], 14336)
                self.assertEqual(budget['reserved_control_bytes'], 10240)
                source = [m for m in run.messages if m['role'] == 'tool'
                          and m['content'].startswith('OBSERVATION:')]
                if reference is None:
                    reference = source
                self.assertEqual(source, reference)
                self.assertEqual(sum(len(protocol.encoded(m)) for m in source),
                                 budget['source_message_delivered_bytes'])
                self.assertLessEqual(budget['source_message_delivered_bytes'], 14336)
                self.assertLessEqual(d['total_tool_message_json_bytes'] +
                                     len(protocol.encoded(protocol.FINISH_INSTRUCTION)) + 6144, 24576)
                self.assertEqual(run.trajectory['iterations'], 2)
                self.assertEqual([t['function']['name'] for t in self.sent[-1]['tools']], ['finish'])

    def test_actual_graph_eight_flag_combinations_share_delivered_observations(self):
        self.setup_candidates()
        reference = None
        for guidance, reread, drill in product((False, True), repeat=3):
            with self.subTest(guidance=guidance, reread=reread, drill=drill):
                result = self.run_graph([
                    self.response('search_code_snippets', {'search_terms': ['dispatch']}),
                    self.response('get_entity_contents', {'entity_names': [self.first]}),
                    self.finish()], guidance=guidance, reread=reread, drill=drill)
                observations = [m for m in self.sent[-1]['messages'] if m['role'] == 'tool']
                if reference is None:
                    reference = observations
                self.assertEqual(observations, reference)
                self.assertLessEqual(result.diagnostics['source_budget']['accounted_delivery_bytes'], 24576)
                if drill:
                    self.assertIn(self.first, str(result.diagnostics['autonomous_reread']['requests']))

    def test_equal_space_counts_unicode_escaping_and_natural_finish(self):
        run = self.run_budget(equal=True, guidance=True, drill=True,
            steps=[self.response('get_entity_contents', {}), self.finish()], maximum=2,
            raw='中文 "\\\n' * 12000)
        d = run.trajectory['diagnostics']
        expected = d['total_tool_message_json_bytes'] + len(protocol.encoded(protocol.FINISH_INSTRUCTION))
        expected += max(len(protocol.encoded(r['message'])) for r in d['autonomous_reread']['requests'])
        expected += max(r['message_json_bytes'] for r in d['candidate_guidance']['requests'])
        self.assertEqual(d['source_budget']['accounted_delivery_bytes'], expected)
        self.assertLessEqual(expected, 24576)
        self.assertLessEqual(d['tool_messages'][0]['message_json_bytes'], 8192)

    def test_huge_call_metadata_cannot_force_oversized_budget_feedback(self):
        call = {'id': 'x' * 9000, 'type': 'function', 'function': {
            'name': 'get_entity_contents', 'arguments': '{}'}}
        run = self.run_budget(equal=True, steps=[self.response(calls=[call])])
        d = run.trajectory['diagnostics']
        self.assertEqual(run.trajectory['iterations'], 1)
        self.assertEqual(d['termination_reason'], 'tool_budget_exhausted')
        self.assertEqual(d['budget_exhaustion']['closing_blocked_by'], 'control_message_limit')
        self.assertLessEqual(d['source_budget']['accounted_delivery_bytes'], 24576)

    def test_old_reservations_remain_unchanged_when_disabled(self):
        delivered = []
        for enabled in (False, True):
            run = self.run_budget(equal=False, guidance=True, reread=enabled)
            delivered.append(sum(a['message_json_bytes'] for a in run.trajectory['diagnostics']['tool_messages']))
            self.assertNotIn('source_budget', run.trajectory['diagnostics'])
        self.assertEqual(delivered[0] - delivered[1], 2048)

    def test_rounds_and_space_are_independent_in_two_by_two_matrix(self):
        for equal, rounds in product((False, True), (3, 5)):
            with self.subTest(equal=equal, rounds=rounds):
                steps = [self.response('get_entity_contents', {}) for _ in range(rounds-1)] + [self.finish()]
                run = self.run_budget(equal=equal, maximum=rounds, steps=steps, raw='small body')
                self.assertEqual(run.trajectory['iterations'], rounds)
                self.assertEqual(len(self.executed), rounds-1)
                self.assertEqual(run.trajectory['termination_reason'], 'finished')
                self.assertTrue(all(x <= 65536 for x in run.trajectory['diagnostics']['request_byte_estimates']))
                if equal:
                    self.assertEqual(run.trajectory['diagnostics']['source_budget']['max_provider_calls'], rounds)

    def test_second_round_candidate_has_two_followup_turns_in_fixed_five(self):
        self.setup_candidates()
        def choose(kw):
            self.assertIn(self.first, str(kw['messages']))
            self.assertIn('reread_visible_entity', [t['function']['name'] for t in kw['tools']])
            return self.response('reread_visible_entity', {'entity_id': self.first})
        def follow(kw):
            self.assertIn('self.deliver()', str(kw['messages']))
            return self.response('search_code_snippets', {'search_terms': ['deliver']})
        steps = [self.response('search_code_snippets', {'search_terms': ['render']}),
                 self.response('search_code_snippets', {'search_terms': ['dispatch']}),
                 choose, follow, self.finish()]
        result = self.run_graph(steps)
        self.assertIn('helper-body-sentinel', str(self.sent[-1]['messages']))
        self.assertEqual(result.iterations, 5)
        self.assertEqual(result.diagnostics['autonomous_reread']['attempts'][0]['status'], 'delivered')
        self.assertEqual(result.diagnostics['source_budget']['extra_rounds'], 0)

    def test_second_round_class_signature_can_be_read_before_fixed_finish(self):
        from test_autonomous_reread import AutonomousRereadTests
        AutonomousRereadTests.setup_preview(self)
        def choose(kw):
            self.assertIn(self.method, str(kw['messages']))
            self.assertNotIn('body-sentinel', str(kw['messages']))
            return self.response('reread_visible_entity', {'entity_id': self.method})
        prefix = [self.response('search_code_snippets', {'search_terms': ['render']}),
                  self.response('search_code_snippets', {'search_terms': ['Channel']})]
        short = self.run_graph([*prefix, self.finish()], reread=True)
        self.assertEqual(short.diagnostics['autonomous_reread']['attempts'], [])
        long = self.run_graph([*prefix, choose,
                              self.response('get_entity_contents', {'entity_names': [self.entity]}),
                              self.finish()], reread=True)
        self.assertEqual(long.diagnostics['autonomous_reread']['attempts'][0]['status'], 'delivered')
        self.assertIn('body-sentinel', str(self.sent[-1]['messages']))
        self.assertEqual(long.iterations, 5)

    def test_three_rounds_cannot_act_on_second_round_candidate(self):
        self.setup_candidates()
        result = self.run_graph([
            self.response('search_code_snippets', {'search_terms': ['render']}),
            self.response('search_code_snippets', {'search_terms': ['dispatch']}), self.finish()])
        self.assertIn(self.first, str(self.sent[-1]['messages']))
        self.assertEqual([t['function']['name'] for t in self.sent[-1]['tools']], ['finish'])
        self.assertEqual(result.diagnostics['autonomous_reread']['attempts'], [])

    def test_evidence_at_last_retrieval_still_cannot_extend_hard_cap(self):
        self.setup_candidates()
        result = self.run_graph([
            *[self.response('search_code_snippets', {'search_terms': ['render']}) for _ in range(3)],
            self.response('search_code_snippets', {'search_terms': ['dispatch']}),
            self.response('reread_visible_entity', {'entity_id': self.first})])
        self.assertEqual(result.iterations, 5)
        self.assertEqual(result.diagnostics['termination_reason'], 'iteration_limit')
        self.assertEqual(result.diagnostics['autonomous_reread']['attempts'], [])

    def test_one_round_never_executes_tools(self):
        run = self.run_budget(equal=True, maximum=1,
                              steps=[self.response('get_entity_contents', {})])
        self.assertEqual(self.executed, [])
        self.assertEqual(run.trajectory['iterations'], 1)

    def test_context_gate_still_blocks_before_provider(self):
        with patch.object(protocol, 'REQUEST_ESTIMATE_GATE', 1):
            run = self.run_budget(equal=True)
        self.assertEqual(self.sent, [])
        self.assertEqual(run.trajectory['termination_reason'], 'context_limit')

    def test_early_valid_finish_is_not_forced_to_use_all_rounds(self):
        run = self.run_budget(equal=True, maximum=5, steps=[self.finish()])
        self.assertEqual(run.trajectory['iterations'], 1)
        self.assertEqual(run.trajectory['termination_reason'], 'finished')
        self.assertEqual(self.executed, [])

    def test_truncated_model_response_never_executes(self):
        run = self.run_budget(equal=True, steps=[self.response('get_entity_contents', {}, reason='length')])
        self.assertEqual(run.trajectory['termination_reason'], 'output_truncated')
        self.assertEqual(self.executed, [])


if __name__ == '__main__':
    unittest.main()
