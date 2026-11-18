"""Single fixed HTTPS exchange; receives key only on an anonymous stdin pipe.

Never invoke directly. live_transport starts this helper only after consuming a
specific durable reservation. It has no retry, redirect, proxy or fallback path.
"""
import base64
import json
import sys


def main():
    import httpx
    request = json.loads(sys.stdin.buffer.read(80000))
    if set(request) != {'body', 'key'}:
        raise ValueError('invalid_helper_input')
    body, key = request['body'].encode(), request['key']
    if not isinstance(key, str) or not 12 <= len(key) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ValueError('invalid_key_shape')
    payload = json.loads(body)
    if (len(body) > 65536 or payload.get('model') != 'deepseek-flash'
            or payload.get('max_tokens') != 2048 or payload.get('thinking') != {'type': 'disabled'}
            or payload.get('stream') is not False or payload.get('temperature') != 0
            or set(payload) != {'model','messages','tools','temperature','max_tokens','thinking','stream','tool_choice'}):
        raise ValueError('fixed_payload_required')
    result = bytearray()
    complete = True
    with httpx.Client(transport=httpx.HTTPTransport(retries=0), trust_env=False,
                      follow_redirects=False, timeout=55) as client:
        with client.stream('POST', 'https://api.deepseek.com/chat/completions', content=body,
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key}) as response:
            try:
                for chunk in response.iter_bytes():
                    if len(result) + len(chunk) > 65536:
                        result.extend(chunk[:65536-len(result)])
                        complete = False
                        break
                    result.extend(chunk)
            except Exception:
                complete = False
            status = response.status_code
    if key.encode() in result:
        raise ValueError('sensitive_response_rejected')
    output = {'status': status, 'body': base64.b64encode(result).decode(), 'complete': complete}
    sys.stdout.write(json.dumps(output))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        # No exception message/traceback: HTTP objects may include authorization.
        sys.stderr.write(type(error).__name__)
        raise SystemExit(1)
