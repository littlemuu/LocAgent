"""Operator-confirmed, one-use grants. No key access and no implicit approval."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from .core import digest, encoded, runtime_identity
from .preparation import engine_binding

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / 'authority'


def now():
    return datetime.now(timezone.utc)


def private(path, directory=False):
    p = Path(path)
    info = p.lstat()
    if (p != p.resolve() or info.st_uid != os.getuid() or info.st_mode & 0o077
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise PermissionError('private_canonical_owner_storage_required')


def save_new(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def current_plan(plan):
    from .deepseek_wire import CONTEXT, ENDPOINT, INPUT_RATE, MODEL, OUTPUT, OUTPUT_RATE, RESERVATION
    from .core import Limits
    from .openhands_replay import SDK_SYSTEM
    from .control import POLICY
    required = {'endpoint': ENDPOINT, 'model': MODEL, 'context_tokens': CONTEXT,
                'max_output_tokens': OUTPUT, 'max_requests_per_arm': 4, 'max_requests_total': 8,
                'budget_micro_cny': 17000000, 'reservation_micro_cny': RESERVATION,
                'input_peak_cache_miss_cny_per_million': INPUT_RATE,
                'output_peak_cny_per_million': OUTPUT_RATE, 'currency': 'CNY',
                'sdk_version': '1.62.0', 'system_hash': digest(SDK_SYSTEM),
                'limits': Limits(max_requests=4).__dict__, 'arms': ['baseline', 'retrieval'],
                'controller_policy': POLICY}
    for key, value in required.items():
        if type(plan.get(key)) is not type(value) or plan[key] != value:
            raise PermissionError('approved_plan_policy_mismatch')
    lock = Path(__file__).parent.parent / 'requirements-openhands.lock'
    if (plan['runtime_hash'] != runtime_identity()
            or plan['dependency_lock_sha256'] != hashlib.sha256(lock.read_bytes()).hexdigest()
            or not plan.get('locagent_engine')
            or plan['locagent_engine'] != engine_binding(plan['locagent_engine']['root'])):
        raise PermissionError('approved_code_or_engine_changed')


class Authority:
    def __init__(self, root=DEFAULT_ROOT):
        self.root = Path(root).absolute()
        if self.root != self.root.resolve():
            raise PermissionError('canonical_authority_root_required')

    def folder(self, plan_hash):
        if len(plan_hash) != 64 or any(c not in '0123456789abcdef' for c in plan_hash):
            raise ValueError('invalid_plan_hash')
        return self.root / plan_hash

    def approve(self, plan, expected_hash, *, currency, input_ceiling, output_ceiling,
                all_charges_included, consent):
        """Invoke only after the user approves this exact plan and account prices.

        This method records the operator's explicit confirmation; it does not
        infer user intent or query the provider account. No grant is made by prepare.
        """
        if (digest(plan) != expected_hash or consent != f'APPROVE {expected_hash} CNY 17'
                or currency != 'CNY' or input_ceiling != '2' or output_ceiling != '8'
                or all_charges_included is not True):
            raise PermissionError('exact_plan_and_account_price_confirmation_required')
        current_plan(plan)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        private(self.root, True)
        folder = self.folder(expected_hash)
        folder.mkdir(mode=0o700, exist_ok=False)
        # An interrupted/empty grant directory remains consumed; no overwrite.
        approved_at = now()
        record = {'version': 1, 'plan': plan, 'plan_hash': expected_hash,
                  'authority_root': str(self.root), 'currency': currency,
                  'input_ceiling': input_ceiling, 'output_ceiling': output_ceiling,
                  'all_charges_included': True, 'consent': consent,
                  'approved_at': approved_at.isoformat(), 'expires_at': (approved_at+timedelta(hours=24)).isoformat(),
                  'run_dir': str(folder / 'run')}
        save_new(folder / 'grant.json', record)
        return record

    def read(self, plan_hash, *, fresh=True):
        private(self.root, True)
        folder = self.folder(plan_hash)
        private(folder, True)
        private(folder / 'grant.json')
        record = json.loads((folder / 'grant.json').read_text())
        if (record['plan_hash'] != plan_hash or digest(record['plan']) != plan_hash
                or record['authority_root'] != str(self.root) or record['run_dir'] != str(folder/'run')
                or record['consent'] != f'APPROVE {plan_hash} CNY 17'
                or record['currency'] != 'CNY' or record['input_ceiling'] != '2'
                or record['output_ceiling'] != '8' or record['all_charges_included'] is not True):
            raise PermissionError('grant_binding_changed')
        if fresh:
            start = datetime.fromisoformat(record['approved_at'])
            end = datetime.fromisoformat(record['expires_at'])
            if start.tzinfo is None or end.tzinfo is None or not start <= now() < end or end-start > timedelta(hours=24):
                raise PermissionError('grant_or_account_confirmation_expired')
            current_plan(record['plan'])
        return record

    def claim(self, plan_hash):
        record = self.read(plan_hash)
        folder = self.folder(plan_hash)
        token = uuid4().hex
        save_new(folder / 'claim.json', {'plan_hash': plan_hash, 'token': token,
                 'ledger_path': str(folder/'run'/'ledger.sqlite')})
        return Admission(self, plan_hash, token)


@dataclass(frozen=True)
class Admission:
    authority: Authority
    plan_hash: str
    token: str

    def validate(self, ledger_path=None):
        record = self.authority.read(self.plan_hash)
        claim_file = self.authority.folder(self.plan_hash) / 'claim.json'
        private(claim_file)
        claim = json.loads(claim_file.read_text())
        expected = str(Path(record['run_dir']) / 'ledger.sqlite')
        if (claim != {'plan_hash': self.plan_hash, 'token': self.token, 'ledger_path': expected}
                or (ledger_path is not None and str(Path(ledger_path).absolute()) != expected)):
            raise PermissionError('claim_or_ledger_owner_mismatch')
        return record
