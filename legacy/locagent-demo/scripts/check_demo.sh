#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
TMPDIR="$("$PYTHON" -B -c 'import pathlib,tempfile; print(pathlib.Path(tempfile.gettempdir()).resolve())')"
export TMPDIR
export PYTHONPATH="$PWD:$PWD/tests"
export PYTHONDONTWRITEBYTECODE=1 LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
unset DEEPSEEK_API_KEY OPENAI_API_KEY DASHSCOPE_API_KEY ANTHROPIC_API_KEY
"$PYTHON" -B -m locagent_service.local --help >/dev/null
"$PYTHON" -B -m locagent_service.local demo
"$PYTHON" -B -m unittest test_local_cli test_local_web test_public_authorization test_public_pipeline test_demo_packaging test_key_setup -v
sh -n start-local-web.command
sh -n configure-api-key.command
if [ -n "${LOCAGENT_NODE:-}" ]; then NODE="$LOCAGENT_NODE"
elif command -v node >/dev/null 2>&1; then NODE=node
else printf '%s\n' 'SKIP: Node is unavailable; frontend tests were not run. Set LOCAGENT_NODE to run them.'; exit 0
fi
"$NODE" --check locagent_service/local_web_assets/app.js
"$NODE" --test tests/local_web_ui.test.cjs
