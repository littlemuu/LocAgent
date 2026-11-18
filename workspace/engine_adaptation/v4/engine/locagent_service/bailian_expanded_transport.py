"""Pinned native HTTPS wire adapter; real send requires the single approved run.

The private exchange routine is exercised only with mock connections. No env/key
discovery, proxy inheritance, redirect handling, SDK retries or header logging.
"""
import http.client
import ssl
from locagent_service import bailian_expanded_runner as runner

HOST = 'ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com'
PATH = '/api/v1/services/embeddings/text-embedding/text-embedding'
TIMEOUT_SECONDS = 20


class PinnedHTTPS:
    def __init__(self, *, approval_id=None):
        plan = runner.load_plan(runner.FROZEN, runner.ROOT)
        self._hashes = frozenset(item['body_sha256'] for item in plan)
        self._token = None
        if approval_id is not None:
            if approval_id != runner.APPROVAL_ID:
                raise runner.Halt('real_transport_not_authorized')
            from locagent_service.bailian_config import load_env_file
            try:
                values = load_env_file(runner.ROOT / '.env.bailian.local')
                if (values.get('DASHSCOPE_WORKSPACE_ID') != 'ws-8t0i3jte6m9op4ad'
                        or values.get('DASHSCOPE_API_HOST') != 'https://' + HOST
                        or not values.get('DASHSCOPE_API_KEY')):
                    raise ValueError()
                self._token = values['DASHSCOPE_API_KEY']
            except Exception:
                raise runner.Halt('existing_private_credentials_unavailable_or_mismatched') from None

    def __call__(self, endpoint, raw):
        if self._token is None:
            raise runner.Halt('real_transport_not_authorized')
        return self._exchange_for_review(endpoint, raw, self._token,
                                         connection_factory=http.client.HTTPSConnection)

    def _exchange_for_review(self, endpoint, raw, token, *, connection_factory):
        """Internal wire routine; public call pins stdlib HTTPSConnection.

        Factory substitution is only available to private offline tests.
        """
        if endpoint != runner.ENDPOINT or not isinstance(raw, bytes) or runner.sha(raw) not in self._hashes:
            raise runner.Halt('transport_request_not_frozen')
        if not isinstance(token, str) or not 1 <= len(token) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise runner.Halt('invalid_credential_format')
        conn = None
        try:
            context = ssl.create_default_context()
            # Exact host/path, TLS validation, direct connection: no env proxy.
            conn = connection_factory(HOST, port=443, timeout=TIMEOUT_SECONDS, context=context)
            conn.request('POST', PATH, body=raw, headers={
                'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                'Accept': 'application/json', 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                raise runner.Halt('unexpected_content_encoding')
            body = response.read(runner.MAX_BODY + 1)
            if len(body) > runner.MAX_BODY:
                raise runner.Halt('response_body_limit')
            # Return errors to the journal: non-200 => unknown held and stop.
            # No Location follow, retry loop, fallback or response reconstruction.
            return response.status, body
        except Exception:
            raise runner.Halt('transport_exchange_failed') from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
