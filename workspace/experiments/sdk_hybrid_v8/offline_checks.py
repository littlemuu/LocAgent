"""Run a whole test suite under the network guard, including SDK imports."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from readonly_agent.offline import no_network


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=('core', 'sdk'), required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--legacy-root', required=True)
    parser.add_argument('--retrieval-python', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = None
    attempts = []
    error = None
    versions = {}
    for package in ('openhands-sdk', 'bm25s', 'PyStemmer'):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            pass
    with (output / 'tests.log').open('w') as log, TemporaryDirectory(prefix='v8-tests-') as td:
        try:
            with redirect_stdout(log), redirect_stderr(log), no_network(Path(td) / 'profiles') as attempts:
                with patch.dict(os.environ, {
                    'V8_LEGACY_ROOT': str(Path(args.legacy_root).resolve()),
                    'V8_RETRIEVAL_PYTHON': str(Path(args.retrieval_python).absolute()),
                    'OPENHANDS_SUPPRESS_BANNER': '1',
                }):
                    name = 'test_hybrid_v8.py' if args.suite == 'core' else 'test_sdk_hybrid_v8.py'
                    suite = unittest.defaultTestLoader.discover(
                        str(Path(__file__).resolve().parents[2] / 'tests_v8'), pattern=name)
                    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
            log.write('\nOffline runner failed: ' + error + '\n')
    passed = result is not None and result.wasSuccessful() and not attempts and error is None
    summary = {
        'suite': args.suite, 'status': 'passed' if passed else 'failed',
        'tests': result.testsRun if result else 0,
        'failures': len(result.failures) if result else 0,
        'errors': len(result.errors) if result else 0,
        'network_attempts': len(attempts), 'runner_error': error,
        'python': sys.version, 'versions': versions,
        'guard_includes_imports': True,
        'real_llm_requests': 0, 'real_embedding_requests': 0,
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
