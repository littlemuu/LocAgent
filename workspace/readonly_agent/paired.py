"""Matched offline arms. No scoring labels, old authorization or paid transport."""
from dataclasses import asdict
import json
from pathlib import Path

from .core import Limits, ScriptedProvider, digest, run, runtime_identity


def run_pair(*, issue, snapshot, scripts, retriever_factory, output_dir,
             limits=Limits(), order=('baseline', 'retrieval')):
    if set(order) != {'baseline', 'retrieval'} or len(order) != 2:
        raise ValueError('invalid_pair_order')
    if set(scripts) != {'baseline', 'retrieval'}:
        raise ValueError('both_arm_scripts_required')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    contract = {'snapshot': snapshot.identity, 'source_hashes': dict(snapshot.hashes),
                'issue_hash': digest(issue), 'limits': asdict(limits), 'order': list(order),
                'runtime_hash': runtime_identity(),
                'provider': 'offline-scripted', 'quality_measured': False,
                'script_hashes': {k: digest(v) for k, v in scripts.items()}}
    (output / 'contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    results = {}
    for arm in order:
        # New provider/history/budgets/cache and fresh retriever for every arm.
        retriever = retriever_factory(snapshot) if arm == 'retrieval' else None
        if arm == 'retrieval' and retriever is None:
            raise ValueError('retrieval_arm_requires_adapter')
        results[arm] = run(issue=issue, snapshot=snapshot, provider=ScriptedProvider(scripts[arm]),
                           trace_path=output / (arm + '.jsonl'), retriever=retriever, limits=limits)
    (output / 'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n')
    return results
