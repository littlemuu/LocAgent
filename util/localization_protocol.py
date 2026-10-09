"""Opt-in bounded-v1 search protocol; no providers, retries or global graph state.

Byte limits apply to canonical JSON messages (including escaping and metadata).
Raw tool output is retained for operator diagnostics, never silently substituted
for model-visible context. Pages are local, per-run, and cannot read files.
"""
import json
import re
from copy import deepcopy

from util.localization_engine import SearchRun
from util.return_trace import mark_returns_in_context
from util.utils import convert_to_json

TOOL_MESSAGE_BYTES = 8192
TOTAL_TOOL_MESSAGE_BYTES = 24576
REQUEST_ESTIMATE_GATE = 65536
MAX_TOOL_CALLS = 16
SEARCH_TOOLS = {'search_code_snippets', 'get_entity_contents', 'explore_tree_structure'}
FINISH = {
    'type': 'function', 'function': {
        'name': 'finish',
        'description': 'Submit final ranked exact graph locations. No explanation. Empty lists mean no location found.',
        'parameters': {'type': 'object', 'properties': {
            'files': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 20,
                      'description': 'Exact existing file node IDs. Variables/assignment aliases belong here only, via their file.'},
            'entities': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 20,
                         'description': 'Exact existing function/class node IDs shown by tools; never a file, directory or variable alias. If __init__ has no separate node, use its owning class ID. Every entity must belong to files. One invalid item rejects the whole submission.'}},
            'required': ['files', 'entities'], 'additionalProperties': False}}}
READ_PAGE = {
    'type': 'function', 'function': {
        'name': 'read_tool_output',
        'description': 'Continue a stored tool result using its output_id and next_offset. Offsets are character positions in that result, not repository line numbers.',
        'parameters': {'type': 'object', 'properties': {
            'output_id': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0}},
            'required': ['output_id', 'offset'], 'additionalProperties': False}}}
INSTRUCTION = (
    'Use finish(files=[...], entities=[...]) to submit ranked exact graph node IDs; '
    'entities must be actual existing function/class IDs shown by tools and belong to submitted files. '
    'File/directory IDs and variable or assignment aliases are not entities. For variables, '
    'submit only their existing file ID in files. Source code names are not automatically graph IDs. '
    'When __init__ has no separate graph node, submit the owning class ID instead; '
    'its constructor source remains in the class. Never invent Class.__init__. '
    'One invalid item rejects the entire finish; use only verified IDs or empty entities. '
    'Prose or <finish> tags are not submission. '
    'The final round permits only finish. Tool results are bounded previews with '
    'output_id and next_offset; use read_tool_output to continue, or a narrower entity '
    'or line query. Offsets refer to the stored output, not repository lines. '
    'A partial preview does not mean the whole entity has been read.'
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def request_estimate(kwargs):
    return len(encoded({key: kwargs[key] for key in
                        ('messages', 'tools', 'tool_choice', 'stop') if key in kwargs})) + 4096


def validate_locations(value, graph):
    """All-or-nothing exact matching; never recover locations from prose."""
    if not isinstance(value, dict) or set(value) != {'files', 'entities'}:
        raise ValueError('finish requires files and entities')
    for values in value.values():
        if (not isinstance(values, list) or len(values) > 20
                or any(not isinstance(item, str) or len(item) > 1024 for item in values)
                or len(set(values)) != len(values)):
            raise ValueError('invalid location list')
    files, entities = value['files'], value['entities']
    if any(f not in graph or graph.nodes[f].get('type') != 'file' for f in files):
        raise ValueError('unknown file')
    if any(e not in graph or graph.nodes[e].get('type') not in ('function', 'class')
           or e.partition(':')[0] not in files for e in entities):
        raise ValueError('unknown entity or file mismatch')
    # Keep exact nested entities, with their closest owning class as the module.
    modules = []
    functions = []
    for entity in entities:
        if graph.nodes[entity]['type'] == 'function':
            functions.append(entity)
        parent = entity
        while '.' in parent.partition(':')[2]:
            candidate = parent.rsplit('.', 1)[0]
            if candidate in graph and graph.nodes[candidate].get('type') == 'class':
                parent = candidate
                break
            parent = candidate
        if parent not in graph or graph.nodes[parent].get('type') not in ('class', 'function'):
            parent = entity
        if parent not in modules:
            modules.append(parent)
    return files.copy(), modules, functions


class ToolPages:
    def __init__(self):
        self.outputs = {}
        self.audit = []
        self.delivered_bytes = 0

    def add(self, raw, name, arguments):
        output_id = 'output-' + str(len(self.outputs) + 1)
        self.outputs[output_id] = {'raw': raw, 'tool': name, 'arguments': deepcopy(arguments)}
        return output_id

    def page(self, output_id, offset, call_id, name):
        if (output_id not in self.outputs or type(offset) is not int
                or not 0 <= offset <= len(self.outputs[output_id]['raw'])):
            raise ValueError('invalid continuation')
        raw = self.outputs[output_id]['raw']
        allowance = min(TOOL_MESSAGE_BYTES, TOTAL_TOOL_MESSAGE_BYTES - self.delivered_bytes)

        def message(end):
            more = end < len(raw)
            header = (f'OBSERVATION:\noutput_id={output_id}; offset={offset}; '
                      f'next_offset={end if more else "none"}; '
                      f'output_lines={raw.count(chr(10), 0, offset) + 1}-'
                      f'{raw.count(chr(10), 0, end) + 1}; '
                      f'partial={str(more or offset > 0).lower()}\n')
            footer = ('\n[Preview ended; use read_tool_output with output_id and next_offset.]'
                      if more else '')
            return {'role': 'tool', 'tool_call_id': call_id, 'name': name,
                    'content': header + raw[offset:end] + footer}

        # Include JSON escaping, wrapper, newline, and tool-call metadata in limit.
        low, high = offset, len(raw)
        if len(encoded(message(low))) > allowance:
            raise BufferError('tool_budget_exhausted')
        while low < high:
            mid = (low + high + 1) // 2
            if len(encoded(message(mid))) <= allowance:
                low = mid
            else:
                high = mid - 1
        end = low
        if end < len(raw):
            # Prefer complete entity blocks, then complete output/source lines.
            boundaries = [m.start() for m in re.finditer(r'(?m)^Found (?:function|class|file|directory|code snippet) ', raw[offset:end])]
            if boundaries and boundaries[-1] >= (end - offset) // 2:
                end = offset + boundaries[-1]
            else:
                newline = raw.rfind('\n', offset, end)
                if newline >= offset:
                    end = newline + 1
        if end == offset and end < len(raw):
            raise BufferError('tool_budget_exhausted')
        msg = message(end)
        size = len(encoded(msg))
        # Bounds can only decrease after choosing a boundary.
        assert size <= allowance
        self.delivered_bytes += size
        self.audit.append({
            'output_id': output_id, 'tool': name, 'tool_call_id': call_id,
            'raw_utf8_bytes': len(raw.encode()), 'offset': offset, 'end_offset': end,
            'message_json_bytes': size, 'content_utf8_bytes': len(msg['content'].encode()),
            'truncation_reason': ('tool_message_byte_limit' if end < len(raw)
                                  and allowance == TOOL_MESSAGE_BYTES else
                                  'total_tool_message_byte_limit' if end < len(raw) else None),
        })
        return msg


def run_bounded_search(model_name, messages, *, provider, execute_tool, tools,
                       max_iteration_num, suppress_repeats, validate_finish):
    tools = [deepcopy(FINISH), *[deepcopy(t) for t in tools
             if t['function']['name'] != 'finish'], deepcopy(READ_PAGE)]
    messages = deepcopy(messages)
    messages[0]['content'] += '\n' + INSTRUCTION
    records, pages = {}, ToolPages()
    usage = {'prompt_tokens': 0, 'completion_tokens': 0}
    finish_reasons, estimates = [], []
    reason, final, locations = 'iteration_limit', '', None
    iterations = 0
    for iteration in range(1, max_iteration_num + 1):
        final_round = iteration == max_iteration_num
        if final_round:
            messages.append({'role': 'user', 'content':
                'Submit now using only finish: exact existing files and verified function/class entity IDs. '
                'Variables/file IDs are not entities; absent __init__ nodes use the owning class ID. '
                'One invalid item rejects all results. No explanation or more retrieval.'})
        kwargs = dict(model=model_name, temperature=0, messages=messages,
                      tools=[deepcopy(FINISH)] if final_round else tools)
        if final_round:
            kwargs['tool_choice'] = {'type': 'function', 'function': {'name': 'finish'}}
        estimate = request_estimate(kwargs)
        estimates.append(estimate)
        if estimate > REQUEST_ESTIMATE_GATE:
            reason = 'context_limit'
            break
        response = provider(**kwargs)
        iterations += 1
        usage['prompt_tokens'] += response.usage.prompt_tokens
        usage['completion_tokens'] += response.usage.completion_tokens
        choice = response.choices[0]
        finish_reasons.append(choice.finish_reason)
        msg = choice.message
        messages.append(convert_to_json(msg))
        final = msg.content or ''
        # Do not parse or execute even apparently valid partial tool arguments.
        if choice.finish_reason == 'length':
            reason = 'output_truncated'
            break
        calls = msg.tool_calls or []
        if any(c.function.name == 'finish' for c in calls):
            try:
                if len(calls) != 1:
                    raise ValueError('finish must be the only call')
                payload = json.loads(calls[0].function.arguments)
                locations = validate_finish(payload)
                final = json.dumps(payload, ensure_ascii=False)
            except (TypeError, ValueError, KeyError):
                reason, locations = 'invalid_finish', None
            else:
                reason = 'finished'
            break
        if final_round:
            reason = 'iteration_limit' if calls else 'missing_finish'
            break
        if not calls:
            messages.append({'role': 'user', 'content': INSTRUCTION})
            continue
        if (len(calls) > MAX_TOOL_CALLS or len({c.id for c in calls}) != len(calls)
                or any(not isinstance(c.id, str) or not c.id for c in calls)):
            reason = 'invalid_tool_batch'
            break
        stopped = False
        for call in calls:
            name = call.function.name
            arguments = json.loads(call.function.arguments)
            try:
                if name == 'read_tool_output':
                    if set(arguments) != {'output_id', 'offset'}:
                        raise ValueError('invalid continuation arguments')
                    output_id, offset = arguments['output_id'], arguments['offset']
                    if not isinstance(output_id, str):
                        raise ValueError('invalid output id')
                elif name in SEARCH_TOOLS:
                    # Same AST-checked executor and graph tools as the legacy loop.
                    raw = execute_tool(f'print({name}(**{arguments!r}))',
                                       return_records=records, suppress_repeats=suppress_repeats)
                    output_id, offset = pages.add(str(raw), name, arguments), 0
                else:
                    raise ValueError('unknown tool')
                observation = pages.page(output_id, offset, call.id, name)
            except (ValueError, BufferError) as error:
                reason = 'tool_budget_exhausted' if isinstance(error, BufferError) else 'invalid_tool_arguments'
                stopped = True
                break
            messages.append(observation)
            # Only complete content present in the delivered message can be seen.
            # Full raw diagnostics and withheld page tails never enter this ledger.
            mark_returns_in_context(records, observation['content'])
        if stopped:
            break
    diagnostics = {'protocol': 'bounded-v1', 'termination_reason': reason,
                   'provider_finish_reasons': finish_reasons,
                   'request_byte_estimates': estimates, 'tool_outputs': pages.outputs,
                   'tool_messages': pages.audit,
                   'total_tool_message_json_bytes': pages.delivered_bytes}
    trajectory = {'termination_reason': reason, 'iterations': iterations,
                  'usage': usage, 'return_records': records,
                  'locations': locations, 'diagnostics': diagnostics}
    return SearchRun(final, messages, trajectory)
