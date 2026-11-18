"""Offline comparison of recorded choices; no transport, model, or key loading."""
import hashlib,json,re,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.authority import save_new
from readonly_agent.core import digest
from experiments.retrieval_choice.audit import audit
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/retrieval-choice-state-v1'
OLD='eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83'
NEW='df07e7a25bad76c053d3f372b8b0b9fd0a883b03577aef53676781553f5c3277'
POS=[('webhook',ROOT/'authority/5cb8a59ad54ba444acf50b9015236b396645254094b493e3a3cbee60decdf8b2/run/ledger.sqlite'),
 ('document_access',ROOT/'authority-batches/34246247d2f59a8626aae8338b92f1183904874835f9fcc63b41f3775848f56e/run/children/ccd494b3be49a0ed8cfcb11387451387c2103fd5bc6ccbdb5b08e7035705c9a3/run/ledger.sqlite')]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def calls(p):
 with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as db:
  db.row_factory=sqlite3.Row;rows=[dict(r) for r in db.execute("SELECT * FROM calls WHERE arm='retrieval' ORDER BY id")]
 for r in rows:
  assert hashlib.sha256(r['request']).hexdigest()==r['request_hash']
  assert hashlib.sha256(r['response']).hexdigest()==r['response_hash']
  r['q']=json.loads(r['request']);r['r']=json.loads(r['response'])
 return rows

def main():
 OUT.mkdir(parents=True,exist_ok=False)
 protected={}
 for ns in ['authority','authority-batches','authority-locbench','authority-sqlglot-validation','locbench_openhands','locbench_live','sqlglot_read_validation','readonly_agent','experiments']:
  for p in (ROOT/ns).rglob('*'):
   if p.is_file() and '__pycache__' not in p.parts:protected[str(p.relative_to(ROOT))]=sha(p)
 save_new(OUT/'before.json',{'files':protected})
 groups=[];contexts={}
 for ns,h,stage in [('authority-locbench',OLD,'before_read_fix'),('authority-sqlglot-validation',NEW,'after_read_fix')]:
  grant=read(ROOT/ns/h/'grant.json')
  for c in grant['plan']['base_manifest']['cases']:
   p=ROOT/ns/h/'run/children'/c['plan_hash']/'run/ledger.sqlite';rs=calls(p)
   label=read(ROOT/'locbench_openhands/v5/scoring-only'/f"{c['id']}.json")
   gold=label['gold_entities'][0];gp,_,qual=gold.partition(':');simple=qual.rsplit('.',1)[-1]
   span=label['mapping']['gold_mappings'][0]['strict_ast'];lo,hi=span['start_line'],span['end_line']
   cfg=read(ROOT/c['case_file']);src=(ROOT/c['case_file']).parent/cfg['root']/gp;source=src.read_text().splitlines()
   states=[]
   for r in rs:
    q=r['q'];texts=[]
    for m in q['messages']:
     if m['role']=='tool':
      packet=json.loads(m['content']);texts.append(packet.get('text',''))
    pattern=re.compile(r'(?<!\w)'+re.escape(simple)+r'(?!\w)')
    known=any(pattern.search(t) for t in texts)
    # Current numbered read output; old wrong-region outputs never cover this span.
    covered={n for n in range(lo,hi+1) if any(re.search(r'^'+str(n)+': '+re.escape(source[n-1])+r'$',t,re.M) for t in texts)}
    names=[t['function']['name'] for t in q['tools']]
    offered=next((t['function'] for t in q['tools'] if t['function']['name']=='locagent_retrieve'),None)
    notice=next(m['content'] for m in q['messages'] if m['role']=='user' and m['content'].startswith('CONTROLLER BUDGET'))
    budget=re.search(r'available investigation calls: (\d+); available source-result bytes: (\d+)',notice)
    selected=[{'name':t['function']['name'],'arguments':json.loads(t['function']['arguments'])} for t in r['r']['choices'][0]['message'].get('tool_calls',[])]
    state={'turn':r['turn'],'request_sha256':r['request_hash'],'tool_order':names,'tool_choice':q['tool_choice'],
     'retrieval_offered':offered is not None,'description_sha256':digest(offered['description']) if offered else None,
     'retrieval_schema_sha256':digest(offered['parameters']) if offered else None,'remaining_calls':int(budget[1]),'remaining_source_bytes':int(budget[2]),
     'known_target_symbol':known,'complete_target_body_already_delivered':len(covered)==hi-lo+1,'target_lines_received':sorted(covered),
     'known_symbol_but_missing_body_and_open_tools':known and len(covered)<hi-lo+1 and offered is not None,
     'selected_tools':[t['name'] for t in selected],
     'selected_arguments_without_finish':[t for t in selected if t['name']!='finish']}
    states.append(state)
    contexts[(stage,c['id'],r['turn'])]=q
   groups.append({'stage':stage,'case':c['id'],'ledger':str(p.relative_to(ROOT)),'gold_only_used_for_audit':gold,'states':states})
 current=contexts[('after_read_fix','tobymao__sqlglot-3417',1)]
 reference=next(t['function'] for t in current['tools'] if t['function']['name']=='locagent_retrieve')
 positives=[]
 for name,p in POS:
  rs=calls(p);first=rs[0]['q'];ret=next(t['function'] for t in first['tools'] if t['function']['name']=='locagent_retrieve')
  a=audit(p,p.parent/'retrieval','retrieval');assert not a['simulation'] and a['all_invocations_verified'] and a['live_auto_selection_observed']
  assert ret==reference
  positives.append({'sample':name,'ledger':str(p.relative_to(ROOT)), 'same_retrieval_tool_definition_as_current':ret==reference,
   'same_tool_names_and_order':[t['function']['name'] for t in first['tools']]==[t['function']['name'] for t in current['tools']],
   'model':first['model'],'temperature':first['temperature'],'thinking':first['thinking'],'tool_choice':first['tool_choice'],
   'system_message_equal_to_current':first['messages'][0]==current['messages'][0],
   'issue':first['messages'][1]['content'],'audit':a})
 assert len(groups)==3
 oldsql=next(g for g in groups if g['stage']=='before_read_fix' and 'sqlglot' in g['case'])
 newsql=next(g for g in groups if g['stage']=='after_read_fix')
 assert [s['turn'] for s in oldsql['states'] if s['known_symbol_but_missing_body_and_open_tools']]==[2,3]
 assert not any(s['known_symbol_but_missing_body_and_open_tools'] for s in newsql['states'])
 # Draft diagnostic pair: historical search-only checkpoint, common repaired tools/system.
 # Never a recorded model trajectory or a runnable admission. Only one description differs.
 checkpoint=json.loads(json.dumps(contexts[('before_read_fix','tobymao__sqlglot-3417',2)]))
 checkpoint['tools']=current['tools'];checkpoint['messages'][0]=current['messages'][0]
 control=json.loads(json.dumps(checkpoint));candidate=json.loads(json.dumps(control))
 newdesc=reference['description'].replace('Use search_text for literal text inside source, and read_file for a known file.',
 'Use search_text for literal text inside source, and read_file for a known file or line range. '
 'If you know a symbol name but have not read its complete body, this tool can return that entity source without choosing line bounds.')
 assert newdesc!=reference['description']
 next(t['function'] for t in candidate['tools'] if t['function']['name']=='locagent_retrieve')['description']=newdesc
 differences=[]
 def diff(a,b,path=''):
  if type(a)!=type(b):differences.append(path);return
  if isinstance(a,dict):
   assert a.keys()==b.keys()
   for k in a:diff(a[k],b[k],path+'/'+k)
  elif isinstance(a,list):
   assert len(a)==len(b)
   for i,(x,y) in enumerate(zip(a,b)):diff(x,y,path+'/'+str(i))
  elif a!=b:differences.append(path)
 diff(control,candidate);assert differences==['/tools/3/function/description']
 save_new(OUT/'diagnostic-control-request.json',control);save_new(OUT/'diagnostic-candidate-request.json',candidate)
 save_new(OUT/'draft-experiment.json',{'status':'offline_draft_not_authorized','context':'constructed replay checkpoint from old SQLGlot turn 2, after search-only first turn; repaired base tools and system held equal in both variants',
 'not_natural_current_run':True,'different_json_paths':differences,'hypothesis':'Making known-symbol body retrieval explicit changes autonomous tool choice at an unmet-evidence checkpoint.',
 'primary_outcome':'Whether the first returned model response selects locagent_retrieve; preserve every outcome and error, no forced selection or retry.',
 'scope_limit':'Request-only replay would test choice, not tool execution, downstream answer quality, or retrieval benefit.',
 'secondary_controls':'Natural current turn 3 already has target body; keep as separate negative-need state if a later study is approved.',
 'confounds':'Same model alias is not an immutable model version; repeated samples, order control, prospective pricing and user approval required before execution.',
 'control_sha256':sha(OUT/'diagnostic-control-request.json'),'candidate_sha256':sha(OUT/'diagnostic-candidate-request.json')})
 for p,h in protected.items():assert sha(ROOT/p)==h
 report={'groups':groups,'positive_controls':positives,'retrieval_description':reference['description'],
 'retrieval_opportunities_in_three_real_arms':9,'selected_in_these_arms':0,'positive_cases_with_verified_auto_selection':2,
 'old_sql_known_symbol_missing_body_opportunities':2,'new_sql_known_symbol_missing_body_opportunities':0,
 'paid_requests':0,'credentials_read':False,'target_code_executed':False,'production_changed':False,'historical_files_unchanged':len(protected),
 'causal_effect_estimated':False,'draft_pair_diff':differences}
 save_new(OUT/'results.json',report)
 print(json.dumps({k:v for k,v in report.items() if k not in ('groups','positive_controls','retrieval_description')},ensure_ascii=False))
 for g in groups:
  print(g['stage'],g['case'],[(s['turn'],s['known_target_symbol'],s['complete_target_body_already_delivered'],s['selected_tools']) for s in g['states']])
if __name__=='__main__':main()
