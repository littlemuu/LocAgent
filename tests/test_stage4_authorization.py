"""Regression for one total approval and pricing-before-env; no real credentials/I/O."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import locagent_service.budget as budget
from locagent_service.evaluate import main, run
from locagent_service.sources import canonical, digest
from test_stage4_evaluation import CONFIG, Response, fixed_plan, confirmed_pricing
import test_stage4_evaluation as helpers


class AuthorizationBoundaryTests(unittest.TestCase):
    def scope(self, root, plan):
        for name,value in [('AUTHORIZATION_PATH',Path(root)/'shared-approval.json'),
                           ('AUTHORIZED_PLAN_HASH',digest(canonical(plan)))]:
            context=patch.object(budget,name,value)
            context.start();self.addCleanup(context.stop)

    def test_two_output_runs_cannot_spend_twice_even_after_six_successful_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);labels=root/'labels.json'
            labels.write_text(json.dumps({'s':{'files':['correct.py'],'entities':['correct.py:f']}}))
            plan=fixed_plan();plan['labels_sha256']=digest(labels.read_bytes())
            self.scope(root,plan)
            planpath=root/'plan.json';planpath.write_text(json.dumps(plan))
            confirmation=root/'prices.json';confirmation.write_text(json.dumps(confirmed_pricing(plan)))
            model_calls=[]
            def completion(**kwargs):model_calls.append(1);return Response()
            def child(command,**kwargs):
                arm=command[command.index('--suppress')+1]=='true'
                provider=budget.BudgetProvider(kwargs['env']['LOCAGENT_BUDGET_LEDGER'],
                                               's',CONFIG,completion,arm=arm)
                for _ in range(3):provider(messages=[])
                record=helpers.EvaluationFailureRegressionTests().completed(arm=arm,mode='live')
                Path(command[command.index('--output')+1]).write_text(json.dumps(record))
                return subprocess.CompletedProcess(command,0,'','')
            with patch('locagent_service.evaluate.load_manifest',return_value=({'config':CONFIG},None)), \
                 patch('locagent_service.evaluate.subprocess.run',side_effect=child) as launcher, \
                 patch.dict(os.environ,{'LOCAGENT_ALLOW_PAID':'1','DEEPSEEK_API_KEY':'offline-placeholder'}), \
                 redirect_stdout(io.StringIO()):
                first=run(planpath,labels,root/'out1',True,confirmation)
                before=(root/'out1/budget.json').read_bytes()
                # Even a newly refreshed confirmation is the SAME first-pilot approval.
                confirmation.write_text(json.dumps(confirmed_pricing(plan)))
                with self.assertRaises(FileExistsError):
                    run(planpath,labels,root/'out2',True,confirmation)
            self.assertEqual(len(model_calls),6)
            self.assertEqual(launcher.call_count,2)
            self.assertEqual(first['billing']['reserved'],'18.911232')
            self.assertFalse((root/'out2/budget.json').exists())
            self.assertEqual((root/'out1/budget.json').read_bytes(),before)

    def test_ten_processes_competing_across_directories_get_only_one_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=fixed_plan();self.scope(root,plan)
            planpath=root/'plan.json';planpath.write_text(json.dumps(plan))
            prices=root/'prices.json';prices.write_text(json.dumps(confirmed_pricing(plan)))
            code = (
                "import sys,json; from pathlib import Path; import locagent_service.budget as b; "
                "plan=json.loads(Path(sys.argv[1]).read_text()); "
                "b.AUTHORIZED_PLAN_HASH=b.digest(b.canonical(plan)); "
                "b.AUTHORIZATION_PATH=Path(sys.argv[3]); "
                "b.initialize_ledger(sys.argv[4],plan,json.loads(Path(sys.argv[2]).read_text()))"
            )
            children=[];paths=[]
            for index in range(10):
                folder=root/str(index);folder.mkdir();path=folder/'budget.json';paths.append(path)
                children.append(subprocess.Popen([sys.executable,'-B','-c',code,str(planpath),
                    str(prices),str(budget.AUTHORIZATION_PATH),str(path)],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
            outputs=[child.communicate(timeout=30) for child in children]
            self.assertEqual(sum(child.returncode==0 for child in children),1)
            self.assertTrue(all('FileExistsError' in result[1] for child,result in zip(children,outputs)
                                if child.returncode!=0))
            ledgers=[path for path in paths if path.exists()]
            self.assertEqual(len(ledgers),1)
            marker=json.loads(budget.AUTHORIZATION_PATH.read_text())
            self.assertEqual(marker['ledger_path'],str(ledgers[0].resolve()))
            for arm in (False,True):
                for _ in range(3):
                    budget.BudgetProvider(ledgers[0],'s',CONFIG,lambda **kw:Response(),arm=arm)(messages=[])
            self.assertEqual(json.loads(ledgers[0].read_text())['reserved'],'18.911232')

    def test_unknown_call_retains_reservation_and_blocks_all_other_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=fixed_plan();self.scope(root,plan)
            first=root/'first.json';budget.initialize_ledger(first,plan,confirmed_pricing(plan))
            def timeout(**kwargs):raise TimeoutError('offline fault')
            with self.assertRaises(TimeoutError):
                budget.BudgetProvider(first,'s',CONFIG,timeout)(messages=[])
            before=first.read_bytes()
            with self.assertRaises(FileExistsError):
                budget.initialize_ledger(root/'second.json',plan,confirmed_pricing(plan))
            state=json.loads(before)
            self.assertEqual(state['calls'][0]['status'],'outcome_unknown')
            self.assertEqual(state['reserved'],'3.151872')
            self.assertEqual(first.read_bytes(),before)
            self.assertTrue(budget.AUTHORIZATION_PATH.exists())

    def test_copied_ledger_cannot_escape_authorized_ledger_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=fixed_plan();self.scope(root,plan)
            first=root/'first.json';second=root/'copied.json'
            budget.initialize_ledger(first,plan,confirmed_pricing(plan))
            shutil.copyfile(first,second)
            with self.assertRaises(RuntimeError):
                budget.BudgetProvider(second,'s',CONFIG,lambda **kw:self.fail('provider called'))(messages=[])
            self.assertEqual(json.loads(first.read_text())['reserved'],'0')
            self.assertEqual(json.loads(second.read_text())['reserved'],'0')

    def test_initialization_failure_consumes_marker_and_never_auto_reclaims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=fixed_plan();self.scope(root,plan)
            first=root/'first.json';real_save=budget.save
            def fail_ledger(path,value):
                if Path(path)==first:raise OSError('injected disk failure')
                real_save(path,value)
            with patch.object(budget,'save',side_effect=fail_ledger),self.assertRaises(OSError):
                budget.initialize_ledger(first,plan,confirmed_pricing(plan))
            self.assertTrue(budget.AUTHORIZATION_PATH.is_file())
            with self.assertRaises(FileExistsError):
                budget.initialize_ledger(root/'new.json',plan,confirmed_pricing(plan))

    def test_interrupted_empty_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=fixed_plan();self.scope(root,plan)
            budget.AUTHORIZATION_PATH.write_text('')
            with self.assertRaises(FileExistsError):
                budget.initialize_ledger(root/'new.json',plan,confirmed_pricing(plan))
            self.assertFalse((root/'new.json').exists())
            self.assertEqual(budget.AUTHORIZATION_PATH.read_bytes(),b'')

    def test_changed_plan_cannot_create_another_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);approved=fixed_plan();self.scope(root,approved)
            changed=deepcopy(approved);changed['new_note']='same mathematical limits, different plan'
            with self.assertRaises(ValueError):
                budget.initialize_ledger(root/'other.json',changed,confirmed_pricing(changed))
            self.assertFalse(budget.AUTHORIZATION_PATH.exists())
            self.assertFalse((root/'other.json').exists())

    def test_missing_corrupt_or_wrong_shared_marker_blocks_existing_ledger(self):
        for payload in (None,'{','{}'):
            with self.subTest(payload=payload),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);plan=fixed_plan();self.scope(root,plan)
                path=root/'budget.json';budget.initialize_ledger(path,plan,confirmed_pricing(plan))
                if payload is None:budget.AUTHORIZATION_PATH.unlink()
                else:budget.AUTHORIZATION_PATH.write_text(payload)
                with self.assertRaises(RuntimeError):
                    budget.BudgetProvider(path,'s',CONFIG,lambda **kw:self.fail('called'))(messages=[])


class PricingBeforeEnvTests(unittest.TestCase):
    def test_missing_invalid_mismatched_stale_or_expensive_confirmation_never_loads_env(self):
        changes=[
            None, '{', {},
            {'plan_hash':'other'},
            {'confirmed_at_utc':(datetime.now(timezone.utc)-timedelta(hours=25)).isoformat()},
            {'confirmed_at_utc':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()},
            {'input_cache_miss_peak_per_million':'3.01'}, {'currency':'EUR'},
            {'all_charges_included':False},
        ]
        for case in changes:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);plan=fixed_plan()
                planpath=root/'plan.json';planpath.write_text(json.dumps(plan))
                pricing=root/'prices.json'
                if case=='{':pricing.write_text('{')
                elif case=={}:pricing.write_text('{}')
                elif case is not None:
                    pricing.write_text(json.dumps({**confirmed_pricing(plan),**case}))
                args=['evaluate','run','--live','--env-file','must-not-be-opened',
                      '--plan',str(planpath),'--labels','unused','--output',str(root/'out'),
                      '--pricing-confirmation',str(pricing)]
                with patch.object(sys,'argv',args), \
                     patch.object(budget,'AUTHORIZED_PLAN_HASH',digest(canonical(plan))), \
                     patch('locagent_service.configure.load_env_file') as loader, \
                     patch('locagent_service.evaluate.run') as execute,redirect_stderr(io.StringIO()):
                    with self.assertRaises((ValueError,FileNotFoundError)):main()
                    loader.assert_not_called();execute.assert_not_called()
                self.assertFalse((root/'out').exists())

    def test_valid_pricing_checked_before_env_and_unapproved_plan_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=fixed_plan()
            planpath=root/'plan.json';planpath.write_text(json.dumps(plan))
            pricing=root/'prices.json';pricing.write_text(json.dumps(confirmed_pricing(plan)))
            args=['evaluate','run','--live','--env-file','fake','--plan',str(planpath),
                  '--labels','unused','--output','unused','--pricing-confirmation',str(pricing)]
            order=[]
            from locagent_service.evaluate import load_live_pricing
            def check(*args):order.append('pricing');return load_live_pricing(*args)
            with patch.object(sys,'argv',args), \
                 patch.object(budget,'AUTHORIZED_PLAN_HASH',digest(canonical(plan))), \
                 patch('locagent_service.evaluate.load_live_pricing',side_effect=check), \
                 patch('locagent_service.configure.load_env_file',side_effect=lambda _:order.append('env')), \
                 patch('locagent_service.evaluate.run',side_effect=lambda *args:order.append('run')):
                main()
            self.assertEqual(order,['pricing','env','run'])
            with patch.object(sys,'argv',args),patch.object(budget,'AUTHORIZED_PLAN_HASH','other'), \
                 patch('locagent_service.configure.load_env_file') as loader, \
                 patch('locagent_service.evaluate.run') as execute,self.assertRaises(ValueError):
                main()
            loader.assert_not_called();execute.assert_not_called()
