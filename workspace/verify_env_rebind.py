"""Read-only scope check plus frozen non-secret evidence; never reads .env bytes."""
import hashlib
import json
from pathlib import Path

from readonly_agent.authority import Authority, current_plan, save_new
from readonly_agent.core import digest
from readonly_agent.journal import Ledger
from readonly_agent.live_run import pilot
from readonly_agent.local_env import check_metadata, select_path

old_hash = 'fb1fca68df8be5273ab7d458a44f0075c614f24c7599ba5927e1cf940b925b9f'
new_hash = '5cb8a59ad54ba444acf50b9015236b396645254094b493e3a3cbee60decdf8b2'
authority = Authority()
old = authority.read(old_hash, fresh=False)
old_folder = authority.folder(old_hash)
assert not (old_folder/'claim.json').exists() and not (old_folder/'run').exists()
assert not authority.folder(new_hash).exists()
_, _, plan = pilot('crossfile')
current_plan(plan)
assert digest(plan) == new_hash
assert [k for k in old['plan'] if old['plan'][k] != plan[k]] == ['runtime_hash']

# Reverse only the exact reviewed .env-related edits in memory. Matching the old
# aggregate runtime hash proves all other runtime files remain byte-identical.
source = Path('readonly_agent/live_run.py').read_text()
pairs = [
    ('    # Worker receives credentials only on stdin, never from args/env/SDK config;\n'
     "    # it does not read or persist the parent's optional local .env.\n",
     '    # No credentials in arguments, environment, persistent files or SDK config.\n'),
    ("def run_pair(plan_hash, *, live=False, prompt_api_key=False, env_api_key=False, case_name='greeting'):\n"
     "    if live is not True or (prompt_api_key is True) == (env_api_key is True):\n"
     "        raise PermissionError('explicit_live_and_one_key_source_required')\n",
     "def run_pair(plan_hash, *, live=False, prompt_api_key=False, case_name='greeting'):\n"
     "    if live is not True or prompt_api_key is not True:\n"
     "        raise PermissionError('explicit_live_and_local_key_prompt_required')\n"),
    ("    # Read the local secret only after current grant, plan and TTY checks.\n"
     "    # Never export it to the environment or import legacy paid settings.\n"
     "    if env_api_key:\n"
     "        from .local_env import load_selected_key\n"
     "        key = load_selected_key()\n"
     "    else:\n"
     "        import warnings\n"
     "        with warnings.catch_warnings():\n"
     "            warnings.simplefilter('error', getpass.GetPassWarning)\n"
     "            key = getpass.getpass('DeepSeek API key (hidden, memory only): ')\n",
     "    # Do not accept env/file/CLI keys. No fallback to echoing stdin.\n"
     "    import warnings\n"
     "    with warnings.catch_warnings():\n"
     "        warnings.simplefilter('error', getpass.GetPassWarning)\n"
     "        key = getpass.getpass('DeepSeek API key (hidden, memory only): ')\n"),
    ("    key_source = parser.add_mutually_exclusive_group()\n"
     "    key_source.add_argument('--prompt-api-key', action='store_true')\n"
     "    key_source.add_argument('--env-api-key', action='store_true',\n"
     "                            help='Read the private local .env after authorization checks.')\n",
     "    parser.add_argument('--prompt-api-key', action='store_true')\n"),
    ("                                  env_api_key=args.env_api_key, case_name=args.case), indent=2))\n",
     "                                  case_name=args.case), indent=2))\n"),
]
for new, previous in pairs:
    assert source.count(new) == 1
    source = source.replace(new, previous)
hashes = {p.name: hashlib.sha256(source.encode() if p.name == 'live_run.py' else p.read_bytes()).hexdigest()
          for p in sorted(Path('readonly_agent').glob('*.py')) if p.name != 'local_env.py'}
assert digest(hashes) == old['plan']['runtime_hash']
selected = check_metadata(select_path())
expected = json.loads(Path('verification/RETRIEVAL_DESCRIPTION_APPROVED_PREFLIGHT.json').read_text())['historical_ledgers']
for item in expected:
    path = Path('authority')/item['plan_hash']/'run/ledger.sqlite'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
    assert Ledger(path, item['plan_hash']).summary()['reserved_micro_cny'] == 0
out = Path('verification/env-rebound-v1')
out.mkdir(mode=0o700, exist_ok=False)
save_new(out/'proposal.json', plan)
save_new(out/'preflight.json', {
    'old_plan_hash': old_hash, 'new_plan_hash': new_hash,
    'only_plan_change': 'runtime_hash', 'reverse_patch_matches_old_runtime': True,
    'changed_runtime_files': ['live_run.py', 'local_env.py (added)'],
    'old_grant_sha256': hashlib.sha256((old_folder/'grant.json').read_bytes()).hexdigest(),
    'old_trial_not_started': True, 'old_authorization_unclaimed': True,
    'existing_env_path': str(selected), 'env_contents_read_during_preflight': False,
    'env_metadata_accepted': True, 'all_historical_ledgers_unchanged': True,
    'all_historical_pending_reservations_zero': True,
    'pricing_source': 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
    'pricing_checked_date_Asia_Shanghai': '2026-11-12',
    'peak_input_miss_cny_per_million': 2, 'peak_output_cny_per_million': 8,
    'max_requests': 8, 'budget_cny': 17, 'full_reservations_cny': 16.842752})
print('Scope verified: only reviewed .env changes; frozen proposal saved; old trial unstarted.')
