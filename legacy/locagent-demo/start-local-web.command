#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -n "${LOCAGENT_PYTHON:-}" ]; then PY="$LOCAGENT_PYTHON"
elif [ -x .venv/bin/python ]; then PY=.venv/bin/python
elif [ -x .venv-local/bin/python ]; then PY=.venv-local/bin/python
else printf '%s\n' 'Install requirements-runtime.txt in .venv, or set LOCAGENT_PYTHON first.' >&2; exit 2
fi
export PYTHONDONTWRITEBYTECODE=1 LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
if [ -f provider.local.json ]; then
 exec "$PY" -B -m locagent_service.local_web serve --provider-config provider.local.json "$@"
else
 exec "$PY" -B -m locagent_service.local_web serve "$@"
fi
