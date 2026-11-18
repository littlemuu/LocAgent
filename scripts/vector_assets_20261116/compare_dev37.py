"""Source-only input coverage probe; no gold, no vectors generated, no corpus policy edits."""
import argparse,ast,collections,hashlib,json,sys,warnings
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parent
WS=Path('/Users/xiaomu/Projects/LocAgent-OpenHands/workspace');sys.path.insert(0,str(WS))
from readonly_agent.core import Snapshot
from readonly_agent.offline import no_network
from experiments.sdk_hybrid_v8.corpus import Corpus
from experiments.retrieval_evidence_v6.retriever import ast_entities
from experiments.cohort_preflight.body import lines

def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def bound(p,expected):
 raw=Path(p).read_bytes();assert sha(raw)==expected,str(p);return json.loads(raw)

def diagnostic_chunks(snapshot):
 # Same physical function input text as v8; deliberately does NOT publish a
 # Corpus or bypass its duplicate-ID guard. Used only to count/cache-match text.
 docs=[];names=collections.Counter();duplicate_examples=[]
 for path,source in snapshot.files.items():
  if not path.endswith('.py'):continue
  _,entries=ast_entities(source);physical=lines(source)
  for (name,start,end),node in entries.items():
   entity=path+':'+name;names[entity]+=1
   if isinstance(node,ast.ClassDef):continue
   first=min([start]+[d.lineno for d in node.decorator_list]);buffer=''
   def emit(text):
    if text.strip():
     raw=(entity+'\n'+text).encode();docs.append({'text_sha256':sha(raw),'bytes':len(raw),'entity':entity})
   for n in range(first,end+1):
    line=physical[n-1]
    if buffer and len(buffer)+len(line)>12000:emit(buffer);buffer=''
    while len(line)>12000:emit(line[:12000]);line=line[12000:]
    buffer+=line
   emit(buffer)
 return docs,[k for k,v in names.items() if v>1]

def main():
 global ROOT
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--verified-hashes',required=True)
 parser.add_argument('--output',required=True)
 args=parser.parse_args();ROOT=Path(args.output).resolve();ROOT.mkdir(parents=True,exist_ok=False)
 registry=read(WS/'verification/dev37-preparation-v4/runtime-cases.json');assert len(registry['cases'])==37
 known=read(args.verified_hashes);doc_hashes=set(known['documents']);query_hashes=set(known['queries'])
 rows=[];unique={};all_issues=set();matching=set();warnings.filterwarnings('ignore',category=SyntaxWarning)
 with TemporaryDirectory() as td:
  with no_network(Path(td)/'profile') as attempts:
   for row in registry['cases']:
    entry=bound(row['entry'],row['entry_sha256']);plan=bound(entry['source_plan'],entry['source_plan_sha256'])
    snapshot=Snapshot(plan['source_root'],list(plan['sources']),hidden_python_paths=plan['hidden_python_paths'])
    assert dict(snapshot.hashes)==plan['sources'] and snapshot.identity==row['snapshot']==entry['source_snapshot']
    docs,duplicates=diagnostic_chunks(snapshot)
    try:
     corpus=Corpus(snapshot)
     assert [sha(d.text.encode()) for d in corpus.documents]==[d['text_sha256'] for d in docs]
     status='ready';error=None
    except ValueError as exc:status='blocked';error=str(exc)
    matches=[d for d in docs if d['text_sha256'] in doc_hashes]
    issue_hash=sha(entry['issue'].encode());all_issues.add(issue_hash)
    for d in docs:unique[d['text_sha256']]=d['bytes']
    matching.update(d['text_sha256'] for d in matches)
    rows.append({'id':row['id'],'repo':row['repo'],'commit':plan['commit'],'snapshot':snapshot.identity,'source_files':len(snapshot.files),'function_chunks_diagnostic':len(docs),'unique_inputs':len({d['text_sha256'] for d in docs}),'exact_document_input_matches':len(matches),'matches':matches,'exact_full_issue_query_cached':issue_hash in query_hashes,'v8_current_corpus_status':status,'v8_current_corpus_error':error,'duplicate_entity_count':len(duplicates),'duplicate_examples':duplicates[:5],'full_issue_query_characters':len(entry['issue']),'full_issue_query_bytes':len(entry['issue'].encode())})
    print(row['id'],status,'chunks',len(docs),'matches',len(matches),flush=True)
   summary={'status':'coverage_checked','cases':len(rows),'repositories':len({r['repo'] for r in rows}),'snapshots':len({r['snapshot'] for r in rows}),'source_only':True,'gold_used':False,'input_definition':'diagnostic v8 physical function chunks, max_chars12000, full entity prefix; NOT a published corpus or encoding plan','total_chunk_memberships':sum(r['function_chunks_diagnostic'] for r in rows),'unique_document_inputs_diagnostic':len(unique),'exact_old_document_inputs':len(matching),'new_document_inputs_diagnostic':len(unique)-len(matching),'unique_input_bytes':sum(unique.values()),'max_input_bytes':max(unique.values()),'inputs_over_historical_16000_byte_cap':sum(v>16000 for v in unique.values()),'unique_full_issue_queries':len(all_issues),'exact_old_full_issue_queries':len(all_issues&query_hashes),'current_v8_corpus_ready_cases':sum(r['v8_current_corpus_status']=='ready' for r in rows),'current_v8_corpus_blocked_cases':sum(r['v8_current_corpus_status']=='blocked' for r in rows),'network_attempts':len(attempts),'new_paid_calls':0,'rows':rows}
  summary['full_issue_queries_over_v8_256_characters']=sum(r['full_issue_query_characters']>256 for r in rows)
  summary['full_issue_queries_over_historical_16000_bytes']=sum(r['full_issue_query_bytes']>16000 for r in rows)
  summary['max_full_issue_bytes']=max(r['full_issue_query_bytes'] for r in rows)
  (ROOT/'dev37-coverage.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k!='rows'}),flush=True)
if __name__=='__main__':main()
