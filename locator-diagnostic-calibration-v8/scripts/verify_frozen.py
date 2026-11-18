"""Read-only verification of this new freeze and selected original B dependencies."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
freeze = json.loads((ROOT/'FREEZE.json').read_text())
actual = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in freeze['files']}
assert actual == freeze['files'], 'frozen_file_changed'
binding = hashlib.sha256(json.dumps(actual, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
assert binding == freeze['v8_code_and_config_binding'], 'binding_changed'
comparison = json.loads((ROOT/'delivery/B-C-COMPARISON.json').read_text())
for row in comparison['baseline_files']:
    original = ROOT.parent/'cloud-checkpoint-20261117-v4/runtime'/row['path']
    assert hashlib.sha256(original.read_bytes()).hexdigest() == row['B_sha256']
for p, expected in comparison['historical_freezes_sha256'].items():
    assert hashlib.sha256((ROOT.parent/p).read_bytes()).hexdigest() == expected
print(json.dumps({'status': 'passed', 'frozen_files': len(actual),
                  'original_B_files_unchanged': len(comparison['baseline_files']),
                  'historical_freezes_unchanged': len(comparison['historical_freezes_sha256']),
                  'v8_binding': binding}, indent=2))
