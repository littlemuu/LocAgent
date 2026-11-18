"""Explicit single-run entry. Default only previews; no alternate run/ledger/key."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from locagent_service import bailian_expanded_runner as r

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-approved-run',action='store_true')
    parser.add_argument('--approval-id')
    args=parser.parse_args()
    if not args.execute_approved_run:
        print(json.dumps(r.preview(r.FROZEN,r.ROOT),indent=2))
    else:
        try:
            print(json.dumps(r.execute(approval_id=args.approval_id),indent=2),flush=True)
        except Exception as exc:
            code=str(exc) if isinstance(exc,r.Halt) else 'execution_or_persistence_failure'
            print(json.dumps({'status':'stopped','code':code,'run_id':r.RUN_ID,'automatic_retry':False}),flush=True)
            sys.exit(2)
