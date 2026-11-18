import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from decimal import Decimal
from locagent_service import bailian_contract as c
from locagent_service import bailian_retrieval_experiment as run
from locagent_service.bailian_memory_evaluation import verify_response,cached_request,assemble,dense_rank,fuse,sha
from locagent_service.bailian_experiment import metrics


def unit(i=0):
    v=[0.]*1024;v[i]=1.;return v


class EvidenceAssemblyTests(unittest.TestCase):
    def fixture(self):
        body=c.canonical(c.request(['public'],'document'))
        request={'body':body,'sha256':sha(body),'count':1,'role':'document','ids':['d']}
        raw=c.canonical({'output':{'embeddings':[{'index':0,'embedding':unit()}]},'usage':{'prompt_tokens':2,'total_tokens':2}})
        binding={'manifest_sha256':'a'*64,'request_sha256':sha(body),'response_sha256':sha(raw),'http_status':200}
        return raw,binding,request,('settled',sha(body),sha(raw))

    def test_source_hashes_and_ledger_tampering_rejected(self):
        raw,binding,request,row=self.fixture();self.assertEqual(verify_response(raw,binding,'a'*64,request,row)[1],2)
        for key in ('manifest_sha256','request_sha256','response_sha256'):
            changed=dict(binding);changed[key]='f'*64
            with self.subTest(key=key),self.assertRaises(ValueError):verify_response(raw,changed,'a'*64,request,row)
        with self.assertRaises(ValueError):verify_response(raw+b' ',binding,'a'*64,request,row)
        with self.assertRaises(ValueError):verify_response(raw,binding,'a'*64,request,('unknown',row[1],row[2]))

    def test_cache_parameters_input_identity_and_role_isolation(self):
        doc={'id':'d','text':'public'}
        source={'endpoint':'https://fixed','model':c.MODEL,'dimensions':1024,'document_parameters':c.request(['x'],'document')['parameters'],'documents':[doc]}
        target=copy.deepcopy(source)
        self.assertEqual(cached_request(source,target,doc,0)['role'],'document')
        for field,value in [('endpoint','https://other'),('model','other'),('dimensions',768),('document_parameters',c.request(['x'],'query')['parameters'])]:
            wrong=copy.deepcopy(source);wrong[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):cached_request(wrong,target,doc,0)
        with self.assertRaises(ValueError):cached_request(source,target,{'id':'d','text':'altered'},0)

    def test_missing_duplicate_wrong_role_and_extra_input_fail(self):
        m={'documents':[{'id':'d'}],'questions':[{'id':'q'}]}
        valid=[('document',['d'],[unit()]),('query',['q'],[unit(1)])]
        self.assertEqual(len(assemble(m,valid)),2)
        for parts in (valid[:1],valid+[valid[0]],[('query',['d'],[unit()]),valid[1]],valid+[('document',['x'],[unit()])],[('document',['d'],[])]+valid[1:]):
            with self.assertRaises(ValueError):assemble(m,parts)

    def test_exact_ranking_entity_dedup_and_ties(self):
        docs=[{'id':'a','entity':'a'},{'id':'b','entity':'b'},{'id':'c','entity':'a'}]
        values={('document','a'):unit(1),('document','b'):unit(),('document','c'):unit()}
        self.assertEqual(dense_rank(docs,values,unit()),['a','b'])
        self.assertEqual(fuse(['b','a'],['a','b']),['a','b'])

    def test_scoring_missing_questions_not_dropped(self):
        qs=[{'id':'q1','relevant_entities':['a']},{'id':'q2','relevant_entities':['b']}]
        scores=metrics(qs,{'q1':['a']},1)
        self.assertEqual(scores['hit_at_k'],.5);self.assertEqual(scores['macro_recall_at_k'],.5)

    def test_cumulative_budget_keeps_old_reservations(self):
        self.assertEqual(run.combined(40),Decimal('1.277952'))
        self.assertEqual(run.combined(0),Decimal('0.622592'))
        for n in (41,-1,True):
            with self.assertRaises(ValueError):run.combined(n)
        with self.assertRaises(ValueError):run.combined(40,Decimal('0.557056'))


class FrozenRunTests(unittest.TestCase):
    def setUp(self):
        self.m=run.expected_manifest();self.reqs=run.requests(self.m)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        for name,value in [('FOLDER',root/'run'),('LOCK',root/'run.lock'),('PLAN',root/'plan.json')]:
            p=patch.object(run,name,value);p.start();self.addCleanup(p.stop)
        p=patch.object(run,'validate',return_value=(self.m,self.reqs));p.start();self.addCleanup(p.stop)
        p=patch.object(run,'load_env_file',side_effect=lambda *a:{'DASHSCOPE_WORKSPACE_ID':run.WORKSPACE,'DASHSCOPE_API_HOST':run.ORIGIN,'DASHSCOPE_API_KEY':'synthetic-test-only'});p.start();self.addCleanup(p.stop)

    def fake(self,body,config):
        texts=json.loads(body)['input']['texts']
        return 200,c.canonical({'usage':{'prompt_tokens':len(texts),'total_tokens':len(texts)},'output':{'embeddings':[{'index':i,'embedding':unit(int(sha(text.encode())[:4],16)%1024)} for i,text in enumerate(texts)]}})

    def test_fixed_membership_batches_and_role_parameters(self):
        self.assertEqual([r['count'] for r in self.reqs],[16,14,10])
        self.assertEqual([r['role'] for r in self.reqs],['document','document','query'])
        self.assertEqual(len(self.m['documents']),32);self.assertEqual(len(self.m['questions']),10)
        self.assertNotIn('instruct',json.loads(self.reqs[0]['body'])['parameters'])
        self.assertEqual(json.loads(self.reqs[2]['body'])['parameters']['instruct'],c.INSTRUCTION)

    def test_offline_full_assembly_retrieval_and_no_authorization_replay(self):
        with patch.object(run,'exchange',side_effect=self.fake) as transport:
            for i in range(3):self.assertEqual(run.step(i)['journal']['calls'][-1]['state'],'settled')
            self.assertEqual(transport.call_count,3)
            result=run.finish();self.assertEqual(result['state'],'completed')
            saved=json.loads((run.FOLDER/'results.json').read_bytes())
            self.assertEqual(len(saved['source_inventory']),5)
            self.assertEqual(len(saved['retrieval']['per_query']),10)
            for i in range(3):
                with self.assertRaises((ValueError,FileExistsError)):run.step(i)
            self.assertEqual(transport.call_count,3)
            self.assertTrue((run.FOLDER/'response-002.body.bin').exists())

    def test_failure_halts_later_inputs_and_raw_body_survives(self):
        with patch.object(run,'exchange',return_value=(200,b'not-json')) as transport:
            self.assertEqual(run.step(0)['journal']['calls'][0]['state'],'unknown')
            self.assertEqual((run.FOLDER/'response-000.body.bin').read_bytes(),b'not-json')
            with self.assertRaises(ValueError):run.step(1)
            self.assertEqual(transport.call_count,1)


if __name__=='__main__':unittest.main()
