#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir/workspace"
export PYTHONDONTWRITEBYTECODE=1 DO_NOT_TRACK=1 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
exec .venv-openhands/bin/python -B -m unittest discover -s tests -p 'test_sdk_selfcheck_v7_*.py' -v
