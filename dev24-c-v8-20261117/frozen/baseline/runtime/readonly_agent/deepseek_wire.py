"""Fixed DeepSeek Chat Completions contract. No live transport or credentials."""
from dataclasses import dataclass
from copy import deepcopy
import json

from .core import encoded
from .control import CLOSING_INSTRUCTION, MAX_OUTPUT_TOKENS, MAX_RESPONSE_BYTES, FINAL_ANSWER_INSTRUCTION

ENDPOINT = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-flash'
CONTEXT = 1048576
OUTPUT = MAX_OUTPUT_TOKENS
INPUT_RATE = 2  # CNY/million, peak cache miss; also micro-CNY/input token.
OUTPUT_RATE = 8
RESERVATION = CONTEXT * INPUT_RATE + OUTPUT * OUTPUT_RATE
RESPONSE_LIMIT = MAX_RESPONSE_BYTES


class WireProtocolError(ValueError):
    code = 'model_protocol_error'


class FinishProtocolError(WireProtocolError):
    code = 'finish_message_contract_error'


class ClosingToolPolicyError(WireProtocolError):
    code = 'closing_tool_violation'


class ClosingFinishMissingError(WireProtocolError):
    code = 'closing_finish_missing'


class ToolPolicyError(WireProtocolError):
    code = 'unavailable_tool_call'


class OutputTruncatedError(WireProtocolError):
    code = 'model_output_truncated'


def finish_message_schema():
    return {'type': 'object', 'additionalProperties': False,
            'description': 'Structured final result. Supply this object directly, not prose or a JSON-encoded string.',
            'properties': {
                'files': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 5, 'uniqueItems': True},
                'entities': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 5, 'uniqueItems': True},
                'answer': {'type': 'string',
                           'description': FINAL_ANSWER_INSTRUCTION},
                'entities_note': {'type': 'null',
                                  'description': 'Optional compatibility field; omit it. Only null is accepted.'}},
            'required': ['files', 'entities', 'answer']}


def structured_finish(value):
    required = {'files', 'entities', 'answer'}
    if (not isinstance(value, dict) or not required <= set(value)
            or set(value) - required - {'entities_note'}
            or ('entities_note' in value and value['entities_note'] is not None)
            or not isinstance(value['answer'], str)):
        raise FinishProtocolError('finish_message_contract_error')
    for key in ('files', 'entities'):
        items = value[key]
        if (not isinstance(items, list) or len(items) > 5
                or any(not isinstance(item, str) for item in items)
                or len(set(items)) != len(items)):
            raise FinishProtocolError('finish_message_contract_error')
    # No content-bearing extension is discarded. The sole permitted extension
    # is a known null marker; original wire arguments remain in the raw receipt.
    return deepcopy({key: value[key] for key in ('files', 'entities', 'answer')})


def wire_tools(tools):
    offered = deepcopy([t.to_openai_tool(add_security_risk_prediction=True) for t in tools])
    for tool in offered:
        fn = tool['function']
        if fn['name'] == 'finish':
            fn['description'] = ('Submit the final structured result and end the task. '
                'message must be an object with files (relative source paths), entities '
                '(path:QualifiedName IDs), and answer (evidence and uncertainty). '
                'Empty lists are valid. Do not submit prose as message.')
            fn['parameters']['properties']['message'] = finish_message_schema()
    return offered


def strict_json(body):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('duplicate_json_key')
            result[k] = v
        return result
    def constant(_):
        raise ValueError('nonfinite_json')
    return json.loads(body, object_pairs_hook=pairs, parse_constant=constant)


def payload(messages, tools, *, closing=False):
    wire = []
    pending, used = set(), set()
    for message in messages:
        if message.contains_image:
            raise ValueError('text_only_plan')
        item = message.to_chat_dict(cache_enabled=False, vision_enabled=False,
            function_calling_enabled=True, force_string_serializer=True, send_reasoning_content=False)
        role = item.get('role')
        if role not in ('system', 'user', 'assistant', 'tool'):
            raise ValueError('unsupported_role')
        allowed = {'role', 'content', 'tool_calls'} if role == 'assistant' else (
            {'role', 'content', 'tool_call_id'} if role == 'tool' else {'role', 'content'})
        item = {k: v for k, v in item.items() if k in allowed}
        item.setdefault('content', None if role == 'assistant' else '')
        if not isinstance(item['content'], str) and not (role == 'assistant' and item['content'] is None):
            raise ValueError('text_content_required')
        if role == 'tool':
            identifier = item.get('tool_call_id')
            if identifier not in pending:
                raise ValueError('orphan_or_duplicate_tool_result')
            pending.remove(identifier)
        else:
            if pending:
                raise ValueError('unresolved_tool_results')
            for call in item.get('tool_calls', []):
                identifier = call.get('id')
                if not isinstance(identifier, str) or not identifier or identifier in used:
                    raise ValueError('invalid_tool_call_id')
                pending.add(identifier)
                used.add(identifier)
        wire.append(item)
    if pending or not wire:
        raise ValueError('unresolved_or_empty_conversation')
    offered = wire_tools(tools)
    names = [t['function']['name'] for t in offered]
    if len(set(names)) != len(names) or not set(names) <= {
            'list_files', 'search_text', 'read_file', 'locagent_retrieve', 'finish'}:
        raise ValueError('unexpected_tool_surface')
    if closing:
        offered = [t for t in offered if t['function']['name'] == 'finish']
        if len(offered) != 1:
            raise ValueError('finish_required')
        if not (wire[-1]['role'] == 'user' and isinstance(wire[-1]['content'], str)
                and wire[-1]['content'].endswith(CLOSING_INSTRUCTION)):
            wire.append({'role': 'user', 'content': CLOSING_INSTRUCTION})
    value = {'model': MODEL, 'messages': wire, 'tools': offered, 'temperature': 0,
             'max_tokens': OUTPUT, 'thinking': {'type': 'disabled'}, 'stream': False,
             'tool_choice': {'type': 'function', 'function': {'name': 'finish'}} if closing else 'auto'}
    data = encoded(value)
    if len(data) > 65536:
        raise ValueError('request_bytes_exhausted')
    return data


def usage(body):
    """Validate original integers before SDK normalization; all-miss upper cost."""
    raw = strict_json(body)
    counters = raw['usage']
    pt, ct, total = (counters[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
    if (any(type(v) is not int for v in (pt, ct, total)) or not 0 < pt <= CONTEXT
            or not 0 <= ct <= OUTPUT or total != pt + ct or raw.get('model') != MODEL
            or not isinstance(raw.get('id'), str) or not raw['id']):
        raise ValueError('invalid_usage_or_model')
    for key in ('prompt_cache_hit_tokens', 'prompt_cache_miss_tokens'):
        if key in counters and (type(counters[key]) is not int or not 0 <= counters[key] <= pt):
            raise ValueError('invalid_cache_usage')
    if all(k in counters for k in ('prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')):
        if counters['prompt_cache_hit_tokens'] + counters['prompt_cache_miss_tokens'] != pt:
            raise ValueError('inconsistent_cache_usage')
    return raw, pt * INPUT_RATE + ct * OUTPUT_RATE


def normalize(raw, available, *, closing=False, normalization_events=None):
    # The durable raw receipt remains untouched. Only the SDK-facing copy uses
    # its native string FinishAction; the provider sees a typed JSON object.
    native = deepcopy(raw)
    choices = native.get('choices')
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError('single_choice_required')
    choice = choices[0]
    if choice.get('finish_reason') == 'length':
        raise OutputTruncatedError('model_output_truncated')
    if choice.get('finish_reason') != 'tool_calls':
        if closing:
            raise ClosingFinishMissingError('closing_finish_missing')
        raise ValueError('missing_or_truncated_finish')
    message = choice.get('message')
    if not isinstance(message, dict) or message.get('role') != 'assistant':
        raise ValueError('invalid_assistant_message')
    calls = message.get('tool_calls')
    if not isinstance(calls, list) or not 1 <= len(calls) <= 16:
        if closing:
            raise ClosingFinishMissingError('closing_finish_missing')
        raise ValueError('invalid_tool_calls')
    if closing and (len(calls) != 1 or calls[0].get('function', {}).get('name') != 'finish'):
        raise ClosingToolPolicyError('closing_tool_violation')
    seen = set()
    events = []
    for call in calls:
        identifier = call.get('id')
        fn = call.get('function', {})
        if fn.get('name') not in available:
            raise ToolPolicyError('unavailable_tool_call')
        if (call.get('type') != 'function' or not isinstance(identifier, str)
                or not 1 <= len(identifier) <= 128 or identifier in seen
                or not isinstance(fn.get('arguments'), str)):
            raise ValueError('unavailable_or_invalid_tool_call')
        args = strict_json(fn['arguments'])
        if not isinstance(args, dict):
            raise ValueError('object_arguments_required')
        if fn['name'] == 'finish':
            if (not set(args) <= {'message', 'summary'} or 'message' not in args
                    or ('summary' in args and not isinstance(args['summary'], str))):
                raise FinishProtocolError('finish_message_contract_error')
            original_message = args.get('message')
            args['message'] = encoded(structured_finish(args.get('message'))).decode()
            if 'entities_note' in original_message:
                events.append({'policy': 'finish-known-null-extension-v1', 'tool_call_id': identifier,
                               'canonicalized_null_fields': ['entities_note'], 'raw_response_preserved': True})
            fn['arguments'] = encoded(args).decode()
        seen.add(identifier)
    if any(c['function']['name'] == 'finish' for c in calls) and len(calls) != 1:
        raise ValueError('mixed_finish')
    from litellm import ModelResponse
    from openhands.sdk.llm import Message
    from openhands.sdk.llm.llm_response import LLMResponse
    from openhands.sdk.llm.utils.metrics import MetricsSnapshot
    response = ModelResponse(**native)
    result = LLMResponse(message=Message.from_llm_chat_message(response.choices[0].message),
        raw_response=ModelResponse(**raw), metrics=MetricsSnapshot(model_name=MODEL))
    if normalization_events is not None:
        normalization_events.extend(events)
    return result


@dataclass(frozen=True)
class RawHTTP:
    status: int
    body: bytes
    complete: bool = True


def exchange_offline(data, transport):
    import httpx
    if type(transport) is not httpx.MockTransport:
        raise ValueError('only_mock_transport_enabled')
    with httpx.Client(transport=transport, follow_redirects=False, trust_env=False, timeout=60) as client:
        with client.stream('POST', ENDPOINT, content=data,
                headers={'Content-Type': 'application/json', 'Authorization': 'Bearer offline-not-a-key'}) as response:
            body = bytearray()
            try:
                for part in response.iter_bytes():
                    if len(body) + len(part) > RESPONSE_LIMIT:
                        body.extend(part[:RESPONSE_LIMIT-len(body)])
                        return RawHTTP(response.status_code, bytes(body), False)
                    body.extend(part)
            except Exception:
                return RawHTTP(response.status_code, bytes(body), False)
            return RawHTTP(response.status_code, bytes(body))


def exchange_live(*args, **kwargs):
    raise PermissionError('new_plan_and_account_pricing_approval_required_live_transport_disabled')
