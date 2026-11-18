"""Offline evidence indexing only; does not change frozen analysis or infer judgments."""
import json,hashlib,collections,re
from pathlib import Path
P=Path(__file__).resolve().parents[1]
packets=[]
for f in sorted((P/'delivery/failure-audit').rglob('*.json')):
 x=json.loads(f.read_text());d=P/'evidence/run/trial'/x['instance_id']/x['arm'];outcomes={};calls={};local_requests={}
 for q in (d/'wire').glob('request-*.json'):
  messages=json.loads(q.read_text()).get('messages',[])
  for m in reversed(messages):
   match=re.search(r'Controller: request (\d+)/40',str(m.get('content',''))) if m.get('role')=='user' else None
   if match:local_requests[q.stem.split('-')[-1]]=int(match.group(1));break
  for m in messages:
   if m.get('role')=='tool':outcomes[m.get('tool_call_id')]=m.get('content')
 for q in (d/'wire').glob('response-*.json'):
  z=json.loads(q.read_text());n=local_requests.get(q.stem.split('-')[-1]);choices=z.get('choices',[])
  if choices:
   for tc in choices[0].get('message',{}).get('tool_calls',[]):calls.setdefault(n,[]).append(tc)
 seq=[]
 for t in x['tool_calls']:
  r=t.get('request');tc=next((c for c in calls.get(r,[]) if c.get('function',{}).get('name')==t['tool'] and all(t.get('arguments',{}).get(k)==v for k,v in json.loads(c.get('function',{}).get('arguments','{}')).items() if k!='summary')),{})
  raw=outcomes.get(tc.get('id'));obj=None
  if raw:
   try:obj=json.loads(raw)
   except ValueError:obj=raw
  stable={k:v for k,v in obj.items() if k!='elapsed_seconds'} if isinstance(obj,dict) else obj
  result=json.dumps(stable,ensure_ascii=False,sort_keys=True) if stable is not None else ''
  seq.append({'r':r,'tool':t['tool'],'args':t.get('arguments'),'exit':t.get('exit_code'),'edit':t.get('source_files_changed',[]),'result_hash':hashlib.sha256(result.encode()).hexdigest()[:12] if result else None,'result_tail':result[-500:]})
 x['sequence']=seq;x.pop('tool_calls');x['patch']=(d/'patch.diff').read_text() if (d/'patch.diff').exists() else None
 packets.append(x)
packets.sort(key=lambda x:(x['number'],x['arm']))
(P/'delivery/review-packets.json').write_text(json.dumps(packets,ensure_ascii=False,indent=2)+'\n')
print('Indexed',len(packets),'unresolved episodes; no judgments assigned.')
