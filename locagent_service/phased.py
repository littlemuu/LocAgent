"""Fixed-cohort phased execution; live requires a fresh external approval."""
import argparse
import math
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import ctypes
from decimal import Decimal
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from uuid import uuid4

from locagent_service import budget, followup, response_store, guidance_experiment as guidance
from locagent_service.sources import canonical, digest, load_manifest
from locagent_service.models import CreateTask, LocalizationResultView

ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP_ROOT = ROOT / 'outputs/stage4/phased-offline-owners'
LIVE_OWNERSHIP_ROOT = ROOT / 'outputs/stage4/phased-live-owners'
SIMULATION_OWNERSHIP_ROOT = ROOT / 'outputs/stage4/phased-http-simulation-owners'
POLICY = 'locagent-phased-v3'
FAILURE_POLICY = 'settled-json-arguments-with-reaped-executor-v1'
PROTOCOL_ERROR = {'code':'invalid_response','message':'Tool arguments must be a valid JSON object'}



def specs():
    return json.loads((ROOT/'locagent_service/phased_cohorts.json').read_text())


def runtime_hashes(spec):
    from locagent_service.engine_binding import behavior_hashes
    hashes = behavior_hashes(ROOT)
    # Cohort contains source IDs whose manifests already bind behavior_hashes.
    # Keep it at plan level to avoid a source/cohort content-addressing cycle.
    name = guidance.CONFIG_NAME if guidance.is_guidance(spec) else 'locagent_service/phased_cohorts.json'
    hashes[name] = digest((ROOT/name).read_bytes())
    return hashes


def expected_plan(cohort, experiment_id, mode='offline'):
    if not isinstance(experiment_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', experiment_id):
        raise ValueError('Explicit safe experiment ID required')
    if mode not in ('offline','live'):raise ValueError('Unknown plan mode')
    from locagent_service import deepseek_http
    spec = guidance.load_spec(ROOT) if cohort == guidance.COHORT else specs()[cohort]
    return {'version':3, 'policy':POLICY, 'arm_failure_policy':FAILURE_POLICY,
            'mode':mode, 'live_authorized':False,
            'transport':{'endpoint':deepseek_http.ENDPOINT,'wire_model':deepseek_http.WIRE_MODEL,
                         'redirects':False,'retries':0,'timeout_seconds':60},
            'cohort':cohort, 'experiment_id':experiment_id, **deepcopy(spec),
            'sources':[s['source_id'] for s in spec['samples']], 'arms':[False,True],
            'denominator_per_arm':len(spec['samples']), 'max_calls':len(spec['samples'])*6,
            'max_calls_per_arm':3, 'reservation_basis':deepcopy(followup.BASIS),
            'reservation_cny':str(followup.RESERVE),
            'runtime_hashes':runtime_hashes(spec), 'python_runtime':sys.version,
            'response_storage':response_store.limits()}


def validate_plan(plan):
    if plan != expected_plan(plan['cohort'], plan['experiment_id'], plan.get('mode')):
        raise ValueError('Frozen cohort/configuration/scoring/runtime changed')
    followup.validate_config(plan['config'])
    return plan


def verify_sources(plan):
    validate_plan(plan)
    from locagent_service.engine_binding import behavior_hashes
    if plan['engine_hashes'] != behavior_hashes(ROOT):
        raise ValueError('Prepared cohort does not bind the complete current behavior')
    environment=subprocess.check_output([sys.executable,'-m','pip','freeze'])
    if digest(environment)!=plan['environment_sha256']:
        raise ValueError('Installed dependency environment changed')
    for sample in plan['samples']:
        manifest, _ = load_manifest(sample['source_id'])
        if (manifest['task']['instance_id'] != sample['instance_id']
            or manifest['task']['base_commit'] != sample['base_commit']
            or manifest['config'] != plan['config']
            or manifest['engine'] != plan['engine_hashes']):
            raise ValueError('Prepared source differs from reviewed cohort')


def check_labels(plan, path):
    raw = Path(path).read_bytes()
    if digest(raw) != plan['labels_sha256']:
        raise ValueError('Scoring labels changed')
    answers = json.loads(raw)
    from locagent_service.evaluate import summarize
    summarize(plan, [], answers)  # Shape/applicability validation; no model inputs.
    return answers


def make_plan(cohort, experiment_id, labels, output, mode='offline'):
    plan = expected_plan(cohort, experiment_id, mode)
    validate_plan(plan); check_labels(plan, labels); verify_sources(plan)
    with Path(output).open('xb') as f:
        f.write(canonical(plan))
    return plan


def refuse_live():
    raise RuntimeError('This operation needs a live plan and a fresh explicit approval')


def read_json(path):
    return followup.raw_json(Path(path).read_bytes())  # Strict JSON, 8 MiB bound.


def owner_path(plan, mode=None):
    mode = mode or ('live' if plan['mode']=='live' else 'offline')
    root = {'offline':OWNERSHIP_ROOT,'live':LIVE_OWNERSHIP_ROOT,
            'simulation':SIMULATION_OWNERSHIP_ROOT}[mode]
    return root / (plan['cohort']+'-'+digest(canonical(plan))+'.json')


def arms_for(plan):
    return [{'source_id':s['source_id'], 'arm':arm, 'instance_id':s['instance_id']}
            for s in plan['samples'] for arm in s['arm_order']]


def result_path(path, index):
    folder = path.parent/(path.name+'.results')
    if folder.is_symlink():
        raise RuntimeError('Result directory cannot be a symlink')
    return folder/('arm-%04d.json' % index)


def totals(state):
    spent = sum((Decimal(c['cost_upper_cny']) for c in state['calls'] if c['status']=='settled'), Decimal(0))
    reserved = followup.RESERVE * sum(c['status']!='settled' for c in state['calls'])
    return spent, reserved


def call_hash(state, index):
    return digest(canonical([c for c in state['calls'] if c['arm_index']==index]))


def record_for(path, state, index):
    target = result_path(path, index)
    if not target.exists():
        return None
    if target.is_symlink():
        raise RuntimeError('Result cannot be a symlink')
    record = read_json(target)
    identity = arms_for(state['plan'])[index]
    if guidance.is_guidance(state['plan']):
        guidance.validate_fields(state['plan'], record, identity['arm'])
    if (record.get('plan_hash') != state['plan_hash'] or record.get('arm_index') != index
        or record.get('source_id') != identity['source_id']
        or type(record.get('suppress_repeats')) is not bool
        or record['suppress_repeats'] != guidance.axis_fields(state['plan'], identity['arm'])['suppress_repeats']
        or record.get('mode') != ('live' if state['mode']=='live' else 'offline') or record.get('status') != 'completed'
        or type(record.get('elapsed_seconds')) not in (int,float)
        or not math.isfinite(record['elapsed_seconds']) or record['elapsed_seconds']<0
        or record.get('calls_hash') != call_hash(state,index)
        or any(c['status']!='settled' for c in state['calls'] if c['arm_index']==index)):
        raise RuntimeError('Result identity/call lineage mismatch')
    LocalizationResultView.model_validate(record['result'], strict=True)
    return record


def malformed_argument_call(path, state, index):
    """Only this evidenced JSON protocol error is eligible; no argument repairs."""
    calls=[c for c in state['calls'] if c['arm_index']==index]
    if not calls or any(c['status']!='settled' for c in calls):
        raise RuntimeError('Protocol failure requires all calls settled')
    call=calls[-1]
    if (call.get('http_status',200)!=200 or call.get('response_complete',True) is not True
        or call.get('transport_error_type') is not None):
        raise RuntimeError('Protocol response is incomplete')
    if state['mode']=='live' and ('http_status' not in call or 'response_complete' not in call):
        raise RuntimeError('Live response transport evidence missing')
    raw,_,_=followup.verify_raw_usage(response_body(path,call))
    choices=raw.get('choices',[])
    if len(choices)!=1 or choices[0].get('finish_reason')!='tool_calls':
        raise RuntimeError('Not an untruncated tool-call response')
    from util.localizer import _TOOLS
    found=False
    for tool in choices[0].get('message',{}).get('tool_calls',[]):
        function=tool.get('function',{})
        if function.get('name') not in (*_TOOLS,'finish','read_tool_output'):
            raise RuntimeError('Unknown tool is not eligible for continuation')
        if function['name']=='finish':
            continue  # Bounded finish has its own validation and outcome.
        try:
            if not isinstance(json.loads(function['arguments']),dict):found=True
        except (TypeError,ValueError):found=True
    if not found:raise RuntimeError('Raw response does not prove the declared protocol error')
    return call


def protocol_failure_evidence(path,state,index, *, unavailable_calls=()):
    arm=state['arms'][index];proof=arm.get('protocol_failure')
    if (not isinstance(proof,dict) or set(proof)!={
            'policy','plan_hash','arm_index','source_id','run_token','calls_hash',
            'call_index','raw_body_sha256','error','executor'}
        or proof['policy']!=FAILURE_POLICY or proof['plan_hash']!=state['plan_hash']
        or proof['arm_index']!=index or proof['source_id']!=arms_for(state['plan'])[index]['source_id']
        or not isinstance(proof['run_token'],str) or not proof['run_token']
        or proof['calls_hash']!=call_hash(state,index)
        or proof['error']!=PROTOCOL_ERROR or arm.get('localization_error')!=PROTOCOL_ERROR
        or arm.get('failure')!={'code':'invalid_response','error_type':'LocalizationError'}
        or arm.get('terminal_sha256')!=digest(canonical(proof))):
        raise RuntimeError('Invalid protocol failure evidence')
    exit_proof=proof['executor']
    if (not isinstance(exit_proof,dict) or set(exit_proof)!={
            'pid','parent_pid','returncode','process_group_empty','confirmed_at_utc'}
        or any(type(exit_proof.get(k)) is not int or exit_proof[k]<=0 for k in ('pid','parent_pid'))
        or type(exit_proof['returncode']) is not int or exit_proof['returncode']!=1
        or exit_proof['process_group_empty'] is not True
        or not isinstance(exit_proof['confirmed_at_utc'],str)):
        raise RuntimeError('Executor exit proof missing')
    when=datetime.fromisoformat(exit_proof['confirmed_at_utc'])
    if when.tzinfo is None:raise RuntimeError('Exit confirmation must be timezone aware')
    calls=[c for c in state['calls'] if c['arm_index']==index]
    if not calls or any(c['status']!='settled' for c in calls):
        raise RuntimeError('Protocol failure call history is not settled')
    call=calls[-1]
    if proof['call_index']!=call['index'] or proof['raw_body_sha256']!=call['raw_body_sha256']:
        raise RuntimeError('Failure raw response lineage changed')
    # Explicit forensic audit may check only the stored proof/reference when this
    # exact body was already found unavailable. It must then halt, never continue.
    if call['index'] not in unavailable_calls:
        malformed_argument_call(path,state,index)
    if result_path(path,index).exists():raise RuntimeError('Conflicting success artifact')
    return proof


def terminal_arm(arm):
    return arm['status']=='completed' or (arm['status']=='failed' and 'protocol_failure' in arm)


def checkpoint_for(state,phase):
    arms=state['arms'][phase['start']:phase['end']]
    if not all(terminal_arm(a) for a in arms):raise RuntimeError('Phase has unterminated arms')
    entries=[{'status':a['status'],'sha256':a['result_sha256'] if a['status']=='completed'
              else a['terminal_sha256']} for a in arms]
    return {'phase':phase['name'],'terminal_arms_sha256':digest(canonical(entries))}


def validate_state(path, state, *, allow_body_errors=False):
    plan = validate_plan(state['plan'])
    identities = arms_for(plan)
    if (state.get('version')!=1 or state.get('policy')!=POLICY
        or state.get('mode') not in (('live','simulation') if plan['mode']=='live' else ('offline',))
        or state.get('plan_hash')!=digest(canonical(plan))
        or type(state.get('revision')) is not int or state['revision']<0
        or state.get('status') not in ('ready','running','halted','complete')
        or not isinstance(state.get('arms'),list) or len(state['arms'])!=len(identities)
        or not isinstance(state.get('calls'),list) or len(state['calls'])>plan['max_calls']
        or type(state.get('next_phase')) is not int
        or not 0<=state['next_phase']<=len(plan['phases'])
        or len(state.get('checkpoints',[]))!=state['next_phase']):
        raise RuntimeError('Invalid phased ledger structure')
    body_errors=[]
    counts = [0]*len(identities)
    last = -1
    for i,c in enumerate(state['calls']):
        index = c.get('arm_index')
        if (type(index) is not int or not 0<=index<len(counts) or index<last
            or c.get('index')!=i or c.get('ordinal')!=counts[index]
            or c.get('reservation_cny')!=str(followup.RESERVE)
            or c.get('source_id')!=identities[index]['source_id']
            or type(c.get('arm')) is not bool or c['arm']!=identities[index]['arm']
            or c.get('status') not in ('reserved','raw_received','settled','outcome_unknown')
            or not re.fullmatch('[0-9a-f]{64}',c.get('request_sha256',''))):
            raise RuntimeError('Invalid call identity/quota/order')
        if guidance.is_guidance(plan):guidance.validate_fields(plan,c,identities[index]['arm'])
        counts[index]+=1; last=index
        body=None
        if 'raw_body_b64' in c:
            raise RuntimeError('Inline response bodies are not valid in this plan')
        if c['status'] in ('raw_received','settled') or 'raw_body_ref' in c:
            reference=c.get('raw_body_ref')
            response_store.validate_reference(i,reference)
            if reference['sha256']!=c.get('raw_body_sha256'):
                raise RuntimeError('Response reference/hash differs')
            try:body=response_store.read(path,i,reference)
            except (OSError,ValueError) as exc:
                if not allow_body_errors:raise RuntimeError('Response evidence invalid; audit required') from exc
                body_errors.append({'call_index':i,'error_type':type(exc).__name__,
                                    'raw_body_ref':deepcopy(reference)})
        if c['status']=='settled':
            if c.get('http_status',200)!=200 or c.get('response_complete',True) is not True:
                raise RuntimeError('Incomplete/failed HTTP cannot settle')
            if body is not None:
                raw,usage,cost=followup.verify_raw_usage(body)
                if (any(c.get(k)!=v for k,v in usage.items()) or c.get('cost_upper_cny')!=str(cost)
                    or (guidance.is_guidance(plan) and c.get('returned_model') != raw.get('model'))):
                    raise RuntimeError('Settlement differs from original usage')
            else:
                # Preserve a previously owned settlement, but do not call it raw-
                # verified. Validate every available accounting field before halt.
                fields=('prompt_tokens','completion_tokens','total_tokens',
                        'prompt_cache_hit_tokens','prompt_cache_miss_tokens')
                if any(type(c.get(k)) is not int for k in fields):
                    raise RuntimeError('Stored settlement usage is invalid')
                pt,ct,total,hit,miss=(c[k] for k in fields)
                cost=(Decimal(pt)*2+Decimal(ct)*8)/1000000
                if (not 0<pt<=1048576 or not 0<=ct<=512 or min(hit,miss)<0
                    or total!=pt+ct or pt!=hit+miss or c.get('cost_upper_cny')!=str(cost)):
                    raise RuntimeError('Stored settlement accounting is inconsistent')
    spent,reserved=totals(state)
    if (max(counts,default=0)>3 or state.get('spent_cny')!=str(spent)
        or state.get('reserved_cny')!=str(reserved)
        or spent+reserved>Decimal(plan['limit_cny'])):
        raise RuntimeError('Invalid ledger totals or budget')
    incomplete=False
    for index,arm in enumerate(state['arms']):
        if arm.get('status') not in ('pending','running','completed','blocked','failed'):
            raise RuntimeError('Invalid arm state')
        if arm['status'] in ('failed','blocked') and 'failure' in arm:
            failure = arm['failure']
            if (not isinstance(failure,dict) or set(failure) != {'code','error_type'}
                or not all(isinstance(v,str) and v for v in failure.values())
                or arm.get('calls_hash') != call_hash(state,index)
                or (arm.get('elapsed_seconds') is not None and (
                    type(arm['elapsed_seconds']) not in (int,float)
                    or not math.isfinite(arm['elapsed_seconds']) or arm['elapsed_seconds']<0))):
                raise RuntimeError('Invalid terminal failure evidence')
        if 'protocol_failure' in arm:
            if arm['status']!='failed':raise RuntimeError('Protocol failure cannot become success or pending')
            protocol_failure_evidence(path,state,index,
                unavailable_calls={error['call_index'] for error in body_errors} if allow_body_errors else ())
        elif arm['status']=='failed' and (
            state['status']!='halted' or state.get('active_run') is not None
            or 'failure' not in arm or any(c['status']!='settled'
                for c in state['calls'] if c['arm_index']==index)):
            raise RuntimeError('System failure must halt the experiment')
        if terminal_arm(arm):
            if incomplete:raise RuntimeError('Terminal arms are out of order')
            if arm['status']=='completed':
                record=record_for(path,state,index)
                if record is None or arm.get('result_sha256')!=digest(canonical(record)):
                    raise RuntimeError('Missing or changed durable result')
        else:
            incomplete=True
        if arm['status']=='pending' and counts[index] and not arm.get('recovery_audit'):
            raise RuntimeError('Call history cannot reset to pending without audit')
    for i,checkpoint in enumerate(state['checkpoints']):
        phase=plan['phases'][i]
        if checkpoint != checkpoint_for(state,phase):
            raise RuntimeError('Phase checkpoint inconsistent')
    if state['status']=='complete' and state['next_phase']!=len(plan['phases']):
        raise RuntimeError('Premature completion')
    return body_errors


def owner_for(path,state):
    marker=read_json(owner_path(state['plan'],state['mode']))
    if (marker.get('policy')!=POLICY or marker.get('mode')!=state['mode']
        or marker.get('ledger_path')!=str(path)
        or marker.get('plan_hash')!=state['plan_hash']
        or marker.get('token')!=state.get('token')):
        raise RuntimeError('Ledger owner/plan mismatch; copied or old authorization is invalid')
    if marker.get('admission')!=state.get('admission'):
        raise RuntimeError('Approval differs from ledger owner')
    if state['mode']=='live':
        from locagent_service.phased_admission import validate_claim
        validate_claim(path,state)
    return marker


def load_state(path, *, allow_one_step=False, allow_body_errors=False):
    path=Path(path).resolve()
    state=read_json(path);validate_state(path,state,allow_body_errors=allow_body_errors)
    marker=owner_for(path,state);sha=digest(canonical(state))
    matches=marker.get('revision')==state['revision'] and marker.get('state_sha256')==sha
    lag=(allow_one_step and type(marker.get('revision')) is int
         and marker['revision']+1==state['revision']
         and marker.get('state_sha256')==state.get('parent_sha256'))
    if not matches and not lag:
        raise RuntimeError('Ledger head inconsistent or rolled back; audit required')
    return state,marker,not matches


def commit(path,state):
    previous=read_json(path)
    if state['revision']!=previous['revision']:
        raise RuntimeError('Stale ledger writer')
    marker=owner_for(path,previous)
    if (marker.get('revision')!=previous['revision']
        or marker.get('state_sha256')!=digest(canonical(previous))):
        raise RuntimeError('Previous persistence incomplete')
    state['parent_sha256']=digest(canonical(previous))
    state['revision']+=1
    state['spent_cny'],state['reserved_cny']=map(str,totals(state))
    response_store.save_json(path,state)
    marker.update(revision=state['revision'],state_sha256=digest(canonical(state)))
    response_store.save_json(owner_path(state['plan'],state['mode']),marker)


@contextmanager
def phase_lock(path):
    path=Path(path).resolve()
    fd=os.open(str(path)+'.phase.lock',os.O_RDWR|os.O_CREAT,0o600)
    with os.fdopen(fd,'r+') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another phase runner/auditor owns this ledger') from None
        yield path


def initialize(path,plan, *, labels=None, live=False, simulate_http=False, approval_id=None):
    if live and (simulate_http or plan.get('mode')!='live'):refuse_live()
    mode = 'live' if live else 'simulation' if simulate_http else 'offline'
    if (plan.get('mode')=='live') != (mode in ('live','simulation')):
        raise ValueError('Live plan requires explicit live or simulate-http initialization')
    if approval_id is not None and not live:
        raise ValueError('Simulation/offline cannot consume an approval')
    approval = None
    if live:
        from locagent_service import phased_admission as admission
        approval = admission.load_approval(plan,approval_id)
        admission.require_switch()
    validate_plan(plan);check_labels(plan,labels);verify_sources(plan)
    path=Path(path).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    with budget.ledger_lock(path):
        if path.exists():raise FileExistsError('Ledger already exists; never reset it')
        admitted = admission.claim(path,plan,approval) if live else None
        marker_path=owner_path(plan,mode);marker_path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(marker_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        token=uuid4().hex
        marker={'policy':POLICY,'mode':mode,'admission':admitted,'plan_hash':digest(canonical(plan)),
                'ledger_path':str(path),'token':token}
        response_store.save_json(marker_path,marker)  # Even partial init consumes this mode-specific identity.
        state={'version':1,'policy':POLICY,'mode':mode,'admission':admitted,'plan':deepcopy(plan),
               'plan_hash':marker['plan_hash'],'token':token,'revision':0,'parent_sha256':None,
               'status':'ready','next_phase':0,'active_run':None,'checkpoints':[],'runs':[],
               'arms':[{'status':'pending'} for _ in arms_for(plan)],'calls':[],
               'spent_cny':'0','reserved_cny':str(followup.RESERVE*0),'audits':[]}
        response_store.save_json(path,state)
        marker.update(revision=0,state_sha256=digest(canonical(state)))
        response_store.save_json(marker_path,marker)
    return state


def no_hook(name): pass


def response_body(path,call):
    return response_store.read(path,call['index'],call['raw_body_ref'])


def settle(path,call):
    if call.get('http_status',200)!=200 or call.get('response_complete',True) is not True:
        raise ValueError('HTTP failure or partial response retains full reservation')
    raw,usage,cost=followup.verify_raw_usage(response_body(path,call))
    from litellm import ModelResponse
    response=ModelResponse(**raw)
    call.update(usage,status='settled',cost_upper_cny=str(cost),returned_model=raw['model'])
    return response


def scripted_raw(ordinal, **kwargs):
    name='explore_tree_structure' if ordinal<2 else 'finish'
    arguments={'start_entities':['.'],'traversal_depth':1} if ordinal<2 else {'files':[],'entities':[]}
    return canonical({'id':'offline-'+str(ordinal),'model':'deepseek-v4-flash',
        'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
            'tool_calls':[{'id':'offline-'+str(ordinal),'type':'function',
                'function':{'name':name,'arguments':json.dumps(arguments)}}]}}],
        'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110,
                 'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100}})


class Provider:
    """Mode-bound HTTP or offline transport; cached responses never consume new calls."""
    def __init__(self,path,index,run_token,raw_completion=None,hook=no_hook):
        self.path=Path(path).resolve();self.index=index;self.run_token=run_token
        self.raw=raw_completion;self.hook=hook;self.cursor=0

    def __call__(self,**kwargs):
        bounded={k:kwargs[k] for k in ('messages','tools','tool_choice','stop') if k in kwargs}
        request_hash=digest(canonical(bounded));estimate=len(canonical(bounded))+4096
        with budget.ledger_lock(self.path):
            state,_,_=load_state(self.path);plan=state['plan']
            wire = None
            if state['mode']!='offline':
                from locagent_service import deepseek_http
                wire = deepseek_http.payload(**bounded)
                estimate=max(estimate,len(canonical(wire))+4096)
                request_hash=digest(canonical(wire))
            if state['mode']=='live':
                from locagent_service.phased_admission import validate_claim
                validate_claim(self.path,state,spending=True)
                if self.raw is not None:
                    raise RuntimeError('Live mode cannot replace official HTTP transport')
                if not os.environ.get('DEEPSEEK_API_KEY'):
                    raise RuntimeError('Existing provider credential unavailable')
            if (state['status']!='running' or state['active_run']['token']!=self.run_token
                or state['arms'][self.index]['status']!='running'
                or state['active_run'].get('arm_index')!=self.index
                or state['arms'][self.index].get('localization_error')):
                raise RuntimeError('Stale or inactive arm runner')
            if estimate>plan['config']['input_estimate_gate']:
                raise RuntimeError('Input byte gate exceeded')
            existing=[c for c in state['calls'] if c['arm_index']==self.index]
            if self.cursor<len(existing):
                call=existing[self.cursor]
                if call['status']!='settled' or call['request_sha256']!=request_hash:
                    raise RuntimeError('Cached request diverged or outcome unknown')
                response=settle(self.path,deepcopy(call));self.cursor+=1
                return response
            if (self.cursor!=len(existing) or len(existing)>=3
                or len(state['calls'])>=plan['max_calls']
                or any(c['status']!='settled' for c in state['calls'])):
                raise RuntimeError('Quota exhausted or outcome requires review')
            spent,pending=totals(state)
            if spent+pending+followup.RESERVE>Decimal(plan['limit_cny']):
                state.update(status='halted',stop_reason='budget_exhausted');commit(self.path,state)
                raise RuntimeError('Full next reservation exceeds the fixed cohort budget')
            storage_capacity=response_store.capacity(self.path)
            if not storage_capacity:
                state.update(status='halted',stop_reason='response_storage_exhausted');commit(self.path,state)
                raise RuntimeError('Raw response storage is full; no request sent')
            identity=arms_for(plan)[self.index]
            call={'index':len(state['calls']),'arm_index':self.index,'ordinal':self.cursor,
                  'source_id':identity['source_id'],'arm':identity['arm'],'status':'reserved',
                  'reservation_cny':str(followup.RESERVE),'request_sha256':request_hash,
                  'input_byte_estimate':estimate}
            if guidance.is_guidance(plan):call.update(guidance.axis_fields(plan,identity['arm']))
            state['calls'].append(call);commit(self.path,state);self.hook('reserved')
            try:
                if self.raw is not None:
                    received=self.raw(self.cursor,**bounded)
                elif state['mode']=='offline':
                    received=scripted_raw(self.cursor,**bounded)
                else:
                    from locagent_service import deepseek_http
                    if state['mode']=='simulation':
                        import httpx
                        transport=httpx.MockTransport(lambda request:httpx.Response(
                            200,content=scripted_raw(self.cursor),request=request))
                        received=deepseek_http.exchange(wire,'offline-simulation',transport=transport,max_response_bytes=storage_capacity)
                    else:
                        received=deepseek_http.exchange(wire,os.environ['DEEPSEEK_API_KEY'],max_response_bytes=storage_capacity)
                from locagent_service.deepseek_http import RawHTTP
                if isinstance(received,RawHTTP):
                    body=received.body
                    call.update(http_status=received.status,response_complete=received.complete,
                                transport_error_type=received.error_type)
                else:body=received
            except Exception as exc:
                call.update(status='outcome_unknown',error_type=type(exc).__name__)
                state.update(status='halted',stop_reason='outcome_unknown');commit(self.path,state)
                raise
            self.hook('sent')
            if not isinstance(body,bytes):
                raise RuntimeError('Original response bytes required; reservation retained')
            if len(body)>storage_capacity:
                body=body[:storage_capacity]
                call.update(response_complete=False,transport_error_type='ResponseStorageLimit')
            try:
                reference=response_store.persist(self.path,call['index'],body)
            except Exception as exc:
                call.update(status='outcome_unknown',error_type=type(exc).__name__)
                state.update(status='halted',stop_reason='response_storage_failure')
                commit(self.path,state)
                raise
            self.hook('body_saved')
            call.update(status='raw_received',raw_body_ref=reference,
                        raw_body_sha256=reference['sha256'])
            commit(self.path,state);self.hook('raw_saved')
            try:response=settle(self.path,call)
            except Exception as exc:
                call.update(status='outcome_unknown',error_type=type(exc).__name__)
                state.update(status='halted',stop_reason='invalid_usage_or_response');commit(self.path,state)
                raise
            commit(self.path,state);self.hook('settled');self.cursor+=1
            return response


def finish_arm(path,index,token,result,elapsed,hook=no_hook):
    path=Path(path).resolve()
    result=LocalizationResultView.model_validate(result,strict=True).model_dump()
    with budget.ledger_lock(path):
        state,_,_=load_state(path);identity=arms_for(state['plan'])[index]
        if (state['status']!='running' or state['active_run']['token']!=token
            or state['active_run'].get('arm_index')!=index or state['arms'][index]['status']!='running'
            or state['arms'][index].get('localization_error')
            or any(c['status']!='settled' for c in state['calls'])):
            raise RuntimeError('Result writer lost arm ownership')
        record={'plan_hash':state['plan_hash'],'arm_index':index,'source_id':identity['source_id'],
                **guidance.axis_fields(state['plan'],identity['arm']),'mode':'live' if state['mode']=='live' else 'offline','status':'completed',
                'result':result,'elapsed_seconds':elapsed,'calls_hash':call_hash(state,index)}
        target=result_path(path,index);target.parent.mkdir(exist_ok=True)
        if target.exists():raise RuntimeError('Existing result requires explicit audit, never overwrite')
        response_store.save_json(target,record);hook('result_saved')
        state['arms'][index].update(status='completed',result_sha256=digest(canonical(record)))
        commit(path,state);hook('arm_committed')


def execute_arm(path,index,token,parent_pid):
    if ctypes.CDLL(None).prctl(1,signal.SIGKILL)!=0 or os.getppid()!=parent_pid:
        os._exit(70)
    path=Path(path).resolve()
    state,_,_=load_state(path);sample=arms_for(state['plan'])[index]
    from locagent_service.offline import offline_engine
    if state['mode']=='live':
        from locagent_service.phased_admission import validate_claim
        validate_claim(path,state,spending=True)
    with (nullcontext() if state['mode']=='live' else offline_engine()):
        from locagent_service.sources import localize_prepared
        manifest,_=load_manifest(sample['source_id'])
        request=CreateTask(source_id=sample['source_id'],problem_statement=manifest['task']['problem_statement'],
            options={'max_iterations':3,'suppress_repeats':guidance.axis_fields(state['plan'],sample['arm'])['suppress_repeats']},max_attempts=1,timeout_seconds=300)
        started=time.monotonic()
        from util.localization_contract import LocalizationError
        try:
            kwargs = {'candidate_guidance': sample['arm']} if guidance.is_guidance(state['plan']) else {}
            result=localize_prepared(request,Provider(path,index,token),**kwargs)
        except LocalizationError as exc:
            fail_localization(path,index,token,exc)
            raise
        finish_arm(path,index,token,result.to_dict(),time.monotonic()-started)


class ExecutorExitUnknown(RuntimeError):
    """The owned child has not been confirmed reaped; fence and require review."""


from util.localization_contract import LocalizationError, ErrorCode


class ReapedProtocolError(LocalizationError):
    """Raised only after the owned subprocess and its process group have exited."""
    def __init__(self, index, token, exit_proof):
        super().__init__(ErrorCode.INVALID_RESPONSE,PROTOCOL_ERROR['message'])
        self.index=index;self.token=token;self.exit_proof=exit_proof


def child_executor(path,index,token):
    state,_,_=load_state(path)
    is_live=state['mode']=='live'
    if is_live:
        from locagent_service.phased_admission import validate_claim
        validate_claim(path,state,spending=True)
    env={**os.environ,'LOCAGENT_ALLOW_PAID':'1' if is_live else '0','LITELLM_LOCAL_MODEL_COST_MAP':'True',
         'HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1'}
    if not is_live:env.pop('DEEPSEEK_API_KEY',None)
    logfile=result_path(path,index).with_suffix('.worker.log');logfile.parent.mkdir(exist_ok=True)
    with logfile.open('a') as log:
        child=subprocess.Popen([sys.executable,'-B','-m','locagent_service.phased','arm',
            '--ledger',str(path),'--arm-index',str(index),'--run-token',token,
            '--parent-pid',str(os.getpid())],env=env,cwd=ROOT,
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code=child.wait(timeout=300)
            if type(code) is not int:
                raise ExecutorExitUnknown('Child wait did not confirm an exit')
        except BaseException as exc:
            try:
                code=child.poll()
                if code is None:
                    os.killpg(child.pid,signal.SIGTERM)
                    try:code=child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL)
                        code=child.wait(timeout=3)
                if type(code) is not int:
                    raise ExecutorExitUnknown('Child cleanup did not confirm an exit')
            except BaseException as cleanup_error:
                raise ExecutorExitUnknown('Owned child exit cannot be verified') from cleanup_error
            raise exc
    if code:
        state,_,_=load_state(path)
        detail=state['arms'][index].get('localization_error')
        if detail:
            if code==1 and detail==PROTOCOL_ERROR and any(c['arm_index']==index for c in state['calls']):
                # wait() reaps the exact child; signal 0 only checks for surviving group members.
                try:os.killpg(child.pid,0)
                except ProcessLookupError:pass
                except OSError as exc:
                    raise ExecutorExitUnknown('Cannot verify executor process group exit') from exc
                else:raise ExecutorExitUnknown('Executor process group still exists')
                raise ReapedProtocolError(index,token,{'pid':child.pid,'parent_pid':os.getpid(),
                    'returncode':code,'process_group_empty':True,'confirmed_at_utc':utc_now()})
            raise LocalizationError(ErrorCode(detail['code']),detail['message'])
        raise RuntimeError('Arm process failed; explicit audit required')



def utc_now():
    return datetime.now(timezone.utc).isoformat()


def close_run_timing(state, elapsed):
    active = state.get('active_run')
    if active:
        state.setdefault('runs', []).append({
            'phase':active.get('phase'), 'started_at_utc':active.get('started_at_utc'),
            'finished_at_utc':utc_now(), 'elapsed_seconds':elapsed,
        })
    state['active_run'] = None


def halt_failed_run(path, token, exc, elapsed, arm_elapsed=None):
    # Catchable parent/child failures stop the cohort; no automatic resume or resend.
    from util.localization_contract import LocalizationError
    code = (exc.code.value if isinstance(exc,LocalizationError) else
            'executor_exit_unverified' if isinstance(exc,ExecutorExitUnknown) else
            'child_timeout' if isinstance(exc,subprocess.TimeoutExpired) else
            'interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'executor_error')
    with budget.ledger_lock(path):
        state,_,_=load_state(path)
        active=state.get('active_run')
        if not active or active.get('token')!=token:
            return
        index=active.get('arm_index')
        if index is not None and state['arms'][index]['status']=='running':
            uncertain=isinstance(exc,ExecutorExitUnknown) or any(
                c['status']!='settled' for c in state['calls'] if c['arm_index']==index)
            state['arms'][index].update(
                status='blocked' if uncertain else 'failed',
                failure={'code':code,'error_type':type(exc).__name__},
                elapsed_seconds=arm_elapsed,attempt_elapsed_seconds=arm_elapsed,calls_hash=call_hash(state,index))
        state.update(status='halted',stop_reason=state.get('stop_reason') or code,
            terminal_failure={'code':code,'error_type':type(exc).__name__})
        close_run_timing(state,elapsed)
        commit(path,state)


def fail_localization(path,index,token,exc):
    # Child communicates a stable error without provider text, credentials or guesses.
    with budget.ledger_lock(path):
        state,_,_=load_state(path)
        active=state.get('active_run')
        if (state['status']!='running' or state['arms'][index]['status']!='running'
            or not active or active.get('token')!=token or active.get('arm_index')!=index):
            raise RuntimeError('Failure writer lost arm ownership')
        state['arms'][index]['localization_error']=exc.to_dict()
        commit(path,state)

def complete_protocol_failure(path,index,token,exc,elapsed,hook=no_hook):
    # Called while run_phase holds the exclusive phase lock. No replay or owner repair.
    with budget.ledger_lock(path):
        state,_,_=load_state(path);active=state.get('active_run')
        if (not isinstance(exc,ReapedProtocolError) or exc.index!=index or exc.token!=token
            or exc.exit_proof.get('parent_pid')!=os.getpid()
            or state['status']!='running' or state.get('terminal_failure') or state.get('stop_reason')
            or not active or active.get('token')!=token or active.get('parent_pid')!=os.getpid()
            or active.get('arm_index')!=index or state['arms'][index]['status']!='running'
            or state['arms'][index].get('localization_error')!=PROTOCOL_ERROR
            or result_path(path,index).exists()
            or any(c['status']!='settled' for c in state['calls'])
            or any(a['status']=='running' for i,a in enumerate(state['arms']) if i!=index)):
            raise RuntimeError('Protocol failure continuation preconditions not satisfied')
        call=malformed_argument_call(path,state,index)
        if call['index']!=len(state['calls'])-1:raise RuntimeError('Concurrent/later call evidence')
        proof={'policy':FAILURE_POLICY,'plan_hash':state['plan_hash'],'arm_index':index,
            'source_id':arms_for(state['plan'])[index]['source_id'],'run_token':token,
            'calls_hash':call_hash(state,index),'call_index':call['index'],
            'raw_body_sha256':call['raw_body_sha256'],'error':deepcopy(PROTOCOL_ERROR),
            'executor':deepcopy(exc.exit_proof)}
        state['arms'][index].update(status='failed',failure={'code':'invalid_response','error_type':'LocalizationError'},
            elapsed_seconds=elapsed,attempt_elapsed_seconds=elapsed,calls_hash=call_hash(state,index),
            protocol_failure=proof,terminal_sha256=digest(canonical(proof)))
        protocol_failure_evidence(path,state,index)
        hook('before_protocol_failure_commit')
        commit(path,state)
        hook('protocol_failure_committed')
        load_state(path)  # Read back both durable heads before any subsequent arm.


def run_phase(path,phase_name, *, labels=None, executor=child_executor,hook=no_hook,live=False):
    if live and not Path(path).exists():refuse_live()
    with phase_lock(path) as path:
        with budget.ledger_lock(path):
            state,_,_=load_state(path);plan=state['plan'];check_labels(plan,labels);verify_sources(plan)
            if live != (state['mode']=='live'):
                raise RuntimeError('Live ledger requires explicit --live; mode cannot change')
            if live:
                from locagent_service.phased_admission import validate_claim
                validate_claim(path,state,spending=True)
            if (state['status']!='ready' or state['next_phase']>=len(plan['phases'])
                or plan['phases'][state['next_phase']]['name']!=phase_name):
                raise RuntimeError('Out-of-order/duplicate stage or explicit recovery required')
            phase=plan['phases'][state['next_phase']]
            token=uuid4().hex
            state.update(status='running',active_run={'token':token,'parent_pid':os.getpid(),
                'phase':phase_name,'started_at_utc':utc_now()})
            commit(path,state)
        started=time.monotonic()
        arm_started=None
        try:
            hook('phase_started')
            for index in range(phase['start'],phase['end']):
                arm_started=None
                with budget.ledger_lock(path):
                    state,_,_=load_state(path)
                    if terminal_arm(state['arms'][index]):continue
                    if state['arms'][index]['status']!='pending':raise RuntimeError('Arm requires audit')
                    state['arms'][index]['status']='running';state['active_run']['arm_index']=index
                    commit(path,state)
                arm_started=time.monotonic()
                hook('arm_claimed')
                try:
                    executor(path,index,token)
                except ReapedProtocolError as exc:
                    complete_protocol_failure(path,index,token,exc,time.monotonic()-arm_started,hook)
                    continue
                with budget.ledger_lock(path):
                    state,_,_=load_state(path)
                    if state['arms'][index]['status']!='completed':raise RuntimeError('Arm did not publish a durable result')
                    state['arms'][index]['attempt_elapsed_seconds']=time.monotonic()-arm_started
                    commit(path,state)
            hook('before_checkpoint')
            with budget.ledger_lock(path):
                state,_,_=load_state(path)
                state['checkpoints'].append(checkpoint_for(state,phase))
                state['next_phase']+=1
                state['status']='complete' if state['next_phase']==len(plan['phases']) else 'ready'
                close_run_timing(state,time.monotonic()-started)
                commit(path,state)
            hook('checkpoint_saved')
            return state
        except BaseException as exc:
            try:
                halt_failed_run(path,token,exc,time.monotonic()-started,
                    time.monotonic()-arm_started if arm_started is not None else None)
            except Exception as persistence_error:
                # Never repair ownership heads implicitly. Preserve the original failure.
                exc.add_note('Terminal state could not be persisted; explicit audit required: '
                             + type(persistence_error).__name__)
            raise


def audit_recovery(path, *, labels=None):
    with phase_lock(path) as path, budget.ledger_lock(path):
        state,marker,lag=load_state(path,allow_one_step=True,allow_body_errors=True)
        check_labels(state['plan'],labels);verify_sources(state['plan'])
        if lag:
            marker.update(revision=state['revision'],state_sha256=digest(canonical(state)))
            response_store.save_json(owner_path(state['plan'],state['mode']),marker)
        audit={'before_sha256':digest(canonical(state)),'id':uuid4().hex,'recovered_raw_calls':[]}
        errors=validate_state(path,state,allow_body_errors=True)
        if errors:
            audit.update(recoverable=False,reason='response_evidence_invalid',
                body_evidence_errors=errors,prior_active_run=deepcopy(state.get('active_run')),
                prior_terminal_failure=deepcopy(state.get('terminal_failure')),
                prior_stop_reason=state.get('stop_reason'),executor_exit_confirmed=False)
            # Clearing the active token fences a possibly live executor; it is not
            # evidence that the executor exited. Calls/reserves/proof refs stay intact.
            for index,arm in enumerate(state['arms']):
                if arm['status']=='running':
                    arm.update(status='blocked',elapsed_seconds=None,calls_hash=call_hash(state,index),
                        failure={'code':'response_evidence_invalid','error_type':'EvidenceLossAudit'})
            state.update(status='halted',stop_reason='response_evidence_invalid',
                terminal_failure={'code':'response_evidence_invalid','error_type':'EvidenceLossAudit'})
            close_run_timing(state,None)
            state['audits'].append(audit)
            # commit checks owned ledger heads without re-reading damaged bodies.
            # Any ledger/owner write failure propagates; no successful audit is returned.
            commit(path,state)
            return audit
        if state['status'] in ('ready','complete') and not lag:
            raise RuntimeError('No interrupted stage to audit')
        if state.get('terminal_failure') or any(a.get('failure') and not a.get('protocol_failure') for a in state['arms']):
            audit.update(recoverable=False,reason='terminal_failure_requires_new_review')
            state['status']='halted'
            close_run_timing(state,None)
            state['audits'].append(audit);commit(path,state)
            return audit
        unknown=any(c['status'] in ('reserved','outcome_unknown') for c in state['calls'])
        if not unknown:
            for call in state['calls']:
                if call['status']=='raw_received':
                    try:settle(path,call);audit['recovered_raw_calls'].append(call['index'])
                    except Exception:unknown=True;break
        if unknown or state.get('stop_reason') in ('budget_exhausted','response_storage_exhausted'):
            state.update(status='halted',stop_reason='outcome_requires_review' if unknown else state['stop_reason'])
            audit['recoverable']=False;state['audits'].append(audit);commit(path,state)
            return audit
        if state.get('active_run'):
            # An available phase lock or dead parent is not proof of executor exit.
            # No liveness guesses or PID signalling: fence, preserve evidence, never resume.
            for index,arm in enumerate(state['arms']):
                if arm['status']=='running':
                    detail=arm.get('localization_error')
                    arm.update(status='blocked',elapsed_seconds=None,calls_hash=call_hash(state,index),
                        failure={'code':detail['code'] if detail else 'executor_exit_unverified',
                                 'error_type':'InterruptedRun'})
            state.update(status='halted',stop_reason='executor_exit_unverified')
            close_run_timing(state,None)
            audit.update(recoverable=False,reason='executor_exit_unverified')
            state['audits'].append(audit);commit(path,state)
            return audit
        if any(a['status']=='running' or (a.get('localization_error') and not a.get('protocol_failure')) for a in state['arms']):
            for index,arm in enumerate(state['arms']):
                if arm['status']=='running':
                    arm.update(status='blocked',elapsed_seconds=None,calls_hash=call_hash(state,index),
                        failure={'code':'executor_exit_unverified','error_type':'InterruptedRun'})
            state.update(status='halted',stop_reason='executor_exit_unverified')
            audit.update(recoverable=False,reason='executor_exit_unverified')
            state['audits'].append(audit);commit(path,state)
            return audit
        state['status']='complete' if state['next_phase']==len(state['plan']['phases']) else 'ready'
        close_run_timing(state,None)
        audit['recoverable']=True;state['audits'].append(audit);commit(path,state)
        return audit


def summary(path,labels):
    path=Path(path).resolve()
    with budget.ledger_lock(path):
        state,_,_=load_state(path);answers=check_labels(state['plan'],labels)
        records=[]
        for i,arm in enumerate(state['arms']):
            if arm['status']=='completed':
                record=record_for(path,state,i)
                record['attempt_elapsed_seconds']=arm.get('attempt_elapsed_seconds')
                records.append(record)
            else:
                identity=arms_for(state['plan'])[i]
                records.append({'source_id':identity['source_id'],**guidance.axis_fields(state['plan'],identity['arm']),
                    'mode':'live' if state['mode']=='live' else 'offline','status':arm['status'],
                    'elapsed_seconds':arm.get('elapsed_seconds'),
                    'terminal_failure_verified':arm['status']=='failed' and 'protocol_failure' in arm,
                    'attempt_elapsed_seconds':arm.get('attempt_elapsed_seconds')})
    from locagent_service.evaluate import summarize
    experiment_complete = (state['status']=='complete'
        and state['next_phase']==len(state['plan']['phases'])
        and len(state['checkpoints'])==len(state['plan']['phases'])
        and state.get('active_run') is None
        and not state.get('terminal_failure') and not state.get('stop_reason'))
    result=summarize(state['plan'],records,answers,execution_mode=state['mode'],
                     experiment_complete=experiment_complete)
    runs=state.get('runs',[])
    unknown_durations=sum(r.get('elapsed_seconds') is None for r in runs)
    unknown_durations+=int(state.get('active_run') is not None)
    legacy_duration_unknown='runs' not in state and any(a['status']!='pending' for a in state['arms'])
    known_phase_seconds=sum(r.get('elapsed_seconds') or 0 for r in runs)
    result['timing']={'phase_wall_seconds':None if unknown_durations or legacy_duration_unknown else known_phase_seconds,
        'recorded_phase_wall_seconds':known_phase_seconds,'unfinished_phase_count':int(state.get('active_run') is not None),
        'duration_unknown':bool(unknown_durations or legacy_duration_unknown),
        'note':'Monotonic phase wall includes child startup/validation/failure. Completed-result seconds are separate. Historical/unclosed durations are unknown.'}
    real=state['mode']=='live'
    result.update(stage_status=state['status'],next_phase=state['next_phase'],
        execution_mode=state['mode'],simulated_calls=0 if real else len(state['calls']),
        simulated_spent_cny=None if real else state['spent_cny'],
        simulated_reserved_cny=None if real else state['reserved_cny'],
        paid_calls=len(state['calls']) if real else 0,
        reservation_note='Live call attempts; uncertain calls retain full reserve, not an invoice.' if real else
                         'Simulated accounting only; no provider usage or spending authority.')
    if real:
        result['billing']={'spent_upper_cny':state['spent_cny'],'reserved_cny':state['reserved_cny'],
                           'unknown_call_count':sum(c['status']!='settled' for c in state['calls'])}
        for arm,metrics in result['arms'].items():
            calls=[c for c in state['calls'] if str(c['arm']).lower()==arm]
            metrics.update(prompt_tokens=sum(c.get('prompt_tokens',0) for c in calls),
                completion_tokens=sum(c.get('completion_tokens',0) for c in calls),
                unknown_call_count=sum(c['status']!='settled' for c in calls),
                cost_upper_cny=str(sum((Decimal(c['cost_upper_cny']) if c['status']=='settled' else
                                       Decimal(c['reservation_cny']) for c in calls),Decimal(0))))
    if guidance.is_guidance(state['plan']):
        result['returned_models'] = sorted({c['returned_model'] for c in state['calls'] if c.get('returned_model')})
        for scope, scoped in result['scoring_groups'].items():
            ids={s['source_id'] for s in state['plan']['samples'] if s['role']==scope}
            for arm, metrics in scoped['arms'].items():
                calls=[c for c in state['calls'] if c['source_id'] in ids and str(c['arm']).lower()==arm]
                metrics.update(call_count=len(calls), unknown_call_count=sum(c['status']!='settled' for c in calls),
                    prompt_tokens=sum(c.get('prompt_tokens',0) for c in calls) if real else None,
                    completion_tokens=sum(c.get('completion_tokens',0) for c in calls) if real else None,
                    cost_upper_cny=str(sum((Decimal(c['cost_upper_cny']) if c['status']=='settled' else Decimal(c['reservation_cny']) for c in calls),Decimal(0))) if real else None)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    make=sub.add_parser('plan');make.add_argument('--cohort',choices=['new20','regression5',guidance.COHORT],required=True)
    make.add_argument('--mode',choices=['offline','live'],default='offline');make.add_argument('--experiment-id',required=True);make.add_argument('--labels',required=True);make.add_argument('--output',required=True)
    init=sub.add_parser('init');init.add_argument('--plan',required=True);init.add_argument('--ledger',required=True);init.add_argument('--labels',required=True);init.add_argument('--live',action='store_true');init.add_argument('--simulate-http',action='store_true');init.add_argument('--approval-id')
    draft=sub.add_parser('approval-proposal');draft.add_argument('--plan',required=True);draft.add_argument('--approval-id',required=True);draft.add_argument('--output',required=True)
    run=sub.add_parser('run');run.add_argument('--ledger',required=True);run.add_argument('--phase',required=True);run.add_argument('--labels',required=True);run.add_argument('--live',action='store_true')
    audit=sub.add_parser('audit-recovery');audit.add_argument('--ledger',required=True);audit.add_argument('--labels',required=True)
    show=sub.add_parser('summary');show.add_argument('--ledger',required=True);show.add_argument('--labels',required=True);show.add_argument('--output',required=True)
    arm=sub.add_parser('arm');arm.add_argument('--ledger',required=True);arm.add_argument('--arm-index',type=int,required=True)
    arm.add_argument('--run-token',required=True);arm.add_argument('--parent-pid',type=int,required=True)
    args=p.parse_args()
    if args.command=='plan':value=make_plan(args.cohort,args.experiment_id,args.labels,args.output,args.mode)
    elif args.command=='init':value=initialize(args.ledger,read_json(args.plan),labels=args.labels,live=args.live,simulate_http=args.simulate_http,approval_id=args.approval_id)
    elif args.command=='approval-proposal':
        from locagent_service.phased_admission import proposal
        plan=validate_plan(read_json(args.plan));value=proposal(plan,args.approval_id)
        with Path(args.output).open('xb') as f:f.write(canonical(value))
    elif args.command=='run':value=run_phase(args.ledger,args.phase,labels=args.labels,live=args.live)
    elif args.command=='audit-recovery':value=audit_recovery(args.ledger,labels=args.labels)
    elif args.command=='summary':
        value=summary(args.ledger,args.labels);response_store.save_json(args.output,value)
    else:execute_arm(args.ledger,args.arm_index,args.run_token,args.parent_pid);return
    if args.command=='audit-recovery':
        print(json.dumps({'command':args.command,'status':'recoverable' if value['recoverable'] else 'blocked',**value}))
        if not value['recoverable']:raise SystemExit(2)
        return
    print(json.dumps({'command':args.command,'status':value.get('status',value.get('stage_status','ok')),
                      'plan_hash':digest(canonical(value)) if args.command=='plan' else value.get('plan_hash')}))

if __name__=='__main__':main()
