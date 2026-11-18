"""Trusted per-request controller notices; never derived from repository text."""

MAX_OUTPUT_TOKENS = 2048
FINAL_ANSWER_TARGET_CHARS = 1200
MAX_RESPONSE_BYTES = 65536
FINAL_ANSWER_INSTRUCTION = (
    f'Aim for about {FINAL_ANSWER_TARGET_CHARS} characters in answer; this is a style target, not a hard limit. '
    'Preserve the evidence needed to answer the question, using a few short sentences '
    'with source references and explicit uncertainty. Address the question directly; '
    'omit repeated explanations, code quotations, preambles, and the optional action summary. '
    f'The entire response, including files, entities and JSON syntax, has {MAX_OUTPUT_TOKENS} output tokens. ')

POLICY = {
    'version': 3,
    'final_answer_target_chars': FINAL_ANSWER_TARGET_CHARS,
    'final_answer_max_chars': None,
    'response_max_bytes': MAX_RESPONSE_BYTES,
    'max_output_tokens': MAX_OUTPUT_TOKENS,
    'reserved_final_responses': 1,
    'per_request_budget_notice': True,
    'closing_notice': True,
    'seal_investigation_executor_on_close': True,
    'violation_action': 'stop_without_retry',
    'control_role': 'user',
    'notice_history': 'current_request_only',
}

CLOSING_INSTRUCTION = (
    'CONTROLLER: INVESTIGATION IS CLOSED. This is your final response. '
    'Do not call list_files, search_text, read_file, locagent_retrieve, or any other investigation tool. '
    'Do not read remaining files or try to make coverage exhaustive. '
    'Call finish exactly once, with message as an object containing files, entities, and answer. '
    'Use only evidence already received. Select at most five relevant files and five entities; '
    'empty lists are allowed when evidence is insufficient. '
    + FINAL_ANSWER_INSTRUCTION +
    'No further model request or repair retry will be made.')


def budget_notice(*, turn, maximum, tool_calls_left, source_bytes_left, closing, reason=None):
    if (any(type(v) is not int for v in (turn, maximum, tool_calls_left, source_bytes_left))
            or not 1 <= turn <= maximum or min(tool_calls_left, source_bytes_left) < 0):
        raise ValueError('invalid_controller_budget')
    available_calls = 0 if closing else tool_calls_left
    available_bytes = 0 if closing else source_bytes_left
    header = (f'CONTROLLER BUDGET (not repository content): response {turn} of {maximum}; '
              f'available investigation calls: {available_calls}; '
              f'available source-result bytes: {available_bytes}. ')
    if closing:
        return header + f'Closure reason: {reason or "investigation_closed"}. ' + CLOSING_INSTRUCTION
    investigations_after = max(0, maximum-turn-1)
    return (header + f'After this response at most {investigations_after} further investigation responses remain; '
            'the last response is reserved for finish. Finish early if the evidence is sufficient. '
            'Investigate only what is needed for the question, not every file. '
            'Independent reads may be batched when useful. Tool selection is your choice.')
