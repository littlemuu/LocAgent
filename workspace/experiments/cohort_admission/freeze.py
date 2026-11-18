"""Freeze an unapproved proposal. Never creates a production grant."""
from pathlib import Path
import sys
from readonly_agent.preparation import make_plan
from readonly_agent.core import digest
from experiments.cohort_preflight.entry import ROOT, read, sha, save, load_entry
from experiments.eval_preflight.common_contract import CONTRACT
from .guard import CASE, NAMES, SENT, source_hashes, verify

def plan_for(mode):
    out = ROOT / 'verification/cohort-preflight-v1'
    row = next(r for r in read(out / 'runtime-catalog.json')['cases'] if r['id'] == CASE)
    value, snapshot = load_entry(row['entry'], row['entry_sha256'])
    status = out / 'body-status' / (CASE + '.json')
    plan = make_plan(snapshot, value['issue'], ROOT / 'engine_adaptation/v4/engine')
    plan.update(cohort_admission_version=1, cohort_execution=mode,
        cohort_sources=source_hashes(), comparison_names=NAMES, comparison_contract=CONTRACT,
        send_categories=SENT, live_transport_enabled=(mode == 'live'),
        purpose='One exposed SQLGlot development task, adapted systems protocol validation; not independent quality evaluation',
        public_pricing_checked_utc_date=None, pricing_status='historical ceilings; current account confirmation required before grant',
        cohort_binding={'case_id':CASE,'entry':row['entry'],'entry_sha256':row['entry_sha256'],
                        'body_status':str(status),'body_status_sha256':sha(status)})
    verify(plan, mode)
    return plan

def main():
    name = sys.argv[1] if len(sys.argv) == 2 else 'cohort-admission-v1'
    if not name.startswith('cohort-admission-') or Path(name).name != name:
        raise ValueError('isolated_verification_name_required')
    out = ROOT / 'verification' / name
    out.mkdir(exist_ok=False)
    for mode in ('live', 'rehearsal'):
        plan = plan_for(mode)
        save(out / (mode + '-proposal.json'), plan)
        save(out / (mode + '-digest.json'), {'sha256':digest(plan),'authorization':'not_granted'})
    print('Frozen unapproved proposals; no grant, credential or request.')

if __name__ == '__main__':
    main()
