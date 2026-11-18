"""Verify and freeze exactly 50 prepared real issues. No network or execution authority."""
import collections,csv,hashlib,importlib.metadata,io,json,math,socket,sys
from pathlib import Path
ROOT=Path('/home/lenovo/projects/LocAgent-rag-preview');sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import prepare_expanded50 as p
from locagent_service.rag_offline import Version,chunk_snapshot
OUT=p.BASE/'frozen';WINDOWS=Path('/mnt/c/Users/Lenovo/Documents/Codex/2026-10-13/task')
def blocked(*a,**k):raise RuntimeError('Network blocked during freeze')
socket.socket.connect=blocked;socket.create_connection=blocked

def main(build):
 if OUT.exists():raise ValueError('Frozen output already exists')
 m=p.read(build)
 if len(m['queries'])!=50:raise ValueError('Exactly 50 verified issues required')
 previous=p.read(p.BASE/'build-1792136462962976345.json')
 assert len(previous['queries'])==46 and {q['id'] for q in previous['queries']}<={q['id'] for q in m['queries']}
 if any(a['status']=='pending' for a in m['audit']):raise ValueError('Earlier candidate unresolved; do not silently substitute later candidate')
 protected=p.read(p.BASE/'protected-before.json')
 assert all(p.sha(Path(path).read_bytes())==h for path,h in protected.items())
 old=p.read(ROOT/'outputs/bailian-retrieval-20261016/manifest.json')
 assert all(q['repo']!='pallets/itsdangerous' for q in m['queries'])
 assert len({q['source_url'] for q in m['queries']})==50 and all('/issues/' in q['source_url'] for q in m['queries'])
 assert max(m['by_repo'].values())<=10 and len(m['by_repo'])>=3
 docs={};snapshots={};archive_bindings={}
 for snap in m['snapshots']:
  repo,commit=snap['repo'],snap['commit'];key=repo.replace('/','__')+'-'+commit
  archive=p.ARCHIVES/(key+'.tar.gz');b=archive.read_bytes();assert p.sha(b)==snap['archive_sha256']
  files,inventory=p.archive_files(b,repo.split('/')[-1]+'-'+commit)
  assert inventory==snap['source_inventory']
  chunks=[c for c in chunk_snapshot(files,Version(repo,commit,old['model'],max_chars=12000)) if c.kind=='function']
  regenerated=[{'id':c.id,'entity':c.path+':'+c.entity,'path':c.path,'start':c.start,'end':c.end,'text':c.path+':'+c.entity+'\n'+c.text} for c in chunks]
  assert regenerated==p.read(p.CACHE/(key+'.json'))['documents']
  assert [d['id'] for d in regenerated]==snap['document_ids']
  snapshots[(repo,commit)]=(files,regenerated)
  archive_bindings[str(archive.relative_to(p.BASE))]=p.sha(b)
  for d in regenerated:
   h=p.sha(d['text'].encode());docs.setdefault(h,{'text':d['text'],'members':[]})['members'].append(d['id'])
 assert docs==m['unique_documents']
 targets=set();history_changed=0
 for q in m['queries']:
  folder=p.SOURCE/'records'/q['source_record'];issue=p.read(folder/'issue.json');pr=p.read(folder/'pr.json');events=p.read(folder/'events.json');patch=p.read(folder/'files.json')
  assert 'pull_request' not in issue and pr['merged_at'] and len(patch)==pr['changed_files'] and len(events)<100
  title,history=p.title_before_fix(issue,events,pr);assert title==q['text'] and history==q['history']
  history_changed+=title!=issue['title']
  files,candidates=snapshots[(q['repo'],q['commit'])];labels=p.label(patch,candidates,files)
  assert all(q[k]==v for k,v in labels.items())
  now={(q['repo'],e) for e in q['function_gold']};assert not p.target_overlap(now,targets);targets.update(now)
 requests=[]
 for role,rows in [('document',[{'id':k,'text':d['text']} for k,d in sorted(docs.items())]),('query',[{'id':q['id'],'text':q['text']} for q in m['queries']])]:
  for start in range(0,len(rows),16):
   batch=rows[start:start+16];params=old['document_parameters'] if role=='document' else old['parameters']
   assert all(0<len(x['text'].encode())<=16000 for x in batch)
   body={'model':old['model'],'input':{'texts':[x['text'] for x in batch]},'parameters':params}
   requests.append({'role':role,'ids':[x['id'] for x in batch],'body':body,'body_sha256':p.sha(p.canonical(body))})
 assert len(requests)==m['budget']['requests_16_per_batch']
 source_hashes={str(x.relative_to(p.SOURCE)):p.sha(x.read_bytes()) for x in sorted(p.SOURCE.rglob('*.json'))}
 engine_names=['scripts/prepare_expanded50.py','scripts/freeze_expanded50.py','scripts/prepare_expanded_subset.py','locagent_service/rag_offline.py','locagent_service/bailian_contract.py']
 manifest={**m,'status':'prepared_frozen_no_model_authorization','endpoint':old['endpoint'],'model':old['model'],'dimensions':old['dimensions'],'parameters':old['parameters'],'document_parameters':old['document_parameters'],'policy':p.read(ROOT/'docs/BAILIAN_EXPANDED50_POLICY.json'),'protocol_amendment':p.read(p.BASE/'protocol-amendment.json'),'official_price':p.read(p.BASE/'official-price.json'),'planned_requests':requests,'source_hashes':source_hashes,'archive_bindings':archive_bindings,'engine_hashes':{name:p.sha((ROOT/name).read_bytes()) for name in engine_names},'package_versions':{name:importlib.metadata.version(name) for name in ['bm25s','PyStemmer']},'cache_key_contract':['endpoint','model','dimensions','role','parameters_including_instruct','path:symbol-newline-code-v1','python-ast-lines-v2','max_chars12000','exact_utf8_text_sha256'],'old_vector_cache_reuse':0,'test_status':'offline tests recorded separately; repository tests and models never executed'}
 manifest['budget_evidence']=p.read(p.BASE/'budget-evidence.json')
 manifest['input_size_evidence']={'document_utf8_bytes':sum(len(d['text'].encode()) for d in docs.values()),'query_utf8_bytes':sum(len(q['text'].encode()) for q in m['queries']),'max_document_utf8_bytes':max(len(d['text'].encode()) for d in docs.values()),'query_instruct_utf8_bytes':len(old['parameters']['instruct'].encode()),'service_added_token_bound':None,'byte_based_hard_budget_proven':False}
 manifest['tests_log_sha256']=p.sha((p.BASE/'final-tests.log').read_bytes())
 OUT.mkdir();raw=p.canonical(manifest);(OUT/'manifest.json').write_bytes(raw);digest=p.sha(raw);(OUT/'manifest.sha256').write_text(digest+'\n')
 with (OUT/'queries.csv').open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=['id','repo','commit','text','source_url','fix_url','function_primary_eligible','function_gold','file_gold','symbol_hint','issue_created_at','fix_merged_at']);writer.writeheader()
  for q in m['queries']:writer.writerow({k:q[k] if k not in ('function_gold','file_gold','issue_created_at','fix_merged_at') else ('; '.join(q[k]) if k in ('function_gold','file_gold') else q['history'][k]) for k in writer.fieldnames})
 audit={'manifest_sha256':digest,'protected_files_unchanged':len(protected),'source_json_files_hashed':len(source_hashes),'fixed_commit_archives_reverified':len(snapshots),'queries':50,'repositories':m['by_repo'],'function_primary':m['function_primary_denominator'],'function_NA':50-m['function_primary_denominator'],'file_primary':50,'multi_function_gold':sum(len(q['function_gold'])>1 for q in m['queries']),'multi_file_gold':sum(len(q['file_gold'])>1 for q in m['queries']),'titles_restored_using_history':history_changed,'target_function_overlap':False,'symbol_hint_is_lexical_heuristic':True,'no_rankings':True,'no_model_calls':True,'no_database_started':True,'budget':m['budget'],'frozen_source_build_sha256':p.sha(build.read_bytes())}
 (OUT/'audit.json').write_bytes(p.canonical(audit))
 (OUT/'test-evidence.log').write_bytes((p.BASE/'final-tests.log').read_bytes())
 for name in ['manifest.json','queries.csv','audit.json']:(WINDOWS/('bailian-expanded50-'+name)).write_bytes((OUT/name).read_bytes())
 print(json.dumps(audit,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]))
