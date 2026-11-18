#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
PROJECT_ROOT=$(cd -- "$TASK_ROOT/.." && pwd)
[[ ! -e "$TASK_ROOT/.venv" ]] || { echo '.venv exists; refusing overwrite'; exit 1; }
TASK_PYTHON=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["host"]["bootstrap_python"])' "$PROJECT_ROOT/project_config.json")
"$TASK_PYTHON" -m venv "$TASK_ROOT/.venv"
"$TASK_ROOT/.venv/bin/python" -m pip install --no-index --find-links "$PROJECT_ROOT/vendor/wheels" --require-hashes -r "$PROJECT_ROOT/requirements-offline.lock"
"$TASK_ROOT/.venv/bin/python" -m pip install -r "$TASK_ROOT/config/requirements-cloud.lock"
"$TASK_ROOT/.venv/bin/python" -m pip check
