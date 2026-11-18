"""Real graph and contract checks. No source execution, no model invocation."""
from adapter import ROOT,PROJECT,save,task,normalize,FIELDS
import os,sys,json,hashlib,socket,unittest
for key in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','DEEPSEEK_API_KEY','DASHSCOPE_API_KEY'):os.environ.pop(key,None)
os.environ.update(LOCAGENT_ALLOW_PAID='0',LITELLM_LOCAL_MODEL_COST_MAP='True',HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',MPLCONFIGDIR=str(ROOT/'mpl'),NLTK_DATA='/Users/xiaomu/Documents/Codex/locagent-expanded-eval-prep-20261107-r2/cache/nltk_data')
sys.path.insert(0,str(PROJECT))
import dotenv
dotenv.load_dotenv=lambda *a,**k:False
from locagent_service.offline import offline_engine
from util.localization_contract import LocalizationRequest
import pyarrow.parquet as pq
rows=pq.read_table(ROOT/'scoring-only/test-00000-of-00001.parquet').to_pylist()
class Checks(unittest.TestCase):
 def test_all_contracts(self):
  for row in rows:self.assertEqual(LocalizationRequest(**task(row)).as_task(),task(row))
 def test_input_allowlist(self):
  for p in (ROOT/'inputs').glob('*/task.json'):
   d=json.loads(p.read_text());self.assertEqual(set(d),set(FIELDS))
 def test_poison_fields_discarded(self):
  r=dict(rows[0]);r.update(patch='SECRET_PATCH',hints_text='SECRET_HINT',edit_functions=['SECRET_GOLD'],test_patch='SECRET_TEST')
  self.assertNotIn('SECRET',json.dumps(task(r)))
 def test_constructor_normalization(self):
  self.assertEqual(normalize('f.py:C.__init__'),'f.py:C');self.assertEqual(normalize('f.py:__init__'),'f.py:__init__')
 def test_exact_source_hashes(self):
  for p in (ROOT/'samples').glob('*/source.json'):
   d=json.loads(p.read_text())
   for f,h in d['python_files'].items():self.assertEqual(hashlib.sha256((p.parent/'repo'/f).read_bytes()).hexdigest(),h)
res=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
assert res.wasSuccessful()
with offline_engine():
 from locagent_service.prepare import build_indexes
 summaries=[]
 gold=json.loads((ROOT/'scoring-only/labels.json').read_text())
 for p in sorted((ROOT/'samples').glob('*/source.json')):
  d=json.loads(p.read_text());i=d['instance_id'];bundle=p.parent/'indexes';bundle.mkdir(exist_ok=False)
  graph=build_indexes(p.parent/'repo',bundle,i)
  files={n for n,v in graph.nodes(data=True) if v['type']=='file'};labels=gold[i]['official_function_labels']
  mapped=[{'label':e,'node_type':graph.nodes[e]['type']} for e in labels if e in graph]
  result={'instance_id':i,'python_files':len(d['python_files']),'graph_file_nodes':len(files),'missing_file_nodes':sorted(set(d['python_files'])-files),'nodes':len(graph),'edges':graph.number_of_edges(),'label_count':len(labels),'mapped_labels':mapped,'missing_labels':[e for e in labels if e not in graph],'bm25_built':(bundle/'bm25'/i/'corpus.jsonl').exists()}
  summaries.append(result);print(json.dumps(result),flush=True)
 save(ROOT/'graph-check.json',{'cases':summaries,'unit_tests':res.testsRun,'model_calls':0,'offline_guard_completed_without_exception':True,'sample_scope':'3 convenience-sample repositories, not all 560 cases','source_execution':False})
