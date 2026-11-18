#!/usr/bin/env bash
set -u
cd /home/ubuntu/dev24-c-v8-20261117
PY=/home/ubuntu/e2e-cloud-smoke-v2/.venv-cloud/bin/python
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1
export HF_DATASETS_OFFLINE=1
umask 077
trap 'rm -f /home/ubuntu/.config/locagent/C-v8.env' EXIT
"$PY" control/observe.py > observer-console.log 2>&1 &
observer=$!
"$PY" control/run_c.py --output run --credentials /home/ubuntu/.config/locagent/C-v8.env --authorization authorization.json > run-console.log 2>&1
result=$?
printf '%s\n' "$result" > run.exit
wait "$observer"
exit "$result"
