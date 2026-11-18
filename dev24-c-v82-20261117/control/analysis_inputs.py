import collections,json,re
from pathlib import Path
P=Path(__file__).resolve().parents[1];S=P/'completed-snapshot';O=P/'delivery/failure-audit';O.mkdir(exist_ok=True)
rows=[]
for case in sorted(S.iterdir()):
 if not (case/'task-summary.json').exists():continue
 row=json.loads((case/'task-summary.json').read_text())
 if row.get('resolved') is not False:continue
 r=json.loads((case/'C/coding.json').read_text());p=json.loads((case/'localization.json').read_text())
 tools=r['tool_audit'];commands=[]
 for t in tools:
  if t['tool']=='terminal':
   cmd=t['arguments']['command'];normalized=re.sub(r'\s+2>&1\s*\|\s*(?:sed|head|tail).*$', '',cmd,flags=re.S).strip();commands.append((t['request'],cmd,normalized))
 count=collections.Counter(n for _,_,n in commands);exact=collections.Counter(c for _,c,_ in commands)
 clusters=[{'normalized_command':n,'count':v,'requests':[req for req,_,key in commands if key==n]} for n,v in count.most_common() if v>1]
 out=O/case.name;out.mkdir(exist_ok=True)
 data={'instance_id':case.name,'requests':r['requests'],'used_all_40':r['requests']==40,'source_edit_events':r['source_edit_events'],'empty_patch':r['empty_patch'],'finished':r['finished'],'command_clusters':clusters,'exact_repeated_commands':[{'command':c,'count':n} for c,n in exact.most_common() if n>1],'tool_calls':tools,'localization':p['result'],'hypothesis_adoption':'待离线审阅','loop_judgment':'待离线审阅'}
 (out/'evidence.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 (out/'locator-answer.txt').write_text(p['result']['answer']+'\n')
 trace=['# '+case.name,'','定位包：','','```text',p['result']['answer'],'```','','编码终答：','','```text',str(r['finished']),'```','','工具记录：']
 for t in tools:trace+=['',f"请求 {t['request']} · {t['tool']} · exit={t['exit_code']} · 修改={t['source_files_changed']}",'```json',json.dumps(t['arguments'],ensure_ascii=False,indent=2),'```']
 (out/'trace.md').write_text('\n'.join(trace)+'\n');rows.append({'instance_id':case.name,'requests':r['requests'],'empty_patch':r['empty_patch'],'largest_command_cluster':clusters[0]['count'] if clusters else 1})
print(json.dumps(rows,ensure_ascii=False))
