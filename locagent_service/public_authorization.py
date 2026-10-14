"""Operator-owned, single-task public-repository experiments. No implicit approval.

Reuse legacy durable locks/writes and immutable raw-response storage; never reuse
historical authorization markers, budget amounts, model names or ledger paths.
"""
import argparse
from decimal import Decimal, InvalidOperation, localcontext
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from locagent_service import budget, response_store
from locagent_service.followup import raw_json
from locagent_service.public_repo import PinnedHTTPS, normalize_url
from locagent_service.sources import canonical, digest, load_manifest, registry

POLICY = 'public-single-task-budget-v1'


class AuthorizationError(ValueError):
    """Public message must not disclose operator configuration or credentials."""


def money(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,30}(?:\.[0-9]{1,30})?', value):
        raise ValueError('Finite nonnegative decimal string required')
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError('Invalid decimal') from None
    if not result.is_finite():
        raise ValueError('Invalid decimal')
    return result


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    endpoint: str
    model: str = Field(min_length=1, max_length=128)
    response_models: list[str] = Field(min_length=1, max_length=16)
    credential_env: str = Field(pattern=r'^[A-Z][A-Z0-9_]{2,63}$')
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    input_per_million: str
    output_per_million: str
    budget: str
    # Reserve the approved full context, not a heuristic estimate of the prompt.
    context_tokens: int = Field(ge=1, le=2000000)
    output_tokens: int = Field(ge=1, le=32768)
    max_calls: int = Field(ge=1, le=12)
    request_bytes: int = Field(ge=1024, le=1024 * 1024)
    timeout_seconds: int = Field(ge=1, le=60)
    pricing_confirmation: str = Field(min_length=1, max_length=2000)

    @field_validator('endpoint')
    @classmethod
    def https_endpoint(cls, value):
        parts = urlsplit(value)
        if (parts.scheme != 'https' or not parts.hostname or parts.netloc != parts.hostname
                or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}', parts.hostname)
                or parts.hostname.endswith(('.local', '.localhost', '.internal'))
                or parts.query or parts.fragment or not parts.path.startswith('/')
                or not re.fullmatch(r'/[A-Za-z0-9/_-]+', parts.path)):
            raise ValueError('Canonical public HTTPS endpoint required')
        return value

    @model_validator(mode='after')
    def bounds(self):
        for value in (self.budget, self.input_per_million, self.output_per_million):
            if not re.fullmatch(r'[0-9]{1,12}(?:\.[0-9]{1,12})?', value):
                raise ValueError('Operator prices require bounded decimal strings')
        if (self.output_tokens > self.context_tokens or not self.model.strip()
                or any(not isinstance(m, str) or not 0 < len(m) <= 128 for m in self.response_models)
                or len(set(self.response_models)) != len(self.response_models)
                or money(self.budget) <= 0 or money(self.input_per_million) <= 0
                or money(self.output_per_million) <= 0 or reserve(self.model_dump()) > money(self.budget)):
            raise ValueError('Invalid price, quota or reservation bounds')
        return self


def reserve(config):
    with localcontext() as context:
        context.prec = 64
        return (config['context_tokens'] * money(config['input_per_million']) +
                config['output_tokens'] * money(config['output_per_million'])) / Decimal(1000000)


def add(*values):
    with localcontext() as context:
        context.prec = 64
        return sum(values, Decimal(0))


def private(path, *, directory=False):
    info = path.lstat()
    if (path.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077
            or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))):
        raise AuthorizationError('Authorization storage must be private and operator-owned')


def authority_root(*, create=False):
    value = os.environ.get('LOCAGENT_PUBLIC_AUTH_ROOT', '')
    path = Path(value)
    if not value or not path.is_absolute() or path != path.resolve():
        raise AuthorizationError('Explicit canonical authorization root required')
    if path == registry() or path.is_relative_to(registry()) or registry().is_relative_to(path):
        raise AuthorizationError('Authorization and source storage must be separate')
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    private(path, directory=True)
    return path


def read_json(path):
    private(path)
    if path.stat().st_size > response_store.MAX_JSON_BYTES:
        raise AuthorizationError('Authorization data is oversized')
    return raw_json(path.read_bytes())


def binding(manifest, suppress_repeats):
    task = manifest['task']
    return {'repository_url': normalize_url('https://github.com/' + task['repo']),
            'commit': task['base_commit'], 'problem_sha256': digest(task['problem_statement'].encode()),
            'max_iterations': manifest['config']['max_calls'], 'suppress_repeats': suppress_repeats}


def make_plan(source_id, config, *, suppress_repeats=True):
    """Offline preparation only. Produces a live-bound manifest but grants no authority."""
    config = ProviderConfig.model_validate(config).model_dump()
    if type(suppress_repeats) is not bool:
        raise ValueError('Boolean suppression option required')
    manifest, _ = load_manifest(source_id)
    if (manifest['config'].get('provider') != 'fake-only'
            or not re.fullmatch(r'[0-9a-f]{40}', manifest['task']['base_commit'])):
        raise AuthorizationError('Verified public preview source required')
    from locagent_service.engine_binding import behavior_hashes
    if manifest['engine'] != behavior_hashes(Path(__file__).resolve().parents[1]):
        raise AuthorizationError('Complete current engine binding required')
    derived = {**manifest, 'parent_source_id': source_id, 'config': {
        **manifest['config'], 'provider': POLICY, 'model': config['model'],
        'provider_endpoint': config['endpoint'], 'max_calls': config['max_calls']}}
    from locagent_service.public_pipeline import publish
    data = canonical(derived)
    source = 'prepared-' + digest(data)
    publish(registry() / (source + '.json'), data)
    plan = {'version': 1, 'policy': POLICY, 'authority_root': str(authority_root(create=True)),
            'source_id': source, 'provider': config, 'binding': binding(derived, suppress_repeats)}
    validate_plan(plan)
    return plan


def validate_plan(plan):
    if (not isinstance(plan, dict) or set(plan) != {
            'version', 'policy', 'authority_root', 'source_id', 'provider', 'binding'}
            or type(plan['version']) is not int or plan['version'] != 1 or plan['policy'] != POLICY
            or plan['authority_root'] != str(authority_root())):
        raise AuthorizationError('Invalid or relocated operator plan')
    config = ProviderConfig.model_validate(plan['provider']).model_dump()
    manifest, _ = load_manifest(plan['source_id'])
    from locagent_service.engine_binding import behavior_hashes
    if (manifest['engine'] != behavior_hashes(Path(__file__).resolve().parents[1])
            or manifest['config'].get('provider') != POLICY
            or manifest['config']['model'] != config['model']
            or manifest['config'].get('provider_endpoint') != config['endpoint']
            or manifest['config']['max_calls'] != config['max_calls']
            or type(plan['binding'].get('suppress_repeats')) is not bool
            or plan['binding'] != binding(manifest, plan['binding']['suppress_repeats'])):
        raise AuthorizationError('Plan/source/request binding changed')
    return manifest


def authorize(plan, expected_hash):
    """Explicit operator command. Exclusive directory is a permanent consumed marker."""
    validate_plan(plan)
    identity = digest(canonical(plan))
    if identity != expected_hash:
        raise AuthorizationError('Operator-confirmed plan hash differs')
    directory = authority_root() / identity
    directory.mkdir(mode=0o700)  # Existing OR interrupted initialization never resets.
    fd = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    token = uuid4().hex
    path = directory / 'ledger.json'
    response_store.save_json(directory / 'authorization.json', {
        'plan': plan, 'plan_hash': identity, 'token': token, 'ledger_path': str(path)})
    response_store.save_json(path, {'version': 1, 'plan_hash': identity, 'token': token,
        'task_id': None, 'claim_token': None, 'halted': False, 'finished': False,
        'spent': '0', 'reserved': '0', 'calls': []})
    return identity


def grant(identity, *, require_enabled=True):
    if require_enabled and os.environ.get('LOCAGENT_PUBLIC_LIVE') != '1':
        raise AuthorizationError('Operator live execution is disabled')
    if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{64}', identity):
        raise AuthorizationError('Invalid authorization identity')
    directory = authority_root() / identity
    private(directory, directory=True)
    marker = read_json(directory / 'authorization.json')
    if (marker.get('plan_hash') != identity or digest(canonical(marker['plan'])) != identity
            or marker['ledger_path'] != str(directory / 'ledger.json')):
        raise AuthorizationError('Authorization identity/path mismatch')
    manifest = validate_plan(marker['plan'])
    return marker, manifest


def validate_request(request):
    marker, manifest = grant(request.authorization_id)
    actual = {'repository_url': request.repository_url, 'commit': request.ref,
        'problem_sha256': digest(request.problem_statement.encode()),
        'max_iterations': request.options.max_iterations,
        'suppress_repeats': request.options.suppress_repeats}
    if (request.source_id != 'github-v1' or request.max_attempts != 1
            or actual != marker['plan']['binding']):
        raise AuthorizationError('Request differs from operator-approved experiment')
    return marker, manifest


def usage(body, config):
    raw = raw_json(body)
    counters = raw['usage']
    names = ('prompt_tokens', 'completion_tokens', 'total_tokens')
    if not isinstance(counters, dict) or any(type(counters.get(k)) is not int for k in names):
        raise ValueError('Original integer usage is required')
    pt, ct, total = (counters[k] for k in names)
    if (not 0 < pt <= config['context_tokens'] or not 0 <= ct <= config['output_tokens']
            or total != pt + ct or raw.get('model') not in config['response_models']
            or not isinstance(raw.get('id'), str) or not raw['id']
            or not isinstance(raw.get('choices'), list) or len(raw['choices']) != 1
            or raw['choices'][0].get('finish_reason') not in ('stop', 'tool_calls', 'length')
            or not isinstance(raw['choices'][0].get('message'), dict)):
        raise ValueError('Usage/model/completion does not match approved limits')
    # Charge all prompt tokens at approved peak price, irrespective of cache discounts.
    with localcontext() as context:
        context.prec = 64
        cost = (pt * money(config['input_per_million']) + ct * money(config['output_per_million'])) / Decimal(1000000)
    return raw, {k: counters[k] for k in names}, cost


def totals(state, config):
    with localcontext() as context:
        context.prec = 64
        spent = sum((money(c['cost']) for c in state['calls'] if c['status'] == 'settled'), Decimal(0))
        pending = sum((reserve(config) for c in state['calls'] if c['status'] != 'settled'), Decimal(0))
    return spent, pending


def validate_state(path, state, marker):
    config = marker['plan']['provider']
    if (state.get('version') != 1 or state.get('plan_hash') != marker['plan_hash']
            or state.get('token') != marker['token'] or type(state.get('halted')) is not bool
            or type(state.get('finished')) is not bool or not isinstance(state.get('calls'), list)
            or len(state['calls']) > config['max_calls']):
        raise AuthorizationError('Ledger identity/quota is invalid')
    for i, call in enumerate(state['calls']):
        if (call.get('index') != i or call.get('status') not in ('reserved', 'raw_received', 'settled', 'outcome_unknown')
                or call.get('reservation') != format(reserve(config), 'f')):
            raise AuthorizationError('Ledger call is invalid')
        if call['status'] == 'settled':
            _, counters, cost = usage(response_store.read(path, i, call['raw']), config)
            if money(call['cost']) != cost or call['usage'] != counters:
                raise AuthorizationError('Settlement differs from durable raw response')
    spent, pending = totals(state, config)
    if money(state['spent']) != spent or money(state['reserved']) != pending or add(spent, pending) > money(config['budget']):
        raise AuthorizationError('Ledger totals are invalid')


def request_payload(config, kwargs):
    # Reuse the established role/metadata filter without its historical endpoint/model.
    from locagent_service.deepseek_http import payload
    value = payload(**kwargs)
    value.pop('thinking', None)
    value.update(model=config['model'], max_tokens=config['output_tokens'])
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
    if len(data) > config['request_bytes']:
        raise AuthorizationError('Request exceeds approved byte limit')
    return data


def exchange(config, data, capacity):
    """Future real transport. Called only AFTER authorization, fencing and reserve.

    No dotenv/config secret reads; a future operator explicitly supplies one
    credential environment variable. Tests inject raw_completion and never enter here.
    """
    from locagent_service.deepseek_http import RawHTTP
    key = os.environ.get(config['credential_env'])
    if not key:
        raise AuthorizationError('Approved credential is unavailable')
    parts = urlsplit(config['endpoint'])
    connection = PinnedHTTPS(parts.hostname, timeout=config['timeout_seconds'])
    try:
        connection.request('POST', parts.path, body=data, headers={
            'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        result = connection.getresponse()
        body = bytearray()
        try:
            while len(body) <= capacity:
                chunk = result.read1(min(65536, capacity + 1 - len(body)))
                if not chunk:
                    length = result.getheader('Content-Length')
                    complete = length is None or (length.isdigit() and len(body) == int(length))
                    return RawHTTP(result.status, bytes(body), complete, None if complete else 'IncompleteBody')
                body.extend(chunk)
            return RawHTTP(result.status, bytes(body[:capacity]), False, 'ResponseTooLarge')
        except Exception as exc:
            partial = getattr(exc, 'partial', b'')
            if isinstance(partial, bytes):
                body.extend(partial[:max(0, capacity-len(body))])
            return RawHTTP(result.status, bytes(body[:capacity]), False, type(exc).__name__)
    finally:
        connection.close()


class AuthorizedProvider:
    def __init__(self, request, claim, report, *, raw_completion=None):
        marker, _ = validate_request(request)
        self.request, self.claim, self.report = request, claim, report
        self.identity = request.authorization_id
        self.path = Path(marker['ledger_path'])
        self.raw_completion = raw_completion or exchange
        self.next_index = 0
        with budget.ledger_lock(self.path):
            marker, _ = validate_request(request)
            state = read_json(self.path)
            validate_state(self.path, state, marker)
            # Bind only once. Even a second executor of the same task is forbidden.
            if state['task_id'] is not None or state['calls'] or state['halted'] or state['finished']:
                raise AuthorizationError('Experiment is already consumed or requires review')
            report({'stage': 'authorizing'})
            state.update(task_id=str(claim.id), claim_token=str(claim.token))
            response_store.save_json(self.path, state)

    def __call__(self, **kwargs):
        with budget.ledger_lock(self.path):
            marker, _ = validate_request(self.request)
            config = marker['plan']['provider']
            state = read_json(self.path)
            validate_state(self.path, state, marker)
            guard = self.path.with_name('inflight.json')
            if (state['task_id'] != str(self.claim.id) or state['claim_token'] != str(self.claim.token)
                    or state['halted'] or state['finished'] or guard.exists() or guard.is_symlink()
                    or len(state['calls']) != self.next_index or any(c['status'] != 'settled' for c in state['calls'])
                    or len(state['calls']) >= config['max_calls']):
                raise AuthorizationError('No fresh authorized call is available')
            data = request_payload(config, kwargs)
            capacity = response_store.capacity(self.path)
            if capacity < response_store.MAX_BODY_BYTES:
                raise AuthorizationError('Insufficient durable response capacity')
            spent, pending = totals(state, config)
            if add(spent, pending, reserve(config)) > money(config['budget']):
                raise AuthorizationError('Full next reservation exceeds approved budget')
            self.report({'stage': 'reserving', 'authorization_id': self.identity})
            call = {'index': len(state['calls']), 'status': 'reserved', 'reservation': format(reserve(config), 'f'),
                    'request_sha256': digest(data)}
            state['calls'].append(call)
            state['reserved'] = format(add(pending, reserve(config)), 'f')
            response_store.save_json(self.path, state)
            try:
                fd = os.open(guard, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
                budget.save(guard, {'index': call['index']})
                # Recheck authorization + DB claim after any lock/persistence delay.
                validate_request(self.request)
                self.report({'stage': 'provider_inflight', 'authorization_id': self.identity})
                response = self.raw_completion(config, data, capacity)
                call['raw'] = response_store.persist(self.path, call['index'], response.body)
                call.update(status='raw_received', http_status=response.status, complete=response.complete)
                response_store.save_json(self.path, state)
                if response.status != 200 or not response.complete:
                    raise ValueError('Remote outcome requires review')
                raw, counters, cost = usage(response.body, config)
                from litellm import ModelResponse
                normalized = ModelResponse(**raw)
                call.update(status='settled', usage=counters, cost=format(cost, 'f'))
                state['spent'], state['reserved'] = (format(value, 'f') for value in totals(state, config))
                response_store.save_json(self.path, state)
                guard.unlink()
                directory_fd = os.open(guard.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                self.next_index += 1
                return normalized
            except BaseException:
                call['status'] = 'outcome_unknown'
                state['halted'] = True
                state['spent'], state['reserved'] = (format(value, 'f') for value in totals(state, config))
                try:
                    response_store.save_json(self.path, state)
                except OSError:
                    pass  # Pre-call durable reservation and consumed grant still stop replay.
                raise

    def finish(self):
        with budget.ledger_lock(self.path):
            marker, _ = validate_request(self.request)
            state = read_json(self.path)
            validate_state(self.path, state, marker)
            if (state['task_id'] != str(self.claim.id) or state['claim_token'] != str(self.claim.token)
                    or state['finished'] or state['halted'] or self.path.with_name('inflight.json').exists()
                    or len(state['calls']) != self.next_index
                    or any(c['status'] != 'settled' for c in state['calls'])):
                raise AuthorizationError('Experiment needs outcome review')
            self.report({'stage': 'settled'})
            state['finished'] = True
            response_store.save_json(self.path, state)


def localize_authorized(request, channel, report):
    marker, _ = validate_request(request)
    from locagent_service.models import CreateTask
    from locagent_service.sources import localize_prepared
    from locagent_service.offline import offline_engine
    # Import optional engine libraries with network guards; transport only runs
    # later, after the exact grant and durable reservation have been checked.
    with offline_engine():
        import litellm
    source = marker['plan']['source_id']
    report(stage='localizing', source_id=source, commit=request.ref)
    provider = AuthorizedProvider(request, channel.claim, lambda values: report(**values))
    prepared = CreateTask(source_id=source, problem_statement=request.problem_statement,
                          options=request.options, max_attempts=1)
    result = localize_prepared(prepared, provider)
    provider.finish()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    plan_cmd = commands.add_parser('plan')
    plan_cmd.add_argument('--source', required=True)
    plan_cmd.add_argument('--provider-config', required=True)
    plan_cmd.add_argument('--output', required=True)
    plan_cmd.add_argument('--no-suppress-repeats', action='store_true')
    auth_cmd = commands.add_parser('authorize')
    auth_cmd.add_argument('--plan', required=True)
    auth_cmd.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    if args.command == 'plan':
        plan = make_plan(args.source, raw_json(Path(args.provider_config).read_bytes()),
                         suppress_repeats=not args.no_suppress_repeats)
        # A proposed plan is not a grant, and never overwrites existing output.
        with Path(args.output).open('x') as stream:
            json.dump(plan, stream, indent=2)
        print(json.dumps({'plan_sha256': digest(canonical(plan)), 'authorized': False}))
    else:
        identity = authorize(raw_json(Path(args.plan).read_bytes()), args.expected_sha256)
        print(json.dumps({'authorization_id': identity, 'enables_live_execution': False}))


if __name__ == '__main__':
    main()
