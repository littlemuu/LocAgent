"""Replay saved final answers only. No model, retrieval, SDK, repository execution."""
import collections,csv,hashlib,importlib.util,json,os,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2];O=R/'dev24-v82-offline-replay-20261117';F=R/'locator-diagnostic-calibration-v8.2'
blocked=[]
def fence(event,args):
 if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen','os.system'):
  blocked.append(event);raise RuntimeError('offline_fence:'+event)
 if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes,os.PathLike)) and 'holdout' in os.fsdecode(args[0]).casefold():raise PermissionError('holdout_forbidden')
sys.addaudithook(fence)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
freeze=json.loads((F/'FREEZE.json').read_text());assert all(sha(F/p)==h for p,h in freeze['files'].items())
spec=importlib.util.spec_from_file_location('soft_policy',F/'calibration/policy.py');policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
fixtures=json.loads((F/'tests/fixtures/v81-recorded24.json').read_text());rows=[];outputs={};input_hashes={}
for c in fixtures:
 ident=c['instance_id'];root=R/'dev24-locator-v81-20261117/evidence/run/trial'/ident
 original_audit=root/'locator/diagnostic-audit.json';original_result=root/'locator/result.json';original_packet=root/'localization.json'
 audit=json.loads(original_audit.read_text());result=json.loads(original_result.read_text());envelope=json.loads(original_packet.read_text())
 assert audit==c['audit'] and result['tool_audit']==c['tool_audit']
 matches=[]
 for name in c['original_finish_paths']:
  p=Path(name);wire=json.loads(p.read_text());input_hashes[str(p.relative_to(R))]=sha(p)
  for choice in wire['choices']:
   for call in choice['message'].get('tool_calls',[]):
    if call['function']['name']=='finish':
     raw=json.loads(call['function']['arguments'])['message'];raw=json.loads(raw) if isinstance(raw,str) else raw
     if raw==audit['raw_packet']:matches.append(str(p))
 assert matches
 delivered,new_audit=policy.calibrate(audit['raw_packet'],policy.EvidenceLedger.from_recorded(audit,result['tool_audit']))
 final={k:envelope[k] for k in ['version','instance_id','base_commit']};final['result']=delivered
 size=len(json.dumps(final,ensure_ascii=False).encode());assert size<=14336
 body=audit['raw_packet']['answer'];expected=body
 if new_audit['disclosure_count']:
  expected+='\n\n'+policy.DISCLOSURE_HEADING+'\n'+'\n'.join('- ['+d['rule']+'] '+'；'.join(d['targets']) for d in new_audit['disclosures'])
 assert not new_audit['fallback'] and delivered['answer']==expected and new_audit['validator_error'] is None
 out=O/'cases'/ident
 write(out/'localization.json',final);write(out/'diagnostic-audit.json',new_audit)
 (out/'delivered-answer.txt').write_text(delivered['answer']+'\n')
 write(out/'provenance.json',{'original_audit':str(original_audit),'original_result':str(original_result),'original_provider_finish':matches,'original_localization_metadata':str(original_packet),'v82_binding':freeze['v8_2_code_and_config_binding'],'replay_mode':'saved original finish + recorded C coverage/search/retrieval metadata; no source snapshot invented','new_API_calls':0,'model_calls':0,'body_sha256':hashlib.sha256(body.encode()).hexdigest(),'body_preserved':True,'serialized_envelope_bytes':size})
 for p in [original_audit,original_result,original_packet]:input_hashes[str(p.relative_to(R))]=sha(p)
 rows.append({'instance_id':ident,'full_fallback':new_audit['fallback'],'disclosure_count':new_audit['disclosure_count'],**new_audit['rule_counts'],'validator_error':new_audit['validator_error'],'original_body_preserved':True,'packet_bytes':size})
 outputs[ident]=(final,new_audit)
review=json.loads((R/'dev24-v81-fallback-audit-20261117/violations-reviewed.json').read_text());comparisons=[]
for v in review:
 final,audit=outputs[v['instance_id']];present=v['recorded_violation'] in audit['violations'];disclosed=v['recorded_violation'] in [d['violation'] for d in audit['disclosures']]
 if v['classification']=='真违规':assert disclosed,v['id']
 if v['classification']=='误判':assert not present,v['id']
 comparisons.append({'id':v['id'],'instance_id':v['instance_id'],'classification':v['classification'],'v81_violation':v['recorded_violation'],'v82_retained':present,'v82_disclosed':disclosed,'audit_reason':v['reason']})
new_flags=[]
for ident,(_,audit) in outputs.items():
 old={v['recorded_violation'] for v in review if v['instance_id']==ident}
 for v in audit['violations']:
  if v not in old:new_flags.append([ident,v])
summary={'binding':freeze['v8_2_code_and_config_binding'],'cases':len(rows),'full_fallback':sum(r['full_fallback'] for r in rows),'disclosure_cases':sum(r['disclosure_count']>0 for r in rows),'unchanged_without_disclosure':sum(r['disclosure_count']==0 for r in rows),'disclosure_items':sum(r['disclosure_count'] for r in rows),'residual_rules':{rule:sum(r[rule] for r in rows) for rule in ['R1','R2','R3','R4']},'validator_errors':sum(r['validator_error'] is not None for r in rows),'original_body_preserved':sum(r['original_body_preserved'] for r in rows),'true_violations_disclosed':sum(v['classification']=='真违规' and v['v82_disclosed'] for v in comparisons),'false_positives_removed':sum(v['classification']=='误判' and not v['v82_retained'] for v in comparisons),'boundaries_remaining':sum(v['classification']=='边界' and v['v82_retained'] for v in comparisons),'boundaries_removed':sum(v['classification']=='边界' and not v['v82_retained'] for v in comparisons),'new_findings_vs_55_reviewed':new_flags,'max_packet_bytes':max(r['packet_bytes'] for r in rows),'packet_byte_limit':14336,'model_calls':0,'API_calls':0,'new_API_cost_cny':0,'cloud_started':False,'Coding_Agent':'未运行','harness':'未运行','fresh_locator_investigation':'未运行','holdout_access':False,'blocked_external_actions':blocked,'scope':'Offline policy replay only; not a new model result/resolved measurement. Original search snippets support narrow facts only; original v8.1 coverage and retrieval metadata are used when full AST spans were not saved.'}
assert summary['cases']==24 and not blocked
write(O/'summary.json',summary);write(O/'per-case.json',rows);write(O/'review-crosscheck.json',comparisons);write(O/'replay-input-sha256.json',input_hashes)
for name,data in [('per-case.csv',rows),('review-crosscheck.csv',comparisons)]:
 with (O/name).open('w') as f:w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
# Three deliberately chosen examples: true R1, true R4 + unknown entity,
# and a remaining sparse-search boundary. Paste the entire packet without ellipses.
samples=['sympy__sympy-13480','django__django-13925','sphinx-doc__sphinx-11445']
lines=['# 三题 v8.2 最终交付包全文','','选取口径：真实 R1 缺口、真实 R4 连续引用缺口、稀疏搜索边界各一题。下面是完整 localization.json，包含 files/entities、原回答正文及附加披露；无删节。']
for ident in samples:
 final,_=outputs[ident];lines+=['',f'## {ident}','','```json',json.dumps(final,ensure_ascii=False,indent=2),'```']
(O/'THREE_FULL_PACKETS.md').write_text('\n'.join(lines)+'\n')
write(O/'sample-ids.json',samples)
print(json.dumps(summary,ensure_ascii=False,indent=2))
