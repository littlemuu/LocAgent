"""Single exact-zero authorization transfer; every ledger/provider here is temporary."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import locagent_service.budget as b
from locagent_service.sources import canonical,digest
from test_stage4_evaluation import CONFIG,Response,fixed_plan,confirmed_pricing


class ZeroRecoveryTests(unittest.TestCase):
    def setup_previous(self,root,plan=None):
        new=deepcopy(plan) if plan is not None else fixed_plan()
        old=deepcopy(new);old['config']['input_estimate_gate']=16000
        oldprices=confirmed_pricing(old)
        marker=root/'approval.json';previous=root/'old.json';token='temporary-test-owner'
        rates=b.validate_pricing_confirmation(old,oldprices)
        state=b.initial_ledger_state(old,oldprices,rates,token)
        previous.write_text(json.dumps(state,sort_keys=True))
        authority={'version':1,'authorization':'first-pilot-cny20','limit':'20',
                   'plan_hash':digest(canonical(old)),'token':token,
                   'pricing_hash':digest(canonical(oldprices)),'ledger_path':str(previous)}
        marker.write_text(json.dumps(authority,sort_keys=True))
        settings={'AUTHORIZATION_PATH':str(marker),'AUTHORIZED_PLAN_HASH':digest(canonical(new)),
                  'RECOVERABLE_PLAN_HASH':digest(canonical(old)),
                  'RECOVERABLE_LEDGER_SHA256':digest(previous.read_bytes()),
                  'RECOVERABLE_MARKER_SHA256':digest(marker.read_bytes())}
        for name,value in settings.items():
            context=patch.object(b,name,Path(value) if name=='AUTHORIZATION_PATH' else value)
            context.start();self.addCleanup(context.stop)
        return previous,new,confirmed_pricing(new),settings

    def test_zero_transfer_preserves_old_evidence_and_allows_only_one_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old,plan,prices,_=self.setup_previous(root)
            before=old.read_bytes();marker_before=b.AUTHORIZATION_PATH.read_bytes()
            new=root/'new.json'
            result=b.recover_zero_use_ledger(old,new,plan,prices)
            self.assertEqual(old.read_bytes(),before)
            audit=json.loads(Path(result['audit']).read_text())
            self.assertEqual(audit['previous_ledger'],json.loads(before))
            self.assertEqual(audit['previous_authorization'],json.loads(marker_before))
            self.assertEqual(audit['previous_marker_sha256'],digest(marker_before))
            self.assertEqual(json.loads(b.AUTHORIZATION_PATH.read_text())['zero_use_recovery']['count'],1)
            with self.assertRaises(RuntimeError):
                b.recover_zero_use_ledger(old,root/'another.json',plan,prices)
            for arm in (False,True):
                for _ in range(3):
                    b.BudgetProvider(new,'s',CONFIG,lambda **kw:Response(),arm=arm)(messages=[])
            self.assertEqual(json.loads(new.read_text())['reserved'],'18.911232')
            with self.assertRaises(RuntimeError):
                b.BudgetProvider(old,'s',CONFIG,lambda **kw:self.fail('old owner called'))(messages=[])

    def test_any_call_reservation_unknown_or_halted_state_is_not_recoverable(self):
        changes=[{'reserved':'0.1'},{'halted':True},
                 *[{'calls':[{'status':status}],'reserved':'0'} for status in
                   ['reserved','outcome_unknown','response_received','usage_limit_violation']]]
        for change in changes:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);old,plan,prices,_=self.setup_previous(root)
                state=json.loads(old.read_text());state.update(change);old.write_text(json.dumps(state))
                # Even if a changed fingerprint were supplied, zero-state checks must reject it.
                with patch.object(b,'RECOVERABLE_LEDGER_SHA256',digest(old.read_bytes())):
                    with self.assertRaises(RuntimeError):
                        b.recover_zero_use_ledger(old,root/'new.json',plan,prices)
                self.assertFalse(b.recovery_journal_path().exists())
                self.assertFalse((root/'new.json').exists())

    def test_zero_looking_but_fingerprint_changed_ledger_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old,plan,prices,_=self.setup_previous(root)
            old.write_bytes(old.read_bytes()+b' ')
            with self.assertRaises(RuntimeError):
                b.recover_zero_use_ledger(old,root/'new.json',plan,prices)
            self.assertFalse(b.recovery_journal_path().exists())

    def test_marker_owner_or_pricing_mismatch_is_rejected(self):
        for field,value in [('ledger_path','/not-the-owner'),('token','wrong'),('pricing_hash','wrong')]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);old,plan,prices,_=self.setup_previous(root)
                marker=json.loads(b.AUTHORIZATION_PATH.read_text());marker[field]=value
                b.AUTHORIZATION_PATH.write_text(json.dumps(marker))
                with patch.object(b,'RECOVERABLE_MARKER_SHA256',digest(b.AUTHORIZATION_PATH.read_bytes())):
                    with self.assertRaises(RuntimeError):
                        b.recover_zero_use_ledger(old,root/'new.json',plan,prices)
                self.assertFalse(b.recovery_journal_path().exists())

    def test_failure_at_each_durable_write_never_reclaims_recovery_or_enables_a_provider(self):
        for phase in ('audit','ledger','marker'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);old,plan,prices,_=self.setup_previous(root)
                new=root/'new.json';real_save=b.save
                target={'audit':b.recovery_journal_path(),'ledger':new,'marker':b.AUTHORIZATION_PATH}[phase]
                def fail(path,value):
                    if Path(path)==target:raise OSError('offline disk fault')
                    real_save(path,value)
                with patch.object(b,'save',side_effect=fail),self.assertRaises(OSError):
                    b.recover_zero_use_ledger(old,new,plan,prices)
                self.assertTrue(b.recovery_journal_path().exists())
                with self.assertRaises(FileExistsError):
                    b.recover_zero_use_ledger(old,root/'retry.json',plan,prices)
                if new.exists() and new.stat().st_size:
                    with self.assertRaises(RuntimeError):
                        b.BudgetProvider(new,'s',CONFIG,lambda **kw:self.fail('paid'))(messages=[])
                with self.assertRaises(RuntimeError):
                    b.initialize_ledger(root/'fresh.json',plan,prices)

    def test_existing_or_same_ledger_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old,plan,prices,_=self.setup_previous(root)
            target=root/'existing.json';target.write_text('keep')
            for path in (old,target):
                with self.assertRaises(FileExistsError):
                    b.recover_zero_use_ledger(old,path,plan,prices)
            self.assertEqual(target.read_text(),'keep')
            self.assertFalse(b.recovery_journal_path().exists())

    def child_configuration(self,root,old,plan,prices,settings):
        config=root/'child.json'
        config.write_text(json.dumps({'settings':settings,'old':str(old),'plan':plan,'prices':prices}))
        code=("import sys,json,os; from pathlib import Path; import locagent_service.budget as b; "
              "c=json.loads(Path(sys.argv[1]).read_text()); "
              "[(setattr(b,k,Path(v) if k=='AUTHORIZATION_PATH' else v)) for k,v in c['settings'].items()]; ")
        return config,code

    def test_eight_real_processes_can_transfer_the_approval_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old,plan,prices,settings=self.setup_previous(root)
            config,code=self.child_configuration(root,old,plan,prices,settings)
            code+="b.recover_zero_use_ledger(c['old'],sys.argv[2],c['plan'],c['prices'])"
            children=[];paths=[]
            for i in range(8):
                path=root/f'new-{i}.json';paths.append(path)
                children.append(subprocess.Popen([sys.executable,'-B','-c',code,str(config),str(path)],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
            output=[p.communicate(timeout=30) for p in children]
            self.assertEqual(sum(p.returncode==0 for p in children),1)
            self.assertEqual(sum(path.exists() for path in paths),1)
            self.assertEqual(json.loads(b.AUTHORIZATION_PATH.read_text())['zero_use_recovery']['count'],1)
            self.assertEqual(digest(old.read_bytes()),settings['RECOVERABLE_LEDGER_SHA256'])

    def test_real_child_crash_after_audit_keeps_transfer_claim_consumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old,plan,prices,settings=self.setup_previous(root)
            config,code=self.child_configuration(root,old,plan,prices,settings)
            code+=("\noriginal=b.save\ndef crash(path,value):\n"
                   " original(path,value)\n"
                   " if Path(path)==b.recovery_journal_path():os._exit(23)\n"
                   "b.save=crash\n"
                   "b.recover_zero_use_ledger(c['old'],sys.argv[2],c['plan'],c['prices'])")
            process=subprocess.run([sys.executable,'-B','-c',code,str(config),str(root/'new.json')],
                                   capture_output=True,timeout=30)
            self.assertEqual(process.returncode,23)
            self.assertTrue(b.recovery_journal_path().exists())
            self.assertEqual(digest(old.read_bytes()),settings['RECOVERABLE_LEDGER_SHA256'])
            with self.assertRaises(FileExistsError):
                b.recover_zero_use_ledger(old,root/'retry.json',plan,prices)

    def test_reservation_committed_under_worker_lock_blocks_waiting_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old,plan,prices,_=self.setup_previous(root)
            started=threading.Event()
            def recover():
                started.set()
                return b.recover_zero_use_ledger(old,root/'new.json',plan,prices)
            with ThreadPoolExecutor(max_workers=1) as pool:
                with b.ledger_lock(old):
                    future=pool.submit(recover);self.assertTrue(started.wait(2))
                    self.assertFalse(future.done())
                    state=json.loads(old.read_text())
                    state['calls']=[{'status':'reserved'}];state['reserved']='3.151872'
                    b.save(old,state)
                with self.assertRaises(RuntimeError):future.result(timeout=5)
            self.assertFalse(b.recovery_journal_path().exists())

    def test_recovery_aliases_pin_canonical_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old,plan,prices,_=self.setup_previous(root)
            alias=root/'old-link.json';alias.symlink_to(old)
            directory=root/'real';directory.mkdir()
            linked=root/'linked';linked.symlink_to(directory,target_is_directory=True)
            b.recover_zero_use_ledger(alias,linked/'new.json',plan,prices)
            marker=json.loads(b.AUTHORIZATION_PATH.read_text())
            self.assertEqual(marker['ledger_path'],str(directory/'new.json'))
            self.assertTrue(alias.is_symlink())
            b.BudgetProvider(linked/'new.json','s',CONFIG,lambda **kw:Response())(messages=[])
            self.assertEqual(json.loads((directory/'new.json').read_text())['reserved'],'3.151872')

    def test_recovery_audit_tampering_disables_the_new_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old,plan,prices,_=self.setup_previous(root)
            new=root/'new.json';b.recover_zero_use_ledger(old,new,plan,prices)
            b.recovery_journal_path().write_text('{}')
            with self.assertRaises(RuntimeError):
                b.BudgetProvider(new,'s',CONFIG,lambda **kw:self.fail('paid'))(messages=[])

    def test_64k_gate_accepts_exact_boundary_rejects_overflow_without_changing_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old,plan,prices,_=self.setup_previous(root)
            new=root/'new.json';b.recover_zero_use_ledger(old,new,plan,prices)
            messages=[{'role':'user','content':''}]
            overhead=len(canonical({'messages':messages,'tools':[]}))+4096
            messages[0]['content']='x'*(65536-overhead)
            provider=b.BudgetProvider(new,'s',CONFIG,lambda **kw:Response())
            provider(messages=messages)
            before=new.read_bytes();messages[0]['content']+='x'
            with self.assertRaises(RuntimeError):provider(messages=messages)
            self.assertEqual(new.read_bytes(),before)
            self.assertEqual(json.loads(before)['reserved'],'3.151872')
            self.assertEqual(b.reserve_cost(CONFIG)*6, b.Decimal('18.911232'))

    def test_cli_recovery_requires_live_before_loading_env(self):
        from locagent_service.evaluate import main
        args=['evaluate','run','--recover-zero-use-from','old','--env-file','must-not-read',
              '--plan','p','--labels','l','--output','o']
        with patch.object(sys,'argv',args),patch('locagent_service.configure.load_env_file') as loader, \
             redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            main()
        loader.assert_not_called()

    def test_evaluation_run_transfers_before_both_simulated_arms(self):
        from contextlib import redirect_stdout
        import test_stage4_evaluation as helpers
        from locagent_service.evaluate import run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);labels=root/'labels.json'
            labels.write_text(json.dumps({'s':{'files':['correct.py'],'entities':['correct.py:f']}}))
            plan=fixed_plan();plan['labels_sha256']=digest(labels.read_bytes())
            old,plan,prices,_=self.setup_previous(root,plan)
            planpath=root/'plan.json';planpath.write_text(json.dumps(plan))
            pricing=root/'prices.json';pricing.write_text(json.dumps(prices))
            def child(command,**kwargs):
                arm=command[command.index('--suppress')+1]=='true'
                provider=b.BudgetProvider(kwargs['env']['LOCAGENT_BUDGET_LEDGER'],'s',CONFIG,
                                          lambda **kw:Response(),arm=arm)
                for _ in range(3):provider(messages=[])
                Path(command[command.index('--output')+1]).write_text(json.dumps(
                    helpers.EvaluationFailureRegressionTests().completed(arm=arm,mode='live')))
                return subprocess.CompletedProcess(command,0,'','')
            with patch('locagent_service.evaluate.load_manifest',return_value=({'config':CONFIG},None)), \
                 patch('locagent_service.evaluate.subprocess.run',side_effect=child), \
                 patch.dict(os.environ,{'LOCAGENT_ALLOW_PAID':'1','DEEPSEEK_API_KEY':'offline-only'}), \
                 redirect_stdout(io.StringIO()):
                summary=run(planpath,labels,root/'run',True,pricing,recover_zero_use_from=old)
            self.assertEqual(summary['billing']['reserved'],'18.911232')
            self.assertTrue(all(arm['completed']==1 for arm in summary['arms'].values()))
            self.assertEqual(json.loads(b.AUTHORIZATION_PATH.read_text())['ledger_path'],
                             str(root/'run/budget.json'))
