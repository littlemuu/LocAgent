"""One explicitly authorized continuation, same r01 ledger and cumulative cap.

Original evidence is read-only. New authorization/events/bodies are appended in
the existing directory; old unknown is never refunded. No automatic retries.
"""
from decimal import Decimal
import json
from pathlib import Path

from locagent_service import bailian_expanded_runner as r
from locagent_service.bailian_response import validate_response

RESUME_APPROVAL = 'Sentinel_f70cd891666081918372e2e6c932a09f'
BASE_AUDIT = r.ROOT / 'outputs/bailian-expanded50-live-evaluation-20261016-r01/ledger-audit.json'
BASE_AUDIT_SHA = '80fedf082b53492f8dda9d8a5a0b82a09baf36e29849f87c1b748addedd0b3db'
BASE_SPENT = Decimal('0.183772625')
BASE_UNKNOWN = Decimal('0.262144')
FIRST = 490
LAST = 617
AUTH_NAME = 'continuation-authorization.json'


def baseline():
    raw = BASE_AUDIT.read_bytes()
    if r.sha(raw) != BASE_AUDIT_SHA:
        raise r.Halt('base_audit_changed')
    audit = r.load_json(raw)
    directory = r.RUN_DOMAIN / r.RUN_ID
    if not directory.is_dir() or directory.is_symlink():
        raise r.Halt('original_run_required')
    for name, expected in audit['ledger_hashes'].items():
        if r.sha(r.secure_read(directory / name)) != expected:
            raise r.Halt('original_evidence_changed')
    if audit['engine_hashes'] != r.engine_identity():
        raise r.Halt('original_engine_changed')
    if (audit['states'] != {'settled': 490, 'unknown': 1}
            or audit['dispatch_events'] != 491 or audit['spent_cny'] != str(BASE_SPENT)
            or audit['unknown_cny'] != str(BASE_UNKNOWN)):
        raise r.Halt('unexpected_base_balance')
    return audit


def spec():
    audit = baseline()
    plan, directory, _, _ = r._fixed_spec(r.RUN_DOMAIN)
    selected = plan[FIRST:LAST + 1]
    if len(selected) != 128 or sum(len(p['ids']) for p in selected) != 2024:
        raise r.Halt('continuation_scope_mismatch')
    binding = {'version': 1, 'approval_id': RESUME_APPROVAL, 'approved_at': '2026-10-16T08:58:00Z',
               'run_id': r.RUN_ID, 'ledger_directory': str(directory), 'cap_cny': '2',
               'base_audit_sha256': BASE_AUDIT_SHA, 'original_spent_cny': str(BASE_SPENT),
               'original_unknown_retained_cny': str(BASE_UNKNOWN), 'manifest_sha256': r.MANIFEST_SHA,
               'continuation_plan_sha256': r.sha(r.canonical(selected)), 'first_batch': FIRST, 'last_batch': LAST,
               'max_new_requests': 128, 'max_cumulative_physical_requests': 619,
               'endpoint': r.ENDPOINT, 'model': 'qwen3.7-text-embedding-flash', 'dimensions': 1024,
               'rate_cny_per_million': str(r.RATE), 'tokens_per_input': r.TOKEN_LIMIT,
               'engine_hashes': r.engine_identity(), 'resume_engine_sha256': r.sha(Path(__file__).read_bytes())}
    return plan, directory, binding, audit


class _AttemptLedger:
    def __init__(self, directory, plan, binding, *, base_spent=BASE_SPENT, base_unknown=BASE_UNKNOWN, original_names=()):
        self.directory, self.plan, self.binding = Path(directory), plan, binding
        self.base_spent, self.base_unknown = base_spent, base_unknown
        self.events, self.rows = [], {}
        auth = self.directory / AUTH_NAME
        if not auth.exists():
            if any(p.name.startswith('continuation-') for p in self.directory.iterdir()):
                raise r.Halt('orphan_continuation_evidence')
            r.persist(auth, r.canonical(binding))
        if r.secure_read(auth) != r.canonical(binding):
            raise r.Halt('continuation_authorization_changed')
        files = sorted(self.directory.glob('continuation-event-*.json'))
        for i, path in enumerate(files):
            if path.name != f'continuation-event-{i:06d}.json':
                raise r.Halt('continuation_event_gap')
            record = r.load_json(r.secure_read(path))
            if record != self.envelope(record['data']):
                raise r.Halt('continuation_chain_changed')
            self.apply(record['data'])
            self.events.append(record)
        allowed = set(original_names) | {'lock', AUTH_NAME} | {p.name for p in files}
        allowed |= {f'continuation-body-{i:06d}.bin' for i in self.rows}
        if any(p.name not in allowed for p in self.directory.iterdir()):
            raise r.Halt('unexpected_run_artifact')

    def envelope(self, data):
        return {'sequence': len(self.events), 'previous': r.sha(r.canonical(self.events[-1])) if self.events
                else r.sha(r.canonical(self.binding)), 'data': data}

    def balance(self):
        spent = self.base_spent + sum((r.cost(v['tokens']) for v in self.rows.values() if v['state'] == 'settled'), Decimal(0))
        unknown = self.base_unknown + sum((r.cost(v['n'] * r.TOKEN_LIMIT) for v in self.rows.values() if v['state'] == 'unknown'), Decimal(0))
        inflight = sum((r.cost(v['n'] * r.TOKEN_LIMIT) for v in self.rows.values() if v['state'] in ('reserved', 'dispatch', 'raw')), Decimal(0))
        return {'spent': spent, 'unknown': unknown, 'inflight': inflight}

    def raw(self, i):
        raw = r.secure_read(self.directory / f'continuation-body-{i:06d}.bin')
        if len(raw) > r.MAX_BODY or r.sha(raw) != self.rows[i]['response_sha256']:
            raise r.Halt('continuation_raw_changed')
        return raw

    def apply(self, data):
        phase, i = data.get('phase'), data.get('batch_index')
        if type(i) is not int or not FIRST <= i < FIRST + len(self.plan):
            raise r.Halt('continuation_batch_out_of_scope')
        item = self.plan[i - FIRST]
        if phase == 'reserved':
            n = len(item['ids'])
            expected = {'phase': phase, 'batch_index': i, 'physical_attempt_index': i + 1,
                        'n': n, 'request_sha256': item['body_sha256']}
            if data != expected or i != FIRST + len(self.rows) or any(v['state'] != 'settled' for v in self.rows.values()):
                raise r.Halt('invalid_continuation_reservation')
            if sum(self.balance().values()) + r.cost(n * r.TOKEN_LIMIT) > Decimal('2'):
                raise r.Halt('cumulative_cap_exceeded')
            self.rows[i] = {'state': phase, 'n': n}
        elif phase == 'dispatch':
            if data != {'phase': phase, 'batch_index': i} or self.rows[i]['state'] != 'reserved':
                raise r.Halt('invalid_continuation_dispatch')
            self.rows[i]['state'] = phase
        elif phase == 'raw':
            if set(data) != {'phase', 'batch_index', 'http_status', 'response_sha256'} or self.rows[i]['state'] != 'dispatch':
                raise r.Halt('invalid_continuation_raw')
            if type(data['http_status']) is not int:
                raise r.Halt('invalid_http_status')
            self.rows[i].update(state=phase, http_status=data['http_status'], response_sha256=data['response_sha256'])
            self.raw(i)
        elif phase == 'settled':
            row = self.rows[i]
            if row['state'] != 'raw':
                raise r.Halt('invalid_continuation_settlement')
            _, tokens, _ = validate_response(self.raw(i), row['n'], row['http_status'])
            if data != {'phase': phase, 'batch_index': i, 'tokens': tokens,
                        'cost_cny': str(r.cost(tokens)), 'response_sha256': row['response_sha256']}:
                raise r.Halt('continuation_settlement_changed')
            row.update(state=phase, tokens=tokens)
        elif phase == 'unknown':
            if data != {'phase': phase, 'batch_index': i} or self.rows[i]['state'] not in ('reserved', 'dispatch', 'raw'):
                raise r.Halt('invalid_continuation_unknown')
            self.rows[i]['state'] = phase
        else:
            raise r.Halt('invalid_continuation_phase')

    def append(self, data):
        record = self.envelope(data)
        self.apply(data)
        r.persist(self.directory / f'continuation-event-{len(self.events):06d}.json', r.canonical(record))
        self.events.append(record)

    def settle(self, i):
        row = self.rows[i]
        try:
            _, tokens, _ = validate_response(self.raw(i), row['n'], row['http_status'])
        except Exception:
            self.append({'phase': 'unknown', 'batch_index': i})
            raise r.Halt('continuation_invalid_response_held') from None
        self.append({'phase': 'settled', 'batch_index': i, 'tokens': tokens,
                     'cost_cny': str(r.cost(tokens)), 'response_sha256': row['response_sha256']})

    def recover(self):
        for i, row in self.rows.items():
            if row['state'] in ('reserved', 'dispatch'):
                self.append({'phase': 'unknown', 'batch_index': i})
            elif row['state'] == 'raw':
                self.settle(i)
        if any(v['state'] == 'unknown' for v in self.rows.values()):
            raise r.Halt('continuation_unknown_stop_no_retry')


def _drive(ledger, transport, checkpoint=lambda _: None):
    ledger.recover()
    for offset, item in enumerate(ledger.plan):
        i = FIRST + offset
        if i in ledger.rows:
            continue
        checkpoint('before_reserve')
        ledger.append({'phase': 'reserved', 'batch_index': i, 'physical_attempt_index': i + 1,
                       'n': len(item['ids']), 'request_sha256': item['body_sha256']})
        checkpoint('after_reserve')
        ledger.append({'phase': 'dispatch', 'batch_index': i})
        checkpoint('before_send')
        try:
            status, raw = transport(r.ENDPOINT, r.canonical(item['body']))
        except Exception:
            ledger.append({'phase': 'unknown', 'batch_index': i})
            raise r.Halt('continuation_transport_unknown') from None
        checkpoint('after_send')
        if type(status) is not int or not isinstance(raw, bytes) or len(raw) > r.MAX_BODY:
            ledger.append({'phase': 'unknown', 'batch_index': i})
            raise r.Halt('continuation_response_limit_or_type')
        r.persist(ledger.directory / f'continuation-body-{i:06d}.bin', raw)
        checkpoint('after_raw_file')
        ledger.append({'phase': 'raw', 'batch_index': i, 'http_status': status, 'response_sha256': r.sha(raw)})
        checkpoint('before_settle')
        ledger.settle(i)
        checkpoint('after_settle')
    return {'status': 'continuation_complete', 'new_requests_settled': len(ledger.rows),
            **{k + '_cny': str(v) for k, v in ledger.balance().items()},
            'original_unknown_preserved': str(BASE_UNKNOWN), 'cumulative_cap_cny': '2'}


def run(*, approval_id=None):
    if approval_id != RESUME_APPROVAL:
        raise r.Halt('continuation_not_authorized')
    plan, directory, binding, audit = spec()
    with r.locked(directory):
        # Recheck fixed original evidence inside the shared original-run lock.
        baseline()
        ledger = _AttemptLedger(directory, plan[FIRST:LAST + 1], binding,
                                original_names=audit['ledger_hashes'])
        ledger.recover()
        from locagent_service.bailian_expanded_transport import PinnedHTTPS
        transport = PinnedHTTPS(approval_id=r.APPROVAL_ID)
        return _drive(ledger, transport)


def preview():
    plan, directory, binding, audit = spec()
    return {'mode': 'dry-run', 'run_id': r.RUN_ID, 'new_requests_limit': 128,
            'cumulative_requests_limit': 619, 'new_document_inputs': 1974, 'new_queries': 50,
            'cumulative_cap_cny': '2', 'base_held_cny': str(BASE_SPENT + BASE_UNKNOWN),
            'ledger_directory': str(directory), 'original_unknown_retained_cny': str(BASE_UNKNOWN)}
