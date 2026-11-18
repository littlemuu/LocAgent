"""Shared official DeepSeek HTTP payload/client; no authority is granted here."""
from dataclasses import dataclass
import json

ENDPOINT = 'https://api.deepseek.com/chat/completions'
WIRE_MODEL = 'deepseek-v4-flash'
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


def payload(**kwargs):
    value = {k: kwargs[k] for k in ('messages','tools','tool_choice','stop') if k in kwargs}
    allowed = {
        'system': {'role','content','name'}, 'user': {'role','content','name'},
        'assistant': {'role','content','name','tool_calls'},
        'tool': {'role','content','tool_call_id'},
    }
    messages = value.get('messages', [])
    if not isinstance(messages, list):
        raise ValueError('Message array required')
    if any(not isinstance(m,dict) or m.get('role') not in allowed for m in messages):
        raise ValueError('Unsupported message shape/role')
    value['messages'] = [
        {k:v for k,v in m.items() if k in allowed[m['role']] and (v is not None or k=='content')}
        for m in messages]
    value.update(model=WIRE_MODEL, temperature=0, max_tokens=512,
                 thinking={'type':'disabled'}, stream=False)
    # Fail before reservation/HTTP on non-JSON values (including NaN/Infinity).
    json.dumps(value, allow_nan=False)
    return value


def client(transport=None):
    import httpx
    return httpx.Client(transport=transport if transport is not None else httpx.HTTPTransport(retries=0),
                        follow_redirects=False, timeout=60, trust_env=False)


@dataclass(frozen=True)
class RawHTTP:
    status: int
    body: bytes
    complete: bool = True
    error_type: str | None = None


def exchange(value, key, *, transport=None, max_response_bytes=None):
    """One request only. Preserve received bytes even for status/read failures."""
    limit=MAX_RESPONSE_BYTES if max_response_bytes is None else max_response_bytes
    if type(limit) is not int or not 0<limit<=MAX_RESPONSE_BYTES:
        raise ValueError('Positive bounded response capacity required')
    # Canonical payload contract; arbitrary endpoint/model/options cannot escape.
    if value != payload(**value):
        raise ValueError('HTTP payload differs from fixed contract')
    with client(transport) as session:
        with session.stream('POST', ENDPOINT,
                            headers={'Authorization':'Bearer '+key}, json=value) as response:
            body = bytearray()
            try:
                for chunk in response.iter_bytes():
                    if len(body)+len(chunk)>limit:
                        body.extend(chunk[:limit-len(body)])
                        return RawHTTP(response.status_code,bytes(body),False,'ResponseTooLarge')
                    body.extend(chunk)
            except Exception as exc:
                return RawHTTP(response.status_code,bytes(body),False,type(exc).__name__)
            return RawHTTP(response.status_code,bytes(body))
