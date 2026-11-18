from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import io
import subprocess
from types import SimpleNamespace

from readonly_agent.authority import Authority, Admission
from readonly_agent.core import digest, encoded
from readonly_agent.deepseek_wire import RawHTTP, MODEL, CONTEXT, OUTPUT, RESERVATION
from readonly_agent.journal import Ledger
from experiments.locbench_batch.control import (candidate, SuiteAuthority, SuiteLedger,
    CaseAuthority, clock, read_status)
from experiments.locbench_batch.live import execute, run, launch_arm
from experiments.locbench_batch.offline_verify import FAKE_KEY


class LocBenchBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.plan=candidate();self.h=digest(self.plan)
        self.authority=SuiteAuthority(self.root/'authority')
        self.confirm={'consent':f'APPROVE LOCBENCH {self.h} CNY 34','currency':'CNY',
                      'input_ceiling':'2','output_ceiling':'8','all_charges_included':True}

    def admit(self):
        self.authority.approve(self.plan,self.h,**self.confirm)
        return self.authority.claim(self.h)

    def test_default_missing_grant_and_no_tty_never_load_key(self):
        with patch('readonly_agent.local_env.load_selected_key') as key:
            with self.assertRaises(PermissionError):run(self.h,authority=self.authority)
            with self.assertRaises(FileNotFoundError):run(self.h,live=True,env_api_key=True,authority=self.authority)
            self.authority.approve(self.plan,self.h,**self.confirm)
            with patch('experiments.locbench_batch.live.sys.stdin.isatty',return_value=False):
                with self.assertRaises(PermissionError):run(self.h,live=True,env_api_key=True,authority=self.authority)
            key.assert_not_called()

    def test_wrong_price_scope_or_consent_rejected(self):
        for key,value in [('consent','yes'),('input_ceiling','3'),('currency','USD'),('all_charges_included',False)]:
            with self.assertRaises(PermissionError):self.authority.approve(self.plan,self.h,**dict(self.confirm,**{key:value}))
        self.assertFalse(self.authority.root.exists())

    def test_duplicate_grant_claim_and_relaunch_block_before_key(self):
        self.admit()
        with self.assertRaises(FileExistsError):self.authority.approve(self.plan,self.h,**self.confirm)
        with self.assertRaises(FileExistsError):self.authority.claim(self.h)
        with patch('readonly_agent.local_env.load_selected_key') as key:
            with self.assertRaises(PermissionError):run(self.h,live=True,env_api_key=True,authority=self.authority)
            key.assert_not_called()

    def test_expiry_and_driver_change_reject(self):
        self.admit()
        with patch('experiments.locbench_batch.control.clock',return_value=clock()+timedelta(hours=25)):
            with self.assertRaises(PermissionError):self.authority.read(self.h)
        with patch('experiments.locbench_batch.control.candidate',return_value={'changed':True}):
            with self.assertRaises(PermissionError):self.authority.read(self.h)

    def test_case_and_arm_order_no_restart(self):
        admission=self.admit();ledger=SuiteLedger.create(admission)
        first,second=self.plan['base_manifest']['cases'][:2]
        with self.assertRaises(PermissionError):ledger.begin_case(second['id'])
        ledger.begin_case(first['id'])
        with self.assertRaises(PermissionError):ledger.begin_case(first['id'])
        with self.assertRaises(PermissionError):ledger.begin_arm(first['id'],'retrieval')
        ledger.begin_arm(first['id'],'baseline')
        reopened=SuiteLedger(admission)
        with self.assertRaises(PermissionError):reopened.begin_arm(first['id'],'baseline')
        with self.assertRaises(FileExistsError):SuiteLedger.create(admission)

    def test_child_cannot_standalone_or_continue_after_suite_halt(self):
        admission=self.admit();global_ledger=SuiteLedger.create(admission)
        item=self.plan['base_manifest']['cases'][0]
        global_ledger.begin_case(item['id'])
        case=CaseAuthority(admission,item['id']);case.prepare();child=case.claim(item['plan_hash'])
        with self.assertRaises((KeyError,PermissionError)):
            Authority(case.root).read(item['plan_hash'])
        global_ledger.begin_arm(item['id'],'baseline')
        worker_case=CaseAuthority(admission,item['id'],'baseline')
        active=Admission(worker_case,item['plan_hash'],child.token)
        active.validate()
        wrong=Admission(CaseAuthority(admission,item['id'],'retrieval'),item['plan_hash'],child.token)
        with self.assertRaises(PermissionError):wrong.validate()
        global_ledger.halt('controlled_failure')
        with self.assertRaises(PermissionError):active.validate()

    def test_first_worker_failure_stops_all_remaining_no_retry(self):
        suite=self.admit();calls=[]
        def failed(*args):calls.append(args[2:4]);raise TimeoutError('synthetic')
        result=execute(suite,FAKE_KEY,failed)
        self.assertEqual(len(calls),1)
        self.assertEqual(result['status'],'halted')
        self.assertEqual(sum(r['status']=='not_run' for r in result['arms']),3)
        self.assertEqual(result['case_budget_hold_micro_cny'],17_000_000)
        self.assertEqual(result['requests'],0)
        self.assertEqual(read_status(self.authority,self.h)['reason'],'TimeoutError')

    def test_unknown_reservation_visible_and_second_arm_not_started(self):
        suite=self.admit()
        def interrupted(suite,child,identifier,arm,key):
            record=child.validate();ledger=Ledger(Path(record['run_dir'])/'ledger.sqlite',child.plan_hash)
            token=ledger.claim(arm)
            ledger.reserve(arm,token,b'{}')
            raise TimeoutError('mock request outcome unknown')
        result=execute(suite,FAKE_KEY,interrupted)
        self.assertEqual(result['request_pending_micro_cny'],RESERVATION)
        self.assertEqual(result['spent_upper_micro_cny'],0)
        self.assertEqual(sum(r['status']=='not_run' for r in result['arms']),3)
        self.assertEqual(result['requests'],1)

    def test_emergency_halt_persists_after_expiry_and_status_still_readable(self):
        admission=self.admit();ledger=SuiteLedger.create(admission)
        with patch('experiments.locbench_batch.control.clock',return_value=clock()+timedelta(hours=25)):
            ledger.halt('expired_mid_run')
            self.assertEqual(read_status(self.authority,self.h)['status'],'halted')
            with self.assertRaises(PermissionError):ledger.begin_case('Delgan__loguru-1239')

    def test_invalid_key_does_not_consume_claim(self):
        self.authority.approve(self.plan,self.h,**self.confirm)
        with patch('experiments.locbench_batch.live.sys.stdin.isatty',return_value=True), \
             patch('readonly_agent.local_env.load_selected_key',side_effect=ValueError):
            with self.assertRaises(ValueError):run(self.h,live=True,env_api_key=True,authority=self.authority)
        self.assertFalse((self.authority.folder(self.h)/'claim.json').exists())

    def test_concurrent_claim_has_exactly_one_winner(self):
        self.authority.approve(self.plan,self.h,**self.confirm)
        def attempt():
            try:self.authority.claim(self.h);return 'claimed'
            except FileExistsError:return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:attempt(),range(2)))
        self.assertEqual(sorted(results),['blocked','claimed'])

    def test_worst_usage_16_tickets_stays_under_34_and_no_third_case(self):
        suite=self.admit();global_ledger=SuiteLedger.create(suite)
        raw=RawHTTP(200,encoded({'id':'synthetic-maximum-usage','model':MODEL,'usage':{'prompt_tokens':CONTEXT,'completion_tokens':OUTPUT,
                                                      'total_tokens':CONTEXT+OUTPUT}}))
        for item in self.plan['base_manifest']['cases']:
            global_ledger.begin_case(item['id'])
            auth=CaseAuthority(suite,item['id']);auth.prepare();child=auth.claim(item['plan_hash'])
            local=Ledger.create(Path(child.validate()['run_dir'])/'ledger.sqlite',item['plan'],admission=child)
            for arm in item['arm_order']:
                global_ledger.begin_arm(item['id'],arm);token=local.claim(arm)
                active=Admission(CaseAuthority(suite,item['id'],arm),item['plan_hash'],child.token)
                for _ in range(4):
                    number=local.reserve(arm,token,b'{}');local.start_transport(number,b'{}',active)
                    local.received(number,raw);local.settle(number)
                    with self.assertRaises(PermissionError):local.start_transport(number,b'{}',active)
                with self.assertRaises(RuntimeError):local.reserve(arm,token,b'{}')
                local.finish(arm,token)
                global_ledger.finish_arm(item['id'],arm,{'status':'completed','sdk_status':'finished'},local,.01)
            global_ledger.finish_case(item['id'],local)
        summary=global_ledger.summary()
        self.assertEqual(summary['requests'],16)
        self.assertEqual(summary['spent_upper_micro_cny'],16*RESERVATION)
        self.assertEqual(summary['case_budget_hold_micro_cny'],0)
        self.assertEqual(summary['status'],'completed')
        with self.assertRaises(PermissionError):global_ledger.begin_case('extra')

    def test_launcher_timeout_kills_group_and_key_only_in_pipe(self):
        run_dir=self.root/'child-run';run_dir.mkdir()
        class Pipe(io.BytesIO):
            def close(self):self.saved=self.getvalue();super().close()
        pipe=Pipe()
        process=SimpleNamespace(stdin=pipe,pid=123456)
        calls=[]
        def wait(*args,**kwargs):
            calls.append(kwargs)
            if kwargs:raise subprocess.TimeoutExpired('fixed-worker',360)
            return -9
        process.wait=wait
        child=SimpleNamespace(validate=lambda:{'run_dir':str(run_dir)},token='case-test-token')
        suite=SimpleNamespace(authority=SimpleNamespace(root=self.root),hash='h',token='suite-test-token')
        with patch('experiments.locbench_batch.live.ROOT',self.root), \
             patch('experiments.locbench_batch.live.subprocess.Popen',return_value=process) as popen, \
             patch('experiments.locbench_batch.live.os.killpg') as kill:
            with self.assertRaises(subprocess.TimeoutExpired):launch_arm(suite,child,'Delgan__loguru-1239','baseline',FAKE_KEY)
            popen.assert_called_once();kill.assert_called_once()
            args,kwargs=popen.call_args
            self.assertNotIn(FAKE_KEY,str(args));self.assertNotIn(FAKE_KEY,str(kwargs['env']))
            self.assertEqual(json.loads(pipe.saved)['key'],FAKE_KEY)
            self.assertEqual(len(calls),2)

    def test_foreign_pair_ledger_cannot_finish_case_or_arm(self):
        from types import SimpleNamespace
        suite=self.admit();ledger=SuiteLedger.create(suite)
        first,second=self.plan['base_manifest']['cases']
        ledger.begin_case(first['id']);ledger.begin_arm(first['id'],'baseline')
        wrong=SimpleNamespace(path=Path(ledger.record['run_dir'])/'children'/second['plan_hash']/'run/ledger.sqlite',
                              plan_hash=second['plan_hash'])
        with self.assertRaisesRegex(PermissionError,'wrong_case_ledger'):
            ledger.finish_arm(first['id'],'baseline',{},wrong,0)
        with self.assertRaisesRegex(PermissionError,'wrong_case_ledger'):
            ledger.finish_case(first['id'],wrong)

    def test_corrupt_case_credit_or_arm_order_is_rejected(self):
        import sqlite3
        suite=self.admit();ledger=SuiteLedger.create(suite)
        first=self.plan['base_manifest']['cases'][0]['id']
        with sqlite3.connect(ledger.path) as db:
            db.execute('UPDATE cases SET cost=-1 WHERE id=?',(first,))
        with self.assertRaisesRegex(PermissionError,'suite_case_state_corruption'):
            ledger.begin_case(first)
        with sqlite3.connect(ledger.path) as db:
            db.execute('UPDATE cases SET cost=0 WHERE id=?',(first,))
            db.execute('UPDATE arms SET seq=99 WHERE case_id=? AND arm=?',(first,'baseline'))
        with self.assertRaisesRegex(PermissionError,'suite_arm_binding_changed'):
            ledger.begin_case(first)

    def test_frozen_scope_is_two_cases_and_old_consent_is_refused(self):
        self.assertEqual(self.plan['max_requests'],16)
        self.assertEqual(self.plan['budget_micro_cny'],34_000_000)
        self.assertEqual(len(self.plan['base_manifest']['cases']),2)
        from experiments.locbench_dev.prepare import ROOT as source_root
        self.assertEqual(self.plan['source_manifest_hash'],
            digest(json.loads((source_root/'manifest.json').read_text())))
        for item in self.plan['base_manifest']['cases']:
            self.assertEqual(item['plan_hash'],digest(item['plan']))
        with self.assertRaises(PermissionError):
            self.authority.approve(self.plan,self.h,**dict(self.confirm,consent=f'APPROVE SUITE {self.h} CNY 102'))


if __name__=='__main__':unittest.main()
