import os,socket,sys,unittest,json
from pathlib import Path
ROOT=Path('/Users/xiaomu/Projects/LocAgent-OpenHands/legacy/locagent-demo')
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
os.environ.update(DO_NOT_TRACK='1',LITELLM_LOCAL_MODEL_COST_MAP='True',HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1')
attempts=[]
def blocked(*args,**kwargs):
 attempts.append('network_connect');raise RuntimeError('offline audit blocks network')
socket.socket.connect=blocked;socket.create_connection=blocked
suite=unittest.TestSuite()
for pattern in ['test_rag_offline.py','test_rag_graph_adapter.py','test_rag_review_regressions.py','test_offline_bailian_rrf.py']:
 suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=pattern))
r=unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skips':len(r.skipped),'network_attempts':len(attempts),'synthetic_embeddings_only':True}))
raise SystemExit(0 if r.wasSuccessful() and not attempts else 1)
