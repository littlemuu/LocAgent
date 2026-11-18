"""Replay saved tool choices offline, explicitly translate old intended line numbers.

No claim of model behavior under the new protocol; no target code executes.
"""
import json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.core import FileTools,Snapshot,Limits
from readonly_agent.openhands_replay import run_sdk_case
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/read-lines-repair-v1'
oldroot=ROOT/'authority-locbench/eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83'
g=json.loads((oldroot/'grant.json').read_text());c=next(x for x in g['plan']['base_manifest']['cases'] if x['id']=='tobymao__sqlglot-3417')
p=ROOT/c['case_file'];case=json.loads(p.read_text());snapshot=Snapshot(p.parent/'source',case['source_files'])
class UnusedRetriever:
    snapshot_id=snapshot.identity
    def retrieve(self,q):raise AssertionError('retrieval_not_forced')
with sqlite3.connect((oldroot/'run/children'/c['plan_hash']/'run/ledger.sqlite').as_uri()+'?mode=ro',uri=True) as db:
    rows=db.execute('SELECT arm,turn,request,response FROM calls ORDER BY id').fetchall()
results=[]
for arm in ('baseline','retrieval'):
 own=[r for r in rows if r[0]==arm];script=[];translated=[]
 last_request=json.loads(own[-1][2]);old_observations={m['tool_call_id']:json.loads(m['content']) for m in last_request['messages'] if m['role']=='tool'}
 for _,turn,req,resp in own:
  content=[]
  for call in json.loads(resp)['choices'][0]['message']['tool_calls']:
   fn=call['function'];args=json.loads(fn['arguments']);args.pop('summary',None)
   if fn['name']=='read_file':
    old_offset=args.pop('offset',0)
    assert old_offset in (5960,5969)
    legacy,_=FileTools(snapshot).render('read_file',{'path':args['path'],'offset':old_offset})
    old_text=old_observations[call['id']]['text'];assert legacy[old_offset:old_offset+len(old_text)]==old_text
    assert '5977:' not in old_text
    args['start_line']=old_offset
    translated.append({'tool_call_id':call['id'],'old_numeric_offset':old_offset,'new_start_line':old_offset,
      'old_text_prefix':old_text[:100],'translation':'Analyst authored offline fixture, not automatic runtime coercion.'})
   elif fn['name']=='finish':args={'files':[],'entities':[],'answer':'Offline protocol replay only. No quality measurement.'}
   content.append({'type':'tool_use','id':call['id'],'name':fn['name'],'input':args})
  script.append({'stop_reason':'tool_use','content':content})
 out=OUT/('sqlglot-'+arm)
 result=run_sdk_case(snapshot=snapshot,issue=case['issue'],script=script,output_dir=out,
   retriever=UnusedRetriever() if arm=='retrieval' else None,limits=Limits(max_requests=4))
 assert result['status']=='completed' and result['requests']==4 and result['network_attempts']==0
 events=[json.loads(s) for s in (out/'trace.jsonl').read_text().splitlines()];observations=[]
 for e in events:
  data=e.get('data',{})
  if data.get('kind')=='ObservationEvent' and data.get('tool_name')=='read_file':
   obs=data['observation'];assert not obs.get('is_error',False)
   packet=json.loads(''.join(x['text'] for x in obs['content'] if x['type']=='text'))
   assert packet['start_line'] in (5960,5969)
   assert '5977:         left = self._parse_primary() or self._parse_id_var()' in packet['text']
   assert '5969:     def _parse_set_item_assignment(' in packet['text']
   observations.append(packet)
 assert len(observations)==2
 results.append({'arm':arm,'result':result,'translations':translated,'new_read_observations':observations})
with (OUT/'sqlglot-replay.json').open('x') as stream:json.dump({'mode':'offline_scripted_migration','model_requests':0,
 'original_results_modified':False,'original_model_choices_reused':True,'new_model_behavior_tested':False,'arms':results},stream,ensure_ascii=False,indent=2)
print('Both SDK arms completed four scripted turns; old wrong pages reproduced; new line reads include full target and line 5977; paid calls 0.')
