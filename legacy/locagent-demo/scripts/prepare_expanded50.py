"""Public static dataset preparation only. Never contacts embedding/LLM endpoints."""
import ast, collections, gzip, hashlib, io, json, math, os, re, resource, sys, tarfile, time
from pathlib import Path, PurePosixPath
from decimal import Decimal
ROOT=Path('/home/lenovo/projects/LocAgent-rag-preview')
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from locagent_service.rag_offline import Version, allowed, chunk_snapshot
from prepare_expanded_subset import changed_old_lines
BASE=ROOT/'outputs/bailian-expanded50-20261016'
SOURCE=BASE/'source';ARCHIVES=BASE/'archives';CACHE=BASE/'snapshots'
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
    b=canonical(v)
    if p.exists():
        if p.read_bytes()!=b:raise ValueError('Refuse overwrite '+p.name)
    else:p.write_bytes(b)
def production(p):
    return p.endswith('.py') and not any(x.lower() in ('test','tests','docs','doc','testing') for x in PurePosixPath(p).parts) and not PurePosixPath(p).name.startswith('test_') and PurePosixPath(p).name!='conftest.py'

def archive_files(b,expected_root=None):
    if len(b)>8*1024**2:raise ValueError('download_limit')
    with gzip.GzipFile(fileobj=io.BytesIO(b)) as z:raw=z.read(32*1024**2+1)
    if len(raw)>32*1024**2:raise ValueError('expanded_limit')
    files={};inventory=[];seen=set();root=None
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as t:
        for i,m in enumerate(t):
            p=PurePosixPath(m.name)
            if i>=3000 or len(m.name)>512 or len(p.parts)>30:raise ValueError('file_count_or_path_limit')
            if p.is_absolute() or '..' in p.parts or '\\' in m.name or any(ord(c)<32 for c in m.name) or m.name in seen:raise ValueError('unsafe_path')
            seen.add(m.name)
            if root is None:root=p.parts[0]
            if expected_root is not None and root!=expected_root:raise ValueError('archive_commit_root_mismatch')
            if not p.parts or p.parts[0]!=root:raise ValueError('multiple_roots')
            if not(m.isfile() or m.isdir()):raise ValueError('links_unsupported')
            if m.isdir():continue
            if m.size>1024**2:raise ValueError('file_limit')
            name=PurePosixPath(*p.parts[1:]).as_posix()
            if name.endswith('.gitmodules'):raise ValueError('submodules_unsupported')
            data=t.extractfile(m).read(1024**2+1)
            if data.startswith(b'version https://git-lfs.github.com/spec/v1') or (name.endswith('.gitattributes') and b'filter=lfs' in data):raise ValueError('lfs_unsupported')
            accepted=allowed(name)
            inventory.append({'path':name,'bytes':len(data),'sha256':sha(data),'included':accepted,'reason':None if accepted else 'existing_allowed_policy_or_non_python'})
            if accepted:
                if b'\0' in data:raise ValueError('nul_python')
                files[name]=data
    return files,inventory

def snapshot(repo,commit,network=False):
    if not re.fullmatch('[a-z0-9_.-]+/[a-z0-9_.-]+',repo) or not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('bad_identity')
    key=repo.replace('/','__')+'-'+commit
    target=CACHE/(key+'.json')
    if target.exists():return read(target)
    ap=ARCHIVES/(key+'.tar.gz')
    if not ap.exists():
        if not network:raise ValueError('archive_not_cached')
        from locagent_service.public_repo import fetch
        b=fetch('codeload.github.com','/'+repo+'/tar.gz/'+commit)
        with ap.open('xb') as f:f.write(b)
    b=ap.read_bytes();files,inventory=archive_files(b,repo.split('/')[-1]+'-'+commit)
    chunks=[c for c in chunk_snapshot(files,Version(repo,commit,'qwen3.7-text-embedding-flash',max_chars=12000)) if c.kind=='function']
    docs=[{'id':c.id,'entity':c.path+':'+c.entity,'path':c.path,'start':c.start,'end':c.end,'text':c.path+':'+c.entity+'\n'+c.text} for c in chunks]
    if not docs:raise ValueError('no_functions')
    if any(len(d['text'].encode())>16000 for d in docs):raise ValueError('embedding_byte_limit')
    result={'repo':repo,'commit':commit,'archive_sha256':sha(b),'source_inventory':inventory,'python_files':len(files),'source_bytes':sum(map(len,files.values())),'documents':docs,'chunks':len(docs),'entities':len({d['entity'] for d in docs}),'provenance':'fixed-commit-codeload-archive-not-independent-git-tree-verification'}
    write(target,result);return result

def verify_patch_context(patch, raw):
    lines=raw.decode('utf-8').splitlines();old=None;remaining=0
    for line in patch.splitlines():
        if line.startswith('@@'):
            if remaining:raise ValueError('incomplete_patch_hunk')
            m=re.match(r'@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@',line)
            if not m:raise ValueError('invalid_patch_hunk')
            old=int(m[1]);remaining=int(m[2] or 1)
        elif old is not None and line[:1] in (' ','-'):
            if old<1 or old>len(lines) or lines[old-1]!=line[1:]:raise ValueError('patch_base_context_mismatch')
            old+=1;remaining-=1
        elif old is not None and not line.startswith(('+','\\')):raise ValueError('invalid_patch_line')
    if remaining:raise ValueError('incomplete_patch_hunk')

def target_overlap(current, previous):
    return any(r==r2 and (e==e2 or e.startswith(e2+'.') or e2.startswith(e+'.')) for r,e in current for r2,e2 in previous)

def apply_public_patch(patch,raw):
    verify_patch_context(patch,raw)
    lines=raw.decode('utf-8').splitlines();out=[];cursor=0;active=False
    for line in patch.splitlines():
        if line.startswith('@@'):
            start=int(re.match(r'@@ -(\d+)',line)[1]);start=max(0,start-1)
            out.extend(lines[cursor:start]);cursor=start;active=True
        elif active and line.startswith(' '):out.append(line[1:]);cursor+=1
        elif active and line.startswith('-'):cursor+=1
        elif active and line.startswith('+'):out.append(line[1:])
    out.extend(lines[cursor:]);return '\n'.join(out)

def semantic_ast(text):
    tree=ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node,(ast.Module,ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and node.body:
            first=node.body[0]
            if isinstance(first,ast.Expr) and isinstance(first.value,ast.Constant) and isinstance(first.value.value,str):node.body=node.body[1:]
    return ast.dump(tree,include_attributes=False)

def label(files,docs,source_files):
    fg=[];gg=[];unmapped=[];tests=[];semantic_changes=0
    for f in files:
        p=f['filename']
        if not production(p):
            if p.endswith('.py'):tests.append(p)
            continue
        fg.append(p)
        if 'patch' not in f:unmapped.append({'path':p,'reason':'missing_patch'});continue
        if p not in source_files:unmapped.append({'path':p,'reason':'not_present_in_base'});continue
        verify_patch_context(f['patch'],source_files[p])
        after=apply_public_patch(f['patch'],source_files[p])
        try:semantic_changes+=semantic_ast(source_files[p].decode('utf-8'))!=semantic_ast(after)
        except SyntaxError:semantic_changes+=1
        known={d['entity'].rsplit(':',1)[-1].split('.')[-1] for d in docs if d['path']==p}
        for added in re.findall(r'^\+\s*(?:async\s+)?def\s+(\w+)\(',f['patch'],re.M):
            if added not in known:unmapped.append({'path':p,'reason':'new_function_without_base_entity','name':added})
        for line,kind in changed_old_lines(f['patch']):
            candidates=[d for d in docs if d['path']==p and d['start']<=line<=d['end']]
            if candidates:
                d=min(candidates,key=lambda d:(d['end']-d['start'],-d['entity'].count('.'),d['entity']))
                gg.append(d['entity'])
            else:unmapped.append({'path':p,'line':line,'reason':'no_existing_function','kind':kind})
    if not semantic_changes:raise ValueError('documentation_only_or_no_semantic_python_change')
    return {'file_gold':sorted(set(fg)),'function_gold':sorted(set(gg)),'unmapped_changes':unmapped,'test_or_docs_evidence':sorted(tests)}

def title_before_fix(issue,events,pr):
    title=issue['title'];renames=sorted((e for e in events if e.get('event')=='renamed'),key=lambda e:e['created_at'],reverse=True)
    for e in renames:
        if e['created_at']>=pr['created_at']:title=e['rename']['from']
    return title,{'strategy':'reverse_title_rename_events_after_fix_PR_creation','rename_events':len(renames),'issue_created_at':issue['created_at'],'issue_updated_at':issue['updated_at'],'fix_PR_created_at':pr['created_at'],'fix_merged_at':pr['merged_at'],'body_edit_history_not_used':True}

def main(network=False):
    for p in [ARCHIVES,CACHE]:p.mkdir(exist_ok=True)
    pool=read(SOURCE/'ordered-candidate-pool-v2.json');accepted=[];audit=[];targets=set();seenissues=set();seenqueries=set();counts=collections.Counter();snaps={}
    for pair in pool:
        repo=pair['repo'].lower();stem=repo.replace('/','__')+'-'+str(pair['pr'])+'-'+str(pair['issue']);folder=SOURCE/'records'/stem
        entry={**pair,'status':'pending'}
        if counts[repo]>=10:entry['status']='repo_cap';audit.append(entry);continue
        if (repo,pair['issue']) in seenissues:entry['status']='duplicate_issue';audit.append(entry);continue
        if not(folder/'complete.json').exists():audit.append(entry);continue
        status=read(folder/'complete.json')
        if status.get('rejected'):entry['status']=status['rejected'];audit.append(entry);continue
        pr=read(folder/'pr.json');issue=read(folder/'issue.json');patch=read(folder/'files.json');events=read(folder/'events.json')
        try:
            if 'pull_request' in issue or not pr['merged_at'] or issue['created_at']>=pr['merged_at']:raise ValueError('not_preexisting_real_issue')
            if len(patch)!=pr['changed_files']:raise ValueError('incomplete_patch_page')
            if len(events)>=100:raise ValueError('event_pagination_required')
            text,history=title_before_fix(issue,events,pr)
            if not text.strip() or len(text.encode())>16000:raise ValueError('bad_query')
            if text.casefold().strip() in seenqueries:raise ValueError('duplicate_query')
            snap=snapshot(repo,pr['base']['sha'],network)
            source_files,_=archive_files((ARCHIVES/(repo.replace('/','__')+'-'+pr['base']['sha']+'.tar.gz')).read_bytes(),repo.split('/')[-1]+'-'+pr['base']['sha'])
            gold=label(patch,snap['documents'],source_files)
            if not gold['function_gold']:raise ValueError('no_function_gold')
            identities={(repo,e) for e in gold['function_gold']}
            if target_overlap(identities,targets):raise ValueError('overlapping_function_target')
            if not set(gold['file_gold'])<={d['path'] for d in snap['documents']}:raise ValueError('file_gold_outside_function_candidates')
            q={'id':repo.replace('/','__')+'-issue-'+str(pair['issue']),'repo':repo,'commit':pr['base']['sha'],'text':text,'source_url':issue['html_url'],'fix_url':pr['html_url'],'history':history,**gold,'function_primary_eligible':not gold['unmapped_changes'],'label_type':'static_patch_overlap_proxy_not_execution_verified_truth','source_record':stem,'symbol_hint':any(e.rsplit(':',1)[-1].split('.')[-1].lower() in text.lower() for e in gold['function_gold'])}
            accepted.append(q);counts[repo]+=1;targets.update(identities);seenissues.add((repo,pair['issue']));seenqueries.add(text.casefold().strip());snaps[(repo,pr['base']['sha'])]=snap;entry['status']='accepted';entry['id']=q['id']
        except Exception as e:entry['status']=getattr(e,'code',str(e) if isinstance(e,ValueError) else type(e).__name__)
        audit.append(entry)
        if len(accepted)==50:break
    docs={};memberships=0
    for s in snaps.values():
        memberships+=len(s['documents'])
        for d in s['documents']:
            k=sha(d['text'].encode());docs.setdefault(k,{'text':d['text'],'members':[]})['members'].append(d['id'])
    size=sum(len(d['text'].encode()) for d in docs.values())+sum(len(q['text'].encode()) for q in accepted)
    n=len(docs)+len(accepted);reserve=Decimal(n)*Decimal('.016384')
    budget={'document_memberships':memberships,'unique_document_inputs':len(docs),'query_inputs':len(accepted),'input_utf8_bytes':size,'requests_16_per_batch':math.ceil(len(docs)/16)+math.ceil(len(accepted)/16),'rough_tokens_bytes_div_4':size/4,'rough_cost_cny':str(Decimal(size)/4*Decimal('.125')/1000000),'rough_estimate_not_hard_bound':True,'reserved_tokens_per_input':131072,'rate_cny_per_million':'.125','new_reservation_cny':str(reserve),'old_held_cny':'1.277952','old_unknown_cny':'.557056','total_held_if_approved_cny':str(reserve+Decimal('1.277952'))}
    result={'status':'ready_to_review_50' if len(accepted)==50 else 'incomplete_no_execution','queries':accepted,'by_repo':dict(counts),'audit':audit,'budget':budget,'snapshots':[{k:v for k,v in s.items() if k!='documents'}|{'document_ids':[d['id'] for d in s['documents']]} for s in snaps.values()],'unique_documents':docs,'function_primary_denominator':sum(q['function_primary_eligible'] for q in accepted),'file_denominator':len(accepted)}
    destination=BASE/('build-'+str(time.time_ns())+'.json');write(destination,result)
    print(json.dumps({'file':str(destination),'accepted':len(accepted),'repos':dict(counts),'statuses':dict(collections.Counter(a['status'] for a in audit)),'budget':budget},indent=2))
    return result

if __name__=='__main__':
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(300,300))
    main('--fetch-source' in sys.argv)
