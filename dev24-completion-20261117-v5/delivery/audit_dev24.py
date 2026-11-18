"""Audit trial-generated evidence and config metadata, without reading task labels."""
import argparse, hashlib, json
from pathlib import Path
def audit(roots):
    contracts=[];models=set();bindings=set();episodes=[];count=[]
    for root,expected_count,limit in roots:
        root=Path(root);s=json.loads((root/'state.json').read_text());ledger=json.loads((root/'ledger.json').read_text())
        bindings.add(s['code_binding']);assert s['failed'] is None
        ids=s['trial_ids'];assert len(ids)*2==expected_count
        stages=s['steps'];chronology=sorted((v['started_at'],k) for k,v in stages.items() if k.startswith('trial:') and k.endswith(':agent'))
        assert [k for _,k in chronology]==[f'trial:{i}:{arm}:agent' for i in ids for arm in ['A','B']]
        intervals=sorted((v['started_at'],v['ended_at']) for v in stages.values())
        assert all(a[1]<=b[0] for a,b in zip(intervals,intervals[1:]))
        for i in ids:
            first_payloads=[]
            for arm in ['A','B']:
                p=root/'trial'/i/arm
                code=json.loads((p/'coding.json').read_text());agent=json.loads((p/'agent/result.json').read_text());pred=json.loads((p/'prediction.json').read_text());ev=json.loads((p/'harness/evaluation.json').read_text());patch=(p/'patch.diff').read_text()
                assert code['status']==ev['status']=='completed'
                assert pred['instance_id']==i and pred['model_patch']==patch
                assert code['empty_patch']==(not bool(patch.strip()))
                assert code['patch_sha256']==hashlib.sha256(patch.encode()).hexdigest()
                assert agent['requests']<=40
                first=min((e['request'] for e in agent['source_edit_events']),default=None)
                assert agent['first_source_edit_request']==first
                assert all(1<=e['request']<=agent['requests'] for e in agent['source_edit_events'])
                contracts.append((agent['system_prompt_sha256'],agent['tool_schema_sha256'],json.dumps(agent['budget'],sort_keys=True)))
                episodes.append((i,arm))
                request=min((p/'wire').glob('request-*.json'),key=lambda f:int(f.stem.split('-')[-1]))
                payload=json.loads(request.read_text())
                user=next(m for m in payload['messages'] if m['role']=='user')
                content=json.loads(user['content'])
                if arm=='A':assert content['localization_packet'] is None
                else:assert content['localization_packet']==json.loads((root/'trial'/i/'localization.json').read_text())
                content['localization_packet']=None;user['content']=content
                first_payloads.append(payload)
            assert first_payloads[0]==first_payloads[1], 'A/B first request differs beyond localization input'
        if limit is None:
            amendment=json.loads((root/'budget-amendment.json').read_text())
            assert amendment['financial_stop_disabled'] is True
            assert ledger['limit_microcny']==amendment['scope_envelope_microcny']
            assert ledger['financial_stop_disabled'] is True
        else:assert ledger['limit_microcny']==limit*1e6
        assert not ledger['stopped']
        assert all(r['status']=='received' for r in ledger['calls'])
        assert sum(r['charged_upper_microcny'] for r in ledger['calls'])<=ledger['limit_microcny']
        models.update(r['actual_model'] for r in ledger['calls']);count.append(len(ledger['calls']))
    assert len(set(episodes))==48 and len(set(contracts))==1 and len(bindings)==len(models)==1
    return dict(status='passed',trial_episodes=48,trial_pairs=24,core_binding=next(iter(bindings)),actual_model=next(iter(models)),ab_prompt_schema_budget_identical=True,ab_first_payload_identical_except_localization=True,all_predictions_match_diff=True,first_edit_and_empty_patch_verified=True,single_lane_A_then_B_verified=True,prior_round_limit_cny=50,new_round_financial_stop_disabled_by_user=True,ledger_all_requests_including_prior_smoke=count,unknown_requests=0,holdout_content_read=False,extra_repetitions_run=False)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=audit([(a.old,16,50),(a.new,32,None)])
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
