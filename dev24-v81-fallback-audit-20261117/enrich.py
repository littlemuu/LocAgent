import ast,collections,hashlib,json,re,runpy,statistics
from pathlib import Path
O=Path(__file__).resolve().parent;ROOT=O.parent
cs=json.loads((O/'cases.json').read_text());vs=json.loads((O/'violations-evidence.json').read_text());D=runpy.run_path(str(O/'decisions.py'))['D']
spans={
 '03-02':(389,444,'C检索元数据；def至末行，不含装饰器'),
 '05-01':(64,101,'同base B补足95-101；C只到94；63行为已读装饰器'),
 '12-03':(6204,6218,'C检索元数据；def至末行，不含装饰器'),
 '13-01':(130,168,'同base B补足161-168；C只到160'),
 '18-03':(181,276,'同base B补足205-276；C只到204'),
 '23-03':(557,607,'C检索元数据；def至末行，不含装饰器'),
}
body_budget={'07-02':'总字节预算耗尽对继续读取头部缺口有直接限制（最后余51字节）；最初读取又从签名尾部760开始。不是唯一原因。',
'19-02':'最后续页容量已小于4096，返回止于1452且余25字节；总字节预算直接截断尾部。限定名/标注问题仍另计。',
'01-02':'题级预算确实耗尽（余11字节），但此实体存在模块/别名问题且未请求该完整定义；不能把这条R1直接归因于字节截断。',
'19-01':'题级预算耗尽，但实际所指align_xlabels的1335-1394已完整收到；这条主要是限定名/映射边界，非该函数正文被预算截断。',
'07-03':'题级预算耗尽，两个cursor未续读；原答已披露分页未续读，触发本条却是词面标注误判。'}
def runs(ns):
 out=[]
 for n in sorted(set(ns)):
  if out and n==out[-1][1]+1:out[-1][1]=n
  else:out.append([n,n])
 return out
read_audit=[]
for c in cs:
 if not c['fallback']:continue
 for ti,t in enumerate(c['tool_audit'],1):
  if t['tool']!='read_file' or 'error' in t['result']:continue
  text=t['result'].get('text','');full=[]
  for row in text.splitlines(keepends=True):
   m=re.match(r'(\d+): (.*)',row)
   if not m:continue
   n=int(m[1]);startcol=t['result'].get('start_column',0) if n==t['result'].get('start_line') else 0
   if startcol==0 and row.endswith('\n'):full.append(n)
  ranges=[x for x in c['ranges'] if x[0]==t['arguments']['path']]
  absent=[n for n in full if not any(a<=n<=b for _,a,b in ranges)]
  read_audit.append(dict(instance_id=c['instance_id'],tool_index=ti,complete_display_lines=len(full),not_credited=absent))
assert not any(r['not_credited'] for r in read_audit)
for v in vs:
 c=cs[v['case_index']-1];answer=c['raw_packet']['answer'];lines=answer.splitlines();path=v['basis'].get('path') or v['basis'].get('entity','').partition(':')[0]
 label,subtype,reason=D[v['id']];v.update(classification=label,subtype=subtype,reason=reason,raw_answer_path=c['raw_answer_path'],raw_audit_path=c['raw_audit_path'])
 if v['rule']=='R1':
  target=v['basis'].get('entity','');leaf=target.partition(':')[2].split('.')[-1]
  if not v['matches']:
   v['matches']=[dict(line=n,text=line) for n,line in enumerate(lines,1) if (leaf and leaf in line) or (not target and any(x in line for x in ['cursor','分页']))]
  if v['basis'].get('structured_candidate'):v['structured_candidate_literal']=target
  v['unread_context']=[dict(line=n,text=line) for n,line in enumerate(lines,1) if any(x in line for x in ['未读','未续读','截断','未核验'])]
  if not target:v['basis']=dict(condition='pending非空且未核验段缺少字面“未读完”或“分页”',pending=c['pending'])
  else:v['basis']['condition']='complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化'
 else:v['unread_context']=[]
 # Distinguish actual returned source/search observations from validator-credited full lines.
 possible_paths={x[0] for x in c['ranges']}
 searches=[]
 for ti,t in enumerate(c['tool_audit'],1):
  if t['tool']=='read_file':possible_paths.add(t['arguments']['path'])
  if t['tool']=='search_text':
   for line in t['result'].get('text','').splitlines():
    m=re.match(r'([^:]+):(\d+): (.*)',line)
    if not m:continue
    possible_paths.add(m[1]);n=int(m[2])
    if path and (m[1]==path or m[1].endswith('/'+path)):
     if v['rule']!='R4' or v['basis'].get('start',n)<=n<=v['basis'].get('end',n):searches.append(dict(tool_index=ti,path=m[1],line=n,text=m[3]))
 resolved=[p for p in sorted(possible_paths) if p==path or p.endswith('/'+path)] if path else []
 v['canonical_path_candidates']=resolved
 v['search_hit_evidence']=searches
 v['read_file_observations']=[]
 for ti,t in enumerate(c['tool_audit'],1):
  if t['tool']=='read_file' and (not path or t['arguments']['path'] in resolved):
   v['read_file_observations'].append(dict(tool_index=ti,path=t['arguments']['path'],requested=t['arguments'],delivered_metadata={k:w for k,w in t['result'].items() if k!='text'},cumulative_source_bytes=t.get('source_bytes')))
 v['canonical_credited_ranges']=[x for x in c['ranges'] if x[0] in resolved]
 if v['rule']=='R1':
  v['function_span']=None
  if v['id'] in spans:
   a,b,provenance=spans[v['id']];v['function_span']=dict(start=a,end=b,length=b-a+1,provenance=provenance,definition_excludes_decorators=True)
   v['entity_read_intersection']=runs(n for p,x,y in c['ranges'] if p==path for n in range(max(a,x),min(b,y)+1))
  else:v['entity_read_intersection']='实体边界未知；仅报告文件已读范围，不冒充完整实体范围'
  if v['id']=='19-01':v['possible_referent_span']=dict(start=1335,end=1394,length=60,note='实际方法定义范围可确认；报错Figure限定名与FigureBase映射未确认，不纳入精确ID长度统计')
  if v['id']=='10-04':v['function_length_status']='不适用：builtin_str为别名赋值'
  elif not v['basis'].get('entity'):v['function_length_status']='不适用：分页规则'
  else:v['function_length_status']='已知def范围' if v['function_span'] else '未知'
  v['budget_assessment']=body_budget.get(v['id'],'未耗尽14,336总字节；不能将缺口归于总字节上限。可能有4096单页截断、未续读、cursor错误、请求次数结束、所选范围不足或实体身份问题，见原工具记录。')
counts={r:{k:sum(v['rule']==r and v['classification']==k for v in vs) for k in ['真违规','误判','边界']} for r in ['R1','R2','R3','R4']}
fallback_cs=[c for c in cs if c['fallback']]
remain=[c['instance_id'] for c in fallback_cs if any(v['instance_id']==c['instance_id'] and v['classification']!='误判' for v in vs)]
removed=[c['instance_id'] for c in fallback_cs if c['instance_id'] not in remain]
truecases=[c['instance_id'] for c in fallback_cs if any(v['instance_id']==c['instance_id'] and v['classification']=='真违规' for v in vs)]
lengths=sorted(b-a+1 for a,b,_ in spans.values())
summary=dict(records=55,counts=counts,total_counts={k:sum(v['classification']==k for v in vs) for k in ['真违规','误判','边界']},
 original_fallback=dict(count=20,total=24,rate=20/24),estimated_after_removing_confirmed_false_positives=dict(count=len(remain),total=24,rate=len(remain)/24,retained=remain,released=removed,boundary_still_blocks=True,method='annotated existing triggers only; no rerun, no new failures inferred'),
 sensitivity=dict(known_true_cases=len(truecases),true_case_ids=truecases,if_all_boundary_flags_waived=len(truecases)/24,if_R3_prefix_semantics_remains_literal=dict(count=15,rate=15/24),note='25% is only an optimistic policy sensitivity bound, NOT the false-positive-only estimate'),
 R1_lengths=dict(entity_flags=23,pagination_flags=2,non_function_aliases=1,function_like_flags=22,exact_identity_def_ranges=6,possible_referent_ranges=1,unknown_exact_ranges=16,lengths=lengths,min=min(lengths),median=statistics.median(lengths),max=max(lengths),bins={'1-50':sum(x<=50 for x in lengths),'51-100':sum(51<=x<=100 for x in lengths),'>100':sum(x>100 for x in lengths)},definition='def到AST末行，含docstring、不含装饰器；只对可核实6项统计，不能外推全部函数'),
 R1_budget=dict(R1_case_count=17,global_cap_closed_cases=[c['instance_id'] for c in fallback_cs if c['source_bytes']>14336-64 and any(v['instance_id']==c['instance_id'] and v['rule']=='R1' for v in vs)],R1_records_in_cap_cases=5,entity_gaps_with_direct_budget_contribution=['07-02','19-02'],note='题级触顶不等于每条R1由预算造成；剩余14题未耗尽总字节上限。4096单页和14336总预算分开统计。'),
 read_line_accounting=dict(read_file_calls_checked=len(read_audit),complete_display_lines_checked=sum(x['complete_display_lines'] for x in read_audit),full_display_lines_not_credited=0,limitation='仅核对日志中从列0开始且以换行结束的完整read_file显示行；无完整快照，不能重建所有AST/字符覆盖'),
 scope=dict(network_calls=0,API_calls=0,cloud_started=False,locator_rerun=False,frozen_modified=False,holdout_access=False,B_reference='20题同base_commit历史B定位日志仅辅助边界，未计入C阅读覆盖'))
(O/'violations-reviewed.json').write_text(json.dumps(vs,ensure_ascii=False,indent=2)+'\n');(O/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');(O/'read-line-crosscheck.json').write_text(json.dumps(read_audit,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
