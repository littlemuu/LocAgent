"""Default dry-run. One explicitly approved continuation; no overrides/retries."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from locagent_service import bailian_expanded_resume as resume
from locagent_service.bailian_expanded_runner import Halt
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-approved-continuation',action='store_true');p.add_argument('--approval-id')
    a=p.parse_args()
    try:
        print(json.dumps(resume.run(approval_id=a.approval_id) if a.execute_approved_continuation else resume.preview(),indent=2),flush=True)
    except Exception as exc:
        print(json.dumps({'status':'stopped','code':str(exc) if isinstance(exc,Halt) else 'continuation_execution_failure','automatic_retry':False}),flush=True)
        sys.exit(2)
