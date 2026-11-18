"""Auditable comparison adapter. Only MockTransport is admitted; no key input."""
from copy import deepcopy
import json

from readonly_agent.core import encoded
from .finish_policy import validate_finish
from readonly_agent.control import CLOSING_INSTRUCTION
from readonly_agent.deepseek_wire import (
    MODEL, OUTPUT, ENDPOINT, finish_message_schema, structured_finish, strict_json,
    exchange_offline, normalize, wire_tools, WireProtocolError)

CONTRACT = {'version': 'paired-contract-paths-v2', 'requests_per_arm': 4,
            'investigation_calls_total': 16, 'source_content_utf8_bytes': 14336,
            'page_content_utf8_bytes': 4096, 'closing_control_utf8_bytes': 4096,
            'request_json_bytes': 65536, 'response_bytes': 65536,
            'output_tokens': 2048, 'ranked_items': 5,
            'accounting': 'UTF-8 of model-visible tool content, including JSON envelope; message wrappers count toward request cap',
            'finish_validation': 'safe relative predictions preserved; unknown paths and symbols are localization errors, never auto-corrected',
            'comparison': 'adapted whole systems, not pristine upstream or retrieval-only causal comparison',
            'live_enabled': False}

FINISH = {'type': 'function', 'function': {'name': 'finish',
    'description': 'Submit the final result and stop. Empty lists are valid.',
    'parameters': {'type': 'object', 'properties': {'message': finish_message_schema()},
                   'required': ['message'], 'additionalProperties': False}}}


class ContractError(WireProtocolError):
    code = 'comparison_contract_error'


def sdk_inputs(messages, tools):
    wire=[]
    for message in messages:
        if message.contains_image:raise ContractError('text_only_plan')
        wire.append(message.to_chat_dict(cache_enabled=False,vision_enabled=False,
            function_calling_enabled=True,force_string_serializer=True,send_reasoning_content=False))
    # No SDK-specific pre-serialization size gate: raw_payload gates exact bytes.
    return wire,wire_tools(tools)


def check_messages(messages):
    pending, used = set(), set()
    source = control = 0
    closed = encoded({'error': 'investigation_closed', 'next': 'finish'}).decode()
    for message in messages:
        if message['role'] not in ('system', 'user', 'assistant', 'tool'):
            raise ContractError('invalid_role')
        content = message.get('content')
        if not isinstance(content, str) and not (message['role'] == 'assistant' and content is None):
            raise ContractError('non_text_content')
        if message['role'] == 'tool':
            identifier = message.get('tool_call_id')
            if identifier not in pending:
                raise ContractError('orphan_tool_result')
            pending.remove(identifier)
            size = len(content.encode())
            if size > CONTRACT['page_content_utf8_bytes']:
                raise ContractError('page_budget_exceeded')
            if content == closed:
                control += size
            else:
                source += size
        else:
            if pending:
                raise ContractError('missing_tool_results')
            for call in message.get('tool_calls', []):
                identifier = call.get('id')
                if not isinstance(identifier, str) or not 1 <= len(identifier) <= 128 or identifier in used:
                    raise ContractError('duplicate_or_invalid_id')
                used.add(identifier); pending.add(identifier)
    if pending or not messages:
        raise ContractError('unresolved_conversation')
    if source > 14336 or control > 4096:
        raise ContractError('source_or_control_budget_exceeded')
    return source


def raw_payload(messages, tools, *, closing):
    wire = deepcopy(messages)
    from .finish_policy import PATH_INSTRUCTION
    wire[0]["content"] += "\n" + PATH_INSTRUCTION
    # Drop only transport-irrelevant native tool message names, identically to SDK payload().
    for m in wire:
        allowed = {'role', 'content', 'tool_calls'} if m['role'] == 'assistant' else (
            {'role', 'content', 'tool_call_id'} if m['role'] == 'tool' else {'role', 'content'})
        for key in list(m):
            if key not in allowed: del m[key]
    check_messages(wire)
    offered = [deepcopy(FINISH) if t['function']['name'] == 'finish' else deepcopy(t) for t in tools]
    names = [t['function']['name'] for t in offered]
    if len(set(names)) != len(names) or names.count('finish') != 1:
        raise ContractError('invalid_tool_surface')
    if closing:
        offered = [deepcopy(FINISH)]
        if not wire[-1].get('content', '').endswith(CLOSING_INSTRUCTION):
            wire.append({'role': 'user', 'content': CLOSING_INSTRUCTION})
    data = encoded({'model': MODEL, 'messages': wire, 'tools': offered,
        'temperature': 0, 'max_tokens': OUTPUT, 'thinking': {'type': 'disabled'}, 'stream': False,
        'tool_choice': {'type': 'function', 'function': {'name': 'finish'}} if closing else 'auto'})
    if len(data) > 65536: raise ContractError('request_bytes_exhausted')
    return data


def validate_response(raw, available, closing, remaining, snapshot, prior_ids=()):
    choices = raw.get('choices')
    if not isinstance(choices, list) or len(choices) != 1:
        raise ContractError('single_choice_required')
    choice = choices[0]
    if choice.get('finish_reason') == 'length': raise ContractError('output_truncated')
    if choice.get('finish_reason') != 'tool_calls': raise ContractError('missing_finish_or_tools')
    msg = choice.get('message', {})
    if msg.get('role') != 'assistant': raise ContractError('invalid_assistant')
    calls = msg.get('tool_calls')
    if not isinstance(calls, list) or not 1 <= len(calls) <= 16:
        raise ContractError('invalid_tool_batch')
    seen = set(prior_ids)
    for call in calls:
        fn = call.get('function', {}); name = fn.get('name'); identifier = call.get('id')
        if (call.get('type') != 'function' or name not in available
                or not isinstance(identifier, str) or not 1 <= len(identifier) <= 128 or identifier in seen):
            raise ContractError('invalid_tool_call')
        seen.add(identifier)
        args = strict_json(fn.get('arguments'))
        if not isinstance(args, dict): raise ContractError('object_arguments_required')
        if name == 'finish':
            if len(calls) != 1 or set(args) != {'message'}: raise ContractError('invalid_finish_wrapper')
            validate_finish(structured_finish(args['message']), snapshot)
        elif closing:
            raise ContractError('closing_tool_violation')
    count = sum(c['function']['name'] != 'finish' for c in calls)
    if count > remaining: raise ContractError('cumulative_tool_budget_exceeded')
    return count


class SharedWire:
    def __init__(self, ledger, arm, snapshot):
        if not ledger.summary()['simulation']: raise PermissionError('simulation_only')
        self.ledger, self.arm, self.snapshot = ledger, arm, snapshot
        self.token = ledger.claim(arm)
        self.calls = 0
        self.requests = []
        self.last_id = None

    def exchange(self, messages, tools, closing, transport):
        import httpx
        # Gate before reservation, credentials or any I/O; old live grants cannot enter.
        if type(transport) is not httpx.MockTransport:
            raise PermissionError('new_comparison_live_admission_not_enabled')
        if self.calls >= 16 or check_messages(messages) >= 14272: closing = True
        turn = sum(c['arm'] == self.arm for c in self.ledger.summary()['calls']) + 1
        closing = closing or turn == 4
        data = raw_payload(messages, tools, closing=closing)
        identifier = self.ledger.reserve(self.arm, self.token, data)
        self.last_id = identifier
        try:
            self.requests.append(strict_json(data))
            response = exchange_offline(data, transport)
            self.ledger.received(identifier, response)
            raw = self.ledger.settle(identifier)
            available = {t['function']['name'] for t in strict_json(data)['tools']}
            prior={c['id'] for m in messages for c in m.get('tool_calls',[])}
            self.calls += validate_response(raw, available, closing, 16-self.calls, self.snapshot,prior)
            return raw, available, closing
        except BaseException as error:
            self.ledger.halt(identifier, str(error) if isinstance(error, ContractError) else type(error).__name__)
            raise

    def generate(self, messages, tools, closing, transport):
        messages,tools=sdk_inputs(messages,tools)
        raw, available, closing = self.exchange(messages,tools,closing,transport)
        try:return normalize(raw, available, closing=closing)
        except BaseException:
            self.fail('sdk_normalization_failed');raise

    def finish(self): self.ledger.finish(self.arm, self.token)

    def fail(self, reason):
        if self.last_id is not None: self.ledger.halt(self.last_id, reason)

    def live(self, *args, **kwargs):
        raise PermissionError('new_comparison_live_admission_not_enabled')
