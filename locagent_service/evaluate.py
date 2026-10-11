"""Predeclared paired suppression experiment. Offline results are plumbing only."""
import argparse
from contextlib import redirect_stdout
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from locagent_service.sources import load_manifest,canonical,digest
from locagent_service.models import CreateTask, LocalizationResultView
from locagent_service.budget import (initialize_ledger, reserve_cost, validate_live_plan,
    validate_pricing_confirmation, validate_authorized_plan, RESERVATION_BASIS, paid_mode,
    recover_zero_use_ledger, RECOVERABLE_PLAN_HASH)


def make_plan(sources, labels, output):
    if len(sources)!=1 or len(set(sources))!=len(sources):
        raise ValueError('Exactly one fixed sample source required')
    manifests=[load_manifest(s)[0] for s in sources]
    answers=json.loads(Path(labels).read_text())
    if set(answers)!=set(sources):
        raise ValueError('Exactly one ground-truth entry per fixed sample required')
    for answer in answers.values():
        if not answer.get('files') or not answer.get('entities'):
            raise ValueError('File and entity labels required')
    configs=[m['config'] for m in manifests]
    if any(c!=configs[0] for c in configs):
        raise ValueError('Both arms/all samples must share one model/index configuration')
    worst=sum((reserve_cost(c)*c['max_calls']*2 for c in configs))
    if worst>20:
        raise ValueError('Pilot reservation exceeds authorized CNY 20')
    plan={'version':2,'sources':sources,'arms':[False,True],'denominator_per_arm':len(sources),
          'config':configs[0],'labels_sha256':digest(Path(labels).read_bytes()),
          'max_calls':sum(c['max_calls']*2 for c in configs),'budget_cny':20,
          'reservation_basis':RESERVATION_BASIS,
          'worst_case_reservation_cny':str(worst),
          'metric':'file/entity recall@1 and @3; failures and missing rows count as zero',
          'sample_role':'development pilot, not held-out benchmark',
          'pricing_source':'https://api-docs.deepseek.com/quick_start/pricing/',
          'pricing_checked':'2026-10-08',
          'reservation_note':'Full context reserve; fresh account confirmation required; never refund unknown calls'}
    validate_live_plan(plan)
    with Path(output).open('x') as stream:
        json.dump(plan,stream,indent=2)
    return plan


def scripted_provider(search_protocol='legacy'):
    from litellm import ModelResponse
    final = ({'files': ['requests/models.py'],
              'entities': ['requests/models.py:Response.iter_content']}
             if search_protocol == 'bounded-v1' else
             {'thought': 'requests/models.py\nclass: Response\nfunction: Response.iter_content'})
    steps=iter([
        ('search_code_snippets',{'search_terms':['requests/models.py:Response.iter_content']}),
        ('get_entity_contents',{'entity_names':['requests/models.py:Response.iter_content']}),
        ('finish',final)])
    def provider(**kwargs):
        name,args=next(steps)
        return ModelResponse(model='offline-scripted',choices=[{'index':0,'message':{
            'role':'assistant','content':None,'tool_calls':[{'id':'offline-call','type':'function',
            'function':{'name':name,'arguments':json.dumps(args)}}]},'finish_reason':'tool_calls'}],
            usage={'prompt_tokens':1,'completion_tokens':1,'total_tokens':2})
    return provider


def execute_one(source, suppress, mode, output):
    manifest,_=load_manifest(source)
    req=CreateTask(source_id=source,problem_statement=manifest['task']['problem_statement'],
        options={'max_iterations':manifest['config']['max_calls'],'suppress_repeats':suppress},
        max_attempts=1,timeout_seconds=300)
    started=time.monotonic()
    record={'source_id':source,'suppress_repeats':suppress,'mode':mode,'status':'started'}
    with Path(output).open('x') as stream:json.dump(record,stream)
    try:
        if mode=='offline':
            from locagent_service.offline import offline_engine
            with offline_engine(),redirect_stdout(io.StringIO()):
                from locagent_service.sources import localize_prepared
                result=localize_prepared(req,scripted_provider(manifest['config'].get('search_protocol','legacy')))
        else:
            from locagent_service.sources import localize
            with redirect_stdout(io.StringIO()):
                result=localize(req)
        record.update(status='completed',result=result.to_dict())
    except Exception as exc:
        record.update(status='failed',error_type=type(exc).__name__)
    record['elapsed_seconds']=time.monotonic()-started
    record['attempt_elapsed_seconds']=record['elapsed_seconds']
    write_json_atomic(output,record)
    return record



def write_json_atomic(path, value):
    path=Path(path)
    temporary=path.with_name(path.name+'.tmp')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def collect_child_record(path, source, arm, mode, *, returncode=None, failure_reason=None):
    """Normalize every child outcome; untrusted/partial results never become scores."""
    record={'source_id':source,'suppress_repeats':arm,'mode':mode,'status':'failed'}
    error=None
    try:
        row=json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        error='MissingChildResult'
    except (OSError,UnicodeError,json.JSONDecodeError):
        error='CorruptChildResult'
    else:
        try:
            if (not isinstance(row,dict) or row.get('source_id')!=source
                or type(row.get('suppress_repeats')) is not bool or row['suppress_repeats']!=arm
                or row.get('mode')!=mode or row.get('status') not in ('completed','failed')):
                raise ValueError('Invalid child envelope')
            elapsed=row.get('elapsed_seconds')
            if (type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed<0):
                raise ValueError('Invalid duration')
            record['elapsed_seconds']=elapsed
            attempt=row.get('attempt_elapsed_seconds')
            if attempt is not None:
                if type(attempt) not in (int,float) or not math.isfinite(attempt) or attempt<0:
                    raise ValueError('Invalid attempt duration')
                record['attempt_elapsed_seconds']=attempt
            if row['status']=='completed':
                result=LocalizationResultView.model_validate(row.get('result'),strict=True).model_dump()
                if any(not isinstance(msg.get('role'),str)
                       or (msg.get('content') is not None and not isinstance(msg['content'],str))
                       for msg in result['messages']):
                    raise ValueError('Invalid result messages')
                record.update(status='completed',result=result)
            else:
                if not isinstance(row.get('error_type'),str):
                    raise ValueError('Invalid failure')
                record['error_type']=row['error_type']
        except (ValueError,TypeError,OverflowError):
            error='InvalidChildResult'
    if failure_reason or returncode or error:
        record['status']='failed'
        record['error_type']=failure_reason or ('ChildExecutionFailed' if returncode else error)
        if error:
            record['record_error']=error
    if record['status']!='completed':
        record.pop('result',None)
    if returncode is not None:
        record['child_returncode']=returncode
    return record


def completed_result(row):
    """Failures may retain forensic payloads, but cannot supply scoring/usage inputs."""
    result=row.get('result')
    return result if row.get('status')=='completed' and isinstance(result,dict) else {}



def valid_finish(row):
    """True/False when termination is known; None when a completed record is ambiguous.

    GraphLocalizer emits legacy success/empty only after a finished trajectory and
    successful location parsing. Bounded diagnostics take precedence; absence of
    both diagnostics and a recognized result status is not evidence of failure.
    """
    if row.get('status') != 'completed':
        return False  # Failed/missing tasks retain their fixed-denominator zero.
    result = completed_result(row)
    status = result.get('status')
    if status == 'iteration_limit':
        return False
    diagnostics = result.get('diagnostics')
    if diagnostics is not None:
        reason = diagnostics.get('termination_reason') if isinstance(diagnostics, dict) else None
        return reason == 'finished' if isinstance(reason, str) and reason else None
    if status in ('success', 'empty'):
        return True
    return None


def summarize(plan,records,answers, *, execution_mode=None, experiment_complete=False):
    expected={(s,arm) for s in plan['sources'] for arm in plan['arms']}
    if len(set(plan['sources'])) != len(plan['sources']) or set(answers) != set(plan['sources']):
        raise ValueError('Exactly one label record per fixed source required')
    for answer in answers.values():
        if (not isinstance(answer, dict) or any(
                not isinstance(answer.get(label), list)
                or any(not isinstance(x, str) or not x for x in answer[label])
                or len(set(answer[label])) != len(answer[label])
                for label in ('files', 'entities')) or not answer['files']):
            raise ValueError('Unique nonempty file labels and an explicit function list required')
    applicable = [source for source in plan['sources'] if answers[source]['entities']]
    declared = plan.get('function_applicable_sources')
    if declared is not None and declared != applicable:
        raise ValueError('Function applicability differs from the predeclared cohort')
    by_key={}
    for row in records:
        key=(row['source_id'],row['suppress_repeats'])
        if key not in expected or key in by_key:
            raise ValueError('Unexpected or duplicate evaluation record')
        by_key[key]=row
    modes={r['mode'] for r in records}
    if len(modes)>1:raise ValueError('Cannot combine fixture and real results')
    if execution_mode is None:
        execution_mode = 'live' if modes == {'live'} else 'offline'
    if execution_mode not in ('live', 'offline', 'simulation'):
        raise ValueError('Unknown execution mode')
    expected_record_mode = 'live' if execution_mode == 'live' else 'offline'
    if modes and modes != {expected_record_mode}:
        raise ValueError('Record mode differs from execution mode')
    if type(experiment_complete) is not bool:
        raise ValueError('Experiment completion must be explicit')
    real = execution_mode == 'live'
    def terminal(row):
        return row['status']=='completed' or (
            plan.get('policy')=='locagent-phased-v3'
            and plan.get('arm_failure_policy')=='settled-json-arguments-with-reaped-executor-v1'
            and row['status']=='failed' and row.get('terminal_failure_verified') is True)
    all_terminal = len(by_key)==len(expected) and all(terminal(r) for r in records)
    quality_allowed = real and experiment_complete and all_terminal
    summary={'mode':execution_mode, 'quality_claim_allowed':quality_allowed,
             'metrics_scope':'completed_experiment' if quality_allowed else 'progress' if real else 'offline',
             'experiment_complete':experiment_complete and all_terminal,
             'denominator_per_arm':len(plan['sources']),'arms':{},
             'paired_outcomes':{
                 'planned_pairs':len(plan['sources']),
                 'terminal_pairs':sum(all((s,a) in by_key and terminal(by_key[(s,a)])
                     for a in plan['arms']) for s in plan['sources']),
                 'both_completed_pairs':sum(all(by_key.get((s,a),{}).get('status')=='completed'
                     for a in plan['arms']) for s in plan['sources'])}}
    for arm in plan['arms']:
        rows=[by_key.get((source,arm),{'status':'missing'}) for source in plan['sources']]
        metrics={}
        coverage_adjusted={}
        for field,label in (('found_files','files'),('found_entities','entities')):
            eligible = plan['sources'] if label == 'files' else applicable
            for k in (1,3):
                score=0
                for source,row in zip(plan['sources'],rows):
                    truth=set(answers[source][label])
                    if not truth:
                        continue  # Explicitly not applicable, not a successful empty answer.
                    predicted=set(completed_result(row).get(field,[])[:k])
                    score+=len(truth & predicted)/len(truth)
                metrics[label+'_recall_at_'+str(k)]=(score/len(eligible)
                    if real and eligible else None)
                if label == 'entities':
                    coverage_adjusted['function_recall_at_'+str(k)+'_full_cohort']=(
                        score/len(rows) if real and rows else None)
        outcomes = [valid_finish(row) for row in rows]
        unknown_finishes = sum(value is None for value in outcomes)
        valid = sum(value is True for value in outcomes)
        completed_times=[r.get('elapsed_seconds') for r in rows if r['status']=='completed']
        completed_seconds=(sum(completed_times) if all(v is not None for v in completed_times) else None)
        summary['arms'][str(arm).lower()]={
            'completed':sum(r['status']=='completed' for r in rows),
            'failed_or_missing':sum(r['status']!='completed' for r in rows),
            'prompt_tokens':sum(completed_result(r).get('usage',{}).get('prompt_tokens',0) for r in rows) if real else None,
            'completion_tokens':sum(completed_result(r).get('usage',{}).get('completion_tokens',0) for r in rows) if real else None,
            # Compatibility alias: completed-result time only, never total run wall time.
            'elapsed_seconds':completed_seconds,
            'completed_result_seconds':completed_seconds,
            'recorded_attempt_seconds':sum(r.get('attempt_elapsed_seconds') or 0 for r in rows),
            'attempt_duration_unknown_count':sum(r['status'] not in ('missing','pending')
                and r.get('attempt_elapsed_seconds') is None for r in rows),
            'failed':sum(r['status']=='failed' for r in rows),
            'terminal':sum(terminal(r) for r in rows),
            'completion_rate':sum(r['status']=='completed' for r in rows)/len(rows) if real and rows else None,
            'failure_rate':sum(r['status']=='failed' for r in rows)/len(rows) if real and rows else None,
            'terminal_rate':sum(terminal(r) for r in rows)/len(rows) if real and rows else None,
            'blocked':sum(r['status']=='blocked' for r in rows),
            'running':sum(r['status']=='running' for r in rows),
            'not_started':sum(r['status'] in ('missing','pending') for r in rows),
            'tool_message_characters':sum(len(msg.get('content') or '')
                for r in rows for msg in completed_result(r).get('messages',[]) if msg['role']=='tool'),
            'metrics':metrics,
            'metric_denominators':{'files':len(rows),'functions':len(applicable)},
            'function_not_applicable':len(rows)-len(applicable),
            'function_applicable_sources':applicable.copy(),
            'coverage_adjusted_metrics':coverage_adjusted,
            'valid_finish_count':valid if real and not unknown_finishes else None,
            'valid_finish_unknown_count':unknown_finishes if real else None,
            'valid_finish_rate':valid/len(rows) if real and rows and not unknown_finishes else None,
            'cost_cny':None,
            'cost_note':'Use budget ledger for all calls including failed attempts; upper bound, not invoice'}
    return summary


def load_live_pricing(plan, pricing_path):
    """Complete non-secret live preflight, also used BEFORE env-file loading."""
    if plan.get('version') == 3:
        from locagent_service.followup import load_live_pricing as followup_pricing
        return followup_pricing(plan, pricing_path)
    validate_live_plan(plan)
    validate_authorized_plan(plan)
    if pricing_path is None:
        raise ValueError('Live execution requires account pricing confirmation')
    confirmation=json.loads(Path(pricing_path).read_text())
    validate_pricing_confirmation(plan,confirmation)
    return confirmation


def run(plan_path,labels,out,live=False,pricing_confirmation=None,recover_zero_use_from=None):
    if recover_zero_use_from and not live:
        raise ValueError('Zero-use recovery requires explicit live execution')
    plan=json.loads(Path(plan_path).read_text())
    if digest(Path(labels).read_bytes())!=plan['labels_sha256']:
        raise ValueError('Labels changed after predeclaring the experiment')
    if (plan['arms'] != [False,True] or len(set(plan['sources'])) != len(plan['sources'])
        or plan['denominator_per_arm'] != len(plan['sources'])
        or any(load_manifest(source)[0]['config'] != plan['config'] for source in plan['sources'])
        or plan['max_calls'] != len(plan['sources'])*2*plan['config']['max_calls']):
        raise ValueError('Plan does not match fixed sources and pilot limits')
    if plan.get('version') == 3:
        from locagent_service.followup import validate_plan
        validate_plan(plan)
        if recover_zero_use_from:
            raise ValueError('Follow-up cannot migrate or reuse the first-pilot authorization')
    elif plan.get('version',1)==2:
        if live or digest(canonical(plan)) != RECOVERABLE_PLAN_HASH:
            validate_live_plan(plan)
    elif live or plan.get('version',1)!=1 or not 0 < plan['budget_cny'] <= 2:
        raise ValueError('Legacy plans are offline-only')
    confirmation=None
    if live:
        confirmation=load_live_pricing(plan,pricing_confirmation)
        if os.environ.get('LOCAGENT_ALLOW_PAID')!='1' or not os.environ.get('DEEPSEEK_API_KEY'):
            raise RuntimeError('Existing provider configuration and explicit paid enablement required')
    # A run directory is single-use. This deliberately cannot resume paid operations.
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    (out/'plan.json').write_text(json.dumps(plan,indent=2))
    mode='live' if live else 'offline'
    if live:
        if recover_zero_use_from:
            recover_zero_use_ledger(recover_zero_use_from,out/'budget.json',plan,confirmation)
        elif plan.get('version') == 3:
            from locagent_service.followup import initialize_ledger as initialize_followup
            initialize_followup(out/'budget.json',plan,confirmation)
        else:
            initialize_ledger(out/'budget.json',plan,confirmation)
    records=[]
    for index,source in enumerate(plan['sources']):
        order = plan['samples'][index]['arm_order'] if plan.get('version') == 3 else plan['arms']
        for arm in order:
            dest=out/f'{index}-{str(arm).lower()}.json'
            env={**os.environ,'LITELLM_LOCAL_MODEL_COST_MAP':'True',
                 'HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1'}
            if live:
                env['LOCAGENT_BUDGET_LEDGER']=str((out/'budget.json').resolve())
                env['LOCAGENT_EVALUATION_ARM']=str(arm).lower()
            try:
                process=subprocess.run([sys.executable,'-B','-m','locagent_service.evaluate',
                    'one','--source',source,'--suppress',str(arm).lower(),'--mode',mode,
                    '--output',str(dest)],env=env,capture_output=True,timeout=300)
                row=collect_child_record(dest,source,arm,mode,returncode=process.returncode)
            except subprocess.TimeoutExpired:
                row=collect_child_record(dest,source,arm,mode,failure_reason='HardTimeout')
            except OSError:
                row=collect_child_record(dest,source,arm,mode,failure_reason='ChildLaunchFailed')
            # Preserve even corrupt bytes for diagnosis; the canonical record is normalized.
            if dest.exists():
                dest.replace(dest.with_suffix('.child.json'))
            write_json_atomic(dest,row)
            records.append(row)
            # Any live failure may represent a paid unknown outcome. Preserve denominator;
            # report unexecuted arms as missing rather than silently retrying or excluding.
            if live and row['status']!='completed':break
        if live and records[-1]['status']!='completed':break
    summary=summarize(plan,records,json.loads(Path(labels).read_text()),
                      execution_mode=mode,experiment_complete=True)
    if live:
        from decimal import Decimal
        billing=json.loads((out/'budget.json').read_text())
        summary['billing']=billing
        for arm,metrics in summary['arms'].items():
            calls=[c for c in billing['calls'] if c.get('arm')==arm]
            metrics['prompt_tokens']=sum(c.get('prompt_tokens',0) for c in calls)
            metrics['completion_tokens']=sum(c.get('completion_tokens',0) for c in calls)
            metrics['unknown_call_count']=sum(c['status'] in ('reserved','raw_received','outcome_unknown') for c in calls)
            metrics['cost_upper_cny']=str(sum((Decimal(c['cost_upper_cny'] if c['status'] in ('settled','response_received') and 'cost_upper_cny' in c else c['reservation_cny'])
                                                   for c in calls),Decimal(0)))
            metrics['cost_note']='Peak-rate conservative CNY estimate; unknown calls use full reservation; not invoice'
    write_json_atomic(out/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='billing'},indent=2))
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    plan=sub.add_parser('plan')
    plan.add_argument('--source',action='append',required=True)
    plan.add_argument('--followup5',action='store_true')
    plan.add_argument('--labels',required=True);plan.add_argument('--output',required=True)
    runp=sub.add_parser('run')
    runp.add_argument('--env-file')
    runp.add_argument('--pricing-confirmation')
    runp.add_argument('--recover-zero-use-from')
    runp.add_argument('--plan',required=True);runp.add_argument('--labels',required=True)
    runp.add_argument('--output',required=True);runp.add_argument('--live',action='store_true')
    one=sub.add_parser('one')
    one.add_argument('--source',required=True);one.add_argument('--suppress',choices=('true','false'),required=True)
    one.add_argument('--mode',choices=('offline','live'),required=True);one.add_argument('--output',required=True)
    args=p.parse_args()
    if args.command=='plan':
        planner = make_plan
        if args.followup5:
            from locagent_service.followup import make_plan as planner
        planner(args.source,args.labels,args.output)
    elif args.command=='run':
        if args.recover_zero_use_from and not args.live:
            p.error('--recover-zero-use-from requires --live')
        if args.live and not args.pricing_confirmation:
            p.error('--live requires --pricing-confirmation before loading any env file')
        if args.live:
            load_live_pricing(json.loads(Path(args.plan).read_text()),args.pricing_confirmation)
        if args.env_file:
            from locagent_service.configure import load_env_file
            load_env_file(args.env_file)
        with paid_mode(args.live):
            run(args.plan,args.labels,args.output,args.live,args.pricing_confirmation,args.recover_zero_use_from)
    else:execute_one(args.source,args.suppress=='true',args.mode,args.output)


if __name__=='__main__':
    main()
