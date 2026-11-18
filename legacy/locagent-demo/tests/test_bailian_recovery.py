import json
import unittest
from decimal import Decimal
from unittest.mock import patch
from locagent_service import bailian_contract as c
from locagent_service.bailian_recovery import combined_cost,recovery_manifest
from locagent_service.bailian_response import safe_response_json


class RecoveryTests(unittest.TestCase):
    def test_combined_budget_includes_unknown(self):
        self.assertEqual(combined_cost('0.262144',16),Decimal('0.524288'))
        self.assertEqual(combined_cost('0.262144',42),Decimal('0.950272'))
        with self.assertRaises(ValueError):combined_cost('0.262144',46)
        for amount in ('0','NaN','-1','0.01'):
            with self.assertRaises(ValueError):combined_cost(amount,42)

    def test_same_dataset_and_parent_not_mutated(self):
        old={'documents':[{'text':'same code'}],'questions':[{'text':'same question','relevant_entities':['same']}],
             'parameters':{'dimension':1024},'engine_files':{'old':'hash'}}
        original=c.canonical(old)
        with patch('locagent_service.bailian_recovery.engine_hashes',return_value={'new':'hash'}):
            result=recovery_manifest(old,{'parent':'hash'})
        self.assertEqual(c.canonical(old),original)
        for field in ('documents','questions','parameters'):self.assertEqual(result[field],old[field])
        self.assertEqual(result['recovery']['combined_full_reservation_cny'],'0.950272')

    def test_safe_json_retains_original_vector_and_usage(self):
        data={'request_id':'1ba94ac8-e058-99bc-9cc1-7fdb37940a46','output':{'embeddings':[{'embedding':[2.,0.],'text_index':0}]},'usage':{'total_tokens':27}}
        saved=safe_response_json(json.dumps(data).encode())
        self.assertEqual(saved['output']['embeddings'][0]['embedding'],[2.,0.])
        self.assertEqual(saved['usage'],{'total_tokens':27})
        self.assertNotIn('model',saved)

    def test_safe_json_never_keeps_arbitrary_strings(self):
        data={'message':'synthetic-secret','Authorization':'synthetic-secret','request_id':'sk-synthetic-secret',
              'model':'synthetic-secret','usage':{'total_tokens':'synthetic-secret'},'code':'synthetic-secret'}
        saved=safe_response_json(json.dumps(data).encode())
        self.assertNotIn('synthetic-secret',json.dumps(saved))


if __name__=='__main__':unittest.main()
