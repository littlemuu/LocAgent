"""Full-context durable reservations; uncertain paid calls are never replayed."""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from locagent_service.sources import canonical, digest

INPUT_CNY = Decimal('3')
OUTPUT_CNY = Decimal('12')
AUTHORIZED_CNY = Decimal('20')
PROVIDER_CONTEXT_TOKENS = 1048576
# This approval is for one first pilot, not one fresh budget per output directory.
# No CLI/environment override. A new plan/approval requires separate review.
AUTHORIZED_PLAN_HASH = '30826b12d1b2d4cd8027c416aa22bd3c85f2217f2e91ff12c3dfcf54c643e6c6'
RECOVERABLE_PLAN_HASH = 'dfb6c70825c4f19260b726a15093b2c695be8dedf7223bcffc250bf9a1a41e92'
RECOVERABLE_LEDGER_SHA256 = 'c17aa04120516df26b4567c4cc0178e54f21e8e8c9a234673022580c761d3e12'
RECOVERABLE_MARKER_SHA256 = '5dc7542f12022c1a04d0af7a048dfa94c05c2548da93eb16e7f2d5ed1cf94442'
AUTHORIZATION_PATH = (Path(__file__).resolve().parents[1] /
                      'outputs/stage4/authorizations/first-pilot-cny20.json')

LIVE_CONFIG = {
    'model': 'openai/deepseek-v4-flash', 'resolved_family': 'DeepSeek-V4.1-Flash',
    'api_base': 'https://api.deepseek.com', 'thinking': 'disabled', 'temperature': 0,
    'max_calls': 3, 'max_output_tokens': 512, 'input_estimate_gate': 65536,
    'provider_context_tokens': PROVIDER_CONTEXT_TOKENS,
}
RESERVATION_BASIS = {
    'version': 2, 'input_tokens_per_call': PROVIDER_CONTEXT_TOKENS,
    'output_tokens_per_call': 512, 'input_cny_per_million': '3',
    'output_cny_per_million': '12',
    'scope': 'full_provider_context_plus_max_tokens',
    'pricing_source': 'https://api-docs.deepseek.com/quick_start/pricing/',
    'account_confirmation_required': True,
}


def validate_live_config(config):
    for key, expected in LIVE_CONFIG.items():
        if type(config.get(key)) is not type(expected) or config[key] != expected:
            raise ValueError('Live configuration differs from the reviewed fixed pilot')
    if 'max_input_tokens' in config:
        raise ValueError('Legacy input heuristic cannot be a live reservation cap')


def reserve_cost(config):
    validate_live_config(config)
    return (PROVIDER_CONTEXT_TOKENS * INPUT_CNY +
            config['max_output_tokens'] * OUTPUT_CNY) / Decimal(1000000)


def decimal_rate(value):
    try:
        if isinstance(value, bool):
            raise ValueError('Boolean is not a price')
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid price') from exc
    if not number.is_finite() or number <= 0:
        raise ValueError('Finite positive price required')
    return number


def validate_live_plan(plan):
    validate_live_config(plan['config'])
    worst = reserve_cost(plan['config']) * 6
    if (type(plan.get('version')) is not int or plan['version'] != 2
        or canonical(plan.get('reservation_basis')) != canonical(RESERVATION_BASIS)
        or not isinstance(plan.get('sources'), list) or len(plan['sources']) != 1
        or not isinstance(plan['sources'][0], str) or not plan['sources'][0]
        or canonical(plan.get('arms')) != canonical([False, True])
        or type(plan.get('denominator_per_arm')) is not int or plan['denominator_per_arm'] != 1
        or type(plan.get('max_calls')) is not int or plan['max_calls'] != 6
        or decimal_rate(plan.get('budget_cny')) != AUTHORIZED_CNY
        or decimal_rate(plan.get('worst_case_reservation_cny')) != worst):
        raise ValueError('Live plan must be the fixed six-call, one-sample pilot')
    return worst


def validate_pricing_confirmation(plan, confirmation):
    required = {'version', 'plan_hash', 'provider', 'currency',
                'input_cache_miss_peak_per_million', 'output_peak_per_million',
                'all_charges_included', 'confirmed_at_utc'}
    if (not isinstance(confirmation, dict) or not required <= confirmation.keys()
        or confirmation.keys() - required - {'cny_per_usd_all_in_ceiling'}
        or type(confirmation['version']) is not int or confirmation['version'] != 1
        or confirmation['plan_hash'] != digest(canonical(plan))
        or confirmation['provider'] != 'deepseek-official'
        or confirmation['all_charges_included'] is not True):
        raise ValueError('Fresh account pricing confirmation bound to this plan is required')
    currency = confirmation['currency']
    if currency == 'CNY':
        if 'cny_per_usd_all_in_ceiling' in confirmation:
            raise ValueError('CNY confirmation cannot contain a USD conversion')
        multiplier = Decimal(1)
    elif currency == 'USD':
        multiplier = decimal_rate(confirmation.get('cny_per_usd_all_in_ceiling'))
        if multiplier > 10:
            raise ValueError('All-in USD conversion ceiling exceeds reservation assumption')
    else:
        raise ValueError('Only explicitly confirmed CNY/USD billing is supported')
    try:
        when = datetime.fromisoformat(confirmation['confirmed_at_utc'].replace('Z', '+00:00'))
        if when.tzinfo is None or when.utcoffset().total_seconds() != 0:
            raise ValueError('UTC timestamp required')
        age = (datetime.now(timezone.utc) - when).total_seconds()
        if not 0 <= age <= 86400:
            raise ValueError('Pricing confirmation must be at most 24 hours old')
    except (AttributeError, TypeError) as exc:
        raise ValueError('Invalid confirmation timestamp') from exc
    input_rate = decimal_rate(confirmation['input_cache_miss_peak_per_million']) * multiplier
    output_rate = decimal_rate(confirmation['output_peak_per_million']) * multiplier
    if input_rate > INPUT_CNY or output_rate > OUTPUT_CNY:
        raise ValueError('Confirmed all-in prices exceed the reviewed ceilings')
    return {'input_cny_per_million': str(input_rate), 'output_cny_per_million': str(output_rate)}


@contextmanager
def paid_mode(enabled):
    """Explicit CLI switch changes this process only; never rewrites an env file."""
    previous = os.environ.get('LOCAGENT_ALLOW_PAID')
    os.environ['LOCAGENT_ALLOW_PAID'] = '1' if enabled else '0'
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('LOCAGENT_ALLOW_PAID', None)
        else:
            os.environ['LOCAGENT_ALLOW_PAID'] = previous


def save(path, value):
    """Atomic durable replacement, guarded by a separate stable lock inode."""
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def validate_authorized_plan(plan):
    if digest(canonical(plan)) != AUTHORIZED_PLAN_HASH:
        raise ValueError('Plan is not the approved first pilot')


def claim_authorization(path, plan, pricing_confirmation):
    """Consume this approval once, across directories/processes and confirmations."""
    validate_authorized_plan(plan)
    marker = AUTHORIZATION_PATH
    if recovery_journal_path().exists() or recovery_journal_path().is_symlink():
        raise RuntimeError('An existing recovery audit prevents a fresh authorization')
    marker.parent.mkdir(parents=True, exist_ok=True)
    # Empty/interrupted markers also remain consumed: never auto-delete or reclaim.
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    token = uuid4().hex
    save(marker, {'version': 1, 'authorization': 'first-pilot-cny20',
                  'plan_hash': AUTHORIZED_PLAN_HASH, 'limit': '20', 'token': token,
                  'pricing_hash': digest(canonical(pricing_confirmation)),
                  'ledger_path': str(Path(path).resolve())})
    return token


def validate_authorization(path, state):
    """Copies/moved ledgers cannot create independent spending authority."""
    try:
        validate_authorized_plan(state['plan'])
        marker = json.loads(AUTHORIZATION_PATH.read_text())
        journal = recovery_journal_path()
        if journal.exists() or journal.is_symlink() or 'zero_use_recovery' in marker:
            raw = journal.read_bytes()
            audit = json.loads(raw)
            audit_hash = digest(raw)
            if (marker.get('zero_use_recovery') != {'count': 1, 'audit_sha256': audit_hash}
                or state.get('recovery_audit_sha256') != audit_hash
                or audit['new_plan_hash'] != AUTHORIZED_PLAN_HASH
                or audit['new_ledger_path'] != str(Path(path).resolve())
                or audit['new_token'] != marker['token']):
                raise ValueError('Recovery audit is incomplete or does not match its owner')
        if (marker['version'] != 1 or marker['authorization'] != 'first-pilot-cny20'
            or marker['plan_hash'] != AUTHORIZED_PLAN_HASH or marker['limit'] != '20'
            or marker['ledger_path'] != str(Path(path).resolve())
            or marker['token'] != state['authorization_token']
            or marker['pricing_hash'] != digest(canonical(state['pricing_confirmation']))):
            raise ValueError('Authorization owner mismatch')
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError('Shared authorization is missing or requires review') from exc


def initialize_ledger(path, plan, pricing_confirmation=None):
    # Resolve once at entry: ownership, locking and atomic replacement use one path.
    path = Path(path).resolve()
    validate_live_plan(plan)
    rates = validate_pricing_confirmation(plan, pricing_confirmation)
    validate_authorized_plan(plan)
    if Path(path).exists():
        raise FileExistsError('Run ledger already exists')
    token = claim_authorization(path, plan, pricing_confirmation)
    # Authorization is durable before ledger creation or any provider execution.
    # Failure from here consumes the approval and requires review, never replay.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    save(path, initial_ledger_state(plan, pricing_confirmation, rates, token))


def initial_ledger_state(plan, pricing_confirmation, rates, token):
    return {'version': 2, 'plan': plan, 'plan_hash': digest(canonical(plan)),
            'authorization_token': token,
            'pricing_confirmation': pricing_confirmation, 'confirmed_rates': rates,
            'config_hash': digest(canonical(plan['config'])), 'limit': '20',
            'reserved': '0', 'halted': False, 'calls': [],
            'sources': plan['sources'], 'max_calls': 6}


def recovery_journal_path():
    marker = AUTHORIZATION_PATH.resolve()
    return marker.with_name(marker.name + '.zero-use-recovery.json')


@contextmanager
def ledger_lock(path):
    path = Path(path).resolve()
    fd = os.open(str(path) + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'r+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def recover_zero_use_ledger(previous_path, path, plan, pricing_confirmation):
    """One audited transfer of the exact reviewed zero-call ledger; never a retry."""
    previous_path, path = Path(previous_path).resolve(), Path(path).resolve()
    validate_live_plan(plan)
    validate_authorized_plan(plan)
    rates = validate_pricing_confirmation(plan, pricing_confirmation)
    if previous_path == path or path.exists():
        raise FileExistsError('Recovery requires a new distinct output ledger')
    journal = recovery_journal_path()
    # Same canonical lock as BudgetProvider: an in-flight reservation always wins
    # before this zero-use check, or loses authorization before its lock is released.
    with ledger_lock(previous_path):
        previous_raw = previous_path.read_bytes()
        marker_raw = AUTHORIZATION_PATH.read_bytes()
        previous = json.loads(previous_raw)
        marker = json.loads(marker_raw)
        old_plan = previous['plan']
        if (type(previous.get('calls')) is not list or previous['calls'] != []
            or previous.get('reserved') != '0' or previous.get('halted') is not False
            or previous.get('version') != 2 or previous.get('limit') != '20'
            or previous.get('max_calls') != 6
            or digest(previous_raw) != RECOVERABLE_LEDGER_SHA256
            or digest(marker_raw) != RECOVERABLE_MARKER_SHA256
            or digest(canonical(old_plan)) != RECOVERABLE_PLAN_HASH
            or previous.get('plan_hash') != RECOVERABLE_PLAN_HASH
            or previous.get('config_hash') != digest(canonical(old_plan['config']))
            or previous.get('sources') != old_plan['sources']
            or marker.get('version') != 1 or marker.get('authorization') != 'first-pilot-cny20'
            or marker.get('limit') != '20' or marker.get('plan_hash') != RECOVERABLE_PLAN_HASH
            or marker.get('ledger_path') != str(previous_path)
            or marker.get('token') != previous.get('authorization_token')
            or marker.get('pricing_hash') != digest(canonical(previous['pricing_confirmation']))
            or 'zero_use_recovery' in marker):
            raise RuntimeError('Only the exact reviewed zero-call, zero-reservation authorization can recover')
        ignore = {'config', 'sources', 'labels_sha256'}
        if ({k:v for k,v in old_plan.items() if k not in ignore}
            != {k:v for k,v in plan.items() if k not in ignore}
            or old_plan['config'].get('input_estimate_gate') != 16000
            or plan['config'].get('input_estimate_gate') != 65536
            or {k:v for k,v in old_plan['config'].items() if k != 'input_estimate_gate'}
            != {k:v for k,v in plan['config'].items() if k != 'input_estimate_gate'}):
            raise ValueError('Recovery may change only the reviewed local input gate and source binding')
        with ledger_lock(path):
            if path.exists():
                raise FileExistsError('Recovery output already exists')
            # O_EXCL audit is the one-time recovery claim. Interrupted/partial audits
            # remain on disk and fail closed; there is no automatic reclaim/rollback.
            fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            token = uuid4().hex
            audit = {'version': 1, 'reason': 'approved input-byte-gate correction after zero provider calls',
                     'created_at_utc': datetime.now(timezone.utc).isoformat(),
                     'previous_ledger_path': str(previous_path),
                     'previous_ledger_sha256': digest(previous_raw),
                     'previous_marker_sha256': digest(marker_raw),
                     'previous_ledger': previous, 'previous_authorization': marker,
                     'new_plan_hash': AUTHORIZED_PLAN_HASH, 'new_ledger_path': str(path),
                     'new_token': token}
            save(journal, audit)
            audit_hash = digest(journal.read_bytes())
            new_state = initial_ledger_state(plan, pricing_confirmation, rates, token)
            new_state['recovery_audit_sha256'] = audit_hash
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            save(path, new_state)  # New ledger is durable before transfer of authority.
            replacement = {'version': 1, 'authorization': 'first-pilot-cny20',
                           'plan_hash': AUTHORIZED_PLAN_HASH, 'limit': '20', 'token': token,
                           'pricing_hash': digest(canonical(pricing_confirmation)),
                           'ledger_path': str(path),
                           'zero_use_recovery': {'count': 1, 'audit_sha256': audit_hash}}
            save(AUTHORIZATION_PATH.resolve(), replacement)
    return {'previous_ledger': str(previous_path), 'ledger': str(path),
            'audit': str(journal), 'audit_sha256': audit_hash}


def validate_ledger(state, config):
    try:
        plan = state['plan']
        validate_live_plan(plan)
        rates = validate_pricing_confirmation(plan, state['pricing_confirmation'])
        cost = reserve_cost(config)
        if (state['version'] != 2 or state['plan_hash'] != digest(canonical(plan))
            or state['config_hash'] != digest(canonical(config)) or plan['config'] != config
            or state['confirmed_rates'] != rates or state['limit'] != '20'
            or state['sources'] != plan['sources'] or state['max_calls'] != 6
            or type(state['halted']) is not bool or len(state['calls']) > 6
            or Decimal(state['reserved']) != cost * len(state['calls'])):
            raise ValueError('Ledger policy mismatch')
        counts = {'false': 0, 'true': 0}
        for call in state['calls']:
            if (call['source_id'] not in plan['sources'] or call['arm'] not in counts
                or Decimal(call['reservation_cny']) != cost
                or call['reserved_input_tokens'] != PROVIDER_CONTEXT_TOKENS
                or call['reserved_output_tokens'] != 512
                or call['status'] not in ('reserved', 'response_received', 'outcome_unknown', 'usage_limit_violation')):
                raise ValueError('Invalid reservation record')
            counts[call['arm']] += 1
        if max(counts.values()) > 3:
            raise ValueError('Arm quota exceeded')
        return counts
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise RuntimeError('Budget ledger is invalid or requires review') from exc


class BudgetProvider:
    def __init__(self, path, source_id, config, completion=None, *, arm=False):
        validate_live_config(config)
        if type(arm) is not bool:
            raise ValueError('Explicit Boolean experiment arm required')
        # Pin the canonical ledger, never a caller's symlink or relative spelling.
        self.path = Path(path).resolve()
        self.source_id = source_id
        self.config = dict(config)
        self.completion = completion
        self.arm = str(arm).lower()
        self.calls = 0

    @classmethod
    def from_env(cls, source_id, config, *, arm=False):
        if os.environ.get('LOCAGENT_ALLOW_PAID') != '1':
            raise RuntimeError('Explicit paid execution is disabled')
        if not os.environ.get('DEEPSEEK_API_KEY'):
            raise RuntimeError('Existing DEEPSEEK_API_KEY is unavailable')
        return cls(os.environ['LOCAGENT_BUDGET_LEDGER'], source_id, config, arm=arm)

    def __call__(self, **kwargs):
        config = self.config
        validate_live_config(config)
        if self.calls >= config['max_calls']:
            raise RuntimeError('Per-attempt call limit reached')
        bounded = {'messages': kwargs.get('messages', []), 'tools': kwargs.get('tools', [])}
        estimate = len(canonical(bounded)) + 4096
        if estimate > config['input_estimate_gate']:
            raise RuntimeError('Input exceeds local byte-estimate gate')
        lock_fd = os.open(str(self.path) + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(lock_fd, 'r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.path.read_text())
            validate_authorization(self.path, state)
            counts = validate_ledger(state, config)
            if (state['halted'] or any(c['status'] != 'response_received' for c in state['calls'])
                or self.source_id not in state['sources']
                or len(state['calls']) >= 6 or counts[self.arm] >= 3):
                raise RuntimeError('Experiment is exhausted or needs outcome review')
            cost = reserve_cost(config)
            reserved = Decimal(state['reserved']) + cost
            if reserved > AUTHORIZED_CNY:
                raise RuntimeError('Reservation would exceed authorized budget')
            call = {'source_id': self.source_id, 'arm': self.arm, 'status': 'reserved',
                    'reservation_cny': str(cost), 'reserved_input_tokens': PROVIDER_CONTEXT_TOKENS,
                    'reserved_output_tokens': 512, 'input_byte_estimate': estimate}
            state['calls'].append(call)
            state['reserved'] = str(reserved)
            save(self.path, state)  # Durable full reserve BEFORE the provider can run.
            self.calls += 1
            started = time.monotonic()
            try:
                if self.completion is None:
                    import litellm
                    completion = litellm.completion
                else:
                    completion = self.completion
                # No caller overrides, extra body, retries, parallel completions or fallbacks.
                forwarded = {k: v for k, v in kwargs.items() if k in ('messages', 'tools', 'tool_choice', 'stop')}
                response = completion(**forwarded, model=config['model'],
                    api_base=config['api_base'], api_key=os.environ.get('DEEPSEEK_API_KEY'),
                    temperature=0, max_tokens=512, extra_body={'thinking': {'type': 'disabled'}},
                    timeout=60, num_retries=0, stream=False)
                usage = response.usage
                pt, ct = usage.prompt_tokens, usage.completion_tokens
                valid = type(pt) is int and type(ct) is int and pt >= 0 and ct >= 0
                call.update(status='response_received', returned_model=response.model,
                            elapsed_seconds=time.monotonic() - started)
                if valid:
                    call.update(prompt_tokens=pt, completion_tokens=ct,
                        cost_upper_cny=str((pt * INPUT_CNY + ct * OUTPUT_CNY) / Decimal(1000000)))
                if not valid or pt > PROVIDER_CONTEXT_TOKENS or ct > 512:
                    state['halted'] = True
                    call['status'] = 'usage_limit_violation'
                call['response'] = response.model_dump(mode='json')
                save(self.path, state)
                if state['halted']:
                    raise RuntimeError('Provider usage violates the reviewed bounds')
                return response
            except BaseException:
                if call['status'] == 'reserved':
                    call.update(status='outcome_unknown', elapsed_seconds=time.monotonic() - started)
                state['halted'] = True
                save(self.path, state)
                raise
