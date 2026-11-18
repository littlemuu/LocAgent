#!/usr/bin/env bash
# Run manually on a dedicated Ubuntu 24.04 x86 host. No model/task run is launched.
set -euo pipefail
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || { echo 'Requires Linux x86_64'; exit 1; }
TASK_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
[[ $(getconf _NPROCESSORS_ONLN) -ge 8 ]] || { echo 'Need at least 8 logical CPUs'; exit 1; }
# Host target 16 GiB and ~150 GB disk. Validate resources before downloading images.
awk '/MemTotal/ { if ($2 < 15000000) exit 1 }' /proc/meminfo || { echo 'Need approximately 16 GB RAM'; exit 1; }
FREE_KIB=$(df -Pk "$TASK_ROOT" | awk 'NR==2 {print $4}')
[[ "$FREE_KIB" -ge 100000000 ]] || { echo 'Need >=100 GB free; target disk about 150 GB'; exit 1; }
sudo apt-get update
sudo apt-get install -y docker.io git python3.12 python3.12-venv python3-dev build-essential curl ca-certificates
sudo systemctl enable --now docker
python3.12 -m venv "$TASK_ROOT/.venv-cloud"
"$TASK_ROOT/.venv-cloud/bin/python" -m pip install --requirement "$TASK_ROOT/config/requirements-cloud.lock"
"$TASK_ROOT/.venv-cloud/bin/python" -m pip check
"$TASK_ROOT/.venv-cloud/bin/python" -m pip freeze > "$TASK_ROOT/cloud-installed.lock"
sudo docker version > "$TASK_ROOT/cloud-docker-version.txt"
echo 'Setup only completed. Run preflight and offline tests before any smoke. Do not run as a root coding agent on the host.'
echo 'Docker access requires an appropriate account/socket policy. Agent commands execute only in isolated containers.'
