"""Reproducible offline acceptance; only new output directory and synthetic responses."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'scripts')]
from locagent_service import bailian_expanded_runner as runner


def denied(*args, **kwargs):
    raise RuntimeError('offline acceptance prohibits network')


def main(out):
    socket.socket.connect = denied
    socket.create_connection = denied
    out = out.resolve()
    out.mkdir(mode=0o700)  # refuses overwrite
    base = ROOT / 'outputs/bailian-expanded50-20261016'
    protected = json.loads((base / 'protected-before.json').read_bytes())
    for p in (base / 'frozen').iterdir():
        protected[str(p)] = runner.sha(p.read_bytes())
    assert all(runner.sha(Path(p).read_bytes()) == h for p, h in protected.items())
    suite = unittest.TestSuite()
    patterns = ('test_expanded_gate.py', 'test_expanded_budget.py', 'test_expanded50.py', 'test_expanded_preparation.py',
                'test_offline_bailian_rrf.py', 'test_bailian_response.py', 'test_bailian_contract.py')
    for pattern in patterns:
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=pattern))
    with (out / 'tests.log').open('x') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError('offline tests failed; see new tests.log')
    manifest = base / 'frozen/manifest.json'
    plan = runner.load_plan(manifest, ROOT)
    proposal = runner.preview(manifest, ROOT)
    calls = []
    def fake(endpoint, raw):
        i = len(calls)
        assert endpoint == runner.ENDPOINT and runner.sha(raw) == plan[i]['body_sha256']
        n = len(json.loads(raw)['input']['texts'])
        calls.append({'request': i, 'body_sha256': runner.sha(raw), 'inputs': n})
        # Synthetic usage exactly 10 tokens/input; not a token estimate or a real bill.
        return 200, runner.canonical({'usage': {'prompt_tokens': n * 10, 'total_tokens': n * 10},
            'output': {'embeddings': [{'text_index': j, 'embedding': [1] + [0] * 1023} for j in range(n)]}})
    domain = out / 'offline-only-domain'
    domain.mkdir(mode=0o700)
    execution = runner._offline_frozen_acceptance(domain, fake)
    assert len(calls) == 618 and sum(c['inputs'] for c in calls) == 9864
    restart = runner._offline_frozen_acceptance(domain, lambda *_: (_ for _ in ()).throw(AssertionError('resend')))
    assert restart == execution
    assert all(runner.sha(Path(p).read_bytes()) == h for p, h in protected.items())
    audit = {'stage': 'offline-only-budget-adapter', 'real_model_calls': 0,
             'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
             'test_patterns': list(patterns), 'tests_sha256': runner.sha((out / 'tests.log').read_bytes()),
             'proposal': proposal, 'synthetic_execution': execution,
             'synthetic_usage_warning': '10 tokens/input fabricated only to test settlement, never a real cost estimate',
             'restart_sent_zero_requests': True, 'all_618_frozen_bodies_exact': True,
             'protected_files_unchanged': len(protected), 'protected_hashes': protected,
             'engine_hashes': runner.engine_identity(), 'request_bindings': calls}
    (out / 'audit.json').write_bytes(runner.canonical(audit))
    print(json.dumps({k: v for k, v in audit.items() if k not in ('protected_hashes', 'request_bindings')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New isolated output directory; never overwrite')
    main(parser.parse_args().out)
