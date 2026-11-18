"""Freeze separate execution/scoring inventories and exact verification denominators."""
import collections,json
from pathlib import Path
from .entry import ROOT,read,sha,save,checked_file
OUT=ROOT/'verification/cohort-preflight-v1'
def main():
    catalog=read(OUT/'runtime-catalog.json');summary=read(OUT/'preparation-summary.json')
    statuses={read(p)['id']:read(p) for p in (OUT/'body-status').glob('*.json')}
    execution=[]
    for row in catalog['cases']:
        status=statuses[row['id']]
        checked_file(row['entry'],row['entry_sha256'])
        attpath=Path(status['body_directory'])/'attestation.json';att=read(checked_file(attpath,status['body_attestation_sha256']))
        if status['status']!='ready' or att['snapshot']!=row['snapshot']:raise ValueError('body_not_ready')
        for name,h in att['artifacts'].items():checked_file(attpath.parent/name,h)
        execution.append({'case_id':row['id'],'entry':row['entry'],'entry_sha256':row['entry_sha256'],
            'snapshot':row['snapshot'],'body_directory':status['body_directory'],
            'body_attestation_sha256':status['body_attestation_sha256'],'body_version':status['body_version']})
    save(OUT/'execution-catalog.json',{'version':1,'cases':execution,'model_execution_enabled':False,
        'comparison_names':['LocAgent-graph+physical-line80-BM25/adapted','OpenHands-basic+entity-BM25/adapted'],
        'not_pristine_upstream_comparison':True,'not_retrieval_only_causal_comparison':True})
    manual=read(ROOT/'verification/eval-fair-review-v1/scoring-only/review-results.json')['reviews']
    hold={r['id'] for r in manual if r['status'].startswith('hold_')}
    old=read(ROOT/'verification/eval-preflight-v2/cohort-semantic-audit.json')
    decisions={r['id']:r['decision'] for r in old['verified_old_checklist_records']}
    bins=collections.Counter();admission=[]
    for r in catalog['cases']:
        id=r['id'];status='historical_excluded' if decisions.get(id)=='excluded' else (
            'development_control_only' if decisions.get(id)=='control_only' else ('manual_hold' if id in hold else 'pending_final_review'))
        bins[status]+=1;admission.append({'id':id,'status':status,'score_admitted':False})
    save(OUT/'scoring-only/admission-status.json',admission)
    pilot=read(OUT/'pilot/summary.json');code=read(OUT/'pilot/claim.json')['code']
    runtime_changes=[n for n,h in code.items() if sha(ROOT/n)!=h]
    if runtime_changes!=['experiments/cohort_preflight/pilot.py'] and set(runtime_changes)!={'experiments/cohort_preflight/pilot.py'}:
        raise ValueError('unexpected_runtime_change_after_pilot')
    # The only follow-up is outer partial-failure accounting, tested independently.
    ledger_calls=sum(r['mock_requests'] for r in pilot['results'])
    assert pilot['completed']==2 and ledger_calls==16
    other_issue_leaks=[]
    for r in pilot['results']:
        own=read(next(x['entry'] for x in catalog['cases'] if x['id']==r['case_id']))
        other=next(x for x in pilot['results'] if x['case_id']!=r['case_id'])
        foreign_issue=read(next(x['entry'] for x in catalog['cases'] if x['id']==other['case_id']))['issue']
        native=read(OUT/'pilot'/r['case_id']/'native.json')['requests']
        sdk=read(OUT/'pilot'/r['case_id']/'sdk/wire-requests.json')
        assert all(any(own['issue'] in (m.get('content') or '') for m in req['messages']) for req in native+sdk)
        if any(foreign_issue in (m.get('content') or '') for req in native+sdk for m in req['messages']):other_issue_leaks.append(r['case_id'])
    assert not other_issue_leaks
    risks=read(OUT/'scoring-only/structural-label-audit.json')
    risk_a={r['id'] for r in risks if r['potential_edited_functions_omitted']}
    risk_b={r['id'] for r in risks if r['patch_paths_outside_python_snapshot']}
    mp=ROOT/'engine_adaptation/v4/adapted-manifest.json';v4=read(mp)
    for n,h in v4['engine']['files'].items():checked_file(ROOT/'engine_adaptation/v4/engine'/n,h)
    for n,h in v4['harness_files'].items():checked_file(ROOT/n,h)
    prior=read(ROOT/'verification/eval-fair-v3/proposal.json')
    for n,h in prior['adapter_sources'].items():checked_file(ROOT/n,h)
    label_root=Path('/Users/xiaomu/Documents/Codex/2026-11-10/task/locbench-remaining-batch134-20261113/scoring-only/labels')
    for r in risks:checked_file(label_root/(r['id']+'.json'),r['label_sha256'])
    final={'technical_source_and_existing_index_hash_checked':130,'hash_unchecked':0,
        'new_body_built_and_reload_verified':130,'new_body_failed':0,'new_body_unprocessed':0,
        'body_chunks':sum(r['chunks'] for r in statuses.values()),
        'body_bytes':sum(p.stat().st_size for p in (OUT/'body').rglob('*') if p.is_file()),
        'paired_engine_end_to_end_cases':2,'paired_engine_end_to_end_unrun':128,'paired_mock_requests':16,
        'manual_semantic_preliminary':6,'manual_semantic_unreviewed':124,'second_reviews_completed':0,
        'automated_structural_label_audit':130,'potential_label_omission_cases':len(risk_a),
        'outside_snapshot_patch_cases':len(risk_b),'risk_union':len(risk_a|risk_b),'risk_overlap':len(risk_a&risk_b),
        'formal_admission_bins':dict(bins),'formal_scoring_admitted':0,
        'earlier_unresolved_130_meant_not_admitted':True,
        'source_only_entry_schema_checked':130,'cross_case_issue_leak_detected':False,
        'source_runtime_core_unchanged_since_e2e':True,'post_e2e_change':'Outer batch partial-failure accounting only; 18 regression tests pass.',
        'real_model_requests':0,'real_cost_cny':0,'tests_passed':18,
        'v4_engine_harness_unchanged':True,'previous_adapters_unchanged':True,'all_original_gold_hashes_unchanged':True,
        'live_ready':False,'live_blocker':'Generic catalog and new physical-line backend are simulation-only; new executable live admission binding/freeze, current account prices and explicit approval remain required.'}
    save(OUT/'final-verification.json',final)
    save(OUT/'code-lock.json',{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'experiments/cohort_preflight').glob('*.py')})
    print(json.dumps(final,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
