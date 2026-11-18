"""Actual SDK + isolated v6 retrieval; scripted decisions, no model requests/gold."""
import json
from pathlib import Path
from experiments.cohort_preflight.entry import ROOT,read,save,sha,load_entry
from experiments.sdk_ablation_v1.sdk_adapter import run_sdk_case
from experiments.retrieval_evidence_v6.offline_adapter import OfflineProcessRetriever
from readonly_agent.core import Limits,encoded

out=ROOT/'verification/retrieval-evidence-v6'
def response(name,args,n):
    return {'stop_reason':'tool_use','content':[{'type':'tool_use','id':f'fixture-{n}','name':name,'input':args}]}

rows=[]
for c in read(out/'manifest.json')['cases']:
    assert sha(c['spec'])==c['sha256']
    spec=read(c['spec']);binding=spec['binding'];value,snapshot=load_entry(binding['entry'],binding['entry_sha256'])
    prior=read(out/c['id']/'result.json')['rows'][0];q=prior['query']
    script=[response('locagent_retrieve',{'query':q,'offset':0},1)]
    if prior['new_first_page']['next_offset'] is not None:
        script.append(response('locagent_retrieve',{'query':q,'offset':prior['new_first_page']['next_offset']},2))
    if prior['new_audit']['candidates']:
        first=prior['new_audit']['candidates'][0];start=first['implementation_start'] or first['start_line']
        script.append(response('read_file',{'path':first['path'],'start_line':start,'end_line':min(start+7,first['end_line'])},3))
    else:
        script.append(response('search_text',{'query':q,'offset':0},3))
    script.append(response('finish',{'files':[],'entities':[],'answer':'Offline integration fixture; no quality conclusion.'},4))
    target=out/'sdk'/c['id']
    result=run_sdk_case(snapshot=snapshot,issue=value['issue'],script=script,output_dir=target,
                        retriever=OfflineProcessRetriever(c['spec'],c['sha256']),limits=Limits(max_requests=4))
    assert result['status']=='completed',result
    events=[json.loads(line) for line in (target/'trace.jsonl').read_text().splitlines()]
    audit=[t for e in events if e.get('event')=='tool_audit' for t in e['audit']]
    retr=[t for t in audit if t['tool']=='locagent_retrieve']
    assert retr[0]['result']==prior['new_first_page']
    assert all('error' not in t['result'] for t in audit)
    assert all(len(encoded(t['result']))<=4096 for t in audit)
    assert all(t['source_bytes']<=14336 and t['calls']<=16 for t in audit)
    rows.append({'id':c['id'],'completed':True,'scripted_requests':len(script),'real_requests':0,
                 'first_page_matches_replay':True,'tool_calls':len(audit),
                 'source_bytes':audit[-1]['source_bytes'],'live_transport':False})
    print(c['id'],'actual SDK + isolated retrieval passed',flush=True)
save(out/'sdk-check.json',{'rows':rows,'real_requests':0,'scripted_not_autonomous':True,'gold_read':False})
