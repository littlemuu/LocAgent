import json
import sqlite3
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from jsonschema import Draft202012Validator, ValidationError
from experiments.cohort_finish_v5.finish_policy import (
    finish_message_schema, validate_finish, FINISH_FORMAT_INSTRUCTION)
from experiments.cohort_finish_v5.common_contract import (
    FINISH, CONTRACT, ContractError, raw_payload, validate_response, SharedWire)
from experiments.cohort_dev37_v4.common_contract import FINISH as OLD_FINISH
from experiments.cohort_preflight.entry import ROOT, read
from readonly_agent.core import Snapshot, encoded
from readonly_agent.preparation import make_plan
from readonly_agent.journal import Ledger


def reply(message, reason='tool_calls', name='finish'):
    return {'id':'fixture','model':'deepseek-flash',
        'choices':[{'finish_reason':reason,'message':{'role':'assistant','content':None,
            'tool_calls':[{'id':'fixture-call','type':'function','function':{
                'name':name,'arguments':json.dumps({'message':message})}}]}}],
        'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}


class Tests(unittest.TestCase):
    def setUp(self):
        self.validator=Draft202012Validator(finish_message_schema())
        self.snapshot=SimpleNamespace(files={'src/example.py':'', '目录/示例.py':''})
        self.answer={'files':['src/example.py'],'entities':['src/example.py:Worker.run'],'answer':'uncertain'}

    def test_historical_response_was_schema_valid_but_remains_invalid_prediction(self):
        plan=read(ROOT/'verification/dev37-batch-v4b/live.json')
        c=next(c for c in plan['cases'] if c['id']=='rwth-i6__sisyphus-191')
        ledger=ROOT/'verification/dev37-live-v4b/authority/run/children'/c['id']/c['hash']/'run/ledger.sqlite'
        with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
            raw=db.execute("SELECT response FROM calls WHERE arm='baseline' AND turn=4").fetchone()[0]
        z=json.loads(raw);before=deepcopy(z)
        message=json.loads(z['choices'][0]['message']['tool_calls'][0]['function']['arguments'])['message']
        Draft202012Validator(OLD_FINISH['function']['parameters']).validate({'message':message})
        errors=list(self.validator.iter_errors(message))
        self.assertEqual(len(errors),4)
        self.assertEqual({tuple(e.path) for e in errors},{('entities',i) for i in range(1,5)})
        with self.assertRaisesRegex(ContractError,'invalid_entity_format'):
            validate_response(z,{'finish'},True,0,self.snapshot)
        self.assertEqual(z,before)

    def test_file_only_answer_and_empty_answer_are_valid(self):
        for a in [{'files':['src/example.py'],'entities':[],'answer':'Only file location known.'},
                  {'files':[],'entities':[],'answer':'Insufficient evidence.'}]:
            self.validator.validate(a)
            self.assertEqual(validate_finish(a,self.snapshot),a)

    def test_valid_python_qualified_names_and_unicode(self):
        for entity in ['src/example.py:load','src/example.py:Worker.run','目录/示例.py:工厂.方法','src/example.py:outer.inner']:
            a={**self.answer,'entities':[entity]}
            self.validator.validate(a);self.assertEqual(validate_finish(a,self.snapshot),a)

    def test_bare_paths_and_empty_entity_components_rejected_by_schema(self):
        for entity in ['src/example.py','src/example.py:',':run','src/example.py:Worker..run',
                       'src/example.py:.run','src/example.py:Worker.','src/example.py:run\n']:
            with self.subTest(entity=entity),self.assertRaises(ValidationError):
                self.validator.validate({**self.answer,'entities':[entity]})

    def test_files_field_does_not_accept_entity_ids(self):
        with self.assertRaises(ValidationError):
            self.validator.validate({**self.answer,'files':['src/example.py:Worker']})

    def test_unsafe_paths_and_non_identifier_still_rejected_without_rewriting(self):
        for entity in ['../x.py:run','/x.py:run','.env:run','src/example.py:bad-name','src/example.py:123']:
            a={**self.answer,'entities':[entity]};before=deepcopy(a)
            with self.assertRaises(ValueError):validate_finish(a,self.snapshot)
            self.assertEqual(a,before)

    def test_unknown_safe_entities_remain_predictions_not_gold_oracle(self):
        a={**self.answer,'files':['unknown.py'],'entities':['unknown.py:Unseen']}
        self.validator.validate(a);self.assertEqual(validate_finish(a,self.snapshot),a)

    def test_non_content_null_extension_preserved_policy(self):
        a={**self.answer,'entities_note':None};self.validator.validate(a)
        self.assertEqual(validate_response(reply(a),{'finish'},True,0,self.snapshot),0)
        for extra in [{'entities_note':'discard me'},{'other':None}]:
            bad={**self.answer,**extra}
            with self.assertRaises(ValidationError):self.validator.validate(bad)
            with self.assertRaises(ValueError):validate_response(reply(bad),{'finish'},True,0,self.snapshot)

    def test_types_duplicates_and_maximum_items_still_rejected(self):
        for extra in [{'entities':None},{'entities':[1]},{'files':[None]},
                      {'entities':['src/example.py:Worker']*2},
                      {'entities':[f'src/example.py:f{i}' for i in range(6)]}]:
            with self.assertRaises(ValidationError):self.validator.validate({**self.answer,**extra})

    def test_both_tool_surfaces_are_replaced_with_identical_finish_schema(self):
        messages=[{'role':'system','content':'base'},{'role':'user','content':'issue'}]
        sdk={'type':'function','function':{'name':'finish','description':'SDK string message',
             'parameters':{'type':'object','properties':{'message':{'type':'string'}}}}}
        a=json.loads(raw_payload(messages,[OLD_FINISH],closing=False))
        b=json.loads(raw_payload(messages,[sdk],closing=False))
        self.assertEqual(a,b);self.assertEqual(a['tools'],[FINISH])
        self.assertIn(FINISH_FORMAT_INSTRUCTION,a['messages'][0]['content'])

    def test_closing_prompt_repeats_file_only_escape_and_budget_stays_fixed(self):
        q=json.loads(raw_payload([{'role':'system','content':'base'}],[FINISH],closing=True))
        self.assertIn(FINISH_FORMAT_INSTRUCTION,q['messages'][-1]['content'])
        self.assertIn('leave entities empty',q['messages'][-1]['content'])
        self.assertEqual(q['max_tokens'],2048)
        self.assertEqual(q['tool_choice']['function']['name'],'finish')
        self.assertEqual((CONTRACT['requests_per_arm'],CONTRACT['source_content_utf8_bytes']),(4,14336))

    def test_truncation_and_extra_investigation_still_stop(self):
        with self.assertRaisesRegex(ContractError,'output_truncated'):
            validate_response(reply(self.answer,reason='length'),{'finish'},True,0,self.snapshot)
        with self.assertRaises(ContractError):
            validate_response(reply(self.answer,name='read_file'),{'finish'},True,0,self.snapshot)

    def test_schema_adds_no_new_answer_length_cutoff(self):
        a={**self.answer,'answer':'Evidence; '*300}
        self.validator.validate(a);self.assertEqual(validate_finish(a,self.snapshot),a)

    def test_bad_finish_retains_receipt_and_halts_before_any_retry(self):
        with TemporaryDirectory() as td:
            root=Path(td).resolve();(root/'a.py').write_text('def run():\n    pass\n')
            snapshot=Snapshot(root,['a.py']);plan=make_plan(snapshot,'offline fixture',ROOT/'engine_adaptation/v4/engine')
            ledger=Ledger.create(root/'ledger.sqlite',plan);wire=SharedWire(ledger,'baseline',snapshot)
            bad={'files':['a.py'],'entities':['a.py'],'answer':'only file known'}
            body=reply(bad);seen=[]
            transport=httpx.MockTransport(lambda q:seen.append(1) or httpx.Response(200,json=body))
            with self.assertRaisesRegex(ContractError,'invalid_entity_format'):
                wire.exchange([{'role':'user','content':'fixture'}],[FINISH],True,transport)
            self.assertEqual(ledger.summary()['reason'],'invalid_entity_format')
            with ledger.transaction() as db:
                saved=json.loads(db.execute('SELECT response FROM calls').fetchone()[0])
                self.assertEqual(saved,body)
            with self.assertRaises(Exception):
                wire.exchange([{'role':'user','content':'fixture'}],[FINISH],True,transport)
            self.assertEqual(seen,[1])
            self.assertEqual(ledger.summary()['reserved_micro_cny'],0)

    def test_live_sdk_rejects_unadmitted_object_before_any_side_effect(self):
        from experiments.cohort_finish_v5.sdk_adapter import run_sdk_case
        with TemporaryDirectory() as td:
            out=Path(td)/'must_not_exist'
            with self.assertRaisesRegex(PermissionError,'explicit_live_session_required'):
                run_sdk_case(snapshot=None,issue='',script=None,output_dir=out,live=object())
            self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
