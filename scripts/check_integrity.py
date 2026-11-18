import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'migration/copied-files.json').read_text())
for r in manifest['files']:
 p=root/r['destination']
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:
  raise SystemExit('Changed or missing: '+r['destination'])
for name in ['raw-run-lock.json','result-lock.json']:
 lock=json.loads((root/'workspace/verification/sdk-finish-selfcheck-v7-live'/name).read_text())
 for relative,h in lock['files'].items():
  assert hashlib.sha256((root/'workspace'/relative).read_bytes()).hexdigest()==h,relative
print('Verified',len(manifest['files']),'copied files and both v7 locks; no network or credential access.')
