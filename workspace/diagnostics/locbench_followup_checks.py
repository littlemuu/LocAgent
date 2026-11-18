"""Post-hoc static evidence checks, explicitly not autonomous agent performance."""
import ast,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.core import Snapshot,FileTools,page,encoded
from experiments.locbench_batch.control import frozen
from experiments.locbench_dev.prepare import functions
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/locbench-offline-diagnosis-v1'
items=[]
for case in frozen()['base_manifest']['cases']:
 p=ROOT/case['case_file'];cfg=json.loads(p.read_text());s=Snapshot(p.parent/'source',cfg['source_files']);tools=FileTools(s)
 labels=json.loads((ROOT/'locbench_openhands/v4/scoring-only'/f'{case["id"]}.json').read_text())
 gold=labels['gold_entities'][0];file,_,qual=gold.partition(':');line,end=functions(s.files[file])[qual]
 rendered,_=tools.render('read_file',{'path':file,'offset':0});cursor=rendered.index(str(line)+': ')
 actual,_=tools.render('read_file',{'path':file,'offset':cursor});packet=page(actual,cursor,4096)
 assert packet['text'].startswith(str(line)+': ') and ('def '+qual.rsplit('.',1)[-1]+'(') in packet['text']
 direct=page(rendered,line,4096)
 key='result.append("".join(row))' if case['id'].startswith('Delgan') else 'left = self._parse_primary() or self._parse_id_var()'
 assert key in packet['text'] and key not in direct['text']
 # These are analyst-selected after inspecting source and labels, not new unbiased queries.
 queries=['def _format','_format_list'] if case['id'].startswith('Delgan') else ['_parse_set_item_assignment','SetItem']
 searches=[]
 for query in queries:
  raw,_=tools.render('search_text',{'query':query,'offset':0});first=page(raw,0,4096)
  searches.append({'query':query,'raw':raw,'first_page':first,'gold_definition_first_page':('def '+qual.rsplit('.',1)[-1]+'(') in first['text']})
 # Confirm a complete function in saved exact-entity output matches the AST source lines.
 probe=json.loads((OUT/case['id']/'results.json').read_text());oracle=next(q for q in probe['queries'] if q['category']=='reference_oracle_exact')
 raw=(OUT/case['id']/oracle['locagent_retrieve']['raw_file']).read_text();body=raw.split('```\n',1)[1].rsplit('\n```',1)[0]
 retrieved='\n'.join(x.split(' | ',1)[1] for x in body.splitlines())
 expected=next(ast.get_source_segment(s.files[file],n) for n in ast.walk(ast.parse(s.files[file])) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.lineno==line)
 assert retrieved==expected
 items.append({'case':case['id'],'gold':gold,'gold_lines':[line,end],'correct_character_cursor':cursor,
  'line_number_as_cursor_page':direct,'correct_cursor_page':packet,'correct_read_bytes':len(encoded(packet)),
  'posthoc_searches':searches,'exact_entity_source_matches_ast_byte_for_byte':True,
  'oracle_label_used_for_checks':True})
with (OUT/'followup-static-checks.json').open('x') as f:json.dump(items,f,ensure_ascii=False,indent=2)
print(json.dumps([{'case':x['case'],'correct_cursor':x['correct_character_cursor'],'gold_lines':x['gold_lines'],'exact_entity_ast_match':True} for x in items]))
