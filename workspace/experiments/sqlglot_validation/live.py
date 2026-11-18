"""Explicitly admitted single-case SQLGlot runner; no retries or resume."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from readonly_agent.authority import Admission, save_new
from readonly_agent.core import Snapshot, Limits, digest, encoded
from readonly_agent.journal import Ledger
from readonly_agent.live_run import parent_alive
from .control import (ROOT, FROZEN, candidate, frozen, SuiteAuthority, SuiteAdmission,
                      SuiteLedger, CaseAuthority, read_status, PROJECT)


def worker(authority,h,identifier,arm,init,alive=parent_alive):
    suite=SuiteAdmission(authority,h,init['suite_token'])
    case_auth=CaseAuthority(suite,identifier,arm)
    admission=Admission(case_auth,case_auth.item['plan_hash'],init['case_token'])
    record=admission.validate()
    case=json.loads((PROJECT/case_auth.item['case_file']).read_text())
    snapshot=Snapshot((PROJECT/case_auth.item['case_file']).parent/case['root'],case['source_files'])
    # No offline script or scoring file is passed to the live SDK.
    from readonly_agent.live_session import LiveSession
    from readonly_agent.openhands_replay import run_sdk_case
    from readonly_agent.bridge import LocAgentProcessRetriever
    session=LiveSession(Ledger(Path(record['run_dir'])/'ledger.sqlite',admission.plan_hash),arm,admission,init.pop('key'),alive)
    engine=Path(record['plan']['locagent_engine']['root'])
    retriever=LocAgentProcessRetriever(snapshot,python=engine/'.venv/bin/python',engine_root=engine) if arm=='retrieval' else None
    try:
        return run_sdk_case(snapshot=snapshot,issue=case['issue'],script=None,
            output_dir=Path(record['run_dir'])/arm,retriever=retriever,limits=Limits(max_requests=4),live=session)
    finally:session.forget_key()


def launch_arm(suite,child,identifier,arm,key):
    if suite.authority.root != ROOT:raise PermissionError('production_worker_requires_default_authority')
    record=child.validate();run=Path(record['run_dir'])
    command=[sys.executable,'-B','-m','experiments.sqlglot_validation.live','_worker','--suite-hash',suite.hash,
             '--case',identifier,'--arm',arm]
    with (run/(arm+'.log')).open('xb') as log:
        process=subprocess.Popen(command,cwd=PROJECT,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,
            start_new_session=True,env={'PATH':os.defpath,'DO_NOT_TRACK':'1','LITELLM_LOCAL_MODEL_COST_MAP':'True',
                                       'OH_PERSISTENCE_DIR':str(run/(arm+'-profiles'))})
        try:
            process.stdin.write(encoded({'suite_token':suite.token,'case_token':child.token,'key':key})+b'\n')
            process.stdin.flush()
            status=process.wait(timeout=360)
            if status:raise RuntimeError('arm_process_failed')
        finally:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait();process.stdin.close()
    return json.loads((run/arm/'result.json').read_text())


def execute(suite,key,arm_runner=launch_arm):
    """Internal coordinator; requires an already consumed suite admission."""
    ledger=SuiteLedger.create(suite)
    save_new(Path(ledger.record['run_dir'])/'execution.json',
             {'mode':'live' if arm_runner is launch_arm else 'mocked_live_transport'})
    identifier=arm=None;child_ledger=None;started=None
    try:
        for item in suite.validate()['plan']['base_manifest']['cases']:
            identifier=item['id'];arm=None;child_ledger=None;started=None
            ledger.begin_case(identifier)
            case_auth=CaseAuthority(suite,identifier);case_auth.prepare()
            child=case_auth.claim(item['plan_hash'])
            child_ledger=Ledger.create(Path(child.validate()['run_dir'])/'ledger.sqlite',item['plan'],admission=child)
            for arm in item['arm_order']:
                ledger.begin_arm(identifier,arm);started=time.perf_counter()
                result=arm_runner(suite,child,identifier,arm,key)
                ledger.finish_arm(identifier,arm,result,child_ledger,time.perf_counter()-started)
            ledger.finish_case(identifier,child_ledger)
        result=ledger.summary();save_new(Path(ledger.record['run_dir'])/'result.json',result)
        return result
    except BaseException as error:
        reason=type(error).__name__
        if child_ledger is not None:
            try:
                child_ledger.halt(None,reason)
                reason=child_ledger.summary()['reason'] or reason
            except Exception:pass
        ledger.halt(reason,identifier,arm,time.perf_counter()-started if started is not None else None)
        result=ledger.summary();save_new(Path(ledger.record['run_dir'])/'stopped.json',result)
        return result
    finally:key=None


def run(h,*,live=False,env_api_key=False,authority=None):
    if live is not True or env_api_key is not True:raise PermissionError('explicit_suite_live_and_env_required')
    authority=authority or SuiteAuthority()
    authority.read(h)
    if (authority.folder(h)/'claim.json').exists():raise PermissionError('suite_already_consumed')
    if not sys.stdin.isatty():raise PermissionError('local_interactive_terminal_required')
    from readonly_agent.local_env import load_selected_key
    key=load_selected_key()
    try:return execute(authority.claim(h),key)
    finally:key=None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['freeze','proposal','authorize','run','status','_worker'])
    p.add_argument('--suite-hash');p.add_argument('--consent');p.add_argument('--currency')
    p.add_argument('--input-ceiling');p.add_argument('--output-ceiling')
    p.add_argument('--all-charges-included',action='store_true')
    p.add_argument('--live',action='store_true');p.add_argument('--env-api-key',action='store_true')
    p.add_argument('--case');p.add_argument('--arm',choices=['baseline','retrieval'])
    args=p.parse_args();authority=SuiteAuthority()
    if args.action=='freeze':
        plan=candidate();FROZEN.parent.mkdir(mode=0o700,parents=True,exist_ok=False);save_new(FROZEN,plan)
        print(json.dumps({'suite_hash':digest(plan),'authorization':'not_granted'}))
    elif args.action=='proposal':print(json.dumps({'suite_hash':digest(frozen()),'plan':frozen()},indent=2))
    elif args.action=='authorize':
        authority.approve(frozen(),args.suite_hash,consent=args.consent,currency=args.currency,
            input_ceiling=args.input_ceiling,output_ceiling=args.output_ceiling,all_charges_included=args.all_charges_included)
        print('Suite grant recorded; no key read or request sent.')
    elif args.action=='status':print(json.dumps(read_status(authority,args.suite_hash),indent=2))
    elif args.action=='run':
        result=run(args.suite_hash,live=args.live,env_api_key=args.env_api_key)
        from .report import write_report
        write_report(authority,args.suite_hash)
        print(json.dumps(result,indent=2))
        if result['status']!='completed':raise SystemExit(1)
    else:
        init=json.loads(sys.stdin.buffer.readline(80000))
        if set(init)!={'suite_token','case_token','key'}:raise PermissionError('invalid_worker_input')
        result=worker(authority,args.suite_hash,args.case,args.arm,init)
        if result['status']!='completed':raise SystemExit(1)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Stopped: '+type(error).__name__+'. No automatic retry.',file=sys.stderr)
        raise SystemExit(1) from None
