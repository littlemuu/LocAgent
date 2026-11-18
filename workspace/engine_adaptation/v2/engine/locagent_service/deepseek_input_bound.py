"""Fail-closed text envelope bound for one reviewed DeepSeek API release.

This is an upper bound, NOT a tokenizer estimate. See docs/BOUNDED_INPUT_BUDGET.md
for the byte-BPE and template proof, release evidence and expiry limitation.
No tokenizer/model download, network, truncation or credential access occurs here.
"""
from datetime import datetime, timezone
import re

from locagent_service.followup import raw_json

POLICY = 'deepseek-v41-text-20261101'
REFERENCE = '314113f8a7dadb388215396ba5fbee2c610a04d6'
TEMPLATE_SHA256 = '13231c592e958fb39e2af6001dae69d90e7a36b265702b9b390236fb387599e2'
VALID_UNTIL = datetime(2026, 11, 2, tzinfo=timezone.utc)
MAX_WIRE_BYTES = 32768
MAX_INPUT_TOKENS = 131072


def utcnow():
    return datetime.now(timezone.utc)


def require_current():
    if not datetime(2026, 11, 1, tzinfo=timezone.utc) <= utcnow() < VALID_UNTIL:
        raise ValueError('Reviewed input-bound release expired; reverify provider contract')


def validate_config(config):
    if (config.get('input_bound') != POLICY
            or config['endpoint'] != 'https://api.deepseek.com/chat/completions'
            or config['model'] != 'deepseek-flash'
            or config['response_models'] != ['deepseek-flash']
            or config['disable_thinking'] is not True
            or config['context_tokens'] < 1048576
            or type(config.get('input_token_cap')) is not int
            or not 1 <= config['input_token_cap'] <= MAX_INPUT_TOKENS
            or not 1 <= config['output_tokens'] <= 1024
            or config['input_token_cap'] + config['output_tokens'] > config['context_tokens']
            or not 1024 <= config['request_bytes'] <= MAX_WIRE_BYTES
            or not 1 <= config['max_calls'] <= 3 or config['currency'] != 'CNY'):
        raise ValueError('Unsupported bounded-input provider configuration')
    from decimal import Decimal
    if (Decimal(config['input_per_million']) < 2 or Decimal(config['output_per_million']) < 8
            or not 0 < Decimal(config['budget']) <= 1):
        raise ValueError('Bounded-input policy requires peak rates and at most CNY 1')


def _object(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) <= set(required) | set(optional):
        raise ValueError('Unsupported bounded-input object shape')


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,127}', value):
        raise ValueError('Unsupported bounded-input name')


def _tree(value, depth=0):
    # Floats can grow when the provider parses/reprints tool argument JSON.
    # Images/server tools/attachments are separately forbidden by shape checks.
    if depth > 16:
        raise ValueError('Bounded-input JSON is too deep')
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if abs(value) > 2**53 - 1:
            raise ValueError('Bounded-input integer is too large')
        return
    if isinstance(value, str):
        value.encode('utf-8', errors='strict')
        if '<image' in value or '<｜deepseek_image' in value:
            raise ValueError('Image markers are outside the text-only proof')
        return
    if isinstance(value, list):
        for item in value:
            _tree(item, depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('String JSON keys required')
            _tree(key, depth + 1)
            _tree(item, depth + 1)
        return
    raise ValueError('Unsupported bounded-input JSON value')


def proof(config, data, *, allow_expired=False):
    validate_config(config)
    if not allow_expired:
        require_current()
    if not isinstance(data, bytes) or len(data) > min(config['request_bytes'], MAX_WIRE_BYTES):
        raise ValueError('Request exceeds bounded-input wire limit')
    value = raw_json(data)
    _object(value, ('model', 'messages', 'temperature', 'max_tokens', 'thinking', 'stream'),
            ('tools', 'tool_choice'))
    if (value['model'] != config['model'] or value['max_tokens'] != config['output_tokens']
            or type(value['max_tokens']) is not int or value['stream'] is not False
            or type(value['temperature']) is not int or value['temperature'] != 0
            or value['thinking'] != {'type': 'disabled'}):
        raise ValueError('Request differs from bounded-input generation contract')
    _tree(value)
    messages, tools = value['messages'], value.get('tools', [])
    if not isinstance(messages, list) or not 1 <= len(messages) <= 64:
        raise ValueError('Bounded message array required')
    if not isinstance(tools, list) or len(tools) > 32:
        raise ValueError('Bounded function tools required')
    names = set()
    for tool in tools:
        _object(tool, ('type', 'function'))
        if tool['type'] != 'function':
            raise ValueError('Server tools are outside the input/price proof')
        fn = tool['function']
        _object(fn, ('name', 'parameters'), ('description',))
        _name(fn['name'])
        if fn['name'] in names or not isinstance(fn['parameters'], dict):
            raise ValueError('Invalid function definition')
        if 'description' in fn and not isinstance(fn['description'], str):
            raise ValueError('Text description required')
        names.add(fn['name'])
    choice = value.get('tool_choice', 'auto')
    if choice != 'auto':
        _object(choice, ('type', 'function'))
        _object(choice['function'], ('name',))
        if choice['type'] != 'function' or choice['function']['name'] not in names:
            raise ValueError('Unsupported tool choice')
    calls = parameters = 0
    for message in messages:
        role = message.get('role') if isinstance(message, dict) else None
        if role in ('system', 'user'):
            _object(message, ('role', 'content'))
            if not isinstance(message['content'], str):
                raise ValueError('Text-only messages required')
        elif role == 'tool':
            _object(message, ('role', 'content', 'tool_call_id'))
            if not isinstance(message['content'], str) or not isinstance(message['tool_call_id'], str):
                raise ValueError('Text-only tool result required')
        elif role == 'assistant':
            _object(message, ('role', 'content'), ('tool_calls',))
            if message['content'] is not None and not isinstance(message['content'], str):
                raise ValueError('Text-only assistant required')
            history = message.get('tool_calls', [])
            if not isinstance(history, list) or len(history) > 32:
                raise ValueError('Bounded tool-call history required')
            for call in history:
                _object(call, ('id', 'type', 'function'), ('index',))
                if (call['type'] != 'function' or not isinstance(call['id'], str)
                        or ('index' in call and (type(call['index']) is not int or not 0 <= call['index'] < 32))):
                    raise ValueError('Unsupported function-call history')
                _object(call['function'], ('name', 'arguments'))
                _name(call['function']['name'])
                args = call['function']['arguments']
                if not isinstance(args, str):
                    raise ValueError('Original JSON argument string required')
                arguments = raw_json(args.encode())
                if not isinstance(arguments, dict) or len(arguments) > 64:
                    raise ValueError('Bounded argument object required')
                _tree(arguments)
                for key in arguments:
                    _name(key)
                calls += 1
                parameters += len(arguments)
        else:
            raise ValueError('Unsupported bounded-input role')
    if calls > 32 or parameters > 256:
        raise ValueError('Tool history exceeds proof limits')
    # 2B covers strings and default-JSON spacing (no floats/normalizer expansion).
    # 8192 covers the 983-byte tool introduction, BOS and choice scaffolding.
    # Each message/function/call/parameter wrapper is <512 bytes in the pinned
    # template. Variable-length names and values are already charged in B.
    units = len(messages) + len(tools) + calls + parameters
    bound = 2 * len(data) + 8192 + 512 * units
    if bound > config['input_token_cap']:
        raise ValueError('Expanded text envelope exceeds approved input token cap')
    return {'policy': POLICY, 'reference': REFERENCE, 'wire_bytes': len(data),
            'envelope_units': units, 'prompt_token_upper_bound': bound}
