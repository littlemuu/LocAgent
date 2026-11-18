#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$TASK_ROOT"
RUN=verification/cloud-smoke-run-v2
[[ ! -e "$RUN" ]] || { echo 'Existing run must not be automatically retried'; exit 1; }
[[ -f verification/cloud-preflight.json && -f verification/cloud-container-check.json ]] || { echo 'Prerequisites missing'; exit 1; }
.venv-cloud/bin/python - <<'PY'
import json
for name in ['cloud-preflight','cloud-container-check']:
 assert json.load(open('verification/'+name+'.json'))['status']=='passed'
from locagent_e2e.driver import config_binding
from locagent_e2e.common import write_json,CONFIG
assert CONFIG['formal_trial_authorized'] is False and CONFIG['smoke_max_cny']==8.75
write_json('verification/cloud-run-start.json',{'code_binding':config_binding(),'formal_trial_authorized':False})
PY
trap 'rm -f /home/ubuntu/.config/locagent/smoke.env' EXIT
set +e
PYTHONPATH=. .venv-cloud/bin/python -m locagent_e2e.driver smoke --output "$RUN" --credentials /home/ubuntu/.config/locagent/smoke.env
RESULT=$?
set -e
.venv-cloud/bin/python scripts/summarize_smoke.py --run "$RUN" --output verification/cloud-smoke-summary.json
printf '%s\n' "$RESULT" > verification/cloud-smoke-exit-code.txt
exit "$RESULT"
