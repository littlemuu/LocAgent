"""Pinned expanded-50 executor with an append-only, fsynced local budget journal.

Real entry binds one explicit user approval; default CLI remains dry-run.
No database or automatic retries. Caller transport injection is test-only.
POSIX local filesystem required; not a distributed lock or adversarial audit store.
"""
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat

from locagent_service.bailian_contract import canonical, request
from locagent_service.bailian_response import validate_response

MANIFEST_SHA = '78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b'
ENDPOINT = 'https://ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding'
RATE = Decimal('0.125')
TOKEN_LIMIT = 131072
MAX_BATCH = 16
MAX_BODY = 4 * 1024 * 1024
OLD_HELD = Decimal('1.277952')
RUN_ID = 'bailian-expanded50-78e24794-cap2-20261016-r01'
RUN_CAP = '2'
ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / 'outputs/bailian-expanded50-20261016/frozen/manifest.json'
RUN_DOMAIN = ROOT / 'outputs/bailian-expanded-budget-runs'
APPROVAL_ID = 'Sentinel_fbb9c43d04ac819197437d5bf7cf38f3'


class Halt(RuntimeError):
    """Safe fixed diagnostic code only; never forward transport/provider messages."""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Halt('duplicate_json_key')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Halt('nonfinite_json')))
    except (ValueError, UnicodeError, RecursionError):
        raise Halt('invalid_json') from None


def money(value):
    # Exact decimal strings only: bool/float/NaN/Infinity never accepted.
    if not isinstance(value, str) or len(value) > 40:
        raise Halt('invalid_cap')
    try:
        result = Decimal(value)
    except Exception:
        raise Halt('invalid_cap') from None
    if not result.is_finite() or result <= 0 or result > 1000 or result.as_tuple().exponent < -9:
        raise Halt('invalid_cap')
    return result


def cost(tokens):
    return Decimal(tokens) * RATE / 1000000


def load_plan(path, root):
    raw = Path(path).read_bytes()
    if sha(raw) != MANIFEST_SHA:
        raise Halt('manifest_hash_mismatch')
    manifest = load_json(raw)
    if manifest['endpoint'] != ENDPOINT or manifest['dimensions'] != 1024:
        raise Halt('manifest_contract_mismatch')
    for name, expected in manifest['engine_hashes'].items():
        target = Path(root) / name
        if sha(target.read_bytes()) != expected:
            raise Halt('frozen_engine_changed')
    plan = manifest['planned_requests']
    seen = {'document': [], 'query': []}
    queries = {q['id']: q['text'] for q in manifest['queries']}
    docs = manifest['unique_documents']
    for item in plan:
        role = item['role']
        if role not in seen or not 1 <= len(item['ids']) <= MAX_BATCH:
            raise Halt('invalid_batch')
        texts = [docs[i]['text'] if role == 'document' else queries[i] for i in item['ids']]
        if item['body'] != request(texts, role) or sha(canonical(item['body'])) != item['body_sha256']:
            raise Halt('request_binding_mismatch')
        seen[role].extend(item['ids'])
    if len(plan) != 618 or len(docs) != 9814 or len(queries) != 50:
        raise Halt('frozen_membership_mismatch')
    if sorted(seen['document']) != sorted(docs) or sorted(seen['query']) != sorted(queries):
        raise Halt('request_membership_mismatch')
    return plan


def engine_identity():
    root = Path(__file__).resolve().parent
    return {name: sha((root / name).read_bytes()) for name in
            ('bailian_expanded_runner.py', 'bailian_expanded_transport.py',
             'bailian_response.py', 'bailian_contract.py', 'bailian_config.py')}


def approval(plan, cap, *, purpose='offline-test'):
    """Build a binding, NOT an authorization grant. Caller needs separate consent.

    This release deliberately cannot mint a live authorization. A later reviewed
    integration must explicitly add the approved transport/authorization path.
    """
    if purpose != 'offline-test':
        raise Halt('live_execution_not_enabled')
    limit = money(cap)
    return {'version': 1, 'purpose': purpose, 'manifest_sha256': MANIFEST_SHA,
            'plan_sha256': sha(canonical(plan)), 'endpoint': ENDPOINT,
            'model': 'qwen3.7-text-embedding-flash', 'dimension': 1024,
            'rate_cny_per_million': str(RATE), 'tokens_per_input': TOKEN_LIMIT,
            'max_batch': MAX_BATCH, 'request_limit': len(plan), 'cap_cny': str(limit),
            'old_held_cny_reference_only': str(OLD_HELD), 'engine_hashes': engine_identity()}


def checked_plan(plan):
    if not isinstance(plan, list) or not 1 <= len(plan) <= 618:
        raise Halt('invalid_plan')
    for item in plan:
        body = item['body']
        texts = body['input']['texts']
        if not 1 <= len(texts) <= MAX_BATCH or len(item['ids']) != len(texts):
            raise Halt('invalid_batch')
        if request(texts, item['role']) != body or sha(canonical(body)) != item['body_sha256']:
            raise Halt('request_binding_mismatch')


def fsync_dir(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def secure_read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise Halt('unsafe_artifact')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            return stream.read(MAX_BODY + 1)
    finally:
        os.close(fd)


def persist(path, raw):
    # O_EXCL: never overwrite evidence. An interrupted partial file poisons the
    # journal on recovery, intentionally stopping before any further dispatch.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    fsync_dir(path.parent)


@contextmanager
def locked(directory):
    directory = Path(directory)
    # User-selected existing trusted parent, no repository paths. Reject symlink
    # components; concurrent malicious parent replacement is outside this threat model.
    for p in (directory, *directory.parents):
        if p.is_symlink():
            raise Halt('symlink_run_path')
    try:
        directory.mkdir(mode=0o700)
        fsync_dir(directory.parent)
    except FileExistsError:
        pass
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
        raise Halt('unsafe_run_directory')
    fd = os.open(directory / 'lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        lock_info = os.fstat(fd)
        if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1 or lock_info.st_mode & 0o077 or lock_info.st_uid != os.getuid():
            raise Halt('unsafe_lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Halt('concurrent_run') from None
        yield directory
    finally:
        os.close(fd)  # never unlink the lock inode


class Journal:
    def __init__(self, directory, plan, binding):
        self.directory, self.plan, self.binding = directory, plan, binding
        self.cap = money(binding['cap_cny'])
        self.events = []
        self.rows = {}
        meta = directory / 'run.json'
        if not meta.exists():
            if any(p.name != 'lock' for p in directory.iterdir()):
                raise Halt('orphan_artifacts')
            persist(meta, canonical(binding))
        if secure_read(meta) != canonical(binding):
            raise Halt('run_binding_changed')
        paths = sorted(directory.glob('event-*.json'))
        for i, path in enumerate(paths):
            if path.name != f'event-{i:06d}.json':
                raise Halt('journal_gap')
            record = load_json(secure_read(path))
            expected = self.envelope(record['data'])
            if record != expected:
                raise Halt('journal_hash_mismatch')
            self.apply(record['data'])
            self.events.append(record)
        permitted = {'lock', 'run.json'} | {p.name for p in paths}
        # A raw file may survive a crash before its journal event. Keep held and
        # stop, never infer successful response/request binding from filename.
        permitted |= {f'body-{i:06d}.bin' for i in self.rows}
        if any(p.name not in permitted for p in directory.iterdir()):
            raise Halt('orphan_artifacts')

    def envelope(self, data):
        record = {'sequence': len(self.events), 'previous':
                  sha(canonical(self.events[-1])) if self.events else sha(canonical(self.binding)),
                  'data': data}
        return record

    def balance(self):
        spent = sum((cost(r['tokens']) for r in self.rows.values() if r['state'] == 'settled'), Decimal(0))
        unknown = sum((cost(r['n'] * TOKEN_LIMIT) for r in self.rows.values() if r['state'] == 'unknown'), Decimal(0))
        inflight = sum((cost(r['n'] * TOKEN_LIMIT) for r in self.rows.values()
                        if r['state'] in ('reserved', 'dispatch', 'raw')), Decimal(0))
        return {'spent': spent, 'unknown': unknown, 'inflight': inflight}

    def apply(self, data):
        # All monetary values recomputed from immutable input counts and usage.
        phase, i = data.get('phase'), data.get('request')
        if type(i) is not int or not 0 <= i < len(self.plan):
            raise Halt('invalid_request_index')
        item = self.plan[i]
        if phase == 'reserved':
            n = len(item['ids'])
            if data != {'phase': phase, 'request': i, 'body_sha256': item['body_sha256'], 'n': n}:
                raise Halt('reservation_binding_changed')
            if i != len(self.rows) or any(r['state'] != 'settled' for r in self.rows.values()):
                raise Halt('nonsequential_reservation')
            if sum(self.balance().values()) + cost(n * TOKEN_LIMIT) > self.cap:
                raise Halt('cap_exceeded')
            self.rows[i] = {'state': phase, 'n': n}
        elif phase == 'dispatch':
            if data != {'phase': phase, 'request': i} or self.rows[i]['state'] != 'reserved':
                raise Halt('invalid_dispatch')
            self.rows[i]['state'] = phase
        elif phase == 'raw':
            if set(data) != {'phase', 'request', 'response_sha256', 'http_status'} or self.rows[i]['state'] != 'dispatch':
                raise Halt('invalid_raw_event')
            raw = secure_read(self.directory / f'body-{i:06d}.bin')
            if len(raw) > MAX_BODY or sha(raw) != data['response_sha256'] or type(data['http_status']) is not int:
                raise Halt('raw_binding_changed')
            self.rows[i].update(state=phase, raw_hash=data['response_sha256'], http_status=data['http_status'])
        elif phase == 'settled':
            row = self.rows[i]
            if row['state'] != 'raw':
                raise Halt('invalid_settlement')
            raw = secure_read(self.directory / f'body-{i:06d}.bin')
            if sha(raw) != row['raw_hash']:
                raise Halt('raw_binding_changed')
            _, tokens, _ = validate_response(raw, row['n'], row['http_status'])
            if data != {'phase': phase, 'request': i, 'tokens': tokens,
                        'cost_cny': str(cost(tokens)), 'response_sha256': row['raw_hash']}:
                raise Halt('settlement_changed')
            row.update(state=phase, tokens=tokens)
        elif phase == 'unknown':
            if data != {'phase': phase, 'request': i} or self.rows[i]['state'] not in ('reserved', 'dispatch', 'raw'):
                raise Halt('invalid_unknown')
            self.rows[i]['state'] = phase
        else:
            raise Halt('invalid_phase')

    def append(self, data):
        record = self.envelope(data)
        # Validate before durability; if write/fsync fails, caller exits and must
        # reload journal before another action. No dispatch after failed append.
        self.apply(data)
        persist(self.directory / f'event-{len(self.events):06d}.json', canonical(record))
        self.events.append(record)

    def settle(self, i):
        row = self.rows[i]
        try:
            raw = secure_read(self.directory / f'body-{i:06d}.bin')
            if sha(raw) != row['raw_hash']:
                raise Halt('raw_binding_changed')
            _, tokens, _ = validate_response(raw, row['n'], row['http_status'])
        except Exception:
            self.append({'phase': 'unknown', 'request': i})
            raise Halt('invalid_response_held') from None
        self.append({'phase': 'settled', 'request': i, 'tokens': tokens,
                     'cost_cny': str(cost(tokens)), 'response_sha256': row['raw_hash']})

    def recover(self):
        for i, row in self.rows.items():
            if row['state'] in ('reserved', 'dispatch'):
                self.append({'phase': 'unknown', 'request': i})
            elif row['state'] == 'raw':
                self.settle(i)  # durable validated response: settle without resend
        if any(row['state'] == 'unknown' for row in self.rows.values()):
            raise Halt('unknown_held_stop')


def _execute_journal(plan, directory, binding, transport, *, checkpoint=lambda _: None, identity=None):
    """Offline-test execution core; transport(endpoint, canonical_bytes)->(status, bytes).

    Caller must retain the expected binding independently. Stored run.json cannot
    confer authorization. Transport errors are ambiguous and never retried.
    """
    # Detach the request plan and cap binding from mutable caller-owned objects.
    plan, binding = load_json(canonical(plan)), load_json(canonical(binding))
    checked_plan(plan)
    expected = approval(plan, binding['cap_cny'])
    if identity is not None:
        expected.update(identity)
        if identity.get('approval_id') == APPROVAL_ID:
            expected['purpose'] = 'approved-live'
    if binding != expected:
        raise Halt('approval_binding_changed')
    with locked(directory) as directory:
        journal = Journal(directory, plan, binding)
        journal.recover()
        for i, item in enumerate(plan):
            if i in journal.rows:
                continue
            checkpoint('before_reserve')
            journal.append({'phase': 'reserved', 'request': i,
                            'body_sha256': item['body_sha256'], 'n': len(item['ids'])})
            checkpoint('after_reserve')
            journal.append({'phase': 'dispatch', 'request': i})
            checkpoint('before_send')
            try:
                status, raw = transport(ENDPOINT, canonical(item['body']))
            except Exception:
                journal.append({'phase': 'unknown', 'request': i})
                raise Halt('transport_unknown_held') from None
            checkpoint('after_send')
            if type(status) is not int or not isinstance(raw, bytes) or len(raw) > MAX_BODY:
                journal.append({'phase': 'unknown', 'request': i})
                raise Halt('response_limit_or_type_held')
            persist(directory / f'body-{i:06d}.bin', raw)
            checkpoint('after_raw_file')
            journal.append({'phase': 'raw', 'request': i, 'http_status': status, 'response_sha256': sha(raw)})
            checkpoint('before_settle')
            journal.settle(i)
            checkpoint('after_settle')
        return {'status': 'complete_live' if binding['purpose'] == 'approved-live' else 'complete_offline_test', 'requests_settled': len(journal.rows),
                **{key + '_cny': str(value) for key, value in journal.balance().items()},
                'cap_cny': binding['cap_cny'], 'live_authorized': binding['purpose'] == 'approved-live'}


def _fixed_spec(domain, *, run_id=RUN_ID, directory=None, cap=RUN_CAP, manifest=None):
    """Only the exact frozen source and fixed run are admissible. No caller plan."""
    if run_id != RUN_ID or cap != RUN_CAP:
        raise Halt('unapproved_run_or_cap')
    domain = Path(domain)
    if not domain.is_absolute() or domain != domain.resolve():
        raise Halt('noncanonical_domain')
    for p in (domain, *domain.parents):
        if p.is_symlink():
            raise Halt('symlink_run_path')
    destination = domain / RUN_ID
    # Reject aliases rather than opening a second budget/lock namespace.
    if directory is not None and str(directory) != str(destination):
        raise Halt('noncanonical_run_directory')
    if manifest is not None and str(manifest) != str(FROZEN):
        raise Halt('noncanonical_manifest')
    if destination.is_symlink():
        raise Halt('symlink_run_path')
    plan = load_plan(FROZEN, ROOT)
    identity = {'run_id': RUN_ID, 'ledger_domain': str(domain),
                'ledger_directory': str(destination), 'frozen_manifest_path': str(FROZEN)}
    binding = approval(plan, RUN_CAP)
    binding.update(identity)
    return plan, destination, binding, identity


def execute(*, run_id=RUN_ID, directory=None, cap=RUN_CAP, manifest=None, approval_id=None):
    """Only the user's explicitly approved fixed run. No caller transport/root."""
    plan, destination, binding, identity = _fixed_spec(
        RUN_DOMAIN, run_id=run_id, directory=directory, cap=cap, manifest=manifest)
    if approval_id != APPROVAL_ID:
        raise Halt('real_execution_not_authorized')
    from locagent_service.bailian_expanded_transport import PinnedHTTPS
    transport = PinnedHTTPS(approval_id=approval_id)
    identity.update(approval_id=APPROVAL_ID, approved_date='2026-10-16')
    binding.update(identity, purpose='approved-live')
    try:
        RUN_DOMAIN.mkdir(mode=0o700)
        fsync_dir(RUN_DOMAIN.parent)
    except FileExistsError:
        pass
    if RUN_DOMAIN.stat().st_mode & 0o077 or RUN_DOMAIN.is_symlink():
        raise Halt('unsafe_authority_domain')
    return _execute_journal(plan, destination, binding, transport, identity=identity)


def _offline_frozen_acceptance(domain, transport, *, checkpoint=lambda _: None, **claims):
    """Test harness only: isolated fake ledger, NOT a real-run authorization path.

    Caller must block sockets. Production execute does not expose domain/transport
    injection and never calls this helper. Arbitrary code with module access is
    outside the authorization threat model, just as monkeypatching constants is.
    """
    plan, destination, binding, identity = _fixed_spec(domain, **claims)
    return _execute_journal(plan, destination, binding, transport,
                            checkpoint=checkpoint, identity=identity)


def preview(path, root, cap='2'):
    plan = load_plan(path, root)
    limit = money(cap)
    largest = max(cost(len(item['ids']) * TOKEN_LIMIT) for item in plan)
    return {'mode': 'dry-run', 'network_calls': 0, 'writes': 0, 'live_authorized': False,
            'manifest_sha256': MANIFEST_SHA, 'public_document_inputs': 9814,
            'public_query_inputs': 50, 'endpoint': ENDPOINT, 'model': 'qwen3.7-text-embedding-flash',
            'max_requests': len(plan), 'max_batch': MAX_BATCH,
            'max_one_request_reservation_cny': str(largest), 'proposed_new_run_cap_cny': str(limit),
            'old_held_cny_unchanged': str(OLD_HELD), 'combined_exposure_if_approved_cny': str(limit + OLD_HELD),
            'can_reserve_first_batch': cost(len(plan[0]['ids']) * TOKEN_LIMIT) <= limit,
            'completion_guaranteed': False}
