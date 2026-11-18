"""New cumulative scope and active-case revalidation, all offline."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from experiments.sdk_ablation_v1.freeze import candidate
from experiments.sdk_ablation_v1.parent import Parent, BatchLedger
from experiments.sdk_ablation_v1.guard import RehearsalAuthority
from experiments.sdk_ablation_v1.cumulative import prior_binding,check_totals,NEW_MICRO_CNY
from readonly_agent.core import digest


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=candidate('rehearsal')

    def test_old_authorization_is_not_new_scope(self):
        p=candidate('live')
        with TemporaryDirectory() as td:
            parent=Parent(Path(td).resolve()/'test-only')
            with self.assertRaises(PermissionError):
                parent.prepare(p,consent=f'APPROVE FIVE {digest(p)} NEW40 TOTAL55 TOTALCNY85',
                  currency='CNY',input_ceiling='2',output_ceiling='8',all_charges_included=True)
            self.assertFalse(parent.root.exists())

    def test_cumulative_accounting_and_boundaries(self):
        b=prior_binding()
        self.assertEqual((b['requests'],b['upper_micro_cny'],b['unknown_micro_cny']),(332,3946826,0))
        check_totals(NEW_MICRO_CNY,48)
        for cost,count in [(NEW_MICRO_CNY+1,48),(0,49),(-1,0),(0,-1)]:
            with self.assertRaises(PermissionError):check_totals(cost,count)

    def test_parent_validates_all_then_active_child_rechecks_material(self):
        with TemporaryDirectory() as td:
            parent=Parent(Path(td).resolve()/'test-only')
            from experiments.sdk_ablation_v1 import parent as module
            with patch.object(module,'verify',wraps=module.verify) as checked:
                parent.prepare(self.plan)
                self.assertEqual(checked.call_count,6)
                token=parent.claim()
                parent.check(token)
                self.assertEqual(checked.call_count,6)
            ledger=BatchLedger.create(parent,token)
            item=self.plan['cases'][0]
            ledger.begin(item['id'])
            authority=RehearsalAuthority(parent.root/'run/children'/item['id'])
            authority.prepare_fixture(item['plan'])
            ticket=authority.claim(item['hash'])
            with patch('experiments.sdk_ablation_v1.guard.load_entry',side_effect=ValueError('changed_source')):
                with self.assertRaisesRegex(ValueError,'changed_source'):
                    ticket.validate()
            # No request is made or reservation created after source revalidation failure.
            self.assertFalse((authority.root/'run/ledger.sqlite').exists())


if __name__ == '__main__':
    unittest.main()
