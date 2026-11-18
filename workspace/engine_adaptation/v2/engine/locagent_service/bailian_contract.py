"""Offline Bailian embedding contract. No credential access or HTTP transport.

This module alone does not authorize calls or implement a paid ledger.
"""
from decimal import Decimal
import hashlib
import json
import math
import re

MODEL = 'qwen3.7-text-embedding-flash'
DIMENSIONS = 1024
PATH = '/api/v1/services/embeddings/text-embedding/text-embedding'
INSTRUCTION = 'Given a code localization question, retrieve Python code that implements the described behavior.'
PREPROCESSING = 'verbatim-utf8-v1'
# Larger of the model page (131072) and synchronous API table (128000).
RESERVED_TOKENS_PER_INPUT = 131072
RATE = Decimal('0.125')  # CNY per million input tokens; no free/batch discount.
CAP = Decimal('1')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def endpoint(workspace, api_host):
    """Validate an operator-provided host against an explicit workspace.

    Syntactic validation is not evidence that the operator owns this workspace.
    No DNS, redirects, normalization or fallback endpoint is attempted here.
    """
    if not isinstance(workspace, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', workspace):
        raise ValueError('Invalid workspace identifier')
    expected = f'https://{workspace}.cn-beijing.maas.aliyuncs.com'
    if api_host != expected:
        raise ValueError('Explicit Beijing workspace API Host required')
    return expected + PATH


def request(texts, role):
    if role not in ('query', 'document'):
        raise ValueError('Invalid embedding role')
    if not isinstance(texts, (tuple, list)) or not 1 <= len(texts) <= 20:
        raise ValueError('Expected one to twenty text inputs')
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Nonempty text required')
        try:
            size = len(text.encode('utf-8'))
        except UnicodeError:
            raise ValueError('UTF-8 text required') from None
        if size > 16000:
            raise ValueError('Local input byte limit exceeded')
    parameters = {'dimension': DIMENSIONS, 'text_type': role, 'output_type': 'dense'}
    if role == 'query':
        parameters['instruct'] = INSTRUCTION
    return {'model': MODEL, 'input': {'texts': list(texts)}, 'parameters': parameters}


def cache_key(text, role, api_endpoint, chunker_identity):
    """Separate roles, instruction, endpoint, model and preprocessing identities."""
    if not isinstance(chunker_identity, str) or not chunker_identity:
        raise ValueError('Chunker identity required')
    return digest({'endpoint': api_endpoint, 'request': request([text], role),
                   'preprocessing': PREPROCESSING, 'chunker': chunker_identity})


def reservation(input_count):
    if type(input_count) is not int or input_count < 1:
        raise ValueError('Positive input count required')
    return Decimal(input_count * RESERVED_TOKENS_PER_INPUT) * RATE / 1000000


def planned_cost(document_count, question_count):
    if type(document_count) is not int or document_count < 1:
        raise ValueError('Document inputs required')
    if type(question_count) is not int or not 1 <= question_count <= 20:
        raise ValueError('Expected one to twenty questions')
    cost = reservation(document_count + question_count)
    if cost > CAP:
        raise ValueError('Full-context experiment reservation exceeds CNY 1')
    return cost


def response(body, count):
    """Compatibility API; strict audited validator, no funds are released here."""
    from locagent_service.bailian_response import validate_response
    values,tokens,_=validate_response(body,count)
    return values,tokens
