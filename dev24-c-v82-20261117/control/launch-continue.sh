#!/usr/bin/env bash
set -u
cd /home/ubuntu/dev24-c-v82-20261117
PY=/home/ubuntu/e2e-cloud-smoke-v2/.venv-cloud/bin/python
export PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
umask 077
trap 'rm -f /home/ubuntu/.config/locagent/C-v82.env' EXIT
"$PY" control/observe.py >> observer-console.log 2>&1 &
observer=$!
"$PY" control/continue_uncapped.py --output run --credentials /home/ubuntu/.config/locagent/C-v82.env --authorization authorization.json --amendment authorization-amendment.json >> run-console.log 2>&1
result=$?
printf '%s\n' "$result" > run.exit
wait "$observer"
exit "$result"
