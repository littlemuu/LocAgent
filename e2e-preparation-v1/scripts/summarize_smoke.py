import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from locagent_e2e.common import write_json,manifest
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
ledger=json.loads((a.run/'ledger.json').read_text()) if (a.run/'ledger.json').exists() else {'calls':[]}
records=ledger['calls'];known=[r for r in records if r['status']=='received'];uncertain=[r for r in records if r['status']!='received'];episodes=[]
for identifier in manifest()['smoke_ids']:
 for arm in ('A','B'):
  episode=a.run/identifier/arm;agent=episode/'agent/result.json';evaluation=episode/'harness/evaluation.json'
  episodes.append({'instance_id':identifier,'arm':arm,'agent':json.loads(agent.read_text()) if agent.exists() else {'status':'未运行'},'evaluation':json.loads(evaluation.read_text()) if evaluation.exists() else {'status':'未运行'}})
complete=len(episodes)==4 and all(e['evaluation']['status']=='completed' for e in episodes)
pt=sum(r['usage']['prompt_tokens'] for r in known);ct=sum(r['usage']['completion_tokens'] for r in known);cost=sum(r['charged_upper_microcny'] for r in known)/1e6
value={'scope':'pipeline only; no repair-rate interpretation','episodes':episodes,'requests_started':len(records),'requests_received':len(known),'uncertain_requests':len(uncertain),'prompt_tokens':pt,'completion_tokens':ct,'metered_peak_cost_upper_cny':cost,'provider_bill_deduction':'not_observed','held_unknown_cny':sum(r['reserved_microcny'] for r in uncertain)/1e6,'actual_model_ids':sorted({r['actual_model'] for r in known}),'all_four_evaluated':complete,'formal_estimate_from_smoke':{'episodes':48,'multiplier':12,'prompt_tokens':pt*12,'completion_tokens':ct*12,'metered_cost_upper_cny':cost*12,'caveat':'linear two-task extrapolation, not measured 24-task cost; no quality inference'} if complete else '未运行完整冒烟，不能据实测外推正式试跑'}
write_json(a.output,value);print(json.dumps({k:v for k,v in value.items() if k!='episodes'},ensure_ascii=False))
