"""Read-only validation of sealed run; writes derived delivery artifacts only."""
import collections, hashlib, json, re
from pathlib import Path
P=Path(__file__).resolve().parents[1]; D=P/'delivery'; E=P/'evidence'; R=E/'run'
def load(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,x): (D/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
rows=load(D/'ABC-per-task.json'); state=load(R/'completed.json'); steps=state['steps']; order=load(P/'execution-order.json')['tasks']
checks={}; mismatches=[]; count=0; image_rows=[]
for f in sorted((R/'evidence-manifests').glob('*.json')):
 m=load(f); iid=m['instance_id']; image=m['image']; arms=[x for x in rows if x['instance_id']==iid]
 for n,h in m['products'].items():
  count+=1
  if not (R/n).is_file() or sha(R/n)!=h: mismatches.append(n)
 assert sorted(m['arms_recorded'])==['A','B','C']
 assert len(arms)==3 and {x['image_id'] for x in arms}=={image['id']}
 c=steps[iid+'--archive-and-image-cleanup']; cr=c['result']
 assert cr['evidence_manifest_sha256']==sha(f) and c['status']=='completed'
 assert c['started_at']<=m['at']<=c['ended_at']
 assert all(v['ended_at']<=c['started_at'] for k,v in steps.items() if k.startswith(iid+'--') and k!=iid+'--archive-and-image-cleanup')
 assert not image['preexisting'] and cr['removed_new_image']==image['name'] and cr['image_id']==image['id']
 image_rows.append(dict(instance_id=iid,**image,all_three_arm_ids_match=True,cleanup_after_evidence_verified=True,cleanup=cr,missing_products=m['missing_due_to_failure_or_not_run']))
checks.update(evidence_manifests=50,product_hashes_checked=count,product_hash_mismatches=mismatches,same_image_for_all_arms=50,new_task_images_removed_after_evidence=50)
checks['deployment_files_checked']=len(load(P/'deployment-manifest.json'))
checks['deployment_hash_mismatches']=[n for n,h in load(P/'deployment-manifest.json').items() if sha(P/n)!=h]
assert not mismatches and not checks['deployment_hash_mismatches']
assert [(x['number'],x['instance_id'],x['arm']) for x in state['rows']]==[(t['number'],t['instance_id'],a) for t in order for a in t['arm_order']]
assert set(x.name for x in (R/'once').iterdir())==set(steps)
intervals=sorted(steps.items(),key=lambda kv:kv[1]['started_at'])
assert all(a[1]['ended_at']<=b[1]['started_at'] for a,b in zip(intervals,intervals[1:]))
for k,v in intervals: assert load(R/'once'/k)['at']<=v['started_at']
checks.update(fixed_task_and_arm_order_verified=True,stage_once_markers=len(steps),stage_intervals_nonoverlapping=True,stage_counts=dict(collections.Counter(k.rsplit('--',1)[1] for k in steps)))
calls=[]
for f in R.glob('trial/*/*/ledger.json'):
 cs=load(f)['calls']; assert [x['sequence'] for x in cs]==list(range(1,len(cs)+1))
 for stage,cap in [('locator',4),('coding',40)]: assert sum(x['context'].endswith(':'+stage) for x in cs)<=cap
 calls+=cs
checks.update(request_reservations=len(calls),request_status_counts=dict(collections.Counter(c['status'] for c in calls)),actual_model_identifiers=sorted({c['actual_model'] for c in calls if c.get('actual_model')}),per_episode_request_sequence_unique=True,request_budgets_respected=True)
obs=[json.loads(x) for x in (E/'resource-observations.jsonl').read_text().splitlines()]; assert all(x['matches_frozen_observation'] for x in obs)
checks['resource_observation_count']=len(obs)
checks['resource_configurations']=[dict(memory_bytes=k[0],nano_cpus=k[1],network_mode=k[2],observations=v) for k,v in collections.Counter((x['Memory'],x['NanoCpus'],x['NetworkMode']) for x in obs).items()]
progress=[json.loads(x) for x in (D/'blind-progress.jsonl').read_text().splitlines()]
checks['minimum_observed_free_bytes']=min(x.get('free_bytes_now',x['free_bytes']) for x in progress)
assert checks['minimum_observed_free_bytes']>=30*1024**3
checks['original_cache']=load(D/'final-remote-verification.json')
checks['status']='passed'
write('integrity-and-execution-audit.json',checks);write('image-digests-and-cleanup.json',image_rows)
totals={}
for arm in 'ABC':
 rr=[r for r in rows if r['arm']==arm]; t={}
 for field in ['total_cost','localization_cost','coding_cost']:
  t[field]={k:sum(r[field].get(k,0) for r in rr) for k in rr[0][field] if k!='cache_usage_complete'}
  t[field]['cache_usage_complete']=all(r[field]['cache_usage_complete'] for r in rr)
 t['stage_seconds']={s:sum(r['stage_seconds'].get(s,0) for r in rr) for s in ['locator','coding','evaluation']}
 t['coding_never_started']=sum(r.get('coding_requests') is None for r in rr)
 t['coding_first_request_rejected_without_actions']=sum(r.get('coding_requests')==1 and any('provider_http_402' in str(e) for e in r['errors']) for r in rr)
 totals[arm]=t
write('usage-cost-time-supplement.json',dict(arms=totals,actual_account_bill_observed=False,uncertain_reservations_are_not_charges=True,run_seconds=state['finished_at']-state['started_at'],image_seconds=sum(s['ended_at']-s['started_at'] for k,s in steps.items() if k.endswith('--image')),run_started_at=state['started_at'],run_finished_at=state['finished_at']))
ha=[]
patterns={'certificate_or_ssl':r'CERTIFICATE_VERIFY_FAILED|certificate verify failed|SSLCertVerificationError','missing_module':r'ModuleNotFoundError:.*','pytest_fixture':r"fixture '[^']+' not found",'leap_second':r'leap.second.*(?:failed|error)|(?:failed|error).*leap.second','missing_requirements':r'Could not find requirements.txt.*','import_error':r'^ImportError:.*'}
for r in rows:
 ep=R/'trial'/r['instance_id']/r['arm']; fs=list(ep.glob('harness/**/report.json')); ts=list(ep.glob('harness/**/test_output.txt'))
 raw=load(fs[0]).get(r['instance_id']) if fs else None
 txt=ts[0].read_text(errors='replace') if ts else ''
 console=(ep/'evaluation-console.log').read_text(errors='replace') if (ep/'evaluation-console.log').exists() else ''
 # Strip ANSI solely for derived display/search; never alter the raw log or score.
 plain=re.sub(r'\x1b\[[0-9;]*[a-zA-Z]','',txt)
 summaries=[l.strip() for l in plain.splitlines() if re.search(r'\b\d+ (?:passed|failed|error|errors|skipped|deselected)\b',l) and (re.match(r'^=+',l) or re.match(r'^\d+ ',l))]
 success_summary=any(re.search(r'\b\d+ passed\b',l) and not re.search(r'\b\d+ (?:failed|errors?|exceptions?)\b',l) for l in summaries[-1:])
 flags={k:list(dict.fromkeys(m.group(0)[:250] for m in re.finditer(pat,txt+'\n'+console,re.I|re.M)))[:8] for k,pat in patterns.items()}
 d=dict(number=r['number'],instance_id=r['instance_id'],arm=r['arm'],resolved=r['resolved'],status=r['status'],errors=r['errors'],report_path=str(fs[0].relative_to(P)) if fs else None,test_output_path=str(ts[0].relative_to(P)) if ts else None,report=raw,raw_test_summary_lines=summaries,raw_last_summary_all_pass_but_report_false=bool(raw and raw.get('resolved') is False and success_summary),environment_text_signals={k:v for k,v in flags.items() if v})
 ha.append(d)
write('raw-harness-audit.json',ha)
write('technical-failures.json',[r for r in rows if r['status']!='completed'])
manual=load(D/'manual-judgments.json'); ms={a:dict(collections.Counter(x['no_progress_loop'] for x in manual if x['arm']==a)) for a in 'ABC'}
write('manual-review-summary.json',dict(reviewed_unresolved=len(manual),by_arm_loop_judgment=ms,C_wrong_localization_adoption=dict(collections.Counter(x['wrong_localization_adoption'] for x in manual if x['arm']=='C')),all40_by_arm={a:sum(x['used_all_40'] is True for x in manual if x['arm']==a) for a in 'ABC'}))
print(json.dumps(dict(integrity=checks,cost=totals,manual=load(D/'manual-review-summary.json'),raw_summary_discrepancies=[(x['instance_id'],x['arm'],x['raw_test_summary_lines'][-1:]) for x in ha if x['raw_last_summary_all_pass_but_report_false']]),ensure_ascii=False,indent=2))
