"""Static trace/reference review; never imports or executes target modules."""
import ast,hashlib,json,re,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.core import Snapshot,FileTools,page,encoded
from experiments.locbench_dev.prepare import functions,git_hash
from experiments.locbench_dev.scoring import score
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/locbench-offline-diagnosis-v1'
H='eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83'
run=ROOT/'authority-locbench'/H/'run';grant=json.loads((run.parent/'grant.json').read_text())
measure=json.loads((run/'measurements.json').read_text());evidence=json.loads((ROOT/'locbench_openhands/v4/upstream-evidence.json').read_text())
results=[]
for case in grant['plan']['base_manifest']['cases']:
 identifier=case['id'];casepath=ROOT/case['case_file'];cfg=json.loads(casepath.read_text())
 snapshot=Snapshot(casepath.parent/'source',cfg['source_files']);tools=FileTools(snapshot)
 labels=json.loads((ROOT/'locbench_openhands/v4/scoring-only'/f'{identifier}.json').read_text())
 original=next(Path(p) for p in evidence if p.endswith('/scoring-only/labels/'+identifier+'.json'))
 assert hashlib.sha256(original.read_bytes()).hexdigest()==evidence[str(original)]==labels['labels_sha256']
 reference=json.loads(original.read_text());gold=labels['gold_entities'][0];path,_,qual=gold.partition(':')
 assert reference['edit_functions']==labels['gold_entities']
 span=functions(snapshot.files[path])[qual];mapped=labels['mapping']['gold_mappings'][0]['strict_ast']
 assert span==(mapped['start_line'],mapped['end_line'])
 assert git_hash('blob',snapshot.files[path].encode())==labels['mapping']['patch_checks'][0]['verified_blob']
 # Validate each old hunk against fixed source, reconstruct revised text in memory, AST parse only.
 patch=reference['patch'];source=snapshot.files[path].splitlines(keepends=True);out=[];cursor=0;plines=patch.splitlines(keepends=True);j=0;hunks=[]
 while j<len(plines):
  match=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',plines[j])
  if not match:j+=1;continue
  start=int(match[1])-1;before=[];after=[];j+=1
  while j<len(plines) and not plines[j].startswith(('@@ ','diff --git')):
   line=plines[j]
   if line.startswith(' '):before.append(line[1:]);after.append(line[1:])
   elif line.startswith('-'):before.append(line[1:])
   elif line.startswith('+'):after.append(line[1:])
   else:break
   j+=1
  assert source[start:start+len(before)]==before
  out.extend(source[cursor:start]);out.extend(after);cursor=start+len(before);hunks.append({'old_start':start+1,'old_count':len(before),'new_count':len(after)})
 out.extend(source[cursor:]);ast.parse(''.join(out))
 pair=run/'children'/case['plan_hash']/'run';arms=[]
 with sqlite3.connect((pair/'ledger.sqlite').as_uri()+'?mode=ro',uri=True) as db:
  db.row_factory=sqlite3.Row;rows=[dict(x) for x in db.execute('SELECT * FROM calls ORDER BY id')]
 for arm in case['arm_order']:
  own=[x for x in rows if x['arm']==arm];latest=json.loads(own[-1]['request'])
  delivered={m['tool_call_id']:json.loads(m['content']) for m in latest['messages'] if m['role']=='tool'}
  actions=[];reads=[]
  for row in own:
   req=json.loads(row['request']);resp=json.loads(row['response'])
   for call in resp['choices'][0]['message']['tool_calls']:
    fn=call['function'];args=json.loads(fn['arguments']);obs=delivered.get(call['id']);action={'turn':row['turn'],'name':fn['name'],'arguments':args,'delivered_before_finish':obs is not None}
    if fn['name']=='finish':continue
    fields={'list_files':('offset',),'search_text':('query','offset'),'read_file':('path','offset')}
    normalized={k:args.get(k,0) if k=='offset' else args[k] for k in fields[fn['name']]}
    raw,offset=tools.render(fn['name'],normalized)
    if obs is not None:
     text=obs['text'];assert text==raw[offset:offset+len(text)]
     line_nums=[int(n) for n in re.findall(r'(?m)^(\d+):',text)]
     action.update(first_line=line_nums[0] if line_nums else None,last_line=line_nums[-1] if line_nums else None,
      delivered_chars=len(text),delivered_bytes=len(encoded(obs)),next_offset=obs['next_offset'],
      empty_result=not bool(text),gold_name_visible=qual.rsplit('.',1)[-1] in text,
      gold_definition_visible=('def '+qual.rsplit('.',1)[-1]+'(') in text,
      gold_file_path_visible=path in text)
     if fn['name']=='search_text':action['literal_hits']=text.splitlines()
     if fn['name']=='read_file':reads.append((normalized,text))
    actions.append(action)
  overlaps=[]
  for index,(args,text) in enumerate(reads):
   for bargs,btext in reads[index+1:]:
    if args['path']==bargs['path']:
     delta=bargs['offset']-args['offset'];n=max(0,min(len(text)-delta,len(btext))) if delta>=0 else 0
     overlaps.append({'path':args['path'],'first_offset':args['offset'],'second_offset':bargs['offset'],
       'identical_shifted_chars':n if delta>=0 and text[delta:delta+n]==btext[:n] else None,'second_page_chars':len(btext)})
  measured=next(x for x in measure['rows'] if x['case']==identifier and x['arm']==arm)
  assert score({'status':'completed','answer':measured['answer']},labels)==measured['localization_score']
  checks=[]
  for predicted in measured['answer']['entities']:
   f,_,q=predicted.partition(':');checks.append({'prediction':predicted,'ast_function_exists':q in functions(snapshot.files[f])})
  arms.append({'arm':arm,'actions':actions,'read_overlap':overlaps,'score_recomputed_exact':True,'entity_function_checks':checks,
    'source_bytes_delivered':sum(a.get('delivered_bytes',0) for a in actions),'calls':len(actions),
    'model_body_claim':measured['answer']['answer'],'retrieval_call_count':sum(a['name']=='locagent_retrieve' for a in actions)})
 result={'case':identifier,'base_commit':case['base_commit'],'gold':gold,'gold_ast_span':span,'old_patch_hunks_exact':hunks,
  'reference_patch':patch,'reference_patch_sha256':hashlib.sha256(patch.encode()).hexdigest(),
  'revised_source_ast_parsed_only':True,'mapping_verified':True,'arms':arms}
 results.append(result)
with (OUT/'trace-and-reference-analysis.json').open('x') as f:json.dump(results,f,ensure_ascii=False,indent=2)
print('Verified original labels, old patch hunks, AST mappings, stored tool evidence, and scores for four arms; no target code executed.')
