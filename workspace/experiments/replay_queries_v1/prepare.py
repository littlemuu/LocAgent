"""Extract original model queries and their actual visible pages, without gold."""
import json,sqlite3
from experiments.cohort_preflight.entry import ROOT,read,save,sha
from readonly_agent.core import digest
out=ROOT/'verification/replay-queries-v1'
plan=read(ROOT/'verification/remaining17-v5-batch-v1/live.json');cases=[]
for item in plan['cases']:
 ledger=ROOT/'verification/remaining17-v5-live-v1/authority/run/children'/item['id']/item['hash']/'run/ledger.sqlite'
 with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
  calls=db.execute("SELECT turn,request,response,request_hash,response_hash FROM calls WHERE arm='retrieval' ORDER BY turn").fetchall()
 final=json.loads(calls[-1][1]);pages={m['tool_call_id']:m['content'] for m in final['messages'] if m['role']=='tool'}
 queries=[]
 for turn,req,res,rqh,rsh in calls:
  for call in json.loads(res)['choices'][0]['message']['tool_calls']:
   f=call['function']
   if f['name']!='locagent_retrieve':continue
   args=json.loads(f['arguments']);assert args.get('offset',0)==0
   page=json.loads(pages[call['id']]);queries.append({'query':args['query'],'offset':0,'original_turn':turn,'original_call_id':call['id'],'original_request_sha256':rqh,'original_response_sha256':rsh,'original_page':page,'original_page_bytes':len(pages[call['id']].encode()),'query_source':'original model tool call; no gold-derived rewrite','has_prior_tool_evidence':any(m['role']=='tool' for m in json.loads(req)['messages'])})
 if queries:
  value={'version':1,'id':item['id'],'binding':item['plan']['cohort_binding'],'snapshot':item['plan']['snapshot'],'queries':queries,'ledger':str(ledger),'ledger_sha256':sha(ledger),'runtime_hash':item['plan']['runtime_hash'],'engine':item['plan']['locagent_engine'],'retriever_sha256':sha(ROOT/'experiments/path_retrieval_v4/retriever.py')}
  save(out/(item['id']+'.json'),value);cases.append({'id':item['id'],'spec':str(out/(item['id']+'.json')),'sha256':sha(out/(item['id']+'.json')),'queries':len(queries)})
assert len(cases)==6 and sum(c['queries'] for c in cases)==7
save(out/'manifest.json',{'cases':cases,'query_count':7,'source':'saved real model calls; all pages measured at capacity4096','gold_read':False})
print('Frozen 7 original queries from 6 cases; no retrieval or model call yet.')
