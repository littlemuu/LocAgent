#!/usr/bin/env bash
set -u
cd /home/ubuntu/dev24-locator-v81-20261117
export PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
umask 077
trap 'rm -f /home/ubuntu/.config/locagent/locator-v81.env' EXIT
/home/ubuntu/e2e-cloud-smoke-v2/.venv-cloud/bin/python control/run_locator.py --output run --credentials /home/ubuntu/.config/locagent/locator-v81.env --authorization authorization.json > run-console.log 2>&1
result=$?
printf '%s\n' "$result" > run.exit
exit "$result"
