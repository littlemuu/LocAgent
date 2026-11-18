"""Post-replay scoring only. No retrieval API is imported or called."""
import ast,json,re
from pathlib import Path
from experiments.cohort_preflight.entry import ROOT,read,save,sha
out=ROOT/'verification/replay-queries-v1';results=read(out/'results.json')
bindings={x['id']:x for x in read(ROOT/'verification/dev37-preparation-v4/scoring-only/gold-binding.json')};rows=[]
for c in results['cases']:
 spec=read(out/(c['id']+'.json'));binding=bindings[c['id']];assert sha(binding['original_label_path'])==binding['original_label_hash']
 entry=read(spec['binding']['entry']);graph=dict(read(Path(entry['entity_index']).parent/'graph.json')['nodes'])
 for i,q in enumerate(c['queries']):
  raw=(out/c['id']/f'query-{i}.txt').read_text();first=q['first_page']['text'];nodes=[x['id'] for x in q['candidate_order']];gold=binding['gold']
  primary=None
  if nodes:
   n=nodes[0];d=graph[n]
   if d['type'] in ('function','class'):
    unit=ast.parse(d['code']).body[0];body=unit.body
    doc=body[0] if body and isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and isinstance(body[0].value.value,str) else None
    implementation=body[1:] if doc else body
    impl_start=d['start_line']+implementation[0].lineno-1 if implementation else None
    # Restrict line-number measurement to primary entity segment before the next header.
    segment=first.split('##Searching for entity `',2)[1] if '##Searching for entity `' in first else ''
    lines=[int(x) for x in re.findall(r'^\s*(\d+) \|',segment,re.M)]
    primary={'id':n,'start_line':d['start_line'],'end_line':d['end_line'],'docstring_lines':None if doc is None else [d['start_line']+doc.lineno-1,d['start_line']+doc.end_lineno-1], 'implementation_start_line':impl_start,'visible_primary_first_page_last_line':max(lines) if lines else None,'implementation_start_visible':impl_start in lines if impl_start else None,'entity_end_line_visible':d['end_line'] in lines}
  rows.append({'id':c['id'],'query':q['query'],'original_page_exact':q['original_page_exact'],'query_from_first_model_turn':q['original_turn']==1,'no_prior_tool_evidence':not q['has_prior_tool_evidence'],'raw_utf8_bytes':q['raw_utf8_bytes'],'complete_return_page_count':len(q['full_pages']),'first_page_bytes':len(__import__('readonly_agent.core',fromlist=['encoded']).encoded(q['first_page'])),'candidates':nodes,'gold_ids_in_top5': [n for n in nodes if n in gold],'gold_ids_visible_first_page':[n for n in gold if n in first],'primary':primary,'gold_used_only_after_replay':True})
save(out/'evaluation.json',{'rows':rows,'raw_results_unchanged':True,'real_model_requests':0,'selection':'6 historically retrieved development cases / 7 real queries; not new held-out tests'})
print(json.dumps(rows,ensure_ascii=False))
