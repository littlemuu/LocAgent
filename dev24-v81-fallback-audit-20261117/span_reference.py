"""Parse already delivered source snippets only. No repository execution."""
import ast,json,re,textwrap
from pathlib import Path
O=Path(__file__).resolve().parent;cs=json.loads((O/'cases.json').read_text());data=[]
for index,path,start,stop,name in [
 (5,'sklearn/ensemble/voting.py',64,102,'fit'),
 (13,'astropy/modeling/separable.py',130,170,'_arith_oper'),
 (18,'sphinx/ext/viewcode.py',181,278,'collect_pages'),
 (19,'lib/matplotlib/figure.py',1335,1395,'align_xlabels')]:
 c=cs[index-1];lines={};origins={}
 for origin,ts in [('C',c['tool_audit']),('B_same_base',json.loads((O/'reference-v5'/c['instance_id']/'locator-result.json').read_text())['tool_audit'])]:
  for ti,t in enumerate(ts,1):
   if t['tool']!='read_file' or t['arguments']['path']!=path or 'error' in t['result']:continue
   for s in t['result'].get('text','').split('\n'):
    m=re.fullmatch(r'(\d+): (.*)',s)
    if not m:continue
    n=int(m[1]);value=m[2]
    if n in lines:assert lines[n]==value
    lines[n]=value;origins.setdefault(n,[]).append(f'{origin}/tool{ti}')
 assert all(n in lines for n in range(start,stop+1)),(index,[n for n in range(start,stop+1) if n not in lines])
 source=textwrap.dedent('\n'.join(lines[n] for n in range(start,stop+1)))
 tree=ast.parse(source);node=tree.body[0];assert isinstance(node,ast.FunctionDef) and node.name==name
 end=start+node.end_lineno-1
 item=dict(case_index=index,path=path,name=name,definition_start=start,definition_end=end,definition_length=end-start+1,proof='continuous same-base C/B tool source with next same-level definition boundary; AST parse only',uses_B_reference=any(not any(x.startswith('C/') for x in origins[n]) for n in range(start,end+1)))
 data.append(item)
 (O/f'cases/{c["instance_id"]}/reference-{name}-source.txt').write_text('\n'.join(f'{n}: {lines[n]}' for n in range(start,stop+1))+'\n')
(O/'derived-spans.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');print(json.dumps(data,indent=2))
