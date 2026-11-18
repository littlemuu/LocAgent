"""Reviewed one-use launcher. Preparation never reads credentials or grants access."""
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from readonly_agent.core import digest
from readonly_agent.authority import private, save_new
from experiments.cohort_preflight.entry import ROOT, read, sha
from .parent import Parent, validate
from .batch import execute

PLAN = ROOT/'verification/finish-v5-batch-v2/live.json'
OUT = ROOT/'verification/finish-v5-live-v1'
LOCK = ROOT/'verification/finish-live-v5-preparation/final-lock.json'


def validate_confirmation(plan, approval):
    expected = {'plan_hash':digest(plan), 'consent':f"APPROVE FINISHV5 {digest(plan)} NEW8 NEWCNY17 TOTAL209 TOTALCNY20",
        'currency':'CNY','input_ceiling':'2','output_ceiling':'8','all_charges_included':True,
        'destination':'https://api.deepseek.com/chat/completions','model':'deepseek-flash',
        'send_categories':plan['cases'][0]['plan']['send_categories'], 'excluded':['gold','reference_patch'],
        'max_requests':8,'new_micro_cny_limit':17000000,'automatic_retry':False}
    if set(approval)!=set(expected)|{'confirmed_at','pricing_checked_at','user_confirmation'}:
        raise PermissionError('exact_new_confirmation_required')
    for name, value in expected.items():
        if type(approval[name]) is not type(value) or approval[name]!=value:
            raise PermissionError('confirmation_scope_changed')
    if not isinstance(approval['user_confirmation'],str) or not approval['user_confirmation'].strip():
        raise PermissionError('user_confirmation_required')
    now=datetime.now(timezone.utc)
    for field in ('confirmed_at','pricing_checked_at'):
        time=datetime.fromisoformat(approval[field])
        if time.tzinfo is None or not timedelta(0)<=now-time<timedelta(hours=24):
            raise PermissionError('fresh_confirmation_and_price_check_required')


def matching_batch(data):
    for line in data.splitlines():
        fields=line.split(None,1)
        if fields and b'python' in fields[0].rsplit(b'/',1)[-1].lower() and any(
            marker in line for marker in (b'experiments.cohort_five',b'experiments.cohort_dev37_v4',b'experiments.cohort_finish_v5')):
            # Ignore this launcher; the exclusive output directory is its one-use lock.
            if b'experiments.cohort_finish_v5.launch' not in line:
                return True
    return False


def launch(confirmation_path):
    confirmation_path=Path(confirmation_path).absolute()
    private(confirmation_path)
    plan=read(PLAN); validate(plan)
    approval=read(confirmation_path); validate_confirmation(plan,approval)
    lock=read(LOCK)
    if lock['live_plan_hash']!=digest(plan):
        raise PermissionError('frozen_plan_changed')
    for name, expected in lock['files'].items():
        if sha(ROOT/name)!=expected:
            raise PermissionError('frozen_material_changed')
    # Neither expired nor failed matching grants may be reclaimed.
    for folder in [ROOT/'verification',*ROOT.glob('authority*')]:
        if folder.is_dir():
            for path in folder.rglob('grant.json'):
                record=read(path)
                if record.get('hash',record.get('plan_hash'))==digest(plan):
                    raise PermissionError('existing_grant_no_restart')
    proc=subprocess.run(['ps','-axo','comm=,args='],capture_output=True,check=True)
    if matching_batch(proc.stdout):
        raise PermissionError('batch_already_running')
    # This exclusive directory consumes the launcher even if later key loading fails.
    OUT.mkdir(mode=0o700,exist_ok=False)
    save_new(OUT/'launch-claimed.json',{'plan_hash':digest(plan),'retry':False})
    save_new(OUT/'confirmation.json',approval)
    key=None
    try:
        from readonly_agent.local_env import check_metadata, select_path, load_selected_key
        check_metadata(select_path()); key=load_selected_key()
        parent=Parent(OUT/'authority')
        parent.prepare(plan,consent=approval['consent'],currency=approval['currency'],
            input_ceiling=approval['input_ceiling'],output_ceiling=approval['output_ceiling'],
            all_charges_included=approval['all_charges_included'])
        return execute(parent,parent.claim(),key=key)
    except BaseException as error:
        save_new(OUT/'launch-error.json',{'error_type':type(error).__name__,'retry':False})
        raise
    finally:
        key=None


def main():
    if len(sys.argv)!=3 or sys.argv[1]!='--execute-approved':
        raise PermissionError('explicit_approved_invocation_required')
    result=launch(sys.argv[2])
    print(json.dumps({k:result[k] for k in ('halted','reason','all_child_requests',
        'request_pending_micro_cny','all_child_settled_micro_cny')}))

if __name__=='__main__':
    try: main()
    except BaseException as error:
        print('Stopped: '+type(error).__name__+'. No automatic retry.',file=sys.stderr)
        raise SystemExit(1) from None
