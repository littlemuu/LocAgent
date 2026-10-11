"""Explicit operator-issued, plan-bound, single-use live admission.

The approval store is a trusted local operator boundary, not a signature service.
No command here approves a proposal; .env and legacy approvals confer no authority.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import re

from locagent_service import budget, followup, deepseek_http
from locagent_service.sources import canonical, digest

ROOT = Path(__file__).resolve().parents[1]
APPROVAL_ROOT = ROOT/'outputs/stage4/phased-live-approvals'
CONSUMED_ROOT = ROOT/'outputs/stage4/phased-live-consumed'
KIND = 'locagent-phased-live-approval-v1'


def binding(plan):
    return {'plan_hash':digest(canonical(plan)), 'cohort':plan['cohort'],
            'experiment_id':plan['experiment_id'], 'model':plan['config']['model'],
            'wire_model':deepseek_http.WIRE_MODEL, 'endpoint':deepseek_http.ENDPOINT,
            'config_sha256':digest(canonical(plan['config'])),
            'runtime_sha256':digest(canonical(plan['runtime_hashes'])),
            'labels_sha256':plan['labels_sha256'],
            'metric_sha256':plan['metric_specification_sha256'],
            'limit_cny':plan['limit_cny'], 'max_calls':plan['max_calls'],
            'max_calls_per_arm':plan['max_calls_per_arm'],
            'reservation_cny':plan['reservation_cny'], 'reservation_basis':plan['reservation_basis']}


def proposal(plan, approval_id):
    valid_id(approval_id)
    return {'version':1,'kind':KIND,'approval_id':approval_id,'approved':False,
            'independent_review_passed':False,'approval_reference':'','approved_at_utc':'',
            'binding':binding(plan),
            'pricing':{'version':1,'plan_hash':digest(canonical(plan)),
                       'provider':'deepseek-official','currency':'CNY',
                       'input_cache_miss_peak_per_million':'2','output_peak_per_million':'8',
                       'all_charges_included':False,'confirmed_at_utc':''}}


def valid_id(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}',value):
        raise ValueError('Safe explicit approval ID required')
    return value


def timestamp(value):
    when=datetime.fromisoformat(value.replace('Z','+00:00'))
    if when.tzinfo is None or when.utcoffset().total_seconds()!=0:
        raise ValueError('UTC approval/pricing timestamp required')
    age=(datetime.now(timezone.utc)-when).total_seconds()
    if age<0:raise ValueError('Future approval/pricing timestamp')
    return age


def validate_record(plan, record, *, fresh=False):
    expected=set(proposal(plan,valid_id(record.get('approval_id'))))
    if (set(record)!=expected or type(record.get('version')) is not int or record['version']!=1
        or record.get('kind')!=KIND or record.get('approved') is not True
        or record.get('independent_review_passed') is not True
        or not isinstance(record.get('approval_reference'),str) or not record['approval_reference'].strip()
        or canonical(record.get('binding'))!=canonical(binding(plan))
        or plan.get('mode')!='live' or plan.get('live_authorized') is not False):
        raise ValueError('Explicit reviewed approval bound to this exact live plan required')
    ages=[timestamp(record['approved_at_utc']),timestamp(record['pricing']['confirmed_at_utc'])]
    if fresh and max(ages)>86400:
        raise ValueError('Approval and pricing must be at most 24 hours old')
    pricing=dict(record['pricing'])
    # Historical ledger inspection stays possible after expiry; spending does not.
    if not fresh:pricing['confirmed_at_utc']=datetime.now(timezone.utc).isoformat()
    rates=budget.validate_pricing_confirmation(plan,pricing)
    if (pricing['currency']!='CNY' or rates!={'input_cny_per_million':'2','output_cny_per_million':'8'}):
        raise ValueError('This plan requires confirmed all-in CNY peak rates 2/8')
    return record


def load_approval(plan, approval_id):
    name=valid_id(approval_id);path=APPROVAL_ROOT/(name+'.json')
    if APPROVAL_ROOT.is_symlink() or path.is_symlink():
        raise ValueError('Approval store cannot use symlinks')
    record=followup.raw_json(path.read_bytes())
    if record.get('approval_id')!=name:raise ValueError('Approval identity differs from filename')
    return validate_record(plan,record,fresh=True)


def require_switch():
    # Check switch before looking up any existing secret, and never load .env.
    if os.environ.get('LOCAGENT_ALLOW_PAID')!='1':
        raise RuntimeError('Paid execution switch remains disabled')


def claim(path, plan, record):
    validate_record(plan,record,fresh=True)
    CONSUMED_ROOT.mkdir(parents=True,exist_ok=True)
    if CONSUMED_ROOT.is_symlink():raise ValueError('Approval consumption store cannot be a symlink')
    target=CONSUMED_ROOT/(record['approval_id']+'.json')
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    receipt={'kind':KIND,'approval_id':record['approval_id'],
             'approval_sha256':digest(canonical(record)), 'plan_hash':digest(canonical(plan)),
             'ledger_path':str(Path(path).resolve())}
    budget.save(target,receipt)  # Partial claims remain consumed; no automatic reset.
    return {'record':record,'receipt':receipt}


def validate_claim(path, state, *, spending=False):
    admission=state['admission'];record=admission['record'];plan=state['plan']
    validate_record(plan,record,fresh=spending)
    if APPROVAL_ROOT.is_symlink() or (APPROVAL_ROOT/(record['approval_id']+'.json')).is_symlink():
        raise ValueError('Approval store cannot use symlinks')
    actual=load_approval(plan,record['approval_id']) if spending else followup.raw_json(
        (APPROVAL_ROOT/(record['approval_id']+'.json')).read_bytes())
    if canonical(actual)!=canonical(record):raise ValueError('Approval removed, revoked or changed')
    target=CONSUMED_ROOT/(record['approval_id']+'.json')
    if target.is_symlink():raise ValueError('Consumed approval cannot be a symlink')
    receipt=followup.raw_json(target.read_bytes())
    expected={'kind':KIND,'approval_id':record['approval_id'],'approval_sha256':digest(canonical(record)),
              'plan_hash':state['plan_hash'],'ledger_path':str(Path(path).resolve())}
    if receipt!=expected or admission['receipt']!=expected:
        raise ValueError('Consumed approval belongs to another ledger/plan')
    if spending:require_switch()
