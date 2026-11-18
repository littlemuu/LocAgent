"""Real PostgreSQL/HTTP/worker tests for bounded prepared-source long admission."""
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import stage2_postgres_acceptance as base
from locagent_service.budget import LIVE_CONFIG
from locagent_service.demo import process_env
from locagent_service.sources import canonical,digest,file_hashes
from prepared_offline_worker import SENTINEL


class PreparedCompatibilityAcceptance(unittest.TestCase):
    cleanup=base.PostgresAcceptance.cleanup
    child=base.PostgresAcceptance.child
    api=base.PostgresAcceptance.api
    await_worker=base.PostgresAcceptance.await_worker

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.registry=Path(self.tmp.name)
        env=patch.dict(os.environ,{'LOCAGENT_SOURCE_ROOT':str(self.registry),
                                  'LOCAGENT_ALLOW_PAID':'0','LITELLM_LOCAL_MODEL_COST_MAP':'True',
                                  'HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1'})
        env.start();self.addCleanup(env.stop)
        base.PostgresAcceptance.setUp(self)

    def source(self,text):
        import networkx as nx
        bundle=self.registry/('bundle-'+digest(text.encode())[:12]);bundle.mkdir()
        graph=nx.MultiDiGraph();graph.add_node('.',type='directory')
        graph.add_node('demo.py',type='file',code='def render():\n    return 1\n')
        graph.add_node('demo.py:render',type='function',code='def render():\n    return 1',
                       start_line=1,end_line=2)
        graph.add_edge('.','demo.py',type='contains');graph.add_edge('demo.py','demo.py:render',type='contains')
        (bundle/'graph.pkl').write_bytes(pickle.dumps(graph))
        manifest={'version':2,'bundle':bundle.name,'task':{'instance_id':'demo__demo-1','repo':'demo/demo',
                  'base_commit':'a'*40,'problem_statement':text},'artifacts':file_hashes(bundle),'engine':{},
                  'config':{**LIVE_CONFIG,'top_k':5,'search_protocol':'bounded-v1',
                            'budget_policy':'locagent-followup5-v1'}}
        data=canonical(manifest);source='prepared-'+digest(data)
        (self.registry/(source+'.json')).write_bytes(data)
        return source

    def body(self,source,text):
        return {'source_id':source,'problem_statement':text,'options':{'max_iterations':3,
                'suppress_repeats':True},'max_attempts':1,'timeout_seconds':90}

    def worker(self):
        log=(self.artifacts/'offline-worker.log').open('w');self.logs.append(log)
        process=subprocess.Popen([sys.executable,'-B','tests/prepared_offline_worker.py','--once'],
            cwd=base.ROOT,env=process_env(self.settings),stdout=log,stderr=subprocess.STDOUT)
        self.processes.append(process)
        return process

    def test_full_long_http_database_worker_and_label_sentinel(self):
        text='Complete frozen issue:\n'+'x'*(22778-len('Complete frozen issue:\n'))
        source=self.source(text);(self.registry/'scoring-only.txt').write_text(SENTINEL)
        _,client,_=self.api()
        body=self.body(source,text)
        self.assertEqual(client.post('/tasks',json={**body,'labels':SENTINEL}).status_code,422)
        created=client.post('/tasks',json=body,headers={'Idempotency-Key':'long-source'})
        self.assertEqual(created.status_code,202,created.text)
        task=created.json();self.assertEqual(task['request']['problem_statement'],text)
        child=self.worker();self.assertNotIn(SENTINEL,str(child.args));self.await_worker(child)
        result=client.get('/tasks/'+task['id']).json()
        self.assertEqual(result['status'],'completed',result.get('error'))
        self.assertEqual(result['request']['problem_statement'],text)
        messages=result['result']['messages']
        self.assertTrue(any(text in (m.get('content') or '') for m in messages))
        self.assertNotIn(SENTINEL,json.dumps(result['request']))
        self.assertNotIn(SENTINEL,json.dumps(messages))
        self.assertLessEqual(max(result['result']['diagnostics']['request_byte_estimates']),65536)
        self.assertEqual(result['result']['diagnostics']['termination_reason'],'finished')
        self.assertEqual(result['result']['iterations'],3)
        audit=result['result']['diagnostics']['offline_acceptance']
        self.assertEqual(audit['child_input_sha256'],digest(canonical(result['request'])))
        self.assertTrue(audit['label_sentinel_absent'])
        history=client.get('/tasks/'+task['id']+'/attempts').json()
        self.assertEqual(len(history),1);self.assertEqual(history[0]['outcome'],'completed')

    def test_http_boundaries_forged_source_mismatch_and_manifest_tamper(self):
        text='x'*32768;source=self.source(text);_,client,_=self.api()
        body=self.body(source,text)
        accepted=client.post('/tasks',json=body);self.assertEqual(accepted.status_code,202,accepted.text)
        invalid=[{'problem_statement':'x'*8001},self.body(source,text+'x'),
                 self.body('prepared-'+'f'*64,'x'*8001),self.body(source,'y'+text[1:]),
                 {**body,'persisted_task':True}]
        for value in invalid:
            with self.subTest(length=len(value['problem_statement'])):
                self.assertEqual(client.post('/tasks',json=value).status_code,422)
        path=self.registry/(source+'.json');path.write_bytes(path.read_bytes()+b' ')
        self.assertEqual(client.post('/tasks',json=body).status_code,422)

    def test_history_and_exact_idempotent_replay_survive_source_removal(self):
        text='x'*8001;source=self.source(text);_,client,_=self.api()
        body=self.body(source,text);headers={'Idempotency-Key':'retained-long'}
        first=client.post('/tasks',json=body,headers=headers)
        self.assertEqual(first.status_code,202,first.text);task=first.json()
        (self.registry/(source+'.json')).unlink()
        replay=client.post('/tasks',json=body,headers=headers)
        self.assertEqual(replay.status_code,202,replay.text)
        self.assertEqual(replay.json()['id'],task['id'])
        stored=client.get('/tasks/'+task['id'])
        self.assertEqual(stored.status_code,200,stored.text)
        self.assertEqual(stored.json()['request']['problem_statement'],text)
        self.assertEqual(client.post('/tasks',json=body).status_code,422)
