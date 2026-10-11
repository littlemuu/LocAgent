"""Five fixed follow-up samples; raw HTTP usage settlement with fail-closed accounting."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from locagent_service import budget as legacy
from locagent_service.sources import canonical, digest, load_manifest

POLICY = 'locagent-followup5-v1'
REVISION = '6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2'
COMMITS = {
    'psf__requests-1963': '110048f9837f8441ea536804115e80b69f400277',
    'psf__requests-2148': 'fe693c492242ae532211e0c173324f09ca8cf227',
    'psf__requests-2317': '091991be0da19de9108dbe5e3752917fea3d7fdc',
    'psf__requests-2674': '0be38a0c37c59c4b66ce908731da15b401655113',
    'psf__requests-863': 'a0df2cbb10419037d11d04352b3175405ab52941',
}
ORDER = sorted(COMMITS, key=lambda name: digest((POLICY + '\n' + name).encode()))
LIMIT = Decimal('5')
RESERVE = Decimal('2.101248')
AUTHORIZATION_PATH = (Path(__file__).resolve().parents[1] /
                      'outputs/stage4/authorizations/followup5-cny5.json')
# Human approval and independent review completed for this exact fixed plan.
# No CLI/environment override; every other plan remains blocked.
APPROVED_PLAN_HASH = 'c94baaa9a06d775d6022cf14a643b4962c440f8dd8d44d5f86eb80da15877660'
# A distinct human-approved round; kept disabled until its independent preflight passes.
BOUNDED_EXPERIMENT = 'bounded5-20261009'
BOUNDED_PLAN_HASH = '1fb5b84b25ef43ef27f71b28a9e56f19321b8361f7a139aee69d0b5cd9e710e8'
BOUNDED_AUTHORIZATION_PATH = (Path(__file__).resolve().parents[1] /
                              'outputs/stage4/authorizations/bounded5-20261009-cny5.json')

BASIS = {'input_tokens_per_call': 1048576, 'output_tokens_per_call': 512,
         'input_cny_per_million': '2', 'output_cny_per_million': '8',
         'settlement': 'durable_raw_http_usage_all_input_cache_miss',
         'unknown': 'retain_full_reservation_and_stop'}


def arm_order(index):
    return [False, True] if index % 2 == 0 else [True, False]


def validate_config(config):
    legacy.validate_live_config(config)
    if config.get('budget_policy') != POLICY:
        raise ValueError('Fixed follow-up policy required')


def validate_plan(plan):
    validate_config(plan['config'])
    samples = plan.get('samples', [])
    if (type(plan.get('version')) is not int or plan['version'] != 3
        or plan.get('policy') != POLICY or plan.get('dataset_revision') != REVISION
        or canonical(plan.get('arms')) != canonical([False, True])
        or type(plan.get('denominator_per_arm')) is not int or plan['denominator_per_arm'] != 5
        or type(plan.get('max_calls')) is not int or plan['max_calls'] != 30
        or type(plan.get('budget_cny')) is not int or plan['budget_cny'] != 5
        or canonical(plan.get('reservation_basis')) != canonical(BASIS)
        or not isinstance(plan.get('sources'), list) or len(plan['sources']) != 5
        or len(set(plan['sources'])) != 5 or len(samples) != 5):
        raise ValueError('Only the fixed five-sample/30-call/CNY5 plan is supported')
    for i, sample in enumerate(samples):
        if (sample.get('instance_id') != ORDER[i]
            or sample.get('base_commit') != COMMITS[ORDER[i]]
            or sample.get('source_id') != plan['sources'][i]
            or canonical(sample.get('arm_order')) != canonical(arm_order(i))):
            raise ValueError('Sample identity/order/commit/arm order changed')


def make_plan(sources, labels, output):
    manifests = {}
    for source in sources:
        manifest, _ = load_manifest(source)
        manifests[manifest['task']['instance_id']] = (source, manifest)
    if len(sources) != 5 or set(manifests) != set(ORDER):
        raise ValueError('Exactly the five frozen follow-up samples are required')
    ordered = [manifests[n] for n in ORDER]
    answers = json.loads(Path(labels).read_text())
    if set(answers) != {s for s, _ in ordered}:
        raise ValueError('Labels must match exactly the frozen sources')
    config = ordered[0][1]['config']
    for name, (source, m) in zip(ORDER, ordered):
        if (m['task']['repo'] != 'psf/requests' or m['task']['base_commit'] != COMMITS[name]
            or m['dataset']['dataset_revision'] != REVISION or m['config'] != config
            or not answers[source].get('files') or not answers[source].get('entities')):
            raise ValueError('Frozen sources/configuration/labels mismatch')
    plan = {'version': 3, 'policy': POLICY, 'dataset_revision': REVISION,
            'sources': [s for s, _ in ordered], 'arms': [False, True],
            'samples': [{'instance_id': n, 'base_commit': COMMITS[n], 'source_id': s,
                         'arm_order': arm_order(i)}
                        for i, (n, (s, _)) in enumerate(zip(ORDER, ordered))],
            'config': config, 'labels_sha256': digest(Path(labels).read_bytes()),
            'denominator_per_arm': 5, 'max_calls': 30, 'budget_cny': 5,
            'reservation_basis': BASIS,
            'sample_role': 'fixed follow-up cohort; previous pilot excluded',
            'metric': 'file/entity recall@1 and @3; failures/missing count as zero'}
    validate_plan(plan)
    with Path(output).open('x') as stream:
        json.dump(plan, stream, indent=2)
    return plan


def validate_pricing(plan, confirmation):
    validate_plan(plan)
    rates = legacy.validate_pricing_confirmation(plan, confirmation)
    if (confirmation['currency'] != 'CNY'
        or Decimal(rates['input_cny_per_million']) != 2
        or Decimal(rates['output_cny_per_million']) != 8):
        raise ValueError('Confirmed official all-in CNY peak rates 2/8 required')
    return rates


def authorization_scope(plan):
    plan_hash = digest(canonical(plan))
    if APPROVED_PLAN_HASH is not None and plan_hash == APPROVED_PLAN_HASH:
        return APPROVED_PLAN_HASH, AUTHORIZATION_PATH
    if (BOUNDED_PLAN_HASH is not None and plan_hash == BOUNDED_PLAN_HASH
        and plan.get('experiment_id') == BOUNDED_EXPERIMENT
        and plan.get('config', {}).get('search_protocol') == 'bounded-v1'):
        return BOUNDED_PLAN_HASH, BOUNDED_AUTHORIZATION_PATH
    raise ValueError('Follow-up approval and independent review are not yet pinned')


def require_approval(plan):
    authorization_scope(plan)


def load_live_pricing(plan, path):
    validate_plan(plan)
    require_approval(plan)
    if path is None:
        raise ValueError('Fresh plan-bound pricing confirmation required')
    confirmation = json.loads(Path(path).read_text())
    validate_pricing(plan, confirmation)
    return confirmation


def initialize_ledger(path, plan, confirmation):
    path = Path(path).resolve()
    validate_pricing(plan, confirmation)
    require_approval(plan)
    if path.exists():
        raise FileExistsError('Ledger already exists')
    approved_hash, marker = authorization_scope(plan)
    marker.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)  # Partial initialization also consumes this separate approval.
    token = uuid4().hex
    legacy.save(marker, {'policy': POLICY, 'limit': '5', 'plan_hash': approved_hash,
                        'ledger_path': str(path), 'token': token,
                        'pricing_hash': digest(canonical(confirmation))})
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    legacy.save(path, {'version': 3, 'plan': plan, 'plan_hash': digest(canonical(plan)),
                      'authorization_token': token, 'pricing_confirmation': confirmation,
                      'spent_cny': '0', 'reserved': '0', 'halted': False, 'calls': []})


def validate_authorization(path, state):
    approved_hash, marker_path = authorization_scope(state['plan'])
    marker = json.loads(marker_path.read_text())
    expected = {'policy': POLICY, 'limit': '5', 'plan_hash': approved_hash,
                'ledger_path': str(Path(path).resolve()), 'token': state['authorization_token'],
                'pricing_hash': digest(canonical(state['pricing_confirmation']))}
    if marker != expected:
        raise RuntimeError('Separate follow-up authorization does not match ledger owner')


def raw_json(body):
    if not isinstance(body, bytes) or len(body) > 8 * 1024 * 1024:
        raise ValueError('Bounded original HTTP response bytes required')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate raw JSON field')
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError('Non-finite JSON constant')
    return json.loads(body.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=invalid_constant)


def verify_raw_usage(body):
    raw = raw_json(body)
    usage = raw['usage']
    fields = ('prompt_tokens', 'completion_tokens', 'total_tokens',
              'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')
    if not isinstance(usage, dict) or any(type(usage.get(k)) is not int for k in fields):
        raise ValueError('All original provider usage fields are required; no synthetic defaults')
    pt, ct, total, hit, miss = (usage[k] for k in fields)
    if (not 0 < pt <= 1048576 or not 0 <= ct <= 512 or min(hit, miss) < 0
        or pt != hit + miss or total != pt + ct):
        raise ValueError('Inconsistent or out-of-bound raw provider usage')
    if (not isinstance(raw.get('id'), str) or not raw['id']
        or raw.get('model') not in ('deepseek-flash', 'deepseek-v4-flash', 'deepseek-v4.1-flash')
        or not isinstance(raw.get('choices'), list) or len(raw['choices']) != 1
        or raw['choices'][0].get('finish_reason') not in ('stop', 'tool_calls', 'length')
        or not isinstance(raw['choices'][0].get('message'), dict)):
        raise ValueError('Incomplete/unexpected raw completion')
    cost = (pt * Decimal(2) + ct * Decimal(8)) / Decimal(1000000)
    return raw, {k: usage[k] for k in fields}, cost


def totals(state):
    settled = sum((Decimal(c['cost_upper_cny']) for c in state['calls']
                   if c['status'] == 'settled'), Decimal(0))
    pending = sum((RESERVE for c in state['calls'] if c['status'] != 'settled'), Decimal(0))
    return settled, pending


def validate_ledger(state, config):
    plan = state['plan']
    validate_plan(plan)
    validate_pricing(plan, state['pricing_confirmation'])
    if (state.get('version') != 3 or state.get('plan_hash') != digest(canonical(plan))
        or config != plan['config'] or type(state.get('halted')) is not bool
        or not isinstance(state.get('calls'), list) or len(state['calls']) > 30):
        raise ValueError('Invalid follow-up ledger')
    counts = {(source, str(arm).lower()): 0 for source in plan['sources'] for arm in plan['arms']}
    for i, call in enumerate(state['calls']):
        key = (call['source_id'], call['arm'])
        if (key not in counts or call['index'] != i or call['reservation_cny'] != str(RESERVE)
            or call['status'] not in ('reserved', 'raw_received', 'settled', 'outcome_unknown')):
            raise ValueError('Invalid call identity/reservation/status')
        counts[key] += 1
        if call['status'] == 'settled':
            body = call['raw_body_utf8'].encode('utf-8')
            _, usage, cost = verify_raw_usage(body)
            if (digest(body) != call['raw_body_sha256'] or any(call.get(k) != v for k, v in usage.items())
                or Decimal(call['cost_upper_cny']) != cost):
                raise ValueError('Settled amount differs from durable original usage')
    spent, reserved = totals(state)
    if (max(counts.values()) > 3 or Decimal(state['spent_cny']) != spent
        or Decimal(state['reserved']) != reserved or spent + reserved > LIMIT):
        raise ValueError('Ledger totals/quota violate budget')
    return counts


def request_raw(**kwargs):
    """Official HTTPS only, no redirects, no retries; preserve HTTP bytes before SDK conversion."""
    if os.environ.get('LOCAGENT_ALLOW_PAID') != '1' or not os.environ.get('DEEPSEEK_API_KEY'):
        raise RuntimeError('Explicit paid execution and existing key required')
    from locagent_service import deepseek_http
    payload = deepseek_http.payload(**kwargs)
    with deepseek_http.client() as client:
        response = client.post(deepseek_http.ENDPOINT,
                               headers={'Authorization': 'Bearer ' + os.environ['DEEPSEEK_API_KEY']},
                               json=payload)
        if response.status_code != 200:
            raise RuntimeError('Provider HTTP failure; outcome requires review')
        return response.content


class SettlingBudgetProvider:
    def __init__(self, path, source_id, config, raw_completion=None, *, arm=False):
        validate_config(config)
        if type(arm) is not bool:
            raise ValueError('Boolean arm required')
        self.path, self.source_id, self.config = Path(path).resolve(), source_id, dict(config)
        self.arm = str(arm).lower()
        self.raw_completion = raw_completion or request_raw

    @classmethod
    def from_env(cls, source_id, config, *, arm=False):
        if os.environ.get('LOCAGENT_ALLOW_PAID') != '1' or not os.environ.get('DEEPSEEK_API_KEY'):
            raise RuntimeError('Explicit paid execution and existing key required')
        return cls(os.environ['LOCAGENT_BUDGET_LEDGER'], source_id, config, arm=arm)

    def __call__(self, **kwargs):
        bounded = {k: kwargs[k] for k in ('messages', 'tools', 'tool_choice', 'stop') if k in kwargs}
        estimate = len(canonical(bounded)) + 4096
        if estimate > self.config['input_estimate_gate']:
            raise RuntimeError('Input exceeds local byte-estimate gate')
        guard = self.path.with_name(self.path.name + '.inflight')
        with legacy.ledger_lock(self.path):
            state = json.loads(self.path.read_text())
            validate_authorization(self.path, state)
            counts = validate_ledger(state, self.config)
            key = (self.source_id, self.arm)
            if (guard.exists() or guard.is_symlink() or state['halted']
                or any(c['status'] != 'settled' for c in state['calls'])
                or key not in counts or counts[key] >= 3 or len(state['calls']) >= 30):
                raise RuntimeError('Budget exhausted or previous outcome requires review')
            spent, pending = totals(state)
            if spent + pending + RESERVE > LIMIT:
                state.update(halted=True, stop_reason='budget_exhausted')
                legacy.save(self.path, state)
                raise RuntimeError('Full next reservation would exceed CNY5')
            call = {'index': len(state['calls']), 'source_id': self.source_id, 'arm': self.arm,
                    'status': 'reserved', 'reservation_cny': str(RESERVE),
                    'input_byte_estimate': estimate}
            state['calls'].append(call)
            state['reserved'] = str(pending + RESERVE)
            legacy.save(self.path, state)
            # Survives every uncertain persistence/network/conversion outcome.
            fd = os.open(guard, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            legacy.save(guard, {'call_index': call['index']})
            started = time.monotonic()
            try:
                body = self.raw_completion(**bounded)
                if not isinstance(body, bytes):
                    raise ValueError('Original HTTP bytes required, not normalized SDK objects')
                call.update(status='raw_received', raw_body_utf8=body.decode('utf-8'),
                            raw_body_sha256=digest(body), elapsed_seconds=time.monotonic()-started)
                legacy.save(self.path, state)  # Full raw response durable before ANY release.
                raw, usage, cost = verify_raw_usage(body)
                from litellm import ModelResponse
                response = ModelResponse(**raw)  # Normalize only AFTER raw validation.
                call.update(usage, status='settled', cost_upper_cny=str(cost),
                            returned_model=raw['model'])
                state['spent_cny'], state['reserved'] = map(str, totals(state))
                legacy.save(self.path, state)  # Settlement durable before next request.
                guard.unlink()
                fd = os.open(guard.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
                return response
            except BaseException as exc:
                call.update(status='outcome_unknown', exception_type=type(exc).__name__,
                            elapsed_seconds=time.monotonic()-started)
                state.update(halted=True, stop_reason='outcome_requires_review')
                state['spent_cny'], state['reserved'] = map(str, totals(state))
                try:
                    legacy.save(self.path, state)
                except OSError:
                    pass  # Durable pre-call reserve + guard still forbid automatic replay.
                raise
