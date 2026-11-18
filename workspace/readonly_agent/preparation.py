"""Unapproved pilot plan and SDK→wire→durable-ledger offline integration."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from .core import Limits, digest, encoded, runtime_identity
from .deepseek_wire import (CONTEXT, ENDPOINT, INPUT_RATE, MODEL, OUTPUT,
                            OUTPUT_RATE, RESERVATION, WireProtocolError, exchange_offline, normalize, payload)
from .openhands_replay import SDK_SYSTEM
from .control import POLICY


def engine_binding(root):
    if root is None:
        return None
    root = Path(root).resolve(strict=True)
    names = set()
    for package in ('locagent_service', 'util', 'plugins', 'dependency_graph', 'repo_index'):
        for path in (root / package).rglob('*'):
            if path.suffix in ('.py', '.j2', '.scm', '.sql'):
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
                    raise ValueError('invalid_engine_source')
                names.add(path.relative_to(root).as_posix())
    names.update(n.name for n in root.glob('requirements*.txt'))
    names.add('evaluation/eval_metric.py')
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(names)}
    return {'root': str(root), 'hash': digest(hashes), 'files': hashes}


def make_plan(snapshot, issue, engine_root=None):
    lock = Path(__file__).parent.parent / 'requirements-openhands.lock'
    return {'version': 1, 'mode': 'offline_preparation', 'authorization': 'not_granted',
            'endpoint': ENDPOINT, 'model': MODEL, 'resolved_family_reference': 'DeepSeek-V4.1-Flash-1017',
            'sdk_version': '1.62.0', 'runtime_hash': runtime_identity(),
            'locagent_engine': engine_binding(engine_root),
            'dependency_lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest(),
            'snapshot': snapshot.identity, 'source_hashes': dict(snapshot.hashes),
            'hidden_python_paths': list(snapshot.hidden_python_paths),
            'issue': issue, 'issue_hash': digest(issue), 'system_hash': digest(SDK_SYSTEM),
            'arms': ['baseline', 'retrieval'], 'max_requests_per_arm': 4, 'max_requests_total': 8,
            'limits': asdict(Limits(max_requests=4)),
            'controller_policy': dict(POLICY),
            'currency': 'CNY', 'budget_micro_cny': 17000000, 'reservation_micro_cny': RESERVATION,
            'full_reservations_micro_cny': RESERVATION * 8,
            'context_tokens': CONTEXT, 'max_output_tokens': OUTPUT,
            'input_peak_cache_miss_cny_per_million': INPUT_RATE, 'output_peak_cny_per_million': OUTPUT_RATE,
            'pricing_source': 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
            'public_pricing_checked_utc_date': '2026-11-12', 'account_pricing_confirmed': False,
            'live_transport_enabled': False, 'purpose': 'one synthetic case, protocol/termination pilot; no quality claim'}


class BudgetedWire:
    """Only accepts MockTransport; no existing grant or real key is consumed."""
    def __init__(self, ledger, arm):
        if not ledger.summary()['simulation']:
            raise PermissionError('simulation_cannot_use_live_ledger')
        self.ledger, self.arm = ledger, arm
        self.token = ledger.claim(arm)

    def generate(self, messages, tools, closing, transport):
        import httpx
        if type(transport) is not httpx.MockTransport:
            raise ValueError('live_transport_not_enabled')
        data = payload(messages, tools, closing=closing)
        identifier = self.ledger.reserve(self.arm, self.token, data)
        try:
            # The durable reservation already exists before ANY transport I/O.
            response = exchange_offline(data, transport)
            self.ledger.received(identifier, response)
            raw = self.ledger.settle(identifier)
            available = {t['function']['name'] for t in json.loads(data)['tools']}
            return normalize(raw, available, closing=closing)
        except BaseException as error:
            try:
                self.ledger.halt(identifier, error.code if isinstance(error, WireProtocolError) else type(error).__name__)
            except Exception:
                pass  # Existing durable reservation still blocks another request.
            raise


class PreparationSession:
    """Synthetic raw HTTP responses exercise the same SDK protocol and ledger."""
    def __init__(self, ledger, arm):
        self.wire = BudgetedWire(ledger, arm)
        self.requests = []

    def generate(self, messages, tools, closing, native_calls):
        import httpx
        def respond(request):
            sent = json.loads(request.content)
            self.requests.append(sent)
            row = self.wire.ledger.summary()['calls'][-1]
            if row['status'] != 'reserved':
                raise AssertionError('transport_before_durable_reservation')
            calls = [c.to_chat_dict() for c in native_calls]
            for call in calls:
                fn = call['function']
                if fn['name'] == 'finish':
                    args = json.loads(fn['arguments'])
                    args['message'] = json.loads(args['message'])
                    fn['arguments'] = encoded(args).decode()
            body = {'id': f'offline-http-{row["id"]}', 'model': MODEL,
                    'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                        'role': 'assistant', 'content': None,
                        'tool_calls': calls}}],
                    'usage': {'prompt_tokens': 1000, 'completion_tokens': 100, 'total_tokens': 1100,
                              'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 1000}}
            return httpx.Response(200, json=body)
        return self.wire.generate(messages, tools, closing, httpx.MockTransport(respond))

    def finish(self):
        self.wire.ledger.finish(self.wire.arm, self.wire.token)
