"""Join exposed dev24 evidence only. Never reads task content or reference patches."""
import argparse, csv, json, math, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'e2e-checkpoint-v4/scripts'))
from summarize_checkpoint import summarize, cost

def exact_mcnemar(b, c):
    n = b + c
    return min(1., 2 * sum(math.comb(n, k) for k in range(min(b,c)+1)) / 2**n) if n else 1.

def stats(rows):
    completed = [r for r in rows if r['status'] == 'completed']
    byid = {}
    for r in completed: byid.setdefault(r['instance_id'], {})[r['arm']] = r
    pairs = {i: v for i,v in byid.items() if set(v) == {'A','B'}}
    awin = [i for i,p in pairs.items() if p['A']['resolved'] and not p['B']['resolved']]
    bwin = [i for i,p in pairs.items() if p['B']['resolved'] and not p['A']['resolved']]
    armstats = {}
    for arm in ['A','B']:
        rr = [r for r in completed if r['arm']==arm]
        first = [r['first_source_edit_request'] for r in rr if r['first_source_edit_request'] is not None]
        armstats[arm] = dict(completed=len(rr), resolved=sum(r['resolved'] for r in rr),
            empty_patch_count=sum(r['empty_patch'] for r in rr),
            empty_patch_rate=sum(r['empty_patch'] for r in rr)/len(rr) if rr else None,
            first_source_edit_median=statistics.median(first) if first else None,
            ever_edited_count=len(first), never_edited_count=len(rr)-len(first),
            totals={k:sum(r['total_cost'][k] for r in rr) for k in ['requests','input_tokens','output_tokens','metered_cny','upper_cny']},
            wall_seconds_including_locator=sum(r['total_seconds'] for r in rr))
    differences=[]
    for i,p in pairs.items():
        d={'instance_id':i,'A_resolved':p['A']['resolved'],'B_resolved':p['B']['resolved']}
        for k in ['input_tokens','output_tokens','metered_cny','upper_cny']:
            d[k+'_B_minus_A']=p['B']['total_cost'][k]-p['A']['total_cost'][k]
        d['total_tokens_B_minus_A']=d['input_tokens_B_minus_A']+d['output_tokens_B_minus_A']
        d['seconds_B_minus_A']=p['B']['total_seconds']-p['A']['total_seconds']
        differences.append(d)
    medians={k:statistics.median(d[k] for d in differences) for k in differences[0] if k.endswith('_B_minus_A')} if differences else {}
    return dict(arms=armstats,complete_pairs=len(pairs),A_correct_B_wrong=awin,A_wrong_B_correct=bwin,
                exact_mcnemar_two_sided_p=exact_mcnemar(len(awin),len(bwin)) if pairs else None,
                paired_difference_medians=medians,paired_differences=differences)

def main():
    p=argparse.ArgumentParser();p.add_argument('--old',type=Path,required=True);p.add_argument('--old-run',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    old=json.loads(a.old.read_text());new=summarize(a.new)
    rows=old['trial_rows']+new['trial_rows']
    for r in rows[len(old['trial_rows']):]:r['number']+=8
    assert old['code_binding']==new['code_binding']
    assert len(rows)==48 and len({(r['instance_id'],r['arm']) for r in rows})==48
    state=json.loads((a.new/'state.json').read_text())
    newwall=max(s.get('ended_at',s['started_at']) for s in state['steps'].values())-state['started_at']
    totalwall=old['trial_wall_seconds_including_images_and_cleanup']+newwall
    s=stats(rows)
    s.update(code_binding=new['code_binding'],models=sorted(set(old['models']+new['models'])),
        new_round_cost=new['round_cost'],new_round_failed_step=new['failed_step'],
        new_round_completed=(a.new/'completed.json').exists(),trial_rows=rows,
        new_round_wall_seconds=newwall,combined_trial_wall_seconds=totalwall,
        price_account_bill_observed=False,extra_repetitions_run=False)
    amendment=a.new/'budget-amendment.json'
    s['new_round_budget_amendment']=json.loads(amendment.read_text()) if amendment.exists() else None
    totalcost={k:sum(r['total_cost'][k] for r in rows) for k in ['requests','input_tokens','output_tokens','metered_cny','upper_cny']}
    s['all_trial_cost']=totalcost
    oldledger=json.loads((a.old_run/'ledger.json').read_text())
    newledger=json.loads((a.new/'ledger.json').read_text())
    paid=[r for ledger in [oldledger,newledger] for r in ledger['calls'] if r['context'].startswith('trial:') and r['status']=='received']
    peak_cost=sum(r['peak_cache_adjusted_microcny'] for r in paid)/1e6
    s['all_trial_peak_cache_adjusted_cny']=peak_cost
    # Only produce a full24 measured extrapolation after all48 observations are complete.
    if s['complete_pairs']==24:
        s['extra_two_repetitions_estimate']={k:2*v for k,v in totalcost.items()}
        s['extra_two_repetitions_estimate'].update(coding_episodes=96,locator_episodes=48,wall_seconds=2*totalwall,peak_same_cache_cny=2*peak_cost,offpeak_same_cache_cny=peak_cost,cloud_compute_and_disk_cny_at_last_quote=2*totalwall/3600*4.09,network_fee='not estimated: traffic volume not measured')
    else:s['extra_two_repetitions_estimate']='未运行；全24题实测尚不完整，暂不外推'
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
    flat=[]
    for r in rows:
        flat.append({k:r.get(k) for k in ['number','instance_id','arm','status','empty_patch','first_source_edit_request','resolved','total_seconds']}|r['total_cost'])
    for name,rr in [('逐题结果.csv',flat),('逐题配对差值.csv',s['paired_differences'])]:
        if rr:
            with (a.output/name).open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=rr[0]);w.writeheader();w.writerows(rr)
    print(json.dumps({k:v for k,v in s.items() if k not in ['trial_rows','paired_differences']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
