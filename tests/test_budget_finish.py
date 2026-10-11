"""Offline scripted budget boundaries; these tests measure no localization quality."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_bounded_protocol as fixtures
from util import localization_protocol as protocol
from util.candidate_evidence import ToolEvidence


def setUpModule():
    fixtures.setUpModule()


def tearDownModule():
    fixtures.tearDownModule()


class BudgetFinishTests(unittest.TestCase):
    setUp = fixtures.BoundedProtocolTests.setUp
    response = fixtures.BoundedProtocolTests.response
    finish = fixtures.BoundedProtocolTests.finish

    def call(self, identity, name='get_entity_contents', **arguments):
        return {'id': identity, 'type': 'function',
                'function': {'name': name, 'arguments': json.dumps(arguments)}}

    def raw_for_size(self, size, identity, output_number=1, partial=False):
        # An actual full delivered observation of exactly this many JSON bytes.
        pages = protocol.ToolPages(24576 - size - 27 if partial else 0)
        for _ in range(output_number - 1):
            pages.add('', 'get_entity_contents', {})
        for n in range(max(1, size - 400), size):
            key = 'output-' + str(output_number)
            raw = 'x' * n + ('\n' + 'y' * 20000 if partial else '')
            pages.outputs[key] = {'raw': raw}
            pages.delivered_bytes = 0
            msg = pages.page(key, 0, identity, 'get_entity_contents')
            if len(protocol.encoded(msg)) == size:
                return raw
        self.fail('Cannot construct exact page size')

    def setup_exhaustion(self, enabled, *, skipped=True):
        allowance = protocol.TOTAL_TOOL_MESSAGE_BYTES - protocol.CLOSING_CONTROL_BYTES
        if enabled:
            allowance -= protocol.CANDIDATE_MESSAGE_BYTES
        sizes = [7500, 7500, allowance - 15000 - 27]
        calls = [self.call('read-' + str(i)) for i in range(len(sizes))]
        raws = [self.raw_for_size(size, c['id'], i + 1, partial=i == len(sizes) - 1)
                for i, (size, c) in enumerate(zip(sizes, calls))]
        failure = self.call('continuation', 'read_tool_output', output_id='output-1', offset=0)
        # Use the real page formatter and JSON serializer, including real newlines.
        # The 27-byte allowance stops page() at its first, empty-wrapper size check.
        probe = protocol.ToolPages(protocol.TOTAL_TOOL_MESSAGE_BYTES - 27)
        self.assertEqual(probe.add(raws[0], 'get_entity_contents', {}), 'output-1')
        def empty_wrapper(call_id):
            with patch.object(protocol, 'encoded', wraps=protocol.encoded) as serializer:
                with self.assertRaisesRegex(BufferError, 'tool_budget_exhausted'):
                    probe.page('output-1', 0, call_id, 'read_tool_output')
                serializer.assert_called_once()
                message = serializer.call_args.args[0]
            return protocol.encoded(message)
        failure['id'] = 'c' * (276 - len(empty_wrapper('')))
        wrapper = empty_wrapper(failure['id'])
        self.assertEqual(len(wrapper), 276)
        content = json.loads(wrapper)['content']
        self.assertEqual(content.count(chr(10)), 3)
        self.assertNotIn(chr(92) + 'n', content)
        pending = [failure]
        if skipped:
            pending.append(self.call('must-not-execute', target='unseen'))
        return [self.response(calls=calls), self.response(calls=pending)], raws

    def run_protocol(self, steps, raws, *, enabled=False, maximum=3, provider=None):
        self.sent, self.executed = [], []
        values, outputs = iter(steps), iter(raws)
        def mock_provider(**kw):
            self.sent.append(deepcopy(kw))
            return next(values) if provider is None else provider(**kw)
        def execute(code, **kw):
            self.executed.append(code)
            return next(outputs)
        return protocol.run_bounded_search('offline', [{'role':'system','content':'offline'}],
            provider=mock_provider, execute_tool=execute, tools=[], max_iteration_num=maximum,
            suppress_repeats=False,
            validate_finish=lambda p: protocol.validate_locations(p, self.graph),
            candidate_graph=self.graph if enabled else None)

    def assert_paired(self, request):
        pending = []
        for message in request['messages']:
            if message['role'] == 'assistant':
                self.assertEqual(pending, [])
                pending = [c['id'] for c in message.get('tool_calls') or []]
            elif message['role'] == 'tool':
                self.assertEqual(message['tool_call_id'], pending.pop(0))
            else:
                self.assertEqual(pending, [])
        self.assertEqual(pending, [])

    def test_exact_27_vs_276_closes_in_existing_third_call_both_modes(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                steps, raws = self.setup_exhaustion(enabled)
                run = self.run_protocol([*steps, self.finish()], raws, enabled=enabled)
                d = run.trajectory['diagnostics']
                evidence = sum(a['message_json_bytes'] for a in d['tool_messages'])
                allowance = 24576 - 4096 - (4096 if enabled else 0)
                self.assertEqual(allowance - evidence, 27)
                self.assertEqual(run.trajectory['termination_reason'], 'finished')
                self.assertEqual(run.trajectory['iterations'], 3)
                self.assertEqual(len(self.executed), len(raws))
                self.assertEqual(len(d['budget_exhaustion']['tool_feedback']), 2)
                self.assert_paired(self.sent[-1])
                self.assertEqual([t['function']['name'] for t in self.sent[-1]['tools']], ['finish'])
                self.assertEqual(self.sent[-1]['tool_choice']['function']['name'], 'finish')
                self.assertEqual(d['request_byte_estimates'],
                                 [protocol.request_estimate(k) for k in self.sent])
                self.assertLessEqual(d['total_tool_message_json_bytes'] + d['budget_exhaustion']['finish_instruction_json_bytes'] + (4096 if enabled else 0), 24576)
                if enabled:
                    self.assertEqual(d['candidate_guidance']['reserved_message_bytes'], 4096)
                    self.assertLessEqual(d['candidate_guidance']['combined_delivery_bytes'], 24576)

    def test_partial_batch_success_then_skipped_calls_remain_paired(self):
        steps, raws = self.setup_exhaustion(True)
        all_calls = steps[0].choices[0].message.tool_calls + steps[1].choices[0].message.tool_calls
        batch = self.response(calls=[c.model_dump() for c in all_calls])
        run = self.run_protocol([batch, self.finish()], raws, enabled=True, maximum=8)
        self.assertEqual(len(self.sent), 2)  # Early close, never uses the other six iterations.
        self.assertEqual(len(self.executed), len(raws))
        self.assert_paired(self.sent[-1])
        self.assertEqual(run.trajectory['termination_reason'], 'finished')

    def test_finish_only_response_cannot_restart_reads_or_loop(self):
        steps, raws = self.setup_exhaustion(False)
        run = self.run_protocol([*steps, self.response('get_entity_contents', {})],
                                raws, maximum=8)
        self.assertEqual(len(self.sent), 3)
        self.assertEqual(len(self.executed), len(raws))
        self.assertEqual(run.trajectory['termination_reason'], 'iteration_limit')

    def test_invalid_or_missing_finish_not_repaired(self):
        for response, expected in [
            (self.response('finish', {'files':['src/demo.py'], 'entities':['unknown']}), 'invalid_finish'),
            (self.response(text='src/demo.py:render'), 'missing_finish'),
            (self.finish(reason='length'), 'output_truncated')]:
            steps, raws = self.setup_exhaustion(True)
            run = self.run_protocol([*steps, response], raws, enabled=True)
            self.assertEqual(run.trajectory['termination_reason'], expected)
            self.assertIsNone(run.trajectory['locations'])
            self.assertEqual(len(self.sent), 3)

    def test_no_iteration_remaining_never_executes_retrieval(self):
        run = self.run_protocol([self.response('get_entity_contents', {})], [], maximum=1)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.executed, [])
        self.assertEqual(run.trajectory['termination_reason'], 'iteration_limit')

    def test_closing_request_size_gate_has_explicit_exhausted_terminal(self):
        steps, raws = self.setup_exhaustion(True)
        values = iter(steps)
        def provider(**kw):
            if len(self.sent) == 2:
                protocol.REQUEST_ESTIMATE_GATE = 1
            return next(values)
        with patch.object(protocol, 'REQUEST_ESTIMATE_GATE', 65536):
            run = self.run_protocol([], raws, enabled=True, provider=provider)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(run.trajectory['termination_reason'], 'tool_budget_exhausted')
        self.assertEqual(run.trajectory['diagnostics']['budget_exhaustion']['closing_blocked_by'], 'context_limit')
        self.assertFalse(run.trajectory['diagnostics']['candidate_guidance']['requests'][-1]['sent'])

    def test_oversized_control_metadata_stops_without_illegal_request(self):
        steps, raws = self.setup_exhaustion(False)
        steps[1].choices[0].message.tool_calls[0].id = '中' * 3000
        run = self.run_protocol(steps, raws)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(run.trajectory['termination_reason'], 'tool_budget_exhausted')
        self.assertEqual(run.trajectory['diagnostics']['budget_exhaustion']['closing_blocked_by'], 'control_message_limit')

    def test_utf8_controls_count_canonical_json_bytes(self):
        steps, raws = self.setup_exhaustion(True)
        steps[1].choices[0].message.tool_calls[0].id = '中"\\\\' * 40
        run = self.run_protocol([*steps, self.finish()], raws, enabled=True)
        d = run.trajectory['diagnostics']; control = d['budget_exhaustion']
        self.assertEqual(control['tool_feedback_json_bytes'],
                         sum(len(protocol.encoded(m)) for m in control['tool_feedback']))
        self.assertLessEqual(control['tool_feedback_json_bytes'] + control['finish_instruction_json_bytes'], 4096)
        self.assertLessEqual(d['candidate_guidance']['combined_delivery_bytes'], 24576)
        self.assert_paired(self.sent[-1])

    def test_visible_hint_only_never_promotes_unseen_tail_or_skipped_call(self):
        steps, raws = self.setup_exhaustion(True)
        hidden = 'hidden.py:secret'
        self.graph.add_node('hidden.py', type='file')
        self.graph.add_node(hidden, type='function')
        visible = {'files':['src/demo.py'], 'entities':[self.entity]}
        hidden_payload = {'files':['hidden.py'], 'entities':[hidden]}
        first = json.dumps(visible) + 'x' * 40000 + json.dumps(hidden_payload)
        span = lambda payload, start, end: dict(payload=payload, type='function',
                                                offset=start, end_offset=end, repeated=False)
        evidence = ToolEvidence(first, [
            span(visible, 0, len(json.dumps(visible))),
            span(hidden_payload, len(first) - len(json.dumps(hidden_payload)), len(first))])
        # Retain the same full first-page size; later calls consume the budget.
        raws[0] = evidence
        run = self.run_protocol([*steps, self.finish()], raws, enabled=True)
        d = run.trajectory['diagnostics']
        ids = [e['id'] for e in d['candidate_guidance']['candidates']]
        self.assertIn(self.entity, ids)
        self.assertNotIn(hidden, ids)
        self.assertIn(hidden, d['tool_outputs']['output-1']['raw'])
        self.assertNotIn(hidden, json.dumps(self.sent[-1]['messages']))
        self.assertEqual(len(self.executed), len(raws))
        self.assertEqual(run.trajectory['termination_reason'], 'finished')

    def test_provider_rejection_is_not_retried_or_replaced_with_success(self):
        steps, raws = self.setup_exhaustion(False)
        values = iter(steps)
        def deny_closing(**kw):
            if len(self.sent) == 3:
                raise RuntimeError('quota exhausted before transport')
            return next(values)
        with self.assertRaisesRegex(RuntimeError, 'quota exhausted'):
            self.run_protocol([], raws, maximum=8, provider=deny_closing)
        self.assertEqual(len(self.sent), 3)
        self.assertEqual(len(self.executed), len(raws))

    def test_sixteen_pending_tool_calls_fit_control_reservation(self):
        calls = [self.call('tool-' + str(i)) for i in range(16)]
        with patch.object(protocol.ToolPages, 'page', side_effect=BufferError):
            run = self.run_protocol([self.response(calls=calls), self.finish()], ['not delivered'])
        self.assertEqual(len(self.executed), 1)
        self.assertEqual(len(run.trajectory['diagnostics']['budget_exhaustion']['tool_feedback']), 16)
        self.assert_paired(self.sent[-1])
        self.assertEqual(run.trajectory['termination_reason'], 'finished')

    def test_cost_and_per_arm_quota_deny_closing_before_transport(self):
        # Reuse temporary synthetic cohort setup, never historical owners/approvals.
        from test_guidance_experiment import GuidanceExperimentTests
        from locagent_service import phased as p
        for limit in ('cost', 'calls'):
            with self.subTest(limit=limit):
                fixture = GuidanceExperimentTests()
                fixture.setUp()
                try:
                    provider = fixture.claim()
                    steps, raws = self.setup_exhaustion(False)
                    if limit == 'calls':
                        steps.insert(0, self.response(text='thinking'))
                    transported = []
                    def raw(ordinal, **kw):
                        transported.append(ordinal)
                        value = json.loads(steps[ordinal].model_dump_json())
                        value['model'] = 'deepseek-v4-flash'
                        tokens = 1048576 if limit == 'cost' else 1
                        completion = 512 if limit == 'cost' else 2
                        value['usage'] = dict(prompt_tokens=tokens, completion_tokens=completion,
                            total_tokens=tokens + completion, prompt_cache_hit_tokens=0,
                            prompt_cache_miss_tokens=tokens)
                        return p.canonical(value)
                    provider.raw = raw
                    with self.assertRaises(RuntimeError):
                        self.run_protocol([], raws, maximum=8, provider=provider)
                    state, _, _ = p.load_state(fixture.path)
                    expected = 2 if limit == 'cost' else 3
                    self.assertEqual(len(transported), expected)
                    self.assertEqual(len(state['calls']), expected)
                    self.assertTrue(all(c['status'] == 'settled' for c in state['calls']))
                    self.assertEqual(state['reserved_cny'], '0.000000')
                    self.assertEqual(state['plan']['limit_cny'], '5')
                    self.assertEqual(state['plan']['max_calls_per_arm'], 3)
                    if limit == 'cost':
                        self.assertEqual(state['stop_reason'], 'budget_exhausted')
                finally:
                    fixture.doCleanups()


if __name__ == '__main__':
    unittest.main()
