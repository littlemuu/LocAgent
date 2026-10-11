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
# Inside TOTAL_TOOL_MESSAGE_BYTES, alongside the unchanged guidance reservation.
# Oversized tool-call metadata can still make a legal closing request impossible.
CLOSING_CONTROL_BYTES = 4096
FINISH_INSTRUCTION = {
    'role': 'user', 'content':
    'Submit now using only finish: exact existing files and verified function/class entity IDs. '
    'Variables/file IDs are not entities; absent __init__ nodes use the owning class ID. '
    'One invalid item rejects all results. No explanation or more retrieval.'}
BUDGET_FEEDBACK = 'tool_budget_exhausted: no result delivered for this call. Retrieval stopped; finish using prior delivered evidence.'

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


CANDIDATE_LIMIT = 20
CANDIDATE_MESSAGE_BYTES = 4096
CANDIDATE_INSTRUCTION = (
    'Candidate guidance v1 (recent visible graph evidence; not a ranking or whitelist). '
    'Use exact IDs and types below: file IDs only in files, function/class IDs only in entities '
    'with their file also in files. Variables/partial aliases and guessed paths are not entities. '
    'Before finish, check every item: one invalid item rejects the whole answer; no repair is applied. '
    'Visibility verifies an ID, not its relevance or that its whole source was read. '
    'This bounded list may omit earlier or undiscovered targets. Continue retrieval while rounds '
    'remain; any exact valid graph target may be submitted even if absent here. '
    'Evidence offsets are character positions in the indicated tool output, not source lines.\n'
)


class CandidateGuidance:
    """Per-attempt cache derived only from complete hints in delivered page slices.

    Never inspect withheld raw tails, model arguments, gold labels or return_records.
    A visible hint is only a suggestion: graph validation is repeated here, and the
    original all-or-nothing finish validator remains the sole acceptance authority.
    """
    def __init__(self, graph):
        self.graph = graph
        self.entries = {}  # Insertion order; most recently observed targets last.

    def message(self):
        return {'role': 'user', 'content': CANDIDATE_INSTRUCTION + encoded({
            'candidates': list(self.entries.values()),
            'limit': CANDIDATE_LIMIT,
        }).decode()}

    @staticmethod
    def prior_evidence(payload, kind, pages):
        if pages is None:
            return None
        for delivered in reversed(pages.audit):
            for original in pages.outputs[delivered['output_id']].get('candidate_spans', []):
                if (not original.get('repeated') and original['payload'] == payload
                        and original['type'] == kind
                        and delivered['offset'] <= original['offset']
                        and original['end_offset'] <= delivered['end_offset']):
                    return {'output_id': delivered['output_id'],
                            'offset': original['offset'], 'end_offset': original['end_offset']}
        return None

    def observe(self, spans, audit, pages=None):
        for span in spans:
            if not (audit['offset'] <= span['offset']
                    and span['end_offset'] <= audit['end_offset']):
                continue
            payload, kind = span['payload'], span['type']
            try:
                validate_locations(payload, self.graph)
                files, entities = payload['files'], payload['entities']
                if len(files) != 1 or len(entities) != (0 if kind == 'file' else 1):
                    continue
                node = entities[0] if entities else files[0]
                if self.graph.nodes[node].get('type') != kind:
                    continue
            except (ValueError, TypeError, KeyError):
                continue
            evidence = {'output_id': audit['output_id'],
                        'offset': span['offset'], 'end_offset': span['end_offset']}
            if span.get('repeated'):
                evidence = self.prior_evidence(payload, kind, pages)
                if evidence is None:
                    continue  # Neither a notice nor another notice is source evidence.
            for node in [*files, *entities]:
                entry = {'id': node, 'type': self.graph.nodes[node]['type'],
                         'evidence': evidence}
                self.entries.pop(node, None)
                self.entries[node] = entry
                while (len(self.entries) > CANDIDATE_LIMIT
                       or len(encoded(self.message())) > CANDIDATE_MESSAGE_BYTES):
                    self.entries.pop(next(iter(self.entries)))


class ToolPages:
    def __init__(self, reserved_bytes=0):
        self.outputs = {}
        self.audit = []
        self.delivered_bytes = 0
        self.reserved_bytes = reserved_bytes

    def add(self, raw, name, arguments):
        output_id = 'output-' + str(len(self.outputs) + 1)
        from util.candidate_evidence import ToolEvidence
        self.outputs[output_id] = {'raw': str(raw), 'tool': name, 'arguments': deepcopy(arguments)}
        if isinstance(raw, ToolEvidence):
            self.outputs[output_id]['candidate_spans'] = deepcopy(raw.candidate_spans)
        return output_id

    def page(self, output_id, offset, call_id, name):
        if (output_id not in self.outputs or type(offset) is not int
                or not 0 <= offset <= len(self.outputs[output_id]['raw'])):
            raise ValueError('invalid continuation')
        raw = self.outputs[output_id]['raw']
        allowance = min(TOOL_MESSAGE_BYTES, TOTAL_TOOL_MESSAGE_BYTES - self.reserved_bytes - self.delivered_bytes)

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
                       max_iteration_num, suppress_repeats, validate_finish,
                       candidate_graph=None):
    tools = [deepcopy(FINISH), *[deepcopy(t) for t in tools
             if t['function']['name'] != 'finish'], deepcopy(READ_PAGE)]
    messages = deepcopy(messages)
    messages[0]['content'] += '\n' + INSTRUCTION
    guidance = CandidateGuidance(candidate_graph) if candidate_graph is not None else None
    records, pages = {}, ToolPages(
        CLOSING_CONTROL_BYTES + (CANDIDATE_MESSAGE_BYTES if guidance is not None else 0))
    closing, controls, exhaustion = False, [], None
    guidance_message, guidance_requests = None, []
    usage = {'prompt_tokens': 0, 'completion_tokens': 0}
    finish_reasons, estimates = [], []
    reason, final, locations = 'iteration_limit', '', None
    iterations = 0
    for iteration in range(1, max_iteration_num + 1):
        final_round = closing or iteration == max_iteration_num
        if guidance_message is not None:
            messages = [m for m in messages if m is not guidance_message]
        if final_round:
            messages.append(deepcopy(FINISH_INSTRUCTION))
        if guidance is not None:
            guidance_message = guidance.message()
            messages.append(guidance_message)
            guidance_requests.append({'iteration': iteration, 'message': deepcopy(guidance_message),
                                      'message_json_bytes': len(encoded(guidance_message)), 'sent': False})
        kwargs = dict(model=model_name, temperature=0, messages=messages,
                      tools=[deepcopy(FINISH)] if final_round else tools)
        if final_round:
            kwargs['tool_choice'] = {'type': 'function', 'function': {'name': 'finish'}}
        estimate = request_estimate(kwargs)
        estimates.append(estimate)
        if estimate > REQUEST_ESTIMATE_GATE:
            reason = 'tool_budget_exhausted' if closing else 'context_limit'
            if closing:
                exhaustion['closing_blocked_by'] = 'context_limit'
            break
        if guidance is not None:
            guidance_requests[-1]['sent'] = True
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
        for call_index, call in enumerate(calls):
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
                    output_id, offset = pages.add(raw, name, arguments), 0
                else:
                    raise ValueError('unknown tool')
                observation = pages.page(output_id, offset, call.id, name)
            except BufferError:
                reason = 'tool_budget_exhausted'
                exhaustion = {'iteration': iteration, 'tool_call_id': call.id,
                              'closing_blocked_by': None}
                # Pair every unanswered call; none of these messages is source evidence.
                pending = [{'role': 'tool', 'tool_call_id': c.id, 'name': c.function.name,
                            'content': BUDGET_FEEDBACK} for c in calls[call_index:]]
                sizes = [len(encoded(m)) for m in pending]
                if (any(size > TOOL_MESSAGE_BYTES for size in sizes)
                        or sum(sizes) + len(encoded(FINISH_INSTRUCTION)) > CLOSING_CONTROL_BYTES):
                    exhaustion['closing_blocked_by'] = 'control_message_limit'
                    stopped = True
                else:
                    controls = pending
                    messages.extend(controls)
                    closing = True
                break
            except ValueError:
                reason, stopped = 'invalid_tool_arguments', True
                break
            messages.append(observation)
            if guidance is not None:
                audit = pages.audit[-1]
                guidance.observe(pages.outputs[output_id].get('candidate_spans', []), audit, pages)
            # Only complete content present in the delivered message can be seen.
            # Full raw diagnostics and withheld page tails never enter this ledger.
            mark_returns_in_context(records, observation['content'])
        if stopped:
            break
    control_bytes = sum(len(encoded(m)) for m in controls)
    diagnostics = {'protocol': 'bounded-v1', 'termination_reason': reason,
                   'provider_finish_reasons': finish_reasons,
                   'request_byte_estimates': estimates, 'tool_outputs': pages.outputs,
                   'tool_messages': pages.audit,
                   'total_tool_message_json_bytes': pages.delivered_bytes + control_bytes}
    if exhaustion is not None:
        diagnostics['budget_exhaustion'] = {
            **exhaustion, 'reserved_control_bytes': CLOSING_CONTROL_BYTES,
            'tool_feedback': controls, 'tool_feedback_json_bytes': control_bytes,
            'finish_instruction_json_bytes': len(encoded(FINISH_INSTRUCTION)) if closing else 0,
        }
    if guidance is not None:
        diagnostics['candidate_guidance'] = {
            'version': 1, 'requests': guidance_requests,
            'reserved_message_bytes': CANDIDATE_MESSAGE_BYTES,
            'combined_delivery_bytes': pages.delivered_bytes + control_bytes + (
                len(encoded(FINISH_INSTRUCTION)) if closing else 0) + max(
                (r['message_json_bytes'] for r in guidance_requests), default=0),
            'candidates': list(guidance.entries.values())}
    trajectory = {'termination_reason': reason, 'iterations': iterations,
                  'usage': usage, 'return_records': records,
                  'locations': locations, 'diagnostics': diagnostics}
    return SearchRun(final, messages, trajectory)
