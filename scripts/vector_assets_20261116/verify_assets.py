"""Read-only local provenance checks; never imports any transport/runner entry point."""
import argparse,ast,collections,gzip,hashlib,importlib.util,io,json,math,sqlite3,sys,tarfile
from pathlib import Path,PurePosixPath
from tempfile import TemporaryDirectory
BASE=Path(__file__).resolve().parent
ROOT=BASE/'restored'
PROJECT=Path('/Users/xiaomu/Projects/LocAgent-OpenHands')
LEGACY=PROJECT/'legacy/locagent-demo'
WORKSPACE=PROJECT/'workspace'
sys.path[:0]=[str(WORKSPACE),str(LEGACY)]
from readonly_agent.offline import no_network

def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def canonical(obj):return json.dumps(obj,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

def checked_relative(text):
 p=PurePosixPath(text)
 assert not p.is_absolute() and str(p)==text and '..' not in p.parts and '\\' not in text
 return text

def source_archive(path,snapshot,legacy):
 raw=path.read_bytes();assert sha(raw)==snapshot['archive_sha256']
 with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:expanded=f.read(32*1024**2+1)
 assert len(expanded)<=32*1024**2
 files={};inventory=[];seen=set();prefix=snapshot['repo'].split('/')[-1]+'-'+snapshot['commit']
 with tarfile.open(fileobj=io.BytesIO(expanded),mode='r:') as t:
  for i,item in enumerate(t):
   name=item.name.rstrip('/') if item.isdir() else item.name
   checked_relative(name);p=PurePosixPath(name)
   assert i<3000 and name not in seen and len(name)<=512 and len(p.parts)<=30 and p.parts[0]==prefix
   seen.add(name);assert item.isfile() or item.isdir()
   if item.isdir():continue
   assert item.size<=1024**2
   data=t.extractfile(item).read();assert len(data)==item.size
   rel=PurePosixPath(*p.parts[1:]).as_posix();accepted=legacy.allowed(rel)
   inventory.append({'path':rel,'bytes':len(data),'sha256':sha(data),'included':accepted,'reason':None if accepted else 'existing_allowed_policy_or_non_python'})
   if accepted:assert b'\0' not in data;files[rel]=data
 assert inventory==snapshot['source_inventory']
 return files

def expanded():
 from locagent_service import rag_offline as legacy
 from locagent_service.bailian_response import validate_response
 review=load('asset_historical_review',LEGACY/'scripts/independent_expanded50_review.py')
 base=ROOT/'outputs/bailian-expanded50-20261016'
 review.BASE=base;review.RUN=ROOT/'outputs/bailian-expanded-budget-runs/bailian-expanded50-78e24794-cap2-20261016-r01';review.RESULT=ROOT/'outputs/bailian-expanded50-resumed-evaluation-20261016-r01'
 raw=(base/'frozen/manifest.json').read_bytes();assert sha(raw)==review.PIN
 m=json.loads(raw)
 assert (m['model'],m['dimensions'])==('qwen3.7-text-embedding-flash',1024)
 assert m['document_parameters']=={'dimension':1024,'text_type':'document','output_type':'dense'}
 assert m['parameters']==dict(m['document_parameters'],text_type='query',instruct='Given a code localization question, retrieve Python code that implements the described behavior.')
 for name,digest in m['archive_bindings'].items():assert sha((base/checked_relative(name)).read_bytes())==digest
 for name,digest in m['source_hashes'].items():assert sha((base/'source'/checked_relative(name)).read_bytes())==digest
 engines={name:sha((ROOT/checked_relative(name)).read_bytes())==digest for name,digest in m['engine_hashes'].items()}
 assert all(engines.values()),engines
 for name in read(review.RESULT/'ledger-audit.json')['ledger_hashes']:checked_relative(name)
 raw_vectors,finances=review.audit_attempts(m)
 print('expanded: 619 attempts and event chains verified',flush=True)
 vectors={};inputs=[];queries={q['id']:q['text'] for q in m['queries']}
 assert len(m['planned_requests'])==618
 for batch,item in enumerate(m['planned_requests']):
  role=item['role'];assert role in ('document','query')
  texts=[m['unique_documents'][i]['text'] if role=='document' else queries[i] for i in item['ids']]
  body={'model':m['model'],'input':{'texts':texts},'parameters':m['document_parameters'] if role=='document' else m['parameters']}
  assert item['body']==body and sha(canonical(body))==item['body_sha256']
  filename=f'body-{batch:06d}.bin' if batch<490 else f'continuation-body-{batch:06d}.bin'
  raw=(review.RUN/filename).read_bytes();checked,_,_=validate_response(raw,len(texts),200)
  assert tuple(raw_vectors[batch])==checked
  for idx,(ident,text,vector) in enumerate(zip(item['ids'],texts,checked)):
   key=(role,ident);assert key not in vectors;vectors[key]=vector
   inputs.append({'role':role,'id':ident,'text_sha256':sha(text.encode()),'response':str((review.RUN/filename).relative_to(ROOT)),'response_sha256':sha(raw),'response_index':idx})
 assert collections.Counter(role for role,_ in vectors)=={'document':9814,'query':50}
 members={}
 for key,doc in m['unique_documents'].items():
  assert sha(doc['text'].encode())==key
  for member in doc['members']:
   assert member not in members or members[member]==key;members[member]=key
 snapshots={};duplicates=[]
 for s in m['snapshots']:
  key=s['repo'].replace('/','__')+'-'+s['commit']
  files=source_archive(base/'archives'/(key+'.tar.gz'),s,legacy)
  chunks=[c for c in legacy.chunk_snapshot(files,legacy.Version(s['repo'],s['commit'],m['model'],max_chars=12000)) if c.kind=='function']
  docs=[{'id':c.id,'entity':c.path+':'+c.entity,'path':c.path,'start':c.start,'end':c.end,'text':c.path+':'+c.entity+'\n'+c.text} for c in chunks]
  cache=read(base/'snapshots'/(key+'.json'))
  assert docs==cache['documents'] and [d['id'] for d in docs]==s['document_ids']
  for d in docs:assert d['text']==m['unique_documents'][members[d['id']]]['text']
  snapshots[(s['repo'],s['commit'])]=s
  definitions=collections.defaultdict(set)
  for c in chunks:definitions[c.path+':'+c.entity].add((c.start,c.end)) if c.part==0 else None
  dup=[k for k,v in definitions.items() if len(v)>1]
  if dup:duplicates.append({'repo':s['repo'],'commit':s['commit'],'duplicate_entity_count':len(dup)})
 print('expanded: 49 source archives and frozen function blocks verified',flush=True)
 clean=[{k:q[k] for k in ('id','text','repo','commit')} for q in m['queries']]
 functions,counts=review.rank_without_gold(clean,snapshots,m['unique_documents'],members,vectors)
 saved=read(review.RESULT/'results.json')
 files={arm:{qid:list(dict.fromkeys(e.split(':',1)[0] for e in ranking)) for qid,ranking in rows.items()} for arm,rows in functions.items()}
 assert functions==saved['function_rankings'] and files==saved['file_rankings'] and counts==saved['candidate_counts']
 result={'status':'verified','manifest_sha256':sha(canonical(m)),'document_vectors':9814,'query_vectors':50,'dimensions':1024,'snapshots_rebuilt':len(snapshots),'source_json_hashes_verified':len(m['source_hashes']),'source_block_memberships':sum(len(s['document_ids']) for s in snapshots.values()),'function_rankings_reproduced':150,'file_rankings_reproduced':150,'engine_hashes_verified':engines,'finances_historical_only':finances,'snapshots_with_duplicate_definitions':duplicates}
 (BASE/'expanded-verification.json').write_text(json.dumps(result,indent=2)+'\n')
 (BASE/'expanded-verified-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 print('expanded: all 150 function and 150 file rankings reproduced',flush=True)
 return m,inputs

def small():
 from locagent_service import rag_offline as legacy
 from locagent_service.bailian_response import validate_response
 folder=ROOT/'outputs/bailian-retrieval-20261016'
 raw=(folder/'manifest.json').read_bytes();assert sha(raw)=='a6a0abb4f12cc6d45fce36a89a384ccd0d92175b94c0246abc9f9b3e14ebf39f'
 m=json.loads(raw);saved=read(folder/'results.json')
 source={p:s.encode() for p,s in m['source_files'].items()}
 assert m['git_blobs']=={p:hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest() for p,b in source.items()}
 chunks=[c for c in legacy.chunk_snapshot(source,legacy.Version(**m['chunker'])) if c.kind=='function']
 docs=[{'id':c.id,'entity':c.path+':'+c.entity,'path':c.path,'text':c.path+':'+c.entity+'\n'+c.text} for c in chunks]
 assert docs==m['documents']
 expected={(role,d['id']):d['text'] for role,key in [('document','documents'),('query','questions')] for d in m[key]}
 vectors={};inputs=[]
 for item in saved['source_inventory']:
  name=Path(item['source_folder']).name;assert name in ('bailian-retrieval-20261016','bailian-mapping-controls-20261015')
  origin=ROOT/'outputs'/name;i=item['request_index'];sm=read(origin/'manifest.json')
  for key in ('endpoint','model','dimensions','document_parameters'):assert sm[key]==m[key]
  role=item['role'];texts=[expected[(role,ident)] for ident in item['ids']]
  body={'model':m['model'],'input':{'texts':texts},'parameters':m['document_parameters'] if role=='document' else m['parameters']}
  binding=read(origin/f'response-{i:03d}.binding.json');assert binding==item['binding']
  raw=(origin/f'response-{i:03d}.body.bin').read_bytes()
  assert binding['manifest_sha256']==sha(canonical(sm)) and binding['request_sha256']==sha(canonical(body)) and binding['response_sha256']==sha(raw) and binding['http_status']==200
  with sqlite3.connect((origin/'ledger.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True) as db:
   row=db.execute('SELECT state,n,request_hash,response_hash,vectors FROM calls WHERE id=?',(i,)).fetchone()
  assert row[:4]==('settled',len(texts),binding['request_sha256'],sha(raw))
  values,_,_=validate_response(raw,len(texts),200);assert json.loads(row[4])==[list(v) for v in values]
  for index,(ident,text,v) in enumerate(zip(item['ids'],texts,values)):
   key=(role,ident);assert key not in vectors;vectors[key]=v
   inputs.append({'role':role,'id':ident,'text_sha256':sha(text.encode()),'response':str((origin/f'response-{i:03d}.body.bin').relative_to(ROOT)),'response_sha256':sha(raw),'response_index':index})
 assert set(vectors)==set(expected)
 result={'status':'verified','document_vectors':32,'query_vectors':10,'source_responses_verified':5,'sqlite_sources_read_only':True,'source_files_rebuilt':4,'manifest_sha256':sha(canonical(m)),'dimensions':1024}
 (BASE/'small-verification.json').write_text(json.dumps(result,indent=2)+'\n')
 (BASE/'small-verified-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 print('small: 32 document / 10 query vectors verified from 5 responses',flush=True)
 return m,inputs

def main():
 global BASE,ROOT
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--evidence-root',required=True)
 parser.add_argument('--output',required=True)
 args=parser.parse_args();ROOT=Path(args.evidence_root).resolve(strict=True)
 BASE=Path(args.output).resolve();BASE.mkdir(parents=True,exist_ok=False)
 with TemporaryDirectory(prefix='vector-verification-') as td:
  with no_network(Path(td)/'profile') as attempts:
   expanded_m,expanded_inputs=expanded();small_m,small_inputs=small()
   (BASE/'verified-text-hashes.json').write_text(json.dumps({'documents':sorted({i['text_sha256'] for i in expanded_inputs+small_inputs if i['role']=='document'}),'queries':sorted({i['text_sha256'] for i in expanded_inputs+small_inputs if i['role']=='query'})},indent=2)+'\n')
   result={'status':'verified','expanded':read(BASE/'expanded-verification.json'),'small':read(BASE/'small-verification.json'),'network_attempts':len(attempts),'new_embedding_requests':0,'new_llm_requests':0,'new_cost':0,'live_sdk_cache_imported':False}
  (BASE/'verification-summary.json').write_text(json.dumps(result,indent=2)+'\n')
 print('offline provenance verification complete',flush=True)

if __name__=='__main__':main()
