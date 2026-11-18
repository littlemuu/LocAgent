"""Run the ORIGINAL 22 tests or new calibration tests with process-wide fences."""
import sys, os, json, unittest, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'baseline'), str(ROOT/'baseline/tests'), str(ROOT/'baseline/runtime')]
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
blocked = []
def fence(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system'):
        blocked.append(event)
        raise RuntimeError('offline_fence:' + event)
    if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
        p = os.fsdecode(args[0])
        if 'holdout' in p.casefold():
            # Original negative test intentionally attempts a fake forbidden path.
            raise PermissionError('holdout_content_forbidden')
sys.addaudithook(fence)
mode = sys.argv[1] if len(sys.argv) > 1 else 'new'
assert mode in ('baseline', 'new')
suite = unittest.defaultTestLoader.discover(str(ROOT/('baseline/tests' if mode == 'baseline' else 'tests')))
start = time.monotonic()
result = unittest.TextTestRunner(verbosity=2).run(suite)
summary = dict(suite=mode, tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
               skipped=len(result.skipped), blocked_external_actions=blocked, api_calls=0,
               elapsed_seconds=time.monotonic()-start, quality_measured=False)
(ROOT/f'delivery/{mode}-tests.json').write_text(json.dumps(summary, indent=2)+'\n')
sys.exit(0 if result.wasSuccessful() and not blocked else 1)
