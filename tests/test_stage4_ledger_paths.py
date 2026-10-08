"""One canonical ledger across symlink/relative aliases; fake providers only."""
from concurrent.futures import ThreadPoolExecutor
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
from locagent_service.sources import canonical,digest
from test_stage4_evaluation import CONFIG,Response,fixed_plan,confirmed_pricing


class LedgerPathTests(unittest.TestCase):
    def scope(self,root):
        plan=fixed_plan()
        for name,value in [('AUTHORIZATION_PATH',root/'approval.json'),
                           ('AUTHORIZED_PLAN_HASH',digest(canonical(plan)))]:
            context=patch.object(budget,name,value)
            context.start();self.addCleanup(context.stop)
        return plan

    def test_initialization_through_dangling_file_symlink_preserves_link_and_real_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=self.scope(root)
            owner=root/'real.json';alias=root/'alias.json';alias.symlink_to(owner)
            budget.initialize_ledger(alias,plan,confirmed_pricing(plan))
            self.assertTrue(alias.is_symlink())
            self.assertTrue(owner.is_file())
            self.assertEqual(json.loads(budget.AUTHORIZATION_PATH.read_text())['ledger_path'],str(owner))
            budget.BudgetProvider(alias,'s',CONFIG,lambda **kw:Response())(messages=[])
            self.assertTrue(alias.is_symlink())
            self.assertEqual(json.loads(owner.read_text())['reserved'],'3.151872')
            self.assertTrue(Path(str(owner)+'.lock').is_file())
            self.assertFalse(Path(str(alias)+'.lock').exists())

    def test_eight_symlink_aliases_share_one_owner_and_six_call_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=self.scope(root)
            owner=root/'budget.json';budget.initialize_ledger(owner,plan,confirmed_pricing(plan))
            aliases=[]
            for i in range(8):
                alias=root/f'alias-{i}.json';alias.symlink_to(owner);aliases.append(alias)
            def attempt(item):
                alias,arm=item
                try:
                    budget.BudgetProvider(alias,'s',CONFIG,lambda **kw:Response(),arm=arm)(messages=[])
                    return True
                except RuntimeError:return False
            with ThreadPoolExecutor(max_workers=8) as pool:
                accepted=list(pool.map(attempt,zip(aliases,[False]*4+[True]*4)))
            state=json.loads(owner.read_text())
            self.assertEqual(sum(accepted),6)
            self.assertEqual(len(state['calls']),6)
            self.assertEqual(state['reserved'],'18.911232')
            self.assertTrue(all(alias.is_symlink() for alias in aliases))
            self.assertTrue(all(json.loads(alias.read_text())==state for alias in aliases))
            self.assertEqual(list(root.glob('*.lock')),[Path(str(owner)+'.lock')])

    def test_environment_alias_is_normalized_by_provider_constructor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=self.scope(root)
            owner=root/'budget.json';budget.initialize_ledger(owner,plan,confirmed_pricing(plan))
            alias=root/'env-alias.json';alias.symlink_to(owner)
            with patch.dict(os.environ,{'LOCAGENT_ALLOW_PAID':'1',
                                        'DEEPSEEK_API_KEY':'offline-placeholder',
                                        'LOCAGENT_BUDGET_LEDGER':str(alias)}):
                provider=budget.BudgetProvider.from_env('s',CONFIG)
            self.assertEqual(provider.path,owner)
            provider.completion=lambda **kw:Response()
            provider(messages=[])
            self.assertEqual(json.loads(owner.read_text())['reserved'],'3.151872')
            self.assertTrue(alias.is_symlink())

    def test_relative_initialization_and_provider_survive_cwd_change(self):
        original=Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);plan=self.scope(root)
                real=root/'real';real.mkdir()
                link=root/'directory-alias';link.symlink_to(real,target_is_directory=True)
                os.chdir(root)
                budget.initialize_ledger('directory-alias/../directory-alias/budget.json',
                                         plan,confirmed_pricing(plan))
                owner=real/'budget.json'
                provider=budget.BudgetProvider('./directory-alias/budget.json',
                                               's',CONFIG,lambda **kw:Response())
                self.assertEqual(provider.path,owner)
                os.chdir(original)
                provider(messages=[])
                self.assertEqual(json.loads(owner.read_text())['reserved'],'3.151872')
                self.assertEqual(json.loads(budget.AUTHORIZATION_PATH.read_text())['ledger_path'],str(owner))
                self.assertEqual(list(real.glob('*.lock')),[Path(str(owner)+'.lock')])
        finally:os.chdir(original)

    def test_ten_processes_with_relative_and_symlink_paths_share_one_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=self.scope(root)
            real=root/'real';real.mkdir()
            owner=real/'budget.json';budget.initialize_ledger(owner,plan,confirmed_pricing(plan))
            repository=Path(__file__).resolve().parents[1]
            code = (
                "import sys,json; from pathlib import Path; "
                "sys.path[:0]=[sys.argv[1],str(Path(sys.argv[1])/'tests')]; "
                "import locagent_service.budget as b; from test_stage4_evaluation import CONFIG,Response; "
                "b.AUTHORIZATION_PATH=Path(sys.argv[2]); b.AUTHORIZED_PLAN_HASH=sys.argv[3]; "
                "p=b.BudgetProvider(sys.argv[4],'s',CONFIG,lambda **kw:Response(),arm=sys.argv[5]=='true'); "
                "p(messages=[]); print(json.dumps({'accepted':True,'path':str(p.path)}))"
            )
            children=[];aliases=[]
            for i in range(10):
                cwd=root/str(i);cwd.mkdir()
                alias=cwd/'linked.json';alias.symlink_to(owner);aliases.append(alias)
                directory=cwd/'linked-dir';directory.symlink_to(real,target_is_directory=True)
                relative=('./linked.json','../real/./budget.json','linked-dir/budget.json')[i%3]
                children.append(subprocess.Popen([sys.executable,'-B','-c',code,str(repository),
                    str(budget.AUTHORIZATION_PATH),digest(canonical(plan)),relative,
                    'true' if i%2 else 'false'],cwd=cwd,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
            output=[child.communicate(timeout=30) for child in children]
            self.assertEqual(sum(child.returncode==0 for child in children),6)
            for child,record in zip(children,output):
                if child.returncode==0:self.assertEqual(json.loads(record[0])['path'],str(owner))
                else:self.assertIn('Experiment is exhausted',record[1])
            state=json.loads(owner.read_text())
            self.assertEqual(len(state['calls']),6)
            self.assertEqual(state['reserved'],'18.911232')
            self.assertEqual(sum(c['arm']=='false' for c in state['calls']),3)
            self.assertTrue(all(alias.is_symlink() for alias in aliases))
            self.assertEqual(list(root.rglob('*.lock')),[Path(str(owner)+'.lock')])

    def test_retargeting_input_alias_after_construction_does_not_redirect_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=self.scope(root)
            owner=root/'budget.json';budget.initialize_ledger(owner,plan,confirmed_pricing(plan))
            copied=root/'copied.json';shutil.copyfile(owner,copied)
            alias=root/'alias.json';alias.symlink_to(owner)
            provider=budget.BudgetProvider(alias,'s',CONFIG,lambda **kw:Response())
            alias.unlink();alias.symlink_to(copied)
            provider(messages=[])
            self.assertEqual(json.loads(owner.read_text())['reserved'],'3.151872')
            self.assertEqual(json.loads(copied.read_text())['reserved'],'0')
            self.assertTrue(alias.is_symlink())
            with self.assertRaises(RuntimeError):
                budget.BudgetProvider(alias,'s',CONFIG,lambda **kw:self.fail('called'))(messages=[])
