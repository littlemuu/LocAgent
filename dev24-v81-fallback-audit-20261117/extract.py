"""Offline evidence extraction only: does not import/run frozen runtime or use network."""
import ast,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=Path(__file__).resolve().parent
RUN=ROOT/'dev24-locator-v81-20261117/evidence/run';POLICY=ROOT/'locator-diagnostic-calibration-v8.1/calibration/policy.py'
state=json.loads((RUN/'state.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
patterns={}
for node in ast.parse(POLICY.read_text()).body:
 if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ['STRONG','CITATION','ENTITY']:
  patterns[node.targets[0].id]=ast.literal_eval(node.value.args[0])
strong=re.compile(patterns['STRONG'],re.I);citation=re.compile(patterns['CITATION']);entity=re.compile(patterns['ENTITY'])
manifest={};case_data=[];violations=[]
for index,row in enumerate(state['rows'],1):
 identifier=row['instance_id'];case=RUN/'trial'/identifier;a_path=case/'locator/diagnostic-audit.json';r_path=case/'locator/result.json'
 a=json.loads(a_path.read_text());r=json.loads(r_path.read_text());answer=a['raw_packet']['answer']
 out=OUT/'cases'/identifier;out.mkdir(parents=True,exist_ok=True)
 (out/'raw-answer.txt').write_text(answer+'\n');write(out/'raw-packet.json',a['raw_packet'])
 tool_blocks=[]
 for ti,t in enumerate(r['tool_audit'],1):
  tool_blocks.append(f"TOOL {ti}: {t['tool']}\nARGS: {json.dumps(t['arguments'],ensure_ascii=False)}\nMETA: {json.dumps({k:v for k,v in t['result'].items() if k!='text'},ensure_ascii=False)}\n{t['result'].get('text','')}\n")
 (out/'tool-output.txt').write_text('\n'.join(tool_blocks))
 finish_wires=[]
 for p in sorted((case/'locator-wire').glob('response-*.json')):
  raw=json.loads(p.read_text())
  if any(c['function']['name']=='finish' for choice in raw.get('choices',[]) for c in choice.get('message',{}).get('tool_calls',[])):finish_wires.append(str(p))
 c=dict(index=index,instance_id=identifier,fallback=a['fallback'],raw_answer_path=str(out/'raw-answer.txt'),raw_audit_path=str(a_path),raw_finish_wire_paths=finish_wires,raw_packet=a['raw_packet'],source_bytes=r['source_bytes'],source_budget=14336,requests=r['requests'],tool_calls=r['tool_calls'],ranges=a['delivered_full_line_ranges'],pending=a['pending_read_pages'],entity_body_complete=a['entity_body_complete'],tool_audit=r['tool_audit'])
 case_data.append(c)
 for vi,v in enumerate(a['violations'],1):
  key=f'{index:02d}-{vi:02d}';rule=v[:2];target=v.partition(':')[2]
  matches=[]
  if rule=='R1':
   matches=[dict(line=n,text=line) for n,line in enumerate(answer.splitlines(),1) if target and target in entity.findall(line)]
   basis=dict(entity=target,structured_candidate=target in a['raw_packet']['entities'],exact_unread_same_line=any(target in entity.findall(line) and '未读完' in line for line in answer.splitlines()),entity_complete=a['entity_body_complete'].get(target,'not_stored_for_answer_only_entity'))
   path=target.partition(':')[0]
  elif rule=='R4':
   matches=[dict(line=n,text=line) for n,line in enumerate(answer.splitlines(),1) if target in line]
   m=citation.fullmatch(target);basis=dict(regex=patterns['CITATION'],citation=target,path=m['path'],start=int(m['start']),end=int(m['end'] or m['start'])) if m else dict(subrule=v)
   path=basis.get('path')
  else:
   matches=[dict(line=n,text=line,matches=[m.group() for m in strong.finditer(line)]) for n,line in enumerate(answer.splitlines(),1) if strong.search(line)]
   basis=dict(regex=patterns['STRONG']);path=None
  item=dict(id=key,case_index=index,instance_id=identifier,rule=rule,recorded_violation=v,matches=matches,basis=basis,credited_ranges_for_path=[x for x in a['delivered_full_line_ranges'] if x[0]==path],all_credited_ranges=a['delivered_full_line_ranges'],source_bytes=r['source_bytes'],source_budget_remaining=14336-r['source_bytes'],classification=None,reason=None)
  violations.append(item)
 write(out/'case-evidence.json',c)
 for p in [a_path,r_path,*[Path(p) for p in finish_wires]]:manifest[str(p.relative_to(ROOT))]=sha(p)
# Freeze all declared existing inputs. No directory traversal through benchmark datasets.
for folder in ['locator-diagnostic-calibration-v8.1','locator-diagnostic-calibration-v8']:
 base=ROOT/folder;fr=json.loads((base/'FREEZE.json').read_text())
 for path in ['FREEZE.json',*fr['files']]:manifest[str((base/path).relative_to(ROOT))]=sha(base/path)
write(OUT/'input-sha256.json',manifest);write(OUT/'cases.json',case_data);write(OUT/'violations-evidence.json',violations)
write(OUT/'patterns.json',patterns)
print(json.dumps(dict(cases=len(case_data),fallback=sum(c['fallback'] for c in case_data),violations=len(violations),by_rule={r:sum(v['rule']==r for v in violations) for r in ['R1','R2','R3','R4']})))
