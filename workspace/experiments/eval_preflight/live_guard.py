"""Dormant paired transport adapter; requires fresh comparison-specific authority.

No environment access, credential discovery, approval creation or I/O on import.
The preflight proposals keep live_transport_enabled=False and cannot be admitted.
"""
import hashlib,json
from pathlib import Path
from readonly_agent.authority import Authority,Admission,current_plan
from readonly_agent.core import digest
from readonly_agent.deepseek_wire import normalize,strict_json
from readonly_agent.live_transport import exchange_live
from .common_contract import SharedWire,CONTRACT,check_messages,raw_payload,validate_response,sdk_inputs

ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def verify_comparison_plan(plan):
    current_plan(plan)
    if (plan.get('comparison_contract')!=CONTRACT or plan.get('live_transport_enabled') is not True
            or plan.get('comparison_live_review_complete') is not True):
        raise PermissionError('comparison_live_review_and_new_freeze_required')
    expected={str(p.relative_to(ROOT)) for p in (ROOT/'experiments/eval_preflight').glob('*.py')}
    sources=plan.get('adapter_sources',{})
    if set(sources)!=expected or any(sha(ROOT/n)!=h for n,h in sources.items()):
        raise PermissionError('comparison_adapter_hash_changed')
    binding=plan.get('cache_binding',{})
    manifest=ROOT/'engine_adaptation/v4/adapted-manifest.json'
    if sha(manifest)!=binding.get('adapted_manifest_sha256'):
        raise PermissionError('comparison_manifest_changed')
    m=json.loads(manifest.read_text())
    item=next((r for r in m['cases'] if r['id']==binding.get('case')),None)
    if item is None or binding.get('snapshot')!=plan['snapshot'] or item['source_snapshot']!=plan['snapshot']:
        raise PermissionError('comparison_source_binding_changed')
    entity_att=Path(item['index_attestation'])
    if sha(entity_att)!=binding['attestation_sha256']:raise PermissionError('entity_attestation_changed')
    for name,h in json.loads(entity_att.read_text())['artifacts'].items():
        artifact=Path(item['index_directory']).parent/name
        if artifact.is_symlink() or sha(artifact)!=h:raise PermissionError('entity_index_changed')
    body=Path(binding['body_root'])/binding['case'];att=body/'attestation.json'
    if sha(att)!=binding['body_attestation_hash']:raise PermissionError('body_attestation_changed')
    meta=json.loads(att.read_text())
    if meta['snapshot']!=plan['snapshot'] or meta['source_hashes']!=plan['source_hashes']:
        raise PermissionError('body_source_changed')
    for name,h in meta['artifacts'].items():
        artifact=body/name
        if artifact.parent!=body or artifact.is_symlink() or sha(artifact)!=h:
            raise PermissionError('body_index_changed')


class ComparisonAuthority(Authority):
    def approve(self,plan,*args,**kwargs):
        verify_comparison_plan(plan)
        return super().approve(plan,*args,**kwargs)

    def read(self,plan_hash,*,fresh=True):
        record=super().read(plan_hash,fresh=fresh)
        if fresh:verify_comparison_plan(record['plan'])
        return record


class SharedLiveWire(SharedWire):
    def __init__(self,ledger,arm,admission,key,*,snapshot,parent_alive=lambda:None):
        # Do not inspect key, and never consume an old generic experiment grant.
        if type(admission) is not Admission or type(admission.authority) is not ComparisonAuthority:
            raise PermissionError('fresh_comparison_specific_admission_required')
        record=admission.validate(ledger.path)
        if ledger.summary()['simulation'] or digest(record['plan'])!=ledger.plan_hash:
            raise PermissionError('comparison_live_ledger_required')
        if snapshot.identity!=record['plan']['snapshot'] or dict(snapshot.hashes)!=record['plan']['source_hashes']:
            raise PermissionError('comparison_snapshot_changed')
        self.ledger,self.arm,self.snapshot=ledger,arm,snapshot
        self.admission,self._key,self.parent_alive=admission,key,parent_alive
        self.token=ledger.claim(arm);self.calls=0;self.requests=[];self.last_id=None
        self.last_normalization_events=[]

    def exchange(self,messages,tools,closing):
        self.parent_alive();self.admission.validate(self.ledger.path)
        turn=sum(c['arm']==self.arm for c in self.ledger.summary()['calls'])+1
        closing=closing or turn==4 or self.calls>=16 or check_messages(messages)>=14272
        data=raw_payload(messages,tools,closing=closing)
        identifier=self.ledger.reserve(self.arm,self.token,data);self.last_id=identifier
        try:
            response=exchange_live(data,self._key,admission=self.admission,ledger=self.ledger,
                                   reservation=identifier,enabled=True)
            self.ledger.received(identifier,response);raw=self.ledger.settle(identifier)
            available={t['function']['name'] for t in strict_json(data)['tools']}
            prior={c['id'] for m in messages for c in m.get('tool_calls',[])}
            self.calls+=validate_response(raw,available,closing,16-self.calls,self.snapshot,prior)
            return raw,available,closing
        except BaseException as error:
            self.fail(type(error).__name__)
            raise RuntimeError('comparison_live_exchange_stopped') from None

    def generate(self,messages,tools,closing):
        self.last_normalization_events=[]
        messages,tools=sdk_inputs(messages,tools)
        raw,available,closing=self.exchange(messages,tools,closing)
        try:return normalize(raw,available,closing=closing,normalization_events=self.last_normalization_events)
        except BaseException:
            self.fail('normalization_failed');raise

    def forget_key(self):self._key=None


def native_provider(wire):
    if type(wire) is not SharedLiveWire:
        raise PermissionError('comparison_native_live_wire_required')
    def generate(**kwargs):
        from litellm import ModelResponse
        raw,_,_=wire.exchange(kwargs['messages'],kwargs['tools'],kwargs.get('tool_choice') is not None)
        return ModelResponse(**raw)
    return generate
