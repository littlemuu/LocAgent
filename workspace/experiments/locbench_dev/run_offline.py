"""Real SDK / real static retrieval with mock HTTP only. No live entry point."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from experiments.dev_compare.suite import BatchGuard
from experiments.retrieval_choice.audit import audit
from readonly_agent.bridge import LocAgentProcessRetriever
from readonly_agent.core import Limits, Snapshot, digest
from readonly_agent.journal import Ledger
from readonly_agent.openhands_replay import run_sdk_case
from readonly_agent.preparation import PreparationSession
from .prepare import PROJECT, ROOT, ENGINE, read, save, validate


def worker(output, identifier, arm):
    manifest = validate()
    item = next(c for c in manifest['cases'] if c['id'] == identifier)
    case_path = PROJECT / item['case_file']
    case = read(case_path)
    snapshot = Snapshot(case_path.parent / case['root'], case['source_files'])
    ledger = Ledger(output / identifier / 'simulation.sqlite', digest(item['plan']))
    retriever = LocAgentProcessRetriever(snapshot, python=ENGINE/'.venv/bin/python', engine_root=ENGINE) if arm == 'retrieval' else None
    result = run_sdk_case(snapshot=snapshot, issue=case['issue'], script=case['scripts'][arm],
        output_dir=output/identifier/arm, retriever=retriever, limits=Limits(max_requests=4),
        preparation=PreparationSession(ledger, arm))
    if result['status'] != 'completed':
        raise RuntimeError('offline_arm_failed')


def replay(output):
    manifest = validate()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    guard = BatchGuard.create(output/'suite.sqlite', manifest)
    records = []
    try:
        for item in manifest['cases']:
            validate()
            guard.start(item['id'])
            pair = output/item['id']
            pair.mkdir(mode=0o700)
            save(pair/'proposal.json', item['plan'])
            ledger = Ledger.create(pair/'simulation.sqlite', item['plan'])
            for arm in item['arm_order']:
                started = time.perf_counter()
                record = {'case': item['id'], 'arm': arm, 'simulation': True, 'live_calls': 0,
                          'localization_score': None, 'actual_cost_cny': 0, 'status': 'failed',
                          'quality_not_scored_reason': 'scripted_connectivity_fixture'}
                records.append(record)
                try:
                    with (pair/(arm+'.log')).open('x') as log:
                        done = subprocess.run([sys.executable, '-B', '-m', 'experiments.locbench_dev.run_offline',
                            '--output', str(output), '--worker', item['id'], '--arm', arm],
                            cwd=PROJECT, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=False)
                    result = read(pair/arm/'result.json')
                    observation = audit(pair/'simulation.sqlite', pair/arm, arm)
                    record.update(status=result['status'], failure=result['failure'], requests=result['requests'],
                        tool_calls=result['tool_calls'], source_bytes=result['source_bytes'],
                        network_attempts=result['network_attempts'], observability=observation,
                        simulated_cost_upper_micro_cny=sum(c['cost'] or 0 for c in ledger.summary()['calls'] if c['arm']==arm))
                    if done.returncode or result['status'] != 'completed':
                        raise RuntimeError('offline_arm_failed')
                    # A lexical query may correctly return no matches. Exercise
                    # both that path and a source-path connectivity query; neither
                    # is autonomous selection or a quality measurement.
                    if arm == 'retrieval':
                        calls = observation['invocations']
                        delivered = bool(calls) and all(c['tool_succeeded'] and c['in_immediate_next_request'] for c in calls)
                        evidence = any(c['chain_verified'] for c in calls)
                        record['all_retrieval_observations_delivered'] = delivered
                        record['source_evidence_chain_verified'] = evidence
                        if not delivered or not evidence:
                            raise RuntimeError('retrieval_chain_not_verified')
                except BaseException as error:
                    record.update(status='failed', failure=str(error))
                    raise
                finally:
                    record['elapsed_wall_seconds'] = time.perf_counter()-started
                    save(pair/(arm+'-measurement.json'), record)
                print(json.dumps({'case':item['id'],'arm':arm,'status':record['status'],
                    'seconds':round(record['elapsed_wall_seconds'],2),'live_calls':0}), flush=True)
            guard.finish(item['id'], ledger.summary())
            save(pair/'budget-summary.json', ledger.summary())
    except BaseException as error:
        guard.halt(type(error).__name__)
        reached = {(r['case'], r['arm']) for r in records}
        save(output/'interrupted.json', {'reason':str(error), 'records':records,
            'not_run':[{'case':c['id'],'arm':arm,'raw_score':None} for c in manifest['cases']
                       for arm in c['arm_order'] if (c['id'],arm) not in reached], 'live_calls':0})
        raise
    save(output/'measurements.json', {'suite_hash':digest(manifest),'simulation':True,'records':records,
        'live_calls':0,'claims_benefit':False,'actual_cost_cny':0,'mock_requests':sum(r['requests'] for r in records)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', choices=[c['id'] for c in read(ROOT/'manifest.json')['cases']])
    parser.add_argument('--arm', choices=['baseline','retrieval'])
    args = parser.parse_args()
    if args.worker:
        if not args.arm:
            parser.error('--arm required for worker')
        worker(args.output.resolve(), args.worker, args.arm)
    else:
        replay(args.output.resolve())
