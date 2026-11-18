"""Explicit C locator entry point. Frozen agent.run remains the B/coding entry.

Call run(issue=..., output=NEW_PATH, transport=..., locator=CurrentRetriever(...)).
Use build_packet() for the frozen version-1 localization envelope; no coding changes.
This module has no cloud CLI, credential lookup, orchestration, or automatic run.
"""
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

# Use exactly the frozen SDK initialization and types, without modifying run().
from locagent_e2e.agent import Agent, LLM, LocalConversation, Message, TextContent, SecretStr
from locagent_e2e.common import CONFIG, digest, encoded, write_json
from locagent_e2e.locator_policy import SDK_SYSTEM
from readonly_agent.core import Limits
from readonly_agent.openhands_tools import ToolSession, register_readonly_tools
from readonly_agent.control import budget_notice
from readonly_agent.deepseek_wire import payload, normalize
from experiments.sdk_finish_selfcheck_v7.finish_policy import SELF_CHECK_INSTRUCTION, validate_finish
from .policy import EvidenceLedger, INSTRUCTION, calibrate


def build_packet(result, *, instance_id, base_commit):
    """Same envelope and byte limit as frozen Checkpoint.locator()."""
    if result['status'] != 'completed':
        raise ValueError('locator_not_completed')
    packet = {'version': 1, 'instance_id': instance_id, 'base_commit': base_commit,
              'result': result['finished']}
    if len(json.dumps(packet, ensure_ascii=False).encode()) > 14336:
        raise RuntimeError('localization_packet_byte_limit')
    return packet


def run(*, issue, output, transport, locator, scripted=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    budget = CONFIG['locator']
    start = time.monotonic()
    count = 0
    failure = finished = diagnostic = None
    ledger = EvidenceLedger(locator.snapshot)

    class CalibratedSession(ToolSession):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            original_respond = self.tools.respond

            def prioritize_body(name, arguments, capacity):
                if ledger.read_priority(name, count, budget['max_requests']):
                    result = {'error': 'candidate_body_read_priority',
                              'next': 'read_file existing candidate/cursor, or finish marking 未读完'}
                    return result if len(encoded(result)) <= capacity else None
                return original_respond(name, arguments, capacity)

            # Same executor/schema, call count and byte accounting. Only the
            # locator's remaining investigation policy changes; BM25 is untouched.
            self.tools.respond = prioritize_body

        def execute(self, name, args):
            observation = super().execute(name, args)
            ledger.observe(self.audit[-1])
            return observation

    session = CalibratedSession(locator.snapshot, retriever=locator, limits=Limits(max_requests=4))
    tool_specs = register_readonly_tools(session)
    prompt = SDK_SYSTEM + '\n' + SELF_CHECK_INSTRUCTION + '\n' + INSTRUCTION
    record_start = len(transport.records)

    def generate(llm, messages, tools=None, **kwargs):
        nonlocal count, finished, diagnostic
        used = transport.records[record_start:]
        pt = sum(r['usage'].get('prompt_tokens', 0) for r in used)
        ct = sum(r['usage'].get('completion_tokens', 0) for r in used)
        if count >= budget['max_requests'] or time.monotonic() - start >= budget['timeout_seconds']:
            raise RuntimeError('agent_request_or_time_budget')
        count += 1
        closing = session.closed or count == budget['max_requests']
        active = [t for t in tools if t.name == 'finish'] if closing else list(tools)
        if closing:
            session.close_investigation()
        notice = budget_notice(turn=count, maximum=budget['max_requests'],
                               tool_calls_left=max(0, 16-session.calls),
                               source_bytes_left=max(0, 14336-session.used), closing=closing,
                               reason='request_limit' if closing else None)
        visible = list(messages) + [Message(role='user', content=[TextContent(text=notice + '\n' + ledger.notice())])]
        body = json.loads(payload(visible, active, closing=closing))
        if pt + len(encoded(body)) + 4096 > budget['input_tokens'] or ct + body['max_tokens'] > budget['output_tokens']:
            raise RuntimeError('agent_token_budget')
        raw = transport.exchange(body)
        choices = raw.get('choices', [])
        if len(choices) != 1 or choices[0].get('finish_reason') != 'tool_calls':
            raise RuntimeError('missing_tool_or_truncated_response')
        calls = choices[0]['message'].get('tool_calls', [])
        names = {t.name for t in active}
        if not calls or any(c['function']['name'] not in names for c in calls):
            raise RuntimeError('unavailable_tool')
        if any(c['function']['name'] == 'finish' for c in calls) and len(calls) != 1:
            raise RuntimeError('mixed_finish')
        response = normalize(raw, names, closing=closing)
        for call in response.message.tool_calls or []:
            if call.name == 'finish':
                packet = validate_finish(json.loads(json.loads(call.arguments)['message']), locator.snapshot)
                finished, diagnostic = calibrate(packet, ledger)
                # SDK finish event and downstream packet see the same calibrated answer.
                # Raw provider response remains intact in transport records and sidecar.
                call.arguments = json.dumps({'message': json.dumps(finished, ensure_ascii=False)}, ensure_ascii=False)
        return response

    llm = LLM(model='openai/deepseek-flash', api_key=SecretStr('transport-supplies-credential'),
              base_url='http://127.0.0.1:9', num_retries=0, max_output_tokens=budget['max_output_tokens'])
    agent = Agent(llm=llm, tools=tool_specs, include_default_tools=['FinishTool'], condenser=None,
                  agent_context=None, system_prompt=prompt)
    with TemporaryDirectory(prefix='locator-v8-sdk-') as td, patch.object(LLM, 'generate', generate), patch.object(LLM, 'resolve_runtime_metadata', return_value=None):
        workspace = Path(td)/'empty-sdk-workspace'; workspace.mkdir()
        conversation = LocalConversation(agent=agent, workspace=workspace, persistence_dir=output/'events',
                                         profile_store_dir=Path(td)/'profiles', visualizer=None,
                                         max_iteration_per_run=budget['max_requests'], stuck_detection=False,
                                         delete_on_close=False)
        try:
            conversation.send_message(issue)
            conversation.run()
            status = conversation.state.execution_status.value
        except Exception as error:
            status = 'error'
            failure = type(error).__name__ + ': ' + str(error)[:250]
        finally:
            conversation.close()
    records = transport.records[record_start:]
    result = dict(status='completed' if status == 'finished' and finished is not None and not failure else 'failed',
                  technical_failure=failure, requests=count,
                  prompt_tokens=sum(r['usage'].get('prompt_tokens', 0) for r in records),
                  completion_tokens=sum(r['usage'].get('completion_tokens', 0) for r in records),
                  cost_upper_cny=sum(r.get('charged_upper_microcny', 0) for r in records)/1e6,
                  actual_model_ids=sorted({r['actual_model'] for r in records}),
                  elapsed_seconds=time.monotonic()-start, finished=finished, source_bytes=session.used,
                  tool_calls=session.calls, tool_audit=session.audit, scripted=scripted,
                  system_prompt_sha256=digest(prompt),
                  tool_schema_sha256=digest([t.to_openai_tool() for t in agent.tools_map.values()]), budget=budget)
    write_json(output/'diagnostic-audit.json', diagnostic)
    write_json(output/'result.json', result)
    return result
