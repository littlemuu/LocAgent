import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from locagent_service.budget import BudgetProvider,initialize_ledger,LIVE_CONFIG,RESERVATION_BASIS
from locagent_service.evaluate import summarize
from locagent_service.models import CreateTask
from locagent_service.sources import canonical,digest,load_manifest

CONFIG=dict(LIVE_CONFIG)


def fixed_plan(sources=None):
    return {'version':2,'sources':sources or ['s'],'arms':[False,True],
            'denominator_per_arm':1,'config':dict(CONFIG),'max_calls':6,'budget_cny':20,
            'reservation_basis':dict(RESERVATION_BASIS),'worst_case_reservation_cny':'18.911232'}


def confirmed_pricing(plan):
    from datetime import datetime,timezone
    return {'version':1,'plan_hash':digest(canonical(plan)),'provider':'deepseek-official',
            'currency':'CNY','input_cache_miss_peak_per_million':'3','output_peak_per_million':'12',
            'all_charges_included':True,'confirmed_at_utc':datetime.now(timezone.utc).isoformat()}


class Response:
    class Usage:
        prompt_tokens=100
        completion_tokens=20
    usage=Usage()
    model='controlled-test'
    def model_dump(self,**kwargs):return {'model':self.model,'usage':{'prompt_tokens':100,'completion_tokens':20}}


class EvaluationTests(unittest.TestCase):
    def ledger(self,root,limit=20,max_calls=6):
        path=Path(root)/'budget.json'
        plan=fixed_plan();plan.update(budget_cny=limit,max_calls=max_calls)
        for name,value in [('AUTHORIZATION_PATH',Path(root)/'authorization.json'),
                           ('AUTHORIZED_PLAN_HASH',digest(canonical(plan)))]:
            context=patch('locagent_service.budget.'+name,value)
            context.start();self.addCleanup(context.stop)
        initialize_ledger(path,plan,confirmed_pricing(plan))
        return path

    def test_budget_reserves_before_call_and_passes_hard_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp)
            def completion(**kwargs):
                state=json.loads(path.read_text())
                self.assertEqual(state['calls'][-1]['status'],'reserved')
                self.assertGreater(float(state['reserved']),0)
                self.assertEqual(kwargs['num_retries'],0)
                self.assertEqual(kwargs['max_tokens'],512)
                return Response()
            provider=BudgetProvider(path,'s',CONFIG,completion)
            provider(messages=[])
            self.assertEqual(json.loads(path.read_text())['calls'][0]['status'],'response_received')

    def test_unknown_paid_response_halts_and_never_refunds_or_replays(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp)
            calls=[]
            def timeout(**kwargs):
                calls.append(1);raise TimeoutError()
            provider=BudgetProvider(path,'s',CONFIG,timeout)
            with self.assertRaises(TimeoutError):provider(messages=[])
            before=path.read_text()
            with self.assertRaises(RuntimeError):provider(messages=[])
            self.assertEqual(path.read_text(),before)
            self.assertEqual(len(calls),1)
            self.assertTrue(json.loads(before)['halted'])
            self.assertEqual(json.loads(before)['calls'][0]['status'],'outcome_unknown')

    def test_crash_after_reservation_cannot_be_restarted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp)
            state=json.loads(path.read_text())
            state['calls']=[{'status':'reserved'}]
            path.write_text(json.dumps(state))
            provider=BudgetProvider(path,'s',CONFIG,lambda **kw:self.fail('network called'))
            with self.assertRaises(RuntimeError):provider(messages=[])

    def test_budget_input_and_call_limits_fail_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):self.ledger(tmp,limit=0.001)
            self.assertFalse((Path(tmp)/'budget.json').exists())
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp)
            provider=BudgetProvider(path,'s',CONFIG,lambda **kw:Response())
            with self.assertRaises(RuntimeError):provider(messages=[{'content':'a'*CONFIG['input_estimate_gate']}])
            for _ in range(3):provider(messages=[])
            with self.assertRaises(RuntimeError):provider(messages=[])

    def test_real_provider_is_disabled_without_explicit_enablement(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(RuntimeError):BudgetProvider.from_env('s',CONFIG)

    def test_budget_rejects_unauthorized_more_than_20_and_existing_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):self.ledger(tmp,21)
            self.ledger(tmp,20)
            with self.assertRaises(FileExistsError):self.ledger(tmp,20)

    def test_fixed_denominator_counts_failures_missing_and_preserves_rank(self):
        plan={'sources':['a','b'],'arms':[False,True]}
        labels={s:{'files':['correct.py'],'entities':['correct.py:f']} for s in plan['sources']}
        records=[{'source_id':'a','suppress_repeats':False,'mode':'live','status':'completed',
                  'result':{'found_files':['wrong.py','correct.py'],'found_entities':['correct.py:f']}}]
        result=summarize(plan,records,labels)['arms']
        self.assertEqual(result['false']['metrics']['files_recall_at_1'],0)
        self.assertEqual(result['false']['metrics']['files_recall_at_3'],0.5)
        self.assertEqual(result['true']['failed_or_missing'],2)
        self.assertEqual(result['true']['metrics']['entities_recall_at_3'],0)
        with self.assertRaises(ValueError):summarize(plan,records+records,labels)

    def test_fixture_never_reports_quality_tokens_or_money(self):
        plan={'sources':['a'],'arms':[False,True]}
        labels={'a':{'files':['correct.py'],'entities':['correct.py:f']}}
        records=[{'source_id':'a','suppress_repeats':False,'mode':'offline','status':'completed'}]
        summary=summarize(plan,records,labels)
        self.assertFalse(summary['quality_claim_allowed'])
        for arm in summary['arms'].values():
            self.assertIsNone(arm['prompt_tokens'])
            self.assertIsNone(arm['cost_cny'])
            self.assertTrue(all(v is None for v in arm['metrics'].values()))

    def test_manifest_and_artifact_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LOCAGENT_SOURCE_ROOT':tmp}):
            bundle=Path(tmp)/'bundle'
            bundle.mkdir();(bundle/'file').write_text('original')
            manifest={'bundle':'bundle','artifacts':{'file':digest(b'original')},'engine':{}}
            data=canonical(manifest);source='prepared-'+digest(data)
            path=Path(tmp)/(source+'.json');path.write_bytes(data)
            self.assertEqual(load_manifest(source)[0],manifest)
            (bundle/'file').write_text('changed')
            with self.assertRaises(ValueError):load_manifest(source)
            path.write_bytes(data+b' ')
            with self.assertRaises(ValueError):load_manifest(source)

    def test_request_lifecycle_bounds_and_source_ids_are_strict(self):
        for fields in ({'timeout_seconds':0},{'max_attempts':6},{'source_id':'prepared-../bad'},
                       {'timeout_seconds':True},{'max_attempts':'2'}):
            with self.assertRaises(ValueError):CreateTask(problem_statement='test',**fields)


class ConfigurationTests(unittest.TestCase):
    def test_env_file_is_opt_in_and_rejects_loose_permissions(self):
        from locagent_service.configure import load_env_file
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{},clear=True):
            path=Path(tmp)/'.env'
            path.write_text('DEEPSEEK_API_KEY=local-test-only\nLOCAGENT_ALLOW_PAID=0\n')
            path.chmod(0o644)
            with self.assertRaises(ValueError):load_env_file(path)
            self.assertNotIn('DEEPSEEK_API_KEY',os.environ)
            path.chmod(0o600)
            load_env_file(path)
            self.assertEqual(os.environ['LOCAGENT_ALLOW_PAID'],'0')

    def test_env_does_not_interpolate_or_load_unrelated_settings(self):
        from locagent_service.configure import load_env_file
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{},clear=True):
            path=Path(tmp)/'.env';path.write_text('UNRELATED=1\n');path.chmod(0o600)
            with self.assertRaises(ValueError):load_env_file(path)
            self.assertNotIn('UNRELATED',os.environ)


class EvaluationFailureRegressionTests(unittest.TestCase):
    def result(self):
        return {'instance_id':'sample','status':'success','found_files':['correct.py'],
                'found_modules':[],'found_entities':['correct.py:f'],'iterations':1,
                'usage':{'prompt_tokens':17,'completion_tokens':3},'raw_output':'correct.py',
                'return_records':{},'messages':[{'role':'tool','content':'evidence'}]}

    def completed(self,source='s',arm=False,mode='offline'):
        return {'source_id':source,'suppress_repeats':arm,'mode':mode,
                'status':'completed','result':self.result(),'elapsed_seconds':0.1}

    def inputs(self,root,sources=None):
        sources=sources or ['s']
        labels=Path(root)/'labels.json'
        labels.write_text(json.dumps({s:{'files':['correct.py'],'entities':['correct.py:f']} for s in sources}))
        plan={'sources':sources,'arms':[False,True],'denominator_per_arm':len(sources),
              'config':CONFIG,'labels_sha256':digest(labels.read_bytes()),
              'max_calls':len(sources)*2*CONFIG['max_calls'],'budget_cny':2}
        path=Path(root)/'plan.json';path.write_text(json.dumps(plan))
        return path,labels

    def test_failed_retained_result_scores_zero_and_cannot_supply_usage(self):
        row=self.completed(mode='live')
        row['status']='failed'
        labels={'s':{'files':['correct.py'],'entities':['correct.py:f']}}
        summary=summarize({'sources':['s'],'arms':[False,True]},[row],labels)
        arm=summary['arms']['false']
        self.assertEqual(arm['failed_or_missing'],1)
        self.assertEqual(arm['completed'],0)
        self.assertTrue(all(score==0 for score in arm['metrics'].values()))
        self.assertEqual(arm['prompt_tokens'],0)
        self.assertEqual(arm['tool_message_characters'],0)

    def test_nonzero_exit_timeout_and_failed_envelope_strip_completed_payload(self):
        from locagent_service.evaluate import collect_child_record
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'record.json'
            path.write_text(json.dumps(self.completed()))
            for kwargs in ({'returncode':7},{'failure_reason':'HardTimeout'}):
                row=collect_child_record(path,'s',False,'offline',**kwargs)
                self.assertEqual(row['status'],'failed')
                self.assertNotIn('result',row)
            stale=self.completed();stale.update(status='failed',error_type='EngineFailed')
            path.write_text(json.dumps(stale))
            row=collect_child_record(path,'s',False,'offline',returncode=0)
            self.assertEqual(row['status'],'failed')
            self.assertNotIn('result',row)

    def test_missing_corrupt_and_invalid_records_keep_summary_and_denominator(self):
        from contextlib import redirect_stdout
        import io
        import subprocess
        from locagent_service.evaluate import run
        cases=[None,b'{"source_id":',b'\xff',b'null',b'[]',b'{}',
               json.dumps({**self.completed(),'result':None}).encode(),
               json.dumps({**self.completed(),'result':{'found_files':['correct.py']}}).encode(),
               json.dumps({**self.completed(),'source_id':'wrong'}).encode(),
               json.dumps({**self.completed(),'suppress_repeats':0}).encode(),
               json.dumps({**self.completed(),'elapsed_seconds':float('nan')}).encode(),
               json.dumps({**self.completed(),'result':{
                   **self.result(),'messages':[{'role':'tool','content':12}]}}).encode()]
        for data in cases:
            with self.subTest(data=data),tempfile.TemporaryDirectory() as tmp:
                plan,labels=self.inputs(tmp);out=Path(tmp)/'run'
                def child(cmd,**kwargs):
                    dest=Path(cmd[cmd.index('--output')+1])
                    arm=cmd[cmd.index('--suppress')+1]=='true'
                    if arm:
                        dest.write_text(json.dumps(self.completed(arm=True)))
                    elif data is not None:
                        dest.write_bytes(data)
                    return subprocess.CompletedProcess(cmd,0,'','')
                with patch('locagent_service.evaluate.load_manifest',return_value=({'config':CONFIG},None)), \
                     patch('locagent_service.evaluate.subprocess.run',side_effect=child),redirect_stdout(io.StringIO()):
                    summary=run(plan,labels,out)
                self.assertTrue((out/'summary.json').is_file())
                self.assertEqual(summary['denominator_per_arm'],1)
                self.assertEqual(summary['arms']['false']['failed_or_missing'],1)
                self.assertEqual(summary['arms']['true']['completed'],1)
                normalized=json.loads((out/'0-false.json').read_text())
                self.assertEqual(normalized['status'],'failed')
                self.assertNotIn('result',normalized)
                if data is not None:self.assertEqual((out/'0-false.child.json').read_bytes(),data)

    def test_actual_partial_write_then_abnormal_child_exit_still_summarizes(self):
        from contextlib import redirect_stdout
        import io
        import subprocess
        import sys
        from locagent_service.evaluate import run
        real_run=subprocess.run
        with tempfile.TemporaryDirectory() as tmp:
            plan,labels=self.inputs(tmp);out=Path(tmp)/'run'
            def crash(cmd,**kwargs):
                dest=cmd[cmd.index('--output')+1]
                return real_run([sys.executable,'-c',
                    'import os,sys; f=open(sys.argv[1],"wb"); f.write(b"{"); f.flush(); os.fsync(f.fileno()); os._exit(7)',
                    dest],capture_output=True,timeout=5)
            with patch('locagent_service.evaluate.load_manifest',return_value=({'config':CONFIG},None)), \
                 patch('locagent_service.evaluate.subprocess.run',side_effect=crash),redirect_stdout(io.StringIO()):
                summary=run(plan,labels,out)
            self.assertTrue((out/'summary.json').exists())
            for arm in ('false','true'):
                row=json.loads((out/f'0-{arm}.json').read_text())
                self.assertEqual(row['child_returncode'],7)
                self.assertEqual(row['record_error'],'CorruptChildResult')
                self.assertEqual((out/f'0-{arm}.child.json').read_bytes(),b'{')
                self.assertEqual(summary['arms'][arm]['failed_or_missing'],1)

    def test_nonzero_exit_with_valid_completed_file_never_scores_as_completed(self):
        from contextlib import redirect_stdout
        import io
        import subprocess
        from locagent_service.evaluate import run
        with tempfile.TemporaryDirectory() as tmp:
            plan,labels=self.inputs(tmp);out=Path(tmp)/'run'
            def child(cmd,**kwargs):
                arm=cmd[cmd.index('--suppress')+1]=='true'
                Path(cmd[cmd.index('--output')+1]).write_text(json.dumps(self.completed(arm=arm)))
                return subprocess.CompletedProcess(cmd,1,'','')
            with patch('locagent_service.evaluate.load_manifest',return_value=({'config':CONFIG},None)), \
                 patch('locagent_service.evaluate.subprocess.run',side_effect=child),redirect_stdout(io.StringIO()):
                summary=run(plan,labels,out)
            self.assertTrue(all(a['completed']==0 for a in summary['arms'].values()))
            self.assertNotIn('result',json.loads((out/'0-false.json').read_text()))

    def test_timeout_partial_file_is_retained_and_summary_is_written(self):
        from contextlib import redirect_stdout
        import io
        import subprocess
        from locagent_service.evaluate import run
        with tempfile.TemporaryDirectory() as tmp:
            plan,labels=self.inputs(tmp);out=Path(tmp)/'run'
            def timeout(cmd,**kwargs):
                Path(cmd[cmd.index('--output')+1]).write_text('{')
                raise subprocess.TimeoutExpired(cmd,300)
            with patch('locagent_service.evaluate.load_manifest',return_value=({'config':CONFIG},None)), \
                 patch('locagent_service.evaluate.subprocess.run',side_effect=timeout),redirect_stdout(io.StringIO()):
                summary=run(plan,labels,out)
            self.assertEqual(json.loads((out/'0-false.json').read_text())['error_type'],'HardTimeout')
            self.assertEqual((out/'0-false.child.json').read_text(),'{')
            self.assertTrue((out/'summary.json').exists())

    def test_live_failure_preserves_billing_denominator_and_stops_future_calls(self):
        # Simulated live envelope only: subprocess is replaced; no provider is invoked.
        from contextlib import redirect_stdout
        import io
        import subprocess
        from locagent_service.evaluate import run
        with tempfile.TemporaryDirectory() as tmp:
            plan,labels=self.inputs(tmp);out=Path(tmp)/'run'
            value=fixed_plan();value['labels_sha256']=digest(labels.read_bytes())
            plan.write_text(json.dumps(value))
            confirmation=Path(tmp)/'pricing.json'
            confirmation.write_text(json.dumps(confirmed_pricing(value)))
            persisted=[]
            def child(cmd,**kwargs):
                ledger=Path(kwargs['env']['LOCAGENT_BUDGET_LEDGER'])
                state=json.loads(ledger.read_text())
                state['calls']=[{'source_id':'s','arm':'false','status':'response_received',
                                 'prompt_tokens':17,'completion_tokens':3,
                                 'reservation_cny':'3.151872','cost_upper_cny':'0.000087'}]
                state['reserved']='3.151872'
                ledger.write_text(json.dumps(state));persisted.append(ledger.read_bytes())
                Path(cmd[cmd.index('--output')+1]).write_text('{"unfinished":')
                return subprocess.CompletedProcess(cmd,1,'','')
            with patch('locagent_service.evaluate.load_manifest',return_value=({'config':CONFIG},None)), \
                 patch('locagent_service.evaluate.subprocess.run',side_effect=child) as launch, \
                 patch.dict(os.environ,{'LOCAGENT_ALLOW_PAID':'1','DEEPSEEK_API_KEY':'test-placeholder-not-a-credential'}), \
                 redirect_stdout(io.StringIO()):
                with patch('locagent_service.budget.AUTHORIZATION_PATH',Path(tmp)/'authorization.json'), \
                     patch('locagent_service.budget.AUTHORIZED_PLAN_HASH',digest(canonical(value))):
                    summary=run(plan,labels,out,live=True,pricing_confirmation=confirmation)
            self.assertEqual(launch.call_count,1)
            self.assertEqual(summary['denominator_per_arm'],1)
            for arm in summary['arms'].values():
                self.assertEqual(arm['failed_or_missing'],1)
                self.assertTrue(all(value==0 for value in arm['metrics'].values()))
            self.assertEqual(summary['arms']['false']['prompt_tokens'],17)
            self.assertEqual(summary['arms']['false']['cost_upper_cny'],'0.000087')
            self.assertEqual((out/'budget.json').read_bytes(),persisted[0])
            self.assertTrue((out/'summary.json').exists())
