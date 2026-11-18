"""Generate a reviewable proposal and run its budgeted SDK simulation only."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from .bridge import LocAgentProcessRetriever
from .core import Limits, Snapshot, digest
from .journal import Ledger
from .openhands_replay import run_sdk_case
from .preparation import make_plan, PreparationSession


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--locagent-python', type=Path, required=True)
    parser.add_argument('--locagent-root', type=Path, required=True)
    parser.add_argument('--arm', choices=['baseline', 'retrieval'], help=argparse.SUPPRESS)
    args = parser.parse_args()
    case = json.loads(args.case.read_text())
    if set(case) != {'root', 'source_files', 'issue', 'scripts'}:
        parser.error('invalid_case_fields')
    root = Path(case['root'])
    if not root.is_absolute():
        root = args.case.resolve().parent / root
    snapshot = Snapshot(root, case['source_files'])
    plan = make_plan(snapshot, case['issue'], args.locagent_root)
    output = args.output.resolve()
    if args.arm is None:
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        (output / 'proposal.json').write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n')
        ledger = Ledger.create(output / 'simulation.sqlite', plan)
        for arm in ('baseline', 'retrieval'):
            command = [sys.executable, '-B', '-m', 'readonly_agent.prepare_run',
                       '--case', str(args.case.resolve()), '--output', str(output),
                       '--locagent-python', str(args.locagent_python), '--locagent-root', str(args.locagent_root), '--arm', arm]
            with (output / f'{arm}.log').open('x') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        summary = ledger.summary()
        (output / 'budget-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps({'plan_hash': digest(plan), 'simulation': summary, 'live_calls': 0}, indent=2))
        return
    saved = json.loads((output / 'proposal.json').read_text())
    if saved != plan:
        raise ValueError('proposal_or_source_changed')
    ledger = Ledger(output / 'simulation.sqlite', digest(plan))
    session = PreparationSession(ledger, args.arm)
    retriever = LocAgentProcessRetriever(snapshot, python=args.locagent_python, engine_root=args.locagent_root) if args.arm == 'retrieval' else None
    result = run_sdk_case(snapshot=snapshot, issue=case['issue'], script=case['scripts'][args.arm],
        output_dir=output / args.arm, retriever=retriever, limits=Limits(max_requests=4), preparation=session)
    if result['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
