#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
export LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
"$PYTHON" -B -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
case "${1:-}" in
  "") ;;
  --postgres)
    "$PYTHON" -B tests/run_stage2_acceptance.py --pattern stage3_postgres_acceptance.py
    ;;
  --compose)
    docker compose build
    "$PYTHON" -B tests/run_stage5_compose.py
    ;;
  *) printf '%s\n' 'Usage: check_local.sh [--postgres|--compose]' >&2; exit 2 ;;
esac
