"""No paid calls: provider doubles, real file locks, and process-death injection."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from locagent_service.budget import (BudgetProvider, LIVE_CONFIG, RESERVATION_BASIS,
    initialize_ledger, reserve_cost, validate_live_plan, validate_pricing_confirmation,
    paid_mode, save)
from locagent_service.sources import canonical, digest
from test_stage4_evaluation import CONFIG, Response, fixed_plan, confirmed_pricing


class ConservativeBudgetTests(unittest.TestCase):
    def setup_ledger(self, root):
        path = Path(root)/'budget.json'
        plan = fixed_plan()
        for name,value in [('AUTHORIZATION_PATH',Path(root)/'authorization.json'),
                           ('AUTHORIZED_PLAN_HASH',digest(canonical(plan)))]:
            context=patch('locagent_service.budget.'+name,value)
            context.start();self.addCleanup(context.stop)
        initialize_ledger(path, plan, confirmed_pricing(plan))
        return path

    def test_full_context_math_is_independent_of_local_input_size(self):
        self.assertEqual(reserve_cost(CONFIG), Decimal('3.151872'))
        self.assertEqual(validate_live_plan(fixed_plan()), Decimal('18.911232'))
        with tempfile.TemporaryDirectory() as tmp:
            path = self.setup_ledger(tmp)
            BudgetProvider(path, 's', CONFIG, lambda **kw:Response())(messages=[])
            state = json.loads(path.read_text())
            self.assertEqual(state['reserved'], '3.151872')
            call = state['calls'][0]
            self.assertEqual(call['reserved_input_tokens'], 1048576)
            self.assertLess(call['input_byte_estimate'], 16000)

    def test_plan_and_live_config_cannot_silently_reduce_or_expand_bounds(self):
        for key, value in [('max_calls',2),('max_calls',4),('provider_context_tokens',16000),
                           ('max_output_tokens',1),('thinking','enabled'),('temperature',True),
                           ('input_estimate_gate',32000),('api_base','https://other.invalid'),
                           ('model','other'),('resolved_family','other')]:
            with self.subTest(key=key, value=value):
                plan = fixed_plan();plan['config'][key] = value
                with self.assertRaises(ValueError):validate_live_plan(plan)
        for key,value in [('version',1),('sources',['s','t']),('arms',[0,1]),
                          ('denominator_per_arm',True),('max_calls',8),('budget_cny',21),
                          ('worst_case_reservation_cny','0.433152')]:
            plan = fixed_plan();plan[key] = value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_live_plan(plan)
        plan=fixed_plan();plan['config']['max_input_tokens']=16000
        with self.assertRaises(ValueError):validate_live_plan(plan)

    def test_confirmation_is_required_before_creating_a_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'budget.json'
            with self.assertRaises(ValueError):initialize_ledger(path,fixed_plan())
            self.assertFalse(path.exists())

    def test_confirmation_rejects_invalid_unconfirmed_stale_or_expensive_prices(self):
        plan=fixed_plan()
        cases=[
            {'plan_hash':'other'}, {'provider':'other'}, {'currency':'EUR'},
            {'all_charges_included':False}, {'all_charges_included':1},
            {'input_cache_miss_peak_per_million':'3.000001'},
            {'output_peak_per_million':'12.000001'}, {'input_cache_miss_peak_per_million':'NaN'},
            {'output_peak_per_million':'Infinity'}, {'output_peak_per_million':True},
            {'input_cache_miss_peak_per_million':0}, {'secret':'must-not-be-here'},
            {'confirmed_at_utc':(datetime.now(timezone.utc)-timedelta(hours=25)).isoformat()},
            {'confirmed_at_utc':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()},
            {'confirmed_at_utc':'2026-10-08T12:00:00'}, {'confirmed_at_utc':None},
            {'cny_per_usd_all_in_ceiling':'10'},
        ]
        for changes in cases:
            confirmation={**confirmed_pricing(plan),**changes}
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                validate_pricing_confirmation(plan,confirmation)

    def test_usd_confirmation_requires_all_in_conversion_within_ceiling(self):
        plan=fixed_plan()
        confirmation={**confirmed_pricing(plan),'currency':'USD',
                      'input_cache_miss_peak_per_million':'0.30','output_peak_per_million':'1.20'}
        with self.assertRaises(ValueError):validate_pricing_confirmation(plan,confirmation)
        confirmation['cny_per_usd_all_in_ceiling']='10'
        self.assertEqual(validate_pricing_confirmation(plan,confirmation),
                         {'input_cny_per_million':'3.00','output_cny_per_million':'12.00'})
        confirmation['cny_per_usd_all_in_ceiling']='10.01'
        with self.assertRaises(ValueError):validate_pricing_confirmation(plan,confirmation)

    def test_six_calls_retain_full_reservations_and_durable_three_per_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_ledger(tmp)
            for arm in (False,True):
                for _ in range(3):
                    BudgetProvider(path,'s',CONFIG,lambda **kw:Response(),arm=arm)(messages=[])
                with self.assertRaises(RuntimeError):
                    BudgetProvider(path,'s',CONFIG,lambda **kw:self.fail('provider called'),arm=arm)(messages=[])
            state=json.loads(path.read_text())
            self.assertEqual(len(state['calls']),6)
            self.assertEqual(state['reserved'],'18.911232')
            self.assertTrue(all(c['reservation_cny']=='3.151872' for c in state['calls']))

    def test_parallel_providers_share_stable_lock_and_exact_quotas(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_ledger(tmp)
            def attempt(arm):
                try:
                    BudgetProvider(path,'s',CONFIG,lambda **kw:Response(),arm=arm)(messages=[])
                    return True
                except RuntimeError:return False
            with ThreadPoolExecutor(max_workers=8) as pool:
                outcomes=list(pool.map(attempt,[False]*5+[True]*5))
            self.assertEqual(sum(outcomes),6)
            self.assertEqual(json.loads(path.read_text())['reserved'],'18.911232')

    def test_actual_child_death_after_durable_reservation_blocks_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_ledger(tmp)
            code = ("import os,sys; from pathlib import Path; import locagent_service.budget as b; "
                    "b.AUTHORIZATION_PATH=Path(sys.argv[2]); b.AUTHORIZED_PLAN_HASH=sys.argv[3]; "
                    "b.BudgetProvider(sys.argv[1],'s',b.LIVE_CONFIG,lambda **kw:os._exit(7))(messages=[])")
            child=subprocess.run([sys.executable,'-B','-c',code,str(path),
                                  str(Path(tmp)/'authorization.json'),digest(canonical(fixed_plan()))],
                                 capture_output=True,timeout=20)
            self.assertEqual(child.returncode,7)
            before=path.read_bytes()
            state=json.loads(before)
            self.assertEqual(state['calls'][0]['status'],'reserved')
            self.assertEqual(state['reserved'],'3.151872')
            with self.assertRaises(RuntimeError):
                BudgetProvider(path,'s',CONFIG,lambda **kw:self.fail('replayed'))(messages=[])
            self.assertEqual(path.read_bytes(),before)

    def test_atomic_post_response_save_failure_leaves_full_reserved_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_ledger(tmp)
            real_save=save
            count=0
            def fail_after_first(target,state):
                nonlocal count
                count+=1
                if count>1:raise OSError('injected disk failure')
                real_save(target,state)
            with patch('locagent_service.budget.save',side_effect=fail_after_first):
                with self.assertRaises(OSError):
                    BudgetProvider(path,'s',CONFIG,lambda **kw:Response())(messages=[])
            state=json.loads(path.read_text())
            self.assertEqual(state['reserved'],'3.151872')
            self.assertEqual(state['calls'][0]['status'],'reserved')
            with self.assertRaises(RuntimeError):
                BudgetProvider(path,'s',CONFIG,lambda **kw:self.fail('replayed'))(messages=[])

    def test_atomic_pre_call_failure_cannot_invoke_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_ledger(tmp);before=path.read_bytes()
            with patch('locagent_service.budget.os.replace',side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    BudgetProvider(path,'s',CONFIG,lambda **kw:self.fail('called'))(messages=[])
            self.assertEqual(path.read_bytes(),before)
            self.assertFalse(list(Path(tmp).glob('*.tmp')))

    def test_usage_above_heuristic_is_covered_by_full_context_reservation(self):
        response=Response()
        response.usage=type('Usage',(),{'prompt_tokens':20000,'completion_tokens':20})()
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_ledger(tmp)
            BudgetProvider(path,'s',CONFIG,lambda **kw:response)(messages=[])
            state=json.loads(path.read_text())
            self.assertFalse(state['halted'])
            self.assertEqual(state['reserved'],'3.151872')

    def test_invalid_or_excess_usage_halts_without_refunding(self):
        for pt,ct in [(1048577,1),(1,513),(True,1),(-1,1),('100',1),(1,None)]:
            with self.subTest(pt=pt,ct=ct),tempfile.TemporaryDirectory() as tmp:
                path=self.setup_ledger(tmp)
                response=Response()
                response.usage=type('Usage',(),{'prompt_tokens':pt,'completion_tokens':ct})()
                with self.assertRaises(RuntimeError):
                    BudgetProvider(path,'s',CONFIG,lambda **kw:response)(messages=[])
                state=json.loads(path.read_text())
                self.assertTrue(state['halted'])
                self.assertEqual(state['reserved'],'3.151872')
                self.assertEqual(state['calls'][0]['status'],'usage_limit_violation')

    def test_caller_cannot_override_provider_safety_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_ledger(tmp);received=[]
            def completion(**kwargs):received.append(kwargs);return Response()
            BudgetProvider(path,'s',CONFIG,completion)(messages=[],max_tokens=100000,n=99,
                model='expensive',api_base='https://other.invalid',num_retries=9,stream=True,
                fallbacks=['other'],extra_body={'thinking':{'type':'enabled'}},api_key='caller-value')
            args=received[0]
            self.assertEqual(args['max_tokens'],512)
            self.assertEqual(args['model'],LIVE_CONFIG['model'])
            self.assertEqual(args['api_base'],LIVE_CONFIG['api_base'])
            self.assertEqual(args['num_retries'],0)
            self.assertFalse(args['stream'])
            self.assertEqual(args['extra_body'],{'thinking':{'type':'disabled'}})
            self.assertNotIn('n',args)
            self.assertNotIn('fallbacks',args)
            self.assertNotEqual(args['api_key'],'caller-value')

    def test_ledger_tampering_fails_closed(self):
        for change in [{'reserved':'0.1'},{'max_calls':100},{'limit':'100'},{'config_hash':'wrong'},
                       {'sources':['other']},{'plan_hash':'wrong'}]:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                path=self.setup_ledger(tmp);state=json.loads(path.read_text());state.update(change)
                path.write_text(json.dumps(state))
                with self.assertRaises(RuntimeError):
                    BudgetProvider(path,'s',CONFIG,lambda **kw:self.fail('called'))(messages=[])

    def test_legacy_live_plan_rejected_before_output_or_child_launch(self):
        from locagent_service.evaluate import run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);labels=root/'labels.json';labels.write_text('{}')
            plan=fixed_plan();plan.update(version=1,labels_sha256=digest(labels.read_bytes()))
            path=root/'plan.json';path.write_text(json.dumps(plan))
            with patch('locagent_service.evaluate.load_manifest',return_value=({'config':CONFIG},None)), \
                 patch('locagent_service.evaluate.subprocess.run') as child:
                with self.assertRaises(ValueError):run(path,labels,root/'run',live=True)
                child.assert_not_called()
            self.assertFalse((root/'run').exists())

    def test_live_without_confirmation_fails_before_output_or_child_launch(self):
        from locagent_service.evaluate import run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);labels=root/'labels.json';labels.write_text('{}')
            plan=fixed_plan();plan['labels_sha256']=digest(labels.read_bytes())
            path=root/'plan.json';path.write_text(json.dumps(plan))
            with patch('locagent_service.evaluate.load_manifest',return_value=({'config':CONFIG},None)), \
                 patch('locagent_service.evaluate.subprocess.run') as child:
                with self.assertRaises(ValueError):run(path,labels,root/'run',live=True)
                child.assert_not_called()
            self.assertFalse((root/'run').exists())

    def test_installed_sdk_sends_one_request_on_timeout_with_reviewed_wire_parameters(self):
        # Exercise the actual installed LiteLLM/OpenAI adapter; intercept httpx before I/O.
        import httpx
        import openai
        import litellm
        from litellm.llms.OpenAI import openai as adapter
        actual_client=openai.OpenAI
        options=[];requests=[]
        def client(**kwargs):
            options.append(kwargs)
            return actual_client(**kwargs)
        def send(client,request,*args,**kwargs):
            requests.append(request)
            raise httpx.ReadTimeout('offline injected timeout',request=request)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ,{'DEEPSEEK_API_KEY':'offline-sdk-test-placeholder'}), \
             patch.object(adapter,'OpenAI',side_effect=client), \
             patch.object(httpx.Client,'send',send), \
             redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            path=self.setup_ledger(tmp)
            with self.assertRaises(Exception):
                BudgetProvider(path,'s',CONFIG)(messages=[{'role':'user','content':'offline'}])
            self.assertEqual(len(requests),1)
            self.assertEqual(options[0]['max_retries'],0)
            body=json.loads(requests[0].content)
            self.assertEqual(body['max_tokens'],512)
            self.assertEqual(body['thinking'],{'type':'disabled'})
            self.assertEqual(body['model'],'deepseek-v4-flash')
            self.assertNotIn('n',body)
            self.assertEqual(str(requests[0].url),'https://api.deepseek.com/chat/completions')
            state=json.loads(path.read_text())
            self.assertEqual(state['reserved'],'3.151872')
            self.assertEqual(state['calls'][0]['status'],'outcome_unknown')

    def test_prepared_provider_arm_is_bound_to_request_not_environment_label(self):
        from locagent_service.sources import localize
        from locagent_service.models import CreateTask
        source='prepared-'+'a'*64
        request=CreateTask(source_id=source,problem_statement='fixed',max_attempts=1,
                           options={'max_iterations':3,'suppress_repeats':True})
        with patch('locagent_service.sources.load_manifest',return_value=({'config':CONFIG},None)), \
             patch('locagent_service.budget.BudgetProvider.from_env') as provider, \
             patch('locagent_service.sources.localize_prepared',return_value='done'), \
             patch.dict(os.environ,{'LOCAGENT_EVALUATION_ARM':'false'}):
            self.assertEqual(localize(request),'done')
            provider.assert_called_once_with(source,CONFIG,arm=True)


class LiveSwitchTests(unittest.TestCase):
    def test_live_switch_overrides_zero_only_in_process_and_preserves_env_file(self):
        from locagent_service.evaluate import main
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{},clear=True):
            path=Path(tmp)/'.env'
            path.write_text('DEEPSEEK_API_KEY=unit-test-placeholder\nLOCAGENT_ALLOW_PAID=0\n')
            path.chmod(0o600);before=path.read_bytes();stat=path.stat()
            plan=fixed_plan();planpath=Path(tmp)/'plan.json';planpath.write_text(json.dumps(plan))
            pricing=Path(tmp)/'pricing.json';pricing.write_text(json.dumps(confirmed_pricing(plan)))
            args=['evaluate','run','--live','--env-file',str(path),'--pricing-confirmation',str(pricing),
                  '--plan',str(planpath),'--labels','l','--output','o']
            def fake(*args):
                self.assertEqual(os.environ['LOCAGENT_ALLOW_PAID'],'1')
                self.assertTrue(args[3])
                self.assertEqual(args[4],str(pricing))
                raise RuntimeError('simulated failure')
            with patch.object(sys,'argv',args),patch('locagent_service.evaluate.run',side_effect=fake), \
                 patch('locagent_service.budget.AUTHORIZED_PLAN_HASH',digest(canonical(plan))):
                with self.assertRaises(RuntimeError):main()
            self.assertEqual(os.environ['LOCAGENT_ALLOW_PAID'],'0')
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual((path.stat().st_mode,path.stat().st_mtime_ns),(stat.st_mode,stat.st_mtime_ns))

    def test_offline_switch_forces_zero_even_when_env_file_has_one(self):
        from locagent_service.evaluate import main
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{},clear=True):
            path=Path(tmp)/'.env';path.write_text('LOCAGENT_ALLOW_PAID=1\n');path.chmod(0o600)
            args=['evaluate','run','--env-file',str(path),'--plan','p','--labels','l','--output','o']
            def fake(*args):self.assertEqual(os.environ['LOCAGENT_ALLOW_PAID'],'0')
            with patch.object(sys,'argv',args),patch('locagent_service.evaluate.run',side_effect=fake):
                main()
            self.assertEqual(os.environ['LOCAGENT_ALLOW_PAID'],'1')

    def test_missing_pricing_argument_rejected_before_env_is_read(self):
        from locagent_service.evaluate import main
        args=['evaluate','run','--live','--env-file','must-not-read','--plan','p','--labels','l','--output','o']
        with patch.object(sys,'argv',args),patch('locagent_service.configure.load_env_file') as loader, \
             redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            main()
        loader.assert_not_called()

    def test_process_switch_restores_missing_value_after_exception(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(RuntimeError):
                with paid_mode(True):
                    self.assertEqual(os.environ['LOCAGENT_ALLOW_PAID'],'1')
                    raise RuntimeError()
            self.assertNotIn('LOCAGENT_ALLOW_PAID',os.environ)
