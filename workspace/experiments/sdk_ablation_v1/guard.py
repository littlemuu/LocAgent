"""Fresh case-bound authorization; rehearsal tickets can never send a real POST."""
from pathlib import Path
from dataclasses import dataclass
from uuid import uuid4
from readonly_agent.authority import save_new
from readonly_agent.authority import Authority, Admission, current_plan
from readonly_agent.core import digest
from readonly_agent.deepseek_wire import exchange_offline, normalize, strict_json
from readonly_agent.live_transport import exchange_live
from experiments.cohort_preflight.entry import ROOT, read, sha, checked_file, load_entry
from .common_contract import (
    SharedWire, ContractError, CONTRACT, check_messages, raw_payload, validate_response, sdk_inputs)

IDS = ('spotify__luigi-3324', 'tobymao__sqlglot-3901', 'tobymao__sqlglot-4366', 'tobymao__sqlglot-4369', 'tobymao__sqlglot-4526', 'xCDAT__xcdat-689')
NAMES = ['OpenHands-basic/retrieval-disabled-v1', 'OpenHands-basic+LocAgent/retrieval-enabled-v1']
SENT = ['issue', 'system_and_task_prompts', 'tool_definitions', 'selected_case_source_evidence', 'same_arm_history']

def source_hashes():
    paths = [p for package in ('sdk_ablation_v1', 'path_retrieval_v4', 'cohort_preflight', 'eval_preflight')
             for p in sorted((ROOT / 'experiments' / package).glob('*.py'))]
    paths.extend([ROOT/'experiments/cohort_five_evidence_v3/cumulative.py', ROOT/'experiments/cohort_dev37_v4/cumulative.py', ROOT/'experiments/cohort_finish_v5/cumulative.py', ROOT/'experiments/cohort_remaining17_v5/cumulative.py'])
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}

PLAN_FIELDS = frozenset(['account_pricing_confirmed', 'arm_order', 'arms', 'authorization', 'budget_micro_cny', 'cohort_admission_version', 'cohort_binding', 'cohort_execution', 'cohort_sources', 'comparison_contract', 'comparison_names', 'context_tokens', 'controller_policy', 'currency', 'dependency_lock_sha256', 'endpoint', 'full_reservations_micro_cny', 'hidden_python_paths', 'input_peak_cache_miss_cny_per_million', 'issue', 'issue_hash', 'limits', 'live_transport_enabled', 'locagent_engine', 'max_output_tokens', 'max_requests_per_arm', 'max_requests_total', 'mode', 'model', 'output_peak_cny_per_million', 'pricing_source', 'pricing_status', 'public_pricing_checked_utc_date', 'purpose', 'reservation_micro_cny', 'resolved_family_reference', 'runtime_hash', 'sdk_version', 'send_categories', 'snapshot', 'source_hashes', 'system_hash', 'version'])

def verify(plan, mode):
    if set(plan) != PLAN_FIELDS:
        raise PermissionError("unexpected_runtime_material")
    current_plan(plan)
    if (mode not in ('live', 'rehearsal') or plan.get('cohort_execution') != mode
            or plan.get('cohort_admission_version') != 1 or plan.get('comparison_names') != NAMES
            or plan.get('comparison_contract') != CONTRACT or plan.get('send_categories') != SENT
            or plan.get('live_transport_enabled') is not (mode == 'live')
            or plan.get('cohort_sources') != source_hashes()):
        raise PermissionError('cohort_plan_or_code_changed')
    binding = plan['cohort_binding']
    if set(binding) != {'case_id', 'entry', 'entry_sha256', 'body_status', 'body_status_sha256'} or binding['case_id'] not in IDS:
        raise PermissionError('single_exposed_case_required')
    value, snapshot = load_entry(binding['entry'], binding['entry_sha256'])
    if (value['case_id'] != binding['case_id'] or plan['issue'] != value['issue'] or plan['issue_hash'] != value['issue_hash']
            or plan['snapshot'] != snapshot.identity or plan['source_hashes'] != dict(snapshot.hashes)):
        raise PermissionError('cohort_case_binding_changed')
    status = read(checked_file(binding['body_status'], binding['body_status_sha256']))
    if status['id'] != binding['case_id'] or status['status'] != 'ready' or status['snapshot'] != snapshot.identity:
        raise PermissionError('cohort_body_binding_changed')
    attpath = Path(status['body_directory']) / 'attestation.json'
    att = read(checked_file(attpath, status['body_attestation_sha256']))
    if (att['snapshot'] != snapshot.identity or att['source_hashes'] != dict(snapshot.hashes)
            or att['version'] != 'source-body-physical-line80-v2'):
        raise PermissionError('cohort_body_version_changed')
    for name, expected in att['artifacts'].items():
        if Path(name).name != name:
            raise PermissionError('invalid_body_artifact')
        checked_file(attpath.parent / name, expected)
    return value, snapshot, status

class CohortAuthority(Authority):
    def approve(self, plan, *args, **kwargs):
        from .parent import check_child
        check_child(self.root, plan)
        verify(plan, 'live')
        return super().approve(plan, *args, **kwargs)

    def read(self, plan_hash, *, fresh=True):
        record = super().read(plan_hash, fresh=fresh)
        from .parent import check_child
        check_child(self.root, record['plan'])
        if fresh:
            verify(record['plan'], 'live')
        return record

class RehearsalAuthority:
    """No production grant schema or Admission object is created by rehearsal."""
    def __init__(self, root):
        self.root = Path(root).resolve()
    def prepare_fixture(self, plan):
        from .parent import check_child
        check_child(self.root, plan)
        verify(plan, 'rehearsal')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=False)
        record = {'plan': plan, 'plan_hash': digest(plan), 'authorization': 'offline_fixture_only',
                  'run_dir': str(self.root / 'run')}
        save_new(self.root / 'rehearsal.json', record)
        return record

    def read(self, plan_hash):
        record = read(self.root / 'rehearsal.json')
        if record['authorization'] != 'offline_fixture_only' or record['plan_hash'] != plan_hash or digest(record['plan']) != plan_hash:
            raise PermissionError('rehearsal_binding_changed')
        if record['run_dir'] != str(self.root / 'run'):
            raise PermissionError('rehearsal_path_changed')
        from .parent import check_child
        check_child(self.root, record['plan'])
        verify(record['plan'], 'rehearsal')
        return record

    def claim(self, plan_hash):
        self.read(plan_hash)
        token = uuid4().hex
        save_new(self.root / 'rehearsal-claim.json', {'plan_hash': plan_hash, 'token': token})
        return RehearsalAdmission(self, plan_hash, token)

@dataclass(frozen=True)
class RehearsalAdmission:
    authority: RehearsalAuthority
    plan_hash: str
    token: str

    def validate(self, ledger_path=None):
        record = self.authority.read(self.plan_hash)
        if read(self.authority.root / 'rehearsal-claim.json') != {'plan_hash': self.plan_hash, 'token': self.token}:
            raise PermissionError('rehearsal_claim_changed')
        if ledger_path is not None and Path(ledger_path).absolute() != Path(record['run_dir']) / 'ledger.sqlite':
            raise PermissionError('rehearsal_ledger_changed')
        return record

def start_mock(ledger, identifier, data, ticket):
    ticket.validate(ledger.path)
    with ledger.transaction() as db:
        _, state, calls, _, _ = ledger.validate(db)
        call = next((c for c in calls if c['id'] == identifier), None)
        if state['mode'] != 'simulation' or state['halted'] or call is None or bytes(call['request']) != data:
            raise PermissionError('mock_reservation_required')
        changed = db.execute("UPDATE calls SET transport_started=1 WHERE id=? AND status='reserved' AND transport_started=0", (identifier,))
        if changed.rowcount != 1:
            raise PermissionError('mock_transport_already_consumed')

class CohortWire(SharedWire):
    def __init__(self, ledger, arm, admission, key, *, snapshot, transport=None, parent_alive=lambda: None):
        import httpx
        if type(admission) not in (Admission, RehearsalAdmission):
            raise PermissionError('cohort_admission_required')
        self.rehearsal = type(admission) is RehearsalAdmission and type(admission.authority) is RehearsalAuthority
        if self.rehearsal:
            if type(transport) is not httpx.MockTransport or key is not None:
                raise PermissionError('rehearsal_mock_only_no_key')
        elif type(admission.authority) is not CohortAuthority or transport is not None:
            raise PermissionError('fresh_cohort_authority_required')
        record = admission.validate(ledger.path)
        if ledger.summary()['simulation'] != self.rehearsal or ledger.plan_hash != digest(record['plan']):
            raise PermissionError('claimed_ledger_required')
        if snapshot.identity != record['plan']['snapshot'] or dict(snapshot.hashes) != record['plan']['source_hashes']:
            raise PermissionError('cohort_snapshot_changed')
        self.ledger, self.arm, self.snapshot = ledger, arm, snapshot
        self.admission, self._key, self.transport = admission, key, transport
        self.parent_alive = parent_alive
        self.token = ledger.claim(arm)
        self.calls, self.requests, self.last_id = 0, [], None
        self.last_normalization_events = []

    def exchange(self, messages, tools, closing):
        self.parent_alive()
        self.admission.validate(self.ledger.path)
        turn = sum(c['arm'] == self.arm for c in self.ledger.summary()['calls']) + 1
        closing = closing or turn == 4 or self.calls >= 16 or check_messages(messages) >= 14272
        names={t['function']['name'] for t in tools}
        expected={'list_files','search_text','read_file','finish'}
        if self.arm=='retrieval':expected.add('locagent_retrieve')
        if names != expected and not (closing and names=={'finish'}):
            raise PermissionError('ablation_tool_availability_changed')
        data = raw_payload(messages, tools, closing=closing)
        identifier = self.ledger.reserve(self.arm, self.token, data)
        self.last_id = identifier
        try:
            self.requests.append(strict_json(data))
            if self.rehearsal:
                # Exercise the same durable one-use reservation; no provider/key path.
                start_mock(self.ledger, identifier, data, self.admission)
                response = exchange_offline(data, self.transport)
            else:
                response = exchange_live(data, self._key, admission=self.admission,
                    ledger=self.ledger, reservation=identifier, enabled=True)
            self.ledger.received(identifier, response)
            raw = self.ledger.settle(identifier)
            available = {t['function']['name'] for t in strict_json(data)['tools']}
            prior = {c['id'] for m in messages for c in m.get('tool_calls', [])}
            self.calls += validate_response(raw, available, closing, 16-self.calls, self.snapshot, prior)
            return raw, available, closing
        except BaseException as error:
            self.fail(str(error) if isinstance(error, ContractError) else type(error).__name__)
            raise RuntimeError('cohort_exchange_stopped') from None

    def generate(self, messages, tools, closing):
        self.last_normalization_events = []
        messages, tools = sdk_inputs(messages, tools)
        raw, available, closing = self.exchange(messages, tools, closing)
        try:
            return normalize(raw, available, closing=closing, normalization_events=self.last_normalization_events)
        except BaseException:
            self.fail('normalization_failed')
            raise

    def forget_key(self):
        self._key = None
