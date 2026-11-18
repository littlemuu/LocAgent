import json,hashlib,unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from readonly_agent.core import Snapshot,digest,encoded
from experiments.cohort_preflight.entry import ROOT,read,sha,validate_entry,load_entry,checked_file,save
from experiments.cohort_preflight.body import lines,chunks
from experiments.cohort_preflight.prepare import changed_old_lines,label_risks
from experiments.cohort_preflight.outcomes import aggregate,require_run_provenance
from experiments.cohort_preflight.batch import run_batch

class CohortTests(unittest.TestCase):
    def test_physical_lines_unicode_and_crlf(self):
        raw='\ufeffx="中\u2028文\x85字"\r\ny=2\rz=3\nlast'
        rows=lines(raw)
        self.assertEqual(len(rows),4);self.assertEqual(''.join(rows),raw)
        self.assertEqual(lines(''),[]);self.assertEqual(lines('\n'),['\n'])

    def test_chunk_line_number_and_raw_bytes(self):
        with TemporaryDirectory() as td:
            p=Path(td);source='x="a\u2028b"\r\n'*81;(p/'a.py').write_bytes(source.encode())
            rows=chunks(Snapshot(p,['a.py']))
            self.assertEqual(len(rows),2)
            self.assertEqual((rows[0]['metadata']['end_line'],rows[1]['metadata']['start_line']),(80,81))
            self.assertEqual(''.join(r['text'] for r in rows),source)

    def entry(self):
        return read(ROOT/'verification/cohort-preflight-v1/runtime/tobymao__sqlglot-3417.json')

    def test_gold_or_patch_field_rejected(self):
        for name in ['gold','patch','scoring','reference_answer']:
            value=self.entry();value[name]='DO_NOT_SEND'
            with self.assertRaises(ValueError):validate_entry(value)

    def test_issue_mutation_rejected(self):
        value=self.entry();value['issue']='changed issue'
        with self.assertRaises(ValueError):validate_entry(value)

    def test_real_entry_hash_and_cross_case_index(self):
        value=self.entry()
        with TemporaryDirectory() as td:
            p=Path(td).resolve()/'entry.json';save(p,value)
            _,snapshot=load_entry(p,sha(p));self.assertEqual(snapshot.identity,value['source_snapshot'])
            value['entity_index']='other/case'
            p.write_bytes(encoded(value))
            with self.assertRaisesRegex(ValueError,'cross_case_index'):load_entry(p,sha(p),check_engine=False)

    def test_hash_mismatch_and_symlink(self):
        with TemporaryDirectory() as td:
            p=Path(td)/'a';p.write_text('a');link=Path(td)/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):checked_file(p,'0'*64)
            with self.assertRaises(ValueError):checked_file(link,sha(p))

    def test_cross_case_body_snapshot_rejected_by_binding(self):
        a=self.entry();b=read(ROOT/'verification/cohort-preflight-v1/runtime/Delgan__loguru-1239.json')
        self.assertNotEqual(a['source_snapshot'],b['source_snapshot'])
        self.assertNotEqual(a['entity_attestation_sha256'],b['entity_attestation_sha256'])

    def test_diff_insert_and_delete_mapping(self):
        patch='diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -2,3 +2,3 @@\n x\n-old\n+new\n z\n'
        self.assertEqual(changed_old_lines(patch)['a.py'],{'removed':[3],'insertions':[4]})

    def test_omitted_label_is_risk_not_gold_rewrite(self):
        labels={'edit_functions':[],'added_functions':[],'patch':'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -2 +2 @@\n-old\n+new\n'}
        original=deepcopy(labels)
        graph={'nodes':[['a.py:f',{'type':'function','start_line':1,'end_line':4}]]}
        result=label_risks(labels,graph,{'a.py':'hash'})
        self.assertEqual(result['potential_edited_functions_omitted'],['a.py:f']);self.assertEqual(labels,original)

    def test_outside_snapshot_patch_detected(self):
        labels={'edit_functions':[],'added_functions':[],'patch':'diff --git a/setup.cfg b/setup.cfg\n--- a/setup.cfg\n+++ b/setup.cfg\n@@ -1 +1 @@\n-old\n+new'}
        self.assertEqual(label_risks(labels,{'nodes':[]},{})['patch_paths_outside_python_snapshot'],['setup.cfg'])

    def test_old_sdk_simulation_not_implicitly_live(self):
        historical={'status':'completed','quality_measured':False,'budget_simulation':{'simulation':True}}
        with self.assertRaises(ValueError):require_run_provenance(historical,'live')
        self.assertEqual(require_run_provenance(historical,'simulation'),'simulation')

    def test_explicit_live_receipt_required_not_quality_flag(self):
        with self.assertRaises(ValueError):require_run_provenance({'status':'completed'},'live')
        fixture={'quality_measured':False,'budget':{'mode':'live','simulation':False,'authorization':'one_use_claimed','calls':[{'id':1}]}}
        self.assertEqual(require_run_provenance(fixture,'live'),'live')

    def test_fixed_denominator_failure_and_not_run(self):
        rows=[{'case_id':'a','mode':'live','status':'completed','answer':{'entities':['x']},'failure':None},
              {'case_id':'b','mode':'live','status':'failed','answer':None,'failure':'timeout'}]
        result=aggregate(['a','b','c'],rows,{'a':['x']},mode='live')
        self.assertEqual((result['completed'],result['failed'],result['not_run']),(1,1,1))
        self.assertEqual(result['completed_only_mean']['Recall'],1)
        self.assertEqual(result['planned_denominator_adjusted']['Recall'],1/3)

    def test_simulation_never_scored(self):
        row={'case_id':'a','mode':'simulation','status':'completed','answer':{'entities':['x']},'failure':None}
        result=aggregate(['a'],[row],{},mode='simulation')
        self.assertFalse(result['quality_scored']);self.assertIsNone(result['completed_only_mean']['Acc'])
        with self.assertRaises(ValueError):aggregate(['a'],[row],{},mode='live')

    def test_duplicate_foreign_missing_gold_rejected(self):
        row={'case_id':'a','mode':'live','status':'completed','answer':{'entities':['x']},'failure':None}
        for expected,rows,gold in [(['a'],[row,row],{'a':['x']}),(['b'],[row],{}),(['a'],[row],{}),(['a'],[row],{'a':[]})]:
            with self.assertRaises(ValueError):aggregate(expected,rows,gold,mode='live')

    def test_batch_timeout_counts_unstarted_and_no_retry(self):
        seen=[]
        def execute(i,id):
            seen.append(id)
            if i==1:raise TimeoutError('fixture timeout')
            return {'case_id':id,'mode':'simulation','status':'completed','mock_requests':8,'real_model_requests':0}
        result=run_batch(['a','b','c'],execute)
        self.assertEqual(seen,['a','b']);self.assertEqual((result['completed'],result['failed'],result['not_started']),(1,1,1))

    def test_batch_duplicate_or_foreign_case_rejected(self):
        with self.assertRaises(ValueError):run_batch(['a','a'],lambda i,id:None)
        result=run_batch(['a','b'],lambda i,id:{'case_id':'other','status':'completed'})
        self.assertEqual((result['failed'],result['not_started']),(1,1))

    def test_batch_rejects_overbudget_result(self):
        result=run_batch(['a','b'],lambda i,id:{'case_id':id,'mode':'simulation','status':'completed','mock_requests':9,'real_model_requests':0})
        self.assertEqual((result['completed'],result['failed'],result['not_started']),(0,1,1))

if __name__=='__main__':unittest.main()
