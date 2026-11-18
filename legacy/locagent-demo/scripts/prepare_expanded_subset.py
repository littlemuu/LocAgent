"""Offline evidence compiler. No network, credentials, model or DB access."""
import ast
import collections
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from decimal import Decimal

ROOT = Path('/home/lenovo/projects/LocAgent-rag-preview')
sys.path.insert(0, str(ROOT))
from locagent_service.rag_offline import Version, allowed, chunk_snapshot

def sha(b): return hashlib.sha256(b).hexdigest()
def encode(v): return json.dumps(v, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()
def read(p): return json.loads(p.read_bytes())
def blob_sha(b): return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()

def changed_old_lines(patch):
    """Return removed lines and insertion anchors; never label whole hunk context."""
    points=[]; old=None; insertion=False
    for line in patch.splitlines():
        if line.startswith('@@'):
            m=re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@',line)
            if not m: raise ValueError('bad hunk')
            old=int(m[1]);insertion=False
        elif old is not None:
            if line.startswith('-'):points.append((old,'removed'));old+=1;insertion=False
            elif line.startswith('+'):
                if not insertion:points.append((max(1,old-1),'insertion_after'))
                insertion=True
            elif line.startswith(' '):old+=1;insertion=False
            elif line.startswith('\\'):pass
            else:raise ValueError('unsupported patch')
    return sorted(set(points))

def score(gold, ranking, k):
    if not gold:return None
    hits=len(set(gold)&set(ranking[:k]))
    return {'hit':int(hits>0),'recall':hits/len(set(gold))}

def prepare(source, policy, destination):
    if destination.exists():raise ValueError('Output must not exist')
    snapshots=[];queries=[];all_docs={};audit=[];seen_targets=set()
    for spec in policy['queries']:
        n=spec['pr'];pr=read(source/f'blinker-pr-{n}.json')
        commit=read(source/f'blinker-commit-{n}.json');tree=read(source/f'blinker-root-tree-{n}.json')
        assert pr['merged_at'] and re.fullmatch('[a-f0-9]{40}',pr['base']['sha'])
        assert commit['sha']==pr['base']['sha'] and tree['sha']==commit['tree']['sha'] and tree['truncated'] is False
        assert len(tree['tree'])<=3000
        files={};excluded=[];inventory=[]
        for entry in tree['tree']:
            p=entry['path'];assert not p.startswith('/') and '..' not in Path(p).parts and '\\' not in p
            assert entry['mode'] in ('040000','100644','100755') and entry['type'] in ('tree','blob')
            assert not p.endswith('.gitmodules')
            if entry['type']=='tree':continue
            if not allowed(p):excluded.append({'path':p,'reason':'existing_allowed_policy_or_non_python'});continue
            b=(source/'blobs'/f"{entry['sha']}.json").read_bytes()
            assert len(b)==entry['size'] and blob_sha(b)==entry['sha']
            assert b'\0' not in b and not b.startswith(b'version https://git-lfs.github.com/spec/v1')
            files[p]=b;inventory.append({'path':p,'git_blob':entry['sha'],'sha256':sha(b),'bytes':len(b)})
        v=Version('pallets-eco/blinker',commit['sha'],'qwen3.7-text-embedding-flash',max_chars=12000)
        chunks=[c for c in chunk_snapshot(files,v) if c.kind=='function']
        docs=[{'id':c.id,'entity':c.path+':'+c.entity,'path':c.path,'text':c.path+':'+c.entity+'\n'+c.text,'start':c.start,'end':c.end} for c in chunks]
        assert all(len(d['text'].encode())<=16000 for d in docs)
        for d in docs:all_docs[d['id']]=d
        origin=read(source/'blinker-issue-173.json') if spec['kind']=='issue' else pr
        query={'id':spec['id'],'text':origin['title'],'repo':v.repo,'commit':v.commit,'source_url':origin['html_url'],'source_type':spec['kind'],'fix_url':pr['html_url'],'file_gold':[],'function_gold':[],'unmapped_changes':[],'test_evidence':[]}
        patchfiles=read(source/f'blinker-pr-{n}-files.json')
        assert len(patchfiles)==pr['changed_files']
        for f in patchfiles:
            path=f['filename']
            if not path.endswith('.py'):continue
            if path.startswith(('tests/','test/')):
                query['test_evidence'].append(path);continue
            query['file_gold'].append(path)
            if path not in files or 'patch' not in f:query['unmapped_changes'].append({'path':path,'reason':'missing_base_or_patch'});continue
            for line,kind in changed_old_lines(f['patch']):
                candidates=[c for c in chunks if c.path==path and c.start<=line<=c.end]
                if candidates:
                    c=min(candidates,key=lambda c:(c.end-c.start,-c.entity.count('.'),c.entity))
                    query['function_gold'].append(path+':'+c.entity)
                else:query['unmapped_changes'].append({'path':path,'line':line,'kind':kind,'reason':'module_or_class_change'})
        query['function_gold']=sorted(set(query['function_gold']));query['file_gold']=sorted(set(query['file_gold']))
        query['function_primary_eligible']=bool(query['function_gold']) and not query['unmapped_changes']
        query['gold_type']='static_patch_overlap_proxy_not_execution_verified_truth'
        query['symbol_hint']=any(word.lower() in query['text'].lower() for word in ['WeakNamespace','make_id','cleanup','_make_cleanup_receiver'])
        query['targets_overlap_prior_subset']=sorted(seen_targets&set(query['function_gold']))
        assert not query['targets_overlap_prior_subset']
        seen_targets.update(query['function_gold'])
        assert set(query['function_gold'])<={d['entity'] for d in docs}
        assert set(query['file_gold'])<={d['path'] for d in docs}
        queries.append(query)
        snapshots.append({'repo':v.repo,'commit':v.commit,'tree_sha':tree['sha'],'files':inventory,'excluded':excluded,'document_ids':[d['id'] for d in docs],'chunks':len(docs),'entities':len({d['entity'] for d in docs}),'source_bytes':sum(map(len,files.values()))})
    # Explicit dedup before any ranking. A commit remains a separate candidate membership.
    unique={}
    for d in all_docs.values():unique.setdefault(sha(d['text'].encode()),{'text':d['text'],'member_ids':[]})['member_ids'].append(d['id'])
    assert len({q['text'].casefold().strip() for q in queries})==len(queries)
    assert all(q['repo']!='pallets/itsdangerous' for q in queries)
    requests=[]
    for role,rows in [('document',[{'id':k,'text':v['text']} for k,v in sorted(unique.items())]),('query',[{'id':q['id'],'text':q['text']} for q in queries])]:
        for offset in range(0,len(rows),16):
            batch=rows[offset:offset+16];parameters={'dimension':1024,'text_type':role,'output_type':'dense'}
            if role=='query':parameters['instruct']='Given a code localization question, retrieve Python code that implements the described behavior.'
            body={'model':'qwen3.7-text-embedding-flash','input':{'texts':[r['text'] for r in batch]},'parameters':parameters}
            requests.append({'role':role,'ids':[r['id'] for r in batch],'body':body,'body_sha256':sha(encode(body))})
    total=len(unique)+len(queries);size=sum(len(v['text'].encode()) for v in unique.values())+sum(len(q['text'].encode()) for q in queries)
    estimate=Decimal(size)/4*Decimal('.125')/1000000
    reserve=Decimal(total)*Decimal('.016384')
    manifest={'status':'offline_subset_frozen_no_authority_to_call','policy':policy,'policy_sha256':sha(encode(policy)),'queries':queries,'snapshots':snapshots,'documents':list(all_docs.values()),'deduplicated_document_inputs':unique,'planned_requests':requests,'source_evidence_hashes':{str(p.relative_to(source)):sha(p.read_bytes()) for p in sorted(source.rglob('*')) if p.is_file()},'engine_hashes':{p:sha((ROOT/p).read_bytes()) for p in ['locagent_service/rag_offline.py','locagent_service/bailian_contract.py','scripts/prepare_expanded_subset.py']},'budget':{'document_memberships':len(all_docs),'unique_document_inputs':len(unique),'queries':len(queries),'inputs':total,'input_utf8_bytes':size,'requests':len(requests),'rate_cny_per_million_assumed_not_revalidated':'.125','rough_tokens_bytes_div_4':size/4,'rough_cost_cny_not_upper_bound':str(estimate),'new_reserved_cny_131072_tokens_per_input':str(reserve),'old_held_cny':'1.277952','old_unknown_cny':'.557056','proposed_total_held_cny':str(reserve+Decimal('1.277952')),'actual_bill':'unknown_no_calls','fifty_query_budget':None},'denominators':{'file':len(queries),'function_primary':sum(q['function_primary_eligible'] for q in queries),'function_NA':sum(not q['function_primary_eligible'] for q in queries)}}
    destination.mkdir();raw=encode(manifest);(destination/'manifest.json').write_bytes(raw);(destination/'manifest.sha256').write_text(sha(raw)+'\n')
    print(json.dumps({'manifest_sha256':sha(raw),'budget':manifest['budget'],'denominators':manifest['denominators'],'queries':queries,'snapshots':[{k:s[k] for k in ['commit','chunks','entities','source_bytes']} for s in snapshots]},indent=2))
    return manifest

if __name__=='__main__':
    import resource,socket
    resource.setrlimit(resource.RLIMIT_CPU,(90,90));resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    def blocked(*a,**kw):raise RuntimeError('Network prohibited in offline compiler')
    socket.socket.connect=blocked;socket.create_connection=blocked
    source=ROOT/'outputs/bailian-expanded-preparation-20261016/source'
    prepare(source,read(ROOT/'docs/BAILIAN_EXPANDED_PREPARATION_POLICY.json'),ROOT/'outputs/bailian-expanded-preparation-20261016/frozen-subset')
